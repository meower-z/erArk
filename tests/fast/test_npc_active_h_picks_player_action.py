# -*- coding: UTF-8 -*-
"""
逆推中「继续享受」「交给对方」定下玩家的行动
==========================================
H中玩家选「继续享受」或「交给对方」时，交互对象替玩家选一个性爱行为：它是玩家这次选的 10 分钟的行动，
不排进计划队列。
测试把指令可用的筛选换成都可用，小世界里的角色才有行为可选。
"""

from collections.abc import Mapping
from unittest import mock

from Script.Config import game_config
from Script.Core import constant
from Script.Design import update
from Script.Kernel import core
from Script.Modules.domains import h_state
from Script.Modules.gameplay_resolution import plan_queue
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct, see_instruct_panel
from tests import kernel_data
from tests.chara_activity import aim
from Script.Modules.domains import flags
from tests.fast.base import FastTestCase

LOADED_FIRST = (update, handle_instruct)
""" 先于 Script.Modules 导入的 update：Script.Modules 的包初始化要在 update 导入途中进行；
handle_instruct 登记指令处理函数 """
NPC = 1
""" 玩家的交互对象 """


class NpcActiveHPicksPlayerActionTest(FastTestCase):
    """交互对象替玩家选的H行为"""

    def setUp(self) -> None:
        """H中的玩家与当交互对象的干员；指令筛选都可用"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.npc = self.world.chara(NPC, "干员")
        aim(self.player.cid, NPC)
        kernel_data.put(flags.set, self.player.cid, is_h=True)
        kernel_data.put(flags.set, self.npc.cid, is_h=True)
        core.reset_state(kernel_data.reprojected(core.state()))
        patch = mock.patch.object(
            see_instruct_panel,
            "judge_single_instruct_filter",
            side_effect=lambda instruct_id, data, *a, **kw: (True, data),
        )
        patch.start()
        self.addCleanup(patch.stop)

    def pick(self, instruct_id: str) -> core.Action:
        """
        跑指令处理函数：要定下玩家的行动，不排计划队列
        Keyword arguments:
        instruct_id -- 指令id
        Return arguments:
        Action -- 定下的行动
        """
        with (
            self.assertRaises(player_pick.Chosen) as chosen,
            player_pick.picking(),
            player_pick.drafting(instruct_id),
        ):
            constant.handle_instruct_data[instruct_id]()
        act = chosen.exception.action
        self.assertEqual((act.who, act.duration), ("0", 10))
        data = act.action_data
        assert isinstance(data, Mapping)
        tags = game_config.config_behavior[str(data["behavior_id"])].tag
        self.assertIn("性爱", tags.split("|"))
        self.assertFalse(plan_queue.plan_has(0, str(data["behavior_id"])))
        return act

    def test_keep_enjoy_starts_now(self) -> None:
        """继续享受：交互对象已在主动H中，定下的是 10 分钟的性爱行为"""
        kernel_data.put(h_state.set, NPC, npc_active_h=True)
        self.pick(constant.Instruct.KEEP_ENJOY)

    def test_change_top_and_bottom_starts_now(self) -> None:
        """交给对方：定下的是 10 分钟的性爱行为"""
        self.pick(constant.Instruct.CHANGE_TOP_AND_BOTTOM)
