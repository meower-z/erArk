"""
角色的能力、经验、宝珠与素质：角色的键 abilities.ability、abilities.experience、abilities.juel、abilities.talent
==============================================================================================================
每个键的值是一张表 {编号的字符串: 数值}，编号见 Ability.csv、Experience.csv、Juel.csv 与 Talent.csv。
角色没有某个键时读到空表。本模块给四个键各登记一条规则，规则用 fold 把一串操作依次套到当前的表上。
代码经 ability、experience、juel、talent 取到角色的一张 Table，像 dict[int, int] 一样读写。
读版本 16 之前的存档时，adopt_old_save 把角色对象上的四张表搬进这四个键。
"""

from collections.abc import Iterator, Mapping, MutableMapping
from types import MappingProxyType
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

ABILITY = "abilities.ability"
""" 能力表的键名 """
EXPERIENCE = "abilities.experience"
""" 经验表的键名 """
JUEL = "abilities.juel"
""" 宝珠表的键名 """
TALENT = "abilities.talent"
""" 素质表的键名 """
PICKLED = {
    "ability": ABILITY,
    "experience": EXPERIENCE,
    "juel": JUEL,
    "talent": TALENT,
}
""" 四张表的属性名（版本 16 之前的存档里角色对象上的属性名）到键名 """
GONE_TALENTS = (6, 7)
""" Talent.csv 里没有的素质编号，adopt_old_save 从旧存档的素质表里去掉它们 """


