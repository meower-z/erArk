"""
角色键：GameState 里每个角色各存一份的数据项
============================================
领域模块为自己的每项角色数据建一个 CharaKey。
CharaKey 记下键名、角色没有这一项时读到的默认值、旧存档里这项数据在角色对象上的属性路径，以及一对换算函数。
encode 把值换成存下的 JSON。decode 把存下的 JSON 换成读出的值。
各角色键读出的 dict、list 与 set 都是 decode 新建的。改读出的值因此不改存下的值。
写入经 working.put 整值替换这个键。换算后的新值与存下的值相同、各层类型也相同时不写。
角色不在花名册里时，working 把这个角色的键存在全局键 roster.offstage 里。
"""

import contextlib
from collections.abc import Callable, Collection, Iterator, Mapping
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

_MISSING = object()
""" 旧属性路径上缺了的属性 """
BY_KEY: dict[str, "CharaKey[Any]"] = {}
""" 键名到角色键，含全部已建的角色键 """


def _plain(value: Any) -> Any:
    return value


class CharaKey[T]:
    """一个角色键：键名、默认值、旧存档里的属性路径与一对换算函数"""

    def __init__(
        self,
        key: str,
        default: T,
        old: str,
        encode: Callable[[T], core.JSON] = _plain,
        decode: Callable[[core.JSON], T] = _plain,
    ) -> None:
        """
        在 working 与 BY_KEY 里登记这个角色键
        Keyword arguments:
        key -- 键名
        default -- 角色没有这一项时读到的值
        old -- 旧存档里角色对象上的属性路径，如 "relationship.nation"
        encode -- 把值换成存下的 JSON
        decode -- 把存下的 JSON 换成读出的值
        """
        self.key = key
        """ 键名 """
        self.old = old
        """ 旧存档里角色对象上的属性路径 """
        self.default = default
        """ 没有这一项时读到的值 """
        self.encode = encode
        """ 值换成存下的 JSON """
        self.decode = decode
        """ 存下的 JSON 换成新值 """
        working.register(key, encode(default))
        BY_KEY[key] = self

    def __call__(self, cid: int, game: core.GameState | None = None) -> T:
        """
        读角色的这项数据
        Keyword arguments:
        cid -- 角色id
        game -- 给出时只读这个 GameState。不给时读当前缓冲区
        Return arguments:
        T -- decode 换出的值
        """
        return self.decode(working.get(str(cid), self.key, game))

    def set(self, cid: int, value: T) -> None:
        """
        把 value 换算后整值写进当前缓冲区
        换算后的值与当前值相同、各层类型也相同时不写
        Keyword arguments:
        cid -- 角色id
        value -- 新值
        """
        new = self.encode(value)
        if not working.same(new, working.get(str(cid), self.key)):
            working.put(str(cid), self.key, new)

    @contextlib.contextmanager
    def editing(self, cid: int) -> Iterator[T]:
        """
        在 with 块里改角色的这项数据（表、列表或集合）
        块正常结束时经 set 写回当前缓冲区。块里抛错时不写
        Keyword arguments:
        cid -- 角色id
        Return arguments:
        Iterator[T] -- 交给 with 块的值
        """
        value = self(cid)
        yield value
        self.set(cid, value)

    def set_item(self, cid: int, item: Any, value: Any) -> None:
        """
        把角色这项数据（表或列表）里的一项换成 value。整值经 set 写回当前缓冲区
        Keyword arguments:
        cid -- 角色id
        item -- 表的键或列表的下标
        value -- 这一项的新值
        """
        table: Any = self(cid)
        table[item] = value
        self.set(cid, table)


def reset(cid: int, keys: Collection[CharaKey[Any]] | None = None) -> None:
    """
    把角色的这些键换回各自的默认值，经 set 写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    keys -- 角色键，None 时为 BY_KEY 里的全部角色键
    """
    for key in BY_KEY.values() if keys is None else keys:
        key.set(cid, key.default)


