# -*- coding: UTF-8 -*-
"""
指令判定没过时按失败的行为计时
==============================
玩家选邀请H，行动开始时开始门（start_gate.gate）判定没过：换成邀请H失败，
内核时长与意图的名义分钟数都是邀请H失败的时长。
"""

from collections.abc import Mapping

from Script.Config import game_config
from Script.Core import constant
from Script.Design import update
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, start_gate
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
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
        self.player.target_character_id = NPC
        core.reset_state(actions.state_from_cache())

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
