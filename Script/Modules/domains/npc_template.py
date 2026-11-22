"""
世界生成的角色模板：全局键 roster.npc_templates
===============================================
roster.npc_templates 存局内生成的角色模板（如读档补出的空白模板），新周目沿用。
键的值是 {模板编号的字符串: {属性名: 值}}，只写 NpcTem() 声明的属性。
字典属性写入时把键转为字符串，读回时把键转回整数。列表属性读回为列表。
缺省时读到空字典。写入整值替换该键，值未变时不写。
数据文件里的静态模板留在 character_config.character_tem_list，不写进这个键，也不写进存档。
table、ids 与 get 合并静态模板与局内生成的模板，同编号时以局内生成的为准。
"""

from collections.abc import Mapping
from typing import Any, cast

from Script.Config import character_config
from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.domains import abilities
from Script.Modules.gameplay_resolution import working

KEY = "roster.npc_templates"
""" 局内生成的角色模板在全局数据里的键 """
FIELDS = tuple(vars(game_type.NpcTem()))
""" NpcTem 声明的属性名，写入全局键时只保留这些属性 """

working.register(KEY, {})


def _stored(game: core.GameState | None) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], working.get(None, KEY, game))


def _encode(template: game_type.NpcTem) -> dict[str, Any]:
    attrs = vars(template)
    out: dict[str, Any] = {}
    for name in FIELDS:
        if name not in attrs:
            continue
        value = attrs[name]
        if isinstance(value, dict):
            out[name] = {str(k): v for k, v in value.items()}
        elif isinstance(value, list | tuple):
            out[name] = list(value)
        else:
            out[name] = value
    return out


def _decode(raw: Mapping[str, Any]) -> game_type.NpcTem:
    template = game_type.NpcTem()
    for name, value in raw.items():
        if isinstance(value, Mapping):
            setattr(template, name, {int(k): v for k, v in value.items()})
        elif isinstance(value, tuple | list):
            setattr(template, name, list(value))
        else:
            setattr(template, name, value)
    return template


def table(game: core.GameState | None = None) -> dict[int, game_type.NpcTem]:
    """
    合并静态模板与局内生成的模板，返回新字典。
    静态条目是 character_config.character_tem_list 里的原对象，排在前面。
    局内生成的条目每次调用都新构造 NpcTem 对象，按添加顺序排在后面，同编号时替换原位置。
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict[int, game_type.NpcTem] -- 编号到角色模板的映射
    """
    out = dict(character_config.character_tem_list)
    for key, raw in _stored(game).items():
        out[int(key)] = _decode(raw)
    return out


def ids(game: core.GameState | None = None) -> list[int]:
    """
    按 table() 的顺序返回全部角色模板的编号列表，不构造模板对象
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    list[int] -- 去重后的角色模板编号列表
    """
    out = dict.fromkeys(character_config.character_tem_list)
    out.update(dict.fromkeys(map(int, _stored(game))))
    return list(out)


def get(
    cid: int, game: core.GameState | None = None
) -> game_type.NpcTem | None:
    """
    按编号取一个角色模板。
    存在局内生成的模板时新构造并返回它，否则返回静态模板对象，都没有时返回 None。
    Keyword arguments:
    cid -- 角色模板编号
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    game_type.NpcTem | None -- 找到的角色模板，没有时为 None
    """
    raw = _stored(game).get(str(cid))
    if raw is not None:
        return _decode(raw)
    return character_config.character_tem_list.get(cid)


def _write(new: Mapping[str, Any]) -> None:
    if not working.same(_stored(None), new):
        working.put(None, KEY, dict(new))


def add(template: game_type.NpcTem) -> None:
    """
    把局内生成的角色模板按 template.AdvNpc 写进当前缓冲区，同编号已有条目会被替换
    Keyword arguments:
    template -- 要写入的角色模板
    """
    _write({**_stored(None), str(template.AdvNpc): _encode(template)})


def remove(cid: int) -> None:
    """
    从当前缓冲区移除指定编号的局内生成模板，没有该编号时不做任何修改
    Keyword arguments:
    cid -- 要移除的角色模板编号
    """
    _write({k: v for k, v in _stored(None).items() if k != str(cid)})


def lift(loaded_dict: dict[str, Any]) -> dict[str, Any]:
    """
    读档解开缓存后调用。缓存属性字典里没有 npc_tem_data 时填入当前缓冲区的 table()，已有时原样保留。
    Keyword arguments:
    loaded_dict -- 存档缓存的属性字典，原地修改
    Return arguments:
    dict[str, Any] -- 传入的 loaded_dict
    """
    if "npc_tem_data" not in loaded_dict:
        loaded_dict["npc_tem_data"] = table()
    return loaded_dict


def adopt_old_save(loaded_dict: dict[str, Any]) -> int:
    """
    读档重建角色循环之后调用。从 loaded_dict 弹出 npc_tem_data，把其中不是静态配置原对象的条目写入当前缓冲区。
    写入前从每条模板的 Talent 中去掉 abilities.GONE_TALENTS（Talent.csv 里没有的 6 与 7），返回去掉的条目总数。
    Keyword arguments:
    loaded_dict -- 存档缓存的属性字典，原地弹出 npc_tem_data
    Return arguments:
    int -- 从局内生成模板中去掉的素质条目总数
    """
    templates = loaded_dict.pop("npc_tem_data")
    config = character_config.character_tem_list
    dropped = 0
    generated: dict[str, Any] = {}
    for key, template in templates.items():
        if template is config.get(key):
            continue
        raw = _encode(template)
        talent = cast(dict[str, Any], raw.get("Talent", {}))
        for tid in abilities.GONE_TALENTS:
            dropped += int(talent.pop(str(tid), None) is not None)
        generated[str(key)] = raw
    _write(generated)
    return dropped
