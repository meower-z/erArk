"""
全干员列表服务（operator_list_service）
=======================================
提供全干员一览页的能力列定义、筛选、排序、分页与行内标签查询。
本模块不导入 Script.UI 与 Script.Settle。
"""

from collections.abc import Callable, Mapping
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text, num
from Script.Design import attr_calculation, handle_premise, map_handle
from Script.Modules.domains import abilities, activity, chara_life
from Script.Modules.domains import chara_profile, hypnosis, needs, relations
from Script.Modules.domains import roster

_: FunctionType = get_text._
""" 翻译api """

PAGE_SIZE = 20
""" 全干员一览每页显示的干员行数。 """
FILTER_STEPS = {
    "work": 3,
    "fall": 5,
    "daughter": 3,
    "visitor": 3,
    "collection": 3,
}
""" 各筛选维度循环切换时的选项总数映射。 """
COLLECTED = 2
""" 角色设置字典中标记收藏状态的键编号（值为 1 表示已收藏）。 """
Columns = dict[int, list[tuple[str, int]]]
""" 能力类型编号（0 至 5）到 (列简称, 能力编号) 列表的映射类型。 """


def ability_columns() -> Columns:
    """
    按能力类型 0 至 5 分组返回能力列简称与编号。
    Return arguments:
    Columns -- 去除技能、感度、扩张与刻印字样后的能力列映射
    """
    columns: Columns = {kind: [] for kind in range(6)}
    for cid, data in game_config.config_ability.items():
        if data.ability_type in columns:
            name = data.name
            for suffix in (_("技能"), _("感度"), _("扩张"), _("刻印")):
                name = name.replace(suffix, "")
            columns[data.ability_type].append((name, cid))
    return columns


def _choice_ok(choice: int, flag: bool) -> bool:
    """按三态筛选值判断布尔条件是否通过（0 不限，1 须真，2 须假）。"""
    return choice == 0 or (choice == 1) == flag


def _fall_ok(choice: int, chara_id: int) -> bool:
    """按五态陷落筛选值判断角色陷落等级是否符合条件。"""
    level = attr_calculation.get_character_fall_level(chara_id, True)
    return (True, level == 0, level != 0, level > 0, level < 0)[choice]


def _passes(chara_id: int, filters: Mapping[str, int]) -> bool:
    """判断角色是否同时通过工作、陷落、女儿、访客与收藏五项筛选。"""
    return (
        _choice_ok(
            filters["work"], bool(handle_premise.handle_have_work(chara_id))
        )
        and _fall_ok(filters["fall"], chara_id)
        and _choice_ok(
            filters["daughter"],
            bool(handle_premise.handle_self_is_player_daughter(chara_id)),
        )
        and _choice_ok(
            filters["visitor"],
            bool(handle_premise.handle_self_visitor_flag_1(chara_id)),
        )
        and _choice_ok(
            filters["collection"],
            bool(handle_premise.handle_find_self_is_favorite(chara_id)),
        )
    )


def _equipment_rank(chara_id: int) -> int:
    """返回角色装备维护排序分值（完美为 2，损坏为 -1，其余为 0）。"""
    if handle_premise.handle_self_equipment_maintenance_ge_2(chara_id):
        return 2
    if handle_premise.handle_self_equipment_damaged_ge_2(chara_id):
        return -1
    return 0


def _fixed_sorts() -> dict[str, Callable[[int], num.Num | float]]:
    """返回固定排序键名称到单角色取值函数的映射表。"""
    return {
        _("无"): lambda cid: 0,
        _("默认ID"): lambda cid: cid,
        _("好感"): lambda cid: relations.favorability(cid).get(0, 0),
        _("信赖"): relations.trust,
        _("体力"): lambda cid: needs.of(cid)["hit"],
        _("最大体力"): lambda cid: needs.of(cid)["hit_max"],
        _("气力"): lambda cid: needs.of(cid)["mana"],
        _("最大气力"): lambda cid: needs.of(cid)["mana_max"],
        _("催眠深度"): hypnosis.degree,
        _("工作"): chara_life.work_type,
        _("装备"): _equipment_rank,
    }


