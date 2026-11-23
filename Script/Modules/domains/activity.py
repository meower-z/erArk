"""
角色的活动：状态、行为、二段行为、事件、位置、交互对象与死亡
============================================================
角色的十个键都整值写入（working.put）。角色没有某个键时读到下面的默认值：
- activity.state：当前状态，int 或 str，默认 0。
- activity.last_behaviors：之前的行为列表，默认 [0]。
- activity.behavior：当前行为，只存与 game_type.Behavior() 不同的字段。start_time 存内核时钟的分钟数，
  默认的 datetime(1, 1, 1) 不存。target_food 存食物记录（kitchen.record）加 uid 的字符串。
- activity.second_behavior：二段行为，只存不为 0 的 {二段行为id: 值}。second_order 里的id按它的顺序排，
  配置里没有的id排在后面。
- activity.must_settle、activity.must_show：必须结算、必须显示的二段行为id列表，默认空。
- activity.event：当前事件，只存与 game_type.Chara_Event() 不同的字段。
- activity.position：所在场景的坐标，默认 ["0", "0"]。
- activity.target：交互对象id，默认 0。
- activity.dead：是否已死亡，默认 False。
角色不在花名册上时，这些键存在全局键 roster.offstage 里这个角色的一项下。
读函数给了 game 时只读这个 GameState，事件触发函数这样读。没给 game 时读当前缓冲区，含还没套用的写入。
target_as 在块内临时覆盖一个角色的交互对象（仅未给 game 时），不写状态也不用缓冲区。
读出的列表是新列表。behavior 与 event 读出只读的 Behavior、Event，属性名与类型同 game_type.Behavior、Chara_Event。
读档时 adopt_old_save 把旧存档角色对象上的这十个属性写进这些键。
"""

from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from functools import cache as memoised
from typing import Any, cast

from Script.Config import game_config
from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.domains.activity_record import (
    EVENT_DEFAULT,
    Behavior,
    Event,
    record,
)
from Script.Modules.gameplay_resolution import working

STATE = "activity.state"
LAST = "activity.last_behaviors"
BEHAVIOR = "activity.behavior"
SECOND = "activity.second_behavior"
MUST_SETTLE = "activity.must_settle"
MUST_SHOW = "activity.must_show"
EVENT = "activity.event"
POSITION = "activity.position"
TARGET = "activity.target"
DEAD = "activity.dead"
KEYS = (
    STATE,
    LAST,
    BEHAVIOR,
    SECOND,
    MUST_SETTLE,
    MUST_SHOW,
    EVENT,
    POSITION,
    TARGET,
    DEAD,
)
""" 十个角色键 """

working.register(STATE, 0)
working.register(LAST, (0,))
working.register(BEHAVIOR, {})
working.register(SECOND, {})
working.register(MUST_SETTLE, ())
working.register(MUST_SHOW, ())
working.register(EVENT, {})
working.register(POSITION, ("0", "0"))
working.register(TARGET, 0)
working.register(DEAD, False)


def _get(cid: int, key: str, game: core.GameState | None) -> Any:
    return working.get(str(cid), key, game)


def state(cid: int, game: core.GameState | None = None) -> int | str:
    """
    角色当前状态
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个 GameState，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    int | str -- 状态
    """
    return cast(int | str, _get(cid, STATE, game))


def set_state(cid: int, value: int | str) -> None:
    """把角色当前状态换成 value，写进当前缓冲区"""
    working.put(str(cid), STATE, value)


def last_behaviors(cid: int, game: core.GameState | None = None) -> list[Any]:
    """角色之前的行为列表，新列表"""
    return list(_get(cid, LAST, game))


def set_last_behaviors(cid: int, values: Iterable[Any]) -> None:
    """把角色之前的行为列表换成 values，写进当前缓冲区"""
    working.put(str(cid), LAST, tuple(values))


def behavior(cid: int, game: core.GameState | None = None) -> Behavior:
    """
    角色当前行为
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个 GameState，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    Behavior -- 只读的行为，属性同 game_type.Behavior
    """
    return Behavior(_get(cid, BEHAVIOR, game))


