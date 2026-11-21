"""
文职部招募的全局键 base.recruit_lines 与 base.recruited
=====================================================
base.recruit_lines 是 {招募线id的字符串: Line}，按开放的先后排列。没有这个键时读 DEFAULT：只有 0 号线，各项为 0。
base.recruited 是已招募、等待博士确认的角色id，从小到大排列。没有这个键时读空表。
写入整值替换键。新值与旧值相同时不写。
"""

from collections.abc import Iterable, Mapping
from typing import Any, TypedDict, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

LINES = "base.recruit_lines"
""" 招募线在全局数据里的键 """
PENDING = "base.recruited"
""" 等待确认的招募角色在全局数据里的键 """


class Line(TypedDict):
    """一条招募线"""

    progress: float
    """ 招募进度，满 100 时结算 """
    strategy: int
    """ 招募策略id，11 为停止招募 """
    main: int
    """ 主招聘专员的角色id，0 为空缺 """


IDLE: Line = {"progress": 0, "strategy": 0, "main": 0}
""" 新开放的招募线 """
DEFAULT: Mapping[str, Line] = {"0": IDLE}
""" 没有 base.recruit_lines 时读到的值 """

working.register(LINES, cast(core.JSON, DEFAULT))
working.register(PENDING, ())


def lines(game: core.GameState | None = None) -> dict[int, Line]:
    """
    全部招募线。返回新建的 dict，改它不改存的值
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 线id 到招募线，按存下的顺序
    """
    stored = cast(Mapping[str, Line], working.get(None, LINES, game))
    return {int(i): cast(Line, dict(line)) for i, line in stored.items()}


def _put(key: str, new: object) -> None:
    if new != working.get(None, key):
        working.put(None, key, cast(core.JSON, new))


def put_lines(new: Mapping[int, Line]) -> None:
    """
    换掉全部招募线
    Keyword arguments:
    new -- 线id 到招募线，按要存的顺序
    """
    _put(LINES, {str(i): dict(line) for i, line in new.items()})


def set_line(line_id: int, **fields: float) -> None:
    """
    改一条招募线的几项，其余项不变
    Keyword arguments:
    line_id -- 线id
    fields -- Line 的项名到新值
    """
    current = lines()
    current[line_id] = cast(Line, {**current[line_id], **fields})
    put_lines(current)


def open_lines(line_ids: Iterable[int]) -> None:
    """
    开放还没有的招募线。新线取 IDLE，按 line_ids 的顺序排在最后
    Keyword arguments:
    line_ids -- 应有的线id
    """
    current = lines()
    for line_id in line_ids:
        current.setdefault(line_id, {**IDLE})
    put_lines(current)


def appoint(line_id: int, chara_id: int) -> None:
    """
    任命或撤下一条招募线的主招聘专员。角色已是这条线的主招聘专员时撤下，
    否则先撤下这名角色在其他线上的任命，再任命到这条线
    Keyword arguments:
    line_id -- 线id
    chara_id -- 角色id
    """
    current = lines()
    if current[line_id]["main"] == chara_id:
        current[line_id]["main"] = 0
    else:
        for line in current.values():
            if line["main"] == chara_id:
                line["main"] = 0
        current[line_id]["main"] = chara_id
    put_lines(current)


def pending(game: core.GameState | None = None) -> set[int]:
    """
    已招募、等待确认的角色。返回新建的 set
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    set -- 角色id
    """
    return set(cast(Iterable[int], working.get(None, PENDING, game)))


def set_pending(cids: Iterable[int]) -> None:
    """
    换掉等待确认的角色
    Keyword arguments:
    cids -- 角色id
    """
    _put(PENDING, tuple(sorted(set(cids))))


def remap(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把主招聘专员（空缺的除外）与等待确认的角色里的旧id换成新id
    Keyword arguments:
    old_to_new -- 旧id到新id，表里没有的id不变
    """
    current = lines()
    for line in current.values():
        if line["main"]:
            line["main"] = old_to_new.get(line["main"], line["main"])
    put_lines(current)
    set_pending(old_to_new.get(cid, cid) for cid in pending())


def chara_id(raw: object) -> int:
    """
    把旧存档里的一个角色id值换成 int，规则同 old_chara_to_new.normalize_single_character_id：
    列表、元组与集合取第一个不是 0 的id，字典先看值再看键，认不出时为 0
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
        return next((cid for cid in map(chara_id, raw) if cid), 0)
    try:
        return int(cast(Any, raw))
    except (TypeError, ValueError):
        return 0


PICKLED = {"recruit_line": dict, "recruited_id": set}
"""
版本 11 之前的存档里，罗德岛对象上这两项的属性名与应有的类型。类型不是这一种的值不导入，
只有待确认招募存成一个非 0 的 int 时，读作只有这一人的集合
"""


def _pickled_line(raw: object) -> Line:
    """
    把旧存档的一条招募线 [进度, 策略id, 主招聘专员, 效率] 换成 Line，效率不留。
    元组照列表读，不足 3 项时补 0，不是列表或元组时当作全 0。主招聘专员由 chara_id 换成 int
    Keyword arguments:
    raw -- 存下的值
    Return arguments:
    Line -- 招募线
    """
    items = list(raw) if isinstance(raw, (list, tuple)) else []
    items += [0] * (3 - len(items))
    main = chara_id(items[2])
    return {"progress": items[0], "strategy": items[1], "main": main}


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED 里的属性，把类型相符的值写进当前缓冲区
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 版本 11 之前的存档里缺了或类型不符的属性个数，计法同 save_handle.update_dict_with_default
    """
    attrs = vars(loaded_dict["rhodes_island"])
    found = {name: attrs.pop(name) for name in PICKLED if name in attrs}
    single = found.get("recruited_id")
    if type(single) is int and single:
        # 原来 old_chara_to_new.migrate_old_save_data 在补默认值之前把它换成集合
        found["recruited_id"] = {single}
    kept = {n: v for n, v in found.items() if type(v) is PICKLED[n]}
    if "recruit_line" in kept:
        raw = kept["recruit_line"].items()
        put_lines({i: _pickled_line(v) for i, v in raw})
    if "recruited_id" in kept:
        set_pending(kept["recruited_id"])
    return len(PICKLED) - len(kept) if version < 11 else 0
