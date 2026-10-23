# -*- coding: UTF-8 -*-
"""
生长养成系统的脚本套件
======================
tests/education/ 下每个 test_*.py 是一份独立脚本：用同目录的 _bootstrap.py 启动游戏，逐条断言，
末尾打印 PASS=通过数 FAIL=失败数 并退出：0 为全部通过，1 为有断言失败，2 为崩溃，
SKIP_EXIT（tests/education/_skip.py）为整份跳过。
这里为每份脚本生成一个同名测试，在新进程里运行脚本并打印它的全部输出（pytest -rP 时通过的测试也显示）。
脚本自己启动游戏，所以 setUp 不启动 FullWorld。
"""

import glob
import os
import re
import subprocess
import sys
from typing import Callable

from tests.education._skip import SKIP_EXIT
from tests.slow.base import SlowTestCase
from tests.world import ROOT

SCRIPT_DIR = os.path.join(ROOT, "tests", "education")
""" 脚本所在的目录 """


class EducationSuiteTest(SlowTestCase):
  """tests/education/ 的每份脚本一个测试：脚本的断言全部通过"""

  def setUp(self) -> None:
    """
    不启动游戏：脚本在自己的进程里启动
    Keyword arguments:
    无
    Return arguments:
    无
    """

  def run_script(self, path: str) -> None:
    """
    在新进程里运行一份脚本，打印它的输出；整份跳过时报告跳过，否则要求退出码为 0，且汇总行里至少一条断言通过、没有失败
    Keyword arguments:
    path -- 脚本路径
    Return arguments:
    无
    """
    result = subprocess.run(
        [sys.executable, "-u", path],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        timeout=self.time_limit,
        check=False,
    )
    print(result.stdout)
    if result.returncode == SKIP_EXIT:
      self.skipTest(result.stdout.strip().splitlines()[-1])
    self.assertEqual(
        result.returncode, 0, f"退出码 {result.returncode}，失败的断言见输出"
    )
    self.assertRegex(result.stdout, re.compile(r"^PASS=[1-9]\d* FAIL=0$", re.M))


def script_test(path: str) -> Callable[[EducationSuiteTest], None]:
  """
  为一份脚本生成测试方法
  Keyword arguments:
  path -- 脚本路径
  Return arguments:
  Callable[[EducationSuiteTest], None] -- 运行这份脚本的测试方法
  """

  def test(self: EducationSuiteTest) -> None:
    """运行脚本，它的断言全部通过"""
    self.run_script(path)

  test.__doc__ = f"{os.path.basename(path)} 的断言全部通过"
  return test


for script_path in sorted(glob.glob(os.path.join(SCRIPT_DIR, "test_*.py"))):
  setattr(
      EducationSuiteTest,
      os.path.splitext(os.path.basename(script_path))[0],
      script_test(script_path),
  )
