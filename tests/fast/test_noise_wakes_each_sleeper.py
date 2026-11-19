# -*- coding: UTF-8 -*-
"""
一阵动静对每个浅睡的人各掷一次
==============================
玩家在场景里弄出动静，同场景有两个浅睡（熟睡度 0）的干员：骰子必中时，两人都记进被吵醒的名单，
等事件 WokenByNoise 各自结算。已在名单里、还没结算的人不再掷骰。
"""

from unittest import mock

from Script.Design import handle_npc_ai_in_h
from tests.fast.base import FastTestCase


class NoiseWakesEachSleeperTest(FastTestCase):
    """吵醒判定按睡着的人各掷一次"""

    def setUp(self) -> None:
        """
        造玩家与两个浅睡的干员
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.world.chara(0, "博士")
        for cid in (1, 2):
            self.world.chara(cid, f"干员{cid}").sleep_point = 0
        self.cache.noise_woken.clear()

    def test_each_light_sleeper_rolls(self) -> None:
        """骰子必中时，两个浅睡的人都被吵醒"""
        with mock.patch("random.randint", return_value=1):
            for cid in (1, 2):
                handle_npc_ai_in_h.judge_weak_up_in_sleep_h(0, cid)
        self.assertEqual(self.cache.noise_woken, {1: 0, 2: 0})

    def test_pending_sleeper_does_not_roll_again(self) -> None:
        """已被吵醒、还没结算的人不再掷骰"""
        self.cache.noise_woken[1] = 0
        with mock.patch("random.randint", return_value=1) as roll:
            handle_npc_ai_in_h.judge_weak_up_in_sleep_h(0, 1)
        roll.assert_not_called()