def update_behavior(cid: int, **fields: object) -> None:
    """
    改角色当前行为的给出字段，别的字段不变，写进当前缓冲区。
    未知的字段名报 AttributeError，不在整游戏分钟上的开始时间报 ValueError
    Keyword arguments:
    cid -- 角色id
    fields -- 字段名到新值，名字与类型同 game_type.Behavior
    """
    old = _get(cid, BEHAVIOR, None)
    working.put(str(cid), BEHAVIOR, record(old, fields, Behavior))


def set_behavior(cid: int, **fields: object) -> None:
    """
    把角色当前行为换成默认行为再改给出的字段，写进当前缓冲区。
    默认行为的字段同 Behavior()，目标食物是 uid 为 0 的空食物
    Keyword arguments:
    cid -- 角色id
    fields -- 字段名到新值，名字与类型同 game_type.Behavior
    """
    working.put(str(cid), BEHAVIOR, record({}, fields, Behavior))


@memoised
def second_order() -> dict[str, int]:
    """
    二段行为的顺序：配置里带“二段结算”标签的行为，按配置的顺序
    Return arguments:
    dict -- 二段行为id 到序号
    """
    ids = (
        i for i, b in game_config.config_behavior.items() if "二段结算" in b.tag
    )
    return {behavior_id: n for n, behavior_id in enumerate(ids)}


def second_behaviors(
    cid: int, game: core.GameState | None = None
) -> Mapping[str, int]:
    """
    角色不为 0 的二段行为，直接返回存下的只读映射
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读该 GameState，为 None 时读当前缓冲区
    Return arguments:
    Mapping[str, int] -- 二段行为id到值的只读映射，按 second_order 顺序排列，配置里没有的id排在后面并按写入先后排列
    """
    return cast(Mapping[str, int], _get(cid, SECOND, game))


def second_ids(cid: int, game: core.GameState | None = None) -> list[str]:
    """
    second_order 里的全部二段行为id（值为 0 的也在内），再接角色存着、配置里没有的id
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个 GameState，没有时读当前缓冲区
    Return arguments:
    list -- 二段行为id
    """
    order = second_order()
    return [*order, *(i for i in _get(cid, SECOND, game) if i not in order)]


def second_behavior(
    cid: int, behavior_id: str, game: core.GameState | None = None
) -> int:
    """角色一个二段行为的值，没有时为 0"""
    return cast(int, _get(cid, SECOND, game).get(behavior_id, 0))


def set_second_behaviors(cid: int, values: Mapping[str, int]) -> None:
    """
    把角色的二段行为换成 values，值为 0 的项不存，写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    values -- 二段行为id 到值
    """
    order = second_order()
    kept = [(i, v) for i, v in values.items() if v]
    known = sorted(
        (p for p in kept if p[0] in order), key=lambda p: order[p[0]]
    )
    known.extend(p for p in kept if p[0] not in order)
    working.put(str(cid), SECOND, dict(known))


def set_second_behavior(cid: int, behavior_id: str, value: int) -> None:
    """把角色一个二段行为的值换成 value，写进当前缓冲区"""
    set_second_behaviors(cid, {**second_behaviors(cid), behavior_id: value})


def must_settle(cid: int, game: core.GameState | None = None) -> list[str]:
    """角色必须结算的二段行为id列表，新列表"""
    return list(_get(cid, MUST_SETTLE, game))


def set_must_settle(cid: int, values: Iterable[str]) -> None:
    """把角色必须结算的二段行为id列表换成 values，写进当前缓冲区"""
    working.put(str(cid), MUST_SETTLE, tuple(values))


def must_show(cid: int, game: core.GameState | None = None) -> list[str]:
    """角色必须显示的二段行为id列表，新列表"""
    return list(_get(cid, MUST_SHOW, game))


def set_must_show(cid: int, values: Iterable[str]) -> None:
    """把角色必须显示的二段行为id列表换成 values，写进当前缓冲区"""
    working.put(str(cid), MUST_SHOW, tuple(values))


def event(cid: int, game: core.GameState | None = None) -> Event:
    """角色当前事件，只读，属性同 game_type.Chara_Event"""
    return Event(_get(cid, EVENT, game))


