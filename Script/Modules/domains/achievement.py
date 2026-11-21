"""
成就与成就的累计数据：全局键 world.achievement
==========================================
值是 game_type.ACHIEVEMENT 的各个属性，按属性名存：计数是 int，列表是 JSON 数组，
字典（成就字典与各项记录）的 int 键存成字符串。没有这一项时读到 ACHIEVEMENT() 的值。
读用 view 拿一个新的 ACHIEVEMENT 对象。写入整值替换这个键，值没变时不写。
"""

from collections.abc import Mapping
from typing import Any, cast

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import pickled

KEY = "world.achievement"
""" 成就数据的全局键 """


def _encode(value: Any) -> core.JSON:
    if isinstance(value, dict):
        return {str(key): _encode(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return tuple(_encode(item) for item in value)
    return cast(core.JSON, value)


def _decode(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {int(key): _decode(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_decode(item) for item in value]
    return value


DEFAULT = cast(Mapping[str, core.JSON], _encode(vars(game_type.ACHIEVEMENT())))
""" 没有 world.achievement 时读到的值 """

working.register(KEY, DEFAULT)


def _data(game: core.GameState | None) -> Mapping[str, core.JSON]:
    return cast(Mapping[str, core.JSON], working.get(None, KEY, game))


def get(name: str, game: core.GameState | None = None) -> Any:
    """
    一个属性的值
    Keyword arguments:
    name -- ACHIEVEMENT 的属性名
    game -- 给出时读这个状态，没有时读当前缓冲区
    Return arguments:
    Any -- 新的值：int、list 或键为 int 的 dict
    """
    return _decode(_data(game)[name])


def done(achievement_id: int) -> bool:
    """
    成就是否已达成，同 achievement_dict.get(achievement_id, False)
    Keyword arguments:
    achievement_id -- 成就编号
    """
    return bool(
        cast(Mapping[str, Any], _data(None)["achievement_dict"]).get(
            str(achievement_id), False
        )
    )


def view(game: core.GameState | None = None) -> game_type.ACHIEVEMENT:
    """
    全部属性，装在一个新的 ACHIEVEMENT 对象里；改它不改 GameState
    Keyword arguments:
    game -- 给出时读这个状态，没有时读当前缓冲区
    Return arguments:
    ACHIEVEMENT -- 成就对象
    """
    shown = game_type.ACHIEVEMENT()
    for name, value in _data(game).items():
        setattr(shown, name, _decode(value))
    return shown


def stored(game: core.GameState | None = None) -> Mapping[str, core.JSON]:
    """
    存着的 JSON 值，新周目继承时整个带过去
    Keyword arguments:
    game -- 给出时读这个状态，没有时读当前缓冲区
    Return arguments:
    Mapping -- world.achievement 的值
    """
    return _data(game)


def restore(value: Mapping[str, core.JSON]) -> None:
    """
    整个换成 stored 交回的值，写进当前缓冲区
    Keyword arguments:
    value -- world.achievement 的值
    """
    if _data(None) != value:
        working.put(None, KEY, value)


def put(name: str, value: Any) -> None:
    """
    把一个属性整个换成 value，写进当前缓冲区
    Keyword arguments:
    name -- ACHIEVEMENT 的属性名
    value -- 新值
    """
    old = _data(None)
    new = _encode(value)
    if _encode(_decode(old[name])) != new:
        working.put(None, KEY, {**old, name: new})


def add(name: str, by: int = 1) -> None:
    """
    计数加 by，同 achievement.name += by
    Keyword arguments:
    name -- 计数的属性名
    by -- 增量
    """
    put(name, get(name) + by)


def append(name: str, item: Any) -> None:
    """
    列表末尾加上 item，同 achievement.name.append(item)
    Keyword arguments:
    name -- 列表的属性名
    item -- 新的一项
    """
    put(name, [*get(name), item])


def set_entry(name: str, key: int, value: Any) -> None:
    """
    字典的一项设为 value，同 achievement.name[key] = value
    Keyword arguments:
    name -- 字典的属性名
    key -- 键
    value -- 值
    """
    put(name, {**get(name), key: value})


def add_entry(name: str, key: int, by: int = 1) -> None:
    """
    字典的一项加 by，没有时从 0 加起，同 setdefault(key, 0) 后 [key] += by
    Keyword arguments:
    name -- 字典的属性名
    key -- 键
    by -- 增量
    """
    values = get(name)
    set_entry(name, key, values.get(key, 0) + by)


def append_entry(name: str, key: int, item: Any) -> None:
    """
    字典的一项是列表，item 不在里面时加到末尾，没有这一项时从空列表开始
    Keyword arguments:
    name -- 字典的属性名
    key -- 键
    item -- 新的一项
    """
    values = get(name)
    listed = values.get(key, [])
    if item not in listed:
        set_entry(name, key, [*listed, item])


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从存档缓存里删掉 achievement，它的各个属性写进当前缓冲区
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 补上或换掉的项数，计法同 save_handle.update_dict_with_default
    """
    default = {"achievement": game_type.ACHIEVEMENT()}
    found, count = pickled.take(loaded_dict, default, version)
    if found:
        restore(
            cast(Mapping[str, core.JSON], _encode(vars(found["achievement"])))
        )
    return count
