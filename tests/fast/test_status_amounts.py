# -*- coding: UTF-8 -*-
"""
状态值的取整：一次性的行动效果截断为整数，时间结算保留精确值
==========================================================
- 行动效果（交互对象增加少量S快）写进状态值与结算记录的量是整数。
- 时间结算（有意识下持续结算的灌肠苦痛）不取整：结算 5 次 1 分钟与结算 1 次 5 分钟加的苦痛相同。
"""

import datetime

from Script.Core import constant, constant_effect, game_type
from Script.Settle import realtime_settle
from tests.fast.base import FastTestCase
from tests import chara_abilities as ca


class StatusAmountsTest(FastTestCase):
    """一次性的行动效果与时间结算写进状态值的量"""

    def setUp(self) -> None:
        """玩家与一名干员在同一场景，玩家的交互对象是干员"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.npc = self.world.chara(1, "干员")
        self.player.target_character_id = 1

    def test_action_effect_writes_whole_amounts(self) -> None:
        """少量S快结算 7 分钟：状态值与记录的量是整数"""
        change = game_type.CharacterStatusChange()
        effect = constant.settle_behavior_effect_data[
            constant_effect.BehaviorEffect.TARGET_ADD_SMALL_S_FEEL
        ]
        effect(0, 7, change, datetime.datetime(2025, 1, 1))
        written = self.npc.status_data[0]
        recorded = change.target_change[1].status_data[0]
        self.assertGreater(written, 0)
        self.assertIs(type(written), int)
        self.assertIs(type(recorded), int)

    def test_time_settlement_stays_exact(self) -> None:
        """灌肠中、苦痛刻印 1 的干员：5 次 1 分钟的苦痛等于 1 次 5 分钟的苦痛，且不是整数"""
        self.npc.dirty.a_clean = 1
        self.npc.dirty.enema_capacity = 1
        ca.ability(self.npc)[15] = 1
        for _ in range(5):
            realtime_settle.settle_conscious_continuous(1, 1)
        pieces = self.npc.status_data[17]
        self.npc.status_data[17] = 0
        realtime_settle.settle_conscious_continuous(1, 5)
        self.assertEqual(pieces, self.npc.status_data[17])
        self.assertNotEqual(pieces, int(pieces))
