"""
基地各区块的供电策略：全局键 base.power_strategy
================================================
值是 {区块id的字符串: 供电策略id}。表里没有的区块读默认值：UNBUILT_ZONES 里的区块断电（2），其余标准（0）。
写入整值替换这个键。动力系统管理面板里改的策略先记进玩家选择的缓冲区，离开面板时随一个 0 分钟的 Edit 生效。
"""

from collections.abc import Mapping
from typing import cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "base.power_strategy"
""" 供电策略在全局数据里的键 """
UNBUILT_ZONES = (8, 18, 20)
""" 未实装的区块，默认断电 """

working.register(KEY, {})


def strategies(game: core.GameState | None = None) -> dict[int, int]:
    """
    表里记下的供电策略
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 区块id（int）到供电策略id，只含表里有的区块
    """
    stored = cast(Mapping[str, int], working.get(None, KEY, game))
    return {int(zone): strategy for zone, strategy in stored.items()}


def strategy_of(zone_cid: int, game: core.GameState | None = None) -> int:
    """
    区块当前的供电策略，表里没有时为默认值：UNBUILT_ZONES 里的区块断电（2），其余标准（0）
    Keyword arguments:
    zone_cid -- 区块id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 供电策略id
    """
    default = 2 if zone_cid in UNBUILT_ZONES else 0
    stored = cast(Mapping[str, int], working.get(None, KEY, game))
    return stored.get(str(zone_cid), default)


def set_strategy(zone_cid: int, value: int) -> None:
    """
    改一个区块的供电策略：整值替换 base.power_strategy，写进当前缓冲区
    Keyword arguments:
    zone_cid -- 区块id
    value -- 供电策略id
    """
    current = cast(Mapping[str, int], working.get(None, KEY))
    working.put(None, KEY, {**current, str(zone_cid): value})
