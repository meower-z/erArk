# -*- coding: UTF-8 -*-
"""
淫纹存档数据：唯一读写 character.mod_data 的模块（tests/lint_mod_data.py 强制）

存档形状（只有内建类型、键全为 str）：
    character.mod_data["lewd_tattoo"] = {"v": 1, "effects": ["boost:vagina", "link1", ...]}   # effects 已排序
- 没有 "lewd_tattoo" 键 = 没有淫纹
- "effects" 为空列表 = 有淫纹但没有效果
- 缺 "v" 视为 1
- 不认识的数据（v 高于本 mod 所知、出现未知效果键、形状不对）：该角色淫纹不激活、不许调整、信息页告警；
  数据原样留在存档里，任何代码路径都不改写它
- 超过槽位上限的旧配置（上限调低后）照常生效，直到下次调整
"""
from typing import FrozenSet, Iterable, NamedTuple, Optional

from Script.Core import cache_control, mod_hook

from . import MOD_ID, effects

DATA_VERSION = 1
""" 当前存档数据版本 """


class TattooView(NamedTuple):
    """
    一个角色的淫纹数据读取结果（面板与信息页用）
    Keyword arguments:
    present -- 是否有淫纹
    active -- 数据是否被本 mod 认识并生效
    keys -- 已知效果键（active 为 False 时为空集合）
    problem -- 不激活的原因（active 为 True 或没有淫纹时为空串）
    """

    present: bool
    active: bool
    keys: FrozenSet[str]
    problem: str


NO_TATTOO = TattooView(False, False, frozenset(), "")
""" 没有淫纹 """


def _entry(character_id: int):
    """
    取角色的原始淫纹数据
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    object -- mod_data 里本 mod 的条目；没有淫纹时为 None
    """
    return cache_control.cache.character_data[character_id].mod_data.get(MOD_ID)


def _parse(entry) -> TattooView:
    """
    解析原始条目；不认识的形状一律判为不激活
    Keyword arguments:
    entry -- mod_data 里本 mod 的条目（非 None）
    Return arguments:
    TattooView -- 读取结果
    """
    if type(entry) is not dict:
        return TattooView(True, False, frozenset(), "数据形状无法识别")
    version = entry.get("v", DATA_VERSION)
    if type(version) is not int or version > DATA_VERSION:
        return TattooView(True, False, frozenset(), f"数据版本 {version!r} 高于本 mod 所知的 {DATA_VERSION}")
    raw = entry.get("effects", [])
    if type(raw) is not list or any(type(key) is not str for key in raw):
        return TattooView(True, False, frozenset(), "效果列表形状无法识别")
    unknown = sorted(key for key in raw if key not in effects.EFFECT_BY_KEY)
    if unknown:
        return TattooView(True, False, frozenset(), "未知效果 " + "、".join(unknown))
    return TattooView(True, True, frozenset(raw), "")


def view(character_id: int) -> TattooView:
    """
    读角色的淫纹（面板、指令、信息页用）
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    TattooView -- 读取结果
    """
    entry = _entry(character_id)
    if entry is None:
        return NO_TATTOO
    return _parse(entry)


def active_keys(character_id: int) -> Optional[FrozenSet[str]]:
    """
    读角色正在生效的效果键（热路径：每次状态结算都会调用；没淫纹的角色只花一次 dict.get）
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    Optional[FrozenSet[str]] -- None 表示没有淫纹或数据不激活；否则为效果键集合
    """
    entry = _entry(character_id)
    if entry is None:
        return None
    result = _parse(entry)
    return result.keys if result.active else None


def has_tattoo(character_id: int) -> bool:
    """
    角色是否已有淫纹（不管数据是否被认识；指令前提用）
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 是否有淫纹
    """
    return _entry(character_id) is not None


def write(character_id: int, keys: Iterable[str]) -> None:
    """
    写入淫纹效果（刻印与调整共用）。只许写在"没有淫纹"或"数据已激活"的角色上；条目里的其他字段原样保留
    Keyword arguments:
    character_id -- 角色id
    keys -- 新的效果键集合（必须全是已知键）
    Return arguments:
    None
    """
    current = view(character_id)
    if current.present and not current.active:
        raise ValueError(f"角色 {character_id} 的淫纹数据不被本 mod 认识，拒绝改写：{current.problem}")
    new_keys = sorted(set(keys))
    unknown = [key for key in new_keys if key not in effects.EFFECT_BY_KEY]
    if unknown:
        raise ValueError(f"未知效果键 {unknown}")
    mod_data = cache_control.cache.character_data[character_id].mod_data
    entry = dict(mod_data.get(MOD_ID) or {})
    entry["v"] = DATA_VERSION
    entry["effects"] = new_keys
    errors = mod_hook.validate_mod_data(entry, f"mod_data[{MOD_ID!r}]")
    if errors:
        raise ValueError("淫纹数据形状错误：" + "；".join(errors))
    mod_data[MOD_ID] = entry
