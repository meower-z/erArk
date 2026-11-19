"""连续数值的转换、显示取整与随机浮动"""

import random
from fractions import Fraction
from unittest import mock

from Script.Core import num
from tests.fast.base import FastTestCase


class NumTest(FastTestCase):
    """exact、shown 与 jitter 的取值"""

    def test_exact_float_is_six_decimals(self) -> None:
        """浮点取 6 位小数，整数与字符串精确"""
        self.assertEqual(num.exact(0.1), Fraction(1, 10))
        self.assertEqual(num.exact(1 / 3).denominator, 10**6)
        self.assertIs(type(num.exact(3)), int)
        self.assertEqual(num.exact("0.25"), Fraction(1, 4))

    def test_shown_floors(self) -> None:
        """显示向下取整，负数也一样"""
        self.assertEqual(num.shown(Fraction(7, 2)), 3)
        self.assertEqual(num.shown(Fraction(-1, 2)), -1)
        self.assertIs(type(num.shown(Fraction(7, 2))), int)

    def test_jitter_draws_once(self) -> None:
        """jitter 只抽一次整百分比"""
        with mock.patch.object(random, "randint", return_value=90) as draw:
            self.assertEqual(num.jitter(10, 80, 120), 9)
        draw.assert_called_once_with(80, 120)
