"""
外勤选人列表服务（commission_roster_service）
=============================================
提供外勤选人界面的筛选、排序、分页、出勤校验与自动选人逻辑。
本模块不导入 Script.UI 与 Script.Settle。
"""

from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import attr_calculation, handle_premise
from Script.Modules.domains import abilities, chara_life, chara_profile
from Script.Modules.domains import identity, roster
from Script.Modules.gameplay_resolution import field_commission_service

_: FunctionType = get_text._
""" 翻译api """

PAGE_SIZE = 20
""" 外勤选人列表每页显示的干员行数（20）。 """
FILTER_STEPS = {
    "filter_work": 3,
    "filter_fall": 5,
    "filter_daughter": 3,
    "filter_collection": 3,
}
""" 四项筛选按键对应的循环状态总数映射。 """
SORT_TOGGLES = {
    "sort_sel": "selected_first",
    "sort_col": "collection_first",
    "sort_work": "work_sort",
}
""" 三项排序开关按键到 RosterView 字段名的映射。 """
WORK_SKILL = 4
""" 工作技能在能力配置表中的 ability_type 编号（4）。 """


@dataclass
class RosterView:
    """外勤选人界面的筛选、排序、装备加成与页码状态。"""

    page: int = 0
    """ 当前选人列表页码（从 0 开始）。 """
    skill: int = 0
    """ 当前按技能排序的能力编号，0 表示默认按角色编号排序。 """
    filter_work: int = 0
    """ 工作状态筛选档位（0 不限，1 有工作，2 无工作）。 """
    filter_fall: int = 0
    """ 陷落状态筛选档位（0 不限，1 无，2 有，3 爱情，4 隶属）。 """
    filter_daughter: int = 0
    """ 玩家女儿筛选档位（0 不限，1 是，2 否）。 """
    filter_collection: int = 0
    """ 收藏状态筛选档位（0 不限，1 是，2 否）。 """
    selected_first: bool = True
    """ 是否将已选入派遣队伍的干员排在前面。 """
    collection_first: bool = False
    """ 是否将已收藏干员排在未收藏干员之前。 """
    work_sort: bool = False
    """ 是否按干员当前工作类型编号升序排列。 """
    equipment: bool = True
    """ 计算技能数值时是否计入装备维护与损坏修正。 """


def press(view: RosterView, key: str) -> None:
    """
    根据选人界面的输入键码原地更新筛选、排序或页码状态。
    Keyword arguments:
    view -- RosterView，原地修改的选人界面状态对象
    key -- str，界面返回的按钮键码
    """
    if key == "888":
        view.page -= 1
    elif key == "222":
        view.page += 1
    elif key in FILTER_STEPS:
        step = (getattr(view, key) + 1) % FILTER_STEPS[key]
        setattr(view, key, step)
        view.page = 0
    elif key in SORT_TOGGLES:
        name = SORT_TOGGLES[key]
        setattr(view, name, not getattr(view, name))
        view.page = 0
    elif key == "toggle_equip":
        view.equipment = not view.equipment
    elif key.startswith("sort_"):
        view.skill = int(key.split("_")[1])
        view.page = 0


def skill_columns() -> list[tuple[str, int]]:
    """
    返回全部工作技能的列简称与能力编号列表。
    Return arguments:
    list[tuple[str, int]] -- 去除“技能”字样的 (简称, 编号) 列表
    """
    return [
        (data.name.replace(_("技能"), ""), cid)
        for cid, data in game_config.config_ability.items()
        if data.ability_type == WORK_SKILL
    ]


def skill_value(chara_id: int, ability_id: int, equipment: bool) -> int:
    """
    计算角色指定技能的显示与排序数值，可叠加装备修正。
    Keyword arguments:
    chara_id -- int，角色编号
    ability_id -- int，能力编号
    equipment -- bool，是否启用装备维护与损坏修正
    Return arguments:
    int -- 计入或忽略装备修正后的技能数值
    """
    value = abilities.ability(chara_id).get(ability_id, 0)
    if equipment:
        if (
            handle_premise.handle_self_equipment_maintenance_ge_2(chara_id)
            and value < 8
        ):
            value += 1
        if (
            handle_premise.handle_self_equipment_damaged_ge_2(chara_id)
            and value > 0
        ):
            value -= 1
    return value


