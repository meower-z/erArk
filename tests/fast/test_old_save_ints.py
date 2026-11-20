# -*- coding: UTF-8 -*-
"""
读档时的连续数值
================
- 默认值是 int 的字段，存档里的 int 与 Fraction 经 update_dict_with_default 补齐字段后值与类型都不变。
- 读档的 Reset 步骤 exact_stats 把存档里是 float 的连续数值换成相等的 Fraction（取 6 位小数），int 与 Fraction 不动。
  测到的数值有角色属性、状态值、污浊的三处精液量与当日理智消耗。
- 体力与气力的上限是 float 的旧存档，exact_stats 也把上限换成 Fraction，读档后第一次时间结算不出错。
- upgrade.adopt_v0 把旧存档角色对象上的疲劳、饥饿、尿意与乳汁写进 body.needs，float 换成相等的 Fraction，int 不动。
  这些属性从对象上删掉，供电策略表写进 base.power_strategy。
- 旧存档角色缺需求属性时，fill_v0_defaults 补上 0。角色缺妊娠数据时，重建后的妊娠数据没有乳汁，adopt_v0 把乳汁读成 0。
  罗德岛缺供电策略表时补空表。
"""

from fractions import Fraction

import datetime

from Script.Core import game_type, save_handle
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import needs, power
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import upgrade
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
        with working.based_on(core.state()):
            realtime_settle.character_aotu_change_value(
                0, now, now - datetime.timedelta(minutes=10)
            )
            self.assertGreater(needs.of(0)["hunger"], 0)
        self.assertEqual(
            [(type(v), v) for v in (npc.hit_point_max, npc.mana_point_max)],
            [(Fraction, Fraction(2001, 2)), (Fraction, Fraction(3201, 4))],
        )

    def test_v0_needs_become_exact(self) -> None:
        """
        旧存档角色对象上的 float 需求写进 body.needs 时换成相等的 Fraction，int 不动，属性删掉。
        供电策略表写进 base.power_strategy
        """
        self.world.chara(0, "博士")
        npc = self.world.chara(1, "干员")
        vars(npc).update(tired_point=12.5, hunger_point=240, urinate_point=0.25)
        vars(npc.pregnancy)["milk"] = 4.75
        island = game_type.Rhodes_Island()
        vars(island)["power_supply_strategy"] = {4: 1}
        loaded = {"character_data": {1: npc}, "rhodes_island": island}
        with working.based_on(core.state()):
            upgrade.adopt_v0(loaded)
            got = needs.of(1)
            strategy = power.strategy_of(4)
        self.assertEqual(strategy, 1)
        self.assertEqual(
            [
                (type(got[k]), got[k])
                for k in ("tired", "hunger", "urine", "milk")
            ],
            [
                (Fraction, Fraction(25, 2)),
                (int, 240),
                (Fraction, Fraction(1, 4)),
                (Fraction, Fraction(19, 4)),
            ],
        )
        self.assertFalse(hasattr(npc, "tired_point"))
        self.assertFalse(hasattr(npc.pregnancy, "milk"))

    def test_v0_defaults_and_missing_pregnancy(self) -> None:
        """缺需求属性的旧角色补上 0，重建后没有乳汁的妊娠数据读成乳汁 0，缺策略表的罗德岛补空表"""
        self.world.chara(0, "博士")
        npc = self.world.chara(1, "干员")
        rebuilt = vars(npc).pop("pregnancy")
        island = game_type.Rhodes_Island()
        loaded = {"character_data": {1: npc}, "rhodes_island": island}
        upgrade.fill_v0_defaults(loaded)
        npc.pregnancy = rebuilt
        with working.based_on(core.state()):
            upgrade.adopt_v0(loaded)
            got = needs.of(1)
            strategies = power.strategies()
        self.assertEqual(
            dict(got), {"tired": 0, "hunger": 0, "urine": 0, "milk": 0}
        )
        self.assertEqual(strategies, {})
