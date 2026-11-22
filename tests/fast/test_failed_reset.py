# -*- coding: UTF-8 -*-
"""
换态失败时内核状态保持不变
==========================
新周目的 setup 运行（计数并把玩家改名）后，后续步骤或输出钩子抛错：
异常向外传播，core.state() 仍是换态前的状态。
"""

import sys
from types import SimpleNamespace
from unittest import mock

from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.gameplay_resolution import actions, plan_queue
from Script.Modules.save_load import kernel_state
from tests.fast.base import FastTestCase
from Script.Modules.domains import identity


class FailedResetTest(FastTestCase):
    """新周目换入中途出错"""

    def setUp(self) -> None:
        """建出玩家，用计数并可改名的替身替换 new_round 面板，加载内核模块"""
        super().setUp()
        self.world.chara(0, "博士")
        self.setups = 0

        def setup(inherit: object) -> None:
            self.setups += 1
            identity.put(identity.Identity(0, name="新周目"))

        panel = SimpleNamespace(setup=setup)
        self.enterContext(
            mock.patch.dict(sys.modules, {"Script.UI.Panel.new_round": panel})
        )
        core.load(load_order.LOAD_ORDER)

    def check_failed(self) -> None:
        """新周目在 setup 运行后抛错，验证异常传播且内核状态与玩家姓名保持换态前的状态"""
        before = core.state()
        with self.assertRaises(RuntimeError):
            kernel_state.new_round({})
        self.assertIs(core.state(), before)
        self.assertEqual(self.setups, 1)
        self.assertEqual(identity.of(0).name, "博士")

    def test_failed_step(self) -> None:
        """setup 之后的投影步骤抛错"""
        broken = mock.Mock(side_effect=RuntimeError("project"))
        with mock.patch.object(actions, "project", broken):
            self.check_failed()

    def test_failed_output_hook(self) -> None:
        """步骤都跑完之后，一个输出钩子出错"""
        broken = mock.Mock(side_effect=RuntimeError("forget"))
        with mock.patch.object(plan_queue, "forget", broken):
            self.check_failed()