def adopt(
    loaded_dict: dict[str, Any],
    keys: Collection[CharaKey[Any]],
    dropped: Collection[str] = (),
) -> None:
    """
    读档时把旧存档角色对象上的数据导入角色键
    对 loaded_dict 里的每个角色对象，key.old 的第一段属性（如 "relationship.nation" 的 relationship）在对象上时，
    沿属性路径取值，经 set 写进当前缓冲区。路径中途缺属性时不写这个键。
    值写在这个角色在 character_data 里的键下，不用对象上的 cid。
    导入后从对象上删掉这些第一段属性，也删掉 dropped 里的属性
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    keys -- 要导入的角色键
    dropped -- 不导入、只从对象上删掉的属性名
    """
    for cid, character in loaded_dict["character_data"].items():
        attrs = vars(character)
        found = set()
        for key in keys:
            head, *path = key.old.split(".")
            if head not in attrs:
                continue
            found.add(head)
            value = attrs[head]
            for name in path:
                value = getattr(value, name, _MISSING)
            if value is not _MISSING:
                key.set(cid, value)
        for name in found.union(dropped):
            attrs.pop(name, None)


def lift(loaded_dict: dict[str, Any]) -> None:
    """
    把角色键的值按旧属性路径写回存档里的角色对象，供按旧属性名复制角色数据的迁移使用
    角色对象上没有任何一个角色键旧属性路径的第一段时（版本 21 的存档），把全部角色键的值写到这个对象上。
    relationship、work、entertainment 与 author_flag 按 game_type 里的类新建。
    对象上带着其中任何一段时（版本 21 之前的存档），这个对象不动
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    from Script.Core import game_type

    records = {
        "relationship": game_type.RELATIONSHIP,
        "work": game_type.CHARA_WORK,
        "entertainment": game_type.CHARA_ENTERTAINMENT,
        "author_flag": game_type.AUTHOR_FLAG,
    }
    heads = {key.old.split(".")[0] for key in BY_KEY.values()}
    for cid, character in loaded_dict["character_data"].items():
        attrs = vars(character)
        if heads & attrs.keys():
            continue
        for key in BY_KEY.values():
            head, *path = key.old.split(".")
            if path:
                record = attrs.setdefault(head, records[head]())
                setattr(record, path[0], key(cid))
            else:
                attrs[head] = key(cid)


def int_table(table: Mapping[int, Any]) -> core.JSON:
    """
    把 int 键的表换成存下的 str 键 dict
    Keyword arguments:
    table -- int 键的表
    Return arguments:
    JSON -- str 键的 dict
    """
    return {str(k): v for k, v in table.items()}


def int_table_of(stored: core.JSON) -> dict[int, Any]:
    """
    把存下的 str 键表换成新建的 int 键 dict
    Keyword arguments:
    stored -- 存下的 str 键表
    Return arguments:
    dict[int, Any] -- 新建的 int 键 dict
    """
    return {int(k): v for k, v in cast(Mapping[str, Any], stored).items()}


def sequence(items: Any) -> core.JSON:
    """
    把列表换成存下的元组
    Keyword arguments:
    items -- 列表
    Return arguments:
    JSON -- 元组
    """
    return tuple(items)


def list_of(stored: core.JSON) -> list[Any]:
    """
    把存下的元组换成新建的 list
    Keyword arguments:
    stored -- 存下的元组
    Return arguments:
    list[Any] -- 新建的 list
    """
    return list(cast(tuple[Any, ...], stored))


def int_set(items: Any) -> core.JSON:
    """
    把 int 的集合换成存下的、排好序的元组
    Keyword arguments:
    items -- int 的集合
    Return arguments:
    JSON -- 排好序的元组
    """
    return tuple(sorted(items))


def set_of(stored: core.JSON) -> set[Any]:
    """
    把存下的元组换成新建的 set
    Keyword arguments:
    stored -- 存下的元组
    Return arguments:
    set[Any] -- 新建的 set
    """
    return set(cast(tuple[Any, ...], stored))
