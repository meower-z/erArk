# -*- coding: UTF-8 -*-
"""
角色替换时生理需求与主调控员跟到新id
====================================
开新游戏，取一名在场干员当旧角色，一名不在场角色的id当新id（从存档属性表的角色表里删掉它），按这个映射跑读档的角色替换。
- 当前存档时，新id的生理需求（body.needs）四项都等于旧角色的。
- 主调控员是旧角色时，替换后 base.power 里的主调控员是新id。
- 旧存档时，旧角色对象带着疲劳、饥饿、尿意属性，这些属性抄到新角色对象上，留给读档后面的 upgrade.adopt_v0。
"""

import importlib
from fractions import Fraction
from types import ModuleType

from tests.slow.base import SlowTestCase

NEEDS = {
    "tired": Fraction(7, 3),
    "hunger": 100,
    "urine": 61,
    "milk": Fraction(37, 8),
}
""" 旧角色的生理需求 """


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


class ReplaceKeepsNeedsTest(SlowTestCase):
    """读档的角色替换带走生理需求"""

    def setUp(self) -> None:
        """取旧角色与新id。存档属性表用缓存属性的浅拷贝，角色表另拷一份并删掉新id"""
        super().setUp()
        self.old = min(cid for cid in self.cache.npc_id_got if cid != 0)
        self.new = max(
            cid
            for cid in self.cache.character_data
            if cid not in self.cache.npc_id_got
            and cid in self.cache.npc_tem_data
        )
        self.loaded = dict(vars(self.cache))
        self.loaded["character_data"] = dict(self.cache.character_data)
        del self.loaded["character_data"][self.new]

    def replace(self) -> None:
        """按旧角色到新id的映射跑角色替换，断言替换了一名"""
        migrate = game("Script.Core.old_chara_to_new")
        count = migrate.migrate_character_replacement(
            self.loaded, {self.old: self.new}
        )
        self.assertEqual(count, 1)

    def test_current_save_moves_needs(self) -> None:
        """当前存档：新id的生理需求等于旧角色的"""
        core = game("Script.Kernel.core")
        needs = game("Script.Modules.domains.needs")
        working = game("Script.Modules.gameplay_resolution.working")
        with working.based_on(core.state()):
            needs.set(self.old, **NEEDS)
            self.replace()
            self.assertEqual(dict(needs.of(self.new)), NEEDS)

    def test_main_power_operator_follows_id(self) -> None:
        """主调控员是旧角色时，角色替换后主调控员是新id"""
        core = game("Script.Kernel.core")
        power = game("Script.Modules.domains.power")
        working = game("Script.Modules.gameplay_resolution.working")
        with working.based_on(core.state()):
            power.set_plant(main_operators=(0, self.old, 0, 0))
            self.replace()
            mains = power.plant()["main_operators"]
        self.assertEqual(mains, (0, self.new, 0, 0))

    def test_old_save_copies_attributes(self) -> None:
        """旧存档：旧角色对象上的属性抄到新角色对象上"""
        core = game("Script.Kernel.core")
        upgrade = game("Script.Modules.save_load.upgrade")
        working = game("Script.Modules.gameplay_resolution.working")
        old = self.loaded["character_data"][self.old]
        for name, stat in upgrade.V0_NEEDS.items():
            setattr(old, name, NEEDS[stat])
        with working.based_on(core.state()):
            self.replace()
        new = self.loaded["character_data"][self.new]
        self.assertEqual(
            {
                stat: getattr(new, name)
                for name, stat in upgrade.V0_NEEDS.items()
            },
            {stat: NEEDS[stat] for stat in upgrade.V0_NEEDS.values()},
        )
