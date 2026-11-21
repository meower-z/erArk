"""
角色的生理需求与体力等数值：角色的键 body.needs
===============================================
值的各项见 Needs：疲劳、饥饿、尿意、乳汁，体力、气力、理智与它们的上限，愤怒、熟睡、欲望、醉酒。
角色没有这一项时读默认值 DEFAULT（饥饿 240，其余 0）。
这个键归本模块的规则 apply 所有。代码不整值替换它，而是用 add 或 set 记一次操作，规则按顺序把操作套到当前值上。
全局键 needs.sleep_noise 记睡中被吵醒、还没结算的角色：{被吵醒的角色id的字符串: 产生动静的角色id}，没有这一项时为空。
它整值替换，值没变时不写。
"""

from collections.abc import Mapping
from typing import Any, TypedDict, cast

from Script.Core.num import Num
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import pickled

KEY = "body.needs"
""" 生理需求在角色数据里的键 """
NOISE = "needs.sleep_noise"
""" 睡中被吵醒、还没结算的角色的全局键 """


class Needs(TypedDict):
    """一个角色的生理需求，每项是 int 或 Fraction"""

    tired: Num
    """ 疲劳 """
    hunger: Num
    """ 饥饿 """
    urine: Num
    """ 尿意 """
    milk: Num
    """ 乳汁 """
    hit: Num
    """ 体力 """
    hit_max: int
    """ 体力上限 """
    mana: Num
    """ 气力 """
    mana_max: int
    """ 气力上限 """
    sanity: Num
    """ 理智 """
    sanity_max: int
    """ 理智上限 """
    angry: int
    """ 愤怒值 """
    sleep: Num
    """ 熟睡值，0 到 100，越大睡得越深 """
    desire: int
    """ 欲望值，不设上限 """
    drunk: Num
    """ 醉酒值，0 到 100 """


DEFAULT: Needs = {
    "tired": 0,
    "hunger": 240,
    "urine": 0,
    "milk": 0,
    "hit": 0,
    "hit_max": 0,
    "mana": 0,
    "mana_max": 0,
    "sanity": 0,
    "sanity_max": 0,
    "angry": 0,
    "sleep": 0,
    "desire": 0,
    "drunk": 0,
}
""" 角色没有 body.needs 时读到的值 """


def fold(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    """
    一次操作。add 给 stat 加 by，再按给出的 max、min 夹住，值与类型同 min(x + by, max)、max(x + by, min)。
    set 把给出的各项换成新值，别的项不变。
    Keyword arguments:
    old -- 当前的需求
    op -- "add" 或 "set"，别的名字报 ValueError
    operand -- add 时为 {"stat", "by", 可选的 "max" 与 "min"}，set 时为 {需求项: 新值}
    Return arguments:
    JSON -- 新的需求
    """
    values = dict(cast(Mapping[str, Num], old))
    args = cast(Mapping[str, Num], operand)
    if op == "set":
        values.update(args)
    elif op == "add":
        stat = str(args["stat"])
        value = values[stat] + args["by"]
        if "max" in args:
            value = min(value, args["max"])
        if "min" in args:
            value = max(value, args["min"])
        values[stat] = value
    else:
        raise ValueError(f"{KEY} has no op {op}")
    return cast(core.JSON, values)


working.register(KEY, cast(core.JSON, DEFAULT), fold)
working.register(NOISE, {})


@core.rule(KEY)
def apply(game: core.GameState, change: core.Change) -> core.GameState:
    """
    body.needs 的规则：用 working.fold_all 把 Change 带的一串操作依次套到角色当前的需求上
    Keyword arguments:
    game -- 状态
    change -- working.flush 给的 Change，operand 为 (操作名, 操作数) 的序列
    Return arguments:
    GameState -- 新状态
    """
    old = core.value(game, change.who, KEY)
    ops = cast(tuple[core.JSON, ...], change.operand)
    return core.with_value(
        game, change.who, KEY, working.fold_all(KEY, old, ops)
    )


def of(cid: int, game: core.GameState | None = None) -> Needs:
    """
    角色的生理需求
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    Needs -- 生理需求，没有这一项时为 DEFAULT
    """
    return cast(Needs, working.get(str(cid), KEY, game))


def add(
    cid: int,
    stat: str,
    by: Num,
    *,
    max: Num | None = None,
    min: Num | None = None,
) -> None:
    """
    给一项需求加 by，再按给出的 max、min 夹住，作为一次操作记进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    stat -- 需求项
    by -- 加的量，可以为负
    max -- 上限，None 时不夹
    min -- 下限，None 时不夹
    """
    operand: dict[str, core.JSON] = {"stat": stat, "by": by}
    if max is not None:
        operand["max"] = max
    if min is not None:
        operand["min"] = min
    working.change(str(cid), KEY, "add", operand)


def set(cid: int, **values: Num) -> None:
    """
    把给出的需求项换成新值，作为一次操作记进当前缓冲区，别的项不变
    Keyword arguments:
    cid -- 角色id
    values -- 需求项到新值
    """
    working.change(str(cid), KEY, "set", cast(core.JSON, values))


def noise_woken() -> dict[int, int]:
    """
    睡中被吵醒、还没结算的角色
    Return arguments:
    dict -- 被吵醒的角色id 到产生动静的角色id，键为 int 的新字典
    """
    woken = cast(Mapping[str, int], working.get(None, NOISE))
    return {int(cid): by for cid, by in woken.items()}


def note_woken(cid: int, by: int) -> None:
    """
    记下 cid 被 by 的动静吵醒，写进当前缓冲区
    Keyword arguments:
    cid -- 被吵醒的角色id
    by -- 产生动静的角色id
    """
    woken = noise_woken()
    if woken.get(cid) != by or cid not in woken:
        _put_woken({**woken, cid: by})


def take_woken(cid: int) -> int:
    """
    取出 cid 的记录，同 dict.pop(cid)，写进当前缓冲区
    Keyword arguments:
    cid -- 被吵醒的角色id，没有记录时报 KeyError
    Return arguments:
    int -- 产生动静的角色id
    """
    woken = noise_woken()
    by = woken.pop(cid)
    _put_woken(woken)
    return by


def _put_woken(woken: Mapping[int, int]) -> None:
    working.put(None, NOISE, {str(cid): by for cid, by in woken.items()})


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从存档缓存里删掉 noise_woken，记录写进当前缓冲区
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 补上或换掉的项数，计法同 save_handle.update_dict_with_default
    """
    found, count = pickled.take(loaded_dict, {"noise_woken": {}}, version)
    if found and noise_woken() != found["noise_woken"]:
        _put_woken(found["noise_woken"])
    return count
