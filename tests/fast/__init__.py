# -*- coding: UTF-8 -*-
"""
快速层：不启动游戏的单元测试，在 MinimalWorld 上运行
====================================================
在仓库根目录运行 pytest tests/fast。测试继承 tests.fast.base.FastTestCase。

导入本包时先装拦截，再载入 MinimalWorld。游戏模块导入时读取配置与状态。世界因此须先载入。
本包先于包内测试模块执行。测试模块因此可在顶部直接导入游戏模块。

快速层禁止导入 FORBIDDEN 中的三个模块。Script.Core.image_catalog 导入时遍历 image 目录。
Script.Core.image_cache 将图片解码为 Tk PhotoImage。Script.Core.game_init 启动 Tk 游戏。
首次导入受禁模块会抛 FastLayerImportError 并指明模块名。此类测试属慢速层。拦截不管装上前
已载入的模块。pytest tests/fast 先导入本包再导入测试模块。
"""

import importlib.abc
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import ModuleType

FORBIDDEN = frozenset(
    {
        "Script.Core.image_catalog",
        "Script.Core.image_cache",
        "Script.Core.game_init",
    }
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
