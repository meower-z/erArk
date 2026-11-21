# -*- coding: UTF-8 -*-
"""
开始门：排队的行动开始时条件已不成立，就换成 1 分钟的发呆
==========================================================
测试直接调用 StartAction 的输入钩子 start_gate.gate，再调用最里层的 actions.time_stop（时停），
行动由 intent.behavior_action 造出，和选行动交回的一样。
门不写缓存，测试看门交给内层的行动：行为id、内核时长、没过的检查（意图 args 的 gate）与意图里的交互对象。
玩家、干员1（阿米娅）与干员2（凯尔希）在同一场景，干员1的交互对象是干员2。
- 干员1在H中时排下了对干员2接吻的后续行动，前提是自己在H中（self_is_h）。
  开始时H已结束，行动换成发呆，交互对象改回自己；H还没结束时原样开始。
- 排队时写明的交互对象在开始前死亡：换成发呆。
- 排队的行动换成发呆时仍标着来自队列，开始时照样弹出队首，角色不会一再选到它。
- 以幼年阶段（素质102）的干员为对象的接吻：换成发呆。
- 对仍保有初吻（素质4）的干员2接吻：干员1做时换成发呆，玩家做时原样开始。
- 时停中玩家的行动在内核里是 0 分钟，名义分钟数留在行动数据里；解除时停的行动保留它的分钟数，
  换成发呆时是 0 分钟。
"""

from collections.abc import Mapping

from Script.Core import constant, constant_promise
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, intent, start_gate
from Script.Modules.domains import modes
from tests import chara_abilities as ca, kernel_data
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
        self.assertFalse(core.in_settlement(), "内核不在结算里")
        self.pl = self.world.chara(0, "博士")
        self.amiya = self.world.chara(AMIYA, "阿米娅")
        self.kaltsit = self.world.chara(KALTSIT, "凯尔希")
        self.amiya.target_character_id = KALTSIT
        self.pl.target_character_id = KALTSIT

    def start(
        self,
        who: int,
        length: int,
        behavior_id: str = constant.Behavior.KISS_H,
        target: int | None = None,
        premises: tuple[str, ...] = (),
        queued: bool = False,
    ) -> core.Action:
        """
        角色选了接吻（或 behavior_id）的意图，把它的行动交给开始门
        Keyword arguments:
        who -- 角色id
        length -- 行动的分钟数
        behavior_id -- 行为id
        target -- 意图里写明的交互对象，None 时不写
        premises -- 开始时都要成立的前提id
        queued -- 意图是否来自队列
        Return arguments:
        Action -- 开始门与时停之后交给内层的行动
        """
        chosen = intent.Intent(behavior_id=behavior_id, minutes=length)
        if queued:
            chosen["queued"] = True
        if target is not None:
            chosen["target"] = target
        if premises:
            chosen["premises"] = list(premises)
        result = start_gate.gate(intent.behavior_action(who, chosen))
        assert isinstance(result, tuple)
        stopped = actions.time_stop(result[0])
        assert isinstance(stopped, tuple)
        return stopped[0]

    def started(self, act: core.Action, who: int) -> tuple:
        """
        开始的行动与缓存里角色的行为
        Keyword arguments:
        act -- 开始门交给内层的行动
        who -- 角色id
        Return arguments:
        tuple -- (行为id, 内核时长, 没过的检查, 意图里的交互对象)
        """
        data = act.action_data
        assert isinstance(data, Mapping)
        args = data.get("args", {})
        assert isinstance(args, Mapping)
        return (
            data["behavior_id"],
            act.duration,
            args.get(start_gate.GATE),
            data.get("target"),
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
                AMIYA,
            ),
            "H结束后开始的后续行动",
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

    def test_queued_target_off_line_falls_back_to_idle(self) -> None:
        """排队时在场的交互对象在开始前离线（不在 npc_id_got 里）：换成发呆"""
        self.cache.npc_id_got.discard(KALTSIT)
        act = self.start(AMIYA, 5, target=KALTSIT, queued=True)
        self.assertEqual(
            self.started(act, AMIYA)[:3],
            (constant.Behavior.SHARE_BLANKLY, 1, "target"),
            "交互对象离线后开始的排队行动",
        )

    def test_picked_off_line_target_starts(self) -> None:
        """刚选出的行动以不在场的角色（如婴儿）为对象：原样开始"""
        self.cache.npc_id_got.discard(KALTSIT)
        act = self.start(
            0, 30, behavior_id=constant.Behavior.HOLD_CHILD, target=KALTSIT
        )
        self.assertEqual(
            self.started(act, 0),
            (constant.Behavior.HOLD_CHILD, 30, None, KALTSIT),
            "以不在场的角色为对象、刚选出的行动",
        )

    def test_idle_keeps_queued_flag(self) -> None:
        """排队的行动因交互对象死亡换成发呆：发呆的意图仍标着来自队列"""
        self.kaltsit.dead = True
        data = self.start(AMIYA, 5, target=KALTSIT, queued=True).action_data
        assert isinstance(data, Mapping)
        self.assertEqual(
            (data["behavior_id"], data.get("queued")),
            (constant.Behavior.SHARE_BLANKLY, True),
            "（换上的行为，是否来自队列）",
        )

    def test_h_on_child_stage_target_falls_back_to_idle(self) -> None:
        """交互对象处于幼年阶段：接吻换成发呆"""
        ca.talent(self.kaltsit)[CHILD] = 1
        self.assertEqual(
            self.started(self.start(AMIYA, 5), AMIYA)[:3],
            (constant.Behavior.SHARE_BLANKLY, 1, "child_stage"),
            "以幼年阶段的干员为对象的接吻",
        )

    def test_npc_does_not_take_kept_first_kiss(self) -> None:
        """干员2仍保有初吻：干员1的接吻换成发呆，玩家的接吻原样开始"""
        ca.talent(self.kaltsit)[FIRST_KISS] = 1
        npc = self.started(self.start(AMIYA, 5), AMIYA)[:3]
        player = self.started(self.start(0, 5), 0)[:3]
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
        kernel_data.set_world(modes.set_time_stop, True)
        act = self.start(0, 5)
        data = act.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(
            (act.duration, data["minutes"]),
            (0, 5),
            "时停中玩家行动的（内核时长，名义分钟数）",
        )

    def test_time_stop_off_keeps_its_kernel_time(self) -> None:
        """
        时停中玩家解除时停 1 分钟：它的结算关掉时停，所以内核时长仍是 1，内核时钟一起走
        Keyword arguments:
        无
        Return arguments:
        无
        """
        kernel_data.set_world(modes.set_time_stop, True)
        act = self.start(0, 1, constant.Behavior.TIME_STOP_OFF)
        self.assertEqual(act.duration, 1, "解除时停的内核时长")

    def test_time_stop_off_swapped_for_idle_takes_no_kernel_time(self) -> None:
        """时停中玩家解除时停，交互对象已死亡：换成发呆，时停没解除，内核时长 0"""
        kernel_data.set_world(modes.set_time_stop, True)
        self.kaltsit.dead = True
        act = self.start(0, 1, constant.Behavior.TIME_STOP_OFF, target=KALTSIT)
        self.assertEqual(
            self.started(act, 0)[:3],
            (constant.Behavior.SHARE_BLANKLY, 0, "target"),
            "换成发呆的解除时停（行为，内核时长，没过的检查）",
        )
