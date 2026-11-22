# -*- coding: UTF-8 -*-
"""
角色的初次记录与历史周目履历（history.first_record、history.first_record_history）
================================================================================
- 占位时间 datetime(1, 1, 1) 编码为 None，解码还原为 datetime(1, 1, 1)（不漂移到 1-03-01）；
  真实游戏时间按分钟数编解码。
- get、part_sex、has_any_record、set、editing、clear。
- 新周目归档（carry_for_new_round / restore_for_new_round）与角色id 重映射（remap_ids）。
- adopt_old_save 搬走旧角色对象上的 first_record 与 first_record_history。
"""

import datetime

from Script.Core import game_type
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import first_record
from Script.Modules.gameplay_resolution import working
from tests.fast.base import FastTestCase


class FirstRecordTest(FastTestCase):
    """history.first_record 与 history.first_record_history 的读写与迁移"""

    def setUp(self) -> None:
        """载入内核模块并建出两名测试角色"""
        super().setUp()
        core.load(load_order.LOAD_ORDER)
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")

    def test_sentinel_datetime_preserved_and_real_time_roundtrips(self) -> None:
        """占位时间保持 0001-01-01，真实时间往返相等"""
        v0 = first_record.view(1)
        self.assertEqual(v0.first_kiss_time, datetime.datetime(1, 1, 1))
        self.assertEqual(v0.first_sex_time, datetime.datetime(1, 1, 1))
        self.assertFalse(first_record.has_any_record(1))

        now = game_time.now()
        with working.based_on(core.state()) as buf:
            first_record.set(1, first_meet=0, day_first_meet=0)
            with first_record.editing(1) as fr:
                fr.first_kiss_id = 0
                fr.first_kiss_time = now
                fr.first_kiss_place = ["中枢", "博士房间"]
                fr.first_part_sex_dict[6] = {
                    "id": 0,
                    "time": now,
                    "place": ["中枢", "博士房间"],
                    "posture": "测试",
                    "item": -1,
                }
                fr.first_h_mode_dict["group_sex"] = [now, ["中枢", "走廊"], "3"]
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertTrue(first_record.has_any_record(1, next_state))
        self.assertEqual(first_record.get(1, "first_meet", next_state), 0)
        part = first_record.part_sex(1, 6, next_state)
        self.assertIsNotNone(part)
        assert part is not None
        self.assertEqual(part["time"], now)
        v = first_record.view(1, next_state)
        self.assertEqual(v.first_kiss_time, now)
        self.assertEqual(v.first_sex_time, datetime.datetime(1, 1, 1))
        self.assertEqual(
            v.first_h_mode_dict["group_sex"], [now, ["中枢", "走廊"], "3"]
        )

    def test_new_round_archive_and_remap_ids(self) -> None:
        """新周目归档把有记录的当前履历收进历史周目；remap_ids 同时更新当前与历史"""
        now = game_time.now()
        with working.based_on(core.state()) as buf:
            with first_record.editing(1) as fr:
                fr.first_hand_in_hand = 10
                fr.first_kiss_id = 10
                fr.first_kiss_time = now
                fr.first_part_sex_dict[6] = {
                    "id": 10,
                    "time": now,
                    "place": ["中枢"],
                    "posture": "",
                    "item": -1,
                }
            effects = buf.effects()
        st1 = core.preview(core.state(), effects)
        carried = first_record.carry_for_new_round(
            {0: object(), 1: object()}, st1
        )

        with working.based_on(core.state()) as buf2:
            first_record.restore_for_new_round(1, 1, carried)
            first_record.set(1, first_kiss_id=10)
            first_record.remap_ids(1, {10: 99})
            effects2 = buf2.effects()
        st2 = core.preview(core.state(), effects2)
        self.assertEqual(first_record.get(1, "first_kiss_id", st2), 99)
        hist = first_record.history(1, st2)
        self.assertIn(1, hist)
        self.assertEqual(hist[1].first_hand_in_hand, 99)
        self.assertEqual(hist[1].first_part_sex_dict[6]["id"], 99)

    def test_adopt_old_save(self) -> None:
        """旧档角色对象上的 first_record 与 first_record_history 迁入内核后删除原属性"""
        now = game_time.now()
        chara = game_type.Character()
        old_fr = game_type.FIRST_RECORD()
        old_fr.first_meet = 0
        old_fr.first_kiss_id = 0
        old_fr.first_kiss_time = now
        old_hist = game_type.FIRST_RECORD()
        old_hist.first_sex_id = 1
        old_hist.first_sex_time = now
        vars(chara)["first_record"] = old_fr
        vars(chara)["first_record_history"] = {1: old_hist}
        with working.based_on(core.state()) as buf:
            first_record.adopt_old_save({"character_data": {1: chara}})
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertFalse(hasattr(chara, "first_record"))
        self.assertFalse(hasattr(chara, "first_record_history"))
        self.assertEqual(first_record.get(1, "first_meet", next_state), 0)
        self.assertEqual(first_record.get(1, "first_kiss_id", next_state), 0)
        hist = first_record.history(1, next_state)
        self.assertEqual(hist[1].first_sex_id, 1)
        self.assertEqual(hist[1].first_sex_time, now)

    def test_clear_inside_editing_persists(self) -> None:
        """editing 块内调用 clear 就地清空，并保留后续编辑"""
        with working.based_on(core.state()) as buf:
            first_record.set(1, first_kiss_id=0, first_sex_id=0)
            with first_record.editing(1) as fr:
                first_record.clear(1)
                self.assertEqual(fr.first_kiss_id, -1)
                self.assertEqual(fr.first_sex_id, -1)
                fr.first_meet = 0
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertEqual(first_record.get(1, "first_kiss_id", next_state), -1)
        self.assertEqual(first_record.get(1, "first_sex_id", next_state), -1)
        self.assertEqual(first_record.get(1, "first_meet", next_state), 0)
