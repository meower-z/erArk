# -*- coding: UTF-8 -*-
"""
读档时重新得出的缓存字段
========================
每个测试先开新游戏（SlowTestCase.setUp），把存档目录换成临时目录，再等待 60 分钟。
- 存档后读档：仓库容量、干员人数上限、访客上限、床位上限、菜谱和角色模板都与存档前相同，
  地图是游戏启动时载入的那份。
- 直接 pickle 整个缓存的旧存档里，四个上限都是 99，地图为空。
  读这个存档后，四个上限回到存档前的值，地图是游戏启动时载入的那份。
"""

import importlib
import os
import pickle
import tempfile
from typing import Any
from unittest import mock

from tests.slow.base import SlowTestCase

SLOT = "rebuilt"
""" 测试写的存档id """
LIMITS = (
    "warehouse_capacity",
    "people_max",
    "medical_bed_limit",
)
""" 缓存文件不写、读档时重新算出的罗德岛字段 """


def game(name: str) -> Any:
    """
    游戏启动之后再导入游戏模块
    Keyword arguments:
    name -- 模块名
    Return arguments:
    Any -- 模块
    """
    return importlib.import_module(name)


class LoadRebuildsDerivedTest(SlowTestCase):
    """读档时重新得出的缓存字段"""

    def setUp(self) -> None:
        """开新游戏，把存档目录换成临时目录，等待 60 分钟，记下游戏启动时载入的地图和存档前的值"""
        super().setUp()
        index = game("Script.Modules.save_load.index")
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.wait(60)
        self.boot_map = self.cache.map_data
        self.before = self.values()

    def wait(self, minutes: int) -> None:
        """
        玩家每次要选行动时都选等待，直到内核时钟比开始时至少晚 minutes 分钟
        Keyword arguments:
        minutes -- 要前进的分钟数
        """
        constant = game("Script.Core.constant")
        kernel = game("Script.Kernel.core")
        player_pick = game("Script.Modules.tk_ui.player_pick")
        handle_instruct = game("Script.System.Instruct_System.handle_instruct")

        def wait() -> None:
            handle_instruct.handle_instruct(constant.Instruct.WAIT)

        start = kernel.state().clock
        with mock.patch.object(player_pick, "chooser", wait):
            while kernel.state().clock < start + minutes:
                kernel.step()

    def values(self) -> dict[str, object]:
        """
        取四个上限、菜谱（draft.encode 的编码）和角色模板（键与对象 id 的列表）
        Return arguments:
        dict -- 字段名: 值
        """
        draft = game("Script.Modules.gameplay_resolution.draft")
        island = self.cache.rhodes_island
        out: dict[str, object] = {k: getattr(island, k) for k in LIMITS}
        out["recipe_data"] = draft.encode(self.cache.recipe_data)
        out["npc_tem_data"] = [
            (k, id(v)) for k, v in self.cache.npc_tem_data.items()
        ]
        return out

    def load(self) -> None:
        """读档，把当前面板设成场景面板，再调用 kernel.load(load_order.LOAD_ORDER)"""
        constant = game("Script.Core.constant")
        save_handle = game("Script.Core.save_handle")
        kernel = game("Script.Kernel.core")
        load_order = game("Script.Modules.load_order")
        view = game("Script.UI.Moudle.view")
        save_handle.input_load_save(SLOT)
        view.now_panel_id = constant.Panel.IN_SCENE
        kernel.load(load_order.LOAD_ORDER)

    def test_save_and_load_keep_values(self) -> None:
        """存档后读档，四个上限、菜谱和角色模板与存档前相同，地图是游戏启动时载入的那份"""
        save_handle = game("Script.Core.save_handle")
        save_handle.establish_save(SLOT)
        self.load()
        self.assertEqual(self.values(), self.before)
        self.assertIs(self.cache.map_data, self.boot_map)

    def test_old_save_gets_rebuilt_values(self) -> None:
        """旧存档里四个上限是 99、地图为空，读这个存档后四个上限回到存档前的值，地图是游戏启动时载入的那份"""
        save_handle = game("Script.Core.save_handle")
        index = game("Script.Modules.save_load.index")
        save_handle.establish_save(SLOT)
        island = self.cache.rhodes_island
        for name in LIMITS:
            setattr(island, name, 99)
        self.cache.map_data = {}
        file_path = os.path.join(index.path(SLOT), index.CACHE_FILE)
        with open(file_path, "wb") as f:
            pickle.dump(self.cache, f)
        self.cache.map_data = self.boot_map
        self.load()
        island = self.cache.rhodes_island
        self.assertEqual(
            {k: getattr(island, k) for k in LIMITS},
            {k: self.before[k] for k in LIMITS},
        )
        self.assertIs(self.cache.map_data, self.boot_map)
