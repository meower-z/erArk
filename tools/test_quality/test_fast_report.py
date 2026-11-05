#!/usr/bin/env python3
"""
fast_report.py 的测试：设置取自 pyproject.toml、缓存目录、变异测试的统计、只出报告的退出码；
不启动游戏

要能导入 lint 引擎的 lint 包，用法：
    PYTHONPATH=<含 lint 的目录> python3 tools/test_quality/test_fast_report.py
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import unittest
from unittest import mock

from checkout_fixture import make_checkout
from checkout_fixture import PASSING_TEST
from checkout_fixture import REPO
from checkout_fixture import run_adapter
from lint import cli
from lint import core
from lint.rules import mutation_engine
from lint.rules import mutation_rule
import fast_report
import fast_suite


class ConfigTest(unittest.TestCase):
  """生成的设置与缓存目录的位置。"""

  def test_rules_point_at_fast_layer_only(self) -> None:
    """覆盖率与变异测试只看 tests/fast 和 Script，不看 tests/slow。"""
    cfg = fast_report.build_config(REPO, pathlib.Path('/c/era-lint/x'))
    rules = cfg['rules']
    self.assertEqual(rules['tests-coverage']['start_dir'], 'tests/fast')
    self.assertEqual(rules['tests-coverage']['source'], ['Script'])
    self.assertEqual(rules['tests-coverage'].get('omit', []), [])
    self.assertEqual(
        rules['tests-assertions']['test_globs'], ['tests/fast/test_*.py']
    )
    for glob in rules['tests-mutation']['test_globs']:
      self.assertTrue(glob.startswith('tests/fast/test_'), glob)
    self.assertEqual(rules['tests-mutation']['mutant_timeout'], 10.0)
    self.assertLessEqual(rules['tests-mutation']['max_workers'], 3)
    self.assertEqual(cfg['tools']['python'], [sys.executable])
    self.assertEqual(
        cfg['tools']['coverage'], [sys.executable, '-m', 'coverage']
    )

  def test_thresholds_stay_at_rule_defaults(self) -> None:
    """设置里不定阈值，所以用规则的默认值。"""
    cfg = fast_report.build_config(REPO, pathlib.Path('/c/era-lint/x'))
    registry = cli.load_rules()
    ctx = core.Context(pathlib.Path('/c/checkout'), cfg)
    for rid, keys in (
        ('tests-coverage', ('abs_min', 'abs_warn', 'inc_min', 'inc_warn')),
        ('tests-mutation', ('score_min', 'score_warn')),
    ):
      rc = ctx.rule_config(registry[rid])
      for key in keys:
        self.assertNotIn(key, cfg['rules'][rid])
        self.assertEqual(rc.get(key), registry[rid].defaults[key])

  def test_cache_dir_is_outside_checkout(self) -> None:
    """每个 checkout 在 ~/.cache/era-lint/ 下有自己的缓存目录。"""
    with mock.patch.dict(os.environ, {'HOME': '/h'}):
      one = fast_report.cache_dir_for(pathlib.Path('/w/a'))
      two = fast_report.cache_dir_for(pathlib.Path('/w/b'))
    self.assertEqual(one.parent, pathlib.Path('/h/.cache/era-lint'))
    self.assertNotEqual(one, two)
    cfg = fast_report.build_config(REPO, one)
    ctx = core.Context(pathlib.Path('/w/a'), cfg)
    self.assertEqual(ctx.cache_dir, one)


class MutationNotesTest(unittest.TestCase):
  """变异测试的说明把缓存里的当前条目加起来。"""

  def test_not_scored_files_count_as_evaluated_only(self) -> None:
    """没变异的整套测试失败的文件算查过、不计分；过期的条目两样都不算。"""
    checkout = make_checkout(self, PASSING_TEST)
    for name in ('n', 'o'):
      (checkout / f'Script/{name}.py').write_text('def g():\n  return 1\n')
    cache_dir = checkout.parent / 'cache'
    cache_dir.mkdir()
    cfg = fast_report.build_config(checkout, cache_dir)
    ctx = core.Context(checkout, cfg)
    rc = ctx.rule_config(cli.load_rules()['tests-mutation'])
    rels = ['Script/m.py', 'Script/n.py', 'Script/o.py']
    files = {rel: {'executed_lines': [2]} for rel in rels}
    (cache_dir / 'coverage.json').write_text(json.dumps({'files': files}))
    t_sha = mutation_rule.tests_sha(checkout, ['tests/fast/test_a.py'])

    def key(rel: str) -> str:
      digest = hashlib.sha256((checkout / rel).read_bytes()).hexdigest()
      return f'{digest}:{t_sha}'

    scored = {'killed': 1, 'total': 2, 'survived': ['Script/m.py:2 (f:x)']}
    cache = {
        'Script/m.py': {'sha': key('Script/m.py'), **scored},
        'Script/n.py': {
            'sha': key('Script/n.py'),
            'killed': 0,
            'total': 0,
            'survived': [],
            'baseline_failed': True,
        },
        'Script/o.py': {'sha': 'stale', 'killed': 9, 'total': 9},
    }
    (cache_dir / 'mutation_cache.json').write_text(json.dumps(cache))
    notes = fast_report.mutation_notes(ctx, rc)
    self.assertIn('kill rate 50.0% (1/2)', notes[0])
    self.assertIn('2 of 3 files evaluated, 1 of them not scored', notes[0])
    self.assertEqual(notes[1:], ['survived: Script/m.py:2 (f:x)'])


class MutationLinesTest(unittest.TestCase):
  """变异测试要改的行只是列出的测试在载入之后执行到的行。"""

  def lines_after_run(self, checkout: pathlib.Path) -> dict[str, list[int]]:
    """提交 checkout 里新加的文件，跑完 fast_report.py 并确认退出码是 0。

    Returns:
      缓存里 coverage.json 记下的每个文件执行到的行，键是相对 checkout 的路径。
    """
    for cmd in (['add', '-A'], ['commit', '-qm', 'more']):
      subprocess.run(
          ['git', '-c', 'user.name=t', '-c', 'user.email=t@t', *cmd],
          cwd=checkout,
          check=True,
          capture_output=True,
      )
    home = checkout.parent / 'home'
    proc = run_adapter(home, str(checkout))
    self.assertEqual(proc.returncode, 0, proc.stderr)
    cache = next((home / '.cache' / 'era-lint').iterdir())
    data = json.loads((cache / 'coverage.json').read_text('utf-8'))
    return {rel: v['executed_lines'] for rel, v in data['files'].items()}

  def test_lines_run_only_at_import_are_not_targets(self) -> None:
    """只在导入时执行的行，不算变异测试要改的行。"""
    checkout = make_checkout(
        self,
        'import unittest\nfrom Script import build\nfrom Script import m\n'
        'class T(unittest.TestCase):\n'
        '  def test_f(self):\n    self.assertEqual(m.f(1), 2)\n'
        "    self.assertEqual(build.TABLE, {'a': 1})\n",
    )
    (checkout / 'Script/build.py').write_text(
        "def build():\n  return {'a': 1}\nTABLE = build()\n"
    )
    lines = self.lines_after_run(checkout)
    self.assertIn(2, lines['Script/m.py'])
    self.assertNotIn(2, lines.get('Script/build.py', []))

  def test_lines_run_only_by_unlisted_tests_are_not_targets(self) -> None:
    """只有没列进 tests-mutation 的测试执行的行，不算变异测试要改的行。"""
    checkout = make_checkout(
        self,
        'import unittest\nfrom Script import m\n'
        'class T(unittest.TestCase):\n'
        '  def test_f(self):\n    self.assertEqual(m.f(1), 2)\n',
    )
    (checkout / 'Script/n.py').write_text('def g():\n  return 1\n')
    (checkout / 'tests/fast/test_c.py').write_text(
        'import unittest\nfrom Script import n\n'
        'class C(unittest.TestCase):\n'
        '  def test_g(self):\n    self.assertEqual(n.g(), 1)\n'
    )
    settings = checkout / 'pyproject.toml'
    head, sep, tail = settings.read_text('utf-8').rpartition(
        'test_globs = ["tests/fast/test_*.py"]'
    )
    settings.write_text(
        head + 'test_globs = ["tests/fast/test_a.py"]' + tail, 'utf-8'
    )
    self.assertTrue(sep)
    lines = self.lines_after_run(checkout)
    self.assertIn(2, lines['Script/m.py'])
    self.assertNotIn(2, lines.get('Script/n.py', []))


class ReportOnlyTest(unittest.TestCase):
  """不论规则怎样，退出码都是 0；参数错误退出码 2。"""

  def test_rule_crash_still_exits_zero(self) -> None:
    """崩溃的规则和步骤写进报告，后面的步骤照常运行。"""

    def crash(exc: BaseException) -> core.Rule:
      def fn(ctx: core.Context, rc: object) -> core.Outcome:
        del ctx, rc
        raise exc

      return core.Rule('stub', 'slow', fn, {}, '')

    def ok(ctx: core.Context, rc: object) -> core.Outcome:
      del ctx, rc
      return core.Outcome(['Absolute coverage: 1.0%'])

    checkout = make_checkout(self, PASSING_TEST)
    home = checkout.parent / 'home'
    stubs = {
        'tests-coverage': core.Rule('stub', 'slow', ok, {}, ''),
        'tests-assertions': crash(RuntimeError('forced crash')),
        'tests-mutation': crash(mutation_engine.MutantTimeoutError('late')),
    }
    with (
        mock.patch.dict(os.environ, {'HOME': str(home)}),
        mock.patch.object(cli, 'load_rules', return_value=stubs),
        mock.patch.object(fast_suite, 'measure_suite') as measure,
    ):
      measure.side_effect = SystemExit(5)
      code = fast_report.main([str(checkout)], quiet=True)
      report = fast_report.cache_dir_for(checkout) / 'report.md'
    self.assertEqual(code, 0)
    text = report.read_text('utf-8')
    for part in (
        'Absolute coverage: 1.0%',
        'RuntimeError: forced crash',
        'SystemExit: 5',
        'MutantTimeoutError: late',
        '- status: finished',
    ):
      self.assertIn(part, text)

  def test_report_is_replaced_before_the_first_step(self) -> None:
    """在某一步里被杀掉的运行，留下的是它自己未完成的报告。"""
    checkout = make_checkout(self, PASSING_TEST)
    home = checkout.parent / 'home'
    seen: list[str] = []

    def killed(ctx: core.Context, rc: object) -> core.Outcome:
      del ctx, rc
      seen.append(report.read_text('utf-8'))
      raise KeyboardInterrupt

    rule = core.Rule('stub', 'slow', killed, {}, '')
    stub = dict.fromkeys(fast_report.RULE_IDS, rule)
    with (
        mock.patch.dict(os.environ, {'HOME': str(home)}),
        mock.patch.object(cli, 'load_rules', return_value=stub),
    ):
      report = fast_report.cache_dir_for(checkout) / 'report.md'
      report.parent.mkdir(parents=True)
      report.write_text('old report\n- status: finished\n', 'utf-8')
      with self.assertRaises(KeyboardInterrupt):
        fast_report.main([str(checkout)], quiet=True)
    self.assertIn('- status: unfinished', seen[0])
    self.assertNotIn('old report', report.read_text('utf-8'))

  def test_end_to_end_with_broken_test_file(self) -> None:
    """测试文件有语法错误时规则崩溃，退出码仍是 0。"""
    checkout = make_checkout(self, 'def test_x(:\n')
    home = checkout.parent / 'home'
    proc = run_adapter(home, str(checkout))
    self.assertEqual(proc.returncode, 0, proc.stderr)
    self.assertIn('SyntaxError', proc.stdout)
    reports = list((home / '.cache' / 'era-lint').glob('*/report.md'))
    self.assertEqual(len(reports), 1)
    status = subprocess.run(
        ['git', 'status', '--porcelain', '--ignored'],
        cwd=checkout,
        capture_output=True,
        text=True,
        check=True,
    )
    self.assertEqual(status.stdout, '')

  def test_bad_arguments_exit_two(self) -> None:
    """checkout 不存在、或报告路径在 checkout 里时，退出码 2。"""
    checkout = make_checkout(self, PASSING_TEST)
    home = checkout.parent / 'home'
    missing = run_adapter(home, str(checkout.parent / 'nope'))
    inside = run_adapter(
        home, str(checkout), '--report', str(checkout / 'r.md')
    )
    self.assertEqual((missing.returncode, inside.returncode), (2, 2))
    self.assertFalse((checkout / 'r.md').exists())
    self.assertFalse(home.exists())


if __name__ == '__main__':
  unittest.main()
