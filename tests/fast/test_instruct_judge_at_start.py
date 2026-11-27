# -*- coding: UTF-8 -*-
"""
玩家指令的判定在行动开始时结算
==============================
玩家选指令时只判不扣；行动开始时开始门（start_gate.gate）再判一次，靠催眠补正通过的这时扣理智，
没过的换成失败的行为。
- 交互对象在催眠中（unconscious_h 为 4）。她有被深层催眠素质、玩家有中级催眠素质时，戴上项圈、邀请群交靠催眠补正通过；
  她有被浅层催眠素质时，挂上避孕套装饰（严重骚扰）靠催眠补正通过。行动开始后玩家的理智少了。
- 邀请群交时场景里两名干员都只靠催眠补正通过，玩家的理智只够一人的代价：开始时逐个判定一次，
  第二人理智不足没过，开始的是邀请群交失败，提示她拒绝了。
- 群交模板编辑里邀请一名只靠催眠补正通过的干员：理智够时她被邀请、理智少了；理智不够时她不被邀请。
"""

import json
from collections.abc import Mapping
from dataclasses import replace
from typing import cast
from unittest import mock

from Script.Core import constant, get_text
from Script.Design import handle_premise, instuct_judege, update
from Script.Kernel import core
from Script.Modules.gameplay_resolution import (
    intent,
    player_starters,
    start_gate,
)
from Script.Modules.npc_action_choice import choice
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
from Script.UI.Panel import group_sex_panel
from Script.UI.Panel import condom_panel
from tests.fast.base import FastTestCase
from tests import chara_abilities as ca, kernel_data
from tests.chara_activity import aim
from Script.Modules.domains import action_info, flags
from Script.Modules.domains import relations
from Script.Modules.domains import identity

