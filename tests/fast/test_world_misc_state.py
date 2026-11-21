# -*- coding: UTF-8 -*-
"""
世界设定、周目、国家、模式、吵醒名单、成就、事件与指令记录与计划队列
================================================================
- 本周目设定与周目数随 kernel_state 编解码完整往返，读取的键是整数。
- 玩家选行动时写入模式开关，选择期间 core.state() 不变，行动开始时落盘。
- 重置到空状态后写回周目数加一、成就、难度与生殖方式设定，模式开关、计划队列与路线保持清空。
- 旧存档导入（adopt_old_save）：版本 11 齐备字段全部迁入并从缓存字典删掉，版本 12 空字典不改写已有状态且计数为 0，
  版本 0 缺项与错类型按默认补齐并计数。
- 成就的各项写入助手与 view() 隔离，修改 view() 不改 GameState。
- 计划队列经 plan.queue 保存，queue_head 只读答出队首，pop 弹出并清掉空队列条目。
- 路线始终读成新列表且修改不影响状态，country.fill 补齐配置并把影响系数夹在 0.1 到 3.0。
- 事件与指令记录的滑动窗口（至多 10 条）与每日清空相互独立。
- 事件触发函数读取传入的 GameState，排进计划队列后触发条件立即不成立。
"""

from typing import Any
from unittest import mock

from Script.Config import game_config
from Script.Core import constant, game_type
from Script.Design import attr_calculation
from Script.Kernel import core
from Script.Modules.domains import (
    achievement,
    country,
    history,
    modes,
    needs,
    plan,
    playthrough,
)
from Script.Modules.gameplay_resolution import plan_queue, working
from Script.Modules.save_load import kernel_state, upgrade
from Script.Modules.tk_ui import player_pick
from Script.UI.Moudle import draw
from tests import kernel_data
from tests.fast.base import FastTestCase


