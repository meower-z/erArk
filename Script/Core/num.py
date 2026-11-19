"""连续数值：整数或有理数，从不为浮点；只在显示时取整"""

import math
import random
from fractions import Fraction

type Num = int | Fraction


def exact(x: int | float | str | Fraction) -> Num:
    """
    转为精确值：int 与 Fraction 原样返回，str 经 Fraction(str)，float 取 6 位小数
    Keyword arguments:
    x -- 要转换的值
    Return arguments:
    Num -- 精确值
    """
    if isinstance(x, int | Fraction):
        return x
    if isinstance(x, str):
        return Fraction(x)
    return Fraction(f"{x:.6f}")


def shown(x: Num) -> int:
    """
    显示用的取整：向下取整
    Keyword arguments:
    x -- 数值
    Return arguments:
    int -- 显示的整数
    """
    return math.floor(x)


def whole(x: Num) -> int:
    """
    作为比率、上下限、下标或次数读取时的取整：向下取整
    Keyword arguments:
    x -- 数值
    Return arguments:
    int -- 整数
    """
    return math.floor(x)


def jitter(x: Num, low: int, high: int) -> Num:
    """
    以整百分比随机浮动，只抽一次
    Keyword arguments:
    x -- 基础值
    low -- 最低百分比
    high -- 最高百分比
    Return arguments:
    Num -- x * randint(low, high) / 100
    """
    return x * Fraction(random.randint(low, high), 100)
