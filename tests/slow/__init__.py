# -*- coding: UTF-8 -*-
"""
慢速层：每个测试在自己的新进程里完整启动游戏，开新游戏，经游戏主循环推进时间
==========================================================================
运行：在仓库根目录 pytest tests/slow --forked
--forked（pytest-forked 插件）让每个测试在新 fork 出的子进程里运行；测试继承 tests.slow.base.SlowTestCase。

收集测试的父进程不能载入游戏：游戏模块在导入时绑定缓存，而缓存要在子进程启动游戏时才建。
所以导入本包时装上 ParentImportGuard，测试模块顶部导入 Script 下的模块即抛 SlowLayerImportError；
游戏模块在测试方法或 setUp 里导入，SlowTestCase.setUp 先撤下拦截再启动游戏。
快速层在本进程载入了小世界时，导入本包即抛 RuntimeError：两层分开跑。
"""

import importlib.abc
import sys

if "tests.fast" in sys.modules:
  raise RuntimeError(
      "快速层与慢速层分开跑：pytest tests/fast，pytest tests/slow --forked"
  )


class SlowLayerImportError(ImportError):
  """慢速层的测试模块在收集时导入了游戏模块"""


class ParentImportGuard(importlib.abc.MetaPathFinder):
  """导入 Script 下的模块时抛 SlowLayerImportError；本身不负责查找模块"""

  def find_spec(self, fullname, path, target=None):
    """
    游戏模块抛错，其他模块交给后面的查找器
    Keyword arguments:
    fullname -- 模块全名
    path -- 由导入系统传入，不使用
    target -- 由导入系统传入，不使用
    Return arguments:
    None -- 让导入系统继续用其他查找器
    """
    if fullname == "Script" or fullname.startswith("Script."):
      raise SlowLayerImportError(
          f"慢速层的测试模块不能在顶部导入 {fullname}：游戏要在每个测试自己的进程里启动，在测试方法或 setUp 里导入",
          name=fullname,
      )
    return None


def remove_parent_guard():
  """
  撤下 ParentImportGuard（SlowTestCase.setUp 在启动游戏前调用）
  Keyword arguments:
  无
  Return arguments:
  无
  """
  sys.meta_path[:] = [
      finder
      for finder in sys.meta_path
      if not isinstance(finder, ParentImportGuard)
  ]


if not any(isinstance(finder, ParentImportGuard) for finder in sys.meta_path):
  sys.meta_path.insert(0, ParentImportGuard())
