# -*- coding: UTF-8 -*-
"""
旁人目睹H时转为露出：邀请的结果排进博士的计划队列，不在发现的结算里另起一次结算
================================================================================
博士和对方（干员1）在H中，发现者（干员2）在场。博士点下「等待」（5 分钟）；等待开始时（结算途中）
给发现者排上发现的行动。被发现面板换成替身：选「转为露出」，露出模式面板直接选无人室内露出。
结算途中另起结算即抛 RuntimeError。每个角色的结算与状态结算换成只记录的替身：
- 邀请成功：博士做完等待后开始转为露出；
- 邀请失败：博士眼下的行为不变，发现者打断，博士做完等待后被打断，结束H；「结束H模式」只显示一次。
"""

from unittest import mock

from Script.Core import constant
from Script.Design import character_behavior, instuct_judege
from Script.Kernel import core
from Script.Modules.gameplay_resolution import hidden_sex_service
from Script.System.Sex_System import exhibitionism_sex_panel
from Script.UI.Panel import sex_be_discovered_panel
from Script.System.Instruct_System import handle_instruct
from tests.fast.base import FastTestCase
from tests.world import play
from tests.chara_activity import aim
from Script.Modules.domains import activity

PARTNER = 1
""" 和博士H的干员 """
FINDER = 2
""" 发现者 """


class DiscoveryExhibitionismPlansTest(FastTestCase):
    """被发现面板转为露出：邀请的结果都排进计划队列"""

    def run_discovery(
        self, invite_ok: bool
    ) -> tuple[list[tuple[str, int]], list[tuple[int, str, int]], list[str]]:
        """
        跑一次被发现后转为露出
        Keyword arguments:
        invite_ok -- 露出的邀请是否成功
        Return arguments:
        list -- 博士开始的行为与时钟
        list -- 干员开始的行为与时钟
        list -- 面板选完后博士眼下的行为
        """
        player = self.world.chara(0, "博士")
        self.world.chara(PARTNER, "对方")
        self.world.chara(FINDER, "发现者")
        aim(player.cid, PARTNER)
        player_starts: list[tuple[str, int]] = []
        settled: list[tuple[int, str, int]] = []
        after_panel: list[str] = []

        def loop() -> None:
            """博士行动开始时结算的替身：记下博士开始的行为；第一次时给发现者排上发现"""
            player_starts.append(
                (activity.behavior(player.cid).behavior_id, core.state().clock)
            )
            if len(player_starts) == 1:
                hidden_sex_service.plan_discovery(FINDER)

        def settle(character_id: int) -> int:
            """
            状态结算的替身：记下干员开始的行为与内核时钟
            Keyword arguments:
            character_id -- 角色id
            Return arguments:
            int -- 1
            """
            if character_id == 0:
                loop()
                return 1
            behavior = activity.behavior(character_id)
            settled.append(
                (character_id, behavior.behavior_id, core.state().clock)
            )
            return 1

        def choose_exhibitionism(
            panel: sex_be_discovered_panel.Sex_Be_Discovered_Panel,
        ) -> None:
            """
            被发现面板的替身：选「转为露出」，记下博士眼下的行为
            Keyword arguments:
            panel -- 面板
            """
            panel._continue_exhibitionism_sex()
            after_panel.append(activity.behavior(player.cid).behavior_id)

        def pick_mode(
            panel: exhibitionism_sex_panel.Select_Exhibitionism_Sex_Mode_Panel,
        ) -> None:
            """
            露出模式面板的替身：选无人室内露出
            Keyword arguments:
            panel -- 面板
            """
            panel.select_this_mode(1)

        with (
            mock.patch.object(
                character_behavior, "judge_character_status", settle
            ),
            mock.patch.object(
                instuct_judege,
                "calculation_instuct_judege",
                return_value=[1 if invite_ok else 0, 0],
            ),
            mock.patch.object(
                sex_be_discovered_panel.Sex_Be_Discovered_Panel,
                "draw",
                choose_exhibitionism,
            ),
            mock.patch.object(
                exhibitionism_sex_panel.Select_Exhibitionism_Sex_Mode_Panel,
                "draw",
                pick_mode,
            ),
        ):
            play(
                lambda: handle_instruct.handle_instruct(constant.Instruct.WAIT)
            )
        return player_starts, settled, after_panel

    def test_invite_ok(self) -> None:
        """邀请成功：博士做完等待后开始转为露出"""
        player_starts, _settled, after_panel = self.run_discovery(True)
        start = player_starts[0][1]
        self.assertEqual(after_panel, [constant.Behavior.WAIT])
        self.assertEqual(
            player_starts,
            [
                (constant.Behavior.WAIT, start),
                (
                    constant.Behavior.OTHER_SEX_BE_FOUND_TO_EXHIBITIONISM_SEX,
                    start + 5,
                ),
            ],
            "博士做完等待后转为露出",
        )

    def test_invite_failed(self) -> None:
        """邀请失败：博士眼下的行为不变，发现者打断，博士做完等待后被打断，提示只显示一次"""
        player_starts, settled, after_panel = self.run_discovery(False)
        start = player_starts[0][1]
        self.assertEqual(
            after_panel,
            [constant.Behavior.WAIT],
            "失败的邀请不改博士眼下的行为",
        )
        self.assertIn(
            (FINDER, constant.Behavior.SEE_H_AND_INTERRUPT, start + 1), settled
        )
        self.assertEqual(
            player_starts,
            [
                (constant.Behavior.WAIT, start),
                (constant.Behavior.H_INTERRUPT, start + 5),
            ],
            "博士做完等待后被打断，结束H",
        )
        end_texts = [t for t in self.world.wait_texts if "结束H模式" in t]
        self.assertEqual(len(end_texts), 1, "「结束H模式」只显示一次")
