#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fast_report.py 的测试：设置取自 pyproject.toml、缓存目录、变异测试的统计、只出报告的退出码、data/ 检查；不启动游戏

要能导入 lint 引擎的 lint 包，用法：
    PYTHONPATH=<含 lint 的目录> python3 tools/test_quality/test_fast_report.py
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from lint import cli
from lint import core
from lint.rules import mutation_engine
from lint.rules import mutation_rule
import fast_report

_REPO = pathlib.Path(__file__).resolve().parents[2]
_ADAPTER = pathlib.Path(fast_report.__file__)
_PASSING_TEST = (
    'import unittest\nclass T(unittest.TestCase):\n'
    '  def test_ok(self):\n    self.assertEqual(1, 1)\n'
)


def _make_checkout(case: unittest.TestCase, test_src: str) -> pathlib.Path:
  """建一个提交过的 git checkout，tests/fast/test_a.py 的内容是 test_src。"""
  tmp = tempfile.TemporaryDirectory()
  case.addCleanup(tmp.cleanup)
  root = pathlib.Path(tmp.name).resolve() / 'checkout'
  files = {
      'tests/__init__.py': '',
      'tests/fast/__init__.py': '',
      'tests/fast/test_a.py': test_src,
      'tests/slow/test_b.py': _PASSING_TEST,
      'Script/__init__.py': '',
      'Script/m.py': 'def f(x):\n  return x + 1\n',
      # 与 erArk 一样，data/ 里有已跟踪的文件，生成的文件被忽略
      '.gitignore': 'data/*.json\n',
      'data/a.csv': 'id\n',
  }
  for rel, text in files.items():
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding='utf-8')
  # 仓库的设置只列出真实的测试文件；这里的 checkout 只有 test_a.py，变异测试改看整个 tests/fast
  settings = (_REPO / 'pyproject.toml').read_text(encoding='utf-8')
  mutation = '[tool.test-quality.rules.tests-mutation]'
  head, tail = settings.split(mutation)
  tail = re.sub(
      r'test_globs = \[.*?\]',
      'test_globs = ["tests/fast/test_*.py"]',
      tail,
      count=1,
      flags=re.S,
  )
  (root / 'pyproject.toml').write_text(head + mutation + tail, encoding='utf-8')
  for cmd in (
      ['git', 'init', '-q'],
      ['git', 'add', '-A'],
      ['git', '-c', 'user.name=t', '-c', 'user.email=t@t']
      + ['commit', '-qm', 'init'],
  ):
    subprocess.run(cmd, cwd=root, check=True, capture_output=True)
  return root


def _run_adapter(
    home: pathlib.Path, *args: str
) -> subprocess.CompletedProcess[str]:
  """在子进程里运行本脚本，HOME 设为 home。"""
  env = dict(os.environ, HOME=str(home))
  return subprocess.run(
      [sys.executable, str(_ADAPTER), *args],
      env=env,
      capture_output=True,
      text=True,
      check=False,
      timeout=120,
  )


class ConfigTest(unittest.TestCase):
  """生成的设置与缓存目录的位置。"""

  def test_rules_point_at_fast_layer_only(self) -> None:
    """覆盖率与变异测试只看 tests/fast 和 Script，不看 tests/slow。"""
    cfg = fast_report.build_config(_REPO, pathlib.Path('/c/era-lint/x'))
    rules = cfg['rules']
    self.assertEqual(rules['tests-coverage']['start_dir'], 'tests/fast')
    self.assertEqual(rules['tests-coverage']['source'], ['Script'])
    self.assertEqual(rules['tests-coverage'].get('omit', []), [])
    self.assertEqual(
        rules['tests-assertions']['test_globs'], ['tests/fast/test_*.py']
    )
    for glob in rules['tests-mutation']['test_globs']:
      self.assertTrue(glob.startswith('tests/fast/test_'), glob)
    self.assertEqual(rules['tests-mutation']['mutant_timeout'], 2.0)
    self.assertLessEqual(rules['tests-mutation']['max_workers'], 3)
    self.assertEqual(cfg['tools']['python'], [sys.executable])
    self.assertEqual(
        cfg['tools']['coverage'], [sys.executable, '-m', 'coverage']
    )

  def test_thresholds_stay_at_rule_defaults(self) -> None:
    """设置里不定阈值，所以用规则的默认值。"""
    cfg = fast_report.build_config(_REPO, pathlib.Path('/c/era-lint/x'))
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
    cfg = fast_report.build_config(_REPO, one)
    ctx = core.Context(pathlib.Path('/w/a'), cfg)
    self.assertEqual(ctx.cache_dir, one)


