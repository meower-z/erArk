#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
只出报告：在游戏的快速测试层 tests/fast 上跑三条测试质量规则。

三条规则是 lint 引擎的 tests-coverage（覆盖率）、
tests-assertions（测试函数自己的代码里有没有断言）与 tests-mutation（变异测试的击杀率），
设置在被查的 checkout 的 pyproject.toml 的 [tool.test-quality]。
变异测试只用设置里列出的测试文件。本进程载入这些文件之后，把其中的测试整套跑一次，
记下执行到的行。变异测试只改这些行。
lint 引擎是可选的本机工具，不随仓库提供（见 CONTRIBUTING.md）。
用游戏的 venv 的 python 运行，它要装 coverage，
并且要能导入 lint 引擎的 lint 包（例如用 PYTHONPATH 指向含 lint 的目录）。
在 checkout 根目录经 tools/verify/limited_run.py 运行，命令里的 python 指游戏的 venv：

  PYTHONPATH=<含 lint 的目录> python tools/verify/limited_run.py \\
      --mem 4G --timeout 1800 -- python -B -u \\
      tools/test_quality/fast_report.py . [--report 文件]

-B 让 Python 不给导入的任何模块写字节码，checkout 里就不会出现 __pycache__ 目录。

任何一步运行之前，先列出 checkout 的 data/ 下被 git 忽略的未跟踪文件。有这样的文件、或 git 列不出来时拒绝运行：
把原因打印到 stderr（有文件时附上清理命令），不写报告，退出码 2。游戏会直接读 data/ 里已生成的文件，不再运行生成它们的代码，
所以在生成过的 data/ 上运行，覆盖率那一步就记不到生成数据的代码执行过。先用
`git -C <checkout> clean -fdX data/` 清理 data/。

每一步打印一行摘要，完整报告写到 --report 给的文件（默认是缓存目录里的 report.md）。缓存目录是
~/.cache/era-lint/<checkout 路径的哈希>/，存放覆盖率数据和变异测试的结果，
每次运行开始时清掉上一次的。按上面的命令带 -B 运行时，本脚本自己的代码不往 checkout 里写东西。
但快速测试层运行的游戏代码可能生成 data/ 下被忽略的文件，那样下一次运行会拒绝，直到再清理 data/。

不论规则查出什么，退出码都是 0，规则崩溃或超时也一样。只有参数错误和 data/ 检查拒绝时退出码是 2。
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import dataclasses
import hashlib
import json
import os
import pathlib
import sys
import time
import tomllib
import traceback
import types
from typing import Any

from lint import cli
from lint import config
from lint import core

import data_check
import fast_suite

SETTINGS_TABLE = 'test-quality'
FAST_DIR = 'tests/fast'
# 按这个顺序运行。tests-mutation 等本进程记下它的测试执行到的行之后才运行
RULE_IDS = ('tests-coverage', 'tests-assertions', 'tests-mutation')


@dataclasses.dataclass
class Step:
  """运行中一步的结果。"""

  name: str
  seconds: float = 0.0
  crash: str = ''
  outcome: core.Outcome | None = None
  notes: list[str] = dataclasses.field(default_factory=list)


def cache_dir_for(checkout: pathlib.Path) -> pathlib.Path:
  """返回 ~/.cache/era-lint/<checkout 路径哈希的前 16 个十六进制位>。"""
  key = hashlib.sha256(str(checkout.resolve()).encode('utf-8')).hexdigest()
  return pathlib.Path.home() / '.cache' / 'era-lint' / key[:16]


