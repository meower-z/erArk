"""
载具、装备维护、污秽查询与监禁调教后端服务测试
==============================================
- 载具服务（vehicle_service）：读档修补补齐缺失载具，以及外勤委托载具损坏结算与概率减半。
- 装备维护服务（equipment_service）：装备状态数值分段映射，以及外勤委托装备损坏等级结算。
- 污秽与状态查询（dirty_queries）：身体部位 6 与 7 当前精液量合计，以及同场景 insert_position 角色查询。
- 监禁调教服务（prison_service）：逃脱概率上下限、有无监狱长逃脱判定、入狱处理、空闲牢房与调教助手行为筛选选择。
"""

from fractions import Fraction
from unittest import mock

from Script.Config import game_config
from Script.Design import game_time, map_handle
from Script.Kernel import core
from Script.Modules.domains import activity, chara_life, commission, dirty
from Script.Modules.domains import flags, h_state, prison, wardrobe, work
from Script.Modules.gameplay_resolution import dirty_queries
from Script.Modules.gameplay_resolution import equipment_service
from Script.Modules.gameplay_resolution import instruct_filter
from Script.Modules.gameplay_resolution import prison_service
from Script.Modules.gameplay_resolution import vehicle_service, working
from Script.Modules.save_load import reset
from tests import chara_abilities as ca
from tests.fast.base import FastTestCase

LEVEL_ONE_COMMISSION = 1
""" 一级外勤委托测试编号（Commission.csv 编号 1） """
PRISONER = 1
""" 测试用囚犯角色编号 """
WARDEN = 2
""" 测试用监狱长角色编号 """


class VehicleServiceTest(FastTestCase):
    """载具服务（vehicle_service）的读档补齐与外勤损坏结算测试"""

    def setUp(self) -> None:
        """创建玩家角色并打开基于当前状态的工作集上下文"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))

    def test_load_repair_fills_missing_vehicles(self) -> None:
        """读档执行 repairs 修补步骤时，将载具表缺失的首项载具以 (0, 0) 追加到末尾且不改动其余项"""
        first, *rest = game_config.config_vehicle
        stored = {str(vid): (2, 1) for vid in rest}
        working.put(None, commission.VEHICLES, stored)
        repairs = next(step for step in reset.STEPS if step.name == "repairs")
        repairs.run(core.state(), {"cause": "load"})
        self.assertEqual(list(commission.vehicles()), [*rest, first])
        self.assertEqual(commission.vehicles()[first], (0, 0))
        for vid in rest:
            self.assertEqual(commission.vehicles()[vid], (2, 1))

    def test_settle_vehicle_breaks_and_halves_rate(self) -> None:
        """外勤委托结算载具时，命中损坏后持有数与外勤中数均减 1 且后续损坏率减半，未命中仅归还外勤中数"""
        first, second, third = list(game_config.config_vehicle)[:3]
        for vid in (first, second, third):
            commission.add_vehicle(vid, owned=2, out=1)
        commission.start(
            LEVEL_ONE_COMMISSION, [], game_time.now(), [first, second, third]
        )
        level = game_config.config_commission[LEVEL_ONE_COMMISSION].level
        between = 0.05 * level * 0.75
        with mock.patch("random.random", side_effect=[0.0, between, 0.0]):
            text = vehicle_service.settle_vehicle(LEVEL_ONE_COMMISSION)
        names = game_config.config_vehicle
        self.assertEqual(
            text, f"({names[first].name}损坏)({names[third].name}损坏)"
        )
        self.assertEqual(commission.vehicles()[first], (1, 0))
        self.assertEqual(commission.vehicles()[second], (2, 0))
        self.assertEqual(commission.vehicles()[third], (1, 0))


class EquipmentServiceTest(FastTestCase):
    """装备维护服务（equipment_service）的状态名称映射与外勤损坏结算测试"""

    def setUp(self) -> None:
        """创建玩家与三名干员角色并打开基于当前状态的工作集上下文"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "甲")
        self.world.chara(2, "乙")
        self.world.chara(3, "丙")
        self.enterContext(working.based_on(core.state()))

    def test_condition_name_thresholds(self) -> None:
        """验证装备状态数值在阈值点、区间内以及低于最低值或高于最高值时均返回对应配置名称"""
        cases = {
            -10: "严重损坏",
            -3: "严重损坏",
            -2.5: "严重损坏",
            -2: "中度损坏",
            -1: "轻微损坏",
            -0.5: "轻微损坏",
            0: "正常状态",
            1: "良好保养",
            2: "完美保养",
            10: "完美保养",
        }
        for value, name in cases.items():
            with self.subTest(value=value):
                self.assertEqual(
                    equipment_service.get_equipment_condition_name(value), name
                )

    def test_commission_damage_levels(self) -> None:
        """按一级委托损坏概率档位抽取随机数，验证各成员装备状态写入与损坏提示文本拼接"""
        commission.start(LEVEL_ONE_COMMISSION, [1, 2, 3], game_time.now(), [])
        with mock.patch("random.random", side_effect=[0.25, 0.7, 0.95]):
            text = equipment_service.settle_equipment_damage_in_commission(
                LEVEL_ONE_COMMISSION
            )
        self.assertEqual(wardrobe.of(1).equipment_condition, 0)
        self.assertEqual(wardrobe.of(2).equipment_condition, -1)
        self.assertEqual(wardrobe.of(3).equipment_condition, -2)
        self.assertEqual(
            text,
            "乙的装备损坏了，损坏情况为轻微损坏，需要进行维修。\n"
            "丙的装备损坏了，损坏情况为中度损坏，需要进行维修。\n",
        )


