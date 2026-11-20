# -*- coding: UTF-8 -*-
"""
玩家指令只选不写
================
每个指令处理函数在玩家选行动时跑一遍：定下行动的抛出 player_pick.Chosen，行动数据是能原样过 JSON 的 Intent，
抛出前缓存逐字节相同（按 pickle 比较）；
不定行动的换面板、问玩家后返回，或是零时间的操作。
种类 Instruct 的开始代码（handle_instruct.start_instruct）在行动开始时才写缓存。
"""

import json
from typing import cast

from Script.Core import constant
from Script.Design import update
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, intent, player_starters
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
from tests.fast.base import FastTestCase
from tests.fast.test_npc_pick_leaves_cache import changed, pickled

LOADED_FIRST = update
""" 先于 Script.Modules 导入的 update：Script.Modules 的包初始化要在 update 导入途中进行 """
NPC = 1
""" 玩家的交互对象 """


class InstructHandlersChooseTest(FastTestCase):
    """指令处理函数只交回选择，不写缓存"""

    def setUp(self) -> None:
        """
        玩家与一个当交互对象的干员；内核状态由缓存投影
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        self.player.target_character_id = NPC
        core.reset_state(actions.state_from_cache())

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
        定下行动的处理函数抛出 Chosen 前缓存不变，行动数据是 JSON；大半指令能在小世界里定下行动
        Keyword arguments:
        无
        Return arguments:
        无
        """
        chosen: dict[str, core.Action] = {}
        writers: dict[str, list[str]] = {}
        failed: dict[str, str] = {}
        for instruct_id in sorted(constant.handle_instruct_data):
            self.setUp()
            before = pickled(self.cache)
            try:
                act = self.pick(instruct_id)
            except Exception as error:
                failed[instruct_id] = repr(error)
                continue
            if act is None:
                continue
            chosen[instruct_id] = act
            written = changed(before, self.cache)
            if written:
                writers[instruct_id] = written
            with self.subTest(instruct=instruct_id):
                self.assertEqual(act.who, "0")
                self.assertTrue(act.action_id.startswith(intent.KIND_PREFIX))
                data = act.action_data
                self.assertEqual(json.loads(json.dumps(data)), data)
        self.assertEqual(writers, {}, "定下行动前写了缓存")
        self.assertGreater(
            len(chosen),
            len(constant.handle_instruct_data) // 2,
            f"定下行动的太少；出错的：{failed}",
        )

    def start(self, act: core.Action) -> None:
        """
        跑种类 Instruct 的开始代码，行动数据先过一遍 JSON
        Keyword arguments:
        act -- 定下的行动
        """
        self.assertEqual(
            act.action_id, intent.KIND_PREFIX + player_starters.KIND
        )
        data = json.loads(json.dumps(act.action_data))
        handle_instruct.start_instruct(0, cast(intent.Intent, data))

    def test_door_lock_written_at_start(self) -> None:
        """
        锁门：选择时门不变，开始时锁上
        Keyword arguments:
        无
        Return arguments:
        无
        """
        scene = self.world.scene(self.player.position)
        scene.close_flag = 0
        act = self.pick(constant.Instruct.DOOR_LOCK_INNER)
        assert act is not None
        self.assertEqual(scene.close_flag, 0)
        self.start(act)
        self.assertEqual(scene.close_flag, scene.close_type)

    def test_apologize_calms_at_start(self) -> None:
        """
        道歉：选择时愤怒值不变，选出的成败按减后的值定，开始时才减
        Keyword arguments:
        无
        Return arguments:
        无
        """
        target = self.cache.character_data[NPC]
        target.angry_point = 35
        act = self.pick(constant.Instruct.APOLOGIZE)
        assert act is not None
        assert isinstance(act.action_data, dict)
        self.assertEqual(target.angry_point, 35)
        self.assertEqual(
            act.action_data["behavior_id"], constant.Behavior.APOLOGIZE
        )
        self.start(act)
        self.assertLess(target.angry_point, 35)

    def test_target_waits_through_plan_queue(self) -> None:
        """
        要交互对象等待的指令：开始时交互对象排上同样分钟数的等待，不直接改她的行为
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Modules.gameplay_resolution import plan_queue

        target = self.cache.character_data[NPC]
        behavior_before = target.behavior.behavior_id
        act = self.pick(constant.Instruct.LISTEN_COMPLAINT)
        assert act is not None
        self.start(act)
        self.assertEqual(target.behavior.behavior_id, behavior_before)
        self.assertTrue(plan_queue.plan_has(NPC, constant.Behavior.WAIT))