def build_config(
    checkout: pathlib.Path, cache_dir: pathlib.Path
) -> dict[str, Any]:
  """返回 lint 的默认设置合并 checkout 的 pyproject.toml 里 [tool.test-quality] 之后的结果。

  Args:
    checkout: 被查的 checkout 根目录。
    cache_dir: 缓存目录的绝对路径；Context 把它原样接在根目录后面。

  Returns:
    这个 checkout 的 lint 设置。
  """
  with open(checkout / 'pyproject.toml', 'rb') as f:
    settings = tomllib.load(f)['tool'][SETTINGS_TABLE]
  cfg = config.deep_merge(config.DEFAULTS, settings)
  over = {
      'paths': {'cache_dir': str(cache_dir)},
      'tools': {
          'python': [sys.executable],
          'coverage': [sys.executable, '-m', 'coverage'],
      },
  }
  merged: dict[str, Any] = config.deep_merge(cfg, over)
  return merged


@dataclasses.dataclass
class _CrashRecorder:
  """with 块的用时记在 step.seconds 上；块里的异常记在 step.crash 上并接住。

  KeyboardInterrupt 照常抛出。erArk 不许用 `# pylint:` 注释，
  所以接住所有异常写成 __exit__，不写成 except BaseException。
  """

  step: Step
  start: float = 0.0

  def __enter__(self) -> None:
    """记下开始时间。"""
    self.start = time.monotonic()

  def __exit__(
      self,
      exc_type: type[BaseException] | None,
      exc: BaseException | None,
      tb: types.TracebackType | None,
  ) -> bool:
    """记下用时；有异常且不是 KeyboardInterrupt 时记下它，返回 True 接住它。"""
    self.step.seconds = time.monotonic() - self.start
    if exc is None or isinstance(exc, KeyboardInterrupt):
      return False
    lines = traceback.format_exception(exc_type, exc, tb)
    tail = ''.join(lines).strip().splitlines()[-6:]
    self.step.crash = '\n'.join([f'{type(exc).__name__}: {exc}', *tail])
    return True


def run_step(step: Step, fn: Callable[[], Any]) -> Any:
  """运行 fn，把用时和抛出的异常记在 step 上。

  除了 KeyboardInterrupt，所有异常都接住，SystemExit 和变异引擎的超时这类
  BaseException 子类也一样，所以规则的结果改变不了退出码。

  Returns:
    fn 的返回值；fn 抛出异常时返回 None。
  """
  value = None
  with _CrashRecorder(step):
    value = fn()
  return value


def _coverage_notes(ctx: core.Context, rc: config.RuleConfig) -> list[str]:
  """返回总覆盖率与规则的阈值。"""
  data = json.loads((ctx.cache_dir / 'coverage.json').read_text('utf-8'))
  totals = data.get('totals', {})
  return [
      f"coverage {float(totals.get('percent_covered', 0.0)):.1f}%"
      f" ({totals.get('covered_lines', 0)}/{totals.get('num_statements', 0)}"
      f" statements in {len(data.get('files', {}))} files under"
      f" {', '.join(rc.strs('source'))}); abs_min {rc.num('abs_min', 75):g},"
      f" abs_warn {rc.num('abs_warn', 90):g}"
  ]


def _fast_notes(fast: dict[str, Any], rc: config.RuleConfig) -> list[str]:
  """说明本进程里的载入与计时的那次整套运行。"""
  limit = rc.num('mutant_timeout', 0.25)
  notes = [
      f"{fast['tests']} tests; load {fast['load_s']:.1f} s once in this"
      f" process; one suite run {fast['suite_s']:.2f} s"
      f" (mutant_timeout {limit:g} s); passed: {fast['passed']}"
  ]
  if fast['suite_s'] > limit:
    notes.append('the suite run is longer than mutant_timeout')
  return notes


def mutation_notes(ctx: core.Context, rc: config.RuleConfig) -> list[str]:
  """返回击杀率与阈值，再列出每个存活的变异体。"""
  totals = fast_suite.mutation_totals(ctx, rc)
  total = totals['total']
  pct = 100.0 * totals['killed'] / total if total else 0.0
  return [
      f"kill rate {pct:.1f}% ({totals['killed']}/{total});"
      f" score_min {rc.num('score_min', 75):g},"
      f" score_warn {rc.num('score_warn', 85):g};"
      f" {len(totals['survived'])} survivors;"
      f" {totals['evaluated_files']} of {totals['files']} files evaluated,"
      f" {totals['baseline_failed']} of them not scored (unmutated suite"
      ' failed or exceeded mutant_timeout)',
      *[f'survived: {s}' for s in totals['survived']],
  ]


