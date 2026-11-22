"""
角色的身份：全局键 identity.characters
=====================================
值是 {角色id的字符串: 身份记录}，按角色建立的先后排列。身份记录包含 name、sex、talk_size、text_color、
birthday（[年, 月, 日]）、adv、profession、race 与 token_text 九项。角色id作为表的键存放，不在记录内另存。
角色在表里即表示存在。遍历全部角色按表内顺序。没有该键时读到空表。
写入以整值替换该键。新角色排在表尾，更新已有角色时位置不变。新值与现值相同时不写。
"""

import dataclasses
import datetime
from collections.abc import Iterable, Iterator, Mapping
from typing import Any, cast

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "identity.characters"
""" 角色身份表在全局数据里的键 """
PICKLED_TYPES: Mapping[str, type] = {
    "cid": int,
    "name": str,
    "sex": int,
    "talk_size": int,
    "text_color": str,
    "birthday": datetime.datetime,
    "adv": int,
    "profession": int,
    "race": int,
    "token_text": str,
}
""" 版本 24 之前的存档里，旧角色对象上身份属性名与期望类型 """

working.register(KEY, {})


@dataclasses.dataclass(frozen=True, slots=True)
class Identity:
    """单个角色的只读身份记录"""

    cid: int
    """ 角色id """
    name: str = ""
    """ 角色名字 """
    sex: int = 0
    """ 角色性别 """
    talk_size: int = 0
    """ 角色口上大小，单位kb """
    text_color: str = ""
    """ 角色对话文本颜色 """
    birthday: datetime.date = datetime.date(1, 1, 1)
    """ 角色生日 """
    adv: int = 0
    """ 剧情npc校验 """
    profession: int = 0
    """ 角色职业 """
    race: int = 0
    """ 角色种族 """
    token_text: str = ""
    """ 角色信物文本 """


def _record(one: Identity) -> core.JSON:
    day = one.birthday
    return {
        "name": one.name,
        "sex": one.sex,
        "talk_size": one.talk_size,
        "text_color": one.text_color,
        "birthday": (day.year, day.month, day.day),
        "adv": one.adv,
        "profession": one.profession,
        "race": one.race,
        "token_text": one.token_text,
    }


_built: dict[int, tuple[Mapping[str, Any], Identity]] = {}
"""
按角色id缓存最近一次读出的底层身份记录对象与对应的 Identity。
底层记录为同一对象时直接复用该 Identity，使同一游戏状态里的重复读取不新建对象
"""


def _identity(cid: int, record: Mapping[str, Any]) -> Identity:
    hit = _built.get(cid)
    if hit is not None and hit[0] is record:
        return hit[1]
    year, month, day = record["birthday"]
    one = Identity(
        cid,
        record["name"],
        record["sex"],
        record["talk_size"],
        record["text_color"],
        datetime.date(year, month, day),
        record["adv"],
        record["profession"],
        record["race"],
        record["token_text"],
    )
    _built[cid] = (record, one)
    return one


def _stored(
    game: core.GameState | None = None,
) -> Mapping[str, Mapping[str, Any]]:
    return cast(Mapping[str, Mapping[str, Any]], working.get(None, KEY, game))


class Table(Mapping[int, Identity]):
    """角色身份表的只读视图，以角色id为键、Identity 为值，按角色建立先后遍历"""

    __slots__ = ("_records",)

    def __init__(self, records: Mapping[str, Mapping[str, Any]]) -> None:
        """
        用底层映射包装出身份表的只读视图
        Keyword arguments:
        records -- 存下的身份表（字符串角色id到身份记录）
        """
        self._records = records

    def __getitem__(self, cid: int) -> Identity:
        """
        按角色id读取身份，角色不在表里时报 KeyError
        Keyword arguments:
        cid -- 角色id
        Return arguments:
        Identity -- 对应角色的身份
        """
        record = self._records.get(str(cid))
        if record is None:
            raise KeyError(cid)
        return _identity(cid, record)

    def __contains__(self, cid: object) -> bool:
        """
        判断角色id是否在表里
        Keyword arguments:
        cid -- 待查对象
        Return arguments:
        bool -- 是整数角色id且在表里时为 True
        """
        return isinstance(cid, int) and str(cid) in self._records

    def __iter__(self) -> Iterator[int]:
        """
        按角色建立的先后依次交出角色id
        Return arguments:
        Iterator[int] -- 角色id迭代器
        """
        return (int(who) for who in self._records)

    def __len__(self) -> int:
        """
        返回表里的角色数量
        Return arguments:
        int -- 角色数量
        """
        return len(self._records)


