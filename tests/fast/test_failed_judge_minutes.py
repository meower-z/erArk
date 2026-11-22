# -*- coding: UTF-8 -*-
"""
指令判定没过时只做失败的行为
============================
玩家选邀请H，行动开始时开始门（start_gate.gate）判定没过：换成邀请H失败，
内核时长与意图的名义分钟数都是邀请H失败的时长。
在爱情旅馆邀请H没过：开始时提示进入H模式失败，玩家与交互对象都没记下在爱情旅馆H。
"""

import json
from collections.abc import Mapping
from typing import cast

from Script.Config import game_config
from Script.Core import constant
from Script.Design import update
from Script.Kernel import core
from Script.Modules.domains import h_state
from Script.Modules.gameplay_resolution import (
    intent,
    player_starters,
    start_gate,
)
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
from tests import kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

LOADED_FIRST = (update, handle_instruct)
""" 先于 Script.Modules 导入的 update：Script.Modules 的包初始化要在 update 导入途中进行；
handle_instruct 登记指令处理函数 """
NPC = 1
""" 玩家的交互对象 """


class FailedJudgeMinutesTest(FastTestCase):
    """判定没过的指令的时长"""

    def setUp(self) -> None:
        """玩家与一个当交互对象的干员；内核状态由缓存投影"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        aim(self.player.cid, NPC)
        core.reset_state(kernel_data.reprojected(core.state()))

    def test_failed_judge_takes_failure_minutes(self) -> None:
        """邀请H没过：开始的是邀请H失败，内核时长与名义分钟数都是它的时长"""
        fail_minutes = game_config.config_behavior[
            constant.Behavior.DO_H_FAIL
        ].duration
        self.assertNotEqual(
            fail_minutes,
            game_config.config_behavior[constant.Behavior.H].duration,
        )
        with self.assertRaises(player_pick.Chosen) as chosen:
            constant.handle_instruct_data[constant.Instruct.DO_H]()
        result = start_gate.gate(chosen.exception.action)
        assert isinstance(result, tuple)
        gated = result[0]
        data = gated.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(
            (data["behavior_id"], data["minutes"], gated.duration),
            (constant.Behavior.DO_H_FAIL, fail_minutes, fail_minutes),
        )

    def test_failed_h_invite_warns_and_sets_no_place(self) -> None:
        """在爱情旅馆邀请H没过：开始时提示失败，两人都没记下在爱情旅馆H"""
        with self.assertRaises(player_pick.Chosen) as chosen:
            constant.handle_instruct_data[
                constant.Instruct.DO_H_IN_LOVE_HOTEL
            ]()
        result = start_gate.gate(chosen.exception.action)
        assert isinstance(result, tuple)
        gated = result[0]
        self.assertEqual(
            gated.action_id, intent.KIND_PREFIX + player_starters.KIND
        )
        data = json.loads(json.dumps(gated.action_data))
        self.world.wait_texts.clear()
        handle_instruct.start_instruct(0, cast(intent.Intent, data))
        self.assertEqual(
            (
                data["behavior_id"],
                any("进入H模式失败" in t for t in self.world.wait_texts),
                h_state.get(0, "h_in_love_hotel"),
                h_state.get(NPC, "h_in_love_hotel"),
            ),
            (constant.Behavior.DO_H_FAIL, True, False, False),
            "（开始的行为，提示了失败，玩家记下爱情旅馆，对方记下爱情旅馆）",
        )
