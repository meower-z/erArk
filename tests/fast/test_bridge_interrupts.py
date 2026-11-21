# -*- coding: UTF-8 -*-
"""
结算途中的打断经计划队列在同一步交给内核
========================================
内核载入游戏的插件表（LOAD_ORDER），GameState 里每个角色都在做一件 50 分钟前开始、120 分钟长的事。
- 睡中被吵醒：Tick 的时间结算里掷骰吵醒了谁（结算换成只掷骰的替身），她在同一步排上"睡觉中被吵醒"，
  当前的行动在这一步就结束，被吵醒的名单清空；玩家也一样。
- 群交中恢复意识：玩家的反应与结束无意识H只为交互对象排一次，其他成员只结束自己的行动。
- 打断已被移除的角色不出错：这一步移除她，打断作废。
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from types import MappingProxyType
from unittest import mock

from Script.Core import constant
from Script.Design import game_time, handle_npc_ai_in_h
from Script.Kernel import core
from Script.Modules.domains import needs, roster
from Script.Modules.gameplay_resolution import (
    actions,
    plan_queue,
    time_hooks,
    working,
)
from Script.Settle import realtime_settle
from Script.Modules.load_order import LOAD_ORDER
from tests.fast.base import FastTestCase
from tests import chara_data, kernel_data
from tests.world import STANDARD_OUTFIT

CLOCK = game_time.minutes(datetime(2020, 12, 22, 10, 40))
""" 内核时钟 """
START = CLOCK - 50
""" 每个角色当前行动的开始 """


class BridgeInterruptsTest(FastTestCase):
    """计划队列的打断在同一步生效，玩家也被打断"""

    def setUp(self) -> None:
        """
        造玩家与干员1、2、3，内核载入插件表，从时钟 100 分开始
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        for cid in range(4):
            self.world.chara(cid, f"角色{cid}")
        core.load(LOAD_ORDER)
        self._reset(actions.roster())
        self.addCleanup(plan_queue.forget)

    def _reset(self, roster_ids: tuple[str, ...], ticked: int = CLOCK) -> None:
        """
        GameState 换成 roster_ids 里的角色各做一件 START 开始、120 分钟长的事。
        随后给这些角色写下置零的服装、状态值与身体管理，并穿上 STANDARD_OUTFIT
        这些角色的数据取自当前状态里的角色数据或 roster.offstage
        Keyword arguments:
        roster_ids -- 角色键
        ticked -- 上一次 Tick 结算到的时钟
        """
        game = core.state()
        kept = {who: chara.data for who, chara in game.characters.items()}
        characters = {
            who: core.Character(
                core.Action(who, core.idle.name, None, START, 120),
                MappingProxyType(dict(kept.get(who, {}))),
            )
            for who in roster_ids
        }
        data: dict[str, core.JSON] = {
            **core.state().data,
            time_hooks.TICKED: ticked,
            time_hooks.SETTLED_DAY: game_time.day(CLOCK),
            roster.ACTIVE: tuple(sorted(int(who) for who in roster_ids)),
        }
        core.reset_state(
            working.reconcile(
                core.GameState(
                    CLOCK, MappingProxyType(characters), MappingProxyType(data)
                )
            )
        )
        for who in roster_ids:
            chara_data.seed(int(who), STANDARD_OUTFIT)

    @contextmanager
    def _noise(self, maker: int, sleeper: int) -> Iterator[None]:
        """
        Tick 到期，时间结算换成替身：结算到 maker 时对 sleeper 掷一次吵醒的骰子，骰子必中
        Keyword arguments:
        maker -- 弄出动静的角色id
        sleeper -- 浅睡的角色id
        """
        kernel_data.set_needs(sleeper, sleep=0)

        def settle(cid: int, now: datetime, since: datetime) -> None:
            if cid == maker:
                handle_npc_ai_in_h.judge_weak_up_in_sleep_h(maker, sleeper)

        self._reset(actions.roster(), ticked=CLOCK - time_hooks.TICK_MINUTES)
        with (
            mock.patch.object(
                realtime_settle, "character_aotu_change_value", settle
            ),
            mock.patch("random.randint", return_value=1),
        ):
            yield

    def _ended(self, who: str) -> bool:
        """
        角色在内核里的行动是否已在此刻结束
        Keyword arguments:
        who -- 角色键
        Return arguments:
        bool -- 结束时为真
        """
        act = core.state().characters[who].action
        return act.start + act.duration <= core.state().clock

    def test_woken_npc_is_interrupted_in_the_same_step(self) -> None:
        """
        Tick 的结算里玩家吵醒了干员2：这一步之后她排上"睡觉中被吵醒"，她的行动在此刻结束，
        别人的不受影响，被吵醒的名单已清空
        Keyword arguments:
        无
        Return arguments:
        无
        """
        with self._noise(0, 2):
            core.step()
        self.assertEqual(core.state().data[time_hooks.TICKED], CLOCK, "Tick")
        self.assertEqual(core.state().clock, CLOCK, "事件那一步时间没走")
        self.assertEqual(needs.noise_woken(), {}, "名单清空")
        self.assertEqual(
            [i["behavior_id"] for i in plan_queue.planned(2)],
            [constant.Behavior.WAKE_UP_BY_NOISE],
        )
        self.assertTrue(self._ended("2"), "被吵醒的干员的行动在这一步结束")
        self.assertFalse(self._ended("1"), "别的干员照旧")
        self.assertFalse(self._ended("0"), "玩家照旧")

    def test_player_is_interrupted_like_an_npc(self) -> None:
        """
        玩家被干员1吵醒：玩家的行动同样在这一步结束，"睡觉中被吵醒"排在玩家的队首
        Keyword arguments:
        无
        Return arguments:
        无
        """
        with self._noise(1, 0):
            core.step()
        self.assertEqual(
            plan_queue.planned(0)[0]["behavior_id"],
            constant.Behavior.WAKE_UP_BY_NOISE,
        )
        self.assertTrue(self._ended("0"), "玩家的行动在这一步结束")

    def test_group_members_only_end_their_own_action(self) -> None:
        """
        交互对象1与成员2、3从无意识H中恢复：成员只被打断、不给玩家排任何行动；
        交互对象的裁决给玩家排一次反应与一次结束无意识H
        Keyword arguments:
        无
        Return arguments:
        无
        """
        with working.based_on(core.state()):
            for member in (2, 3):
                handle_npc_ai_in_h.handle_unconscious_h_response(
                    0, member, can_continue=False
                )
            self.assertEqual(plan_queue.planned(0), [], "成员不给玩家排行动")
            handle_npc_ai_in_h.handle_unconscious_h_response(0, 1)
            ends = [
                i["behavior_id"]
                for i in plan_queue.planned(0)
                if i["behavior_id"] == constant.Behavior.NO_CONSCIOUS_H_END
            ]
        self.assertEqual(len(ends), 1, "结束无意识H只排一次")
        effects = plan_queue.drain(())[0]
        self.assertEqual(
            {e.who for e in effects if isinstance(e, core.Interrupt)},
            {"0", "2", "3"},
            "玩家与两名成员被打断，交互对象不被打断",
        )

    def test_interrupt_of_a_removed_character_is_dropped(self) -> None:
        """
        干员3已离开（不在 npc_id_got 里）又被打断：这一步移除她，打断作废，不抛错
        Keyword arguments:
        无
        Return arguments:
        无
        """
        kernel_data.put(roster.discard, 3)
        plan_queue.interrupt(3)
        effects = plan_queue.drain(())[0]
        self.assertEqual(effects, (core.RemoveCharacter("3"),))
        self.assertEqual(
            tuple(core.preview(core.state(), effects).characters),
            ("0", "1", "2"),
        )
