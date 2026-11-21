# -*- coding: UTF-8 -*-
"""
工程部与体检的状态（maintenance 与 physical_exam 的全局键）
===========================================================
- 读档：罗德岛对象上旧的十二个属性的值写进 GameState，属性从对象上删掉。以角色id为键的表读回时键为 int，
  集合读回为集合。设施损坏、检修地点、装备维护对象与体检日保持原来的先后。另一种系统的路径分隔符换成本系统的。
  对象带着一个模块的任一旧属性或版本低于 15 时，这个模块缺了或类型不符的属性计数。类型不符的属性不导入。
- 设施损坏：按第一次损坏的先后排列。改损坏值不改位置。损坏值降到 0 以下时去掉这个场景。
- 体检：记下的检查留在正在进行的体检里。结束体检时，这些检查移进今日已体检，受检者进本周期已体检名单并离开等待名单。
- 换id：检修地点、维修记录、装备维护对象、今日已体检与三份体检名单里的旧id换成新id。drop 交回去掉的项数。
"""

import os
from types import SimpleNamespace

from Script.Kernel import core
from Script.Modules.domains import maintenance, physical_exam
from Script.Modules.gameplay_resolution import working
from tests.fast.base import FastTestCase

FOREIGN = "\\" if os.sep == "/" else "/"
""" 另一种系统的路径分隔符 """


def local(*parts: str) -> str:
    """
    本系统的场景路径
    Keyword arguments:
    parts -- 路径的各段
    Return arguments:
    str -- 用 os.sep 连起来的路径
    """
    return os.sep.join(parts)


def old_island() -> SimpleNamespace:
    """
    带着旧的十二个属性的罗德岛对象，值是旧存档里的类型。对象另有一个不归这两个模块管的属性 office_work
    Return arguments:
    SimpleNamespace -- 罗德岛对象
    """
    return SimpleNamespace(
        facility_damage_data={
            FOREIGN.join(["区域甲", "房间一"]): 2,
            "房间二": 1,
        },
        maintenance_place={5: FOREIGN.join(["区域甲", "房间一"]), 3: "房间二"},
        maintenance_equipment_chara_id={7: 5},
        equipment_maintain_setting={0: 1, 3: 0},
        equipment_maintain_operator_ids=[9, 5],
        physical_examination_setting={2: 1, 3: 3, 4: 2},
        today_physical_examination_chara_id_dict={5: {"check_b", "check_a"}},
        physical_examination_in_progress={7: {"check_a"}},
        examined_operator_ids={9, 5},
        waiting_for_exam_operator_ids={7},
        manually_selected_exam_operator_ids={5},
        manually_selected_exam_week_day_list=[4, 1],
        office_work=3,
    )


