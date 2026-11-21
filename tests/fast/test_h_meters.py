# -*- coding: UTF-8 -*-
"""
角色的射精/精液数值与全局射精位置（h.meters、h.shoot_position）
==============================================================
- 默认读 DEFAULT（全 0），射精位置默认 0。
- add 与 set 经 h.meters 规则套用，保留 int 与 Fraction 类型，按 min/max 夹住。
- adopt_old_save 搬走旧角色对象上的五个属性并把 float 转为精确值；
  adopt_world 搬走旧缓存上的 shoot_position，版本低于 20 且缺失时计 1 条更新。
- 存档版本 CURRENT 为 20，STEPS 含 19。
"""

from fractions import Fraction

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import h_meters
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import upgrade
from tests.fast.base import FastTestCase


class HMetersTest(FastTestCase):
    """h.meters 与 h.shoot_position 的读写、规则与旧档导入"""

    def setUp(self) -> None:
        """载入内核模块，建出玩家与一名干员"""
        super().setUp()
        core.load(load_order.LOAD_ORDER)
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")

    def test_save_version_is_20(self) -> None:
        """存档版本升到 20，STEPS 含 19"""
        self.assertGreaterEqual(upgrade.CURRENT, 20)
        self.assertIn(19, upgrade.STEPS)

    def test_defaults_and_fold_exact_num(self) -> None:
        """默认值全 0；add 与 set 经规则套用后保留 Fraction 与 int 类型"""
        self.assertEqual(h_meters.of(0), h_meters.DEFAULT)
        self.assertEqual(h_meters.shoot_position(), 0)
        with working.based_on(core.state()) as buf:
            h_meters.set(0, eja_max=1000, semen_max=100, semen=50)
            h_meters.add(0, "eja", Fraction(5, 2), max=1000)
            h_meters.add(0, "semen", Fraction(1, 4), max=100)
            h_meters.add(0, "extra_semen", 30)
            h_meters.set_shoot_position(2)
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        got = h_meters.of(0, next_state)
        self.assertEqual(got["eja_max"], 1000)
        self.assertEqual(got["eja"], Fraction(5, 2))
        self.assertIs(type(got["eja"]), Fraction)
        self.assertEqual(got["semen"], Fraction(201, 4))
        self.assertIs(type(got["semen"]), Fraction)
        self.assertEqual(got["extra_semen"], 30)
        self.assertEqual(h_meters.shoot_position(next_state), 2)

    def test_clamp_bounds_and_unknown_op(self) -> None:
        """add 的 min 与 max 夹住结果；未知操作名报 ValueError"""
        with working.based_on(core.state()) as buf:
            h_meters.set(0, eja=10, semen=95, semen_max=100)
            h_meters.add(0, "eja", -50, min=0)
            h_meters.add(0, "semen", 20, max=100)
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        got = h_meters.of(0, next_state)
        self.assertEqual(got["eja"], 0)
        self.assertIs(type(got["eja"]), int)
        self.assertEqual(got["semen"], 100)
        with self.assertRaises(ValueError):
            h_meters.fold({"eja_max": 0}, "mul", {})

    def test_adopt_old_save_and_world(self) -> None:
        """旧档角色对象上的五个属性与缓存上的 shoot_position 迁入内核后删除原属性"""
        chara = game_type.Character()
        vars(chara).update(
            eja_point_max=1000,
            eja_point=12.5,
            semen_point_max=120,
            semen_point=Fraction(7, 3),
            tem_extra_semen_point=40,
        )
        loaded: dict[str, object] = {
            "character_data": {0: chara},
            "shoot_position": 6,
        }
        with working.based_on(core.state()) as buf:
            self.assertEqual(h_meters.adopt_world(loaded, 14), 0)
            self.assertEqual(h_meters.adopt_old_save(loaded), 0)
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertNotIn("shoot_position", loaded)
        for attr in (
            "eja_point_max",
            "eja_point",
            "semen_point_max",
            "semen_point",
            "tem_extra_semen_point",
        ):
            self.assertFalse(hasattr(chara, attr))
        got = h_meters.of(0, next_state)
        self.assertEqual(
            (got["eja_max"], got["eja"], got["semen_max"], got["semen"]),
            (1000, Fraction(25, 2), 120, Fraction(7, 3)),
        )
        self.assertIs(type(got["eja"]), Fraction)
        self.assertEqual(got["extra_semen"], 40)
        self.assertEqual(h_meters.shoot_position(next_state), 6)

    def test_adopt_world_missing_count_by_version(self) -> None:
        """缺少 shoot_position 时，20 之前计 1 条更新，20 起计 0"""
        with working.based_on(core.state()):
            self.assertEqual(h_meters.adopt_world({}, 19), 1)
            self.assertEqual(h_meters.adopt_world({}, 20), 0)
