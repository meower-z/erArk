# -*- coding: UTF-8 -*-
"""
生理需求的 add 操作与直接用 min、max 夹住同值同类型
===================================================
直接写是 min(x + d, 上限) 与 max(x - d, 0)。数值是 int、Fraction、分母为 1 的 Fraction 或 int 与 Fraction 混用时，
结果在界以内、正好在界上、越过界，fold 都与直接写的值相等、类型相同。set 只换给出的项，没有的操作名报错。
"""

from fractions import Fraction
from typing import cast

from Script.Core.num import Num
from Script.Kernel import core
from Script.Modules.domains import needs
from tests.fast.base import FastTestCase

KINDS: dict[str, tuple[Num, Num, Num]] = {
    "int": (230, 5, 240),
    "fraction": (Fraction(479, 2), Fraction(1, 3), Fraction(481, 2)),
    "fraction over one": (Fraction(230, 1), Fraction(5, 1), Fraction(240, 1)),
    "mixed": (230, Fraction(7, 72), 240),
}
""" 每种数值：(当前值, 每次加的量, 上限) """


def needs_with(**values: Num) -> core.JSON:
    """
    默认需求换上给出的项
    Keyword arguments:
    values -- 需求项到值
    Return arguments:
    JSON -- 需求
    """
    return cast(core.JSON, {**needs.DEFAULT, **values})


def added(x: Num, by: Num, **bounds: Num) -> Num:
    """
    在疲劳为 x 的需求上做一次 add，返回新的疲劳
    Keyword arguments:
    x -- 当前疲劳
    by -- 加的量
    bounds -- max 与 min
    Return arguments:
    Num -- 新的疲劳
    """
    new = needs.fold(
        needs_with(tired=x), "add", {"stat": "tired", "by": by, **bounds}
    )
    assert isinstance(new, dict)
    value = new["tired"]
    assert isinstance(value, (int, Fraction))
    return value


class NeedsFoldTest(FastTestCase):
    """fold 的结果与直接写的结果逐一比较"""

    def assertSame(self, got: Num, want: Num) -> None:
        """
        值相等且类型相同
        Keyword arguments:
        got -- fold 的结果
        want -- 直接写的结果
        """
        self.assertEqual(got, want)
        self.assertIs(type(got), type(want))

    def test_capped_add(self) -> None:
        """加量后按上限夹住：低于、正好、高于上限"""
        for name, (start, by, cap) in KINDS.items():
            for steps in (0, 1, 2, 3, 100):
                with self.subTest(name, steps=steps):
                    x = start + by * steps - by
                    self.assertSame(added(x, by, max=cap), min(x + by, cap))
            with self.subTest(name, at="cap"):
                x = cap - by
                self.assertSame(added(x, by, max=cap), min(x + by, cap))

    def test_floored_subtract(self) -> None:
        """减量后按 0 夹住：高于、正好、低于 0"""
        for name, (_, by, _) in KINDS.items():
            for x in (by * 3, by, 0):
                with self.subTest(name, x=x):
                    self.assertSame(added(x, -by, min=0), max(x - by, 0))

    def test_set_replaces_given_stats(self) -> None:
        """set 只换给出的项，别的项不动"""
        new = needs.fold(
            needs_with(milk=Fraction(37, 8)), "set", {"hunger": 0, "tired": 0}
        )
        self.assertEqual(
            new, {"tired": 0, "hunger": 0, "urine": 0, "milk": Fraction(37, 8)}
        )

    def test_unknown_op_raises(self) -> None:
        """没有的操作名报 ValueError"""
        with self.assertRaisesRegex(ValueError, "no op"):
            needs.fold(needs_with(), "mul", {})