def fold(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    """
    规则的一次操作，交回新表，不改 old
    Keyword arguments:
    old -- 当前的表 {编号的字符串: 数值}
    op -- 操作名。set 写入给出的各项，drop 去掉给出的编号（表里没有时报 KeyError），replace 换成给出的整张表。
    别的名字报 ValueError
    operand -- set 与 replace 时为 {编号的字符串: 数值}，drop 时为编号的字符串的序列
    Return arguments:
    JSON -- 新的表
    """
    if op == "replace":
        return dict(cast(Mapping[str, int], operand))
    table = cast(MappingProxyType[str, int], old).copy()
    if op == "set":
        table.update(cast(Mapping[str, int], operand))
    elif op == "drop":
        for tid in cast(tuple[str, ...], operand):
            del table[tid]
    else:
        raise ValueError(f"abilities has no op {op}")
    return table


def _apply(game: core.GameState, change: core.Change) -> core.GameState:
    old = core.value(game, change.who, change.key)
    ops = cast(tuple[core.JSON, ...], change.operand)
    return core.with_value(
        game, change.who, change.key, working.fold_all(change.key, old, ops)
    )


for _key in PICKLED.values():
    working.register(_key, {}, fold)
    core.rule(_key)(_apply)


class Table(MutableMapping[int, int]):
    """
    一个角色的一张表，像 dict[int, int] 一样读写，编号为 int。
    读经 working.get，读得到当前缓冲区里还没套用的写入。写一项、删一项、merge 与 replace 各在当前缓冲区记一次操作。
    不在一步、玩家选择或 based_on 的缓冲区里写时，working 报 RuntimeError
    """

    __slots__ = ("_who", "_key", "_game")

    def __init__(
        self, cid: int, key: str, game: core.GameState | None = None
    ) -> None:
        """
        指向角色 cid 在键 key 下的表，建时不读数据
        Keyword arguments:
        cid -- 角色id
        key -- 键名，PICKLED 里的一个值
        game -- 给出时只读这个状态，没有时读当前缓冲区
        """
        self._who = str(cid)
        self._key = key
        self._game = game

    def _raw(self) -> Mapping[str, int]:
        return cast(
            Mapping[str, int], working.get(self._who, self._key, self._game)
        )

    def __getitem__(self, tid: int) -> int:
        """编号 tid 的数值，表里没有时报 KeyError"""
        return self._raw()[str(tid)]

    def __setitem__(self, tid: int, value: int) -> None:
        """把编号 tid 的数值写成 value，表里没有这一项时加上"""
        working.change(self._who, self._key, "set", {str(tid): value})

    def __delitem__(self, tid: int) -> None:
        """去掉编号 tid，表里没有时报 KeyError"""
        if str(tid) not in self._raw():
            raise KeyError(tid)
        working.change(self._who, self._key, "drop", (str(tid),))

    def __iter__(self) -> Iterator[int]:
        """依次给出此刻表里的编号"""
        return iter([int(tid) for tid in self._raw()])

    def __len__(self) -> int:
        """此刻表里的项数"""
        return len(self._raw())

    def __repr__(self) -> str:
        """角色id、键名与此刻表里的内容"""
        return f"Table({self._who}, {self._key}, {self.copy()!r})"

    def copy(self) -> dict[int, int]:
        """
        此刻的表的副本
        Return arguments:
        dict -- 编号（int）到数值
        """
        return {int(tid): value for tid, value in self._raw().items()}

    def keys(self) -> Any:
        """此刻的编号，取自副本，之后的写入不改变它"""
        return self.copy().keys()

    def items(self) -> Any:
        """此刻的 (编号, 数值)，取自副本，之后的写入不改变它"""
        return self.copy().items()

    def values(self) -> Any:
        """此刻的数值，取自副本，之后的写入不改变它"""
        return self.copy().values()

    def merge(self, values: Mapping[int, int]) -> None:
        """
        把 values 的各项写进这张表，在当前缓冲区记作一次 set 操作
        Keyword arguments:
        values -- 编号到数值
        """
        table = {str(tid): value for tid, value in values.items()}
        working.change(self._who, self._key, "set", table)

    def replace(self, values: Mapping[int, int]) -> None:
        """
        把整张表换成 values，在当前缓冲区记作一次 replace 操作
        Keyword arguments:
        values -- 编号到数值
        """
        table = {str(tid): value for tid, value in values.items()}
        working.change(self._who, self._key, "replace", table)


def ability(cid: int, game: core.GameState | None = None) -> Table:
    """
    角色的能力表
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    Table -- 能力编号到等级
    """
    return Table(cid, ABILITY, game)


def experience(cid: int, game: core.GameState | None = None) -> Table:
    """
    角色的经验表
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    Table -- 经验编号到经验值
    """
    return Table(cid, EXPERIENCE, game)


def juel(cid: int, game: core.GameState | None = None) -> Table:
    """
    角色的宝珠表
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    Table -- 宝珠编号到数量
    """
    return Table(cid, JUEL, game)


def talent(cid: int, game: core.GameState | None = None) -> Table:
    """
    角色的素质表
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    Table -- 素质编号到数值
    """
    return Table(cid, TALENT, game)


def clear(cid: int) -> None:
    """
    把角色的四张表都换成空表，在当前缓冲区记操作。建角色时用它让四张表从空开始
    Keyword arguments:
    cid -- 角色id
    """
    for key in PICKLED.values():
        Table(cid, key).replace({})


def copy_tables(old_cid: int, new_cid: int) -> None:
    """
    把 old_cid 的四张表整张抄给 new_cid，在当前缓冲区记操作
    Keyword arguments:
    old_cid -- 抄出的角色id
    new_cid -- 抄入的角色id
    """
    for key in PICKLED.values():
        Table(new_cid, key).replace(Table(old_cid, key).copy())


def carry(cids: list[int], game: core.GameState) -> dict[str, core.JSON]:
    """
    读出给出的角色在 game 里的四张表。新周目从空的 GameState 开始，要继承的表经它带过去
    Keyword arguments:
    cids -- 角色id的列表
    game -- 结束的周目的状态
    Return arguments:
    dict -- {角色id的字符串: {属性名: {编号的字符串: 数值}}}，属性名为 PICKLED 的键
    """
    return {
        str(cid): {
            name: working.get(str(cid), key, game)
            for name, key in PICKLED.items()
        }
        for cid in cids
    }


def carried(
    carry_data: Mapping[str, Any], cid: int, name: str
) -> dict[int, int]:
    """
    从 carry 交回的数据里取一个角色的一张表
    Keyword arguments:
    carry_data -- carry 交回的数据
    cid -- 角色id
    name -- 属性名，PICKLED 的键
    Return arguments:
    dict -- 编号（int）到数值，carry_data 里没有这个角色时为空表
    """
    tables = carry_data.get(str(cid), {})
    return {int(tid): value for tid, value in tables.get(name, {}).items()}


def adopt_old_save(loaded_dict: dict[str, Any]) -> int:
    """
    读档时把存档缓存里角色对象上的四张表搬进当前缓冲区，要在角色替换与重建角色之前调用。
    角色对象带着 PICKLED 里的属性时（版本 16 之前的存档），删掉这些属性，按 loaded_dict 里的角色id 写成整张表。
    素质表先去掉 GONE_TALENTS 再写。不带这些属性的角色对象不改
    Keyword arguments:
    loaded_dict -- 存档缓存（文件 "1"）解开后的属性表
    Return arguments:
    int -- 去掉的素质项数
    """
    dropped = 0
    for cid, character in loaded_dict.get("character_data", {}).items():
        attrs = vars(character)
        for name, key in PICKLED.items():
            if name not in attrs:
                continue
            table = dict(attrs.pop(name))
            if key == TALENT:
                for tid in GONE_TALENTS:
                    dropped += int(table.pop(tid, None) is not None)
            Table(cid, key).replace(table)
    return dropped
