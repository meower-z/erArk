#!/usr/bin/env python3
"""tools/test_quality 的测试共用的假 checkout 和运行 fast_report.py 的子进程。"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
ADAPTER = pathlib.Path(__file__).resolve().parent / 'fast_report.py'
PASSING_TEST = (
    'import unittest\nclass T(unittest.TestCase):\n'
    '  def test_ok(self):\n    self.assertEqual(1, 1)\n'
)


def make_checkout(case: unittest.TestCase, test_src: str) -> pathlib.Path:
  """建一个提交过的 git checkout，tests/fast/test_a.py 的内容是 test_src。"""
  tmp = tempfile.TemporaryDirectory()
  case.addCleanup(tmp.cleanup)
  root = pathlib.Path(tmp.name).resolve() / 'checkout'
  files = {
      'tests/__init__.py': '',
      'tests/fast/__init__.py': '',
      'tests/fast/test_a.py': test_src,
      'tests/slow/test_b.py': PASSING_TEST,
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
  settings = (REPO / 'pyproject.toml').read_text(encoding='utf-8')
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


def run_adapter(
    home: pathlib.Path, *args: str
) -> subprocess.CompletedProcess[str]:
  """以 home 为 HOME，在子进程里运行 fast_report.py。"""
  env = dict(os.environ, HOME=str(home))
  return subprocess.run(
      [sys.executable, str(ADAPTER), *args],
      env=env,
      capture_output=True,
      text=True,
      check=False,
      timeout=120,
  )
