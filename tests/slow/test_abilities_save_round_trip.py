# -*- coding: UTF-8 -*-
"""
角色的能力、经验、宝珠与素质表随存档存读往返并可继续推进
======================================================
新游戏里等待三次后，改写玩家的能力表，以及一名干员的经验表、宝珠表与素质表，再经 save_handle 存档。
存档的文件 "1" 里角色对象没有这四个属性，文件 "2" 里这名干员的数据有这四个键。
存档后再改写这些表，读档后每个角色的四张表都回到存档时的值。读档后再等待三次，时钟比存档时晚 15 分钟。
"""

import importlib
import json
import os
import shutil
from types import ModuleType

from tests import kernel_data
from tests.slow.base import SlowTestCase

SAVE_ID = "test_abilities_save_round_trip"
""" 本测试写进 save/ 的存档id，读档后删掉这个存档 """


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


class AbilitiesSaveRoundTripTest(SlowTestCase):
    """四张表随新游戏的存档存下，读档后还原，游戏照常推进"""

    def test_tables_survive_save_load_and_continue(self) -> None:
        """存档后改写四张表，读档后四张表回到存档时的值，再等待三次时钟推进 15 分钟"""
        from tests.snapshot_states import instruct

        constant = game("Script.Core.constant")
        core = game("Script.Kernel.core")
        save_handle = game("Script.Core.save_handle")
        abilities = game("Script.Modules.domains.abilities")

        for _ in range(3):
            instruct(self.world, constant.Instruct.WAIT)
        cache = self.world.cache
        npc = next(cid for cid in sorted(cache.npc_id_got) if cid)
        first = {
            key: next(iter(abilities.Table(npc, key)))
            for key in abilities.PICKLED.values()
        }
        with kernel_data.writing():
            abilities.ability(0)[first[abilities.ABILITY]] += 2
            abilities.experience(npc)[first[abilities.EXPERIENCE]] += 30
            abilities.juel(npc)[first[abilities.JUEL]] += 500
            abilities.talent(npc)[first[abilities.TALENT]] = 1

        def tables() -> dict[tuple[int, str], dict[int, int]]:
            return {
                (cid, key): abilities.Table(cid, key).copy()
                for cid in sorted(cache.character_data)
                for key in abilities.PICKLED.values()
            }

        saved = tables()
        saved_clock = core.state().clock
        save_handle.establish_save(SAVE_ID)
        path = save_handle.get_save_dir_path(SAVE_ID)
        try:
            pickled = save_handle.load_save(SAVE_ID)
            with open(os.path.join(path, "2"), encoding="utf-8") as f:
                state = json.load(f)
            with kernel_data.writing():
                abilities.ability(0)[first[abilities.ABILITY]] = 0
                abilities.experience(npc).replace({})
                abilities.clear(npc)
            save_handle.input_load_save(SAVE_ID)
        finally:
            shutil.rmtree(path, ignore_errors=True)
        for chara in pickled.character_data.values():
            for name in abilities.PICKLED:
                self.assertNotIn(name, vars(chara))
        stored = {
            *state["data"].get("roster.offstage", {}).get(str(npc), {}),
            *state["characters"].get(str(npc), {}).get("data", {}),
        }
        self.assertTrue(set(abilities.PICKLED.values()) <= stored, stored)
        self.assertTrue(tables() == saved, "四张表读档后回到存档时的值")
        self.assertEqual(core.state().clock, saved_clock)
        for _ in range(3):
            instruct(self.world, constant.Instruct.WAIT)
        self.assertEqual(core.state().clock, saved_clock + 15)
