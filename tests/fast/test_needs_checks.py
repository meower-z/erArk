# -*- coding: UTF-8 -*-
"""
自检读生理需求（body.needs）
============================
NUM-27（疲劳）、NUM-28（尿意非负）、NUM-29（尿意不超过 300）与 BODY-26（乳汁在 0 与上限之间）
各用一个合法值与一个越界值。合法值时这项检查不报这名干员，越界值时报。
NUM-27 的修复把越界的疲劳拉回 160，写进 body.needs，饥饿不动。
"""

from fractions import Fraction

from Script.Kernel import core
from Script.Modules.domains import needs
from Script.Modules.gameplay_resolution import working
from Script.Test.Static_Check import repair
from Script.Test.Static_Check.check_registry import get_all_checks
from tests.fast.base import FastTestCase

CASES: dict[str, tuple[str, int | Fraction, int | Fraction]] = {
    "NUM-27": ("tired", Fraction(319, 2), Fraction(321, 2)),
    "NUM-28": ("urine", 0, Fraction(-1, 3)),
    "NUM-29": ("urine", 300, Fraction(901, 3)),
    "BODY-26": ("milk", Fraction(399, 2), Fraction(401, 2)),
}
""" 检查编号到 (需求项, 合法值, 越界值)，乳汁上限设为 200 """


class NeedsChecksTest(FastTestCase):
    """四项检查各用一个合法值与一个越界值"""

    def setUp(self) -> None:
        """博士与一名干员，干员的乳汁上限 200。GameState 数据的读写记在 working.based_on(core.state()) 开的缓冲区里"""
        super().setUp()
        self.world.chara(0, "博士")
        self.chara = self.world.chara(1, "干员")
        self.chara.pregnancy.milk_max = 200
        self.enterContext(working.based_on(core.state()))

    def flagged(self, check_id: str) -> bool:
        """
        跑一项检查
        Keyword arguments:
        check_id -- 检查编号
        Return arguments:
        bool -- 这项检查报了这名干员（角色id 1）
        """
        _name, run = get_all_checks()[check_id]
        return any(f.involved_character_ids == [1] for f in run())

    def test_valid_and_violating_values(self) -> None:
        """合法值不报，越界值报"""
        for check_id, (stat, good, bad) in CASES.items():
            with self.subTest(check_id):
                needs.set(1, **{stat: good})
                self.assertFalse(self.flagged(check_id))
                needs.set(1, **{stat: bad})
                self.assertTrue(self.flagged(check_id))
                needs.set(1, **{stat: good})

    def test_repair_pulls_tired_back(self) -> None:
        """NUM-27 的修复把越界的疲劳拉回 160，饥饿不动"""
        needs.set(1, tired=Fraction(321, 2), hunger=Fraction(7, 3))
        repair.repair_fatigue_family_range(self.cache)
        stats = needs.of(1)
        self.assertEqual(
            (stats["tired"], stats["hunger"]), (160, Fraction(7, 3))
        )
