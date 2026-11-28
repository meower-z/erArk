# -*- coding: UTF-8 -*-
"""
旁人目睹H时转为露出：邀请结果排进博士计划队列，不在发现结算内嵌套结算
=====================================================================
博士和对方（干员1）在H中，发现者（干员2）在场。博士点下「等待」（5 分钟），等待开始时（结算途中）
给发现者排上发现行动。测试将 modal_hooks._ask 换为直接选「转为露出」的替身，
露出模式面板替身直接选无人室内露出，并包装 hidden_sex_discovered.resolve 记录返回时博士行为。
结算途中另起结算即抛 RuntimeError。状态结算换成只记录的替身：
- 邀请成功：博士做完等待后开始转为露出。
- 邀请失败：博士眼下行为不变，发现者打断，博士做完等待后被打断结束H，「结束H模式」只显示一次。
"""

from unittest import mock

from Script.Core import constant
from Script.Design import character_behavior, instuct_judege
from Script.Kernel import core
from Script.Modules.gameplay_resolution import hidden_sex_discovered
from Script.Modules.gameplay_resolution import hidden_sex_service, modal_hooks
from Script.Protocol.modal_prompts import ChoicePrompt, ChoiceResult
from Script.UI.Panel import exhibitionism_sex_panel
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
    """发现选择转为露出时，邀请结果均排进计划队列。"""

    def run_discovery(
        self, invite_ok: bool
    ) -> tuple[list[tuple[str, int]], list[tuple[int, str, int]], list[str]]:
        """
        跑一次被发现后选择转为露出的流程。
        Keyword arguments:
        invite_ok -- bool，露出的邀请是否成功
        Return arguments:
        list[tuple[str, int]] -- 博士开始的行为与时钟
        list[tuple[int, str, int]] -- 干员开始的行为与时钟
        list[str] -- resolve 返回后博士眼下的行为
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

        real_resolve = hidden_sex_discovered.resolve

        def resolve(discoverer_id: int, from_hidden_sex_flag: bool) -> None:
            """
            包装 hidden_sex_discovered.resolve，在其返回后记录博士当前的行为编号。
            Keyword arguments:
            discoverer_id -- int，发现者的角色编号
            from_hidden_sex_flag -- bool，是否由隐奸被发现触发
            Return arguments:
            None -- 无返回值
            """
            real_resolve(discoverer_id, from_hidden_sex_flag)
            after_panel.append(activity.behavior(player.cid).behavior_id)

        def choose_exhibitionism(prompt: ChoicePrompt) -> ChoiceResult:
            """
            返回选项标识为 "3" 的 ChoiceResult，模拟选择转为露出。
            Keyword arguments:
            prompt -- ChoicePrompt，本次收到的选项提示
            Return arguments:
            ChoiceResult -- 选中 "3" 的选择结果
            """
            return ChoiceResult(prompt.prompt_id, "3")

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
            mock.patch.object(hidden_sex_discovered, "resolve", resolve),
            mock.patch.object(modal_hooks, "_ask", choose_exhibitionism),
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
