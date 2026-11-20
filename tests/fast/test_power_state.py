# -*- coding: UTF-8 -*-
"""
基地动力的状态（base.power 与 base.power_storage）
==================================================
- 最大储能是各级蓄电池数量乘单体容量之和。存入电量后储能不超过最大储能。
- 面板的增减。蓄电池与清洁能源设施合计已达上限时不增加，并交回上限。拆掉蓄电池后储能降到新的最大储能。
- 任命主调控员。不是调控员的不任命。同一人任命到另一类时从原来那类撤下。再任命同一类时撤下。
- 一天的结算。发电不足时储能补进缺口，补不上的部分占耗电量的比例是缺口比例。
  发电有余时先自放电，再充回满，余下的溢出。燃料按计划扣除。
- 读档。罗德岛对象带着动力属性（旧存档）时，值写进 GameState，属性从对象上删掉，缺的属性取默认值。
  对象上没有动力属性（当前存档）时 GameState 不变。
- 自检 ISLAND-27（储能不超过最大储能）与 ISLAND-28（主调控员槽位有效）各试一个合法值与一个违规值。
  ISLAND-28 的修复清空指向不存在角色的槽位。
- 公务事件把储能设为取整后的值，读出 float。
"""

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.domains import power, power_supply
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import upgrade
from Script.System.Official_Event_System import ri_value
from Script.Test.Static_Check import repair
from Script.Test.Static_Check.check_registry import get_all_checks
from tests.fast.base import FastTestCase