def is_collected(chara_id: int) -> bool:
    """
    判断角色在角色设置中是否已标记收藏。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    bool -- 收藏标记为 1 时返回 True
    """
    return chara_profile.chara_setting(chara_id).get(2, 0) == 1


def can_dispatch(chara_id: int) -> bool:
    """
    判断角色是否满足外勤出勤的全部硬性前提条件。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    bool -- 正常在线、无重损且非特殊职位或访客时返回 True
    """
    return bool(
        handle_premise.handle_normal_2(chara_id)
        and handle_premise.handle_normal_7(chara_id)
        and not handle_premise.handle_self_equipment_damaged_ge_3(chara_id)
        and not handle_premise.handle_work_is_warden(chara_id)
        and not handle_premise.handle_is_assistant(chara_id)
        and not handle_premise.handle_self_visitor_flag_1(chara_id)
    )


def _choice_ok(choice: int, flag: bool) -> bool:
    """按三态筛选档位判断布尔标志是否通过（0 不限，1 须真，2 须假）。"""
    return choice == 0 or (choice == 1) == flag


def _fall_ok(choice: int, chara_id: int) -> bool:
    """按五态陷落筛选档位判断角色陷落等级是否通过。"""
    level = attr_calculation.get_character_fall_level(chara_id, True)
    has_fall = level != 0
    return (True, not has_fall, has_fall, level > 0, level < 0)[choice]


def _passes(chara_id: int, view: RosterView) -> bool:
    """判断角色是否同时通过工作、陷落、女儿与收藏四项筛选。"""
    return (
        _choice_ok(
            view.filter_work, bool(handle_premise.handle_have_work(chara_id))
        )
        and _fall_ok(view.filter_fall, chara_id)
        and _choice_ok(
            view.filter_daughter,
            bool(handle_premise.handle_self_is_player_daughter(chara_id)),
        )
        and _choice_ok(view.filter_collection, is_collected(chara_id))
    )


def candidates(view: RosterView, team: list[int]) -> list[int]:
    """
    筛选可出勤干员并按当前视图规则排序后返回角色编号列表。
    Keyword arguments:
    view -- RosterView，当前选人界面的筛选与排序状态
    team -- list[int]，当前已选中的派遣角色编号列表
    Return arguments:
    list[int] -- 通过筛选且排序完成的可派遣角色编号列表
    """
    ids = [
        cid
        for cid in roster.active()
        if cid != 0 and can_dispatch(cid) and _passes(cid, view)
    ]
    ids.sort(
        key=lambda cid: (
            0 if view.selected_first and cid in team else 1,
            0 if view.collection_first and is_collected(cid) else 1,
            (
                -skill_value(cid, view.skill, view.equipment)
                if view.skill != 0
                else 0
            ),
            chara_life.work_type(cid) if view.work_sort else 0,
            cid,
        )
    )
    return ids


def page_of(ids: list[int], page: int) -> tuple[int, int, list[int]]:
    """
    按每页行数对角色编号列表分页并将页码钳制到合法范围。
    Keyword arguments:
    ids -- list[int]，候选角色编号列表
    page -- int，请求的页码（从 0 开始）
    Return arguments:
    tuple[int, int, list[int]] -- (有效页码, 总页数, 当前页编号)
    """
    total = max(1, (len(ids) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(page, 0), total - 1)
    start = page * PAGE_SIZE
    return page, total, ids[start : start + PAGE_SIZE]


def equipment_label(chara_id: int) -> tuple[str, str]:
    """
    返回角色装备状态的显示文本与界面颜色样式名。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    tuple[str, str] -- (状态文本, 样式名)，损坏/完美/正常三态
    """
    if handle_premise.handle_self_equipment_damaged_ge_2(chara_id):
        return _("损坏"), "red"
    if handle_premise.handle_self_equipment_maintenance_ge_2(chara_id):
        return _("完美"), "spring_green"
    return _("正常"), "standard"


def auto_pick(commission_id: int, team: list[int]) -> None:
    """
    将委托指定且可出勤的在编干员自动追加到派遣队伍中。
    Keyword arguments:
    commission_id -- int，委托编号
    team -- list[int]，原地追加成员的派遣角色编号列表
    """
    advs = field_commission_service.required_advs(commission_id)
    for cid in roster.active():
        if cid == 0:
            continue
        if identity.of(cid).adv in advs and cid not in team:
            if can_dispatch(cid):
                team.append(cid)
