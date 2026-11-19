# -*- coding: UTF-8 -*-
"""
读档时的连续数值
================
- 默认值是 int 的字段，存档里的 int 与 Fraction 经 update_dict_with_default 补齐字段后值与类型都不变。
- 读档的 Reset 步骤 exact_stats 把存档里是 float 的连续数值换成相等的 Fraction（取 6 位小数），
  int 与 Fraction 不动：角色属性、状态值、污浊的三处精液量、奶量、当日理智消耗。
- 体力与气力的上限是 float 的旧存档：exact_stats 也把上限换成 Fraction，
  读档后第一次时间结算（饥饿按体力气力与上限之比）不出错。
"""

from fractions import Fraction

import datetime

from Script.Core import game_type, save_handle
from Script.Design import game_time
from Script.Settle import realtime_settle
from tests.fast.base import FastTestCase


class OldSaveIntsTest(FastTestCase):
    """读档时连续数值的类型"""

    def test_defaults_keep_int_and_fraction(self) -> None:
        """存档里的 int 与 Fraction 补齐字段后值与类型不变，缺的字段取默认值 0"""
        loaded = game_type.Character()
        loaded.hit_point = 7
        loaded.sanity_point = Fraction(10, 3)
        del loaded.drunk_point
        save_handle.update_dict_with_default(
            loaded.__dict__, game_type.Character().__dict__
        )
        got = [
            (type(v), v)
            for v in (loaded.hit_point, loaded.sanity_point, loaded.drunk_point)
        ]
        self.assertEqual(got, [(int, 7), (Fraction, Fraction(10, 3)), (int, 0)])

    def test_exact_stats_turns_floats_exact(self) -> None:
        """旧存档里的 float（经 vars 写入，同 pickle 读回）换成相等的 Fraction，int 与 Fraction 原样留下"""
        npc = self.world.chara(0, "博士")
        vars(npc).update(
            eja_point=12.5,
            hit_point=900,
            sanity_point=Fraction(1, 3),
            status_data={1: 0.25, 2: 4},
        )
        vars(npc.dirty)["absorbed_total_semen"] = 3.5
        npc.dirty.body_semen = {0: ["头发", 1.5, 0, 2]}
        npc.dirty.semen_flow = [
            {
                "source": {"type": "body", "id": 0},
                "targets": [
                    {"type": "body", "id": 1, "remaining_volume": 2.25}
                ],
            }
        ]
        vars(npc.pregnancy)["milk"] = 4.75
        vars(npc.pl_ability)["today_sanity_point_cost"] = 0.1
        save_handle.exact_stats()
        got = [
            npc.eja_point,
            npc.hit_point,
            npc.sanity_point,
            npc.status_data[1],
            npc.status_data[2],
            npc.dirty.absorbed_total_semen,
            npc.dirty.body_semen[0][1],
            npc.dirty.semen_flow[0]["targets"][0]["remaining_volume"],
            npc.pregnancy.milk,
            npc.pl_ability.today_sanity_point_cost,
        ]
        want = [
            Fraction(25, 2),
            900,
            Fraction(1, 3),
            Fraction(1, 4),
            4,
            Fraction(7, 2),
            Fraction(3, 2),
            Fraction(9, 4),
            Fraction(19, 4),
            Fraction(1, 10),
        ]
        self.assertEqual(
            [(type(v), v) for v in got], [(type(v), v) for v in want]
        )

    def test_float_maxima_settle(self) -> None:
        """体力与气力上限是 float：换成相等的 Fraction，之后的时间结算不出错"""
        npc = self.world.chara(0, "博士")
        vars(npc).update(hit_point_max=1000.5, mana_point_max=800.25)
        save_handle.exact_stats()
        now = game_time.now()
        npc.behavior.start_time = now - datetime.timedelta(minutes=10)
        npc.behavior.duration = 10
        realtime_settle.character_aotu_change_value(
            0, now, now - datetime.timedelta(minutes=10)
        )
        self.assertGreater(npc.hunger_point, 0)
        self.assertEqual(
            [(type(v), v) for v in (npc.hit_point_max, npc.mana_point_max)],
            [(Fraction, Fraction(2001, 2)), (Fraction, Fraction(3201, 4))],
        )
