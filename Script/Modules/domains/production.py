"""
基地生产线的全局键 base.production
==================================
值是 {种类: {"lines": {线id的字符串: Line}, "workers": [角色id]}}，种类见 KINDS。
没有这个键时读 DEFAULT：0 号流水线生产配方 1，药田与温室的 0 号线不生产，三类都没有工人。
写入整值替换这个键。新值与旧值相同时不写。
"""

from collections.abc import Iterable, Mapping
from typing import Any, TypedDict, cast

from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working
from Script.Modules.domains import chara_life
from Script.Modules.domains import identity

KEY = "base.production"
""" 生产线在全局数据里的键 """
KINDS = {"assembly": 121, "herb_garden": 161, "green_house": 162}
""" 生产线的种类到负责它的职位id：assembly 是制造加工区的流水线，herb_garden 是药田，green_house 是温室 """


class Line(TypedDict):
    """一条生产线"""

    product: int
    """ 生产的东西：流水线是生产配方id，药田与温室是资源id，0 为不生产 """
    main: int
    """ 主负责人的角色id，0 为空缺 """
    hour: int
    """ 上次结算时的小时（game_time.now().hour） """


IDLE: Line = {"product": 0, "main": 0, "hour": 0}
""" 新开放的生产线：不生产，主负责人空缺，上次结算记作 0 时 """
DEFAULT: Mapping[str, Mapping[str, object]] = {
    "assembly": {"lines": {"0": {**IDLE, "product": 1}}, "workers": ()},
    "herb_garden": {"lines": {"0": IDLE}, "workers": ()},
    "green_house": {"lines": {"0": IDLE}, "workers": ()},
}
""" 没有 base.production 时读到的值 """

working.register(KEY, cast(core.JSON, DEFAULT))


def _table(game: core.GameState | None = None) -> Mapping[str, Mapping]:
    return cast(Mapping[str, Mapping], working.get(None, KEY, game))


def _put_kind(kind: str, **part: object) -> None:
    table = _table()
    new = {**table, kind: {**table[kind], **part}}
    if new != table:
        working.put(None, KEY, cast(core.JSON, new))


def lines(kind: str, game: core.GameState | None = None) -> dict[int, Line]:
    """
    一类生产线
    Keyword arguments:
    kind -- KINDS 里的种类
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 线id（int）到生产线，按存下的顺序
    """
    stored = cast(Mapping[str, Line], _table(game)[kind]["lines"])
    return {int(line_id): line for line_id, line in stored.items()}


def workers(kind: str, game: core.GameState | None = None) -> list[int]:
    """
    一类生产线的工人名单：流水线的是生产工人，药田与温室的是种植员
    Keyword arguments:
    kind -- KINDS 里的种类
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    list -- 角色id，按名单的顺序
    """
    return list(cast(Iterable[int], _table(game)[kind]["workers"]))


def _put_lines(kind: str, new: Mapping[int, Line]) -> None:
    stored = {str(line_id): line for line_id, line in new.items()}
    _put_kind(kind, lines=stored)


def set_line(kind: str, line_id: int, **fields: int) -> None:
    """
    改一条生产线的几项，其余项不变
    Keyword arguments:
    kind -- KINDS 里的种类
    line_id -- 线id
    fields -- Line 的项名到新值
    """
    current = lines(kind)
    current[line_id] = cast(Line, {**current[line_id], **fields})
    _put_lines(kind, current)


def open_lines(kind: str, line_ids: Iterable[int]) -> None:
    """
    开放这类还没有的生产线。新线取 IDLE，按 line_ids 的顺序排在最后
    Keyword arguments:
    kind -- KINDS 里的种类
    line_ids -- 这类应有的线id
    """
    current = lines(kind)
    for line_id in line_ids:
        current.setdefault(line_id, {**IDLE})
    _put_lines(kind, current)


def set_workers(kind: str, cids: Iterable[int]) -> None:
    """
    换掉一类生产线的工人名单
    Keyword arguments:
    kind -- KINDS 里的种类
    cids -- 角色id，按名单的顺序
    """
    _put_kind(kind, workers=tuple(cids))


def appoint(kind: str, line_id: int, chara_id: int) -> None:
    """
    任命或撤下一条生产线的主负责人。角色不在这类的工人名单里时不改。
    角色已是这条线的主负责人时撤下。否则先撤下这名角色在这类其他线上的任命，再任命到这条线
    Keyword arguments:
    kind -- KINDS 里的种类
    line_id -- 线id
    chara_id -- 角色id
    """
    if chara_id not in workers(kind):
        return
    current = lines(kind)
    if current[line_id]["main"] == chara_id:
        current[line_id] = {**current[line_id], "main": 0}
    else:
        for other, line in current.items():
            if line["main"] == chara_id:
                current[other] = {**line, "main": 0}
        current[line_id] = {**current[line_id], "main": chara_id}
    _put_lines(kind, current)