def _render(head: list[str], steps: list[Step]) -> str:
  """生成完整的 Markdown 报告。"""
  out = ['# erArk fast-layer lint report', '', *head]
  for step in steps:
    out += ['', f'## {step.name} ({step.seconds:.1f} s)', '']
    out += [f'- {n}' for n in step.notes]
    if step.outcome is not None:
      out += [f'- skipped: {step.outcome.skipped}'] * bool(step.outcome.skipped)
      for kind, items in (
          ('error', step.outcome.errors),
          ('warning', step.outcome.warnings),
      ):
        out += [f'- {kind}: {i}'.replace('\n', '\n  ') for i in items]
    if step.crash:
      out += ['- crashed:', '', '```text', step.crash, '```']
  return '\n'.join(out) + '\n'


def _headline(step: Step) -> str:
  """返回摘要里一步结果的第一行。"""
  if step.crash:
    first = 'crashed: ' + step.crash.splitlines()[0]
  elif step.outcome is not None and step.outcome.skipped:
    first = 'skipped: ' + step.outcome.skipped
  elif step.notes:
    first = step.notes[0]
  elif step.outcome is not None and step.outcome.errors:
    first = step.outcome.errors[0].splitlines()[0]
  else:
    first = 'ok'
  out = step.outcome
  if out is not None and (out.errors or out.warnings):
    first += f' [{len(out.errors)} errors, {len(out.warnings)} warnings]'
  return f'{step.name} ({step.seconds:.1f} s): {first}'


def _parse(argv: list[str]) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
  """返回 (checkout, 缓存目录, 报告文件)；参数错误时退出码 2。"""
  p = argparse.ArgumentParser(
      description="Report-only lint run on an erArk checkout's tests/fast."
  )
  p.add_argument('checkout', type=pathlib.Path, help='erArk checkout root')
  p.add_argument('--report', type=pathlib.Path, help='full report file')
  args = p.parse_args(argv)
  checkout = args.checkout.resolve()
  if not (checkout / FAST_DIR).is_dir():
    p.error(f'{checkout} has no {FAST_DIR}/ folder')
  cache_dir = cache_dir_for(checkout)
  report = (args.report or cache_dir / 'report.md').resolve()
  for path in (cache_dir, report):
    if path.is_relative_to(checkout):
      p.error(f'{path} is inside the checkout')
  return checkout, cache_dir, report


