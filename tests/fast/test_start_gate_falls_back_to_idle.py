# -*- coding: UTF-8 -*-
"""
开始门：排队的行动开始时条件已不成立，就换成 1 分钟的发呆
==========================================================
测试直接调用 StartAction 的输入钩子 start_gate.gate，行动数据由 actions.mirror 写出，和内核开始行动时一样。
测试先导入 update 再导入 Script.Modules，和游戏的导入顺序一样（反过来会循环导入）。
玩家、干员1（阿米娅）与干员2（凯尔希）在同一场景，干员1的交互对象是干员2。
- 干员1在H中时排下了对干员2接吻的后续行动，前提是自己在H中（self_is_h）。
  开始时H已结束，行动换成发呆，缓存里的行为与交互对象一起换；H还没结束时原样开始。
- 排队时写明的交互对象在开始前死亡：换成发呆。
- 以幼年阶段（素质102）的干员为对象的接吻：换成发呆。
- 对仍保有初吻（素质4）的干员2接吻：干员1做时换成发呆，玩家做时原样开始。
- 时停中玩家的行动在内核里是 0 分钟，名义分钟数留在行动数据里；解除时停的行动保留它的分钟数。
"""

from collections.abc import Mapping
from types import MappingProxyType

from Script.Core import constant, constant_promise
from Script.Design import update
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, plan_queue, start_gate
from tests.fast.base import FastTestCase

AMIYA = 1
""" 干员1的角色id """
KALTSIT = 2
""" 干员2的角色id """
FIRST_KISS = 4
""" 无接吻经验素质的id，值为1表示仍保有初吻 """
CHILD = 102
""" 幼女素质的id """


