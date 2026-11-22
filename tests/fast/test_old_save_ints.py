# -*- coding: UTF-8 -*-
"""
读档时的连续数值
================
- 默认值是 int 的字段，存档里的 int 与 Fraction 经 update_dict_with_default 补齐字段后值与类型都不变。
- 读档时 status.adopt_old_save 与 Reset 步骤 exact_stats 把存档里是 float 的连续数值换成相等的 Fraction（取 6 位小数），
  int 与 Fraction 不动。状态值由 status.adopt_old_save 换。测到的其余数值有角色属性、污浊的三处精液量与当日理智消耗，
  由 exact_stats 换。
- 体力与气力的上限是 float 的旧存档，upgrade.adopt_pickled 把上限换成相等的 Fraction，读档后第一次时间结算不出错。
- upgrade.adopt_pickled 把版本 3 之前的角色对象上的体力、气力、理智与它们的上限，愤怒、熟睡、欲望、醉酒写进
  body.needs，乳汁上限写进 body.pregnancy，再从对象上删掉这些属性与 last_hunger_time。
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
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import upgrade
from Script.Settle import realtime_settle
from Script.Modules.domains import (
    needs,
    player_ability,
    power,
    pregnancy,
    status,
)
from tests import kernel_data
from tests.fast.base import FastTestCase


class OldSaveIntsTest(FastTestCase):
    """读档时连续数值的类型"""

    def test_defaults_keep_int_and_fraction(self) -> None:
        """存档里的 int 与 Fraction 补齐字段后值与类型不变，缺的字段取默认值 0"""
        loaded = game_type.Character()
        loaded.eja_point = 7
        loaded.semen_point = Fraction(10, 3)
        del loaded.tem_extra_semen_point
        save_handle.update_dict_with_default(
            loaded.__dict__, game_type.Character().__dict__
        )
        got = [
            (type(v), v)
            for v in (
                loaded.eja_point,
                loaded.semen_point,
                loaded.tem_extra_semen_point,
            )
        ]
        self.assertEqual(got, [(int, 7), (Fraction, Fraction(10, 3)), (int, 0)])

    def test_exact_stats_turns_floats_exact(self) -> None:
        """经 vars 写入的 float 由 status.adopt_old_save 与 exact_stats 换成相等的 Fraction，int 与 Fraction 不动"""
        npc = self.world.chara(0, "博士")
        vars(npc).update(
            eja_point=12.5,
            semen_point=Fraction(1, 3),
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
        pa = game_type.PLAYER_ABILITY()
        vars(pa)["today_sanity_point_cost"] = 0.1
        vars(npc)["pl_ability"] = pa
        loaded = {"character_data": {npc.cid: npc}}
        kernel_data.written(status.adopt_old_save, loaded)
        kernel_data.written(save_handle.exact_stats)
        with working.based_on(core.state()):
            player_ability.adopt_old_save({"character_data": {0: npc}})
            adopted_cost = player_ability.get(0, "today_sanity_point_cost")
        got = [
            npc.eja_point,
            npc.semen_point,
            status.of(npc.cid)[1],
            status.of(npc.cid)[2],
            npc.dirty.absorbed_total_semen,
            npc.dirty.body_semen[0][1],
            npc.dirty.semen_flow[0]["targets"][0]["remaining_volume"],
            adopted_cost,
        ]
        want = [
            Fraction(25, 2),
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
        vars(npc).update(
            hit_point=500,
            hit_point_max=1000.5,
            mana_point_max=800.25,
            pregnancy=game_type.PREGNANCY(),
        )
        now = game_time.now()
        npc.behavior.start_time = now - datetime.timedelta(minutes=10)
        npc.behavior.duration = 10
        with working.based_on(core.state()):
            upgrade.adopt_pickled({"character_data": {0: npc}})
            realtime_settle.character_aotu_change_value(
                0, now, now - datetime.timedelta(minutes=10)
            )
            self.assertGreater(needs.of(0)["hunger"], 0)
            got = needs.of(0)
        self.assertEqual(
            [(type(got[k]), got[k]) for k in ("hit_max", "mana_max")],
            [(Fraction, Fraction(2001, 2)), (Fraction, Fraction(3201, 4))],
        )

    def test_pickled_stats_become_exact(self) -> None:
        """
        版本 3 之前的角色对象上的十项写进 body.needs：PICKLED_EXACT 里的 float 换成相等的 Fraction，
        int、Fraction 与别的项原样，对象上没有的欲望读 0。乳汁上限 230 写进 body.pregnancy。
        之后对象上没有体力、熟睡与 last_hunger_time，妊娠数据上没有乳汁上限
        """
        self.world.chara(0, "博士")
        npc = self.world.chara(1, "干员")
        vars(npc).update(
            hit_point=900,
            hit_point_max=1000,
            mana_point=12.5,
            mana_point_max=800,
            sanity_point=Fraction(1, 3),
            sanity_point_max=7,
            angry_point=20,
            sleep_point=0.25,
            drunk_point=Fraction(5, 2),
            last_hunger_time=datetime.datetime(1, 1, 1),
        )
        old_preg = game_type.PREGNANCY()
        vars(old_preg)["milk_max"] = 230
        vars(npc)["pregnancy"] = old_preg
        with working.based_on(core.state()):
            upgrade.adopt_pickled({"character_data": {1: npc}})
            got = needs.of(1)
            milk_max = pregnancy.milk_max(1)
        want = {
            "hit": 900,
            "hit_max": 1000,
            "mana": Fraction(25, 2),
            "mana_max": 800,
            "sanity": Fraction(1, 3),
            "sanity_max": 7,
            "angry": 20,
            "sleep": Fraction(1, 4),
            "desire": 0,
            "drunk": Fraction(5, 2),
        }
        self.assertEqual(
            {k: (type(v), v) for k, v in got.items() if k in want},
            {k: (type(v), v) for k, v in want.items()},
        )
        self.assertEqual(milk_max, 230)
        left = {"hit_point", "sleep_point", "last_hunger_time"} & set(vars(npc))
        self.assertEqual(left, set())
        self.assertFalse(hasattr(old_preg, "milk_max"))

    def test_v0_needs_become_exact(self) -> None:
        """
        旧存档角色对象上的 float 需求写进 body.needs 时换成相等的 Fraction，int 不动，属性删掉。
        供电策略表写进 base.power_strategy
        """
        self.world.chara(0, "博士")
        npc = self.world.chara(1, "干员")
        vars(npc).update(tired_point=12.5, hunger_point=240, urinate_point=0.25)
        old_preg = game_type.PREGNANCY()
        vars(old_preg)["milk"] = 4.75
        vars(npc)["pregnancy"] = old_preg
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
        self.assertFalse(hasattr(old_preg, "milk"))

    def test_v0_defaults_and_missing_pregnancy(self) -> None:
        """缺需求属性的旧角色补上 0，重建后没有乳汁的妊娠数据读成乳汁 0，缺策略表的罗德岛补空表"""
        self.world.chara(0, "博士")
        npc = self.world.chara(1, "干员")
        rebuilt = game_type.PREGNANCY()
        island = game_type.Rhodes_Island()
        loaded = {"character_data": {1: npc}, "rhodes_island": island}
        upgrade.fill_v0_defaults(loaded)
        vars(npc)["pregnancy"] = rebuilt
        with working.based_on(core.state()):
            upgrade.adopt_v0(loaded)
            got = needs.of(1)
            strategies = power.strategies()
        self.assertEqual(
            {k: got[k] for k in ("tired", "hunger", "urine", "milk")},
            {"tired": 0, "hunger": 0, "urine": 0, "milk": 0},
        )
        self.assertEqual(strategies, {})
