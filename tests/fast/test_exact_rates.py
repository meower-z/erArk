# -*- coding: UTF-8 -*-
"""
疲劳的精确比率：干员醒着每分钟加 7/72，睡着每分钟减 1/3，没有取整、没有下限
==========================================================================
- 睡 8 小时（每 5 分钟结算一次，同 Tick）减少疲劳 160。
- 睡 5 分钟减少疲劳 5/3。
- 干员醒着 5 分钟增加疲劳 35/72，3 分钟增加 7/24。
"""

import datetime
from fractions import Fraction

from Script.Core import constant
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import activity, needs
from Script.Modules.gameplay_resolution import working
from Script.Settle import realtime_settle
from tests.fast.base import FastTestCase
from Script.Modules.domains import identity


class ExactRatesTest(FastTestCase):
    """疲劳按分钟的精确比率"""

    def setUp(self) -> None:
        """玩家与一名干员，都在开局时刻。GameState 数据的读写记在 working.based_on(core.state()) 开的缓冲区里"""
        super().setUp()
        self.world.chara(0, "博士")
        self.npc = self.world.chara(1, "干员")
        self.enterContext(working.based_on(core.state()))

    def run_behavior(
        self, behavior_id: str, minutes: int, step: int
    ) -> identity.Identity:
        """
        干员从开局时刻起做 minutes 分钟的 behavior_id，每 step 分钟结算一次
        Keyword arguments:
        behavior_id -- 行为id
        minutes -- 分钟数
        step -- 每段的分钟数
        Return arguments:
        Character -- 干员
        """
        start = game_time.now()
        activity.update_behavior(
            self.npc.cid,
            behavior_id=behavior_id,
            start_time=start,
            duration=minutes,
        )
        cuts = list(range(0, minutes, step)) + [minutes]
        for since, now in zip(cuts, cuts[1:], strict=False):
            realtime_settle.character_aotu_change_value(
                self.npc.cid,
                start + datetime.timedelta(minutes=now),
                start + datetime.timedelta(minutes=since),
            )
        return self.npc

    def test_sleep_eight_hours(self) -> None:
        """疲劳 200 睡 480 分钟、每 5 分钟结算：剩 40"""
        needs.set(self.npc.cid, tired=200)
        self.run_behavior(constant.Behavior.SLEEP, 480, 5)
        self.assertEqual(needs.of(self.npc.cid)["tired"], 40)

    def test_sleep_five_minutes(self) -> None:
        """疲劳 100 睡 5 分钟：减 5/3"""
        needs.set(self.npc.cid, tired=100)
        self.run_behavior(constant.Behavior.SLEEP, 5, 5)
        self.assertEqual(needs.of(self.npc.cid)["tired"], 100 - Fraction(5, 3))

    def test_awake_five_minutes(self) -> None:
        """醒着等待 5 分钟：疲劳加 35/72"""
        needs.set(self.npc.cid, tired=0)
        self.run_behavior(constant.Behavior.WAIT, 5, 5)
        self.assertEqual(needs.of(self.npc.cid)["tired"], Fraction(35, 72))

    def test_awake_three_minutes(self) -> None:
        """醒着等待 3 分钟：疲劳加 7/24"""
        needs.set(self.npc.cid, tired=0)
        self.run_behavior(constant.Behavior.WAIT, 3, 3)
        self.assertEqual(needs.of(self.npc.cid)["tired"], Fraction(7, 24))
