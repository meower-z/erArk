# -*- coding: UTF-8 -*-
"""
换入失败时一切如旧：Reset 的钩子出错，内核状态与游戏缓存都回到换入前
==================================================================
新周目的步骤先改了缓存（周目数、玩家名、面板），之后的一步或一个输出钩子出错：
错误照常抛出，core.state() 还是换入前的那个，缓存里的值也都是换入前的。
"""

import sys
from types import SimpleNamespace
from unittest import mock

from Script.Core import constant
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.gameplay_resolution import actions, plan_queue
from Script.Modules.save_load import kernel_state
from tests.fast.base import FastTestCase


class FailedResetTest(FastTestCase):
    """新周目换入中途出错"""

    def setUp(self) -> None:
        """玩家在场；新周目的面板换成只改缓存的替身，载入游戏的模块"""
        super().setUp()
        self.world.chara(0, "博士")

        def setup(inherit: object) -> None:
            self.cache.game_round += 1
            self.cache.character_data[0].name = "新周目"

        panel = SimpleNamespace(setup=setup)
        self.enterContext(
            mock.patch.dict(sys.modules, {"Script.UI.Panel.new_round": panel})
        )
        core.load(load_order.LOAD_ORDER)
        self.cache.now_panel_id = constant.Panel.SEE_MAP

    def check_failed(self) -> None:
        """新周目出错抛出，内核状态与缓存都是换入前的"""
        before = core.state()
        game_round = self.cache.game_round
        with self.assertRaises(RuntimeError):
            kernel_state.new_round({})
        self.assertIs(core.state(), before)
        self.assertEqual(self.cache.game_round, game_round)
        self.assertEqual(self.cache.character_data[0].name, "博士")
        self.assertEqual(self.cache.now_panel_id, constant.Panel.SEE_MAP)

    def test_failed_step(self) -> None:
        """改过缓存之后的投影一步出错"""
        broken = mock.Mock(side_effect=RuntimeError("project"))
        with mock.patch.object(actions, "project", broken):
            self.check_failed()

    def test_failed_output_hook(self) -> None:
        """步骤都跑完之后，一个输出钩子出错"""
        broken = mock.Mock(side_effect=RuntimeError("forget"))
        with mock.patch.object(plan_queue, "forget", broken):
            self.check_failed()