class PowerStateTest(FastTestCase):
    """基地动力的状态、面板的增减、每天的结算、读档、自检与公务事件"""

    def setUp(self) -> None:
        """博士一人。GameState 的读写记在 working.based_on(core.state()) 开的缓冲区里。记下各级蓄电池的单体容量"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        self.caps = power.storage_levels("电池容量", int, 0)

    def flagged(self, check_id: str) -> bool:
        """
        跑一项自检
        Keyword arguments:
        check_id -- 检查编号
        Return arguments:
        bool -- 这项检查报了问题时为 True
        """
        _name, run = get_all_checks()[check_id]
        return bool(run())

    def test_storage_max_and_store(self) -> None:
        """最大储能是各级数量乘单体容量之和。存入的电量超过最大储能时，储能停在最大储能"""
        power.set_plant(batteries=(2, 1, 0))
        self.assertEqual(power.storage_max(), 2 * self.caps[0] + self.caps[1])
        power.store(10)
        self.assertEqual(power.storage(), 10)
        power.store(power.storage_max())
        self.assertEqual(power.storage(), power.storage_max())

    def test_battery_limit_and_clamp(self) -> None:
        """动力区 1 级且没有扩展模块时最多 10 台蓄电池，再加时交回上限 10。拆掉一台后储能降到新的最大储能"""
        for _ in range(10):
            self.assertIsNone(power.change_battery(0, 1))
        self.assertEqual(power.change_battery(1, 1), 10)
        self.assertEqual(power.plant()["batteries"], (10, 0, 0))
        power.set_storage(power.storage_max())
        power.change_battery(0, -1)
        self.assertEqual(power.storage(), 9 * self.caps[0])

    def test_clean_limit(self) -> None:
        """动力区 1 级且没有扩展模块时，三类清洁能源设施合计最多 5 组。数量为 0 时减少不改数量"""
        self.assertIsNone(power.change_clean(1, -1))
        for kind in (0, 0, 1, 2, 2):
            self.assertIsNone(power.change_clean(kind, 1))
        self.assertEqual(power.change_clean(1, 1), 5)
        self.assertEqual(power.plant()["clean"], (2, 1, 2))

    def test_appoint_main_operator(self) -> None:
        """不是调控员的不任命。同一人任命到另一类时从原来那类撤下。再任命同一类时撤下"""
        self.world.chara(1, "干员甲")
        self.world.chara(2, "干员乙")
        self.cache.rhodes_island.all_work_npc_set[power.OPERATOR_WORK] = {1}
        power.appoint_main_operator(1, 2)
        self.assertEqual(power.plant()["main_operators"], (0, 0, 0, 0))
        power.appoint_main_operator(1, 1)
        power.appoint_main_operator(3, 1)
        self.assertEqual(power.plant()["main_operators"], (0, 0, 0, 1))
        power.appoint_main_operator(3, 1)
        self.assertEqual(power.plant()["main_operators"], (0, 0, 0, 0))

    def test_short_day_draws_storage(self) -> None:
        """不发电的一天。储能全部补进缺口，补不上的部分占耗电量的比例是缺口比例"""
        power.set_plant(aux_reactors=0, batteries=(1, 0, 0))
        power.set_storage(5.0)
        consumed = power_supply.power_consumption()
        self.assertGreater(consumed, 5.0, "前提：耗电多于储能")
        day = power_supply.settle_day()
        self.assertTrue(day["short"])
        self.assertEqual((day["drawn"], power.storage()), (5.0, 0.0))
        self.assertEqual(day["shortage_ratio"], (consumed - 5.0) / consumed)

    def test_surplus_day_fills_batteries(self) -> None:
        """发电有余的一天。满储能先自放电，再充回满，余下的溢出。燃料按计划扣除"""
        island = self.cache.rhodes_island
        island.materials_resouce[15] = 10**6
        power.set_plant(aux_reactors=50, batteries=(1, 0, 0))
        power.set_storage(self.caps[0])
        rate = power.storage_levels("自放电率", float, 0.0)[0]
        day = power_supply.settle_day()
        self.assertFalse(day["short"])
        self.assertEqual(
            day["after_discharge"], self.caps[0] - self.caps[0] * rate
        )
        self.assertEqual(power.storage(), self.caps[0])
        self.assertEqual(day["overflow"], day["surplus"] - day["charged"])
        self.assertGreater(day["overflow"], 0)
        self.assertEqual(
            island.materials_resouce[15], 10**6 - int(day["fuel_plan"])
        )

    def test_old_island_moves_into_state(self) -> None:
        """旧存档的罗德岛对象带着全部动力属性。动力值写进 GameState，这些属性从对象上删掉"""
        island = game_type.Rhodes_Island()
        vars(island).update(
            power_use=0,
            power_max=0,
            power_storage=123.5,
            power_storage_max=9,
            power_operator_ids_list=[7],
            main_power_facility_operator_ids=[0, 7, 0, 0],
            orundum_reactor_list=[2, 5],
            other_power_facility_list=[1, 2, 3],
            battery_list=[2, 0, 0],
            now_used_extra_clean_energy_module_count=1,
            now_used_extra_battery_count=0,
        )
        upgrade.adopt_power({"rhodes_island": island})
        self.assertEqual(
            dict(power.plant()),
            {
                "aux_reactors": 5,
                "clean": (1, 2, 3),
                "batteries": (2, 0, 0),
                "main_operators": (0, 7, 0, 0),
            },
        )
        self.assertEqual(power.storage(), 123.5)
        self.assertEqual(set(upgrade.V1_POWER) & set(vars(island)), set())

    def test_old_island_missing_fields(self) -> None:
        """旧存档的罗德岛对象只带一部分动力属性。缺的取 DEFAULT_PLANT 的值，储能为 0.0"""
        island = game_type.Rhodes_Island()
        vars(island)["battery_list"] = [0, 1, 0]
        upgrade.adopt_power({"rhodes_island": island})
        self.assertEqual(
            dict(power.plant()), {**power.DEFAULT_PLANT, "batteries": (0, 1, 0)}
        )
        self.assertEqual(power.storage(), 0.0)

    def test_current_island_keeps_state(self) -> None:
        """当前存档的罗德岛对象没有动力属性。GameState 里的动力不变"""
        power.set_plant(batteries=(3, 0, 0))
        power.set_storage(7)
        upgrade.adopt_power({"rhodes_island": game_type.Rhodes_Island()})
        self.assertEqual(power.plant()["batteries"], (3, 0, 0))
        self.assertEqual(power.storage(), 7)

    def test_island_checks_and_repair(self) -> None:
        """ISLAND-27 与 ISLAND-28 对合法值不报、对违规值报。ISLAND-28 的修复清空指向不存在角色的槽位"""
        power.set_plant(batteries=(1, 0, 0))
        power.set_storage(self.caps[0])
        self.assertFalse(self.flagged("ISLAND-27"))
        power.set_storage(self.caps[0] + 1)
        self.assertTrue(self.flagged("ISLAND-27"))
        self.world.chara(1, "干员甲").work.work_type = power.OPERATOR_WORK
        power.set_plant(main_operators=(1, 0, 0, 0))
        self.assertFalse(self.flagged("ISLAND-28"))
        power.set_plant(main_operators=(1, 9999, 0, 0))
        self.assertTrue(self.flagged("ISLAND-28"))
        repair.repair_main_power_operator_slots(self.cache)
        self.assertEqual(power.plant()["main_operators"], (1, 0, 0, 0))

    def test_official_event_power(self) -> None:
        """公务事件把储能设为取整后的值，读出的是 float"""
        ri_value.set_ri_value(ri_value.RI_TYPE_POWER, 42.7)
        self.assertEqual(power.storage(), 42)
        self.assertEqual(ri_value.get_ri_value(ri_value.RI_TYPE_POWER), 42.0)
