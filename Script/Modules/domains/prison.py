"""
基地关押区的全局键 base.prisoners 与 base.prison_settings
=========================================================
base.prisoners 是 {囚犯角色id的字符串: {"since": 入狱分钟数, "escape": 逃脱概率}}，按记下顺序排列。
since 为内核时钟的分钟数，读出时用 game_time.at 还原为 GameTime。没有这个键时读空表。
base.prison_settings 存监禁调教设置、调教前清洗与润滑开关、调教前道具表、调教助手行为列表与禁止列表。
没有这个键时，settings() 返回配置表全部设置项为 0 的字典，其余项取 False、0、空表或空列表。
写入整值替换对应键，新值与旧值相同时不写。
"""

import datetime
from collections.abc import Collection, Mapping
from typing import Any, cast

from Script.Config import game_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

PRISONERS = "base.prisoners"
""" 囚犯名册在全局数据里的键 """
SETTINGS = "base.prison_settings"
""" 监禁调教设置与调教前准备项在全局数据里的键 """

PICKLED_TYPES: Mapping[str, type] = {
    "current_prisoners": dict,
    "confinement_training_setting": dict,
    "pre_training_cleaning": bool,
    "pre_training_lubrication": bool,
    "pre_training_tool_dict": dict,
    "sex_assistant_ai_behavior_id_list": list,
    "sex_assistant_ai_ban_behavior_id_list": list,
}
""" 版本 14 之前的存档里，罗德岛对象上七项关押区属性名与应有类型 """

_SETTINGS_OLD_KEYS = (
    "confinement_training_setting",
    "pre_training_cleaning",
    "pre_training_lubrication",
    "pre_training_tool_dict",
    "sex_assistant_ai_behavior_id_list",
    "sex_assistant_ai_ban_behavior_id_list",
)

working.register(PRISONERS, {})
working.register(SETTINGS, None)


def _raw_prisoners(
    game: core.GameState | None = None,
) -> Mapping[str, Mapping[str, core.JSON]]:
    return cast(
        Mapping[str, Mapping[str, core.JSON]],
        working.get(None, PRISONERS, game),
    )


def _put_prisoners(new: Mapping[str, Mapping[str, core.JSON]]) -> None:
    if new != _raw_prisoners():
        working.put(None, PRISONERS, cast(core.JSON, new))


def prisoners(game: core.GameState | None = None) -> dict[int, list[Any]]:
    """全部在册囚犯的记录：角色id 到 [入狱时间(GameTime), 逃脱概率]，按存下顺序排列"""
    stored = _raw_prisoners(game)
    if not stored:
        return {}
    return {
        int(cid): [game_time.at(cast(int, rec["since"])), rec["escape"]]
        for cid, rec in stored.items()
    }


def prisoner_ids(game: core.GameState | None = None) -> tuple[int, ...]:
    """全部在册囚犯的角色id，按存下顺序排列"""
    stored = _raw_prisoners(game)
    if not stored:
        return ()
    return tuple(int(cid) for cid in stored)


def is_prisoner(cid: int, game: core.GameState | None = None) -> bool:
    """角色是否在囚犯名册里"""
    return str(cid) in _raw_prisoners(game)


def escape_probability(
    cid: int, game: core.GameState | None = None
) -> int | float:
    """一名在册囚犯的逃脱概率，不在名册时报 KeyError"""
    return cast(int | float, _raw_prisoners(game)[str(cid)]["escape"])


def imprison(
    cid: int, since: datetime.datetime, escape: int | float = 0
) -> None:
    """登记或覆盖一名囚犯的入狱时间与逃脱概率"""
    current = dict(_raw_prisoners())
    current[str(cid)] = {"since": game_time.minutes(since), "escape": escape}
    _put_prisoners(current)


def set_escape_probability(cid: int, escape: int | float) -> None:
    """更新一名囚犯的逃脱概率。不在名册里时以当前游戏时间为入狱时间登记"""
    current = dict(_raw_prisoners())
    key = str(cid)
    if key in current:
        current[key] = {**current[key], "escape": escape}
    else:
        current[key] = {
            "since": game_time.minutes(game_time.now()),
            "escape": escape,
        }
    _put_prisoners(current)


def release(cid: int) -> bool:
    """从囚犯名册里移除一名角色，在册并移除时为 True，不在名册时为 False"""
    current = dict(_raw_prisoners())
    if current.pop(str(cid), None) is None:
        return False
    _put_prisoners(current)
    return True


def drop_prisoners(cids: Collection[int]) -> int:
    """从囚犯名册里移除 cids 中所有在册角色，返回实际移除人数"""
    current = _raw_prisoners()
    if not current:
        return 0
    drop_keys = {str(cid) for cid in cids}
    kept = {k: v for k, v in current.items() if k not in drop_keys}
    removed = len(current) - len(kept)
    if removed:
        _put_prisoners(kept)
    return removed


