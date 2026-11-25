"""
调试面板角色状态修改服务（debug_chara_edit）
============================================
提供调试面板 NPC 角色编辑页各子页面的状态写入逻辑与统一分发入口。
本模块不导入 Script.UI 与 Script.Settle。
"""

from collections.abc import Callable
from types import MappingProxyType
from typing import Any

from Script.Design import attr_calculation, game_time
from Script.Modules.domains import abilities, action_info, activity, chara_life
from Script.Modules.domains import dirty, flags, h_meters, h_state, hypnosis
from Script.Modules.domains import needs, pregnancy, relations, status
from Script.Modules.gameplay_resolution.debug_chara_view import FLAG_ROWS

_BASE_FIELDS = (
    (0, needs.set, "hit"),
    (1, needs.set, "hit_max"),
    (2, needs.set, "mana"),
    (3, needs.set, "mana_max"),
    (4, needs.set, "sanity"),
    (5, needs.set, "sanity_max"),
    (11, needs.set, "tired"),
    (12, needs.set, "urine"),
    (13, needs.set, "hunger"),
    (14, needs.set, "sleep"),
    (15, needs.set, "angry"),
    (16, h_meters.set, "eja"),
    (19, needs.set, "milk"),
    (21, needs.set, "desire"),
    (22, h_meters.set, "semen"),
    (23, h_meters.set, "semen_max"),
    (24, needs.set, "drunk"),
)
""" 基础属性子页数值项编号到领域写入函数及字段名的映射表。 """
_DATE_PARTS = ("year", "month", "day")
""" 日期分量索引 0、1、2 对应的年、月、日属性名元组。 """


def _base(cid: int, index: Any, value: int) -> bool:
    """修改角色基础属性、好感度、信赖度或乳汁上限（子页 000）。"""
    for key, setter, field in _BASE_FIELDS:
        if index == key:
            setter(cid, **{field: value})
    if index == 17:
        relations.favorability.set_item(cid, 0, value)
    elif index == 18:
        relations.trust.set(cid, value)
    elif index == 20:
        pregnancy.set_milk_max(cid, value)
    return True


def _table(
    view: Callable[[int], abilities.Table],
) -> Callable[[int, Any, int], bool]:
    """生成写入指定角色数值表的子页修改回调函数。"""

    def write(cid: int, index: Any, value: int) -> bool:
        """按索引将数值写入指定角色对应的数值表视图。"""
        view(cid)[index] = value
        return True

    return write


def _second(cid: int, index: Any, value: int) -> bool:
    """修改角色指定二段行为的数值（子页 004）。"""
    activity.set_second_behavior(cid, index, value)
    return True


def _state(cid: int, index: Any, value: int) -> bool:
    """修改角色指定状态项的数值（子页 006）。"""
    status.set(cid, index, value)
    return True


def _assistant(cid: int, index: Any, value: int) -> bool:
    """修改角色指定助理服务项的数值（子页 014）。"""
    relations.assistant_services.set_item(cid, index, value)
    return True


def _add_semen(slots: Any, value: int, place: int) -> None:
    """为精液槽表全部位增加精液量并重算对应精液等级。"""
    for i in range(len(slots)):
        slots[i][1] += value
        slots[i][2] = attr_calculation.get_semen_now_level(
            slots[i][1], i, place
        )


def _dirty(cid: int, index: Any, value: int) -> bool:
    """修改角色污浊状态、精液量或精液等级（子页 012）。"""
    with dirty.editing(cid) as d:
        if index == 3:
            d.a_clean = value
        elif index == 8:
            _add_semen(d.body_semen, value, 0)
            _add_semen(d.cloth_semen, value, 1)
            _add_semen(d.cloth_locker_semen, value, 2)
        elif index[0] in (0, 1, 2):
            table = (d.body_semen, d.cloth_semen, d.cloth_locker_semen)
            table[index[0]][index[1]][index[2]] = value
        elif index[0] in (4, 6):
            slots = d.body_semen if index[0] == 4 else d.cloth_semen
            slots[index[1]][1] = value
            slots[index[1]][2] = attr_calculation.get_semen_now_level(
                value, index[1], 0 if index[0] == 4 else 1
            )
        elif index[0] in (5, 7):
            slots = d.body_semen if index[0] == 5 else d.cloth_semen
            slots[index[1]][2] = value
    return True


def _h_state(cid: int, index: Any, value: int) -> bool:
    """修改角色本次 H 的道具、捆绑、射精位与高潮记录（子页 013）。"""
    with h_state.editing(cid) as hs:
        if index == 1:
            hs.bondage = value
        elif index == 2:
            hs.insert_position = value
        elif index == 3:
            hs.shoot_position_body = value
        elif index == 4:
            hs.shoot_position_cloth = value
        elif index[0] == 0:
            hs.body_item[index[1]][index[2]] = value
        elif index[0] == 5:
            hs.orgasm_level[index[1]] = value
        elif index[0] == 6:
            hs.orgasm_count[index[1]][index[2]] = value
    return True


