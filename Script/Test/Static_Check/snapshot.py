# -*- coding: UTF-8 -*-
"""
静态检查系统 - 全局状态快照序列化
将调用方传入的cache递归转换为JSON可序列化的数据结构，供检查失败时随日志一并落盘，方便事后调试。
"""

from __future__ import annotations

import dataclasses
import datetime
import json

from typing import TYPE_CHECKING

from Script.Core import constant
from Script.Modules.domains import scene_state

if TYPE_CHECKING:
    from typing import Any
    from Script.Core import game_type

# 快照时排除的Cache顶层字段名单
# 这些字段要么是静态配置数据（游戏启动后不再随玩家操作变化，快照价值低且体积巨大），
# 要么是纯渲染/绘制用的中间缓存（不反映游戏逻辑状态，只会让快照膨胀并干扰阅读）
EXCLUDED_TOP_LEVEL_FIELDS = {
    "random_npc_list",  # 旧存档读档后会留在cache上的随机npc数据，Cache本身不声明它
}
# 字段名前缀黑名单：以这些前缀开头的字段均为渲染缓存中间数据，一并排除
EXCLUDED_FIELD_PREFIXES = ("text_",)

# 递归转换时的最大深度，超过后直接使用repr兜底，防止极端嵌套结构导致快照过大或递归过深
MAX_DEPTH = 15

# 单次快照最多转储的涉事角色数量：首次检查时若存在大范围失败（如某检查对上百个角色逐一命中），
# 涉事角色并集可达数百人，全部转储仍会让单份快照膨胀到数MB。超出上限的角色只记id不转储数据
MAX_SNAPSHOT_CHARACTERS = 30


def _is_excluded_top_level_field(field_name: str) -> bool:
    """
    参数:
        field_name (str): Cache对象的顶层字段名
    返回值:
        bool: 是否应当在快照中排除该字段
    功能:
        判断某个Cache顶层字段是否命中排除名单或排除前缀，命中则该字段不进入快照
    """
    if field_name in EXCLUDED_TOP_LEVEL_FIELDS:
        return True
    return field_name.startswith(EXCLUDED_FIELD_PREFIXES)


def _to_json_safe(value: object, depth: int, visited: set) -> Any:
    """
    参数:
        value (Any): 待转换的任意对象
        depth (int): 当前递归深度，从0开始
        visited (set): 已访问对象id集合，用于检测循环引用
    返回值:
        Any: 转换后的JSON可序列化数据（仅由dict/list/str/int/float/bool/None构成）
    功能:
        递归地将任意Python对象转换为JSON可序列化结构：
        基础类型原样返回；datetime转为isoformat字符串；set/tuple转为列表（能排序则排序，保证快照可复现比较）；
        dict的键统一转为字符串；带__dict__的自定义对象取其字段字典递归转换；
        出现循环引用、超过最大深度或转换失败时，均以repr(value)兜底，保证函数不会抛出异常
    """
    # 基础可直接JSON化的类型
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    # 日期时间类型转为可读字符串
    if isinstance(value, datetime.datetime) or isinstance(value, datetime.date):
        return value.isoformat()
    # 深度超限，直接使用repr兜底，避免递归过深
    if depth >= MAX_DEPTH:
        try:
            return repr(value)
        except Exception:
            return "<不可repr对象>"
    # 循环引用检测：容器与自定义对象才需要记录，基础类型不会成环
    obj_id = id(value)
    if obj_id in visited:
        return f"<循环引用: {type(value).__name__}>"
    if isinstance(value, dict):
        visited = visited | {obj_id}
        result = {}
        for k, v in value.items():
            try:
                safe_key = k if isinstance(k, str) else repr(k)
                result[safe_key] = _to_json_safe(v, depth + 1, visited)
            except Exception as e:
                result[repr(k)] = f"<转换失败: {e}>"
        return result
    if isinstance(value, (set, frozenset, tuple, list)):
        visited = visited | {obj_id}
        try:
            items = list(value)
            # 集合/元组尽量排序后输出，保证同一状态下多次快照结果一致，便于anti-spam做去重比较
            if isinstance(value, (set, frozenset)):
                try:
                    items = sorted(items)
                except TypeError:
                    pass
            return [_to_json_safe(item, depth + 1, visited) for item in items]
        except Exception as e:
            return f"<转换失败: {e}>"
    # 自定义对象：取其__dict__字段递归转换
    if hasattr(value, "__dict__"):
        visited = visited | {obj_id}
        try:
            return _to_json_safe(vars(value), depth + 1, visited)
        except Exception as e:
            try:
                return repr(value)
            except Exception:
                return f"<不可repr对象: {e}>"
    # 其余一律使用repr兜底（如函数、模块、枚举等）
    try:
        return repr(value)
    except Exception:
        return "<不可repr对象>"


