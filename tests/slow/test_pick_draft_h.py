# -*- coding: UTF-8 -*-
"""
H 类与公务的选择只读：选择期间缓存不变，选定的东西在行动开始时才生效
====================================================================
- 邀请隐奸：判定过了，行动开始后双方在所选的隐奸模式里；没过（判定在行动开始时跑一次），开始的是邀请隐奸失败，
  双方都不在隐奸模式里，画出「邀请隐奸失败」。邀请露出判定过了，行动开始后双方在露出模式里。打开选择隐奸模式的面板直接返回：没有行动。
- 邀请群交：选择时不问玩家，开始的是邀请群交。群交编辑面板里邀请一名不在场的干员：一个 0 分钟的 Edit，
  之后她被邀请，玩家再等 1 分钟时她开始前往。
- 切换催眠类型：一个 0 分钟的 Edit，之后玩家的催眠类型已换；换过之后取消整个选择：没有行动，类型不变。
- 处理公务：队列里有两条公务事件时只弹出第一条；选项的结算在行动开始时跑一次，第一条记进履历，第二条留在队列里。
- 停止睡眠猥亵：一个 0 分钟的 Edit，之后交互对象不在睡眠猥亵模式里。
"""

from collections.abc import Callable, Mapping
from typing import cast

from tests import kernel_data
from tests.slow.base import SlowTestCase
from tests import chara_abilities as ca
from tests.chara_activity import aim
from tests.kernel_project import activity


