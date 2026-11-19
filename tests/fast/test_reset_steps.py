# -*- coding: UTF-8 -*-
"""
Reset 的步骤：save_load.reset 的输入钩子按 why["cause"] 依次运行步骤
====================================================================
- 读档：装存档、换精确值、投影角色、修补、回到场景面板；新周目：建新周目、投影角色、回到场景面板；新游戏：投影角色。
- 启动、改时钟与其他原因不运行任何步骤，换入的 GameState 原样交给内核。
"""

import sys
from types import MappingProxyType, SimpleNamespace
from unittest import mock

from Script.Core import constant, save_handle
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.gameplay_resolution import actions
from Script.Modules.save_load import reset
from tests.fast.base import FastTestCase


class ResetStepsTest(FastTestCase):
    """每种原因运行的步骤与顺序"""

    def setUp(self) -> None:
        """步骤的目标换成记下调用的替身（新周目面板不在快速层导入），载入游戏的模块"""
        super().setUp()
        self.calls: list[str] = []

        def record(name: str) -> mock.MagicMock:
            def call(*args: object) -> object:
                self.calls.append(name)
                return args[0] if name == "project" else None

            return mock.MagicMock(side_effect=call)

        for module, name in (
            (save_handle, "install_save"),
            (save_handle, "exact_stats"),
            (save_handle, "repair_installed"),
            (actions, "project"),
        ):
            self.enterContext(mock.patch.object(module, name, record(name)))
        panel = SimpleNamespace(setup=record("setup"))
        self.enterContext(
            mock.patch.dict(sys.modules, {"Script.UI.Panel.new_round": panel})
        )
        core.load(load_order.LOAD_ORDER)

    def run_cause(self, why: core.Data) -> list[str]:
        """
        以 why 换入一个没有角色的 GameState
        Keyword arguments:
        why -- 换入的原因
        Return arguments:
        list -- 运行过的步骤目标
        """
        self.calls.clear()
        self.cache.now_panel_id = constant.Panel.SEE_MAP
        clock = core.state().clock
        empty = core.GameState(
            clock, MappingProxyType({}), MappingProxyType({})
        )
        core.reset_state(empty, why)
        return self.calls

    def test_steps_per_cause(self) -> None:
        """每种原因运行的步骤，按表里的顺序"""
        cases: list[tuple[core.Data, list[str]]] = [
            (
                {"cause": "load", "save": "1"},
                ["install_save", "exact_stats", "project", "repair_installed"],
            ),
            (
                {"cause": "new_round", "inherit": {}},
                ["setup", "project"],
            ),
            ({"cause": "new_game"}, ["project"]),
            ({"cause": "boot"}, []),
            ({"cause": "clock"}, []),
            ({"cause": "unknown"}, []),
            ({}, []),
        ]
        for why, expected in cases:
            with self.subTest(str(why.get("cause"))):
                self.assertEqual(self.run_cause(why), expected)
                in_scene = self.cache.now_panel_id == constant.Panel.IN_SCENE
                self.assertEqual(
                    in_scene, why.get("cause") in ("load", "new_round")
                )

    def test_reset_runs_first(self) -> None:
        """reset 在 LOAD_ORDER 的最后，它的输入钩子在别的输入钩子之前运行"""
        self.assertIs(load_order.LOAD_ORDER[-1], reset)
