# -*- coding: UTF-8 -*-
"""
场景门锁的存档读写与版本 22 旧存档导入
======================================
- 新游戏锁定玩家所在房间并存档后，内核存档文件包含 scene.closed，读档后门锁保持锁定且玩家仍在场景内。
- 将存档改写为版本 22 并在缓存文件放入含门锁与无效路径的旧 scene_data，读档后仅导入现有场景的非 0 门锁，缓存中不含
scene_data。
"""

import importlib
import json
import os
import pickle
import tempfile
from typing import Any
from unittest import mock

from tests.slow.base import SlowTestCase

SLOT = "scene_state"


def _mod(name: str) -> Any:
    return importlib.import_module(name)


class SceneStateSaveTest(SlowTestCase):
    """场景门锁完整存档读档与版本 22 旧存档迁移测试"""

    def setUp(self) -> None:
        """开新游戏，将存档目录改向临时目录，并记录玩家当前所在场景路径"""
        super().setUp()
        index = _mod("Script.Modules.save_load.index")
        self.folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", self.folder))
        activity = _mod("Script.Modules.domains.activity")
        self.room = os.sep.join(activity.position(0))

    def _load(self) -> None:
        constant = _mod("Script.Core.constant")
        save_handle = _mod("Script.Core.save_handle")
        kernel = _mod("Script.Kernel.core")
        load_order = _mod("Script.Modules.load_order")
        view = _mod("Script.UI.Moudle.view")
        save_handle.input_load_save(SLOT)
        view.now_panel_id = constant.Panel.IN_SCENE
        kernel.load(load_order.LOAD_ORDER)

    def test_lock_survives_save_and_load(self) -> None:
        """锁定玩家所在房间并存档后，内核存档文件记录 scene.closed，读档后保持锁定且玩家在场"""
        save_handle = _mod("Script.Core.save_handle")
        kernel_state = _mod("Script.Modules.save_load.kernel_state")
        scene_state = _mod("Script.Modules.domains.scene_state")
        kernel_data = _mod("tests.kernel_data")
        kernel_data.put(scene_state.set_close_flag, self.room, 1)
        save_handle.establish_save(SLOT)
        path = os.path.join(self.folder, SLOT, kernel_state.SAVE_FILE)
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["data"][scene_state.CLOSED], {self.room: 1})
        self._load()
        self.assertEqual(scene_state.closed(), {self.room: 1})
        self.assertIn(0, scene_state.occupants(self.room))

    def test_v22_save_adopts_flags(self) -> None:
        """读取版本 22 存档时从缓存 scene_data 导入现有场景的非 0 门锁，并从缓存移除 scene_data"""
        save_handle = _mod("Script.Core.save_handle")
        game_type = _mod("Script.Core.game_type")
        index = _mod("Script.Modules.save_load.index")
        kernel_state = _mod("Script.Modules.save_load.kernel_state")
        scene_state = _mod("Script.Modules.domains.scene_state")
        save_handle.establish_save(SLOT)
        path = os.path.join(self.folder, SLOT, kernel_state.SAVE_FILE)
        with open(path, encoding="utf-8") as f:
            saved = json.load(f)
        saved["version"] = 22
        saved["data"].pop(scene_state.CLOSED, None)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(saved, f)
        locked, other = game_type.Scene(), game_type.Scene()
        vars(locked)["close_flag"] = 1
        vars(locked)["character_list"] = {0}
        vars(other)["close_flag"] = 0
        vars(self.cache)["scene_data"] = {self.room: locked, "旧\\房间": other}
        with open(os.path.join(index.path(SLOT), index.CACHE_FILE), "wb") as f:
            pickle.dump(self.cache, f)
        del vars(self.cache)["scene_data"]
        self._load()
        self.assertEqual(scene_state.closed(), {self.room: 1})
        self.assertNotIn("scene_data", vars(self.cache))
