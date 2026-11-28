# -*- coding: UTF-8 -*-
"""
旁人目睹H：发现行动发起选择结算，各方的后续行动排进计划队列
===========================================================
博士和对方（干员1）在H中，发现者（干员2）在场。博士点下「等待」（5 分钟），等待开始时（结算途中）
给发现者排上发现行动。测试将 modal_hooks._ask 换为直接选「尴尬地结束H」的替身，
并包装 hidden_sex_discovered.resolve 在结算后再调用一次 plan_h_end（应当什么也不做）。
状态结算换成只记录的替身，干员不自己选行动（没有可选的状态机，发呆不记），只看内核与计划队列：
- 发现者被打断，在博士等待开始的同一分钟触发选择提问，其打断反应在发现的 1 分钟之后开始。
- 对方被打断，在选择提问发生的同一分钟开始等待。
- 博士做完等待后被打断并结束H，「结束H模式」只显示一次。
"""

from unittest import mock

from Script.Core import constant
from Script.Design import character_behavior, handle_npc_ai
from Script.Kernel import core
from Script.Modules.gameplay_resolution import hidden_sex_discovered
from Script.Modules.gameplay_resolution import hidden_sex_service, modal_hooks
from Script.Protocol.modal_prompts import ChoicePrompt, ChoiceResult
from Script.System.Instruct_System import handle_instruct
from tests.fast.base import FastTestCase
from tests.world import play
from tests.chara_activity import aim
from Script.Modules.domains import activity

PARTNER = 1
""" 和博士H的干员 """
FINDER = 2
""" 发现者 """


class DiscoveryPlansReactionsTest(FastTestCase):
    """发现行动经选择提示结算，并将各方的后续行动排进计划队列。"""

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

        real_resolve = hidden_sex_discovered.resolve

        def resolve(discoverer_id: int, from_hidden_sex_flag: bool) -> None:
            """
            包装 hidden_sex_discovered.resolve，结算完成后再调用一次 handle_instruct.plan_h_end。
            Keyword arguments:
            discoverer_id -- int，发现者的角色编号
            from_hidden_sex_flag -- bool，是否由隐奸被发现触发
            Return arguments:
            None -- 无返回值
            """
            real_resolve(discoverer_id, from_hidden_sex_flag)
            handle_instruct.plan_h_end()

        def choose_end_h(prompt: ChoicePrompt) -> ChoiceResult:
            """
            记录发起选择提问时的内核时钟，并返回选项标识为 "5" 的 ChoiceResult。
            Keyword arguments:
            prompt -- ChoicePrompt，本次收到的选项提示
            Return arguments:
            ChoiceResult -- 选中 "5" 的选择结果
            """
            opened.append(core.state().clock)
            return ChoiceResult(prompt.prompt_id, "5")

        with (
            mock.patch.object(
                character_behavior, "judge_character_status", settle
            ),
            mock.patch.object(
                handle_npc_ai, "choose_state_machine", return_value=None
            ),
            mock.patch.object(hidden_sex_discovered, "resolve", resolve),
            mock.patch.object(modal_hooks, "_ask", choose_end_h),
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
