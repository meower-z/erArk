# -*- coding: UTF-8 -*-
"""
一个时钟：内核的 clock 就是游戏时间
====================================
- 时间流逝最多走 5 分钟或到下一个 0 点；Tick 每 5 分钟把每个角色从上一次 Tick 结算到此刻，
  跨进新一天时先结算到 0 点；NewDay 在 0 点、任何人选行动之前只跑一次。
- tick_one 只结算一个角色，从上一次 Tick 算起；没有 ticked / settled_day 的 GameState 从它的时钟记起。
- game_time.minutes 与 at 互为逆运算，跨季也一样。
- 太阳与月相的取值不往缓存里写东西。
"""

import datetime
from dataclasses import replace
from types import MappingProxyType
from unittest import mock

from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import time_hooks
from Script.Settle import past_day_settle, realtime_settle
from tests.fast.base import FastTestCase

TICK = "gameplay_resolution.time_hooks.Tick"
NEW_DAY = "gameplay_resolution.time_hooks.NewDay"


class OneClockTest(FastTestCase):
    """内核时钟上的 Tick、NewDay 与时间流逝"""

    def setUp(self) -> None:
        """只扫描 Tick 与 NewDay；结算本身换成记录调用的替身"""
        super().setUp()
        self.enterContext(mock.patch.object(core, "_events", [TICK, NEW_DAY]))
        self.trace: list[tuple[str, int, core.JSON]] = []
        self.settled: list[tuple[int, int, int]] = []
        self.world.chara(0, "博士")
        self.npc = self.world.chara(1, "干员").cid

        def settle(
            cid: int, now: datetime.datetime, since: datetime.datetime
        ) -> None:
            self.settled.append(
                (cid, game_time.minutes(since), game_time.minutes(now))
            )

        def new_day() -> None:
            self.trace.append(("NewDay", core.state().clock, None))

        self.enterContext(
            mock.patch.object(
                realtime_settle, "character_aotu_change_value", settle
            )
        )
        self.enterContext(
            mock.patch.object(
                realtime_settle, "change_character_persistent_state"
            )
        )
        self.enterContext(
            mock.patch.object(past_day_settle, "update_new_day", new_day)
        )
        from Script.Design import handle_npc_ai

        self.enterContext(
            mock.patch.object(handle_npc_ai, "early_end", return_value=False)
        )

    def start(self, clock: int) -> None:
        """
        玩家与一名干员各做一个 10 小时的行动，从 clock 开始
        Keyword arguments:
        clock -- 起始时钟
        """
        characters = {
            who: core.Character(
                core.Action(who, core.idle.name, None, clock, 600),
                MappingProxyType({}),
            )
            for who in ("0", str(self.npc))
        }
        core.load((time_hooks,))
        core.reset_state(
            core.GameState(
                clock,
                MappingProxyType(characters),
                MappingProxyType(
                    {
                        time_hooks.TICKED: clock,
                        time_hooks.SETTLED_DAY: game_time.day(clock),
                    }
                ),
            )
        )

    def run_steps(self, n: int) -> None:
        """
        走 n 步，记下每步之后的时钟与 ticked
        Keyword arguments:
        n -- 步数
        """
        for __ in range(n):
            core.step()
            game = core.state()
            self.trace.append(
                ("step", game.clock, game.data[time_hooks.TICKED])
            )

    def test_tick_every_five_minutes_and_new_day_at_midnight(self) -> None:
        """23:50 起：23:55 Tick，0 点 Tick 再 NewDay，之后 00:05、00:10 各一次 Tick"""
        day = game_time.day(game_time.minutes(datetime.datetime(2019, 3, 1)))
        midnight = (day + 1) * game_time.MINUTES_PER_DAY
        self.start(midnight - 10)
        self.run_steps(9)
        self.assertEqual(
            [entry for entry in self.trace if entry[0] == "NewDay"],
            [("NewDay", midnight, None)],
        )
        clocks = [clock for kind, clock, _ in self.trace if kind == "step"]
        self.assertEqual(
            clocks,
            [midnight - 5] * 2
            + [midnight] * 3
            + [midnight + 5] * 2
            + [midnight + 10] * 2,
        )
        ticks = sorted({(since, now) for _, since, now in self.settled})
        self.assertEqual(
            ticks,
            [
                (midnight - 10, midnight - 5),
                (midnight - 5, midnight),
                (midnight, midnight + 5),
                (midnight + 5, midnight + 10),
            ],
        )
        self.assertEqual(
            sorted(cid for cid, since, _ in self.settled if since == midnight),
            [0, self.npc],
        )
        new_day_at = self.trace.index(("NewDay", midnight, None))
        self.assertEqual(
            self.trace[new_day_at - 1], ("step", midnight, midnight)
        )
        self.assertEqual(core.state().data[time_hooks.SETTLED_DAY], day + 1)

    def test_day_change_settles_the_piece_before_midnight(self) -> None:
        """23:57 起：时钟停在 0 点，先把 23:57 到 0 点结算掉，再跑新一天，下一次 Tick 在 00:05"""
        day = game_time.day(game_time.minutes(datetime.datetime(2019, 6, 30)))
        midnight = (day + 1) * game_time.MINUTES_PER_DAY
        self.start(midnight - 3)
        self.run_steps(5)
        self.assertIn((0, midnight - 3, midnight), self.settled)
        self.assertEqual(
            [entry[1] for entry in self.trace if entry[0] == "NewDay"],
            [midnight],
        )
        self.assertEqual(game_time.now(), game_time.at(midnight + 5))
        self.assertEqual(game_time.now().month, 9)
        self.assertEqual(game_time.now().day, 1)

    def test_tick_one_settles_one_character_from_ticked(self) -> None:
        """行动结束时只结算这个角色，从上一次 Tick 算起"""
        self.start(game_time.minutes(datetime.datetime(2019, 3, 1, 12)))
        self.run_steps(3)
        game = core.state()
        self.settled.clear()
        time_hooks.tick_one(self.npc)
        ticked = game.data[time_hooks.TICKED]
        self.assertEqual(self.settled, [(self.npc, ticked, game.clock)])

    def test_state_without_marks_starts_them_at_its_clock(self) -> None:
        """换进来的 GameState 没有 ticked / settled_day 时，从它的时钟记起，Tick 5 分钟后来"""
        clock = game_time.minutes(datetime.datetime(2019, 12, 30, 23, 58))
        self.start(clock)
        core.reset_state(replace(core.state(), data=MappingProxyType({})))
        self.assertEqual(
            dict(core.state().data),
            {
                time_hooks.TICKED: clock,
                time_hooks.SETTLED_DAY: game_time.day(clock),
            },
        )
        self.run_steps(2)
        self.assertEqual({since for _, since, _ in self.settled}, {clock})


