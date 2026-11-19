# -*- coding: UTF-8 -*-
"""
一阵动静对每个浅睡的人各掷一次
==============================
玩家在场景里弄出动静，同场景有两个浅睡（熟睡度 0）的干员：骰子必中时，两人都记进被吵醒的名单，
在掷骰的这一步里按角色id依次醒来（time_hooks._wake_the_woken），名单清空。
同一次结算里已在名单里的人不重复掷骰。
"""

from unittest import mock

from Script.Design import handle_npc_ai_in_h
from Script.Modules.gameplay_resolution import time_hooks
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

    def test_woken_wake_in_order_and_list_empties(self) -> None:
        """两人被吵醒后，这一步里按角色id依次醒来（wake_by_noise 的替身记下顺序），名单清空"""
        with mock.patch("random.randint", return_value=1):
            for cid in (2, 1):
                handle_npc_ai_in_h.judge_weak_up_in_sleep_h(0, cid)
        with mock.patch.object(handle_npc_ai_in_h, "wake_by_noise") as wake:
            time_hooks._wake_the_woken()
        self.assertEqual(
            [c.args for c in wake.call_args_list], [(0, 1), (0, 2)]
        )
        self.assertEqual(self.cache.noise_woken, {})

    def test_pending_sleeper_does_not_roll_again(self) -> None:
        """同一次结算里已被吵醒的人不重复掷骰"""
        self.cache.noise_woken[1] = 0
        with mock.patch("random.randint", return_value=1) as roll:
            handle_npc_ai_in_h.judge_weak_up_in_sleep_h(0, 1)
        roll.assert_not_called()
