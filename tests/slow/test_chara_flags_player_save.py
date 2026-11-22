# -*- coding: UTF-8 -*-
"""
存档角色标记、行动记录、玩家能力与收藏品往返测试
================================================
开新游戏（SlowTestCase.setUp），存档目录换成临时目录。
- 写入四个新键的非默认值（含 Fraction 类型的 today_sanity_point_cost），存盘后校验文件 "2" 版本为当前版本、
  含 "$frac" 与四个新键，且重读后数值与类型完整保留；
- 存盘后再存一次，文件 "2"（除存档标记外）逐字相同；
- 存盘前后以相同随机种子推进 60 分钟，内核状态、花名册顺序与四项域快照一致；
- 构造带四个旧属性的 v16 存档读回，验证 adopt_old_save 把 float 转为精确 Fraction、忽略 unnormal_flag，
  且载入后的 Character 对象不含这四个属性。
"""

import hashlib
import importlib
import json
import os
import random
import tempfile
from fractions import Fraction
from typing import Any
from unittest import mock

from tests import kernel_data as kd
from tests.slow.base import SlowTestCase

SLOT = "v17"
SEED = 20261121


def game(name: str) -> Any:
    """按模块名导入游戏模块"""
    return importlib.import_module(name)


class SaveCharaFlagsPlayerTest(SlowTestCase):
    """v17 存档对四个新角色键的存、读、续玩与旧档迁移"""

    time_limit = 900

    def setUp(self) -> None:
        """为本用例创建临时存档目录"""
        super().setUp()
        index = game("Script.Modules.save_load.index")
        self.folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", self.folder))

    def load(self, save_id: str) -> None:
        """从指定槽位读档并挂载内核"""
        from Script.UI.Moudle import view

        constant = game("Script.Core.constant")
        save_handle = game("Script.Core.save_handle")
        kernel = game("Script.Kernel.core")
        load_order = game("Script.Modules.load_order")
        save_handle.input_load_save(save_id)
        view.now_panel_id = constant.Panel.IN_SCENE
        kernel.load(load_order.LOAD_ORDER)

    def wait(self, minutes: int) -> None:
        """以玩家等待方式推进内核指定分钟数"""
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

    def state_json(self) -> str:
        """序列化当前内核状态以便跨轮比较"""
        kernel = game("Script.Kernel.core")
        kernel_state = game("Script.Modules.save_load.kernel_state")
        return json.dumps(
            kernel_state.encode(kernel.state(), "fixed"), sort_keys=True
        )

    def test_round_trip_and_continue(self) -> None:
        """四个新角色键存读、$frac 保留、二次存盘一致、续玩 60 分钟一致"""
        save_handle = game("Script.Core.save_handle")
        kernel = game("Script.Kernel.core")
        kernel_state = game("Script.Modules.save_load.kernel_state")
        upgrade = game("Script.Modules.save_load.upgrade")
        flags = kd.domain("flags")
        action_info = kd.domain("action_info")
        player_ability = kd.domain("player_ability")
        player_collection = kd.domain("player_collection")

        npc_id = min(
            cid for cid in kd.domain("roster").active_sorted() if cid != 0
        )
        kd.put(flags.set, npc_id, is_follow=1, morning_salutation=2)
        kd.put(action_info.set, npc_id, "talk_count", 4)
        kd.put(action_info.record_move, 0, ["中枢", "博士房间"])
        kd.put(
            player_ability.set,
            0,
            visual=True,
            jj_size=2,
            today_sanity_point_cost=Fraction(5, 3),
        )
        kd.put(player_collection.set_token, npc_id, True)
        kd.put(player_collection.set_bonus, 1, True)
        kd.put(player_collection.append_used_condom, 15)
        kd.put(player_collection.set_eqip_token, 2, [npc_id])

        before_save = self.state_json()
        save_handle.establish_save(SLOT)
        path = os.path.join(self.folder, SLOT, kernel_state.SAVE_FILE)
        with open(path, encoding="utf-8") as f:
            first_file = json.load(f)
        self.assertEqual(first_file["version"], upgrade.CURRENT)
        self.assertIn('"$frac"', json.dumps(first_file))
        pl_data = first_file["characters"]["0"]["data"]
        self.assertIn(player_ability.KEY, pl_data)
        self.assertIn(player_collection.KEY, pl_data)
        self.assertIn(action_info.KEY, pl_data)
        npc_data = first_file["characters"][str(npc_id)]["data"]
        self.assertIn(flags.KEY, npc_data)

        random.seed(SEED)
        self.wait(60)
        played = (
            self.state_json(),
            tuple(kernel.state().characters),
            hashlib.sha256(repr(random.getstate()).encode()).hexdigest(),
        )

        self.load(SLOT)
        self.assertEqual(self.state_json(), before_save)
        cost = player_ability.get(0, "today_sanity_point_cost")
        self.assertIs(type(cost), Fraction)
        self.assertEqual(cost, Fraction(5, 3))
        self.assertEqual(flags.get(npc_id, "is_follow"), 1)
        self.assertEqual(action_info.get(npc_id, "talk_count"), 4)
        self.assertTrue(player_collection.get("token_list")[npc_id])
        for cid, ch in self.cache.character_data.items():
            for attr in (
                "sp_flag",
                "action_info",
                "pl_ability",
                "pl_collection",
            ):
                self.assertFalse(hasattr(ch, attr), f"cid={cid} attr={attr}")

        random.seed(SEED)
        self.wait(60)
        replayed = (
            self.state_json(),
            tuple(kernel.state().characters),
            hashlib.sha256(repr(random.getstate()).encode()).hexdigest(),
        )
        self.assertEqual(played, replayed)

        self.load(SLOT)
        save_handle.establish_save(SLOT)
        with open(path, encoding="utf-8") as f:
            second_file = json.load(f)
        for doc in (first_file, second_file):
            doc.pop(kernel_state.TOKEN)
        self.assertEqual(second_file, first_file)

    def test_adopt_synthetic_v16_save(self) -> None:
        """合成 v16 旧存档（角色带四个旧属性、float 理智消耗）读档后完整迁入内核并删去旧属性"""
        game_type = game("Script.Core.game_type")
        save_handle = game("Script.Core.save_handle")
        kernel_state = game("Script.Modules.save_load.kernel_state")
        flags = kd.domain("flags")
        action_info = kd.domain("action_info")
        player_ability = kd.domain("player_ability")
        player_collection = kd.domain("player_collection")

        npc_id = min(
            cid for cid in kd.domain("roster").active_sorted() if cid != 0
        )
        save_handle.establish_save("v16_old")

        # 改写文件 "2" 为 v16 且去掉四个新键
        p2 = os.path.join(self.folder, "v16_old", kernel_state.SAVE_FILE)
        with open(p2, encoding="utf-8") as f:
            doc = json.load(f)
        doc["version"] = 16
        for entry in doc["characters"].values():
            for k in (
                flags.KEY,
                action_info.KEY,
                player_ability.KEY,
                player_collection.KEY,
            ):
                entry["data"].pop(k, None)
        with open(p2, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)

        # 改写文件 "1"：给玩家和一名干员挂上旧属性
        loaded = save_handle.load_save("v16_old")
        sp = game_type.SPECIAL_FLAG()
        sp.vistor = 2
        vars(loaded.character_data[npc_id])["sp_flag"] = sp
        ai = game_type.ACTION_INFO()
        ai.health_check_today = 1
        vars(loaded.character_data[npc_id])["action_info"] = ai
        pa = game_type.PLAYER_ABILITY()
        vars(pa)["today_sanity_point_cost"] = 0.25
        pa.jj_size = 3
        vars(loaded.character_data[0])["pl_ability"] = pa
        pc = game_type.PLAYER_COLLECTION()
        pc.used_condoms = [7, 9]
        vars(loaded.character_data[0])["pl_collection"] = pc
        save_handle.write_save_data("v16_old", "1", loaded)

        self.load("v16_old")
        self.assertEqual(flags.get(npc_id, "vistor"), 2)
        self.assertEqual(action_info.get(npc_id, "health_check_today"), 1)
        cost = player_ability.get(0, "today_sanity_point_cost")
        self.assertIs(type(cost), Fraction)
        self.assertEqual(cost, Fraction(1, 4))
        self.assertEqual(player_ability.get(0, "jj_size"), 3)
        self.assertEqual(player_collection.get("used_condoms"), [7, 9])
        for cid in (0, npc_id):
            ch = self.cache.character_data[cid]
            for attr in (
                "sp_flag",
                "action_info",
                "pl_ability",
                "pl_collection",
            ):
                self.assertFalse(hasattr(ch, attr))
