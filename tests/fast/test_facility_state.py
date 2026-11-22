# -*- coding: UTF-8 -*-
"""
基地设施的状态（base.facility_level、base.facility_open 与 base.effectiveness）
===============================================================================
- 设施等级与基地效率影响设施的工作效率。宿舍区从 1 级升到 3 级，效率加 0.04。基地效率从 100 改为 150，效率再加 0.5。
- 宿舍区升到 2 级后刷新基地。开放所需的区块等级是宿舍区 2 级的房间都开放。干员人数上限是宿舍区 2 级的效果值。
- 剩余公务远超总工作量时，每日公务结算把基地效率降到下限 50。公务事件读到的效率也是 50。
- 公务事件写基地效率时，值限在 50~200 之间并保留一位小数。公务事件写设施等级被忽略。
- 读档：版本 3 的罗德岛对象带着三个设施属性。adopt_facility 把它们的值写进 GameState，再从对象上删掉这些属性。
  版本 0 的对象只带设施等级时，adopt_facility 只写等级并交回 2。版本 4 的对象没有设施属性时，GameState 不变。
- 自检 ISLAND-02（等级落在配置区间）与 ISLAND-03（不超过控制中枢等级 + 1）对合法的等级不报，对违规的等级报。
"""

from Script.Config import game_config
from Script.Design import basement
from Script.Kernel import core
from Script.Modules.domains import facility, official
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import upgrade
from Script.System.Official_Event_System import ri_value
from Script.Test.Static_Check.check_registry import get_all_checks
from tests.fast.base import FastTestCase
from Script.Modules.save_load.legacy_pickle import LegacyObject

DORMITORY = 4
""" 宿舍区的设施id """
OFFICE = 7
""" 文职部的设施id """


