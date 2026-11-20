"""
gameplay_resolution 的草稿
=========================
玩家选行动时写的是缓存的副本：Session 打开时把缓存的顶层属性（界面与全局设置除外）先拿走，
代码第一次读到某个属性时（game_type.Cache.__getattr__ 调用 fetch）才复制它，dict 换成按条目复制的 LazyDict。
Session 关闭时 diff 比较副本与原物，得到草稿（Change 的列表），再把缓存换回原物。
草稿随选定的行动走，行动开始时 apply 把它写进缓存；每一项只在原值仍等于 old 时才写，否则报错。
草稿里的值经 encode 换成 JSON，decode 换回来。
"""

import pickle
import uuid
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from fractions import Fraction
from importlib import import_module
from typing import Any, Literal, cast

from Script.Core import cache_control
from Script.Kernel import core
from Script.Modules.gameplay_resolution import plan_queue

type Step = tuple[Literal["a", "k"], core.JSON]
""" 路径的一步：("a", 属性名) 或 ("k", 编码后的键) """
type Change = tuple[tuple[Step, ...], core.JSON, core.JSON]
""" 草稿的一项：(路径, 原值, 新值)，值都已编码，没有这一项时为 ABSENT """

ABSENT: core.JSON = {"$absent": True}
""" 编码后的“没有这一项” """


def _qualname(cls: type) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def _state(value: object) -> dict[str, object]:
    if hasattr(value, "__dict__"):
        return dict(vars(value))
    slots = (
        n for c in type(value).__mro__ for n in getattr(c, "__slots__", ())
    )
    return {n: getattr(value, n) for n in slots if hasattr(value, n)}


def encode(value: object) -> core.JSON:
    """
    把缓存里的值编码成 JSON；不认识的类型报 TypeError
    Keyword arguments:
    value -- 缓存里的值
    Return arguments:
    JSON -- 编码后的值
    """
    if value is None or isinstance(value, bool | str | float):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, Fraction):
        return {"$frac": (value.numerator, value.denominator)}
    if isinstance(value, dict):
        return {
            "$dict": tuple((encode(k), encode(v)) for k, v in value.items())
        }
    if isinstance(value, list):
        return {"$list": tuple(encode(v) for v in value)}
    if isinstance(value, tuple):
        return {"$tuple": tuple(encode(v) for v in value)}
    if isinstance(value, set | frozenset):
        items = sorted((encode(v) for v in value), key=repr)
        return {"$set": tuple(items)}
    if isinstance(value, datetime):
        return {"$dt": value.isoformat(), "$type": _qualname(type(value))}
    if isinstance(value, uuid.UUID):
        return {"$uuid": str(value)}
    cls = type(value)
    if cls.__module__.startswith("Script."):
        state = {name: encode(item) for name, item in _state(value).items()}
        return {"$obj": _qualname(cls), "$state": state}
    raise TypeError(f"草稿不能编码 {cls.__module__}.{cls.__qualname__}")


def _class(qualname: str) -> Any:
    module, name = qualname.split(":")
    cls: Any = import_module(module)
    for part in name.split("."):
        cls = getattr(cls, part)
    return cls


def decode(value: core.JSON) -> object:
    """
    encode 的逆：JSON 换回缓存里的值；接受内核冻结过的元组与只读映射
    Keyword arguments:
    value -- 编码后的值
    Return arguments:
    object -- 缓存里的值
    """
    if not isinstance(value, Mapping):
        return value
    tag = next(iter(value))
    body: Any = value[tag]
    if tag == "$frac":
        return Fraction(int(body[0]), int(body[1]))
    if tag == "$dict":
        return {decode(k): decode(v) for k, v in body}
    if tag == "$list":
        return [decode(v) for v in body]
    if tag == "$tuple":
        return tuple(decode(v) for v in body)
    if tag == "$set":
        return {decode(v) for v in body}
    if tag == "$dt":
        return _class(str(value["$type"])).fromisoformat(str(body))
    if tag == "$uuid":
        return uuid.UUID(str(body))
    if tag == "$obj":
        cls = _class(str(body))
        obj = cls.__new__(cls)
        state = cast(Mapping[str, core.JSON], value["$state"])
        for attr, item in state.items():
            setattr(obj, attr, decode(item))
        return obj
    raise TypeError(f"草稿不认识 {tag}")


