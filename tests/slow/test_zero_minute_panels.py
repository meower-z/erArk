# -*- coding: UTF-8 -*-
"""
看一眼就走的面板什么也不留下，改游戏状态里的设置才是 0 分钟的 Edit
==================================================================
- add_panel 登记的每个面板（player_pick.UNDRAFTED、标题与建角色面板、OPENED_BY_SETTLEMENT 之外）各打开一次，
  每次等输入时按屏幕上的「返回」（没有时按「退出」「离开」「取消」「关闭」），直到面板退出：
  内核没有开始玩家的行动，缓存的指纹（tests.pick_guard.fingerprint）不变。新游戏与用户存档 99 各走一遍
  （存档 99 不入库，装在 save/99 时才跑，没装时报跳过）。打开时写缓存的面板（旧存档的修补、显示前的重算）
  会让看一眼也定下一个 0 分钟的 Edit，这里把它们都找出来。
- 新游戏里文本生成AI的设置还是空的，且属于全局设置（不是游戏状态）。在设置面板里改一项不触发内核行动。改完后每项 AI
  设置都有值（没改的是默认值）。干员个人设置改一项则是一个 0 分钟的 Edit。
"""

import importlib
import os
import pickle
from collections.abc import Callable
from typing import TYPE_CHECKING
from unittest import mock

from tests.slow.base import SlowTestCase
from tests import kernel_data

if TYPE_CHECKING:
    from Script.Kernel import core

USER_SAVE_ID = "99"
""" 用户存档的存档id（不入库，装在 save/99） """
EXIT_LABELS = ("返回", "退出", "离开", "取消", "关闭")
""" 离开面板时按的按钮文字，按这个顺序找第一个在屏幕上的 """
PRESS_LIMIT = 12
""" 一个面板里最多按几次离开的按钮 """
OPENED_BY_SETTLEMENT = {
    "EJACULATION": "射精部位的选择：在结算高潮时画出，只能选一个部位离开",
    "EVENT_OPTION": "事件选项：在结算事件时画出，要有待选的事件",
}
""" 不从选择里打开的面板（面板名：原因） """


class CannotLeave(AssertionError):
    """面板按了 PRESS_LIMIT 次离开的按钮仍没有退出，或屏幕上没有离开的按钮"""