def remap(old_to_new: Mapping[int, int]) -> None:
    """角色换 id 时，把囚犯名册里的旧角色id换成新角色id，表里没有的 id 不变"""
    current = _raw_prisoners()
    if not current:
        return
    remapped = {
        str(old_to_new.get(int(cid), int(cid))): rec
        for cid, rec in current.items()
    }
    _put_prisoners(remapped)


def _settings_blob(
    game: core.GameState | None = None,
) -> Mapping[str, core.JSON] | None:
    stored = working.get(None, SETTINGS, game)
    if stored is None:
        return None
    return cast(Mapping[str, core.JSON], stored)


def _default_settings_map() -> dict[str, int]:
    return {
        str(cid): 0 for cid in game_config.config_confinement_training_setting
    }


def _put_settings(**part: core.JSON) -> None:
    stored = _settings_blob()
    base: dict[str, core.JSON] = (
        dict(stored)
        if stored is not None
        else {
            "settings": _default_settings_map(),
            "cleaning": False,
            "lubrication": False,
            "tools": {},
            "assistant_behaviors": (),
            "assistant_ban_behaviors": (),
        }
    )
    new = {**base, **part}
    if stored is None or new != stored:
        working.put(None, SETTINGS, cast(core.JSON, new))


def settings(game: core.GameState | None = None) -> dict[int, int]:
    """
    监禁调教设置表。未写入过键时按配置表各项返回 0
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 设置id到设置值
    """
    stored = _settings_blob(game)
    if stored is None:
        return {
            cid: 0 for cid in game_config.config_confinement_training_setting
        }
    raw = cast(Mapping[str, int], stored.get("settings", {}))
    return {int(cid): value for cid, value in raw.items()}


def setting(
    cid: int, default: int = 0, game: core.GameState | None = None
) -> int:
    """
    读取一项监禁调教设置
    Keyword arguments:
    cid -- 设置id
    default -- 缺项时返回的值
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 设置值
    """
    stored = _settings_blob(game)
    if stored is None:
        return default
    raw = cast(Mapping[str, int], stored.get("settings", {}))
    return raw.get(str(cid), default)


def set_setting(cid: int, value: int) -> None:
    """
    修改一项监禁调教设置，键已存且值未变时不写
    Keyword arguments:
    cid -- 设置id
    value -- 新值
    """
    stored = _settings_blob()
    raw = (
        dict(cast(Mapping[str, int], stored.get("settings", {})))
        if stored is not None
        else _default_settings_map()
    )
    key = str(cid)
    if stored is not None and raw.get(key) == value and key in raw:
        return
    raw[key] = value
    _put_settings(settings=cast(core.JSON, raw))


def reset_settings() -> None:
    """按配置表把全部监禁调教设置初始化为 0"""
    _put_settings(settings=cast(core.JSON, _default_settings_map()))


def fill_missing_settings() -> int:
    """
    补全配置表里有但当前设置表里缺的设置项为 0
    Return arguments:
    int -- 补全的项数
    """
    stored = _settings_blob()
    raw = (
        dict(cast(Mapping[str, int], stored.get("settings", {})))
        if stored is not None
        else {}
    )
    added = 0
    for cid in game_config.config_confinement_training_setting:
        key = str(cid)
        if key not in raw:
            raw[key] = 0
            added += 1
    if added or stored is None:
        _put_settings(settings=cast(core.JSON, raw))
    return added


def cleaning(game: core.GameState | None = None) -> bool:
    """
    调教前清洗准备开关
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    bool -- 是否开启
    """
    stored = _settings_blob(game)
    return bool(stored.get("cleaning", False)) if stored is not None else False


def set_cleaning(value: bool) -> None:
    """
    设置调教前清洗准备开关，未变时不写
    Keyword arguments:
    value -- 是否开启
    """
    if cleaning() != value:
        _put_settings(cleaning=bool(value))


def lubrication(game: core.GameState | None = None) -> bool:
    """
    调教前润滑准备开关
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    bool -- 是否开启
    """
    stored = _settings_blob(game)
    return (
        bool(stored.get("lubrication", False)) if stored is not None else False
    )


def set_lubrication(value: bool) -> None:
    """
    设置调教前润滑准备开关，未变时不写
    Keyword arguments:
    value -- 是否开启
    """
    if lubrication() != value:
        _put_settings(lubrication=bool(value))


def tools(game: core.GameState | None = None) -> dict[int, int]:
    """
    调教前道具启用表
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 道具下标到启用标志（0 或 1）
    """
    stored = _settings_blob(game)
    if stored is None:
        return {}
    raw = cast(Mapping[str, int], stored.get("tools", {}))
    return {int(k): v for k, v in raw.items()}


