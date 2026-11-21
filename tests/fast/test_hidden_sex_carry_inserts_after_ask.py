# -*- coding: UTF-8 -*-
"""
携带模式的隐奸：邀请之后接着插入
================================
玩家在隐奸模式面板选携带模式（模式5）、插入阴道且邀请通过：定下的行动是邀请隐奸；
这个行动开始时，玩家的计划队列里排上对面抱位的阴道插入，邀请结束后接着做。
测试把选插入部位的面板换成选阴道，把实行值判定换成通过。
"""

import json
from collections.abc import Mapping
from typing import cast
from unittest import mock

from Script.Config import game_config
from Script.Core import constant
from Script.Design import instuct_judege, update
from Script.Kernel import core
from Script.Modules.gameplay_resolution import intent, plan_queue
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
from Script.System.Sex_System import hidden_sex_panel
from tests import kernel_data
from tests.fast.base import FastTestCase

LOADED_FIRST = update
""" 先于 Script.Modules 导入的 update：Script.Modules 的包初始化要在 update 导入途中进行 """
NPC = 1
""" 玩家的交互对象 """
CARRY = 5
""" 携带模式 """
VAGINA = 1
""" 插入部位：阴道 """
FACING_CARRY_POSITION = 9
""" 对面抱位 """


class HiddenSexCarryInsertsAfterAskTest(FastTestCase):
    """携带模式邀请隐奸之后的插入"""

    def setUp(self) -> None:
        """玩家与当交互对象的干员"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        self.player.target_character_id = NPC
        core.reset_state(kernel_data.reprojected(core.state()))

    def test_carry_insert_queued_when_ask_starts(self) -> None:
        """邀请隐奸开始时排上阴道插入"""
        panel = hidden_sex_panel.Select_Hidden_Sex_Mode_Panel(80)
        with (
            mock.patch.object(
                panel, "select_carry_insert_part", return_value=VAGINA
            ),
            mock.patch.object(
                instuct_judege,
                "calculation_instuct_judege",
                return_value=[1, 1, 1.0],
            ),
            kernel_data.writing(),
            self.assertRaises(player_pick.Chosen) as chosen,
        ):
            panel.select_this_mode(CARRY)
        data = chosen.exception.action.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["behavior_id"], constant.Behavior.ASK_HIDDEN_SEX)
        insert = game_config.config_sex_position_data[
            FACING_CARRY_POSITION
        ].vaginal_sex_behavior_id
        kernel_data.written(
            handle_instruct.start_instruct,
            0,
            cast(intent.Intent, json.loads(json.dumps(data))),
        )
        self.assertTrue(plan_queue.plan_has(0, insert))