class ZeroMinutePanelsTest(SlowTestCase):
    """打开每个面板再离开：没有行动，缓存不变"""

    time_limit = 1200
    maxDiff = None

    def setUp(self) -> None:
        """开新游戏，记下内核开始的每个行动"""
        super().setUp()
        self.constant = importlib.import_module("Script.Core.constant")
        self.core = importlib.import_module("Script.Kernel.core")
        self.player_pick = importlib.import_module(
            "Script.Modules.tk_ui.player_pick"
        )
        self.edits = importlib.import_module(
            "Script.Modules.gameplay_resolution.edits"
        )
        self.pick_guard = importlib.import_module("tests.pick_guard")
        self.tests_world = importlib.import_module("tests.world")
        self.started: list[core.Action] = []
        saved = self.core._bodies["kernel.StartAction"]

        def spy(act: "core.Action") -> "core.Effects":
            self.started.append(act)
            return saved(act)

        self.core._bodies["kernel.StartAction"] = spy
        self.addCleanup(
            self.core._bodies.__setitem__, "kernel.StartAction", saved
        )

    def player_starts(self) -> list[tuple[str, int]]:
        """上次清空以来玩家开始的行动：(action_id, 分钟数)"""
        return [(a.action_id, a.duration) for a in self.started if a.who == "0"]

    def leave_on_every_wait(self) -> Callable[[], None]:
        """
        换掉读输入的函数：没有安排的输入时按屏幕上离开的按钮
        Return arguments:
        Callable -- 把按过的次数清零的函数（每个面板打开前调用）
        """
        flow_handle = importlib.import_module("Script.Core.flow_handle")
        player = self.world.player
        real = flow_handle.order_deal
        presses = [0]

        def order_deal(
            flag: str = "order",
            print_order: bool = True,
            donot_return_null_str: bool = True,
        ) -> str | None:
            if not player.planned and donot_return_null_str:
                shown = [text for text, _ in player.buttons]
                label = next(
                    (
                        want
                        for want in EXIT_LABELS
                        if any(want in text for text in shown)
                    ),
                    None,
                )
                presses[0] += 1
                if label is None or presses[0] > PRESS_LIMIT:
                    raise CannotLeave(f"屏幕上的按钮：{shown}")
                player.press(label)
            return real(flag, print_order, donot_return_null_str)

        patch = mock.patch.object(flow_handle, "order_deal", order_deal)
        patch.start()
        self.addCleanup(patch.stop)

        def reset() -> None:
            presses[0] = 0

        return reset

    def parts(self) -> dict[str, bytes]:
        """序列化缓存中除顶层界面状态与全局设置外的全部顶层属性"""
        out: dict[str, bytes] = {}
        for name, value in vars(self.cache).items():
            out[name] = pickle.dumps(value)
        return out

    def sweep(self) -> tuple[int, dict[str, str]]:
        """
        每个面板打开再离开
        Return arguments:
        tuple -- (打开的面板数, {面板名: 定下的行动与变了的缓存属性，或出的错})
        """
        from Script.UI.Moudle import view

        names = {
            value: name
            for name, value in vars(self.constant.Panel).items()
            if isinstance(value, int)
        }
        panels = sorted(
            panel
            for panel in set(self.constant.panel_data)
            - self.player_pick.UNDRAFTED
            - set(self.player_pick.PRE_GAME_PANELS)
            if names.get(panel) not in OPENED_BY_SETTLEMENT
        )
        reset = self.leave_on_every_wait()
        self.tests_world.act(lambda: None)
        problems: dict[str, str] = {}
        for panel in panels:
            name = names.get(panel, str(panel))
            view.now_panel_id = panel
            reset()
            self.world.player.planned.clear()
            before = self.pick_guard.fingerprint()
            parts = self.parts()
            self.started.clear()
            try:
                self.tests_world.act(self.constant.panel_data[panel])
            except Exception as error:
                problems[name] = f"{type(error).__name__}：{error}"[:300]
                view.now_panel_id = self.constant.Panel.IN_SCENE
                self.tests_world.act(lambda: None)
                continue
            after = self.pick_guard.fingerprint()
            if self.player_starts() or after != before:
                now = self.parts()
                moved = sorted(
                    key
                    for key in parts.keys() | now.keys()
                    if parts.get(key) != now.get(key)
                )
                extra = [
                    label
                    for label, i in (("内核", 1), ("随机数", 2), ("打断", 3))
                    if before[i] != after[i]
                ]
                problems[name] = (
                    f"行动 {self.player_starts()}，变了 {moved + extra}"
                )
            view.now_panel_id = self.constant.Panel.IN_SCENE
        return len(panels), problems

    def test_new_game_open_and_leave(self) -> None:
        """新游戏里每个面板打开再离开：玩家没有开始行动，缓存的指纹不变"""
        count, problems = self.sweep()
        self.assertEqual(problems, {}, f"打开了 {count} 个面板")

    def test_save_99_open_and_leave(self) -> None:
        """存档 99 里每个面板打开再离开：玩家没有开始行动，缓存的指纹不变"""
        from Script.UI.Moudle import view

        save_handle = importlib.import_module("Script.Core.save_handle")
        if not os.path.isdir(os.path.join("save", USER_SAVE_ID)):
            self.skipTest("用户存档 99 没装在 save/99")
        save_handle.input_load_save(USER_SAVE_ID)
        view.now_panel_id = self.constant.Panel.IN_SCENE
        count, problems = self.sweep()
        self.assertEqual(problems, {}, f"打开了 {count} 个面板")

    def run_edit(
        self, origin: str, fn: Callable[[], None], edit: bool = True
    ) -> None:
        """
        在 origin 对应的玩家选择草稿里执行 fn，并断言内核时钟不变。edit 为 True 时断言定下一个 0 分钟 Edit，为
        False 时断言没有开始任何玩家行动。
        Keyword arguments:
        origin -- 草稿来源标识
        fn -- 在草稿上下文中执行的函数
        edit -- 是否预期定下一个 0 分钟 Edit（默认为 True）
        """
        clock = self.core.state().clock

        def pick() -> None:
            with self.player_pick.drafting(origin):
                fn()

        self.started.clear()
        self.tests_world.act(pick)
        expected = [(self.edits.EDIT, 0)] if edit else []
        self.assertEqual(self.player_starts(), expected)
        self.assertEqual(self.core.state().clock, clock)

    def test_setting_edits_commit_one_edit(self) -> None:
        """
        新游戏里改一项文本生成 AI 设置不触发内核行动。改完后每项 AI 设置都有值（2 号与 7 号均为 1）。
        改一项干员个人设置会定下一个 0 分钟 Edit 并更新该设置。
        """
        from Script.Modules.domains import chara_profile

        game_config = importlib.import_module("Script.Config.game_config")
        normal_config = importlib.import_module("Script.Config.normal_config")
        chat_ai = importlib.import_module("Script.UI.Panel.chat_ai_setting")
        chara = importlib.import_module("Script.UI.Panel.character_setting")
        self.tests_world.act(lambda: None)
        self.assertEqual(normal_config.ai_setting.ai_chat_setting, {})
        options = game_config.config_ai_chat_setting_option[2]
        self.run_edit(
            "chat ai",
            lambda: chat_ai.Chat_Ai_Setting_Panel(120).change_setting(
                2, len(options)
            ),
            edit=False,
        )
        settings = normal_config.ai_setting.ai_chat_setting
        self.assertEqual(set(settings), set(game_config.config_ai_chat_setting))
        self.assertEqual(settings[2], 1)
        self.assertEqual(settings[7], 1)

        cid = sorted(kernel_data.domain("roster").active())[0]
        setting = sorted(game_config.config_chara_setting)[0]
        before = chara_profile.chara_setting(cid).get(setting, 0)
        self.run_edit(
            "chara setting",
            lambda: chara.CharacterSetting(cid, 120, 1).change_setting(
                setting, len(game_config.config_chara_setting_option[setting])
            ),
        )
        self.assertNotEqual(chara_profile.chara_setting(cid)[setting], before)