def tool(tool_id: int, game: core.GameState | None = None) -> int:
    """
    读取一个调教前道具的启用标志，缺项为 0
    Keyword arguments:
    tool_id -- 道具下标
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 启用标志
    """
    stored = _settings_blob(game)
    if stored is None:
        return 0
    raw = cast(Mapping[str, int], stored.get("tools", {}))
    return raw.get(str(tool_id), 0)


def set_tool(tool_id: int, value: int) -> None:
    """
    设置一个调教前道具的启用标志，键已存且该项值未变时不写
    Keyword arguments:
    tool_id -- 道具下标
    value -- 启用标志
    """
    stored = _settings_blob()
    raw = (
        dict(cast(Mapping[str, int], stored.get("tools", {})))
        if stored is not None
        else {}
    )
    key = str(tool_id)
    if stored is not None and raw.get(key) == value and key in raw:
        return
    raw[key] = value
    _put_settings(tools=cast(core.JSON, raw))


def assistant_behaviors(game: core.GameState | None = None) -> list[str]:
    """
    调教助手的指定行为列表
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    list -- 行为id列表，保持存下顺序
    """
    stored = _settings_blob(game)
    if stored is None:
        return []
    return list(cast(tuple[str, ...], stored.get("assistant_behaviors", ())))


def toggle_assistant_behavior(behavior_id: str) -> None:
    """
    在调教助手的指定行为列表里切换一项：已在其中则移除，不在则追加在末尾
    Keyword arguments:
    behavior_id -- 行为id
    """
    items = assistant_behaviors()
    if behavior_id in items:
        items.remove(behavior_id)
    else:
        items.append(behavior_id)
    _put_settings(assistant_behaviors=tuple(items))


def assistant_ban_behaviors(game: core.GameState | None = None) -> list[str]:
    """
    调教助手的禁止行为列表
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    list -- 行为id列表，保持存下顺序
    """
    stored = _settings_blob(game)
    if stored is None:
        return []
    return list(
        cast(tuple[str, ...], stored.get("assistant_ban_behaviors", ()))
    )


def toggle_assistant_ban_behavior(behavior_id: str) -> None:
    """
    在调教助手的禁止行为列表里切换一项：已在其中则移除，不在则追加在末尾
    Keyword arguments:
    behavior_id -- 行为id
    """
    items = assistant_ban_behaviors()
    if behavior_id in items:
        items.remove(behavior_id)
    else:
        items.append(behavior_id)
    _put_settings(assistant_ban_behaviors=tuple(items))


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED_TYPES 里的七项属性，把类型相符的值写进当前缓冲区。
    对象带有任意一项设置类旧属性时，整份写进 base.prison_settings，缺项或类型不符项取空值或 False。
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档版本，旧存档为 0
    Return arguments:
    int -- 版本 14 之前的存档里缺了或类型不符的属性个数，版本 14 及以后为 0
    """
    island = loaded_dict.get("rhodes_island")
    attrs = vars(island) if island is not None else {}
    found: dict[str, Any] = {
        name: attrs.pop(name) for name in PICKLED_TYPES if name in attrs
    }
    kept: dict[str, Any] = {
        n: v for n, v in found.items() if type(v) is PICKLED_TYPES[n]
    }
    raw_prisoners = kept.get("current_prisoners")
    if raw_prisoners:
        converted: dict[str, dict[str, core.JSON]] = {}
        for cid, rec in raw_prisoners.items():
            if isinstance(rec, (list, tuple)) and len(rec) >= 2:
                since = (
                    game_time.minutes(rec[0])
                    if isinstance(rec[0], datetime.datetime)
                    else 0
                )
                converted[str(cid)] = {"since": since, "escape": rec[1]}
        if converted:
            working.put(None, PRISONERS, cast(core.JSON, converted))
    if any(name in found for name in _SETTINGS_OLD_KEYS):
        raw_settings = kept.get("confinement_training_setting", {})
        raw_tools = kept.get("pre_training_tool_dict", {})
        blob: dict[str, core.JSON] = {
            "settings": {str(k): v for k, v in raw_settings.items()},
            "cleaning": kept.get("pre_training_cleaning", False),
            "lubrication": kept.get("pre_training_lubrication", False),
            "tools": {str(k): v for k, v in raw_tools.items()},
            "assistant_behaviors": tuple(
                kept.get("sex_assistant_ai_behavior_id_list", ())
            ),
            "assistant_ban_behaviors": tuple(
                kept.get("sex_assistant_ai_ban_behavior_id_list", ())
            ),
        }
        working.put(None, SETTINGS, cast(core.JSON, blob))
    return len(PICKLED_TYPES) - len(kept) if version < 14 else 0
