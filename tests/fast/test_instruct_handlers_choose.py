# -*- coding: UTF-8 -*-
"""
玩家指令只选不写
================
每个已注册的指令处理函数在玩家选择中各运行一次：
定下行动的函数抛出 player_pick.Chosen，其 Intent 经 JSON 往返不变；
未定下行动的函数切换面板、询问玩家后返回或执行零时间操作。
"""

import json
from typing import cast

from Script.Core import constant
from Script.Design import update
from Script.Kernel import core
from Script.Modules.gameplay_resolution import intent, player_starters
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
from tests.fast.base import FastTestCase
from tests import kernel_data
from tests.chara_activity import aim
from Script.Modules.domains import activity, scene_state

LOADED_FIRST = update
""" 先于 Script.Modules 导入的 update：Script.Modules 的包初始化要在 update 导入途中进行 """
NPC = 1
""" 玩家的交互对象 """


class InstructHandlersChooseTest(FastTestCase):
    """指令处理函数只交回选择，不直接修改游戏状态"""

    def setUp(self) -> None:
        """
        玩家与一个当交互对象的干员；内核状态由领域数据投影
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        aim(self.player.cid, NPC)
        core.reset_state(kernel_data.reprojected(core.state()))

    def pick(self, instruct_id: str) -> core.Action | None:
        """
        跑一个指令处理函数
        Keyword arguments:
        instruct_id -- 指令id
        Return arguments:
        Action | None -- 定下的行动；没定下时为 None
        """
        try:
            constant.handle_instruct_data[instruct_id]()
        except player_pick.Chosen as chosen:
            return chosen.action
        return None

    def test_handlers_choose_without_writing(self) -> None:
        """
        定下行动的指令处理函数交回 JSON 行动数据，小世界里过半指令能定下行动
        Keyword arguments:
        无
        Return arguments:
        无
        """
        chosen: dict[str, core.Action] = {}
        failed: dict[str, str] = {}
        for instruct_id in sorted(constant.handle_instruct_data):
            self.setUp()
            try:
                act = self.pick(instruct_id)
            except Exception as error:
                failed[instruct_id] = repr(error)
                continue
            if act is None:
                continue
            chosen[instruct_id] = act
            with self.subTest(instruct=instruct_id):
                self.assertEqual(act.who, "0")
                self.assertTrue(act.action_id.startswith(intent.KIND_PREFIX))
                data = act.action_data
                self.assertEqual(json.loads(json.dumps(data)), data)
        self.assertGreater(
            len(chosen),
            len(constant.handle_instruct_data) // 2,
            f"定下行动的太少；出错的：{failed}",
        )

    def start(self, act: core.Action) -> None:
        """
        跑种类 Instruct 的开始代码，行动数据先过一遍 JSON。开始代码写的 GameState 数据随后套用到内核状态上
        Keyword arguments:
        act -- 定下的行动
        """
        self.assertEqual(
            act.action_id, intent.KIND_PREFIX + player_starters.KIND
        )
        data = json.loads(json.dumps(act.action_data))
        with kernel_data.writing():
            handle_instruct.start_instruct(0, cast(intent.Intent, data))

    def test_door_lock_written_at_start(self) -> None:
        """
        锁门：选择时门不变，开始时锁上
        Keyword arguments:
        无
        Return arguments:
        无
        """
        scene = self.world.scene(activity.position(self.player.cid))
        kernel_data.put(scene_state.set_close_flag, scene.scene_path, 0)
        act = self.pick(constant.Instruct.DOOR_LOCK_INNER)
        assert act is not None
        self.assertEqual(scene_state.close_flag(scene.scene_path), 0)
        self.start(act)
        self.assertEqual(
            scene_state.close_flag(scene.scene_path), scene.close_type
        )

    def test_apologize_calms_at_start(self) -> None:
        """
        道歉：选择时愤怒值不变，选出的成败按减后的值定，开始时才减
        Keyword arguments:
        无
        Return arguments:
        无
        """
        kernel_data.set_needs(NPC, angry=35)
        act = self.pick(constant.Instruct.APOLOGIZE)
        assert act is not None
        assert isinstance(act.action_data, dict)
        self.assertEqual(kernel_data.needs_of(NPC)["angry"], 35)
        self.assertEqual(
            act.action_data["behavior_id"], constant.Behavior.APOLOGIZE
        )
        self.start(act)
        self.assertLess(kernel_data.needs_of(NPC)["angry"], 35)

    def test_target_waits_through_plan_queue(self) -> None:
        """
        要交互对象等待的指令：开始时交互对象排上同样分钟数的等待，不直接改她的行为
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Modules.gameplay_resolution import plan_queue

        behavior_before = activity.behavior(NPC).behavior_id
        act = self.pick(constant.Instruct.LISTEN_COMPLAINT)
        assert act is not None
        self.start(act)
        self.assertEqual(activity.behavior(NPC).behavior_id, behavior_before)
        self.assertTrue(plan_queue.plan_has(NPC, constant.Behavior.WAIT))
