"""
缓存文件不写的字段
==================
缓存文件是存档目录里的文件 "1"。UNSAVED 按类列出缓存文件不写的字段。
其中一部分字段能由数据文件或别的状态算出，读档时 save_handle.install_save 重新算出它们。
其余是类里没有声明的字段名，旧存档里可能还存着它们。
dump 写缓存文件时略过这些字段。别处的 pickle（如 draft.py 的复制）照常带上它们。
dump 还把角色模板里与 character_config.character_tem_list 是同一个对象的条目写成 None。
游戏里生成的模板照常写入，如游戏中出生的孩子的模板。
restore 在读档解开缓存文件之后运行，它补全 dump 略过的内容。
fill_defaults 在读档补默认值之前运行，dump 略过的字段因此不计入跨版本更新的条数。
本模块不登记行动、事件或规则，也不在 LOAD_ORDER 里。
"""

import copyreg
import pickle
from typing import IO, Any

from Script.Config import character_config
from Script.Core import game_type

UNSAVED: dict[type, frozenset[str]] = {
    game_type.Cache: frozenset(
        {"map_data", "recipe_data", "sun_phase", "moon_phase"}
    ),
    game_type.Rhodes_Island: frozenset(
        {
            "warehouse_capacity",
            "people_max",
            "visitor_max",
            "medical_bed_limit",
            "life_zone_max",
            "research_zone_max",
            "soldier_max",
        }
    ),
    game_type.Character: frozenset({"hit_point_tem", "mana_point_tem"}),
}
""" 缓存文件不写的字段，类: 字段名 """


def _reduce(obj: Any) -> tuple[Any, ...]:
    reduced = obj.__reduce_ex__(pickle.DEFAULT_PROTOCOL)
    func, args, saved, *rest = reduced
    names = UNSAVED[type(obj)]
    state = {k: v for k, v in saved.items() if k not in names}
    templates = state.get("npc_tem_data")
    if type(obj) is game_type.Cache and isinstance(templates, dict):
        config = character_config.character_tem_list
        state["npc_tem_data"] = {
            k: None if v is config.get(k) else v for k, v in templates.items()
        }
    return (func, args, state, *rest)


def dump(value: object, file: IO[bytes]) -> None:
    """
    用 pickle 把 value 写进 file。UNSAVED 列出的字段不写。角色模板里与配置是同一个对象的条目写成 None。
    Keyword arguments:
    value -- 要写的对象，存档时是游戏缓存
    file -- 以二进制写入方式打开的文件
    """
    pickler = pickle.Pickler(file)
    pickler.dispatch_table = {
        **copyreg.dispatch_table,
        **dict.fromkeys(UNSAVED, _reduce),
    }
    pickler.dump(value)


def restore(loaded: game_type.Cache) -> None:
    """
    补全刚解开的缓存。删掉缓存、rhodes_island 和每个角色上旧存档带来的 UNSAVED 字段。
    写成 None 的角色模板换回配置的模板。配置里没有该键的条目直接删掉。
    Keyword arguments:
    loaded -- 刚解开的游戏缓存
    """
    state = vars(loaded)
    holders: list[object] = [loaded, state.get("rhodes_island")]
    characters = state.get("character_data")
    if isinstance(characters, dict):
        holders.extend(characters.values())
    for holder in holders:
        names = UNSAVED.get(type(holder))
        for name in names & vars(holder).keys() if names else ():
            del vars(holder)[name]
    templates = state.get("npc_tem_data")
    if isinstance(templates, dict):
        config = character_config.character_tem_list
        for key in [k for k, v in templates.items() if v is None]:
            if key in config:
                templates[key] = config[key]
            else:
                del templates[key]


def fill_defaults(loaded: dict[str, Any], default: game_type.Cache) -> None:
    """
    读档补默认值之前，把缓存文件不写的字段设成新缓存里的值。
    这样 save_handle.update_dict_with_default 不把它们算作跨版本更新，读档后面再重新算出它们。
    Keyword arguments:
    loaded -- 刚解开的游戏缓存的属性字典
    default -- 新建的游戏缓存，带着各字段的默认值
    """
    pairs: list[tuple[dict[str, Any], object]] = [(loaded, default)]
    base = loaded.get("rhodes_island")
    if isinstance(base, game_type.Rhodes_Island):
        pairs.append((vars(base), default.rhodes_island))
    for state, holder in pairs:
        defaults = vars(holder)
        for name in UNSAVED[type(holder)] & (defaults.keys() - state.keys()):
            state[name] = defaults[name]