def _scene_snapshot() -> dict[str, dict[str, Any]]:
    """
    返回值:
        dict[str, dict[str, Any]]: 按 constant.scene_data 顺序排列的非空或已关门场景快照字典
    功能:
        从内核状态构造场景快照，按 constant.scene_data 顺序收录有在场角色或门锁非 0 的场景。
        每项为 {"character_list": 升序在场角色 id 列表, "close_flag": 门锁状态}，省略无人且未关门的场景以控制体积
    """
    doors = scene_state.closed()
    scenes = {}
    for path in constant.scene_data:
        people = scene_state.occupants(path)
        if people or path in doors:
            scenes[path] = {
                "character_list": people,
                "close_flag": doors.get(path, 0),
            }
    return scenes


def build_snapshot(
    cache: game_type.Cache,
    involved_character_ids: list[int] | set[int] | None = None,
) -> dict:
    """
    参数:
        cache: 当前游戏缓存对象
        involved_character_ids (list[int] | set[int] | None): 涉事角色id集合，为None时全量转储角色身份表
    返回值:
        dict: 当前全局状态的JSON可序列化快照
    功能:
        将传入cache的顶层字段转为JSON可序列化数据（排除EXCLUDED_TOP_LEVEL_FIELDS与text_前缀字段）。
        角色身份表写入identity.characters键：传入involved_character_ids时仅保留涉事角色与玩家（最多
        MAX_SNAPSHOT_CHARACTERS人），并附identity.characters_omitted说明，未传入时全量保留。
        随后从内核状态补充 scene_data 节，只记有角色或门锁非 0 的场景（character_list 与 close_flag），失败时写占位文本
    """
    snapshot = {}
    for field_name, field_value in vars(cache).items():
        if _is_excluded_top_level_field(field_name):
            continue
        try:
            snapshot[field_name] = _to_json_safe(field_value, 0, set())
        except Exception as e:
            snapshot[field_name] = f"<字段快照失败: {e}>"
    from Script.Modules.domains import identity

    table = identity.table()
    if involved_character_ids is None:
        dumped_ids = list(table)
    else:
        # 仅保留涉事角色与玩家（id 0）的身份，最多 MAX_SNAPSHOT_CHARACTERS 人，超出的涉事角色只记 id
        keep_ids = sorted((set(involved_character_ids) | {0}) & set(table))
        dumped_ids = keep_ids[:MAX_SNAPSHOT_CHARACTERS]
        snapshot[f"{identity.KEY}_omitted"] = (
            f"共{len(table)}个角色，涉事{len(keep_ids)}个，仅转储前{len(dumped_ids)}个{dumped_ids}，未转储的涉事角色id={keep_ids[MAX_SNAPSHOT_CHARACTERS:]}"
        )
    snapshot[identity.KEY] = _to_json_safe(
        {cid: dataclasses.asdict(table[cid]) for cid in dumped_ids}, 0, set()
    )
    try:
        snapshot["scene_data"] = _scene_snapshot()
    except Exception as e:
        snapshot["scene_data"] = f"<字段快照失败: {e}>"
    return snapshot


def _json_default_fallback(obj: object) -> str:
    """
    参数:
        obj (Any): json.dumps遇到的无法直接序列化的对象
    返回值:
        str: 该对象的repr字符串
    功能:
        作为json.dumps的default兜底函数，理论上build_snapshot已将所有内容转换为JSON安全类型，
        此函数仅作为双重保险，防止个别遗漏对象导致dump_snapshot_json抛出异常
    """
    try:
        return repr(obj)
    except Exception:
        return "<不可序列化对象>"


def dump_snapshot_json(
    cache: game_type.Cache,
    involved_character_ids: list[int] | set[int] | None = None,
) -> str:
    """
    参数:
        cache: 当前游戏缓存对象
        involved_character_ids (list[int] | set[int] | None): 涉事角色id集合，为None时全量转储角色身份表
    返回值:
        str: 当前全局状态快照的JSON字符串（ensure_ascii=False，保留中文可读性）
    功能:
        调用build_snapshot获取快照字典，并序列化为紧凑的单行JSON字符串，供写入日志文件
    """
    snapshot = build_snapshot(cache, involved_character_ids)
    try:
        return json.dumps(
            snapshot, ensure_ascii=False, default=_json_default_fallback
        )
    except Exception as e:
        return f"<快照序列化失败: {e}>"