def update_event(cid: int, **fields: object) -> None:
    """改角色当前事件的给出字段，别的字段不变，写进当前缓冲区"""
    old = _get(cid, EVENT, None)
    working.put(str(cid), EVENT, record(old, fields, Event))


def set_event(cid: int, **fields: object) -> None:
    """把角色当前事件换成默认事件（同 Chara_Event()）再改给出的字段，写进当前缓冲区"""
    working.put(str(cid), EVENT, record({}, fields, Event))


def position(cid: int, game: core.GameState | None = None) -> list[str]:
    """
    角色所在场景的坐标
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个 GameState，没有时读当前缓冲区
    Return arguments:
    list -- 坐标，新列表
    """
    return list(_get(cid, POSITION, game))


def set_position(cid: int, value: Iterable[str]) -> None:
    """把角色所在场景的坐标换成 value，写进当前缓冲区"""
    working.put(str(cid), POSITION, tuple(value))


_target_as: dict[int, int] = {}


def target(cid: int, game: core.GameState | None = None) -> int:
    """
    角色当前交互对象的id。未给 game 且在该角色的 target_as 块内时读块内值
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个 GameState，不受 target_as 影响；没有时读 target_as 块或当前缓冲区
    Return arguments:
    int -- 交互对象id
    """
    if game is None and cid in _target_as:
        return _target_as[cid]
    return cast(int, _get(cid, TARGET, game))


def set_target(cid: int, value: int) -> None:
    """
    把角色当前交互对象换成 value，写进当前缓冲区。
    在该角色的 target_as 块内时只改块内值，不写缓冲区
    Keyword arguments:
    cid -- 角色id
    value -- 交互对象id
    """
    if cid in _target_as:
        _target_as[cid] = value
    else:
        working.put(str(cid), TARGET, value)


@contextmanager
def target_as(cid: int, value: int) -> Iterator[None]:
    """
    在 with 块内把角色的交互对象读作 value（仅未给 game 的 target），块内对它的 set_target 只改块内值。
    退出块时撤回这次覆盖，状态不变，不需要缓冲区。判前提、换文本时临时指向别的角色用
    Keyword arguments:
    cid -- 角色id
    value -- 块内读到的交互对象id
    """
    outer = _target_as.get(cid)
    _target_as[cid] = value
    try:
        yield
    finally:
        if outer is None:
            del _target_as[cid]
        else:
            _target_as[cid] = outer


def dead(cid: int, game: core.GameState | None = None) -> bool:
    """角色是否已死亡"""
    return cast(bool, _get(cid, DEAD, game))


def set_dead(cid: int, value: bool) -> None:
    """把角色是否已死亡换成 value，写进当前缓冲区"""
    working.put(str(cid), DEAD, value)


def _given(old: object, fields: Iterable[str]) -> dict[str, Any]:
    """旧对象上属于 fields 的属性；为 None 的不取，读出时得默认值"""
    names = set(fields)
    return {n: v for n, v in vars(old).items() if n in names and v is not None}


PICKLED: Mapping[str, Callable[[int, Any], None]] = {
    "state": set_state,
    "last_behavior_id_list": set_last_behaviors,
    "behavior": lambda cid, b: set_behavior(cid, **_given(b, Behavior._fields)),
    "second_behavior": set_second_behaviors,
    "must_settle_second_behavior_id_list": set_must_settle,
    "must_show_second_behavior_id_list": set_must_show,
    "event": lambda cid, e: set_event(cid, **_given(e, EVENT_DEFAULT)),
    "position": set_position,
    "target_character_id": set_target,
    "dead": set_dead,
}
""" 旧存档角色对象上的属性名到把它的值写进当前缓冲区的函数 """


