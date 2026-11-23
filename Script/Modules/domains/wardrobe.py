"""
角色的服装：角色键 body.cloth
=============================
值是 {CLOTH 的属性名: 属性值}，属性按 FIELDS 的顺序。值里字典的键存成字符串，列表存成元组。
clothing_tem 是服装模板编号的列表。cloth_wear、cloth_off、cloth_locker_in_shower 与 cloth_locker_in_dormitory
是 {部位编号: 服装id的列表}。cloth_see 是 {部位编号: 能否被看见}。
另有 stolen_panties_in_unconscious、stolen_socks_in_unconscious 与 equipment_condition。
角色没有这一项时读 CLOTH() 的值。put 整值替换这个键，值与值的类型都没变时不写。
of 返回带缓存的只读 ClothView。clone_mutable_snapshot 返回可修改的新 CLOTH。
set、set_part、append、remove 各先取一份克隆，改一处后再用 put 写回。
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, cast

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.domains import counts
from Script.Modules.gameplay_resolution import readonly, working

KEY = "body.cloth"
""" 服装在角色数据里的键 """
PICKLED = "cloth"
""" 版本 19 之前的存档里，角色对象上服装的属性名 """
FIELDS = tuple(vars(game_type.CLOTH()))
""" 存下的 CLOTH 属性名，按 CLOTH() 里的顺序 """
_ATOMS = frozenset((int, bool, float, str, type(None)))
""" 编解码时原样交回的值的类型 """
_MAPS = frozenset((dict, MappingProxyType))
""" 解码时不用再查 Mapping 的映射类型 """


def _encoded(value: Any) -> core.JSON:
    if type(value) in _ATOMS:
        return cast(core.JSON, value)
    if isinstance(value, Mapping):
        return {
            str(k): v if type(v) in _ATOMS else _encoded(v)
            for k, v in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str):
        return tuple(v if type(v) in _ATOMS else _encoded(v) for v in value)
    return cast(core.JSON, value)


def _decoded(value: core.JSON) -> Any:
    kind = type(value)
    if kind in _ATOMS:
        return value
    if kind is tuple:
        seq = cast(Sequence[core.JSON], value)
        return [v if type(v) in _ATOMS else _decoded(v) for v in seq]
    if kind in _MAPS or isinstance(value, Mapping):
        table = cast(Mapping[str, core.JSON], value)
        return {
            int(k): v if type(v) in _ATOMS else _decoded(v)
            for k, v in table.items()
        }
    if isinstance(value, tuple | list):
        return [_decoded(v) for v in value]
    return value


def encode(cloth: game_type.CLOTH) -> dict[str, core.JSON]:
    """
    把 CLOTH 换成存下的值，只取 FIELDS 里的属性
    Keyword arguments:
    cloth -- 服装
    Return arguments:
    dict -- 属性名到值，字典的键换成字符串，列表换成元组
    """
    attrs = vars(cloth)
    return {name: _encoded(attrs[name]) for name in FIELDS}


working.register(KEY, encode(game_type.CLOTH()))


@dataclass(frozen=True, slots=True)
class ClothView:
    """角色服装的只读视图，包含与 CLOTH 相同的九个字段。容器字段为只读映射与元组，不可原地修改。"""

    clothing_tem: tuple[int, ...]
    cloth_wear: Mapping[int, tuple[int, ...]]
    cloth_off: Mapping[int, tuple[int, ...]]
    cloth_locker_in_shower: Mapping[int, tuple[int, ...]]
    cloth_locker_in_dormitory: Mapping[int, tuple[int, ...]]
    cloth_see: Mapping[int, bool]
    stolen_panties_in_unconscious: bool
    stolen_socks_in_unconscious: bool
    equipment_condition: float


def _viewed(value: core.JSON) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({int(k): _viewed(v) for k, v in value.items()})
    return value


def _view(stored: core.JSON) -> ClothView:
    table = cast(Mapping[str, core.JSON], stored)
    return ClothView(**{name: _viewed(v) for name, v in table.items()})


def of(cid: int, game: core.GameState | None = None) -> ClothView:
    """
    读取角色服装的只读视图，原始值未变时复用缓存
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读该 GameState，为 None 时读当前缓冲区（含未套用的写入）
    Return arguments:
    ClothView -- 角色服装的只读视图，不可原地修改
    """
    return readonly.view(str(cid), KEY, _view, game)


def clone_mutable_snapshot(
    cid: int, game: core.GameState | None = None
) -> game_type.CLOTH:
    """
    按当前存下的服装数据新建可修改的 CLOTH 副本，修改副本不影响存下的服装
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读该 GameState，为 None 时读当前缓冲区（含未套用的写入）
    Return arguments:
    game_type.CLOTH -- 新建的可修改服装对象，字典键还原为 int，元组还原为 list
    """
    stored = cast(Mapping[str, core.JSON], working.get(str(cid), KEY, game))
    made = object.__new__(game_type.CLOTH)
    vars(made).update({name: _decoded(v) for name, v in stored.items()})
    return made


def put(cid: int, cloth: game_type.CLOTH) -> None:
    """
    把角色的服装整个换成 cloth，写进当前缓冲区。换成存下的值后，与当前值相同（working.same）时不写
    Keyword arguments:
    cid -- 角色id
    cloth -- 服装
    """
    new = encode(cloth)
    if not working.same(working.get(str(cid), KEY), new):
        working.put(str(cid), KEY, new)


def set(cid: int, field: str, value: Any) -> None:
    """
    把服装的一个属性换成 value，同 cloth.<field> = value，写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    field -- 属性名
    value -- 新值
    """
    cloth = clone_mutable_snapshot(cid)
    setattr(cloth, field, value)
    put(cid, cloth)


def set_part(cid: int, field: str, part: int, value: Any) -> None:
    """
    把服装一个字典属性里一个部位的值换成 value，同 cloth.<field>[part] = value，写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    field -- 属性名
    part -- 部位编号
    value -- 新值
    """
    cloth = clone_mutable_snapshot(cid)
    getattr(cloth, field)[part] = value
    put(cid, cloth)


def append(cid: int, field: str, part: int, cloth_id: int) -> None:
    """
    在服装一个字典属性里一个部位的列表最后加上 cloth_id，同 cloth.<field>[part].append(cloth_id)，写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    field -- 属性名
    part -- 部位编号
    cloth_id -- 服装id
    """
    cloth = clone_mutable_snapshot(cid)
    getattr(cloth, field)[part].append(cloth_id)
    put(cid, cloth)


def remove(cid: int, field: str, part: int, cloth_id: int) -> None:
    """
    从服装一个字典属性里一个部位的列表里删掉第一个 cloth_id，同 cloth.<field>[part].remove(cloth_id)，写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    field -- 属性名
    part -- 部位编号
    cloth_id -- 服装id，列表里没有时报 ValueError
    """
    cloth = clone_mutable_snapshot(cid)
    getattr(cloth, field)[part].remove(cloth_id)
    put(cid, cloth)


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时调用。存档里的角色对象带着 PICKLED 属性时（版本 19 之前的存档），从对象上删掉它，再用 put 写进当前缓冲区。
    服装对象缺的属性取 CLOTH() 的值，FIELDS 以外的属性不存
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    for cid, pickled in counts.taken(loaded_dict, PICKLED):
        cloth = game_type.CLOTH()
        vars(cloth).update(vars(pickled))
        put(cid, cloth)