def change_product(kind: str, line_id: int, product: int) -> None:
    """
    换一条生产线生产的东西。线正在生产且这个小时还没结算过时不换
    Keyword arguments:
    kind -- KINDS 里的种类
    line_id -- 线id
    product -- 新的生产配方id（流水线）或资源id（药田、温室）
    """
    line = lines(kind)[line_id]
    if line["product"] == 0 or line["hour"] == game_time.now().hour:
        set_line(kind, line_id, product=product)


def release_mains(kind: str) -> None:
    """
    职位不是这类生产线职位的主负责人设为 0（空缺）。不在身份表（identity.characters）里的主负责人保留
    Keyword arguments:
    kind -- KINDS 里的种类
    """
    characters = identity.table()
    current = lines(kind)
    for line_id, line in current.items():
        main = line["main"]
        if (
            main
            and main in characters
            and chara_life.work_type(main) != KINDS[kind]
        ):
            current[line_id] = {**line, "main": 0}
    _put_lines(kind, current)


def remap(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把三类生产线的主负责人与工人名单里的旧id换成新id
    Keyword arguments:
    old_to_new -- 旧id到新id，表里没有的id不变
    """
    for kind in KINDS:
        current = lines(kind)
        for line_id, line in current.items():
            if line["main"]:
                main = old_to_new.get(line["main"], line["main"])
                current[line_id] = {**line, "main": main}
        _put_lines(kind, current)
        set_workers(kind, (old_to_new.get(c, c) for c in workers(kind)))


PICKLED_LINES = {
    "assembly_line": "assembly",
    "herb_garden_line": "herb_garden",
    "green_house_line": "green_house",
}
""" 版本 8 之前的存档里，罗德岛对象上的生产线属性名到种类 """
PICKLED_WORKERS = {
    "production_worker_ids": "assembly",
    "herb_garden_operator_ids": "herb_garden",
    "green_house_operator_ids": "green_house",
}
""" 版本 8 之前的存档里，罗德岛对象上的工人名单属性名到种类 """
PICKLED_TYPES = {
    **dict.fromkeys(PICKLED_LINES, dict),
    **dict.fromkeys(PICKLED_WORKERS, list),
}
""" 这六个属性在罗德岛对象上应有的类型。类型不是这一种的值不导入 """


def _cid(raw: object) -> int:
    """
    把旧存档里的一个角色id值换成 int，规则同 old_chara_to_new.normalize_single_character_id。
    列表、元组与集合取第一个不是 0 的id，字典先看值再看键，认不出时为 0。
    本模块另写一份，因为 old_chara_to_new 导入本模块
    Keyword arguments:
    raw -- 存下的值
    Return arguments:
    int -- 角色id
    """
    if isinstance(raw, int):
        return raw
    if isinstance(raw, Mapping):
        raw = (*raw.values(), *raw.keys())
    if isinstance(raw, (list, tuple, set)):
        return next((cid for cid in map(_cid, raw) if cid), 0)
    try:
        return int(cast(Any, raw))
    except (TypeError, ValueError):
        return 0


def _pickled_line(raw: object) -> Line:
    """
    把旧存档的一条生产线 [生产, 主负责人, 效率, 待换生产, 上次结算的小时] 换成 Line，效率与待换生产不留。
    元组照列表读，不足 5 项时补 0，不是列表或元组时当作全 0。主负责人由 _cid 换成 int
    Keyword arguments:
    raw -- 存下的值
    Return arguments:
    Line -- 生产线
    """
    items = list(raw) if isinstance(raw, (list, tuple)) else []
    items += [0] * (5 - len(items))
    return {"product": items[0], "main": _cid(items[1]), "hour": items[4]}


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED_TYPES 里的属性，把其中类型相符的值写进当前缓冲区。
    对象带着其中任何一个属性时，三类生产线整表写进 base.production。
    缺了或类型不符的生产线表与工人名单取 DEFAULT 里的值。对象上没有这些属性时什么也不写
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 版本 8 之前的存档里缺了或类型不符的属性个数，计法同 save_handle.update_dict_with_default。版本 8 的存档为 0
    """
    attrs = vars(loaded_dict["rhodes_island"])
    found = {name: attrs.pop(name) for name in PICKLED_TYPES if name in attrs}
    kept = {n: v for n, v in found.items() if type(v) is PICKLED_TYPES[n]}
    table = {kind: dict(part) for kind, part in DEFAULT.items()}
    for name, kind in PICKLED_LINES.items():
        if name in kept:
            raw = kept[name].items()
            table[kind]["lines"] = {str(i): _pickled_line(v) for i, v in raw}
    for name, kind in PICKLED_WORKERS.items():
        if name in kept:
            table[kind]["workers"] = tuple(kept[name])
    if found:
        working.put(None, KEY, cast(core.JSON, table))
    return len(PICKLED_TYPES) - len(kept) if version < 8 else 0
