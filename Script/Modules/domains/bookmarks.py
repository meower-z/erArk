"""
收藏地点：全局键 map.bookmarks
==============================
值是场景坐标的元组，每个坐标是字符串元组，按收藏的先后排列。没有这个键时读到空列表。
写入整值替换这个键，新值与旧值相同时不写。
"""

from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import pickled

KEY = "map.bookmarks"
""" 收藏地点的全局键 """
START = (
    ("中枢", "博士房间"),
    ("中枢", "博士办公室"),
    ("贸易", "成人用品店"),
    ("书", "藏品馆"),
)
""" 新游戏的收藏地点 """

working.register(KEY, ())


def places(game: core.GameState | None = None) -> list[list[str]]:
    """
    收藏地点
    Keyword arguments:
    game -- 给出时只读这个 GameState，没有时读当前缓冲区
    Return arguments:
    list -- 场景坐标的列表，新列表
    """
    stored = cast(tuple[tuple[str, ...], ...], working.get(None, KEY, game))
    return [list(place) for place in stored]


def _put(value: list[list[str]]) -> None:
    new = tuple(tuple(place) for place in value)
    if working.get(None, KEY) != new:
        working.put(None, KEY, new)


def add(position: list[str]) -> None:
    """
    把场景坐标 position 记进收藏列表，写进当前缓冲区（允许重复）
    Keyword arguments:
    position -- 场景坐标
    """
    _put([*places(), position])


def remove(position: list[str]) -> None:
    """
    取消收藏 position。删掉第一个相同的坐标并写进当前缓冲区。坐标不在列表中时报 ValueError
    Keyword arguments:
    position -- 场景坐标
    """
    value = places()
    value.remove(position)
    _put(value)


def reset() -> None:
    """收藏地点换成新游戏的 START，写进当前缓冲区"""
    _put([list(place) for place in START])


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。存档缓存带着 collect_position_list 或版本早于 12 时，取出它并写进当前缓冲区
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表，原地修改
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 补上或换掉的项数，计法同 save_handle.update_dict_with_default
    """
    found, count = pickled.take(
        loaded_dict, {"collect_position_list": []}, version
    )
    if found:
        _put([list(place) for place in found["collect_position_list"]])
    return count
