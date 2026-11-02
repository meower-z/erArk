#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data_check.py 的测试：data/ 下有被忽略的生成文件时拒绝运行，并给出清理命令；不启动游戏

用法：
    PYTHONPATH=<含 lint 的目录> python3 tools/test_quality/test_data_check.py
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

from checkout_fixture import make_checkout
from checkout_fixture import PASSING_TEST
from checkout_fixture import run_adapter
import data_check


class DataCheckTest(unittest.TestCase):
  """data/ 下有被忽略的生成文件、或 git 出错时，拒绝运行。"""

  def test_ignored_file_under_data_is_refused(self) -> None:
    """在写任何东西之前以退出码 2 退出，并给出清理命令。"""
    checkout = make_checkout(self, PASSING_TEST)
    home = checkout.parent / 'home'
    built = checkout / 'data' / 'Character.json'
    built.write_text('{}', encoding='utf-8')
    proc = run_adapter(home, str(checkout))
    self.assertEqual(proc.returncode, 2, proc.stderr)
    self.assertIn('1 git-ignored untracked files', proc.stderr)
    self.assertIn('data/Character.json', proc.stderr)
    self.assertIn(f'git -C {checkout} clean -fdX data/', proc.stderr)
    self.assertEqual(proc.stdout, '')
    self.assertTrue(built.exists())
    self.assertFalse(home.exists())

  def test_refusal_names_a_sample(self) -> None:
    """文件多时只列 SAMPLE_SIZE 个名字，个数照实数。"""
    checkout = make_checkout(self, PASSING_TEST)
    for i in range(data_check.SAMPLE_SIZE + 2):
      (checkout / 'data' / f'f{i}.json').write_text('{}', encoding='utf-8')
    reason = data_check.refuse_reason(checkout)
    self.assertIn(f'{data_check.SAMPLE_SIZE + 2} git-ignored', reason)
    self.assertIn('data/f4.json, ...', reason)
    self.assertNotIn('data/f5.json', reason)

  def test_hint_quotes_the_checkout_path(self) -> None:
    """清理命令里的路径按 shell 规则加了引号，照打印出来的样子就能运行。"""
    checkout = make_checkout(self, PASSING_TEST)
    spaced = checkout.parent / 'my checkout'
    checkout.rename(spaced)
    (spaced / 'data' / 'Character.json').write_text('{}', encoding='utf-8')
    hint = data_check.refuse_reason(spaced).splitlines()[-1].strip()
    self.assertEqual(hint, f"git -C '{spaced}' clean -fdX data/")
    subprocess.run(hint, shell=True, check=True, capture_output=True)
    self.assertEqual(data_check.refuse_reason(spaced), '')

  def test_clean_data_passes(self) -> None:
    """已跟踪的文件和没被忽略的未跟踪文件不会让它拒绝。"""
    checkout = make_checkout(self, PASSING_TEST)
    (checkout / 'data' / 'b.csv').write_text('id\n', encoding='utf-8')
    self.assertEqual(data_check.ignored_data_files(checkout), [])
    self.assertEqual(data_check.refuse_reason(checkout), '')

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
      proc = run_adapter(home, str(checkout))
    self.assertEqual(proc.returncode, 2, proc.stderr)
    self.assertIn('cannot check', proc.stderr)
    self.assertIn('git ls-files exited', proc.stderr)
    self.assertFalse(home.exists())

  def test_missing_git_is_refused(self) -> None:
    """git 启动不了时，与 git 出错一样拒绝。"""
    checkout = make_checkout(self, PASSING_TEST)
    with mock.patch.object(
        subprocess, 'run', side_effect=FileNotFoundError('git')
    ):
      reason = data_check.refuse_reason(checkout)
    self.assertIn('cannot check', reason)
    self.assertIn('FileNotFoundError', reason)


if __name__ == '__main__':
  unittest.main()
