"""
全局模式开关：全局键 mode.time_stop、mode.group_sex 与 mode.sex_class
================================================================
mode.time_stop 是时间停止模式，mode.group_sex 是群交模式，mode.sex_class 是性技实操课（课堂H）模式。
开课时须同时开群交模式，群交模板与它的读取点才生效；mode.sex_class 只用于口上差分、前提区分与结算差分。
没有某一项时读到 False。写入整值替换一个键，值没变时不写。
"""

from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import pickled

TIME_STOP = "mode.time_stop"
""" 时间停止模式的全局键 """
GROUP_SEX = "mode.group_sex"
""" 群交模式的全局键 """
SEX_CLASS = "mode.sex_class"
""" 性技实操课模式的全局键 """
PICKLED = {
    "time_stop_mode": TIME_STOP,
    "group_sex_mode": GROUP_SEX,
    "sex_class_mode": SEX_CLASS,
}
""" 存档缓存（版本 12 之前）里的属性名到全局键 """

for _key in PICKLED.values():
    working.register(_key, False)


def _set(key: str, on: bool) -> None:
    if working.get(None, key) != on:
        working.put(None, key, on)


def time_stop(game: core.GameState | None = None) -> bool:
    """时间停止模式是否开着"""
    return cast(bool, working.get(None, TIME_STOP, game))


def set_time_stop(on: bool) -> None:
    """
    开关时间停止模式，写进当前缓冲区
    Keyword arguments:
    on -- 开为 True
    """
    _set(TIME_STOP, on)


def group_sex(game: core.GameState | None = None) -> bool:
    """群交模式是否开着"""
    return cast(bool, working.get(None, GROUP_SEX, game))


def set_group_sex(on: bool) -> None:
    """
    开关群交模式，写进当前缓冲区
    Keyword arguments:
    on -- 开为 True
    """
    _set(GROUP_SEX, on)


def sex_class(game: core.GameState | None = None) -> bool:
    """性技实操课模式是否开着"""
    return cast(bool, working.get(None, SEX_CLASS, game))


def set_sex_class(on: bool) -> None:
    """
    开关性技实操课模式，写进当前缓冲区
    Keyword arguments:
    on -- 开为 True
    """
    _set(SEX_CLASS, on)


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从存档缓存里删掉 PICKLED 的三个开关，写进当前缓冲区
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 补上或换掉的项数，计法同 save_handle.update_dict_with_default
    """
    default = {name: False for name in PICKLED}
    found, count = pickled.take(loaded_dict, default, version)
    for name, value in found.items():
        _set(PICKLED[name], value)
    return count
