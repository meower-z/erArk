# -*- coding: UTF-8 -*-
"""
身体检查只记下真正做了的检查
============================
每项检查是一个行动，选完面板就关上，下一项要再打开面板。这次体检里已做过的检查记在游戏数据里，
选择时的写入随行动的草稿在行动开始时写进去：
- 检查头发：开始后，再打开面板它是「已检查」。
- 测试头发（要判定初级骚扰）选择时在询问里点了返回：没有行动，它不算检查过。
- 测试头发判定没过，开始的是失败的行为：它也不算检查过。
- 再打开面板：已进行 1 次，只有检查头发是「已检查」；返回结束体检后，今日体检记录里只有检查头发。
"""

import importlib
from unittest import mock

from tests.slow.base import SlowTestCase
from tests import kernel_data
from tests.chara_activity import aim
from tests.kernel_project import activity

HAIR = "examine_hair"
""" 检查头发 """
HAIR_TEST = "examine_hair_smoothness"
""" 测试头发：要先检查头发，要判定初级骚扰 """


class PhysicalCheckRecordsPerformedTest(SlowTestCase):
    """身体检查面板记下的检查"""

    def setUp(self) -> None:
        """开新游戏，玩家以同一场景里的一名干员为交互对象"""
        super().setUp()
        self.npc_id: int = sorted(
            i for i in kernel_data.domain("roster").active() if i
        )[0]
        self.world.move(self.npc_id, activity.position(0))
        aim(0, self.npc_id)

    def label(self, behavior_id: str) -> str:
        """
        检查列表里这项检查按钮的文字片段
        Keyword arguments:
        behavior_id -- 行为id
        Return arguments:
        str -- 「：」加行为名
        """
        from Script.Config import game_config

        return "：" + game_config.config_behavior[behavior_id].name

    def visit(self, *presses: str) -> None:
        """
        玩家这一次选行动：打开身体检查与管理面板，依次按下按钮
        Keyword arguments:
        presses -- 按钮文字片段
        """
        from Script.UI.Moudle import view
        from Script.Core import constant
        from tests import world

        panel_id = constant.Panel.PHYSICAL_CHECK_AND_MANAGE
        self.world.player.press(*presses)

        def pick() -> None:
            view.now_panel_id = panel_id
            constant.panel_data[panel_id]()

        world.act(pick)
        self.world.player.check_done()

    def test_only_performed_checks_are_recorded(self) -> None:
        """取消的与判定没过的测试不算检查过，结束体检时不进今日记录"""
        from Script.Design import instuct_judege

        self.visit("[001]", self.label(HAIR))
        with mock.patch.object(instuct_judege, "ask_judge", return_value=False):
            self.visit("[001]", self.label(HAIR_TEST))
        with (
            mock.patch.object(instuct_judege, "ask_judge", return_value=True),
            mock.patch.object(
                instuct_judege,
                "calculation_instuct_judege",
                return_value=[0, 0, 0],
            ),
        ):
            self.visit("[001]", self.label(HAIR_TEST))
        self.world.player.screen.clear()
        self.visit("[001]", "返回", "返回")
        screen = "".join(self.world.player.screen)
        self.assertEqual(
            (
                self.label(HAIR) + "(已检查)" in screen,
                self.label(HAIR_TEST) + "(已检查)" in screen,
                "已进行的/共可进行的检查次数：1/" in screen,
            ),
            (True, False, True),
            "（检查头发已检查，测试头发已检查，已进行 1 次）",
        )
        exam = importlib.import_module("Script.Modules.domains.physical_exam")
        self.assertEqual(
            exam.checks(exam.TODAY).get(self.npc_id), {HAIR}, "今日体检记录"
        )