class MutationNotesTest(unittest.TestCase):
  """变异测试的说明把缓存里的当前条目加起来。"""

  def test_not_scored_files_count_as_evaluated_only(self) -> None:
    """没变异的整套测试失败的文件算查过、不计分；过期的条目两样都不算。"""
    checkout = _make_checkout(self, _PASSING_TEST)
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
    notes = fast_report._mutation_notes(ctx, rc)
    self.assertIn('kill rate 50.0% (1/2)', notes[0])
    self.assertIn('2 of 3 files evaluated, 1 of them not scored', notes[0])
    self.assertEqual(notes[1:], ['survived: Script/m.py:2 (f:x)'])

  def test_remeasure_uses_only_the_mutation_test_files(self) -> None:
    """只有没列进 tests-mutation 的测试执行的行，不算变异测试要查的行。"""
    checkout = _make_checkout(
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
    cache_dir = checkout.parent / 'cache'
    cache_dir.mkdir()
    cfg = fast_report.build_config(checkout, cache_dir)
    cfg['rules']['tests-mutation']['test_globs'] = ['tests/fast/test_a.py']
    ctx = core.Context(checkout, cfg)
    registry = cli.load_rules()
    fast_report.remeasure_for_mutation(
        ctx,
        ctx.rule_config(registry['tests-coverage']),
        ctx.rule_config(registry['tests-mutation']),
    )
    data = json.loads((cache_dir / 'coverage.json').read_text('utf-8'))
    files = data['files']
    self.assertEqual(files['Script/m.py']['executed_lines'], [1, 2])
    self.assertNotIn(2, files.get('Script/n.py', {}).get('executed_lines', []))


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

    checkout = _make_checkout(self, _PASSING_TEST)
    home = checkout.parent / 'home'
    stubs = {
        'tests-coverage': core.Rule('stub', 'slow', ok, {}, ''),
        'tests-assertions': crash(RuntimeError('forced crash')),
        'tests-mutation': crash(mutation_engine.MutantTimeoutError('late')),
    }
    with (
        mock.patch.dict(os.environ, {'HOME': str(home)}),
        mock.patch.object(cli, 'load_rules', return_value=stubs),
        mock.patch.object(fast_report, 'measure_suite') as measure,
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
    checkout = _make_checkout(self, _PASSING_TEST)
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
    checkout = _make_checkout(self, 'def test_x(:\n')
    home = checkout.parent / 'home'
    proc = _run_adapter(home, str(checkout))
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
    checkout = _make_checkout(self, _PASSING_TEST)
    home = checkout.parent / 'home'
    missing = _run_adapter(home, str(checkout.parent / 'nope'))
    inside = _run_adapter(
        home, str(checkout), '--report', str(checkout / 'r.md')
    )
    self.assertEqual((missing.returncode, inside.returncode), (2, 2))
    self.assertFalse((checkout / 'r.md').exists())
    self.assertFalse(home.exists())


class DataCheckTest(unittest.TestCase):
  """data/ 下有被忽略的生成文件、或 git 出错时，拒绝运行。"""

  def test_ignored_file_under_data_is_refused(self) -> None:
    """在写任何东西之前以退出码 2 退出，并给出清理命令。"""
    checkout = _make_checkout(self, _PASSING_TEST)
    home = checkout.parent / 'home'
    built = checkout / 'data' / 'Character.json'
    built.write_text('{}', encoding='utf-8')
    proc = _run_adapter(home, str(checkout))
    self.assertEqual(proc.returncode, 2, proc.stderr)
    self.assertIn('1 git-ignored untracked files', proc.stderr)
    self.assertIn('data/Character.json', proc.stderr)
    self.assertIn(f'git -C {checkout} clean -fdX data/', proc.stderr)
    self.assertEqual(proc.stdout, '')
    self.assertTrue(built.exists())
    self.assertFalse(home.exists())

  def test_refusal_names_a_sample(self) -> None:
    """文件多时只列 SAMPLE_SIZE 个名字，个数照实数。"""
    checkout = _make_checkout(self, _PASSING_TEST)
    for i in range(fast_report.SAMPLE_SIZE + 2):
      (checkout / 'data' / f'f{i}.json').write_text('{}', encoding='utf-8')
    reason = fast_report.refuse_reason(checkout)
    self.assertIn(f'{fast_report.SAMPLE_SIZE + 2} git-ignored', reason)
    self.assertIn('data/f4.json, ...', reason)
    self.assertNotIn('data/f5.json', reason)

  def test_hint_quotes_the_checkout_path(self) -> None:
    """清理命令里的路径按 shell 规则加了引号，照打印出来的样子就能运行。"""
    checkout = _make_checkout(self, _PASSING_TEST)
    spaced = checkout.parent / 'my checkout'
    checkout.rename(spaced)
    (spaced / 'data' / 'Character.json').write_text('{}', encoding='utf-8')
    hint = fast_report.refuse_reason(spaced).splitlines()[-1].strip()
    self.assertEqual(hint, f"git -C '{spaced}' clean -fdX data/")
    subprocess.run(hint, shell=True, check=True, capture_output=True)
    self.assertEqual(fast_report.refuse_reason(spaced), '')

  def test_clean_data_passes(self) -> None:
    """已跟踪的文件和没被忽略的未跟踪文件不会让它拒绝。"""
    checkout = _make_checkout(self, _PASSING_TEST)
    (checkout / 'data' / 'b.csv').write_text('id\n', encoding='utf-8')
    self.assertEqual(fast_report.ignored_data_files(checkout), [])
    self.assertEqual(fast_report.refuse_reason(checkout), '')

  def test_not_a_git_repo_is_refused(self) -> None:
    """git 出错时以退出码 2 拒绝，这项检查从不跳过。"""
    tmp = tempfile.TemporaryDirectory()
    self.addCleanup(tmp.cleanup)
    root = pathlib.Path(tmp.name).resolve()
    checkout = root / 'checkout'
    (checkout / 'tests' / 'fast').mkdir(parents=True)
    home = root / 'home'
    env = {'GIT_CEILING_DIRECTORIES': str(root)}
    with mock.patch.dict(os.environ, env):
      proc = _run_adapter(home, str(checkout))
    self.assertEqual(proc.returncode, 2, proc.stderr)
    self.assertIn('cannot check', proc.stderr)
    self.assertIn('git ls-files exited', proc.stderr)
    self.assertFalse(home.exists())

  def test_missing_git_is_refused(self) -> None:
    """git 启动不了时，与 git 出错一样拒绝。"""
    checkout = _make_checkout(self, _PASSING_TEST)
    with mock.patch.object(
        subprocess, 'run', side_effect=FileNotFoundError('git')
    ):
      reason = fast_report.refuse_reason(checkout)
    self.assertIn('cannot check', reason)
    self.assertIn('FileNotFoundError', reason)


if __name__ == '__main__':
  unittest.main()
