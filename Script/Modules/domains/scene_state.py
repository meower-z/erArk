"""
场景运行态：门锁状态与场景内角色
================================
全局键 scene.closed（常量 CLOSED）存放已关门场景的门锁状态，形状为 {场景路径: 1 | 2}，默认值为 {}。
门锁取值与 Scene.close_type 相同：1 表示正常关门，2 表示小隔间关门，未关门（0）的场景不入表。
场景内的角色不存入状态，由 occupants 按玩家 0 与在编名册（roster.active）中各角色的 activity.position 算出，按角色 id
升序返回新列表。
读函数传入 game 时只读该 GameState，未传入时读当前缓冲区（含尚未套用的写入）。
读档时 adopt_old_save 移除缓存字典里的 scene_data，把其中仍在 constant.scene_data 且非 0 的门锁写入 scene.closed。
随后它将 scene.closed 键中的异系统路径分隔符转为当前系统的 os.sep，并剔除不在 constant.scene_data 中的条目。
"""

import os
from collections.abc import Mapping
from typing import Any, cast

from Script.Core import constant
from Script.Kernel import core
from Script.Modules.domains import activity, roster
from Script.Modules.gameplay_resolution import working

CLOSED = "scene.closed"
""" 全局键：已关门场景到门锁状态的映射 """

working.register(CLOSED, {})


def _closed(game: core.GameState | None) -> Mapping[str, int]:
    return cast(Mapping[str, int], working.get(None, CLOSED, game))


def closed(game: core.GameState | None = None) -> dict[str, int]:
    """
    返回已关门场景到门锁状态的映射副本
    Keyword arguments:
    game -- 给出时只读这个 GameState，省略时读当前缓冲区（含尚未套用的写入）
    Return arguments:
    dict[str, int] -- 场景路径到非 0 门锁状态的新字典
    """
    return dict(_closed(game))


def close_flag(path: str, game: core.GameState | None = None) -> int:
    """
    读取指定场景的门锁状态，未在表内时返回 0
    Keyword arguments:
    path -- 场景路径字符串
    game -- 给出时只读这个 GameState，省略时读当前缓冲区（含尚未套用的写入）
    Return arguments:
    int -- 门锁状态（0 表示未关门，1 表示正常关门，2 表示小隔间关门）
    """
    return _closed(game).get(path, 0)


def set_close_flag(path: str, value: int) -> None:
    """
    将指定场景的门锁状态写入当前缓冲区。value 为 0 时移除该场景条目，与当前值相同时不写入。须在一步结算、玩家选择草稿或
    working 缓冲区内调用
    Keyword arguments:
    path -- 场景路径字符串
    value -- 新的门锁状态（0 表示未关门）
    """
    stored = _closed(None)
    if stored.get(path, 0) == value:
        return
    table = {k: v for k, v in stored.items() if k != path}
    if value:
        table[path] = value
    working.put(None, CLOSED, table)


# 缓存全部场景到升序角色 id 列表的索引，避免每次 occupants() 重复遍历在编名册。
# 未传 game 时按 working.revision(activity.POSITION, roster.ACTIVE) 缓存，仅在读取缓冲区、基准
# GameState 或位置与名册键写入次数变化时重建。传入 game 时按该 GameState 缓存，换用其他状态时重建。
_memo: tuple[
    object, core.GameState | None, tuple[int, ...], dict[str, list[int]]
] = (None, None, (), {})


def _index(game: core.GameState | None) -> dict[str, list[int]]:
    global _memo
    if game is None:
        key = working.revision(activity.POSITION, roster.ACTIVE)
    else:
        key = (None, game, ())
    buffer, base, revision, index = _memo
    if buffer is key[0] and base is key[1] and revision == key[2]:
        return index
    index = {}
    for cid in sorted({0, *roster.active(game)}):
        path = os.sep.join(activity.position(cid, game))
        index.setdefault(path, []).append(cid)
    _memo = (*key, index)
    return index


def occupants(path: str, game: core.GameState | None = None) -> list[int]:
    """
    返回当前位于指定场景的角色 id 列表，按角色 id 升序排列。
    结果由玩家 0 与在编名册（roster.active）中各角色的 activity.position 实时算出，每次调用返回新列表
    Keyword arguments:
    path -- 场景路径字符串
    game -- 给出时只读这个 GameState，省略时读当前缓冲区（含尚未套用的写入）
    Return arguments:
    list[int] -- 该场景内角色 id 的新列表，按升序排列
    """
    return list(_index(game).get(path, ()))


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时导入旧存档的门锁并清理 scene.closed。
    先从 loaded_dict 移除 scene_data，若其为字典，将存在于 constant.scene_data 且 close_flag 非 0 的门锁写入
    scene.closed。
    不读取旧存档里的场景角色列表，场景内角色由存档中的位置与在编名册算出。
    随后将 scene.closed 键中的异系统路径分隔符转为当前系统的 os.sep，并剔除不在 constant.scene_data 中的条目。
    仅在清理结果与原表不同时写回 scene.closed
    Keyword arguments:
    loaded_dict -- 读档阶段加载的缓存字段字典
    """
    saved = loaded_dict.pop("scene_data", None)
    if isinstance(saved, dict):
        for path, scene in saved.items():
            flag = getattr(scene, "close_flag", 0)
            if flag and path in constant.scene_data:
                set_close_flag(path, flag)
    foreign = "\\" if os.sep == "/" else "/"
    stored = dict(_closed(None))
    kept = {}
    for path, flag in stored.items():
        local = path.replace(foreign, os.sep)
        if local in constant.scene_data:
            kept[local] = flag
    if kept != stored:
        working.put(None, CLOSED, kept)
