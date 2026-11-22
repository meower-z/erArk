# -*- coding: UTF-8 -*-
"""
存档往返（版本不低于 18）：名册、妊娠与养成状态
===============================================
开一局新游戏，写入名册（在编、禁用、已用姓名）、成年干员的妊娠数据与养成数据，
真实写盘再读档，核对 save.json 版本等于 upgrade.CURRENT 且当前版本不低于 18、
目录里只有 save.json、三个领域状态往返一致、继续推进后再次写盘的 save.json（除 head 外）稳定。
"""

import importlib
import json
import os
import tempfile
from unittest import mock

from tests import kernel_data as kd
from tests.slow.base import SlowTestCase

SLOT = "v18_roster_pregnancy_growth"


class RosterPregnancyGrowthSaveTest(SlowTestCase):
    """新游戏写入名册、妊娠与养成数据后的存档往返与续跑（版本不低于 18）"""

    def test_v18_round_trip_and_continuation(self) -> None:
        """写盘、读档、核对字段与续跑"""
        from Script.Core import save_handle
        from Script.Design import game_time
        from Script.Kernel import core
        from Script.Modules.domains import growth, pregnancy, roster
        from Script.Modules.save_load import index, upgrade
        from Script.Core import constant

        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))

        adult_id = min(cid for cid in roster.active_sorted() if cid != 0)
        now = game_time.now()
        with kd.writing():
            roster.forbid(999001)
            roster.add_name("测试留档名")
            pregnancy.set_milk_max(adult_id, 245)
            with pregnancy.editing(adult_id) as p:
                p.reproduction_period = 4
                p.fertilization_time = now
                p.acceleration_days = 2.5
                p.prenatal_point = 1.5
            with growth.editing(adult_id) as g:
                assert g is not None
                g.attend_class_count = 7
                g.care_point = 3.5
                g.selected_course = {0: {1: [0, "理论教室一"]}}
                g.event_history = {"通用1": {"time": now, "choice": 0}}
                g.report_card_history = [
                    {
                        "year": now.year,
                        "month": now.month,
                        "attend": 7,
                        "absent": 0,
                        "rate": 100,
                        "level_change": {41: [0, 1]},
                        "top_ability": 41,
                        "top_level": 1,
                        "grade": 1,
                        "reason": "",
                    }
                ]

        expected_active = roster.active_sorted()
        expected_forbidden = roster.forbidden()
        expected_names = roster.names()
        expected_preg = pregnancy.of(adult_id)
        expected_growth = growth.of(adult_id)
        assert expected_growth is not None

        save_handle.establish_save(SLOT)
        save_dir = os.path.join(folder, SLOT)
        with open(
            os.path.join(save_dir, index.SAVE_FILE), encoding="utf-8"
        ) as f:
            first_file = json.load(f)
        self.assertEqual(first_file["version"], upgrade.CURRENT)
        self.assertGreaterEqual(upgrade.CURRENT, 18)

        self.assertEqual(os.listdir(save_dir), [index.SAVE_FILE])

        save_handle.input_load_save(SLOT)
        self.assertEqual(roster.active_sorted(), expected_active)
        self.assertEqual(roster.forbidden(), expected_forbidden)
        self.assertEqual(roster.names(), expected_names)
        self.assertEqual(pregnancy.milk_max(adult_id), 245)
        self.assertEqual(vars(pregnancy.of(adult_id)), vars(expected_preg))
        got_g = growth.of(adult_id)
        assert got_g is not None
        self.assertEqual(vars(got_g), vars(expected_growth))

        save_handle.establish_save(SLOT)
        with open(
            os.path.join(save_dir, index.SAVE_FILE), encoding="utf-8"
        ) as f:
            second_file = json.load(f)
        for payload in (first_file, second_file):
            payload.pop("head")
        self.assertEqual(second_file, first_file)

        # 读档后正常推进一步
        self.instruct(constant.Instruct.WAIT)
        self.assertGreater(core.state().clock, 0)
        self.assertEqual(roster.forbidden(), expected_forbidden)
        self.assertEqual(pregnancy.milk_max(adult_id), 245)
        self.assertIsNotNone(
            importlib.import_module("Script.Modules.domains.growth").of(
                adult_id
            )
        )
