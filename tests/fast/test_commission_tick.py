# -*- coding: UTF-8 -*-
"""
外勤委托在 5 分钟一次的 Tick 里结算
==================================
玩家睡着、没有任何选择时，到期的委托在到期时刻之后的第一次 Tick 完成，之前的 Tick 不完成它。
"""

import datetime
from types import MappingProxyType
from unittest import mock

from Script.Core import constant
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import time_hooks
from Script.Settle import realtime_settle
from tests.fast.base import FastTestCase

COMMISSION = 2
""" 采集周围的药草：1 人，奖励资源 """


class CommissionTickTest(FastTestCase):
    """委托完成的时刻"""

    def setUp(self) -> None:
        """玩家从开局时刻起睡 10 小时；只扫描 Tick 与 NewDay，逐角色的数值结算换成空操作"""
        super().setUp()
        self.enterContext(
            mock.patch.object(
                core,
                "_events",
                [
                    "gameplay_resolution.time_hooks.Tick",
                    "gameplay_resolution.time_hooks.NewDay",
                ],
            )
        )
        self.enterContext(
            mock.patch.object(realtime_settle, "character_aotu_change_value")
        )
        self.enterContext(
            mock.patch.object(
                realtime_settle, "change_character_persistent_state"
            )
        )
        player = self.world.chara(0, "博士")
        player.behavior.behavior_id = constant.Behavior.SLEEP
        player.behavior.duration = 600
        self.base = core.state().clock
        action = core.Action("0", core.idle.name, None, self.base, 600)
        core.load((time_hooks,))
        core.reset_state(
            core.GameState(
                self.base,
                MappingProxyType(
                    {"0": core.Character(action, MappingProxyType({}))}
                ),
                MappingProxyType(
                    {
                        time_hooks.TICKED: self.base,
                        time_hooks.SETTLED_DAY: game_time.day(self.base),
                    }
                ),
            )
        )
        self.action = action

    def test_due_commission_finishes_in_next_tick(self) -> None:
        """8 分钟后到期：第 5 分钟的 Tick 不完成，第 10 分钟的 Tick 完成，玩家的睡觉没有结束、没有选择"""
        ongoing = self.cache.rhodes_island.ongoing_field_commissions
        ongoing[COMMISSION] = [
            [],
            game_time.at(self.base) + datetime.timedelta(minutes=8),
            [],
        ]
        finished_at = None
        clocks = []
        for __ in range(6):
            core.step()
            clocks.append(core.state().clock)
            if finished_at is None and COMMISSION not in ongoing:
                finished_at = core.state().clock
        self.assertEqual(
            clocks, [self.base + m for m in (5, 5, 10, 10, 15, 15)]
        )
        self.assertEqual(finished_at, self.base + 10)
        self.assertIn(
            COMMISSION, self.cache.rhodes_island.finished_field_commissions_set
        )
        self.assertEqual(core.state().characters["0"].action, self.action)
