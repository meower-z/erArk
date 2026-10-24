# -*- coding: UTF-8 -*-
"""
测试的登记检查
==============
测试靠位置与基类登记，没有总清单：
- tests/fast/ 下的测试类继承 tests.fast.base.FastTestCase；
- tests/slow/ 下的测试类继承 tests.slow.base.SlowTestCase；
- 仓库里别处不能有 test_*.py，NOT_IN_LAYERS 列出的除外。
两层的测试模块由 tests.registration 像 unittest discover 那样导入后再查，基类由 Python 自己解析。
tests/slow/__init__.py 不许在快速层的进程里导入，所以慢速层在子进程里以 python -m tests.registration 导入、检查；
子进程里 tests/slow/__init__.py 拦下测试模块顶部对 Script 的导入，不会启动游戏。
两层之外的文件取自 git：已跟踪的，加上没有被忽略的新文件。
"""

import json
import os
import shutil
import subprocess
import sys
import unittest

from tests.fast.base import FastTestCase
from tests.registration import (
    FAST_LAYER,
    SLOW_LAYER,
    is_test_file,
    layer_problems,
)
from tests.world import ROOT

LAYERS = (FAST_LAYER, SLOW_LAYER)
""" 两层的目录 """
NOT_IN_LAYERS = {
    "tests/education/": "生长养成系统的脚本，由慢速层的 test_education_suite.py 运行",
    "tools/MCP/prts_character_downloader/test_downloader.py": "PRTS 立绘下载器的手动脚本，从网上下载图片，不是游戏的测试",
}
""" 可以不在两层里的 test_*.py：路径（以 / 结尾的是目录）: 原因 """


def slow_layer_problems() -> list:
  """
  在子进程里检查慢速层
  Keyword arguments:
  无
  Return arguments:
  list[str] -- layer_problems 对慢速层的结果
  """
  result = subprocess.run(
      [sys.executable, "-m", "tests.registration"],
      cwd=ROOT,
      capture_output=True,
      text=True,
      encoding="utf-8",
  )
  if result.returncode != 0:
    raise AssertionError(f"检查慢速层的子进程出错：\n{result.stderr}")
  return json.loads(result.stdout.strip().splitlines()[-1])


def repository_test_files() -> list:
  """
  列出仓库里现有的 test_*.py：git 跟踪的，加上没有被忽略的新文件
  Keyword arguments:
  无
  Return arguments:
  list[str] -- 相对仓库根目录、用 / 分隔的路径
  """
  output = subprocess.run(
      ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
      cwd=ROOT,
      capture_output=True,
      check=True,
  ).stdout
  paths = output.decode("utf-8").split("\0")
  return [
      path
      for path in paths
      if is_test_file(path) and os.path.isfile(os.path.join(ROOT, path))
  ]


def covers(entry: str, path: str) -> bool:
  """
  LAYERS 或 NOT_IN_LAYERS 的一项是否包含该文件：以 / 结尾的项是目录，包含其下全部文件；其余的项只包含同名文件
  Keyword arguments:
  entry -- 表中的一项
  path -- 用 / 分隔的路径
  Return arguments:
  bool -- 是否包含
  """
  return path.startswith(entry) if entry.endswith("/") else path == entry


class RegistrationTest(FastTestCase):
  """两层里的测试类继承该层的基类；别处的 test_*.py 只有 NOT_IN_LAYERS 列出的"""

  def check(self, problems: list) -> None:
    """
    有问题时逐行列出并失败
    Keyword arguments:
    problems -- 问题
    Return arguments:
    无
    """
    if problems:
      self.fail("\n" + "\n".join(problems))

  def test_fast_layer_uses_fast_base(self) -> None:
    """快速层收集到的测试类都继承 FastTestCase，没有不会运行的测试"""
    self.check(layer_problems(FAST_LAYER, FastTestCase))

  def test_slow_layer_uses_slow_base(self) -> None:
    """慢速层收集到的测试类都继承 SlowTestCase，没有不会运行的测试"""
    self.check(slow_layer_problems())

  def test_no_test_outside_layers(self) -> None:
    """test_*.py 只在 tests/fast/、tests/slow/ 与 NOT_IN_LAYERS 里；NOT_IN_LAYERS 的每一项都还有 test_*.py"""
    if shutil.which("git") is None or not os.path.exists(
        os.path.join(ROOT, ".git")
    ):
      raise unittest.SkipTest(
          "两层之外的文件从 git 取，这里没有 git 或不是 git 检出"
      )
    paths = repository_test_files()
    misplaced = [
        path
        for path in paths
        if not any(covers(entry, path) for entry in (*LAYERS, *NOT_IN_LAYERS))
    ]
    stale = [
        f"NOT_IN_LAYERS 的 {entry} 已没有 test_*.py：从表里去掉"
        for entry in NOT_IN_LAYERS
        if not any(covers(entry, path) for path in paths)
    ]
    self.check(
        [f"{path}：测试放进 tests/fast/ 或 tests/slow/" for path in misplaced]
        + stale
    )
