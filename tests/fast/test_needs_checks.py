# -*- coding: UTF-8 -*-
"""
自检读 body.needs 与 body.pregnancy
===================================
NUM-27（疲劳、熟睡、醉酒）、NUM-28（尿意非负）、NUM-29（尿意不超过 300）、BODY-26（乳汁在 0 与上限之间）、
NUM-20（体力在 1 与上限之间）、NUM-21（气力在 0 与上限之间）、NUM-22（理智在 0 与上限之间）、
MIND-24（熟睡在 0 与 100 之间）、NUM-30（欲望非负）与 SUPP-05（愤怒非负）各用一个合法值与一个越界值。
合法值时这项检查不报这名干员，越界值时报。
BODY-26 另有一例：乳汁上限（body.pregnancy）低于乳汁时报。
NUM-27 的修复把越界的疲劳拉回 160，写进 body.needs，饥饿不动。SUPP-05 的修复把负的愤怒拉回 0。
"""

from fractions import Fraction

from Script.Kernel import core
from Script.Modules.domains import needs, pregnancy
from Script.Modules.gameplay_resolution import working
from Script.Test.Static_Check import repair
from Script.Test.Static_Check.check_registry import get_all_checks
from tests.fast.base import FastTestCase
from tests import kernel_data

CASES: list[tuple[str, str, int | Fraction, int | Fraction]] = [
    ("NUM-27", "tired", Fraction(319, 2), Fraction(321, 2)),
    ("NUM-27", "sleep", 100, Fraction(301, 3)),
    ("NUM-27", "drunk", 0, Fraction(-1, 2)),
    ("NUM-28", "urine", 0, Fraction(-1, 3)),
    ("NUM-29", "urine", 300, Fraction(901, 3)),
    ("BODY-26", "milk", Fraction(399, 2), Fraction(401, 2)),
    ("NUM-20", "hit", 100, Fraction(201, 2)),
    ("NUM-21", "mana", 0, Fraction(-1, 3)),
    ("NUM-22", "sanity", 0, Fraction(1, 3)),
    ("MIND-24", "sleep", 0, 101),
    ("NUM-30", "desire", 0, -1),
    ("SUPP-05", "angry", 0, -1),
]
""" (检查编号, body.needs 的项, 合法值, 越界值)。干员的体力与气力上限 100，理智上限 0，乳汁上限 200 """


class NeedsChecksTest(FastTestCase):
    """四项检查各用一个合法值与一个越界值"""

    def setUp(self) -> None:
        """博士与一名干员，干员的乳汁上限 200。GameState 数据的读写记在 working.based_on(core.state()) 开的缓冲区里"""
        super().setUp()
        self.world.chara(0, "博士")
        self.chara = self.world.chara(1, "干员")
        kernel_data.set_milk_max(self.chara.cid, 200)
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
        for check_id, stat, good, bad in CASES:
            with self.subTest(check_id, stat=stat):
                needs.set(1, **{stat: good})
                self.assertFalse(self.flagged(check_id))
                needs.set(1, **{stat: bad})
                self.assertTrue(self.flagged(check_id))
                needs.set(1, **{stat: good})

    def test_milk_above_its_max(self) -> None:
        """乳汁 150：乳汁上限 200 时 BODY-26 不报，上限改成 149 时报"""
        needs.set(1, milk=150)
        self.assertFalse(self.flagged("BODY-26"))
        pregnancy.set_milk_max(1, 149)
        self.assertTrue(self.flagged("BODY-26"))

    def test_repair_pulls_angry_back(self) -> None:
        """SUPP-05 的修复把愤怒 -3 拉回 0，写进 body.needs"""
        needs.set(1, angry=-3)
        repair.repair_angry_point_lower_bound()
        self.assertEqual(needs.of(1)["angry"], 0)

    def test_repair_pulls_tired_back(self) -> None:
        """NUM-27 的修复把越界的疲劳拉回 160，饥饿不动"""
        needs.set(1, tired=Fraction(321, 2), hunger=Fraction(7, 3))
        repair.repair_fatigue_family_range()
        stats = needs.of(1)
        self.assertEqual(
            (stats["tired"], stats["hunger"]), (160, Fraction(7, 3))
        )
