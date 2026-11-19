# -*- coding: UTF-8 -*-
"""
体控催眠的木头人干员不选目标
============================
木头人（hypnosis.blockhead）的干员和H中的干员一样不赋予新活动，发呆到下一次 Tick；
没有木头人时，她照常选出目标（这里是原地待机10分钟）。
"""

from types import MappingProxyType
from unittest import mock

from Script.Config import config_def, game_config
from Script.Core import constant
from Script.Design import update
from Script.Design import game_time, handle_npc_ai
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, npc_starters
from Script.Modules.npc_action_choice import choose
from tests.fast.base import FastTestCase

LOADED_FIRST = (update, npc_starters)
""" 先于 Script.Modules 导入的 update：Script.Modules 的包初始化要在 update 导入途中进行；
npc_starters 登记各种类的开始函数 """
NPC = 1
""" 选行动的干员 """
WAIT_TARGET = "10101"
""" 原地待机10分钟的目标 """


class BlockheadNpcWaitsTest(FastTestCase):
    """木头人干员选行动"""

    def setUp(self) -> None:
        """玩家与一个空闲干员，唯一成立的目标是原地待机10分钟；上一次 Tick 在 2 分钟前"""
        super().setUp()
        self.world.chara(0, "博士")
        self.npc = self.world.chara(NPC, "干员")
        clock = game_time.minutes(game_time.now())
        core.reset_state(
            core.GameState(
                clock,
                MappingProxyType({}),
                MappingProxyType({actions.TICKED: clock - 2}),
            )
        )
        wait_target = config_def.Target()
        wait_target.__dict__ = {
            "cid": WAIT_TARGET,
            "state_machine_id": constant.StateMachine.WAIT_10_MIN,
            "premise_id": "high_1",
            "type": 1,
            "remarks": "",
        }
        targets = mock.patch.dict(
            game_config.config_target, {WAIT_TARGET: wait_target}
        )
        search = mock.patch.object(
            handle_npc_ai,
            "search_target",
            side_effect=lambda cid, target_list, *rest, **kw: (
                (WAIT_TARGET, 1, 1, rest[1])
                if WAIT_TARGET in target_list
                else ("", 0, 0, rest[1])
            ),
        )
        for patch in (targets, search):
            patch.start()
            self.addCleanup(patch.stop)

    def picked(self) -> tuple[object, int]:
        """
        干员选出的行动
        Return arguments:
        tuple -- (行为id, 分钟数)
        """
        act = choose.choose(NPC)
        data = act.action_data
        assert isinstance(data, MappingProxyType | dict)
        return data["behavior_id"], act.duration

    def test_awake_npc_picks_target(self) -> None:
        """没被催眠成木头人：选出原地待机10分钟"""
        self.assertEqual(self.picked(), (constant.Behavior.WAIT, 10))

    def test_blockhead_npc_idles(self) -> None:
        """木头人：不选目标，发呆到下一次 Tick（3 分钟）"""
        self.npc.hypnosis.blockhead = True
        self.assertEqual(self.picked(), (constant.Behavior.SHARE_BLANKLY, 3))
