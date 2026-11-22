# -*- coding: UTF-8 -*-
"""
干员选行动交回纯 JSON 意图
==========================
每个状态机在空闲干员上各运行一次：计划转换出的内核行动数据经 JSON 往返不变，
且行动种类有已登记的开始函数。
目标 10100（原地待机5分钟，状态机id为0）是一个行动；没有可选的行动时干员发呆到下一次 Tick。
"""

import json
from types import MappingProxyType
from typing import Any
from unittest import mock

from Script.Config import config_def, game_config
from Script.Core import constant
from Script.Design import update
from Script.Design import game_time, handle_npc_ai, handle_state_machine
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, intent, npc_starters
from Script.Modules.npc_action_choice import choose
from tests.fast.base import FastTestCase
from tests.chara_activity import behave

LOADED_FIRST = (update, npc_starters)
""" 先于 Script.Modules 导入的 update：Script.Modules 的包初始化要在 update 导入途中进行；
npc_starters 登记各种类的开始函数 """
NPC = 1
""" 选行动的干员 """
WAIT_TARGET = "10100"
""" 原地待机5分钟的目标 """


def thawed(value: core.JSON) -> Any:
    """
    内核冻结的 JSON 值换回 json 模块的形状（元组换成列表，映射换成字典）
    Keyword arguments:
    value -- 冻结的值
    Return arguments:
    Any -- 列表与字典组成的值
    """
    if isinstance(value, tuple | list):
        return [thawed(item) for item in value]
    if isinstance(value, MappingProxyType | dict):
        return {k: thawed(v) for k, v in value.items()}
    return value


class NpcIntentsPureTest(FastTestCase):
    """状态机只交回意图，不直接修改游戏状态"""

    def setUp(self) -> None:
        """
        玩家与一个空闲干员，内核时钟是此刻，上一次 Tick 在 2 分钟前
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.npc = self.world.chara(NPC, "干员")
        behave(self.npc.cid, constant.Behavior.SHARE_BLANKLY)
        self.clock = game_time.minutes(game_time.now())
        core.reset_state(
            core.GameState(
                self.clock,
                MappingProxyType({}),
                MappingProxyType(
                    {**core.state().data, actions.TICKED: self.clock - 2}
                ),
            )
        )

    def assert_json_intent(self, act: core.Action) -> None:
        """
        行动是这个干员此刻开始的，种类已登记，数据是经 json 往返不变的意图
        Keyword arguments:
        act -- 选出的行动
        Return arguments:
        无
        """
        self.assertEqual((act.who, act.start), (str(NPC), self.clock))
        self.assertGreaterEqual(act.duration, 1)
        self.assertTrue(act.action_id.startswith(intent.KIND_PREFIX))
        if act.action_id != intent.KIND_PREFIX + "Behavior":
            self.assertIn(act.action_id, core._actions)
        data = thawed(core._frozen(act.action_data))
        self.assertEqual(json.loads(json.dumps(data)), data)
        self.assertLessEqual(set(data), set(intent.Intent.__annotations__))
        self.assertIsInstance(data["behavior_id"], str)

    def test_every_state_machine_reads_only(self) -> None:
        """
        每个状态机的计划都是纯 JSON 意图，小世界里过半状态机正常运行
        Keyword arguments:
        无
        Return arguments:
        无
        """
        failed: dict[int, str] = {}
        ran = 0
        for state_machine_id in sorted(handle_state_machine.plans):
            with self.subTest(state_machine_id=state_machine_id):
                try:
                    plan = handle_state_machine.plan_of(state_machine_id, NPC)
                except Exception as error:  # 小世界缺这个状态机要读的数据
                    failed[state_machine_id] = repr(error)
                else:
                    ran += 1
                    self.assert_json_intent(plan.action())
        self.assertGreater(ran, len(failed), f"失败的状态机：{failed}")

    def test_pick_reads_only(self) -> None:
        """
        choose.choose 交回纯 JSON 意图
        Keyword arguments:
        无
        Return arguments:
        无
        """
        act = choose.choose(NPC)
        self.assert_json_intent(act)

    def test_wait_target_starts_five_minute_wait(self) -> None:
        """
        选中的目标执行状态机 0（原地待机5分钟，例如目标 10100）时干员原地等待 5 分钟，而不是当作没有可选的行动
        Keyword arguments:
        无
        Return arguments:
        无
        """
        wait_target = config_def.Target()
        wait_target.__dict__ = {
            "cid": WAIT_TARGET,
            "state_machine_id": constant.StateMachine.WAIT_5_MIN,
            "premise_id": "high_1",
            "type": 1,
            "remarks": "",
        }
        with (
            mock.patch.dict(
                game_config.config_target, {WAIT_TARGET: wait_target}
            ),
            mock.patch.object(
                handle_npc_ai,
                "search_target",
                side_effect=lambda cid, targets, *rest, **kw: (
                    (WAIT_TARGET, 1, 1, rest[1])
                    if WAIT_TARGET in targets
                    else ("", 0, 0, rest[1])
                ),
            ),
        ):
            act = choose.choose(NPC)
        self.assert_json_intent(act)
        self.assertEqual(act.duration, 5)
        self.assertEqual(act.action_data["behavior_id"], constant.Behavior.WAIT)

    def test_no_choice_idles_until_next_tick(self) -> None:
        """
        没有可选的行动时干员发呆到下一次 Tick（上一次 Tick 在 2 分钟前，发呆 3 分钟）
        Keyword arguments:
        无
        Return arguments:
        无
        """
        with mock.patch.object(
            handle_npc_ai, "choose_state_machine", return_value=None
        ):
            act = choose.choose(NPC)
        self.assert_json_intent(act)
        self.assertEqual(act.duration, 3)
        self.assertEqual(
            act.action_data["behavior_id"], constant.Behavior.SHARE_BLANKLY
        )
