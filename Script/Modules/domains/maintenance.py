"""
工程部的全局键：设施损坏、检修地点与装备维护
============================================
base.facility_damage 是 {场景路径: 损坏值}，按场景第一次损坏的先后排列。
base.maintenance_place 是 {检修工程师id的字符串: 场景路径}。
base.equipment_repair 是 {铁匠id的字符串: 铁匠正在维修或保养的装备所属角色id}。
base.equipment_setting 是 {装备维护设置id的字符串: 设置值}。
base.equipment_operators 是手动选择的装备维护对象的角色id，按选择的先后排列。
写入函数整值替换一个键。新值与旧值的各项与先后都相同时不写。没有某个键时读到空的值。
"""

import os
from collections.abc import Mapping
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

DAMAGE = "base.facility_damage"
""" 设施损坏的全局键 """
PLACES = "base.maintenance_place"
""" 检修地点的全局键 """
REPAIRS = "base.equipment_repair"
""" 铁匠的维修或保养记录的全局键 """
SETTING = "base.equipment_setting"
""" 装备维护设置的全局键 """
OPERATORS = "base.equipment_operators"
""" 手动选择的装备维护对象的全局键 """

for _key in (DAMAGE, PLACES, REPAIRS, SETTING):
    working.register(_key, {})
working.register(OPERATORS, ())


def _stored(key: str, game: core.GameState | None) -> Mapping[str, Any]:
    return cast(Mapping[str, Any], working.get(None, key, game))


def _by_id(key: str, game: core.GameState | None) -> dict[int, Any]:
    return {int(cid): value for cid, value in _stored(key, game).items()}


def _put(key: str, new: Mapping[Any, Any]) -> None:
    table = {str(k): v for k, v in new.items()}
    if list(table.items()) != list(_stored(key, None).items()):
        working.put(None, key, cast(core.JSON, table))


def damage(game: core.GameState | None = None) -> dict[str, int]:
    """
    全部损坏的设施
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    dict -- 场景路径到损坏值，按场景第一次损坏的先后排列
    """
    return dict(_stored(DAMAGE, game))


def set_damage(scene: str, count: int) -> None:
    """
    把一个场景的损坏值设为 count。count 不大于 0 时，这个场景从表里去掉。
    已在表里的场景位置不变，新场景排在最后
    Keyword arguments:
    scene -- 场景路径
    count -- 损坏值
    """
    table = damage()
    if count > 0:
        table[scene] = count
    else:
        table.pop(scene, None)
    _put(DAMAGE, table)


def places(game: core.GameState | None = None) -> dict[int, str]:
    """
    全部检修地点
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    dict -- 检修工程师id到场景路径
    """
    return _by_id(PLACES, game)


def place_of(cid: int, game: core.GameState | None = None) -> str | None:
    """
    一名检修工程师的检修地点
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    str | None -- 场景路径，这名角色没有检修地点时为 None
    """
    return _stored(PLACES, game).get(str(cid))


def set_place(cid: int, scene: str) -> None:
    """
    记下一名检修工程师的检修地点。这名角色原有的检修地点被换掉
    Keyword arguments:
    cid -- 角色id
    scene -- 场景路径
    """
    _put(PLACES, {**places(), cid: scene})


def drop_place(cid: int) -> None:
    """
    去掉一名角色的检修地点。这名角色没有检修地点时不写
    Keyword arguments:
    cid -- 角色id
    """
    if str(cid) in _stored(PLACES, None):
        _put(PLACES, {k: v for k, v in places().items() if k != cid})


def repairs(game: core.GameState | None = None) -> dict[int, int]:
    """
    全部铁匠的维修或保养记录
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    dict -- 铁匠id到装备所属角色id
    """
    return _by_id(REPAIRS, game)


def set_repair(smith: int, owner: int) -> None:
    """
    记下铁匠正在维修或保养 owner 的装备
    Keyword arguments:
    smith -- 铁匠的角色id
    owner -- 装备所属角色id
    """
    _put(REPAIRS, {**repairs(), smith: owner})


