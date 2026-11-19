# -*- coding: UTF-8 -*-
"""
玩家指令的判定在行动开始时结算
==============================
玩家选指令时只判不扣；行动开始时开始门（start_gate.gate）再判一次，靠催眠补正通过的这时扣理智，
没过的换成失败的行为。
- 交互对象在催眠中（unconscious_h 为 4）。她有被深层催眠素质、玩家有中级催眠素质时，戴上项圈、邀请群交靠催眠补正通过；
  她有被浅层催眠素质时，挂上避孕套装饰（严重骚扰）靠催眠补正通过。行动开始后玩家的理智少了。
"""

import json
from collections.abc import Mapping
from typing import cast
from unittest import mock

from Script.Core import constant, get_text
from Script.Design import instuct_judege, update
from Script.Kernel import core
from Script.Modules.gameplay_resolution import (
    actions,
    intent,
    player_starters,
    start_gate,
)
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
from Script.System.Item_System import condom_panel
from tests.fast.base import FastTestCase

LOADED_FIRST = update
""" 先于 Script.Modules 导入的 update：Script.Modules 的包初始化要在 update 导入途中进行 """
NPC = 1
""" 玩家的交互对象 """
PL_INTERMEDIATE_HYPNOSIS = 332
""" 中级催眠素质 """
BEEN_PRIMARY_HYPNOSIS = 71
""" 被浅层催眠素质 """
BEEN_DEEP_HYPNOSIS = 72
""" 被深层催眠素质 """
IN_HYPNOSIS = 4
""" unconscious_h 的催眠中 """
SANITY = 1000
""" 玩家开始时的理智 """
_ = get_text._


class InstructJudgeAtStartTest(FastTestCase):
    """指令的判定与它的代价在行动开始时"""

    def setUp(self) -> None:
        """玩家与一个当交互对象的干员；内核状态由缓存投影"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.npc = self.world.chara(NPC, "干员")
        self.player.target_character_id = NPC
        self.player.sanity_point = SANITY
        self.player.sanity_point_max = SANITY
        self.npc.sp_flag.unconscious_h = IN_HYPNOSIS
        core.reset_state(actions.state_from_cache())

    def pick(self, instruct_id: str) -> core.Action:
        """
        跑一个指令处理函数，交回它定下的行动
        Keyword arguments:
        instruct_id -- 指令id
        Return arguments:
        Action -- 定下的行动
        """
        with self.assertRaises(player_pick.Chosen) as chosen:
            constant.handle_instruct_data[instruct_id]()
        return chosen.exception.action

    def start(self, act: core.Action) -> core.Action:
        """
        行动过开始门，再跑种类 Instruct 的开始代码
        Keyword arguments:
        act -- 定下的行动
        Return arguments:
        Action -- 开始门交给内层的行动
        """
        result = start_gate.gate(act)
        assert isinstance(result, tuple)
        gated = result[0]
        if gated.action_id == intent.KIND_PREFIX + player_starters.KIND:
            data = json.loads(json.dumps(gated.action_data))
            handle_instruct.start_instruct(0, cast(intent.Intent, data))
        return gated

    def passes_by_hypnosis_only(self, judge: str) -> None:
        """
        前提：判定只靠催眠补正通过（去掉交互对象的被催眠素质就不过），只判时理智不变
        Keyword arguments:
        judge -- 判定名
        """
        talents = (BEEN_PRIMARY_HYPNOSIS, BEEN_DEEP_HYPNOSIS)
        kept = {t: self.npc.talent[t] for t in talents}
        for t in talents:
            self.npc.talent[t] = 0
        without = instuct_judege.calculation_instuct_judege(
            0, NPC, judge, not_draw_flag=True, settle_hypnosis=False
        )[0]
        self.npc.talent.update(kept)
        with_hypnosis = instuct_judege.calculation_instuct_judege(
            0, NPC, judge, not_draw_flag=True, settle_hypnosis=False
        )[0]
        self.assertEqual((without, with_hypnosis), (0, 1))
        self.assertEqual(self.player.sanity_point, SANITY)

    def deep_hypnosis(self) -> None:
        """玩家有中级催眠，交互对象被深层催眠"""
        self.player.talent[PL_INTERMEDIATE_HYPNOSIS] = 1
        self.npc.talent[BEEN_DEEP_HYPNOSIS] = 1

    def test_necklace_pays_hypnosis_at_start(self) -> None:
        """戴上项圈靠催眠补正通过：选择时理智不变，开始后少了，行为是戴上项圈"""
        self.deep_hypnosis()
        self.npc.trust = 200
        self.passes_by_hypnosis_only(_("戴上项圈"))
        act = self.pick(constant.Instruct.GIVE_NECKLACE)
        self.assertEqual(self.player.sanity_point, SANITY)
        gated = self.start(act)
        data = gated.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["behavior_id"], constant.Behavior.GIVE_NECKLACE)
        self.assertLess(self.player.sanity_point, SANITY)

    def test_group_sex_pays_hypnosis_at_start(self) -> None:
        """邀请群交靠催眠补正通过：开始后理智少了，行为是邀请群交"""
        self.deep_hypnosis()
        self.passes_by_hypnosis_only(_("群交"))
        act = self.pick(constant.Instruct.ASK_GROUP_SEX)
        self.assertEqual(self.player.sanity_point, SANITY)
        gated = self.start(act)
        data = gated.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["behavior_id"], constant.Behavior.ASK_GROUP_SEX)
        self.assertLess(self.player.sanity_point, SANITY)

    def test_condom_decoration_pays_hypnosis_at_start(self) -> None:
        """挂上避孕套装饰靠催眠补正通过严重骚扰判定：开始后理智少了"""
        self.npc.talent[BEEN_PRIMARY_HYPNOSIS] = 1
        self.passes_by_hypnosis_only(_("严重骚扰"))
        with mock.patch.object(
            condom_panel.Condom_Select_Panel,
            "draw",
            return_value={"op": "hang", "part": [0, 0], "condom": []},
        ):
            act = self.pick(constant.Instruct.HANG_CONDOM_DECORATION)
        self.assertEqual(self.player.sanity_point, SANITY)
        gated = self.start(act)
        data = gated.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(
            data["behavior_id"], constant.Behavior.HANG_CONDOM_DECORATION
        )
        self.assertLess(self.player.sanity_point, SANITY)