class LazyDict(dict[Any, Any]):
    """
    缓存里一个 dict 的草稿副本：开始时条目引用原物，第一次读到某个条目时才复制它（pickle），
    并记下原物的 pickle 字节供 diff 比较。pickle 时是普通 dict
    """

    def __init__(self, original: dict[Any, Any]) -> None:
        """
        Keyword arguments:
        original -- 原来的 dict
        """
        super().__init__(original)
        self.original = original
        """ 原来的 dict """
        self.kept: dict[Any, bytes] = {}
        """ 已复制的条目的原物 pickle 字节 """

    def _copied(self, key: Any) -> Any:
        if key not in self.kept and dict.__contains__(self, key):
            item = dict.__getitem__(self, key)
            if item is self.original.get(key, ABSENT):
                kept = pickle.dumps(item)
                self.kept[key] = kept
                dict.__setitem__(self, key, pickle.loads(kept))
        return dict.__getitem__(self, key)

    def _all(self) -> None:
        for key in list(dict.keys(self)):
            self._copied(key)

    def __getitem__(self, key: Any) -> Any:
        """读条目：第一次读时复制"""
        return self._copied(key)

    def get(self, key: Any, default: Any = None) -> Any:
        """读条目，没有时为 default"""
        return self._copied(key) if dict.__contains__(self, key) else default

    def setdefault(self, key: Any, default: Any = None) -> Any:
        """读条目，没有时写入 default"""
        if dict.__contains__(self, key):
            return self._copied(key)
        dict.__setitem__(self, key, default)
        return default

    def pop(self, key: Any, *default: Any) -> Any:
        """取出条目"""
        if dict.__contains__(self, key):
            self._copied(key)
        return dict.pop(self, key, *default)

    def values(self) -> Any:
        """全部条目的值：全部复制"""
        self._all()
        return dict.values(self)

    def items(self) -> Any:
        """全部条目：全部复制"""
        self._all()
        return dict.items(self)

    def copy(self) -> dict[Any, Any]:
        """浅拷贝成普通 dict：全部复制"""
        self._all()
        return dict(self)

    def __reduce__(self) -> tuple[Any, ...]:
        """pickle 成普通 dict"""
        return (dict, (dict(self),))


_session: "Session | None" = None
""" 打开着的草稿 """


def active() -> bool:
    """有打开着的草稿时为 True"""
    return _session is not None


def fetch(owner: object, name: str) -> object:
    """
    Cache.__getattr__：草稿里第一次读游戏缓存的属性 name 时复制它并放进缓存
    草稿没打开、owner 不是游戏缓存、名字以 __ 开头或原来没有这个属性时报 AttributeError
    Keyword arguments:
    owner -- 读属性的 Cache 对象
    name -- 属性名
    Return arguments:
    object -- 副本
    """
    session = _session
    if (
        session is None
        or owner is not cache_control.cache
        or name.startswith("__")
        or name not in session.orig
    ):
        raise AttributeError(name)
    value = session.orig[name]
    if type(value) is dict:
        copy: object = LazyDict(value)
    else:
        copy = pickle.loads(pickle.dumps(value))
    vars(cache_control.cache)[name] = copy
    return copy


def _leaf_diff(
    path: tuple[Step, ...], old: object, new: object, out: list[Change]
) -> None:
    if old is new:
        return
    try:
        if type(old) is type(new) and old == new:
            return
    except Exception:
        pass
    # ABSENT 本身是 dict：新加或删掉的字典值整个记成一项，不逐键比较
    if (
        type(old) is dict
        and isinstance(new, dict)
        and old is not ABSENT
        and new is not ABSENT
    ):
        _dict_diff(path, old, new, out)
        return
    if (
        type(old) is type(new)
        and type(old).__module__.startswith("Script.")
        and hasattr(old, "__dict__")
    ):
        old_vars, new_vars = vars(old), vars(new)
        for name in old_vars.keys() | new_vars.keys():
            _leaf_diff(
                (*path, ("a", name)),
                old_vars.get(name, ABSENT),
                new_vars.get(name, ABSENT),
                out,
            )
        return
    try:
        before = ABSENT if old is ABSENT else encode(old)
        after = ABSENT if new is ABSENT else encode(new)
    except TypeError as error:
        raise TypeError(f"{error} at {path}") from None
    if before != after:
        out.append((path, before, after))


