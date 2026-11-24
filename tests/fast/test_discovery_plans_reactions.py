# -*- coding: UTF-8 -*-
"""
旁人目睹H：发现的行动打开面板，各方的后续行动排进计划队列
========================================================
博士和对方（干员1）在H中，发现者（干员2）在场。博士点下「等待」（5 分钟）；等待开始时（结算途中）
给发现者排上发现的行动。被发现面板换成替身：直接选「尴尬地结束H」，再结束一次H（应当什么也不做）。
状态结算换成只记录的替身，干员不自己选行动（没有可选的状态机，发呆不记），只看内核与计划队列：
- 发现者被打断，在博士的等待开始的同一分钟打开面板；他的打断反应在发现的 1 分钟之后开始；
- 对方被打断，在面板打开的同一分钟开始等待；
- 博士做完等待后被打断，结束H；「结束H模式」只显示一次。
"""

from unittest import mock

from Script.Core import constant
from Script.Design import character_behavior, handle_npc_ai
from Script.Kernel import core
from Script.Modules.gameplay_resolution import hidden_sex_service
from Script.System.Instruct_System import handle_instruct
from Script.System.Sex_System import sex_be_discovered_panel
from tests.fast.base import FastTestCase
from tests.world import play
from tests.chara_activity import aim
from Script.Modules.domains import activity

PARTNER = 1
""" 和博士H的干员 """
FINDER = 2
""" 发现者 """


class DiscoveryPlansReactionsTest(FastTestCase):
    """发现的行动打开面板；面板的选择把各方的后续行动排进计划队列"""

    def test_end_h_choice(self) -> None:
        """选「尴尬地结束H」：发现者打断，对方等待，博士被打断结束H，提示只显示一次"""
        player = self.world.chara(0, "博士")
        self.world.chara(PARTNER, "对方")
        self.world.chara(FINDER, "发现者")
        aim(player.cid, PARTNER)
        player_starts: list[tuple[str, int]] = []
        settled: list[tuple[int, str, int]] = []
        opened: list[int] = []

        def loop() -> None:
            """
            博士行动开始时结算的替身：记下博士开始的行为；第一次时给发现者排上发现
            Keyword arguments:
            无
            Return arguments:
            无
            """
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
            if behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
                return 1
            settled.append(
                (character_id, behavior.behavior_id, core.state().clock)
            )
            return 1

        def choose_end_h(
            panel: sex_be_discovered_panel.Sex_Be_Discovered_Panel,
        ) -> None:
            """
            被发现面板的替身：选「尴尬地结束H」，再结束一次H
            Keyword arguments:
            panel -- 面板
            Return arguments:
            无
            """
            opened.append(core.state().clock)
            panel._end_current_h()
            handle_instruct.plan_h_end()

        with (
            mock.patch.object(
                character_behavior, "judge_character_status", settle
            ),
            mock.patch.object(
                handle_npc_ai, "choose_state_machine", return_value=None
            ),
            mock.patch.object(
                sex_be_discovered_panel.Sex_Be_Discovered_Panel,
                "draw",
                choose_end_h,
            ),
        ):
            play(
                lambda: handle_instruct.handle_instruct(constant.Instruct.WAIT)
            )
        start = player_starts[0][1]
        self.assertEqual(opened, [start], "发现者被打断，马上打开面板")
        self.assertEqual(
            sorted(settled),
            [
                (PARTNER, constant.Behavior.WAIT, start),
                (FINDER, constant.Behavior.SEE_H_AND_INTERRUPT, start + 1),
                (FINDER, constant.Behavior.WAIT, start),
            ],
            "对方马上开始等待，发现者发现（1 分钟的等待）之后打断",
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
