# -*- coding: UTF-8 -*-
"""
简单模式

三处数值放宽，全部通过本体 Script/Core/mod_hook.py 的钩子点生效，不替换任何本体函数：
1. 催眠增长的随机系数由 0.5~1.5 放大为 5~10
2. 睡眠时理智上限成长量由"当日消耗的 1/50"改为"当日消耗的全部"（成长门槛仍是当日消耗 >= 50）
3. 酒店房间价格由 2/10/100 粉红凭证降为 1/2/3（预订面板按钮上的价格文字仍是本体原文）
"""
from Script.Core import mod_hook

MOD_ID = "easy_mode"
""" mod_id，也是钩子挂载者名 """

HYPNOSIS_FACTOR_RANGE = (5.0, 10.0)
""" 催眠随机系数的新区间 """
BASE_HYPNOSIS_FACTOR_RANGE = (0.5, 1.5)
""" 本体催眠随机系数的区间 """
HOTEL_ROOM_PRICE = [1, 2, 3]
""" 标间、情趣主题房、顶级套房的新价格 """


def scale_hypnosis_factor(factor: float, target_character_id: int) -> float:
    """
    把本体抽到的 0.5~1.5 均匀系数线性映射到 5~10：仍是均匀分布，且不额外消耗随机数
    Keyword arguments:
    factor -- 本体抽到的随机系数
    target_character_id -- 被催眠角色id（不使用）
    Return arguments:
    float -- 新系数
    """
    base_low, base_high = BASE_HYPNOSIS_FACTOR_RANGE
    low, high = HYPNOSIS_FACTOR_RANGE
    return low + (factor - base_low) * (high - low) / (base_high - base_low)


def full_sanity_growth(grow_value: int, today_cost: int) -> int:
    """
    理智上限成长量改为当日消耗的全部
    Keyword arguments:
    grow_value -- 本体算出的成长量（不使用）
    today_cost -- 当日理智消耗
    Return arguments:
    int -- 新的成长量
    """
    return round(today_cost)


def cheaper_room_price(room_price: list) -> list:
    """
    酒店房间改用新价格
    Keyword arguments:
    room_price -- 本体价格表（不使用）
    Return arguments:
    list -- 新价格表（返回副本，避免被调用方改写）
    """
    return list(HOTEL_ROOM_PRICE)


def install() -> None:
    """
    挂载三个钩子；先摘掉本 mod 的旧挂载，重复执行本文件不会重复生效
    Keyword arguments:
    无
    Return arguments:
    None
    """
    for hook, fn in (
        (mod_hook.hypnosis_random_factor, scale_hypnosis_factor),
        (mod_hook.sanity_point_growth, full_sanity_growth),
        (mod_hook.hotel_room_price, cheaper_room_price),
    ):
        hook.unregister(MOD_ID)
        hook.register(fn, owner=MOD_ID)


install()
