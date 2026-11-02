#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fast_report.py 对快速测试层的测量：载入并计时、为变异测试重测执行过的行、汇总变异缓存。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from typing import Any

from lint import config
from lint import core
from lint.rules import mutation_engine
from lint.rules import mutation_rule


def test_rels(ctx: core.Context, rc: config.RuleConfig) -> list[str]:
  """返回 tests-mutation 导入的测试模块。"""
  globs = rc.strs('test_globs')
  return [f for f in ctx.repo_files() if core.matches_any(f, globs)]


def measure_suite(ctx: core.Context, rc: config.RuleConfig) -> dict[str, Any]:
  """在本进程里载入快速测试层，并给整套测试计一次时。

  导入 tests/fast 时，每个进程载入一次 erArk 的 MinimalWorld。之后 tests-mutation
  从 sys.modules 取同样的模块，它 fork 出的工作进程继承这个世界，不再各自载入。
  计时用的运行器与 tests-mutation 每个变异体用的相同，时限远高于任何一次整套运行：
  这一步只量时间，不下判断。
  """
  if str(ctx.root) not in sys.path:
    sys.path.insert(0, str(ctx.root))
  start = time.monotonic()
  suites = mutation_engine.load_test_suites_fn(test_rels(ctx, rc))
  load_s = time.monotonic() - start
  suite = suites('')
  start = time.monotonic()
  passed = mutation_engine.suite_passes(suite, 600.0)
  return {
      'tests': suite.countTestCases(),
      'load_s': load_s,
      'suite_s': time.monotonic() - start,
      'passed': passed,
  }


def covered_lines(ctx: core.Context) -> dict[str, set[int]]:
  """返回 tests-coverage 记下的每个源文件执行过的行。"""
  data = json.loads((ctx.cache_dir / 'coverage.json').read_text('utf-8'))
  return {
      rel: set(info.get('executed_lines', []))
      for rel, info in data.get('files', {}).items()
      if isinstance(info, dict)
  }


def remeasure_for_mutation(
    ctx: core.Context, cov_rc: config.RuleConfig, mut_rc: config.RuleConfig
) -> None:
  """只用 tests-mutation 的测试文件重测一次覆盖率，覆盖缓存里的 coverage.json。

  tests-mutation 只变异 coverage.json 里执行过的行。那份数据来自整个 tests/fast；
  只有没列进 tests-mutation 的测试才执行的行上，变异体不可能被杀掉，会算成存活。

  Raises:
    RuntimeError: coverage 运行失败；消息里带着它最后 20 行输出。
  """
  cov = ctx.tool('coverage')
  modules = [
      rel[: -len('.py')].replace('/', '.') for rel in test_rels(ctx, mut_rc)
  ]
  env = dict(
      os.environ, COVERAGE_FILE=str(ctx.cache_dir / '.coverage-mutation')
  )
  source = ','.join(cov_rc.strs('source'))
  for argv in (
      [*cov, 'run', f'--source={source}', '-m', 'unittest', *modules],
      [*cov, 'json', '-o', str(ctx.cache_dir / 'coverage.json'), '-q'],
  ):
    proc = subprocess.run(
        argv, cwd=ctx.root, env=env, capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
      tail = (proc.stdout + proc.stderr).strip().splitlines()[-20:]
      raise RuntimeError(
          '\n'.join(
              [f'coverage {argv[len(cov)]} exited {proc.returncode}:', *tail]
          )
      )


def mutation_totals(ctx: core.Context, rc: config.RuleConfig) -> dict[str, Any]:
  """把 tests-mutation 各目标文件在变异缓存里的当前条目加起来。

  目标文件有当前的缓存条目就算查过，没变异的整套测试失败、一个变异体也没跑的也算。
  """
  t_sha = mutation_rule.tests_sha(ctx.root, test_rels(ctx, rc))
  covered = covered_lines(ctx)
  sources = set(ctx.targets(rc, sorted(covered)))
  # 目标文件和缓存键的算法与 tests-mutation 选文件、记缓存的相同
  keys = {}
  for rel, lines in sorted(covered.items()):
    path = ctx.root / rel
    if rel in sources and lines and path.is_file():
      keys[rel] = f'{hashlib.sha256(path.read_bytes()).hexdigest()}:{t_sha}'
  cache_p = ctx.cache_dir / 'mutation_cache.json'
  cache = json.loads(cache_p.read_text('utf-8')) if cache_p.is_file() else {}
  done = [
      cache[rel]
      for rel, key in keys.items()
      if (cache.get(rel) or {}).get('sha') == key
  ]
  return {
      'files': len(keys),
      'evaluated_files': len(done),
      'killed': sum(int(r['killed']) for r in done),
      'total': sum(int(r['total']) for r in done),
      'survived': [s for r in done for s in r['survived']],
      'baseline_failed': sum(1 for r in done if r.get('baseline_failed')),
  }
