# -*- coding: UTF-8 -*-
"""
确认招募在行动开始时招募：选择只定下行动，新干员在 5 分钟等待开始时加入
====================================================================
- 有一名待确认的干员、宿舍有空：确认招募定下玩家 5 分钟的等待（开始代码 recruit）；选择期间缓存不变；
  行动开始后她在本局的干员里，待确认列表空了。
- 宿舍已满：不定下行动，缓存不变。
"""

import importlib
from collections.abc import Mapping
from typing import cast
from unittest import mock

from tests import kernel_data
from tests.slow.base import SlowTestCase


class RecruitAtStartTest(SlowTestCase):
    """确认招募"""

    def setUp(self) -> None:
        """开新游戏，放一名可招募的干员进待确认列表，记下玩家开始的行动"""
        super().setUp()
        from Script.Kernel import core
        from Script.Modules.domains import recruit
        from Script.UI.Panel import recruit_panel
        from tests import kernel_data

        self.new_id = recruit_panel.find_recruitable_npc()[0]
        kernel_data.put(recruit.set_pending, {self.new_id})
        self.started: list[core.Action] = []
        saved = core._bodies["kernel.StartAction"]

        def spy(act: core.Action) -> core.Effects:
            if act.who == "0":
                self.started.append(act)
            return saved(act)

        core._bodies["kernel.StartAction"] = spy
        self.addCleanup(core._bodies.__setitem__, "kernel.StartAction", saved)

    def confirm(self) -> bool:
        """
        玩家点下确认招募
        Return arguments:
        bool -- 选择期间（定下行动之前）缓存的指纹变了
        """
        from Script.Core import constant
        from Script.System.Instruct_System import handle_instruct
        from tests import pick_guard, world

        changed: list[bool] = []

        def pick() -> None:
            before = pick_guard.fingerprint()
            try:
                handle_instruct.handle_instruct(
                    constant.Instruct.CONFIM_RECRUIT
                )
            finally:
                changed.append(pick_guard.fingerprint() != before)

        world.act(pick)
        return changed[0]

    def test_recruit_joins_at_start(self) -> None:
        """选择期间缓存不变；5 分钟的等待开始后新干员加入，待确认列表空了"""
        from Script.Core import constant
        from Script.Modules.domains import recruit

        changed = self.confirm()
        self.assertFalse(changed, "选择期间招募已经写了缓存")
        started = [
            (
                cast(Mapping[str, object], a.action_data)["behavior_id"],
                a.duration,
            )
            for a in self.started
        ]
        self.assertEqual(started, [(constant.Behavior.WAIT, 5)])
        self.assertIn(self.new_id, kernel_data.domain("roster").active())
        self.assertEqual(recruit.pending(), set())

    def test_full_dormitory_commits_nothing(self) -> None:
        """宿舍已满：没有行动，缓存不变，新干员没有加入"""
        facility = importlib.import_module("Script.Modules.domains.facility")
        full = len(kernel_data.domain("roster").active())
        self.enterContext(
            mock.patch.object(facility, "people_max", lambda: full)
        )
        changed = self.confirm()
        self.assertFalse(changed)
        self.assertEqual(self.started, [])
        self.assertNotIn(self.new_id, kernel_data.domain("roster").active())