def sort_value(chara_id: int, key: str, columns: Columns) -> num.Num | float:
    """
    计算角色在指定排序键下的排序数值。
    Keyword arguments:
    chara_id -- int，角色编号
    key -- str，固定排序键名或能力列简称
    columns -- Columns，能力类型到能力列的映射表
    Return arguments:
    num.Num | float -- 对应的排序数值，未命中任何键时返回 0
    """
    fixed = _fixed_sorts().get(key)
    if fixed is not None:
        return fixed(chara_id)
    for cols in columns.values():
        for name, ability_id in cols:
            if name == key:
                return abilities.ability(chara_id).get(ability_id, 0)
    return 0


def is_collected(chara_id: int) -> bool:
    """
    判断角色是否已标记为收藏。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    bool -- 角色设置键 2 为 1 时返回 True，否则返回 False
    """
    return chara_profile.chara_setting(chara_id).get(COLLECTED, 0) == 1


def visible_ids(
    filters: Mapping[str, int],
    main: str,
    sub: str,
    reverse: bool,
    collected_first: bool,
) -> list[int]:
    """
    筛选并排序在编非玩家干员，返回可见角色编号列表。
    Keyword arguments:
    filters -- Mapping[str, int]，五项筛选维度当前值
    main, sub -- str，主排序键名与副排序键名
    reverse -- bool，是否整体倒序
    collected_first -- bool，是否启用收藏优先排序
    Return arguments:
    list[int] -- 筛选并排序后的干员角色编号列表
    """
    columns = ability_columns()
    found = [
        cid for cid in roster.active() if cid != 0 and _passes(cid, filters)
    ]
    found.sort(
        key=lambda cid: (
            0 if collected_first and is_collected(cid) else 1,
            sort_value(cid, main, columns),
            sort_value(cid, sub, columns),
            cid,
        ),
        reverse=reverse,
    )
    return found


def page_of(count: int, page: int) -> tuple[int, int]:
    """
    计算总页数并将目标页码钳制到合法范围。
    Keyword arguments:
    count -- int，可见干员总数
    page -- int，当前请求的页码（从 0 开始）
    Return arguments:
    tuple[int, int] -- (钳制后的页码, 至少为 1 的总页数)
    """
    total = max(1, (count + PAGE_SIZE - 1) // PAGE_SIZE)
    return min(max(page, 0), total - 1), total


def fall_label(chara_id: int) -> tuple[str, str]:
    """
    返回角色最高优先级陷落素质的名称与显示样式。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    tuple[str, str] -- (陷落名称, 样式名)，无陷落时返回 (无, standard)
    """
    talents = abilities.talent(chara_id)
    for talent_id, name, style in (
        (204, _("爱侣"), "hot_pink"),
        (203, _("恋人"), "hot_pink"),
        (202, _("恋慕"), "deep_pink"),
        (201, _("思慕"), "light_pink"),
        (214, _("奴隶"), "levelex"),
        (213, _("宠物"), "red"),
        (212, _("驯服"), "crimson"),
        (211, _("屈从"), "coral"),
    ):
        if talents.get(talent_id):
            return name, style
    return _("无"), "standard"


def equipment_label(chara_id: int) -> tuple[str, str]:
    """
    返回角色装备维护状态的展示文本与样式名。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    tuple[str, str] -- 损坏/red、完美/spring_green 或 正常/standard
    """
    if handle_premise.handle_self_equipment_damaged_ge_2(chara_id):
        return _("损坏"), "red"
    if handle_premise.handle_self_equipment_maintenance_ge_2(chara_id):
        return _("完美"), "spring_green"
    return _("正常"), "standard"


def position_text(chara_id: int) -> str:
    """
    返回角色当前所在位置的展示路径文本。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    str -- 地图系统格式化的当前位置路径文本
    """
    return map_handle.get_map_system_path_str_for_list(
        activity.position(chara_id)
    )


def work_name(chara_id: int) -> str:
    """
    返回角色当前所任工作的配置名称。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    str -- 角色当前工作类型在配置中的名称
    """
    return game_config.config_work_type[chara_life.work_type(chara_id)].name


def operator_ids() -> list[int]:
    """
    返回除玩家外的所有在编干员角色编号列表。
    Return arguments:
    list[int] -- 排除角色编号 0 后的在编干员编号列表
    """
    return [cid for cid in roster.active() if cid != 0]
