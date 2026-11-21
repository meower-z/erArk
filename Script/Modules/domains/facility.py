"""
基地设施的全局键 base.facility_level、base.facility_open 与 base.effectiveness
==============================================================================
base.facility_level 是 {设施id的字符串: 等级}，设施见 Facility.csv。
base.facility_open 是 {待开放设施id的字符串: 是否已开放}，待开放设施见 Facility_open.csv。
base.effectiveness 是基地效率，单位为百分数。
某个键不在全局数据里时，读到新基地的值：每个设施 1 级，每个待开放设施未开放，效率 100。
写入整值替换一个键。对外的设施id 是 int，存进键里时换成字符串。
基建面板里的升级先记进玩家选择的缓冲区，离开面板时随一个 0 分钟的 Edit 生效。
"""

from collections.abc import Mapping
from typing import cast

from Script.Config import game_config
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

LEVEL = "base.facility_level"
""" 设施等级的全局键 """
OPEN = "base.facility_open"
""" 待开放设施开放情况的全局键 """
EFFECTIVENESS = "base.effectiveness"
""" 基地效率的全局键 """
START_EFFECTIVENESS = 100
""" 新基地的效率，也是没有 base.effectiveness 时读到的值 """

working.register(LEVEL, None)
working.register(OPEN, None)
working.register(EFFECTIVENESS, START_EFFECTIVENESS)


def _map(key: str, game: core.GameState | None) -> Mapping[str, core.JSON]:
    stored = working.get(None, key, game)
    if stored is not None:
        return cast(Mapping[str, core.JSON], stored)
    if key == LEVEL:
        return {str(cid): 1 for cid in game_config.config_facility}
    return {str(cid): False for cid in game_config.config_facility_open}


def _set(key: str, cid: int, value: int | bool) -> None:
    old = _map(key, None)
    if old.get(str(cid)) != value or str(cid) not in old:
        working.put(None, key, {**old, str(cid): value})


def _get(
    key: str, cid: int, default: int | bool | None, game: core.GameState | None
) -> core.JSON:
    found = _map(key, game).get(str(cid), default)
    if found is None:
        raise KeyError(cid)
    return found


def levels(game: core.GameState | None = None) -> dict[int, int]:
    """
    全部设施的等级
    Keyword arguments:
    game -- 给出时读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 设施id 到等级，键为 int 的新字典
    """
    return {int(cid): cast(int, v) for cid, v in _map(LEVEL, game).items()}


def level(
    cid: int, default: int | None = None, game: core.GameState | None = None
) -> int:
    """
    一个设施的等级
    Keyword arguments:
    cid -- 设施id
    default -- 表里没有这个设施时交回的值，为 None 时报 KeyError
    game -- 给出时读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 等级
    """
    return cast(int, _get(LEVEL, cid, default, game))


def set_level(cid: int, value: int) -> None:
    """
    把一个设施的等级设为 value，写进当前缓冲区。表里这个设施的等级已等于 value 时不写
    Keyword arguments:
    cid -- 设施id
    value -- 等级
    """
    _set(LEVEL, cid, value)


def opens(game: core.GameState | None = None) -> dict[int, bool]:
    """
    全部待开放设施的开放情况
    Keyword arguments:
    game -- 给出时读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 待开放设施id 到是否已开放，键为 int 的新字典
    """
    return {int(cid): cast(bool, v) for cid, v in _map(OPEN, game).items()}


def is_open(
    cid: int, default: bool | None = None, game: core.GameState | None = None
) -> bool:
    """
    一个待开放设施是否已开放
    Keyword arguments:
    cid -- 待开放设施id
    default -- 表里没有这个设施时交回的值，为 None 时报 KeyError
    game -- 给出时读这个状态，没有时读当前缓冲区
    Return arguments:
    bool -- 是否已开放
    """
    return cast(bool, _get(OPEN, cid, default, game))


def set_open(cid: int, value: bool = True) -> None:
    """
    把一个待开放设施的开放情况设为 value，写进当前缓冲区。表里这个设施的值已等于 value 时不写
    Keyword arguments:
    cid -- 待开放设施id
    value -- 是否开放
    """
    _set(OPEN, cid, value)


def effectiveness(game: core.GameState | None = None) -> int | float:
    """
    基地效率，单位为百分数
    Keyword arguments:
    game -- 给出时读这个状态，没有时读当前缓冲区
    Return arguments:
    int | float -- 效率
    """
    return cast(int | float, working.get(None, EFFECTIVENESS, game))


def set_effectiveness(value: int | float) -> None:
    """
    把基地效率设为 value，写进当前缓冲区。当前效率与 value 值相等、类型相同时不写
    Keyword arguments:
    value -- 效率，单位为百分数
    """
    old = effectiveness()
    if old != value or type(old) is not type(value):
        working.put(None, EFFECTIVENESS, value)