class StartGateTest(FastTestCase):
    """start_gate.gate 对排队与刚选出的行动的检查"""

    def setUp(self) -> None:
        """
        造玩家与两名干员，干员1以干员2为交互对象
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.assertFalse(update.in_resolution(), "内核没在跑")
        self.pl = self.world.chara(0, "博士")
        self.amiya = self.world.chara(AMIYA, "阿米娅")
        self.kaltsit = self.world.chara(KALTSIT, "凯尔希")
        self.amiya.target_character_id = KALTSIT
        self.pl.target_character_id = KALTSIT

    def start(self, who: int, length: int, **extra: core.JSON) -> core.Action:
        """
        让角色以接吻为当前行为，把它的行动交给开始门
        Keyword arguments:
        who -- 角色id
        length -- 行动的分钟数
        extra -- 行动数据里另加的键
        Return arguments:
        Action -- 开始门交给内层的行动
        """
        behavior = self.cache.character_data[who].behavior
        behavior.behavior_id = constant.Behavior.KISS_H
        behavior.duration = length
        act = core.Action(
            str(who),
            actions.behave.name,
            actions.mirror(behavior, **extra),
            0,
            length,
        )
        result = start_gate.gate(act)
        assert isinstance(result, tuple)
        return result[0]

    def started(self, act: core.Action, who: int) -> tuple:
        """
        开始的行动与缓存里角色的行为
        Keyword arguments:
        act -- 开始门交给内层的行动
        who -- 角色id
        Return arguments:
        tuple -- (行为id, 内核时长, 没过的检查, 缓存的行为id, 缓存的时长, 缓存的交互对象)
        """
        data = act.action_data
        assert isinstance(data, Mapping)
        character_data = self.cache.character_data[who]
        return (
            data["behavior_id"],
            act.duration,
            data.get(start_gate.GATE),
            character_data.behavior.behavior_id,
            character_data.behavior.duration,
            character_data.target_character_id,
        )

    def queued_h_follow_up(self) -> core.Action:
        """
        干员1在H中时排下的后续行动：对干员2接吻 5 分钟，前提是自己在H中
        Keyword arguments:
        无
        Return arguments:
        Action -- 开始门交给内层的行动
        """
        return self.start(
            AMIYA,
            5,
            target=KALTSIT,
            premises=(constant_promise.Premise.SELF_IS_H,),
        )

    def test_stale_queued_action_falls_back_to_idle(self) -> None:
        """排下后续行动后H结束了：开始时换成 1 分钟的发呆，交互对象改回自己"""
        self.amiya.sp_flag.is_h = False
        self.assertEqual(
            self.started(self.queued_h_follow_up(), AMIYA),
            (
                constant.Behavior.SHARE_BLANKLY,
                1,
                "premises",
                constant.Behavior.SHARE_BLANKLY,
                1,
                AMIYA,
            ),
            "H结束后开始的后续行动",
        )

    def test_stale_planned_npc_action_falls_back_to_idle(self) -> None:
        """
        计划队列里干员1的行动（plan_queue.start_planned）在H结束后开始：开始门把它换成 1 分钟的 behave 行动，
        没过的检查记为 premises
        """
        self.amiya.sp_flag.is_h = False
        act = core.Action(
            str(AMIYA),
            plan_queue.start_planned.name,
            MappingProxyType(
                {
                    "behavior_id": constant.Behavior.KISS_H,
                    "duration": 5,
                    "target": KALTSIT,
                    "premises": (constant_promise.Premise.SELF_IS_H,),
                }
            ),
            0,
            5,
        )
        result = start_gate.gate(act)
        assert isinstance(result, tuple)
        self.assertEqual(
            (result[0].action_id, *self.started(result[0], AMIYA)[1:3]),
            (actions.behave.name, 1, "premises"),
            "H结束后开始的排队行动（行动, 内核时长, 没过的检查）",
        )

    def test_queued_action_still_valid_starts_as_planned(self) -> None:
        """H还没结束：后续行动原样开始"""
        self.amiya.sp_flag.is_h = True
        self.assertEqual(
            self.started(self.queued_h_follow_up(), AMIYA),
            (
                constant.Behavior.KISS_H,
                5,
                None,
                constant.Behavior.KISS_H,
                5,
                KALTSIT,
            ),
            "H中开始的后续行动",
        )

    def test_queued_target_gone_falls_back_to_idle(self) -> None:
        """排队时写明的交互对象在开始前死亡：换成发呆"""
        self.kaltsit.dead = True
        act = self.start(AMIYA, 5, target=KALTSIT)
        self.assertEqual(
            self.started(act, AMIYA)[:3],
            (constant.Behavior.SHARE_BLANKLY, 1, "target"),
            "交互对象死亡后开始的行动",
        )

    def test_h_on_child_stage_target_falls_back_to_idle(self) -> None:
        """交互对象处于幼年阶段：接吻换成发呆"""
        self.kaltsit.talent[CHILD] = 1
        self.assertEqual(
            self.started(self.start(AMIYA, 5), AMIYA)[:3],
            (constant.Behavior.SHARE_BLANKLY, 1, "child_stage"),
            "以幼年阶段的干员为对象的接吻",
        )

    def test_npc_does_not_take_kept_first_kiss(self) -> None:
        """干员2仍保有初吻：干员1的接吻换成发呆，玩家的接吻原样开始"""
        self.kaltsit.talent[FIRST_KISS] = 1
        npc = self.started(self.start(AMIYA, 5), AMIYA)[:3]
        player = self.started(self.start(0, 5, minutes=5), 0)[:3]
        self.assertEqual(
            (npc, player),
            (
                (constant.Behavior.SHARE_BLANKLY, 1, "virginity"),
                (constant.Behavior.KISS_H, 5, None),
            ),
            "（干员1的接吻，玩家的接吻）",
        )

    def test_time_stop_player_action_takes_no_kernel_time(self) -> None:
        """时停中玩家接吻 5 分钟：内核时长 0，名义分钟数 5"""
        self.cache.time_stop_mode = True
        act = self.start(0, 5, minutes=5)
        data = act.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(
            (act.duration, data[start_gate.MINUTES]),
            (0, 5),
            "时停中玩家行动的（内核时长，名义分钟数）",
        )

    def test_time_stop_off_keeps_its_kernel_time(self) -> None:
        """
        时停中玩家解除时停 1 分钟：结算关掉时停、缓存的游戏时间前进 1 分钟，所以内核时长仍是 1，内核时钟一起走
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.cache.time_stop_mode = True
        behavior = self.pl.behavior
        behavior.behavior_id = constant.Behavior.TIME_STOP_OFF
        behavior.duration = 1
        act = core.Action(
            "0", actions.behave.name, actions.mirror(behavior, minutes=1), 0, 1
        )
        result = start_gate.gate(act)
        assert isinstance(result, tuple)
        self.assertEqual(result[0].duration, 1, "解除时停的内核时长")