class ClockHelpersTest(FastTestCase):
    """分钟数与游戏时间的换算，以及不写缓存的天象"""

    def test_minutes_and_at_round_trip_across_seasons(self) -> None:
        """两年里每隔 997 分钟取一点，minutes(at(m)) == m，at(m) 总在四季月上"""
        first = game_time.minutes(datetime.datetime(2019, 3, 1))
        for m in range(first, first + 2 * game_time.YEAR_DAY * 1440, 997):
            with self.subTest(m=m):
                self.assertEqual(game_time.minutes(game_time.at(m)), m)
                self.assertIn(
                    game_time.at(m).month, game_time.SEASON_MONTH_LIST
                )
        self.assertEqual(
            game_time.at(first + game_time.SEASON_DAY * 1440),
            datetime.datetime(2019, 6, 1),
        )

    def test_sun_and_moon_leave_the_cache_alone(self) -> None:
        """取太阳位置与月相不给缓存添键，也不改已有的值（字典按内容比）"""
        before = {
            key: dict(value) if isinstance(value, dict) else value
            for key, value in vars(self.cache).items()
        }
        when = datetime.datetime(2019, 9, 14, 21, 30)
        phase = game_time.get_moon_phase(when)
        game_time.get_sun_time(when)
        self.assertEqual(game_time.get_moon_phase(when), phase)
        self.assertEqual(vars(self.cache).keys(), before.keys())
        for key, value in vars(self.cache).items():
            if isinstance(value, dict):
                self.assertEqual(value, before[key], key)
            else:
                self.assertIs(value, before[key], key)