LOADED_FIRST = update
""" 先于 Script.Modules 导入的 update：Script.Modules 的包初始化要在 update 导入途中进行 """
NPC = 1
""" 玩家的交互对象 """
OTHER_NPC = 2
""" 同一场景里的另一名干员 """
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
        aim(self.player.cid, NPC)
        kernel_data.set_needs(self.player.cid, sanity=SANITY, sanity_max=SANITY)
        kernel_data.put(flags.set, self.npc.cid, unconscious_h=IN_HYPNOSIS)
        core.reset_state(kernel_data.reprojected(core.state()))

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
        行动过开始门，再跑种类 Instruct 的开始代码。这两步写的 GameState 数据随后套用到内核状态上
        Keyword arguments:
        act -- 定下的行动
        Return arguments:
        Action -- 开始门交给内层的行动
        """
        with kernel_data.writing():
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
        kept = {t: ca.talent(self.npc)[t] for t in talents}
        for t in talents:
            ca.talent(self.npc)[t] = 0
        without = instuct_judege.calculation_instuct_judege(
            0, NPC, judge, not_draw_flag=True, settle_hypnosis=False
        )[0]
        ca.talent(self.npc).update(kept)
        with_hypnosis = instuct_judege.calculation_instuct_judege(
            0, NPC, judge, not_draw_flag=True, settle_hypnosis=False
        )[0]
        self.assertEqual((without, with_hypnosis), (0, 1))
        self.assertEqual(
            kernel_data.needs_of(self.player.cid)["sanity"], SANITY
        )

    def deep_hypnosis(self) -> None:
        """玩家有中级催眠，交互对象被深层催眠"""
        ca.talent(self.player)[PL_INTERMEDIATE_HYPNOSIS] = 1
        ca.talent(self.npc)[BEEN_DEEP_HYPNOSIS] = 1

    def test_necklace_pays_hypnosis_at_start(self) -> None:
        """戴上项圈靠催眠补正通过：选择时理智不变，开始后少了，行为是戴上项圈"""
        self.deep_hypnosis()
        kernel_data.put(relations.trust.set, self.npc.cid, 200)
        self.passes_by_hypnosis_only(_("戴上项圈"))
        act = self.pick(constant.Instruct.GIVE_NECKLACE)
        self.assertEqual(
            kernel_data.needs_of(self.player.cid)["sanity"], SANITY
        )
        gated = self.start(act)
        data = gated.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["behavior_id"], constant.Behavior.GIVE_NECKLACE)
        self.assertLess(kernel_data.needs_of(self.player.cid)["sanity"], SANITY)

    def test_group_sex_pays_hypnosis_at_start(self) -> None:
        """邀请群交靠催眠补正通过：开始后理智少了，行为是邀请群交"""
        self.deep_hypnosis()
        self.passes_by_hypnosis_only(_("群交"))
        act = self.pick(constant.Instruct.ASK_GROUP_SEX)
        self.assertEqual(
            kernel_data.needs_of(self.player.cid)["sanity"], SANITY
        )
        gated = self.start(act)
        data = gated.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["behavior_id"], constant.Behavior.ASK_GROUP_SEX)
        self.assertLess(kernel_data.needs_of(self.player.cid)["sanity"], SANITY)

    def test_condom_decoration_pays_hypnosis_at_start(self) -> None:
        """挂上避孕套装饰靠催眠补正通过严重骚扰判定：开始后理智少了"""
        ca.talent(self.npc)[BEEN_PRIMARY_HYPNOSIS] = 1
        self.passes_by_hypnosis_only(_("严重骚扰"))
        with mock.patch.object(
            condom_panel.Condom_Select_Panel,
            "draw",
            return_value={"op": "hang", "part": [0, 0], "condom": []},
        ):
            act = self.pick(constant.Instruct.HANG_CONDOM_DECORATION)
        self.assertEqual(
            kernel_data.needs_of(self.player.cid)["sanity"], SANITY
        )
        gated = self.start(act)
        data = gated.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(
            data["behavior_id"], constant.Behavior.HANG_CONDOM_DECORATION
        )
        self.assertLess(kernel_data.needs_of(self.player.cid)["sanity"], SANITY)

    def invite_from_editor(self) -> None:
        """
        在群交模板编辑里邀请交互对象：小世界的干员没穿衣服（服装异常），状态检查记为正常，
        她到玩家处的路程记为 0 分钟。邀请写的 GameState 数据随后套用到内核状态上
        """
        editor = group_sex_panel.Edit_Group_Sex_Temple_Panel(100)
        with (
            mock.patch.object(choice, "route_minutes", return_value=0),
            mock.patch.object(
                handle_premise, "handle_normal_24567", return_value=1
            ),
            kernel_data.writing(),
        ):
            editor.invite_npc(NPC)

    def test_editor_invite_pays_hypnosis(self) -> None:
        """模板编辑里邀请一名只靠催眠补正通过的干员：她被邀请，理智扣了一人的代价"""
        self.deep_hypnosis()
        self.passes_by_hypnosis_only(_("群交"))
        self.invite_from_editor()
        self.assertTrue(flags.get(self.npc.cid, "go_to_join_group_sex"))
        self.assertLess(kernel_data.needs_of(self.player.cid)["sanity"], SANITY)

    def test_editor_invite_refused_without_sanity(self) -> None:
        """理智不够催眠的代价：模板编辑里邀请她，她不被邀请"""
        self.deep_hypnosis()
        self.passes_by_hypnosis_only(_("群交"))
        kernel_data.set_needs(self.player.cid, sanity=0)
        self.invite_from_editor()
        self.assertFalse(flags.get(self.npc.cid, "go_to_join_group_sex"))

    def test_group_sex_judged_once_against_remaining_sanity(self) -> None:
        """两名干员都靠催眠补正通过，理智只够一人：开始的是邀请群交失败，恰好一人拒绝，理智扣完一人的代价"""
        self.deep_hypnosis()
        self.passes_by_hypnosis_only(_("群交"))
        other = self.world.chara(OTHER_NPC, "干员2")
        kernel_data.put(flags.set, other.cid, unconscious_h=IN_HYPNOSIS)
        ca.talent(other)[BEEN_DEEP_HYPNOSIS] = 1
        core.reset_state(kernel_data.reprojected(core.state()))
        with kernel_data.writing():
            instuct_judege.calculation_instuct_judege(
                0, NPC, _("群交"), not_draw_flag=True
            )
        one_member_cost = (
            SANITY - kernel_data.needs_of(self.player.cid)["sanity"]
        )
        self.assertGreater(one_member_cost, 0)
        kernel_data.set_needs(self.player.cid, sanity=one_member_cost)
        act = self.pick(constant.Instruct.ASK_GROUP_SEX)
        picked = cast(Mapping[str, core.JSON], act.action_data)
        staged = {"who": None, "key": "base.power_strategy", "old": None}
        act = replace(act, action_data={**picked, "effects": (staged,)})
        self.world.wait_texts.clear()
        gated = self.start(act)
        data = gated.action_data
        assert isinstance(data, Mapping)
        refused = action_info.get(
            self.player.cid, "ask_group_sex_refuse_chara_id_list"
        )
        self.assertEqual(
            (
                data["behavior_id"],
                len(refused),
                kernel_data.needs_of(self.player.cid)["sanity"],
            ),
            (constant.Behavior.ASK_GROUP_SEX_FAIL, 1, 0),
            "（开始的行为，拒绝的人数，剩下的理智）",
        )
        self.assertNotIn("effects", data, "失败的行为不带选择时的写入")
        name = identity.of(refused[0]).name
        self.assertTrue(
            any(f"{name}拒绝了群交" in t for t in self.world.wait_texts),
            "提示了拒绝的人",
        )