class FacilityStateTest(FastTestCase):
    """设施等级、开放情况与基地效率在基地刷新、公务结算、公务事件、读档与自检里的读写"""

    def setUp(self) -> None:
        """博士一人。测试在以当前状态为底的缓冲区里读写 GameState，测试结束时丢掉这个缓冲区"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))

    def flagged(self, check_id: str) -> bool:
        """
        跑一项自检
        Keyword arguments:
        check_id -- 自检编号，例如 ISLAND-02
        Return arguments:
        bool -- 这项自检报了问题时为 True
        """
        _name, run = get_all_checks()[check_id]
        return bool(run())

    def test_level_and_effectiveness_drive_efficiency(self) -> None:
        """宿舍区从 1 级升到 3 级，工作效率加 0.04。基地效率从 100 改为 150，工作效率再加 0.5。基地的全局效率为 1.5"""
        start = basement.calc_facility_efficiency(DORMITORY)
        facility.set_level(DORMITORY, 3)
        raised = basement.calc_facility_efficiency(DORMITORY)
        self.assertAlmostEqual(raised - start, 0.04)
        facility.set_effectiveness(150)
        self.assertAlmostEqual(
            basement.calc_facility_efficiency(DORMITORY) - raised, 0.5
        )
        self.assertEqual(basement.calc_facility_efficiency(), 1.5)

    def test_refresh_opens_rooms_of_the_level(self) -> None:
        """宿舍区升到 2 级后刷新基地。开放所需的区块等级是宿舍区 2 级的房间都开放。干员人数上限是宿舍区 2 级的效果值"""
        name = game_config.config_facility[DORMITORY].name
        effect_cid = game_config.config_facility_effect_data[name][2]
        rooms = [
            cid
            for cid, room in game_config.config_facility_open.items()
            if room.zone_cid == effect_cid
        ]
        self.assertTrue(rooms, "宿舍区 2 级开放房间")
        self.assertFalse(any(facility.is_open(cid) for cid in rooms))
        facility.set_level(DORMITORY, 2)
        basement.get_base_updata()
        self.assertTrue(all(facility.is_open(cid) for cid in rooms))
        self.assertEqual(
            facility.people_max(),
            game_config.config_facility_effect[effect_cid].effect,
        )

    def test_office_work_settle_floors_effectiveness(self) -> None:
        """剩余公务远超总工作量时，每日公务结算把基地效率降到 50。公务事件读到的效率也是 50"""
        official.set_office_work(10**6)
        basement.settle_office_work()
        self.assertEqual(facility.effectiveness(), 50)
        self.assertEqual(
            ri_value.get_ri_value(ri_value.RI_TYPE_EFFECTIVENESS), 50.0
        )

    def test_official_event_values(self) -> None:
        """公务事件写效率 250 时存下 200，写 87.26 时存下 87.3。写设施等级被忽略。读设施等级读到当前等级"""
        ri_value.set_ri_value(ri_value.RI_TYPE_EFFECTIVENESS, 250)
        self.assertEqual(facility.effectiveness(), 200)
        ri_value.set_ri_value(ri_value.RI_TYPE_EFFECTIVENESS, 87.26)
        self.assertEqual(facility.effectiveness(), 87.3)
        token = f"{ri_value.RI_TYPE_FACILITY}|{OFFICE}"
        ri_value.set_ri_value(token, 5)
        self.assertEqual(facility.level(OFFICE), 1)
        facility.set_level(OFFICE, 2)
        self.assertEqual(ri_value.get_ri_value(token), 2.0)

    def test_old_island_moves_into_state(self) -> None:
        """版本 3 的罗德岛对象带着三个设施属性。adopt_facility 把值写进 GameState，并删掉这些属性。缺的个数为 0"""
        island = LegacyObject()
        vars(island).update(
            facility_level={0: 2, OFFICE: 3},
            facility_open={101: True, 102: False},
            effectiveness=87.5,
        )
        missing = upgrade.adopt_facility({"rhodes_island": island}, 3)
        self.assertEqual(missing, 0)
        self.assertEqual(facility.levels(), {0: 2, OFFICE: 3})
        self.assertEqual(facility.opens(), {101: True, 102: False})
        self.assertEqual(facility.effectiveness(), 87.5)
        self.assertEqual(
            set(upgrade.PICKLED_FACILITY) & set(vars(island)), set()
        )

    def test_old_island_missing_fields(self) -> None:
        """版本 0 的罗德岛对象只带设施等级。adopt_facility 只写等级。开放情况与效率不变。缺的个数为 2"""
        opens = facility.opens()
        island = LegacyObject()
        vars(island)["facility_level"] = {OFFICE: 4}
        missing = upgrade.adopt_facility({"rhodes_island": island}, 0)
        self.assertEqual(missing, 2)
        self.assertEqual(facility.levels(), {OFFICE: 4})
        self.assertEqual(facility.opens(), opens)
        self.assertEqual(facility.effectiveness(), 100)

    def test_current_island_keeps_state(self) -> None:
        """版本 4 的罗德岛对象没有设施属性。GameState 里的设施等级与效率不变。缺的个数为 0"""
        facility.set_level(OFFICE, 3)
        facility.set_effectiveness(120)
        missing = upgrade.adopt_facility({"rhodes_island": LegacyObject()}, 4)
        self.assertEqual(missing, 0)
        self.assertEqual(facility.level(OFFICE), 3)
        self.assertEqual(facility.effectiveness(), 120)

    def test_island_checks(self) -> None:
        """ISLAND-02 报 99 级的设施。ISLAND-03 报比控制中枢高 2 级的设施。合法的等级两项都不报"""
        self.assertFalse(self.flagged("ISLAND-02"))
        self.assertFalse(self.flagged("ISLAND-03"))
        facility.set_level(OFFICE, 99)
        self.assertTrue(self.flagged("ISLAND-02"))
        facility.set_level(OFFICE, 3)
        self.assertFalse(self.flagged("ISLAND-02"))
        self.assertTrue(self.flagged("ISLAND-03"))
        facility.set_level(0, 2)
        self.assertFalse(self.flagged("ISLAND-03"))
