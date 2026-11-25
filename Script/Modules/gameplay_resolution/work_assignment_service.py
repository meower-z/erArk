"""
岗位指派服务（work_assignment_service）
=======================================
提供岗位分组刷新、干员可指派岗位判定与岗位变更写入逻辑。
本模块不导入 Script.UI 与 Script.Settle。
"""

from dataclasses import dataclass
from types import FunctionType

from Script.Config import config_def, game_config
from Script.Core import get_text
from Script.Design import attr_calculation, basement, handle_premise, map_handle
from Script.Modules.domains import abilities, body_manage, chara_life, facility
from Script.Modules.domains import identity, roster, visitor, work

_: FunctionType = get_text._
""" 翻译api """

WARDEN = 191
""" 监狱长岗位的工作类型编号（191）。 """
TRAINEE = 193
""" 性爱练习生岗位的工作类型编号（193）。 """
TRAINING_IDS = range(30, 40)
""" 离开性爱练习生岗位时清空的身体管理训练项编号范围（30 至 39）。 """
PRISON_DORM = ["关押", "休息室"]
""" 监狱长专属休息室的系统地图路径段列表。 """


@dataclass(frozen=True, slots=True)
class Member:
    """岗位分组中的干员展示条目，含角色编号、名称与按钮标签。"""

    chara_id: int
    name: str
    label: str


@dataclass(frozen=True, slots=True)
class WorkGroup:
    """单个工作类型的分组展示数据，含岗位编号、标题标签与成员元组。"""

    work_id: int
    label: str
    members: tuple[Member, ...]


@dataclass(frozen=True, slots=True)
class WorkOption:
    """干员工作选择条目，含岗位编号、文本、可选标记与锁定原因。"""

    work_id: int
    text: str
    pickable: bool
    locked_reason: str | None


def _ability_name(ability_id: int) -> str:
    """返回指定能力配置名称的前两个字符作为岗位能力简称。"""
    return game_config.config_ability[ability_id].name[:2]


def _member(chara_id: int, ability_id: int) -> Member:
    """构造单个干员在岗位分组中的 Member 条目并按需附加能力等级。"""
    data = identity.of(chara_id)
    label = f"[{str(data.adv).rjust(4, '0')}]{data.name}"
    if ability_id != 0:
        label += f"(lv{abilities.ability(chara_id)[ability_id]})"
    return Member(chara_id, data.name, label)


def _assignable(chara_id: int) -> bool:
    """判断角色是否可排班：不是玩家、不是访客，且常规状态 2 与 7 均正常。"""
    return (
        chara_id != 0
        and not visitor.is_visitor(chara_id)
        and bool(handle_premise.handle_normal_2(chara_id))
        and bool(handle_premise.handle_normal_7(chara_id))
    )


def refresh_groups() -> list[WorkGroup]:
    """
    先刷新各岗位名册，再按工作类型分组返回可排班干员列表。
    调用 basement.update_work_people() 同步名册后汇总各岗位成员。
    Return arguments:
    list[WorkGroup] -- 按工作配置顺序排列的岗位分组列表
    """
    basement.update_work_people()
    members: dict[int, list[int]] = {
        cid: [] for cid in game_config.config_work_type
    }
    for chara_id in roster.active():
        if _assignable(chara_id):
            work_id = chara_life.work_type(identity.of(chara_id).cid)
            if work_id in members:
                members[work_id].append(chara_id)
    groups = []
    for work_id, data in game_config.config_work_type.items():
        label = data.name
        if data.ability_id != 0:
            label += f"({_ability_name(data.ability_id)})"
        label += _("({0}人)").format(len(members[work_id]))
        rows = tuple(_member(cid, data.ability_id) for cid in members[work_id])
        groups.append(WorkGroup(work_id, label, rows))
    return groups


def current_work_text(chara_id: int) -> str:
    """
    组装干员当前工作与可指派岗位列表的抬头说明文本。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    str -- 包含干员姓名、当前工作名称与所属部门的提示文本
    """
    data = game_config.config_work_type[chara_life.work_type(chara_id)]
    return (
        _("{0}的当前工作为：").format(identity.of(chara_id).name)
        + f"{data.name}({data.department})"
        + _("\n可指派的工作有：\n")
    )


def _open(data: config_def.WorkType, chara_id: int) -> tuple[bool, str]:
    """检查角色是否满足岗位的 need 条件与 place 对应设施的开放状态。"""
    reason = data.cant_reason
    if data.need != "无":
        passed, why = attr_calculation.judge_require(
            data.need.split("&"), chara_id
        )
        if not passed:
            return False, reason + " " + why
    if data.place in game_config.config_facility_open_name_set:
        open_cid = game_config.config_facility_open_name_to_cid[data.place]
        if not facility.is_open(open_cid):
            return False, reason
    return True, reason


def _unlocked(work_id: int, chara_id: int) -> bool:
    """判断特殊解锁岗位（tag 为 2 的 191 与 193）对角色是否已解锁。"""
    if work_id == WARDEN:
        return bool(
            handle_premise.handle_prisoner_in_custody(chara_id)
            and (
                handle_premise.handle_self_fall_3(chara_id)
                or handle_premise.handle_self_fall_4(chara_id)
            )
        )
    if work_id == TRAINEE:
        return bool(handle_premise.handle_ask_one_exercises(chara_id))
    return False


def work_options(chara_id: int) -> list[WorkOption]:
    """
    生成指定干员的全体岗位选项列表，含展示文案、可选标记与锁定原因。
    Keyword arguments:
    chara_id -- int，角色编号
    Return arguments:
    list[WorkOption] -- 按工作配置顺序排列的岗位选项列表
    """
    ability = abilities.ability(chara_id)
    options = []
    for work_id, data in game_config.config_work_type.items():
        is_open, reason = _open(data, chara_id)
        if data.tag == 2:
            is_open = _unlocked(work_id, chara_id)
        text = f"[{str(work_id).rjust(3, '0')}]{data.name}({data.place})"
        text = text.ljust(18, "　")
        if data.ability_id != 0:
            level = ability[data.ability_id]
            text += f"({_ability_name(data.ability_id)}:{level})".ljust(6, "　")
        else:
            text += "　" * 4
        text += f"：{data.describe}"
        pickable = is_open and data.tag in {0, 2}
        locked = None if is_open and data.tag != 1 else reason
        options.append(WorkOption(work_id, text, pickable, locked))
    return options


def assign_work(chara_id: int, work_id: int) -> None:
    """
    为干员指派新岗位，处理练习生清理、监狱长交接与宿舍变更并刷新名册。
    Keyword arguments:
    chara_id -- int，角色编号
    work_id -- int，目标工作类型编号
    Return arguments:
    None -- 无返回值
    """
    from Script.System.Dormitory_System import common as dormitory_common

    if chara_life.work_type(chara_id) == TRAINEE:
        body_manage.clear(chara_id, TRAINING_IDS)
    if handle_premise.handle_work_is_warden(chara_id):
        chara_life.work_type.set(chara_id, 0)
        dormitory_common.restore_character_dormitory(chara_id)
        work.set_warden(0)
    chara_life.work_type.set(chara_id, work_id)
    if handle_premise.handle_work_is_warden(chara_id):
        if work.warden() != 0 and work.warden() != chara_id:
            chara_life.work_type.set(work.warden(), 0)
            dormitory_common.restore_character_dormitory(work.warden())
        work.set_warden(chara_id)
        dormitory_common.register_permanent_dormitory(chara_id)
        chara_life.dormitory.set(
            chara_id, map_handle.get_map_system_path_str_for_list(PRISON_DORM)
        )
    basement.update_work_people()