def adopt_old_save(loaded_dict: dict[str, Any]) -> int:
    """
    install_save 在重建角色之后调用。角色对象上带着 PICKLED 里的属性时，把它们写进当前缓冲区，再从对象上删掉。
    行为id是整数编号时换成行为名。二段行为表里的整数键换成二段行为名，找不到名字的键丢掉
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    Return arguments:
    int -- 这些角色的二段行为表缺的配置项数（second_order 里有、表里没有的id），计入跨版本更新
    """
    count = 0
    for cid, character in loaded_dict["character_data"].items():
        attrs = vars(character)
        if not any(name in attrs for name in PICKLED):
            continue
        attrs["second_behavior"] = _second_ids_to_names(
            attrs.get("second_behavior", {})
        )
        count += sum(
            1 for i in second_order() if i not in attrs["second_behavior"]
        )
        if "behavior" in attrs:
            _behavior_id_to_name(attrs["behavior"])
        for name, write in PICKLED.items():
            if name in attrs:
                write(cid, attrs.pop(name))
    return count


def _behavior_id_to_name(old: game_type.Behavior) -> None:
    from Script.Core import constant

    number_id: object = getattr(old, "behavior_id", None)
    if isinstance(number_id, int):
        for key, number in vars(constant.Behavior_Int).items():
            if not key.startswith("__") and number_id == number:
                old.behavior_id = getattr(constant.Behavior, key)
                break


def _second_ids_to_names(old: Mapping[Any, int]) -> dict[str, int]:
    from Script.Core import constant

    names = {
        number: getattr(constant.SecondBehavior, key)
        for key, number in vars(constant.SecondBehavior_Int).items()
        if not key.startswith("__")
    }
    values = {k: v for k, v in old.items() if not isinstance(k, int)}
    for key, value in old.items():
        if isinstance(key, int) and key in names:
            values[names[key]] = value
    return values


def copy_on_replace(
    old: object, new: object, old_id: int, new_id: int, ids: Mapping[int, int]
) -> None:
    """
    读档时一个角色换成新id（old_chara_to_new.migrate_character_replacement）：死亡以外的九项抄给新角色，
    交互对象按 ids 换成新id。旧对象上有 state 属性时，九项抄到新对象的属性上，由 adopt_old_save 写进状态。
    旧对象上没有 state 属性时，九项从旧id的键抄到新id的键
    Keyword arguments:
    old -- 旧角色对象
    new -- 新角色对象
    old_id -- 旧角色id
    new_id -- 新角色id
    ids -- 旧id到新id
    """
    pickled = vars(old)
    if "state" not in pickled:
        set_state(new_id, state(old_id))
        set_last_behaviors(new_id, last_behaviors(old_id) or [0])
        set_target(new_id, ids.get(target(old_id), target(old_id)))
        set_position(new_id, position(old_id))
        working.put(str(new_id), BEHAVIOR, _get(old_id, BEHAVIOR, None))
        set_second_behaviors(new_id, second_behaviors(old_id))
        set_must_settle(new_id, must_settle(old_id))
        set_must_show(new_id, must_show(old_id))
        working.put(str(new_id), EVENT, _get(old_id, EVENT, None))
        return
    attrs = vars(new)
    attrs["state"] = pickled["state"]
    attrs["last_behavior_id_list"] = list(
        pickled.get("last_behavior_id_list") or [0]
    )
    old_target = pickled["target_character_id"]
    attrs["target_character_id"] = ids.get(old_target, old_target)
    attrs["position"] = list(pickled["position"] or ["0", "0"])
    attrs["behavior"] = pickled["behavior"]
    attrs["second_behavior"] = dict(pickled.get("second_behavior") or {})
    for name in (
        "must_settle_second_behavior_id_list",
        "must_show_second_behavior_id_list",
    ):
        attrs[name] = list(pickled.get(name) or [])
    attrs["event"] = pickled["event"]


def remap_targets(
    characters: Mapping[int, object], ids: Mapping[int, int]
) -> None:
    """
    读档时角色换id后，把每个角色的交互对象按 ids 换成新id。
    角色对象上有 target_character_id 属性时改这个属性，否则改当前缓冲区里的键
    Keyword arguments:
    characters -- 角色id到角色对象
    ids -- 旧id到新id
    """
    for cid, character in characters.items():
        attrs = vars(character)
        if "target_character_id" in attrs:
            old_target = attrs["target_character_id"]
            attrs["target_character_id"] = ids.get(old_target, old_target)
        elif target(cid) in ids:
            set_target(cid, ids[target(cid)])
