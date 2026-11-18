# -*- coding: UTF-8 -*-
"""
干员选行动时缓存不变
====================
每个状态机在一个空闲干员身上跑一遍：交回计划前后，游戏缓存逐字节相同（按 pickle 比较），
只有 WRITERS 里还没搬走写入的状态机例外。计划交给 gameplay_resolution 的 npc_start 开始后，干员才换上计划里的行为。
"""

import pickle
from typing import Any

from Script.Core import constant
from Script.Design import update
from Script.Design import handle_state_machine
from Script.Modules.gameplay_resolution import npc_start
from Script.Modules.npc_action_choice import choose
from tests.fast.base import FastTestCase

LOADED_FIRST = update
""" 先于 Script.Modules 导入的 update：Script.Modules 的包初始化要在 update 导入途中进行，
先进 Script.Modules 会循环导入失败 """
NPC = 1
""" 选行动的干员 """
WRITERS = frozenset({constant.StateMachine.SEE_H_AND_MOVE_TO_DORMITORY})
""" 还会写缓存的状态机：被撞见的状态机在选择时弹面板（它归 gameplay_resolution 的发现结算） """


def changed(before: dict[str, bytes], cache: Any) -> list[str]:
    """
    缓存里与 before 不同的属性名；character_data 按角色比
    Keyword arguments:
    before -- 属性名 -> pickle
    cache -- 游戏缓存
    Return arguments:
    list -- 变了的属性
    """
    now = pickled(cache)
    return sorted(
        k for k in before.keys() | now.keys() if before.get(k) != now.get(k)
    )


def pickled(cache: Any) -> dict[str, bytes]:
    """
    缓存的每个属性（character_data 拆成每个角色）的 pickle
    Keyword arguments:
    cache -- 游戏缓存
    Return arguments:
    dict -- 属性名 -> pickle
    """
    out = {
        k: pickle.dumps(v)
        for k, v in vars(cache).items()
        if k != "character_data"
    }
    for cid, data in cache.character_data.items():
        out[f"character_data[{cid}]"] = pickle.dumps(data)
    return out


class NpcPickLeavesCacheTest(FastTestCase):
    """状态机只交回计划，不写缓存"""

    def setUp(self) -> None:
        """
        玩家与一个空闲干员
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.npc = self.world.chara(NPC, "干员")
        self.npc.behavior.behavior_id = constant.Behavior.SHARE_BLANKLY

    def test_state_machines_leave_cache(self) -> None:
        """
        每个状态机交回计划时缓存不变（跑到一半抛错的也算）；至少要跑起来大半
        Keyword arguments:
        无
        Return arguments:
        无
        """
        wrote: dict[int, list[str]] = {}
        ran = failed = 0
        before = pickled(self.cache)
        for state_machine_id in sorted(handle_state_machine.plans):
            if state_machine_id in WRITERS:
                continue
            try:
                handle_state_machine.plan_of(state_machine_id, NPC)
            except Exception:  # 小世界缺这个状态机要读的数据
                failed += 1
            else:
                ran += 1
            diff = changed(before, self.cache)
            if diff:
                wrote[state_machine_id] = diff
                before = pickled(self.cache)
        self.assertEqual(wrote, {}, "状态机写了缓存")
        self.assertGreater(ran, failed, f"跑起来 {ran} 个，失败 {failed} 个")

    def test_pick_leaves_cache(self) -> None:
        """
        choose.choose 选出状态机与计划，缓存不变
        Keyword arguments:
        无
        Return arguments:
        无
        """
        before = pickled(self.cache)
        picked = choose.choose(NPC)
        self.assertEqual(changed(before, self.cache), [])
        self.assertIsNotNone(picked)
        assert picked is not None
        self.assertTrue(picked.state_machine_id)
        self.assertIsNotNone(picked.plan)

    def test_plan_starts_at_npc_start(self) -> None:
        """
        睡觉的计划交回时干员还在发呆，计划的时长是8小时；npc_start 开始它后，干员睡8小时
        Keyword arguments:
        无
        Return arguments:
        无
        """
        plan = handle_state_machine.plan_of(constant.StateMachine.SLEEP, NPC)
        assert plan is not None
        self.assertEqual(plan.minutes(), 480)
        self.assertEqual(
            self.npc.behavior.behavior_id, constant.Behavior.SHARE_BLANKLY
        )
        npc_start.start_plan(NPC, plan)
        self.assertEqual(self.npc.behavior.behavior_id, constant.Behavior.SLEEP)
        self.assertEqual(self.npc.behavior.duration, 480)
        self.assertEqual(self.npc.state, constant.CharacterStatus.STATUS_SLEEP)