def _dict_diff(
    path: tuple[Step, ...],
    old: dict[Any, Any],
    new: dict[Any, Any],
    out: list[Change],
) -> None:
    kept = new.kept if isinstance(new, LazyDict) else {}
    keys: Iterable[Any] = list(old) + [
        k for k in dict.keys(new) if k not in old
    ]
    for key in keys:
        here = (*path, ("k", encode(key)))
        if not dict.__contains__(new, key):
            _leaf_diff(here, old[key], ABSENT, out)
            continue
        item = dict.__getitem__(new, key)
        if key in kept and pickle.dumps(item) == kept[key]:
            continue
        _leaf_diff(here, old.get(key, ABSENT), item, out)


class Session:
    """玩家一次选择里的草稿：打开时拿走缓存的顶层属性，关闭时比较、换回原物"""

    def __init__(self, keep: Iterable[str]) -> None:
        """
        打开草稿
        Keyword arguments:
        keep -- 选择时可以直接写的缓存顶层属性名，如 "input_cache"
        """
        global _session
        if _session is not None:
            raise RuntimeError("a draft session is already open")
        self.keep = frozenset(keep)
        """ 不复制的顶层属性 """
        cache = vars(cache_control.cache)
        self.orig: dict[str, object] = dict(cache)
        """ 打开时缓存的顶层属性 """
        for name in list(cache):
            if name not in self.keep:
                del cache[name]
        self.pending = len(plan_queue._pending)
        """ 打开时计划队列里待交给内核的打断数 """
        _session = self

    def _restore(self) -> list[core.Interrupt]:
        global _session
        _session = None
        cache = vars(cache_control.cache)
        for name in list(cache):
            if name not in self.keep:
                del cache[name]
        for name, value in self.orig.items():
            if name not in self.keep:
                cache[name] = value
        added = plan_queue._pending[self.pending :]
        del plan_queue._pending[self.pending :]
        return added

    def close(self) -> tuple[list[Change], list[str]]:
        """
        关闭草稿：比较副本与原物，换回原物，计划队列退回打开时
        Return arguments:
        tuple -- (草稿, 这次选择里排下打断的角色键)
        """
        cache = vars(cache_control.cache)
        changes: list[Change] = []
        for name in list(cache):
            if name in self.keep:
                continue
            _leaf_diff(
                (("a", name),),
                self.orig.get(name, ABSENT),
                cache[name],
                changes,
            )
        added = self._restore()
        return changes, [i.who for i in added]

    def drop(self) -> None:
        """丢掉草稿：换回原物，计划队列退回打开时"""
        self._restore()


def abandon() -> None:
    """有打开着的草稿时丢掉它（读档或新周目换掉缓存之前），之后关闭它什么也不做"""
    if _session is not None:
        _session.drop()


def _parent(path: Sequence[Step]) -> tuple[Any, Step]:
    node: Any = cache_control.cache
    for kind, part in path[:-1]:
        node = getattr(node, str(part)) if kind == "a" else node[decode(part)]
    return node, path[-1]


def _current(node: Any, step: Step) -> object:
    kind, part = step
    if kind == "a":
        return getattr(node, str(part), ABSENT)
    key = decode(part)
    return node[key] if key in node else ABSENT


def apply(changes: Sequence[Change]) -> None:
    """
    把草稿写进缓存：每一项先查路径上的当前值仍等于原值，不等时报错，再写入或删除
    Keyword arguments:
    changes -- 草稿，可以是内核冻结过的
    """
    for path, old, new in changes:
        node, step = _parent(path)
        now = _current(node, step)
        if (ABSENT if now is ABSENT else encode(now)) != _thawed(old):
            raise RuntimeError(f"draft at {path} does not follow")
        kind, part = step
        if kind == "a":
            if _thawed(new) == ABSENT:
                delattr(node, str(part))
            else:
                setattr(node, str(part), decode(new))
        elif _thawed(new) == ABSENT:
            del node[decode(part)]
        else:
            node[decode(part)] = decode(new)


def _thawed(value: core.JSON) -> core.JSON:
    if isinstance(value, Mapping):
        return {k: _thawed(v) for k, v in value.items()}
    if isinstance(value, tuple | list):
        return tuple(_thawed(v) for v in value)
    return value
