# -*- coding: UTF-8 -*-
"""
随时间变化的数值按 5 分钟一段结算，合计与整段结算一样
==================================================
Tick 每 5 分钟结算一次，行动结束时再结算余下的一段；取整的数值按行为开始以来的分钟数取整，分段不丢也不重复。
- 睡 8 小时减少疲劳 160。
- 不落在 5 分钟格上的 5 分钟行动（3 分钟 + 2 分钟）增加疲劳 1。
- 视觉系技艺一个 60 分钟的行动消耗理智 5，不是每段至少 1。
- 时停中玩家的行动在内核里是 0 分钟，行动结束时按名义分钟数结算：每分钟消耗理智 2。
"""

import datetime

from Script.Core import constant
from Script.Design import game_time
from Script.Modules.gameplay_resolution import time_hooks
from Script.Settle import realtime_settle
from tests.fast.base import FastTestCase


class SettlePiecesTest(FastTestCase):
    """分段结算的合计"""

    def setUp(self) -> None:
        """玩家与一名干员，都在开局时刻"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.npc = self.world.chara(1, "干员")
        self.start = game_time.now()

    def behave(
        self, who: int, behavior_id: str, start: datetime.datetime, minutes: int
    ) -> None:
        """
        角色换上一个行为
        Keyword arguments:
        who -- 角色id
        behavior_id -- 行为id
        start -- 开始时间
        minutes -- 分钟数
        """
        behavior = self.cache.character_data[who].behavior
        behavior.behavior_id = behavior_id
        behavior.start_time = start
        behavior.duration = minutes

    def settle(self, who: int, cuts: list[int]) -> None:
        """
        从开局时刻起按分钟数 cuts 依次结算，每段从上一个切点到下一个
        Keyword arguments:
        who -- 角色id
        cuts -- 从开局时刻算起的切点分钟数，递增
        """
        for since, now in zip(cuts, cuts[1:], strict=False):
            realtime_settle.character_aotu_change_value(
                who,
                self.start + datetime.timedelta(minutes=now),
                self.start + datetime.timedelta(minutes=since),
            )

    def test_sleep_eight_hours_in_ticks(self) -> None:
        """睡 480 分钟，每 5 分钟结算一次：疲劳 120 减到 0（整段结算减 160）"""
        self.npc.tired_point = 120
        self.behave(1, constant.Behavior.SLEEP, self.start, 480)
        self.settle(1, list(range(0, 481, 5)))
        self.assertEqual(self.npc.tired_point, 0)

    def test_off_grid_action_adds_tired(self) -> None:
        """2 分钟开始的 5 分钟等待，在 5 分钟处切开（3 + 2）：疲劳加 1"""
        self.npc.tired_point = 0
        start = self.start + datetime.timedelta(minutes=2)
        self.behave(1, constant.Behavior.WAIT, start, 5)
        self.settle(1, [0, 5, 7])
        self.assertEqual(self.npc.tired_point, 1)

    def test_visual_art_sixty_minutes(self) -> None:
        """视觉系技艺开着做 60 分钟的行动，12 段结算：理智 100 减 5"""
        self.player.pl_ability.visual = True
        self.player.sanity_point = 100
        self.behave(0, constant.Behavior.WAIT, self.start, 60)
        self.settle(0, list(range(0, 61, 5)))
        self.assertEqual(self.player.sanity_point, 95)

    def test_time_stop_action_costs_nominal_minutes(self) -> None:
        """时停中玩家开始 10 分钟的行动（内核里 0 分钟），行动结束时结算：理智 100 减 20"""
        self.cache.time_stop_mode = True
        self.player.sanity_point = 100
        self.behave(0, constant.Behavior.WAIT, self.start, 10)
        time_hooks.tick_one(0)
        self.assertEqual(self.player.sanity_point, 80)