class FastRun:
  """一次运行：各步、它们的结果和报告文件。"""

  def __init__(
      self,
      checkout: pathlib.Path,
      cache_dir: pathlib.Path,
      report: pathlib.Path,
  ) -> None:
    """读设置、载入规则，准备好报告的开头。"""
    cfg = build_config(checkout, cache_dir)
    self.registry = cli.load_rules()
    self.ctx = core.Context(checkout, cfg)
    self.rcs = {r: self.ctx.rule_config(self.registry[r]) for r in RULE_IDS}
    self.report = report
    self.head = [
        f'- checkout: {checkout}',
        f'- python: {sys.executable}',
        f'- settings: pyproject.toml [tool.{SETTINGS_TABLE}]; thresholds are'
        ' the rule defaults',
        f'- cache: {cache_dir}',
    ]
    self.steps: list[Step] = []
    self.start = time.monotonic()

  def write_report(self, finished: bool) -> None:
    """用目前为止的各步和运行状态重写报告。

    开始时和每一步之后都重写报告，所以运行被外部杀掉（limited_run 的时限或内存上限）时，
    留下的是这次运行标着未完成的部分报告，而不是上一次运行的报告。
    """
    status = 'finished' if finished else 'unfinished (still running or killed)'
    total = f'{time.monotonic() - self.start:.1f} s'
    head = [*self.head, f'- status: {status}', f'- wall time: {total}']
    self.report.write_text(_render(head, self.steps), encoding='utf-8')

  def step(self, name: str, fn: Callable[[Step], Any]) -> Any:
    """运行有保护的一步，再重写报告。"""
    step = Step(name)
    self.steps.append(step)
    value = run_step(step, lambda: fn(step))
    self.write_report(finished=False)
    return value

  def rule(
      self,
      step: Step,
      notes: Callable[[core.Context, config.RuleConfig], list[str]],
  ) -> None:
    """运行名为 step.name 的规则，再加上 notes(ctx, 规则设置)。"""
    rc = self.rcs[step.name]
    step.outcome = self.registry[step.name].fn(self.ctx, rc)
    step.notes += notes(self.ctx, rc)

  def measure(self, step: Step) -> dict[str, Any]:
    """在本进程里载入 tests-mutation 列出的测试文件，并给其中的测试整套计一次时。"""
    rc = self.rcs['tests-mutation']
    fast = fast_suite.measure_suite(self.ctx, rc)
    step.notes += _fast_notes(fast, rc)
    return fast

  def mutation(self, step: Step) -> None:
    """在本进程里记下 tests-mutation 的测试文件执行到的行，再运行 tests-mutation。"""
    fast_suite.measure_mutation_lines(
        self.ctx, self.rcs['tests-coverage'], self.rcs['tests-mutation']
    )
    self.rule(step, mutation_notes)

  def run(self) -> None:
    """按顺序运行每一步；哪一步失败都不挡后面的步。"""
    self.write_report(finished=False)
    self.step('tests-coverage', lambda s: self.rule(s, _coverage_notes))
    self.step('tests-assertions', lambda s: self.rule(s, lambda c, r: []))
    self.step('fast-layer load', self.measure)
    self.step('tests-mutation', self.mutation)
    self.write_report(finished=True)

  def print_summary(self) -> None:
    """每步打印一行，最后打印总用时和报告路径。"""
    for step in self.steps:
      print(_headline(step))
    total = time.monotonic() - self.start
    print(f'total {total:.1f} s; report: {self.report}')


def main(argv: list[str], quiet: bool = False) -> int:
  """运行本脚本，见模块说明。

  Args:
    argv: 命令行参数（不含程序名）。
    quiet: 是否不打印摘要（供测试用）。

  Returns:
    data/ 检查拒绝时返回 2，在任何一步之前；其余情况返回 0。
    参数错误时 argparse 以 2 退出，同样在任何一步之前。
  """
  checkout, cache_dir, report = _parse(argv)
  reason = data_check.refuse_reason(checkout)
  if reason:
    print(f'fast_report.py: {reason}', file=sys.stderr)
    return 2
  # 从这里起导入的模块和子进程（例如 tests-coverage 运行的 coverage）都不写字节码
  # 本脚本自己的模块在这之前已经导入，它们靠命令里的 -B 不写字节码
  sys.dont_write_bytecode = True
  os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
  cache_dir.mkdir(parents=True, exist_ok=True)
  report.parent.mkdir(parents=True, exist_ok=True)
  # 留着旧的 coverage.json，tests-mutation 就可能按上一次运行的行来跑；
  # 变异缓存的键不含执行过的行，留着它，执行过的行变了也会沿用上一次的结果
  for name in ('coverage.json', 'mutation_cache.json'):
    (cache_dir / name).unlink(missing_ok=True)
  fast_run = FastRun(checkout, cache_dir, report)
  fast_run.run()
  if not quiet:
    fast_run.print_summary()
  return 0


if __name__ == '__main__':
  sys.exit(main(sys.argv[1:]))
