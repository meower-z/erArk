# -*- coding: UTF-8 -*-
"""
疲劳的连锁反应是内核事件，后续行动排进计划队列
==============================================
开新游戏，把阿米娅与凯尔希放到博士身边：阿米娅与博士在 H 中，凯尔希在智能跟随博士。
两人的体力都是 1，还没疲劳。事件在每一步开始时先于选行动结算，所以博士下一次选行动之前：
- 阿米娅变疲劳，H 结束，「太累了，H 结束」显示一次；凯尔希变疲劳，「太累了，无法继续跟随」显示一次；
  H 结束的那句在前；
- 博士接下来开始的行动是 T_H_HP_0（体力耗尽的结束 H），他还没有选别的行动；
- 结束后阿米娅不在 H 中，凯尔希不再跟随。
两个事件互相让对方成立时，事件与收尾步数的上限（core.CYCLE_LIMIT）让内核抛 core.EventCycle，而不是在同一时刻无限循环。
"""

import importlib
from unittest import mock

from tests import kernel_data
from tests.chara_activity import aim, behave
from tests.slow.base import SlowTestCase
from tests.kernel_project import activity

AMIYA_ID = 1
""" 阿米娅的角色id """
KALTSIT_ID = 3
""" 凯尔希的角色id """


class EventsTiredChainTest(SlowTestCase):
    """疲劳的连锁反应按事件结算，H 结束在前，玩家接着做 T_H_HP_0"""

    time_limit = 180

    def setUp(self) -> None:
        """
        开新游戏后把阿米娅与凯尔希移到博士身边：阿米娅与博士在 H 中，凯尔希智能跟随，两人体力为 1
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        from Script.Core import constant

        self.pl = self.cache.character_data[0]
        self.amiya = self.cache.character_data[AMIYA_ID]
        self.kaltsit = self.cache.character_data[KALTSIT_ID]
        for cid in (AMIYA_ID, KALTSIT_ID):
            self.assertIn(
                cid,
                kernel_data.domain("roster").active(),
                f"本局应有干员 {cid}",
            )
            self.world.move(cid, list(activity.position(self.pl.cid)))
        aim(self.pl.cid, AMIYA_ID)
        kernel_data.put(kernel_data.domain("flags").set, self.pl.cid, is_h=True)
        kernel_data.put(
            kernel_data.domain("flags").set, self.amiya.cid, is_h=True
        )
        kernel_data.put(
            kernel_data.domain("flags").set, self.kaltsit.cid, is_follow=1
        )
        behave(self.kaltsit.cid, constant.Behavior.SHARE_BLANKLY)
        for chara in (self.amiya, self.kaltsit):
            kernel_data.set_needs(chara.cid, hit=1)
            kernel_data.put(
                kernel_data.domain("flags").set, chara.cid, tired=False
            )
        history = importlib.import_module("Script.Modules.domains.history")
        kernel_data.set_world(history.set_recent, [])
        from Script.UI.Moudle import draw

        patcher = mock.patch.object(
            draw.WaitDraw, "draw", autospec=True, side_effect=draw.WaitDraw.draw
        )
        self.wait_draw = patcher.start()
        self.addCleanup(patcher.stop)

    def drawn(self) -> list[str]:
        """
        从 setUp 起 WaitDraw 画过的文本，按画的顺序
        Keyword arguments:
        无
        Return arguments:
        list[str] -- 文本
        """
        return [str(c.args[0].text) for c in self.wait_draw.call_args_list]

    def test_h_end_then_follow_stop(self) -> None:
        """
        游戏推进到博士下一次选行动：两句各显示一次，H 结束在前；博士先做 T_H_HP_0；阿米娅出了 H，凯尔希不再跟随
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Core import constant
        from tests import world

        world.act(lambda: None)
        texts = self.drawn()
        h_end = [t for t in texts if "太累了，H 结束" in t]
        follow = [t for t in texts if "太累了，无法继续跟随" in t]
        self.assertEqual(
            h_end,
            [self.amiya.name + "太累了，H 结束\n"],
            f"显示的文本：{texts}",
        )
        self.assertEqual(
            follow,
            [self.kaltsit.name + "太累了，无法继续跟随\n"],
            f"显示的文本：{texts}",
        )
        self.assertLess(
            texts.index(h_end[0]), texts.index(follow[0]), "H 结束的那句在前"
        )
        history = importlib.import_module("Script.Modules.domains.history")
        self.assertEqual(
            history.recent()[:1],
            [constant.Behavior.T_H_HP_0],
            "博士接下来开始的行动是 T_H_HP_0",
        )
        self.assertFalse(
            kernel_data.domain("flags").get(self.amiya.cid, "is_h"),
            "阿米娅不在 H 中",
        )
        self.assertEqual(
            kernel_data.domain("flags").get(self.kaltsit.cid, "is_follow"),
            0,
            "凯尔希不再跟随",
        )

    def test_event_cycle_raises(self) -> None:
        """
        注册两个互相让对方成立的事件，博士等待五分钟：内核抛 core.EventCycle
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Core import constant
        from Script.Kernel import core

        kernel_data.put(
            kernel_data.domain("flags").set, self.pl.cid, is_h=False
        )
        kernel_data.put(
            kernel_data.domain("flags").set, self.amiya.cid, is_h=False
        )
        kernel_data.put(
            kernel_data.domain("flags").set, self.kaltsit.cid, is_follow=0
        )
        flip = {"a": True}

        def a_holds(game: core.GameState) -> bool | None:
            """事件 A 的触发：flip 为真"""
            return True if flip["a"] else None

        def b_holds(game: core.GameState) -> bool | None:
            """事件 B 的触发：flip 为假"""
            return None if flip["a"] else True

        @core.event("tests.CycleA", a_holds)
        def cycle_a(_due: bool) -> core.Effects:
            """事件 A：让 B 成立"""
            flip["a"] = False
            return ()

        @core.event("tests.CycleB", b_holds)
        def cycle_b(_due: bool) -> core.Effects:
            """事件 B：让 A 成立"""
            flip["a"] = True
            return ()

        with self.assertRaises(core.EventCycle):
            self.instruct(constant.Instruct.WAIT)

    def test_player_spent_not_when_other_end_queued(self) -> None:
        """
        博士体力为 1、还在 H 中，而他的队列里已排着别的 H 结束（H_INTERRUPT）：玩家不算力竭。
        成立的话 plan_h_end 什么也不排，条件一直成立，内核抛 EventStillTrue
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from typing import cast

        from Script.Core import constant
        from Script.Kernel import core
        from Script.Modules.gameplay_resolution import events, plan_queue

        kernel_data.set_needs(self.pl.cid, hit=1)
        game = cast(core.GameState, None)
        self.assertTrue(events._player_spent(game), "没排结束时成立")
        kernel_data.written(
            plan_queue.plan_next, 0, constant.Behavior.H_INTERRUPT, 5
        )
        self.assertFalse(
            events._player_spent(game), "排着 H_INTERRUPT 时不成立"
        )

    def test_group_exit_skips_members_already_exiting(self) -> None:
        """
        群交中阿米娅力竭退出时，凯尔希已排上退出：不再把她算作剩下的成员，群交结束排进博士的队列，
        不排转为与她的普通 H
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Core import constant
        from Script.Design import handle_npc_ai
        from Script.Modules.gameplay_resolution import plan_queue

        modes = importlib.import_module("Script.Modules.domains.modes")
        kernel_data.set_world(modes.set_group_sex, True)
        kernel_data.put(
            kernel_data.domain("flags").set, self.kaltsit.cid, is_follow=0
        )
        kernel_data.put(
            kernel_data.domain("flags").set, self.kaltsit.cid, is_h=True
        )
        with kernel_data.writing():
            plan_queue.plan_next(
                KALTSIT_ID, constant.Behavior.GROUP_SEX_NPC_HP_0_END, 1
            )
            handle_npc_ai.commit_group_sex_tired_exit(AMIYA_ID)
        queued = [p["behavior_id"] for p in plan_queue.planned(0)]
        ends = {constant.Behavior.GROUP_SEX_END, *constant.special_end_H_list}
        self.assertNotIn(
            constant.Behavior.GROUP_SEX_TO_H, queued, f"队列：{queued}"
        )
        self.assertTrue(any(b in ends for b in queued), f"队列：{queued}")
