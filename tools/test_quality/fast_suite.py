#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fast_report.py 对快速测试层的测量：载入并计时、在本进程里记下变异测试的测试执行到的行、汇总变异缓存。"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from typing import Any

import coverage
from lint import config
from lint import core
from lint.rules import mutation_engine
from lint.rules import mutation_rule


def test_rels(ctx: core.Context, rc: config.RuleConfig) -> list[str]:
  """返回 tests-mutation 导入的测试模块。"""
  globs = rc.strs('test_globs')
  return [f for f in ctx.repo_files() if core.matches_any(f, globs)]


def measure_suite(ctx: core.Context, rc: config.RuleConfig) -> dict[str, Any]:
  """在本进程里载入 tests-mutation 列出的测试文件，并给其中的测试整套计一次时。

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
  """返回缓存目录的 coverage.json 里每个源文件执行过的行。

  tests-mutation 之后，这份文件里是 measure_mutation_lines 记下的行。
  """
  data = json.loads((ctx.cache_dir / 'coverage.json').read_text('utf-8'))
  return {
      rel: set(info.get('executed_lines', []))
      for rel, info in data.get('files', {}).items()
      if isinstance(info, dict)
  }


def measure_mutation_lines(
    ctx: core.Context, cov_rc: config.RuleConfig, mut_rc: config.RuleConfig
) -> None:
  """在本进程里把 tests-mutation 的测试文件整套跑一次，把执行到的行写进缓存目录的 coverage.json。

  tests-mutation 只改 coverage.json 里列出的行。变异体运行执行不到的行上，变异体不可能被杀掉。
  变异体运行从本进程已载入的状态开始，跑法与这里相同。所以这里记下的行不含只在载入时执行的行，
  也不含只有没列出的测试文件才执行的行。

  Args:
    ctx: 被查 checkout 的 lint Context。
    cov_rc: tests-coverage 的设置，记下它的 source 里各文件夹的行。
    mut_rc: tests-mutation 的设置，跑它的 test_globs 列出的测试文件。

  Raises:
    RuntimeError: 没变异的整套测试没有通过。
  """
  suite = mutation_engine.load_test_suites_fn(test_rels(ctx, mut_rc))('')
  cov = coverage.Coverage(
      data_file=None,
      config_file=False,
      source=[str(ctx.root / s) for s in cov_rc.strs('source')],
  )
  cov.start()
  try:
    passed = mutation_engine.suite_passes(suite, 600.0)
  finally:
    cov.stop()
  if not passed:
    raise RuntimeError('the unmutated suite failed; see fast-layer load')
  data = cov.get_data()
  files = {
      os.path.relpath(path, ctx.root): {
          'executed_lines': sorted(data.lines(path) or [])
      }
      for path in data.measured_files()
  }
  out = json.dumps({'files': files}, indent=1, sort_keys=True)
  (ctx.cache_dir / 'coverage.json').write_text(out + '\n', encoding='utf-8')


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