class WorldMiscStateTest(FastTestCase):
    """全局杂项状态在 GameState 里的读写、旧存档导入与编解码"""

    def setUp(self) -> None:
        """建玩家与一名成年干员"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")

    def test_settings_and_round_round_trip(self) -> None:
        """四张设定表与周目数随 kernel_state 编解码后键值与整数键不变"""
        with kernel_data.writing():
            playthrough.set_setting(playthrough.DIFFICULTY, 1, 3)
            playthrough.set_setting(playthrough.BIRTH_TYPE, 2, 1)
            playthrough.set_setting(playthrough.FIRST_BONUS, 5, True)
            playthrough.set_setting(playthrough.WORLD, 7, 2)
            playthrough.set_game_round(4)
        encoded = kernel_state.encode(core.state(), "tok")
        self.assertEqual(encoded["version"], upgrade.CURRENT)
        decoded = kernel_state.decode(encoded, tagged=True)
        self.assertEqual(
            playthrough.settings(playthrough.DIFFICULTY, decoded)[1], 3
        )
        self.assertEqual(
            playthrough.settings(playthrough.BIRTH_TYPE, decoded)[2], 1
        )
        self.assertIs(
            playthrough.settings(playthrough.FIRST_BONUS, decoded)[5], True
        )
        self.assertEqual(playthrough.settings(playthrough.WORLD, decoded)[7], 2)
        self.assertEqual(playthrough.game_round(decoded), 4)

    def test_pick_writes_mode_ride_chosen_action(self) -> None:
        """选行动时打开模式开关，选择期间内核状态不变，行动开始时一并落盘"""
        from tests.world import act

        kernel_data.set_needs(0, sanity_max=100, sanity=100)
        seen_in_pick: list[tuple[bool, bool]] = []

        def choose() -> None:
            with player_pick.drafting("pick_mode"):
                modes.set_time_stop(True)
                seen_in_pick.append(
                    (
                        modes.time_stop(),
                        bool(working.get(None, modes.TIME_STOP, core.state())),
                    )
                )
                player_pick.choose(constant.Behavior.WAIT, 5)

        act(choose)
        self.assertEqual(seen_in_pick, [(True, False)])
        self.assertTrue(modes.time_stop())

    def test_new_round_carries_round_and_achievement(self) -> None:
        """重置到空状态后，继承写回周目数+1、成就与设定，模式与计划队列保持清空"""
        with kernel_data.writing():
            playthrough.set_game_round(3)
            playthrough.set_setting(playthrough.DIFFICULTY, 1, 2)
            playthrough.set_setting(playthrough.BIRTH_TYPE, 2, 1)
            achievement.add("field_commission_count", 7)
            modes.set_time_stop(True)
            plan.set_route([["中枢", "走廊"], ["中枢", "会议室"]])
        prev = core.state()
        carried_round = playthrough.game_round(prev)
        carried_ach = achievement.stored(prev)
        carried_diff = playthrough.settings(playthrough.DIFFICULTY, prev)
        carried_birth = playthrough.settings(playthrough.BIRTH_TYPE, prev)
        kernel_state.reset_clock(prev.clock)
        with kernel_data.writing():
            playthrough.set_game_round(carried_round + 1)
            playthrough.set_settings(playthrough.DIFFICULTY, carried_diff)
            playthrough.set_settings(playthrough.BIRTH_TYPE, carried_birth)
            achievement.restore(carried_ach)
        self.assertEqual(playthrough.game_round(), 4)
        self.assertEqual(achievement.get("field_commission_count"), 7)
        self.assertEqual(playthrough.setting(playthrough.DIFFICULTY, 1), 2)
        self.assertEqual(playthrough.setting(playthrough.BIRTH_TYPE, 2), 1)
        self.assertFalse(modes.time_stop())
        self.assertEqual(plan.queues(), {})
        self.assertIsNone(plan.route())

    def test_adopt_old_save_present_mistyped_missing_and_v12(self) -> None:
        """旧存档导入：版本 11 齐备值迁入并弹出，版本 12 空字典不改写已有状态，版本 0 缺项与错类型补齐并计数"""

        class Quiet:
            """不画的绘制对象"""

            def __init__(self) -> None:
                self.style = ""
                self.text = ""

            def draw(self) -> None:
                pass

        old_country = game_type.Country()
        old_country.nation_reputation = {1: 50}
        old_country.country_infection_rate = {1: 30}
        old_country.country_infection_patient_ratio = {1: 1.0}
        old_country.last_week_all_country_infection_rate = 12.5
        old_ach = game_type.ACHIEVEMENT()
        old_ach.field_commission_count = 9
        loaded: dict[str, Any] = {
            "difficulty_setting": attr_calculation.get_difficulty_setting_zero(),
            "birth_type_setting": attr_calculation.get_birth_type_setting_zero(),
            "first_bonus": {1: True},
            "world_setting": {2: 1},
            "game_round": 5,
            "country": old_country,
            "time_stop_mode": True,
            "group_sex_mode": False,
            "sex_class_mode": False,
            "noise_woken": {1: 0},
            "achievement": old_ach,
            "taiggered_event_record": {"ev_b", "ev_a"},
            "today_taiggered_event_record": {"ev_a"},
            "pl_pre_behavior_instruce": ["wait"],
            "daily_intsruce": ["line1"],
            "plan_queue": {
                1: [("Behavior", {"behavior_id": "wait", "minutes": 5})]
            },
            "player_route": (["中枢", "走廊"], ["中枢", "会议室"]),
            "pl_sleep_save_flag": True,
        }
        with (
            mock.patch.object(draw, "NormalDraw", Quiet),
            kernel_data.writing(),
        ):
            total = 0
            total += playthrough.adopt_old_save(loaded, 11)
            total += country.adopt_old_save(loaded, 11)
            total += modes.adopt_old_save(loaded, 11)
            total += needs.adopt_old_save(loaded, 11)
            total += achievement.adopt_old_save(loaded, 11)
            total += history.adopt_old_save(loaded, 11)
            total += plan.adopt_old_save(loaded, 11)
        self.assertEqual(total, 0)
        self.assertEqual(loaded, {})
        self.assertEqual(playthrough.game_round(), 5)
        self.assertEqual(country.reputation(1), 50)
        self.assertEqual(country.last_week_rate(), 12.5)
        self.assertTrue(modes.time_stop())
        self.assertEqual(needs.noise_woken(), {1: 0})
        self.assertEqual(achievement.get("field_commission_count"), 9)
        self.assertEqual(history.triggered_ids(), {"ev_a", "ev_b"})
        self.assertEqual(history.today_ids(), {"ev_a"})
        self.assertEqual(history.recent(), ["wait"])
        self.assertEqual(history.daily(), "line1")
        self.assertEqual(plan.route(), [["中枢", "走廊"], ["中枢", "会议室"]])
        self.assertTrue(plan.sleep_save())

        # 版本 12 缓存里没有这 18 个字段：不改写已有状态，计数为 0
        v12_loaded: dict[str, Any] = {}
        with (
            mock.patch.object(draw, "NormalDraw", Quiet),
            kernel_data.writing(),
        ):
            v12_count = (
                playthrough.adopt_old_save(v12_loaded, 12)
                + country.adopt_old_save(v12_loaded, 12)
                + modes.adopt_old_save(v12_loaded, 12)
                + needs.adopt_old_save(v12_loaded, 12)
                + achievement.adopt_old_save(v12_loaded, 12)
                + history.adopt_old_save(v12_loaded, 12)
                + plan.adopt_old_save(v12_loaded, 12)
            )
        self.assertEqual(v12_count, 0)
        self.assertEqual(playthrough.game_round(), 5)
        self.assertTrue(modes.time_stop())

        # 旧存档（版本 0）缺项与错类型：按默认补齐并计数
        broken: dict[str, Any] = {
            "country": "bad",
            "time_stop_mode": 123,
            "plan_queue": "not_a_dict",
        }
        with (
            mock.patch.object(draw, "NormalDraw", Quiet),
            kernel_data.writing(),
        ):
            c_country = country.adopt_old_save(broken, 0)
            c_modes = modes.adopt_old_save(broken, 0)
            c_needs = needs.adopt_old_save(broken, 0)
            c_plan = plan.adopt_old_save(broken, 0)
        self.assertEqual(c_country, 1)
        self.assertEqual(c_modes, 3)
        self.assertEqual(c_needs, 1)
        self.assertEqual(c_plan, 3)
        self.assertFalse(modes.time_stop())
        self.assertEqual(plan.queues(), {})

    def test_achievement_helpers_and_view_isolation(self) -> None:
        """成就助手写入各类字段，改 view() 返回的对象不影响 GameState"""
        with kernel_data.writing():
            achievement.add("field_commission_count", 3)
            achievement.set_entry("achievement_dict", 10, True)
            achievement.add_entry("sleep_sex_record", 2, 4)
            achievement.add_entry("sleep_sex_record", 2, 1)
            achievement.append("visited_nation_list", 3)
            achievement.append_entry("group_sex_record", 1, 2)
            achievement.append_entry("group_sex_record", 1, 2)
        self.assertTrue(achievement.done(10))
        self.assertEqual(achievement.get("field_commission_count"), 3)
        self.assertEqual(achievement.get("sleep_sex_record")[2], 5)
        self.assertEqual(achievement.get("visited_nation_list"), [3])
        self.assertEqual(achievement.get("group_sex_record")[1], [2])
        shown = achievement.view()
        shown.field_commission_count = 999
        shown.achievement_dict[10] = False
        self.assertEqual(achievement.get("field_commission_count"), 3)
        self.assertTrue(achievement.done(10))

    def test_plan_queue_head_and_pop(self) -> None:
        """plan_queue 排入 plan.queue，queue_head 只读答出队首，pop 弹出并清掉空项"""
        kernel_data.written(plan_queue.plan_next, 1, constant.Behavior.WAIT, 15)
        self.assertEqual(len(plan.queue(1)), 1)
        intercepted = plan_queue.queue_head("1")
        self.assertIsInstance(intercepted, core.Intercept)
        assert isinstance(intercepted, core.Intercept)
        self.assertEqual(intercepted.value.duration, 15)
        self.assertEqual(len(plan.queue(1)), 1)
        popped = kernel_data.written(plan_queue.pop, 1)
        self.assertEqual(popped["behavior_id"], constant.Behavior.WAIT)
        self.assertEqual(plan.queues(), {})

    def test_route_stays_list_and_country_fill_clamps(self) -> None:
        """路线读出为可改新列表且修改不影响状态，country.fill 补全并把系数夹在 0.1 到 3.0"""
        kernel_data.set_world(
            plan.set_route, (["中枢", "走廊"], ["中枢", "会议室"], 0, False)
        )
        got = plan.route()
        self.assertIsInstance(got, list)
        assert got is not None
        got[0].append("修改")
        self.assertEqual(
            plan.route(), [["中枢", "走廊"], ["中枢", "会议室"], 0, False]
        )
        kernel_data.written(country.fill)
        for nation_id in game_config.config_nation:
            self.assertEqual(country.reputation(nation_id), 0)
        for cid in game_config.config_birthplace:
            ratio = country.patient_ratio(cid)
            self.assertGreaterEqual(ratio, 0.1)
            self.assertLessEqual(ratio, 3.0)

    def test_history_window_and_event_records(self) -> None:
        """最近行为至多留 10 条且每日记录追加，今日事件清空不影响累计事件"""
        with kernel_data.writing():
            for i in range(12):
                history.note_instruction(f"t{i};", f"b{i}")
            history.trigger("e1")
            history.trigger_today("e1")
            history.trigger_today("e2")
        self.assertEqual(history.recent(), [f"b{i}" for i in range(2, 12)])
        self.assertEqual(history.daily(), "".join(f"t{i};" for i in range(12)))
        self.assertEqual(history.today_count(), 2)
        with kernel_data.writing():
            history.clear_today()
            history.clear_daily()
        self.assertTrue(history.triggered("e1"))
        self.assertFalse(history.triggered_today("e1"))
        self.assertEqual(history.today_count(), 0)
        self.assertEqual(history.daily(), "")
        self.assertEqual(len(history.recent()), 10)

    def test_event_trigger_reads_post_effect_plan_queue(self) -> None:
        """事件触发函数读传入的 GameState：排进 plan.queue 后触发条件立即不成立"""
        from Script.Modules.gameplay_resolution import events

        kernel_data.set_needs(0, hit_max=100, hit=1)
        kernel_data.set_world(modes.set_group_sex, True)
        before = core.state()
        self.assertTrue(events._player_spent(before))
        with working.based_on(before) as buf:
            plan_queue.plan_next(0, constant.Behavior.GROUP_SEX_END, 1)
            after = core.preview(before, buf.effects())
        self.assertTrue(events._player_spent(before))
        self.assertFalse(events._player_spent(after))
