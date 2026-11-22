# -*- coding: UTF-8 -*-
"""
新周目重建的体力、气力与理智
============================
开新游戏，把博士的体力上限设为 3000、气力上限 2600、理智上限 300，玩家额外上限的继承档位选 2（继承比例 100%），
开新周目，按下「[醒来]」。
- 博士的三项上限按继承比例从旧周目的值算出：1000 + (3000 - 1000) = 3000，1000 + (2600 - 1000) = 2600，
  100 + (300 - 100) = 300。
- 每名干员的体力与气力上限等于角色模板的，体力与气力等于上限，愤怒在 1 到 34 之间。
"""

import importlib
from types import ModuleType

from tests import kernel_data
from tests.slow.base import SlowTestCase


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回这个模块"""
    return importlib.import_module(name)


class NewRoundVitalsTest(SlowTestCase):
    """新周目里博士的上限按继承比例算出，干员的上限取模板"""

    def test_new_round_rebuilds_vitals(self) -> None:
        """博士的三项上限按继承比例算出。干员的体力与气力上限取模板，体力与气力等于上限，愤怒在 1 到 34 之间"""
        from tests import world

        new_round = game("Script.UI.Panel.new_round")
        cache_control = game("Script.Core.cache_control")
        npc_template = game("Script.Modules.domains.npc_template")
        kernel_data.set_needs(0, hit_max=3000, mana_max=2600, sanity_max=300)
        handle = new_round.New_Round_Handle()
        handle.pl_extra_growth_count = 2
        self.world.player.press("醒来")
        world.act(handle.start_new_round)
        self.world.player.check_done()
        player = kernel_data.needs_of(0)
        self.assertEqual(
            {k: player[k] for k in ("hit_max", "mana_max", "sanity_max")},
            {"hit_max": 3000, "mana_max": 2600, "sanity_max": 300},
        )
        cache = cache_control.cache
        npcs = [cid for cid in cache.character_data if cid != 0]
        self.assertTrue(npcs, "新周目有干员")
        wrong = {}
        for cid in npcs:
            tem = npc_template.get(cid)
            stats = kernel_data.needs_of(cid)
            got = tuple(
                stats[k] for k in ("hit_max", "mana_max", "hit", "mana")
            )
            angry = stats["angry"]
            if got != (tem.Hp, tem.Mp, tem.Hp, tem.Mp) or not 1 <= angry <= 34:
                wrong[cid] = (got, angry)
        self.assertEqual(wrong, {}, "上限、体力、气力或愤怒不对的干员")