class MaintenanceExamStateTest(FastTestCase):
    """读档导入、设施损坏的先后、体检的结束、换id与 drop"""

    def setUp(self) -> None:
        """以 core.state() 为底开一个缓冲区，测试里对 GameState 的读写都对着它"""
        super().setUp()
        self.enterContext(working.based_on(core.state()))

    def adopt(self, island: SimpleNamespace, version: int) -> int:
        """
        用两个模块的 adopt_old_save 读入罗德岛对象
        Keyword arguments:
        island -- 罗德岛对象
        version -- 存档的版本
        Return arguments:
        int -- 两个模块交回的属性个数之和
        """
        loaded = {"rhodes_island": island}
        return maintenance.adopt_old_save(
            loaded, version
        ) + physical_exam.adopt_old_save(loaded, version)

    def test_old_island_moves_into_state(self) -> None:
        """十二个属性的值写进 GameState，属性从对象上删掉。读回的类型与先后同原来，路径换成本系统的。属性齐全时不计数"""
        island = old_island()
        self.assertEqual(self.adopt(island, 14), 0)
        self.assertEqual(vars(island), {"office_work": 3})
        damage = maintenance.damage()
        self.assertEqual(list(damage), [local("区域甲", "房间一"), "房间二"])
        self.assertEqual(list(damage.values()), [2, 1])
        self.assertEqual(
            list(maintenance.places().items()),
            [(5, local("区域甲", "房间一")), (3, "房间二")],
        )
        self.assertEqual(maintenance.repairs(), {7: 5})
        self.assertEqual(maintenance.settings(), {0: 1, 3: 0})
        self.assertEqual(maintenance.operators(), [9, 5])
        self.assertEqual(physical_exam.settings(), {2: 1, 3: 3, 4: 2})
        self.assertEqual(
            physical_exam.checks(physical_exam.TODAY),
            {5: {"check_a", "check_b"}},
        )
        self.assertEqual(
            physical_exam.checks(physical_exam.IN_PROGRESS), {7: {"check_a"}}
        )
        self.assertEqual(
            [physical_exam.ids(key) for key in physical_exam.ID_LISTS],
            [{5, 9}, {7}, {5}],
        )
        self.assertEqual(physical_exam.week_days(), [4, 1])

    def test_missing_or_mistyped_attributes(self) -> None:
        """
        版本低于 15 时，缺了或类型不符的属性计数，类型不符的值不导入。
        版本为 15 时，对象上没有旧属性时不计数。对象上只带 maintenance_place 时，计 maintenance 的其余四个属性
        """
        island = SimpleNamespace(
            facility_damage_data=["房间二"],
            examined_operator_ids=[5],
            manually_selected_exam_week_day_list=[2],
        )
        self.assertEqual(self.adopt(island, 0), 5 + 6)
        self.assertEqual(vars(island), {})
        self.assertEqual(maintenance.damage(), {})
        self.assertEqual(physical_exam.ids(physical_exam.EXAMINED), set())
        self.assertEqual(physical_exam.week_days(), [2])
        self.assertEqual(self.adopt(SimpleNamespace(), 15), 0)
        self.assertEqual(
            self.adopt(SimpleNamespace(maintenance_place={}), 15), 4
        )

    def test_damage_keeps_first_order(self) -> None:
        """改损坏值不改先后。损坏值降到 0 以下时去掉这个场景，它再损坏时排在最后"""
        maintenance.set_damage("房间一", 1)
        maintenance.set_damage("房间二", 2)
        maintenance.set_damage("房间一", 3)
        self.assertEqual(
            list(maintenance.damage().items()), [("房间一", 3), ("房间二", 2)]
        )
        maintenance.set_damage("房间一", -1)
        maintenance.set_damage("房间一", 1)
        self.assertEqual(list(maintenance.damage()), ["房间二", "房间一"])

    def test_finish_moves_checks(self) -> None:
        """结束体检时，做过的检查移进今日已体检，正在进行的体检清空。受检者进已体检名单并离开等待名单"""
        physical_exam.add(physical_exam.WAITING, 5)
        physical_exam.record_check(5, "check_a")
        physical_exam.record_check(5, "check_b")
        done = physical_exam.checks(physical_exam.IN_PROGRESS)[5]
        physical_exam.finish(5, done)
        self.assertEqual(
            physical_exam.checks(physical_exam.TODAY),
            {5: {"check_a", "check_b"}},
        )
        self.assertEqual(physical_exam.checks(physical_exam.IN_PROGRESS), {})
        self.assertTrue(physical_exam.has(physical_exam.EXAMINED, 5))
        self.assertFalse(physical_exam.has(physical_exam.WAITING, 5))

    def test_remap_and_drop(self) -> None:
        """换id后各处是新id。drop 去掉今日已体检与三份名单里的角色，并交回去掉的项数"""
        self.adopt(old_island(), 15)
        old_to_new = {5: 50, 7: 70}
        maintenance.remap(old_to_new)
        physical_exam.remap(old_to_new)
        self.assertEqual(list(maintenance.places()), [50, 3])
        self.assertEqual(maintenance.repairs(), {70: 50})
        self.assertEqual(maintenance.operators(), [9, 50])
        self.assertEqual(list(physical_exam.checks(physical_exam.TODAY)), [50])
        self.assertEqual(
            [physical_exam.ids(key) for key in physical_exam.ID_LISTS],
            [{9, 50}, {70}, {50}],
        )
        self.assertEqual(physical_exam.drop({50, 70}), 4)
        self.assertEqual(physical_exam.checks(physical_exam.TODAY), {})
        self.assertEqual(
            [physical_exam.ids(key) for key in physical_exam.ID_LISTS],
            [{9}, set(), set()],
        )