def table(game: core.GameState | None = None) -> Table:
    """
    返回角色身份表的只读视图
    Keyword arguments:
    game -- 给出时只读该状态，缺省时读当前缓冲区
    Return arguments:
    Table -- 角色id到 Identity 的只读映射
    """
    return Table(_stored(game))


def of(cid: int, game: core.GameState | None = None) -> Identity:
    """
    按角色id读取身份，角色不在表里时报 KeyError
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读该状态，缺省时读当前缓冲区
    Return arguments:
    Identity -- 对应角色的身份
    """
    record = _stored(game).get(str(cid))
    if record is None:
        raise KeyError(cid)
    return _identity(cid, record)


def get(cid: int, game: core.GameState | None = None) -> Identity | None:
    """
    按角色id读取身份，角色不在表里时返回 None
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读该状态，缺省时读当前缓冲区
    Return arguments:
    Identity | None -- 对应角色的身份，不存在时为 None
    """
    record = _stored(game).get(str(cid))
    return None if record is None else _identity(cid, record)


def exists(cid: int, game: core.GameState | None = None) -> bool:
    """
    判断角色是否在身份表里
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读该状态，缺省时读当前缓冲区
    Return arguments:
    bool -- 在表里时为 True
    """
    return str(cid) in _stored(game)


def ids(game: core.GameState | None = None) -> tuple[int, ...]:
    """
    按角色建立先后返回全部角色id
    Keyword arguments:
    game -- 给出时只读该状态，缺省时读当前缓冲区
    Return arguments:
    tuple[int, ...] -- 按建立先后排列的角色id元组
    """
    return tuple(int(who) for who in _stored(game))


def _write(records: Mapping[str, core.JSON]) -> None:
    if not working.same(records, _stored()):
        working.put(None, KEY, cast(core.JSON, records))


def put(one: Identity) -> None:
    """
    写入一名角色的身份。新角色排在表尾，已有角色保持原位
    Keyword arguments:
    one -- 待写入的角色身份
    """
    _write({**_stored(), str(one.cid): _record(one)})


def update(cid: int, **fields: Any) -> None:
    """
    更新指定角色身份的给定字段，角色不在表里时报 KeyError
    Keyword arguments:
    cid -- 角色id
    fields -- 待更新的字段名与新值
    """
    put(dataclasses.replace(of(cid), **fields))


def discard(cid: int) -> None:
    """
    从身份表移除指定角色，角色不在表里时不改动
    Keyword arguments:
    cid -- 角色id
    """
    current = _stored()
    if str(cid) in current:
        _write({who: rec for who, rec in current.items() if who != str(cid)})


def replace_all(records: Iterable[Identity]) -> None:
    """
    用给定的身份序列按顺序整表替换身份表
    Keyword arguments:
    records -- 角色身份序列
    """
    _write({str(one.cid): _record(one) for one in records})


def _pickled(cid: int, attrs: dict[str, Any]) -> Identity:
    found = {name: attrs.pop(name) for name in PICKLED_TYPES if name in attrs}
    kept: dict[str, Any] = {
        name: value
        for name, value in found.items()
        if name != "cid"
        and (
            type(value) is PICKLED_TYPES[name]
            or isinstance(value, datetime.datetime)
            and name == "birthday"
        )
    }
    if "birthday" in kept:
        day = kept["birthday"]
        kept["birthday"] = datetime.date(day.year, day.month, day.day)
    return Identity(cid, **kept)


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时最先调用，导入旧存档的角色身份或补齐占位字典。
    loaded_dict 含字典型 character_data（版本 24 之前的存档）时，从各角色对象移除 PICKLED_TYPES 中的属性，
    并按 character_data 的键和顺序整表写入当前缓冲区。缺失或类型不符的字段取 Identity 默认值。
    loaded_dict 不含字典型 character_data 时，保留文件 "2" 的身份表，
    并把 loaded_dict["character_data"] 设为按身份表顺序排列的空旧角色对象字典。
    两种情况下，调用后 loaded_dict["character_data"] 与身份表的键和顺序一致。
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    characters = loaded_dict.get("character_data")
    if not isinstance(characters, dict):
        loaded_dict["character_data"] = {
            cid: game_type.Character() for cid in ids()
        }
        return
    replace_all(
        _pickled(cid, chara.__dict__) for cid, chara in characters.items()
    )
