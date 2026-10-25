# -*- coding: UTF-8 -*-
"""
快速层：不启动游戏的单元测试，在 MinimalWorld 上运行
====================================================
运行：在仓库根目录 pytest tests/fast
测试继承 tests.fast.base.FastTestCase。

导入本包时先装上导入拦截，再载入本进程的 MinimalWorld。游戏模块在导入时绑定缓存，
所以世界必须先于测试模块里的游戏导入载入；包在其中任何模块之前执行，测试模块可以在顶部直接导入游戏模块。

快速层不能导入 FORBIDDEN 中的三个模块：era_image 导入时遍历整个 image 目录，web_server 与 game_init 是启动 Web 服务与 Tk 游戏的模块。
拦截装上后，本进程首次导入其中之一时抛 FastLayerImportError，说明是哪个模块；这样的测试属于慢速层。
拦截不管装上前已载入的模块；pytest tests/fast 在导入任何测试模块之前就导入本包。
"""

import importlib.abc
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from collections.abc import Sequence
  from types import ModuleType

FORBIDDEN = frozenset(
    {"Script.Core.era_image", "Script.Core.web_server", "Script.Core.game_init"}
)
""" 快速层不能导入的模块 """


class FastLayerImportError(ImportError):
  """快速层的测试导入了 FORBIDDEN 中的模块"""


class FastLayerImportGuard(importlib.abc.MetaPathFinder):
  """导入 FORBIDDEN 中的模块时抛 FastLayerImportError；本身不负责查找模块"""

  def find_spec(
      self,
      fullname: str,
      path: "Sequence[str] | None",
      target: "ModuleType | None" = None,
  ) -> None:
    """
    受禁模块抛错，其他模块交给后面的查找器
    Keyword arguments:
    fullname -- 模块全名
    path -- 由导入系统传入，不使用
    target -- 由导入系统传入，不使用
    Return arguments:
    None -- 让导入系统继续用其他查找器
    """
    if fullname in FORBIDDEN:
      raise FastLayerImportError(
          f"快速层不能导入 {fullname}：导入它的测试要启动游戏，应放进慢速层（导入链见下方回溯）",
          name=fullname,
      )
    return None


if not any(
    isinstance(finder, FastLayerImportGuard) for finder in sys.meta_path
):
  sys.meta_path.insert(0, FastLayerImportGuard())


from tests.world import MinimalWorld  # noqa: E402

WORLD = MinimalWorld.load()
""" 本进程的小世界 """