class PickDraftHTest(SlowTestCase):
    """H 类与公务的选择只读"""

    def setUp(self) -> None:
        """开新游戏，记下内核开始的每个行动"""
        super().setUp()
        from Script.Kernel import core

        self.started: list[core.Action] = []
        saved = core._bodies["kernel.StartAction"]

        def spy(act: core.Action) -> core.Effects:
            self.started.append(act)
            return saved(act)

        core._bodies["kernel.StartAction"] = spy
        self.addCleanup(core._bodies.__setitem__, "kernel.StartAction", saved)

    def run_pick(self, fn: "Callable[[], None]") -> tuple[int, int, bool]:
        """
        玩家这一次选择跑 fn；记下选择期间（fn 结束或抛出之前）缓存的指纹是否变了
        Return arguments:
        tuple -- (选择前的分钟, 推进到玩家下一次选行动时的分钟, 选择期间指纹变了)
        """
        from Script.Kernel import core
        from tests import pick_guard, world

        changed: list[bool] = []

        def pick() -> None:
            before = pick_guard.fingerprint()
            try:
                fn()
            finally:
                changed.append(pick_guard.fingerprint() != before)

        clock = core.state().clock
        self.started.clear()
        world.act(pick)
        self.world.player.check_done()
        return clock, core.state().clock, changed[0]

    def player_starts(self) -> list[str]:
        """这次选择以来玩家开始的行动：行为id，没有行为id的为 action_id"""
        result = []
        for act in self.started:
            if act.who != "0":
                continue
            data = act.action_data
            if isinstance(data, Mapping) and "behavior_id" in data:
                result.append(str(data["behavior_id"]))
            else:
                result.append(act.action_id)
        return result

    def target_here(self) -> int:
        """把第一名干员移到玩家所在的场景并设为交互对象，交回她的角色id"""
        target = min(c for c in kernel_data.domain("roster").active() if c)
        self.world.move(target, activity.position(0))
        aim(0, target)
        return target

    def panel(self, panel_id: int) -> "Callable[[], None]":
        """
        选择时打开面板 panel_id（与主循环的一轮相同）
        Return arguments:
        Callable -- 交给 run_pick 的操作
        """
        from Script.UI.Moudle import view
        from Script.Core import constant

        def show() -> None:
            view.now_panel_id = panel_id
            constant.panel_data[panel_id]()

        return show

    def screen(self) -> str:
        """最近画出的文字"""
        return "".join(self.world.player.screen)

    def watch_judge(
        self, name: str, refuse: bool = False
    ) -> list[tuple[bool, bool]]:
        """
        包住实行值判定 calculation_instuct_judege，记下判定 name 的每次调用
        Keyword arguments:
        name -- 判定名，如 隐奸
        refuse -- 为真时这个判定一律不过
        Return arguments:
        list -- 每次调用的 (是否在玩家选择期间, 是否结算催眠的代价)
        """
        from Script.Design import instuct_judege
        from Script.Modules.tk_ui import player_pick

        calls: list[tuple[bool, bool]] = []
        real = instuct_judege.calculation_instuct_judege

        def watched(
            character_id: int,
            target_character_id: int,
            instruct_name: str,
            not_draw_flag: bool = False,
            settle_hypnosis: bool = True,
        ) -> list[float]:
            if instruct_name == name:
                calls.append((player_pick.in_pick(), settle_hypnosis))
                if refuse:
                    return [0, 0, 0.0]
            return real(
                character_id,
                target_character_id,
                instruct_name,
                not_draw_flag=not_draw_flag,
                settle_hypnosis=settle_hypnosis,
            )

        instuct_judege.calculation_instuct_judege = watched
        self.addCleanup(
            setattr, instuct_judege, "calculation_instuct_judege", real
        )
        return calls

    def test_hidden_sex_passes_mode_set_at_start(self) -> None:
        """debug 模式下邀请隐奸（不隐藏）：选择期间缓存不变，开始的是邀请隐奸，之后双方在模式 1 里"""
        from Script.Core import constant

        self.cache.debug_mode = True
        target = self.target_here()
        calls = self.watch_judge("隐奸")
        self.world.player.press("[1]不隐藏")
        _, _, changed = self.run_pick(self.panel(constant.Panel.ASK_HIDDEN_SEX))
        self.assertFalse(changed, "选择期间写了缓存")
        self.assertEqual(
            self.player_starts(), [constant.Behavior.ASK_HIDDEN_SEX]
        )
        self.assertEqual([c for c in calls if c[1]], [(False, True)])
        self.assertEqual(
            kernel_data.domain("flags").get(0, "hidden_sex_mode"), 1
        )
        self.assertEqual(
            kernel_data.domain("flags").get(target, "hidden_sex_mode"), 1
        )

    def test_hidden_sex_fails_runs_fail_behaviour(self) -> None:
        """
        邀请隐奸的判定没过：结算代价的判定只在行动开始时跑一次（选择时只有不结算的询问），开始的是邀请隐奸失败，
        双方都不在隐奸模式里，画出「邀请隐奸失败」
        """
        from Script.Core import constant

        target = self.target_here()
        calls = self.watch_judge("隐奸", refuse=True)
        self.world.player.press("[1]不隐藏")
        _, _, changed = self.run_pick(self.panel(constant.Panel.ASK_HIDDEN_SEX))
        self.assertFalse(changed, "选择期间写了缓存")
        self.assertEqual(
            self.player_starts(), [constant.Behavior.ASK_HIDDEN_SEX_FAIL]
        )
        self.assertEqual(
            [c for c in calls if c[1]],
            [(False, True)],
            "结算的判定不是只在开始时跑一次",
        )
        self.assertEqual(
            kernel_data.domain("flags").get(0, "hidden_sex_mode"), 0
        )
        self.assertEqual(
            kernel_data.domain("flags").get(target, "hidden_sex_mode"), 0
        )
        self.assertIn("邀请隐奸失败", self.screen())

    def test_hidden_sex_panel_back_commits_nothing(self) -> None:
        """打开选择隐奸模式的面板直接返回：没有行动，缓存不变"""
        from Script.Core import constant

        self.target_here()
        self.world.player.press("返回")
        start, end, changed = self.run_pick(
            self.panel(constant.Panel.ASK_HIDDEN_SEX)
        )
        self.assertEqual(self.player_starts(), [])
        self.assertEqual(end, start)
        self.assertFalse(changed)

    def test_exhibitionism_passes_mode_set_at_start(self) -> None:
        """debug 模式下邀请露出（模式 1）：选择期间缓存不变，开始的是邀请露出，之后双方在模式 1 里"""
        from Script.Core import constant

        self.cache.debug_mode = True
        target = self.target_here()
        calls = self.watch_judge("露出")
        self.world.player.press("[1]无人室内露出")
        _, _, changed = self.run_pick(
            self.panel(constant.Panel.ASK_EXHIBITIONISM_SEX)
        )
        self.assertFalse(changed, "选择期间写了缓存")
        self.assertEqual(
            self.player_starts(), [constant.Behavior.ASK_EXHIBITIONISM_SEX]
        )
        self.assertEqual([c for c in calls if c[1]], [(False, True)])
        self.assertEqual(
            kernel_data.domain("flags").get(0, "exhibitionism_sex_mode"), 1
        )
        self.assertEqual(
            kernel_data.domain("flags").get(target, "exhibitionism_sex_mode"), 1
        )

    def test_group_sex_invite_asks_nothing(self) -> None:
        """邀请群交：选择时不问玩家（没有安排输入），选择期间缓存不变，开始的是邀请群交"""
        from Script.Core import constant
        from Script.System.Instruct_System import handle_instruct

        self.cache.debug_mode = True
        self.target_here()
        calls = self.watch_judge("群交")
        _, _, changed = self.run_pick(
            lambda: handle_instruct.handle_instruct(
                constant.Instruct.ASK_GROUP_SEX
            )
        )
        self.assertFalse(changed, "选择期间写了缓存")
        self.assertEqual(
            self.player_starts(), [constant.Behavior.ASK_GROUP_SEX]
        )
        self.assertTrue(calls, "开始时没有判定群交")
        self.assertEqual([c for c in calls if c[0]], [], "选择时判定了群交")

    def test_group_sex_editor_invite_rides_edit(self) -> None:
        """
        群交编辑面板里邀请一名不在场的干员再退出：一个 0 分钟的 Edit，时钟不动，之后她被邀请；
        名单的判定不结算代价，邀请她的那次判定结算一次；
        玩家再等 1 分钟，她开始的第一个行动是前往玩家所在的地点
        """
        from Script.Core import constant
        from Script.Modules.gameplay_resolution import edits
        from Script.Modules.tk_ui import player_pick
        from tests import world

        self.cache.debug_mode = True
        here = self.world.scene(activity.position(0)).character_list
        guest = min(
            c
            for c in kernel_data.domain("roster").active()
            if c and c not in here
        )
        guest_data = self.cache.character_data[guest]
        calls = self.watch_judge("群交")
        self.world.player.press("▶邀请", guest_data.name, "返回", "返回")
        start, end, changed = self.run_pick(
            self.panel(constant.Panel.EDIT_GROUP_SEX_TEMPLE)
        )
        self.assertFalse(changed, "选择期间写了缓存")
        self.assertEqual(self.player_starts(), [edits.EDIT])
        self.assertEqual(end, start)
        self.assertTrue(calls, "邀请名单没有判定群交")
        self.assertEqual(
            len([c for c in calls if c[1]]),
            1,
            "名单只判不扣，邀请她时结算一次代价（随 Edit 生效）",
        )
        self.assertTrue(
            kernel_data.domain("flags").get(guest, "go_to_join_group_sex")
        )
        self.started.clear()
        world.act(lambda: player_pick.choose(constant.Behavior.WAIT, 1))
        guest_starts = [
            cast(Mapping, a.action_data)["behavior_id"]
            for a in self.started
            if a.who == str(guest)
        ]
        self.assertEqual(guest_starts[:1], [constant.Behavior.MOVE])

    def test_hypnosis_type_rides_edit_and_back_keeps_nothing(self) -> None:
        """切换催眠类型：一个 0 分钟的 Edit，之后类型已换；换过之后取消整个选择：没有行动，类型不变"""
        from Script.Config import game_config
        from Script.Core import constant
        from Script.Modules.gameplay_resolution import edits
        from Script.Modules.tk_ui import player_pick

        aim(0, 0)
        cid = min(c for c in game_config.config_hypnosis_type if c > 0)
        type_data = game_config.config_hypnosis_type[cid]
        ca.talent(0)[type_data.talent_id] = 1
        kernel_data.put(
            kernel_data.domain("player_ability").set, 0, hypnosis_type=0
        )
        show = self.panel(constant.Panel.CHANGE_HYPNOSIS_MODE)

        def change_then_back() -> None:
            with player_pick.drafting("test"):
                show()
                player_pick.back()

        self.world.player.press(f"[{type_data.name}]")
        start, end, changed = self.run_pick(change_then_back)
        self.assertEqual(self.player_starts(), [])
        self.assertEqual(
            kernel_data.domain("player_ability").get(0, "hypnosis_type"), 0
        )
        self.world.player.press(f"[{type_data.name}]")
        start, end, changed = self.run_pick(show)
        self.assertFalse(changed, "选择期间写了缓存")
        self.assertEqual(self.player_starts(), [edits.EDIT])
        self.assertEqual(end, start)
        self.assertEqual(
            kernel_data.domain("player_ability").get(0, "hypnosis_type"), cid
        )

    def test_official_work_settles_one_event_at_start(self) -> None:
        """两条公务事件排队：弹出第一条，选项结算在开始时跑一次，第一条记进履历，第二条留在队列里"""
        from Script.Config import game_config
        from Script.Core import constant
        from Script.Modules.domains import official
        from Script.Modules.tk_ui import player_pick
        from Script.System.Instruct_System import handle_instruct
        from Script.System.Official_Event_System import official_event_handle
        from tests import kernel_data

        for uid in ("测试公务甲", "测试公务乙"):
            game_config.config_official_event[uid] = {
                "department": 0,
                "text": uid,
                "option_1": uid + "选项一",
                "option_1_effect": uid + "结算一",
                "option_2": uid + "选项二",
                "option_2_effect": uid + "结算二",
            }
            self.addCleanup(game_config.config_official_event.pop, uid)
            self.assertTrue(
                kernel_data.written(
                    official_event_handle.push_official_event,
                    uid,
                    ignore_capacity=True,
                )
            )
        effects: list[tuple[str, bool]] = []
        saved = official_event_handle.handle_effect_text

        def spy(
            effect_text: str, character_id: int = 0, partner_id: int = 0
        ) -> None:
            effects.append((effect_text, player_pick.in_pick()))

        official_event_handle.handle_effect_text = spy
        self.addCleanup(
            setattr, official_event_handle, "handle_effect_text", saved
        )
        self.world.player.press("测试公务甲选项二")
        _, _, changed = self.run_pick(
            lambda: handle_instruct.handle_instruct(
                constant.Instruct.OFFICIAL_WORK
            )
        )
        self.assertFalse(changed, "选择期间写了缓存")
        self.assertEqual(
            self.player_starts(), [constant.Behavior.OFFICIAL_WORK]
        )
        self.assertEqual(effects, [("测试公务甲结算二", False)])
        history = official.history()
        self.assertEqual(history["测试公务甲"]["choice"], 2)
        self.assertNotIn("测试公务乙", history)
        self.assertEqual(
            [one["uid"] for one in official.queue()],
            ["测试公务乙"],
        )
        self.assertNotIn("测试公务乙选项一", self.screen())

    def test_stop_sleep_obscenity_commits_edit(self) -> None:
        """停止睡眠猥亵：一个 0 分钟的 Edit，时钟不动，之后交互对象不在睡眠猥亵模式里"""
        from Script.Core import constant
        from Script.Modules.gameplay_resolution import edits
        from Script.System.Instruct_System import handle_instruct

        target = self.target_here()
        kernel_data.put(
            kernel_data.domain("flags").set, target, unconscious_h=1
        )
        start, end, changed = self.run_pick(
            lambda: handle_instruct.handle_instruct(
                constant.Instruct.STOP_SLEEP_OBSCENITY
            )
        )
        self.assertFalse(changed, "选择期间写了缓存")
        self.assertEqual(self.player_starts(), [edits.EDIT])
        self.assertEqual(end, start)
        self.assertEqual(
            kernel_data.domain("flags").get(target, "unconscious_h"), 0
        )
