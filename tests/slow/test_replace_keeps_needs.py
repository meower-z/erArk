# -*- coding: UTF-8 -*-
"""
角色替换时 body.needs、主调控员、岗位名册与监狱长跟到新id
==========================================================
开新游戏，取一名在场干员当旧角色，一名不在场角色的id当新id（从存档属性表的角色表里删掉它），按这个映射跑读档的角色替换。
- 当前存档：新id的 body.needs 里体力与气力上限取新id的模板，醉酒为 0，其余各项等于旧角色的。
- 主调控员是旧角色时，替换后 base.power 里的主调控员是新id。
- 旧角色在招聘专员名册里、也是监狱长时，替换后名册里她的位置换成新id，监狱长是新id，名册里别人不变。
- 旧存档：旧角色对象带着疲劳、饥饿、尿意属性时，这些属性抄到新角色对象上，留给读档后面的 upgrade.adopt_v0。
- 版本 1 与 2 的存档：疲劳、饥饿、尿意、乳汁在 GameState 里，旧角色对象带着体力等十项属性。
  新角色对象抄过属性、再经读档后面的 upgrade.adopt_pickled 写进 body.needs 之后，与当前存档得到的相同。
"""

import importlib
from fractions import Fraction
from types import ModuleType

from tests.slow.base import SlowTestCase
from tests import kernel_data

NEEDS = {
    "tired": Fraction(7, 3),
    "hunger": 100,
    "urine": 61,
    "milk": Fraction(37, 8),
    "hit": Fraction(901, 2),
    "hit_max": 1500,
    "mana": 300,
    "mana_max": 1200,
    "sanity": 40,
    "sanity_max": 90,
    "angry": 20,
    "sleep": Fraction(10, 3),
    "desire": 55,
    "drunk": 30,
}
""" 旧角色的十四项数值。版本 1 的存档用例里，其中十项是旧角色对象的属性，GS1_NEEDS 的四项写进 body.needs """
GS1_NEEDS = ("tired", "hunger", "urine", "milk")
""" 版本 1 的存档里已在 GameState（文件 "2"）里的四项 """
OTHER = 99999
""" 名册里不参与替换的另一个角色id """


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


class ReplaceKeepsNeedsTest(SlowTestCase):
    """读档的角色替换带走生理需求"""

    def setUp(self) -> None:
        """取旧角色与新id。存档属性表用缓存属性的浅拷贝，角色表另拷一份并删掉新id"""
        super().setUp()
        self.old = min(
            cid for cid in kernel_data.domain("roster").active() if cid != 0
        )
        self.new = max(
            cid
            for cid in self.cache.character_data
            if cid not in kernel_data.domain("roster").active()
            and cid in game("Script.Config.character_config").character_tem_list
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

    def template_maxima(self) -> dict[str, int]:
        """新id模板的体力与气力上限，键是 body.needs 的项"""
        tem = game("Script.Config.character_config").character_tem_list[
            self.new
        ]
        return {"hit_max": tem.Hp, "mana_max": tem.Mp}

    def test_current_save_moves_needs(self) -> None:
        """当前存档：新id的体力与气力上限取模板，醉酒为 0，其余各项等于旧角色的"""
        core = game("Script.Kernel.core")
        needs = game("Script.Modules.domains.needs")
        working = game("Script.Modules.gameplay_resolution.working")
        with working.based_on(core.state()):
            needs.set(self.old, **NEEDS)
            self.replace()
            got = dict(needs.of(self.new))
        want = {**NEEDS, **self.template_maxima(), "drunk": 0}
        self.assertEqual(got, want)

    def test_pickled_stats_copy_attributes(self) -> None:
        """版本 1 与 2 的存档：新角色对象抄过属性、再经 adopt_pickled 写进 body.needs 之后，与当前存档得到的相同"""
        core = game("Script.Kernel.core")
        game_type = game("Script.Core.game_type")
        needs = game("Script.Modules.domains.needs")
        upgrade = game("Script.Modules.save_load.upgrade")
        working = game("Script.Modules.gameplay_resolution.working")
        old = self.loaded["character_data"][self.old]
        vars(old)["pregnancy"] = game_type.PREGNANCY()
        for name, stat in upgrade.PICKLED_NEEDS.items():
            setattr(old, name, NEEDS[stat])
        with working.based_on(core.state()):
            needs.set(self.old, **{k: NEEDS[k] for k in GS1_NEEDS})
            self.replace()
            new = self.loaded["character_data"][self.new]
            upgrade.adopt_pickled({"character_data": {self.new: new}})
            got = dict(needs.of(self.new))
        want = {**NEEDS, **self.template_maxima(), "drunk": 0}
        self.assertEqual(got, want)

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

    def test_roster_and_warden_follow_id(self) -> None:
        """旧角色在招聘专员名册里、也是监狱长时，角色替换后名册里的位置与监狱长都是新id"""
        core = game("Script.Kernel.core")
        work = game("Script.Modules.domains.work")
        working = game("Script.Modules.gameplay_resolution.working")
        with working.based_on(core.state()):
            work.set_rosters({work.HR_WORK: [OTHER, self.old]})
            work.set_warden(self.old)
            self.replace()
            got = (work.roster(work.HR_WORK), work.warden())
        self.assertEqual(got, ((OTHER, self.new), self.new))

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