class DirtyQueriesTest(FastTestCase):
    """污秽与状态查询（dirty_queries）的精液量合计与同场景角色查询测试"""

    def setUp(self) -> None:
        """创建玩家、交互对象与同场景旁人角色并打开基于当前状态的工作集上下文"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "对方")
        self.world.chara(2, "旁人")
        self.enterContext(working.based_on(core.state()))

    def test_semen_count_sums_parts_six_and_seven(self) -> None:
        """精液量查询仅合计身体部位 6 与 7 并保留精确分数，无记录角色返回 0"""
        with dirty.editing(1) as d:
            d.body_semen[6][1] = Fraction(3, 2)
            d.body_semen[7][1] = 4
            d.body_semen[8][1] = 100
        self.assertEqual(
            dirty_queries.get_v_and_w_semen_count(1), Fraction(11, 2)
        )
        self.assertEqual(dirty_queries.get_v_and_w_semen_count(2), 0)

    def test_inserted_character_prefers_target(self) -> None:
        """同场景内无角色满足 insert_position 条件时返回 0，旁人与交互对象同时满足时优先返回交互对象"""
        activity.set_target(0, 1)
        self.assertEqual(dirty_queries.get_inserted_character_id(), 0)
        h_state.set(2, insert_position=6)
        self.assertEqual(dirty_queries.get_inserted_character_id(), 2)
        h_state.set(1, insert_position=6)
        self.assertEqual(dirty_queries.get_inserted_character_id(), 1)


class PrisonServiceTest(FastTestCase):
    """监禁与调教助手服务（prison_service）的逃脱、入狱、牢房与助手行为测试"""

    def setUp(self) -> None:
        """创建玩家、囚犯与监狱长角色，打开工作集上下文并重置监禁设置"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(PRISONER, "囚犯")
        self.world.chara(WARDEN, "监狱长")
        self.enterContext(working.based_on(core.state()))
        prison.reset_settings()

    def test_escape_probability_grows_with_floor_and_cap(self) -> None:
        """逃脱概率增量保底为 1、受剩余空间 10% 上限约束，且总概率不超过 100"""
        now = game_time.now()
        prison.imprison(PRISONER, now, 10)
        self.assertEqual(
            prison_service.calculate_escape_probability(PRISONER), 11
        )
        self.assertEqual(prison.escape_probability(PRISONER), 11)
        ca.ability(PRISONER)[42] = 10
        ca.ability(PRISONER)[45] = 10
        prison.set_setting(4, 2)
        prison.set_escape_probability(PRISONER, 50)
        self.assertEqual(
            prison_service.calculate_escape_probability(PRISONER), 55
        )
        prison.set_escape_probability(PRISONER, 100)
        self.assertEqual(
            prison_service.calculate_escape_probability(PRISONER), 100
        )

    def test_judge_can_escape_without_warden(self) -> None:
        """无监狱长时，非囚犯不可逃脱，囚犯逃脱概率大于 30 才判定为可逃脱"""
        self.assertEqual(
            prison_service.judge_can_escape(PRISONER), (False, 0, 0)
        )
        prison.imprison(PRISONER, game_time.now(), 31)
        self.assertEqual(
            prison_service.judge_can_escape(PRISONER), (True, 0, 0)
        )
        prison.set_escape_probability(PRISONER, 30)
        self.assertEqual(
            prison_service.judge_can_escape(PRISONER), (False, 0, 0)
        )

    def test_judge_can_escape_against_warden(self) -> None:
        """有监狱长时，低于门槛直接失败，达到门槛后按囚犯逃脱值与监狱长对抗值大小判定结果"""
        work.set_warden(WARDEN)
        prison.set_setting(4, 1)
        prison.imprison(PRISONER, game_time.now(), 10)
        self.assertEqual(
            prison_service.judge_can_escape(PRISONER), (False, 0, 0)
        )
        prison.set_escape_probability(PRISONER, 100)
        ca.ability(PRISONER)[42] = 5
        ca.ability(WARDEN)[42] = 3
        self.assertEqual(
            prison_service.judge_can_escape(PRISONER), (True, 4.0, 3.0)
        )
        ca.ability(WARDEN)[42] = 5
        self.assertEqual(
            prison_service.judge_can_escape(PRISONER), (False, 4.0, 5.0)
        )

    def test_become_prisoner(self) -> None:
        """角色入狱后更新囚禁相关标志、写入逃脱概率 0 与当前位置宿舍，并按预期提升能力 14、17 与 18"""
        flags.set(PRISONER, be_bagged=True, escaping=True)
        prison_service.chara_become_prisoner(PRISONER)
        self.assertFalse(flags.get(PRISONER, "be_bagged"))
        self.assertTrue(flags.get(PRISONER, "imprisonment"))
        self.assertFalse(flags.get(PRISONER, "escaping"))
        self.assertTrue(prison.is_prisoner(PRISONER))
        self.assertEqual(prison.escape_probability(PRISONER), 0)
        self.assertEqual(
            chara_life.dormitory(PRISONER),
            map_handle.get_map_system_path_str_for_list(
                activity.position(PRISONER)
            ),
        )
        ability = ca.ability(PRISONER)
        self.assertEqual((ability[14], ability[17], ability[18]), (2, 1, 3))

    def imprison_in(self, cid: int, cell: str) -> None:
        """
        将指定角色登记为囚犯并把宿舍设为关押区内的目标牢房
        Keyword arguments:
        cid -- int，角色编号
        cell -- str，牢房名称
        Return arguments:
        None -- 直接写入囚犯记录与角色宿舍
        """
        prison.imprison(cid, game_time.now(), 0)
        chara_life.dormitory.set(
            cid, map_handle.get_map_system_path_str_for_list(["关押", cell])
        )

    def test_unused_prison_dormitory(self) -> None:
        """空闲牢房按牢1至牢8顺序返回首个未占用房间，八间均占用时返回空字符串"""
        self.assertEqual(prison_service.get_unused_prison_dormitory(), "牢1")
        self.imprison_in(PRISONER, "牢1")
        self.imprison_in(WARDEN, "牢3")
        self.assertEqual(prison_service.get_unused_prison_dormitory(), "牢2")
        for index in range(8):
            self.imprison_in(10 + index, f"牢{index + 1}")
        self.assertEqual(prison_service.get_unused_prison_dormitory(), "")

    def test_assistant_behavior_filters(self) -> None:
        """验证调教助手候选行为来自口、手、道具池且不含 pl 触发项，并正确套用部位筛选与禁用列表"""
        groups = game_config.config_behavior_id_list_of_group_sex_body_part
        pool = set(groups["口"]) | set(groups["手"]) | set(groups["道具"])
        with mock.patch.object(
            instruct_filter,
            "judge_single_instruct_filter",
            side_effect=lambda _id, data, *args, **kwargs: (True, data),
        ):
            found = (
                prison_service.get_all_can_use_behavior_id_for_sex_assistant()
            )
            selected = (
                prison_service.get_all_can_use_behavior_id_for_sex_assistant(
                    select_part="B"
                )
            )
            banned = selected[0]
            prison.toggle_assistant_ban_behavior(banned)
            narrowed = (
                prison_service.get_all_can_use_behavior_id_for_sex_assistant(
                    select_part="B"
                )
            )
            avoided = (
                prison_service.get_all_can_use_behavior_id_for_sex_assistant(
                    not_selet_part="B"
                )
            )
        self.assertTrue(found)
        self.assertLessEqual(set(found), pool)
        for behavior_id in found:
            self.assertNotEqual(
                game_config.config_behavior[behavior_id].trigger, "pl"
            )
        tags = {
            behavior_id: game_config.config_behavior[behavior_id].tag.split("|")
            for behavior_id in found
        }
        self.assertEqual(
            sorted(selected), sorted(b for b in found if "B" in tags[b])
        )
        self.assertEqual(sorted(narrowed), sorted(set(selected) - {banned}))
        self.assertEqual(
            sorted(avoided),
            sorted(b for b in found if "B" not in tags[b] and b != banned),
        )
        self.assertIn(banned, found)

    def test_assistant_behavior_choice(self) -> None:
        """验证调教助手在关闭、对象未囚禁、列表模式可用与监狱长受束缚四种情形下的行为选择结果"""
        work.set_warden(WARDEN)
        activity.set_target(0, PRISONER)
        self.assertEqual(prison_service.get_behavior_id_of_sex_assistant(), "0")
        prison.set_setting(12, 3)
        prison.toggle_assistant_behavior("act_a")
        self.assertEqual(prison_service.get_behavior_id_of_sex_assistant(), "0")
        flags.set(PRISONER, imprisonment=True)
        self.assertEqual(
            prison_service.get_behavior_id_of_sex_assistant(), "act_a"
        )
        h_state.set(WARDEN, bondage=1)
        self.assertEqual(prison_service.get_behavior_id_of_sex_assistant(), "0")
