"""
角色活动里行为与事件的存法与只读读出
=====================================
activity.behavior 与 activity.event 只存与默认不同的字段。record 把写入的字段并进存下的记录。
Behavior 与 Event 把存下的记录读成只读对象，属性名与类型同 game_type.Behavior 与 Chara_Event。
开始时间存内核时钟的分钟数，不在整游戏分钟上的开始时间报 ValueError。
目标食物存食物记录（kitchen.record）与它的 uid 字符串。没存目标食物时读出 uid 为 0 的空食物，读的时候不取随机 uuid。
"""

import datetime
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, ClassVar, cast

from Script.Core import game_type
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import kitchen

NO_START = datetime.datetime(1, 1, 1)
""" Behavior() 的开始时间，不存 """
_NO_FOOD = uuid.UUID(int=0)
_EMPTY_FOOD = kitchen.record(game_type.Food(_NO_FOOD))
_LISTS = frozenset({"move_target", "move_src", "move_final_target"})
BEHAVIOR_DEFAULT: Mapping[str, core.JSON] = {
    "duration": 0,
    "behavior_id": "share_blankly",
    "move_target": (),
    "move_src": (),
    "move_final_target": (),
    "make_food_time": 0,
    "make_food_count": 1,
    "pan_name": "",
    "socks_name": "",
    "book_id": 0,
    "book_name": "",
    "milk_ml": 0,
    "urine_ml": 0,
    "h_interrupt_chara_name": "",
    "board_game_type": 0,
    "board_game_ai_difficulty": 0,
    "gift_id": 0,
    "gift_egg_id": -1,
    "gift_child_id": -1,
}
""" Behavior() 除开始时间与食物外各字段的值，列表存成元组 """
EVENT_DEFAULT: Mapping[str, core.JSON] = {
    "event_id": "",
    "son_event_id": "",
    "chara_diy_event_flag": False,
    "skip_instruct_talk": False,
}
""" Chara_Event() 各字段的值 """


def _same(value: object, default: object) -> bool:
    return type(value) is type(default) and value == default


def _start(stored: core.JSON) -> datetime.datetime:
    return NO_START if stored is None else game_time.at(cast(int, stored))


def _food(stored: core.JSON) -> game_type.Food:
    if stored is None:
        return kitchen.food(str(_NO_FOOD), _EMPTY_FOOD)
    record = cast(Mapping[str, core.JSON], stored)
    return kitchen.food(str(record["uid"]), record)


def _encode(name: str, value: object) -> core.JSON:
    if name == "start_time":
        start = cast(datetime.datetime, value)
        if _same(start, NO_START):
            return None
        minutes = game_time.minutes(start)
        if game_time.at(minutes) != start:
            raise ValueError(f"start_time {start!r} is not a game minute")
        return minutes
    if name == "target_food":
        food = cast(game_type.Food, value)
        return {**_EMPTY_FOOD, **kitchen.record(food), "uid": str(food.uid)}
    if name in _LISTS:
        return tuple(cast(Iterable[str], value))
    return cast(core.JSON, value)


class _Record:
    """只读的记录：属性按 _fields 读出，没存的取默认值"""

    __slots__ = ("_stored",)
    _fields: ClassVar[Mapping[str, Callable[[core.JSON], object]]] = {}

    def __init__(self, stored: Mapping[str, core.JSON]) -> None:
        """
        按存下的记录建只读对象
        Keyword arguments:
        stored -- 存下的记录
        """
        object.__setattr__(self, "_stored", stored)

    def __setattr__(self, name: str, value: object) -> None:
        """给属性赋值都报 AttributeError。改字段用 activity.update_behavior 或 activity.update_event"""
        raise AttributeError(f"{name} is read only")

    def __reduce__(self) -> tuple[type, tuple[dict[str, core.JSON]]]:
        """复制与 pickle 时按存下的记录新建"""
        return type(self), (dict(cast(Any, self)._stored),)

    def as_dict(self) -> dict[str, object]:
        """全部字段名到读出的值"""
        return {name: getattr(self, name) for name in self._fields}

    @classmethod
    def build(cls, fields: Mapping[str, Callable[[core.JSON], object]]) -> None:
        """
        给类装上每个字段的只读属性
        Keyword arguments:
        fields -- 字段名到把存下的值（没存时为 None）换成读出的值的函数
        """
        cls._fields = fields
        for name, read in fields.items():

            def get(self: _Record, _n: str = name, _r: Any = read) -> object:
                return _r(cast(Any, self)._stored.get(_n))

            setattr(cls, name, property(get))


def _default(
    name: str, source: Mapping[str, core.JSON]
) -> Callable[[core.JSON], object]:
    default = source[name]
    if isinstance(default, tuple):
        return lambda v: list(cast(Sequence[str], default if v is None else v))
    return lambda v: default if v is None else v


class Behavior(_Record):
    """读出的当前行为，属性同 game_type.Behavior"""

    __slots__ = ()
    start_time: datetime.datetime
    duration: int
    behavior_id: str
    move_target: list[str]
    move_src: list[str]
    move_final_target: list[str]
    target_food: game_type.Food
    make_food_time: int
    make_food_count: int
    pan_name: str
    socks_name: str
    book_id: int
    book_name: str
    milk_ml: int
    urine_ml: int
    h_interrupt_chara_name: str
    board_game_type: int
    board_game_ai_difficulty: int
    gift_id: int
    gift_egg_id: int
    gift_child_id: int


class Event(_Record):
    """读出的当前事件，属性同 game_type.Chara_Event"""

    __slots__ = ()
    event_id: str
    son_event_id: str
    chara_diy_event_flag: bool
    skip_instruct_talk: bool


Behavior.build(
    {
        "start_time": _start,
        "target_food": _food,
        **{n: _default(n, BEHAVIOR_DEFAULT) for n in BEHAVIOR_DEFAULT},
    }
)
Event.build({n: _default(n, EVENT_DEFAULT) for n in EVENT_DEFAULT})


def record(
    old: Mapping[str, core.JSON],
    fields: Mapping[str, object],
    kind: type[_Record],
) -> dict[str, core.JSON]:
    """
    把 fields 并进存下的记录 old，与默认相同的字段不存。
    未知的字段名报 AttributeError，不在整游戏分钟上的开始时间报 ValueError
    Keyword arguments:
    old -- 存下的记录，不改
    fields -- 字段名到新值
    kind -- Behavior 或 Event
    Return arguments:
    dict -- 新记录
    """
    new = dict(old)
    defaults = BEHAVIOR_DEFAULT if kind is Behavior else EVENT_DEFAULT
    for name, value in fields.items():
        if name not in kind._fields:
            raise AttributeError(f"{kind.__name__} has no field {name}")
        encoded = _encode(name, value)
        if encoded is None or _same(encoded, defaults.get(name)):
            new.pop(name, None)
        else:
            new[name] = encoded
    return new