def drop_repair(smith: int) -> None:
    """
    去掉铁匠的维修或保养记录。铁匠没有记录时不写
    Keyword arguments:
    smith -- 铁匠的角色id
    """
    if str(smith) in _stored(REPAIRS, None):
        _put(REPAIRS, {k: v for k, v in repairs().items() if k != smith})


def settings(game: core.GameState | None = None) -> dict[int, int]:
    """
    装备维护设置
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    dict -- 设置id到设置值
    """
    return _by_id(SETTING, game)


def set_setting(sid: int, value: int) -> None:
    """
    改一项装备维护设置。表里没有这项时加在最后
    Keyword arguments:
    sid -- 设置id
    value -- 设置值
    """
    _put(SETTING, {**settings(), sid: value})


def operators(game: core.GameState | None = None) -> list[int]:
    """
    手动选择的装备维护对象
    Keyword arguments:
    game -- 给出时只读这个状态，不给时读当前缓冲区
    Return arguments:
    list -- 角色id，按选择的先后排列
    """
    return list(cast(tuple[int, ...], working.get(None, OPERATORS, game)))


def toggle_operator(cid: int) -> None:
    """
    切换一名角色是否在手动选择的装备维护对象里。
    角色在名单里时，去掉它第一次出现的那一项。角色不在名单里时，加在最后
    Keyword arguments:
    cid -- 角色id
    """
    current = operators()
    if cid in current:
        current.remove(cid)
    else:
        current.append(cid)
    working.put(None, OPERATORS, tuple(current))


def remap(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把检修地点、维修或保养记录（铁匠与装备所属角色两边）与手动选择的装备维护对象里的旧id换成新id
    Keyword arguments:
    old_to_new -- 旧id到新id，表里没有的id不变
    """
    _put(PLACES, {old_to_new.get(c, c): p for c, p in places().items()})
    _put(
        REPAIRS,
        {
            old_to_new.get(smith, smith): old_to_new.get(owner, owner)
            for smith, owner in repairs().items()
        },
    )
    current = operators()
    new = [old_to_new.get(cid, cid) for cid in current]
    if new != current:
        working.put(None, OPERATORS, tuple(new))


PICKLED = {
    "facility_damage_data": (DAMAGE, dict),
    "maintenance_place": (PLACES, dict),
    "maintenance_equipment_chara_id": (REPAIRS, dict),
    "equipment_maintain_setting": (SETTING, dict),
    "equipment_maintain_operator_ids": (OPERATORS, list),
}
""" 版本 15 之前的存档里，罗德岛对象上的属性名到 (全局键, 这个属性应有的类型) """


def _local(path: object) -> object:
    """
    把字符串里另一种系统的路径分隔符换成本系统的
    Keyword arguments:
    path -- 存下的值
    Return arguments:
    object -- 是字符串时为换过分隔符的字符串，不是时原样交回
    """
    foreign = "\\" if os.sep == "/" else "/"
    if isinstance(path, str) and foreign in path:
        return path.replace(foreign, os.sep)
    return path


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED 里的属性，把类型正是 PICKLED 所列类型的值写进当前缓冲区。
    手动选择的装备维护对象是空列表时不写。随后把设施损坏的场景路径与检修地点里另一种系统的路径分隔符换成本系统的。
    这一步在每次读档时都做，与存档版本无关
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 对象带着 PICKLED 里任一属性或 version 低于 15 时，为缺了或类型不符的属性个数，
    计法同 save_handle.update_dict_with_default。其余为 0
    """
    attrs = vars(loaded_dict["rhodes_island"])
    found = {name: attrs.pop(name) for name in PICKLED if name in attrs}
    kept = {n: v for n, v in found.items() if type(v) is PICKLED[n][1]}
    for name, value in kept.items():
        key = PICKLED[name][0]
        if key != OPERATORS:
            _put(key, value)
        elif value:
            working.put(None, key, tuple(value))
    stored = damage()
    _put(DAMAGE, {_local(scene): n for scene, n in stored.items()})
    _put(PLACES, {cid: _local(p) for cid, p in places().items()})
    return len(PICKLED) - len(kept) if found or version < 15 else 0