def _fun(cid: int, index: Any, value: int) -> bool:
    """修改角色娱乐类型、借书集合或还书概率（子页 017）。"""
    if index[0] == 0:
        chara_life.entertainment_type.set(cid, [index[1], index[2], index[3]])
    elif index[0] == 1:
        with chara_life.borrow_book_id_set.editing(cid) as books:
            if index[1] == 1:
                books.add(index[2])
            else:
                books.remove(index[2])
    elif index[0] == 2:
        chara_life.book_return_possibility.set(cid, index[1])
    return True


def _shift_year(cid: int, field: str, delta: int) -> None:
    """将角色怀孕记录中指定日期字段的年份偏移指定年数。"""
    with pregnancy.editing(cid) as preg:
        old = getattr(preg, field)
        setattr(preg, field, old.replace(year=old.year + delta))


def _set_date(cid: int, field: str, part: int, value: int) -> None:
    """按年月日索引修改角色怀孕记录中的指定日期字段。"""
    with pregnancy.editing(cid) as preg:
        if part in (0, 1, 2):
            old = getattr(preg, field)
            setattr(preg, field, old.replace(**{_DATE_PARTS[part]: value}))


def _pregnancy(cid: int, index: Any, value: int) -> bool:
    """修改角色怀孕周期、日期、素质或乳汁，单元素子项返回 False。"""
    if index == 0:
        pregnancy.update(cid, fertilization_rate=value)
    elif index == 1:
        pregnancy.update(cid, reproduction_period=value)
    elif index == 5:
        abilities.talent(cid)[22] = 1
        now = game_time.now()
        pregnancy.update(cid, fertilization_time=now.replace(year=now.year - 1))
    elif index == 6:
        _shift_year(relations.child_id_list(cid)[-1], "born_time", -1)
    elif index == 7:
        needs.set(cid, milk=value)
    elif index == 8:
        pregnancy.set_milk_max(cid, value)
    elif index[0] in (2, 3, 4):
        if len(index) == 1:
            return False
        if index[0] == 3:
            abilities.talent(cid)[20 + index[1]] = value
            pregnancy.update(cid, fertilization_time=game_time.now())
        else:
            field = "fertilization_time" if index[0] == 2 else "born_time"
            _set_date(cid, field, index[1], value)
    return True


def _relations(cid: int, index: Any, value: int) -> bool:
    """修改角色父母编号或增删孩子列表条目（子页 019）。"""
    if index[0] == 0:
        relations.father_id.set(cid, index[1])
    elif index[0] == 1:
        relations.mother_id.set(cid, index[1])
    elif index[0] == 2:
        with relations.child_id_list.editing(cid) as children:
            if index[1] == 1:
                children.append(index[2])
            else:
                children.remove(index[2])
    return True


def _flags(cid: int, index: Any, value: int) -> bool:
    """按编号修改角色特殊 flag 或当日体检时间（子页 020）。"""
    if 0 <= index[0] < len(FLAG_ROWS):
        flags.set(cid, **{FLAG_ROWS[index[0]][1]: index[1]})
    elif index[0] == 29:
        action_info.set(cid, "health_check_today", index[1])
    return True


def _hypnosis(cid: int, index: Any, value: int) -> bool:
    """修改角色催眠程度、体控开关或追加角色扮演项（子页 021）。"""
    fields = ("increase_body_sensitivity", "force_ovulation")
    fields += ("blockhead", "active_h")
    if index[0] == 0:
        hypnosis.set(cid, hypnosis_degree=index[1])
    elif index[0] in (1, 2, 3, 4):
        hypnosis.set(cid, **{fields[index[0] - 1]: bool(index[1])})
    elif index[0] == 5:
        roleplay = hypnosis.view(cid).roleplay
        hypnosis.set_roleplay(cid, [*roleplay, index[1]])
    return True


EDITS: MappingProxyType[int, Callable[[int, Any, int], bool]] = (
    MappingProxyType(
        {
            0: _base,
            4: _second,
            6: _state,
            7: _table(abilities.ability),
            8: _table(abilities.experience),
            9: _table(abilities.juel),
            10: _table(abilities.talent),
            12: _dirty,
            13: _h_state,
            14: _assistant,
            17: _fun,
            18: _pregnancy,
            19: _relations,
            20: _flags,
            21: _hypnosis,
        }
    )
)
""" 角色调试子页编号到状态写入函数的只读映射。 """


def edit(key: int, cid: int, index: Any, value: int) -> bool:
    """
    按子页编号分发角色状态修改操作。
    Keyword arguments:
    key -- int，角色调试子页编号
    cid -- int，目标角色编号
    index -- Any，解析后的项索引或逗号列表
    value -- int，双输入子页传入的目标数值
    Return arguments:
    bool -- 仅子页 018 收到首项 2 至 4 的单元素列表时返回 False 供重输
    其余返回均为 True 以刷新，含不写入项（如 020 只读项 28 及未定义项）
    """
    return EDITS[key](cid, index, value)
