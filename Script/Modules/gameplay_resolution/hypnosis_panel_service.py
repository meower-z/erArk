"""
催眠面板规则服务（hypnosis_panel_service）
============================================
本模块提供催眠能力与类型行数据、体控与心控指令列表、强制排卵拦截判定以及角色扮演目录、可选判定、变更与结算规则。
本模块公开数据类 TalentRow、TypeRow、ControlRow、RoleplayCatalog 与 RoleplayOption。
本模块公开函数 talent_rows、type_rows、set_hypnosis_type、control_rows、force_ovulation_blocked、
roleplay_catalog、selected_names、can_select、roleplay_options、job_prefix、with_roleplay 与 settle_roleplay。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import handle_premise, hypnosis_state
from Script.Modules.domains import abilities, flags, hypnosis, player_ability

_: FunctionType = get_text._
""" 翻译api """


@dataclass(frozen=True, slots=True)
class TalentRow:
    """玩家催眠能力行，含能力名称 name、说明 info、最高催眠深度 max_degree 与解锁标志 unlocked。"""

    name: str
    info: str
    max_degree: int
    unlocked: bool


@dataclass(frozen=True, slots=True)
class TypeRow:
    """
    催眠类型展示行，记录编号 type_id、名称 name、前置能力名 talent_name、
    所需深度 need_degree、说明 introduce 以及当前是否可选 available。
    """

    type_id: int
    name: str
    talent_name: str
    need_degree: int
    introduce: str
    available: bool


@dataclass(frozen=True, slots=True)
class ControlRow:
    """控制指令行，记录行为编号 behavior_id、行为名称 name 与子类型说明 introduce（无子类型时为 None）。"""

    behavior_id: str
    name: str
    introduce: str | None


@dataclass(frozen=True, slots=True)
class RoleplayCatalog:
    """
    角色扮演分组目录，记录特殊分组名 special_type、普通分组名顺序 type_list、
    是否存在特殊项 has_special 以及按分组名映射到成员编号元组的 members。
    """

    special_type: str
    type_list: tuple[str, ...]
    has_special: bool
    members: Mapping[str, tuple[int, ...]]

    def sections(self) -> tuple[tuple[str, bool], ...]:
        """
        按展示顺序返回全部分组名称及其是否为特殊分组的二元组元组。
        普通分组按 type_list 顺序排在前面，has_special 为 True 时将特殊分组附在末尾。
        Return arguments:
        tuple[tuple[str, bool], ...] -- (分组名, 是否特殊分组) 二元组元组
        """
        normal = tuple((name, False) for name in self.type_list)
        if self.has_special:
            return normal + ((self.special_type, True),)
        return normal


@dataclass(frozen=True, slots=True)
class RoleplayOption:
    """角色扮演选项，记录编号 cid、展示文本 text、名称 name、可选标志 selectable 与已选标志 chosen。"""

    cid: int
    text: str
    name: str
    selectable: bool
    chosen: bool


def talent_rows() -> tuple[TalentRow, ...]:
    """
    按 config_hypnosis_talent_of_pl 顺序返回玩家（角色 0）的催眠能力展示行。
    Return arguments:
    tuple[TalentRow, ...] -- 催眠能力展示行元组
    """
    talent = abilities.talent(0)
    rows = []
    for hypnosis_data in game_config.config_hypnosis_talent_of_pl.values():
        talent_id = hypnosis_data.hypnosis_talent_id
        talent_data = game_config.config_talent[talent_id]
        rows.append(
            TalentRow(
                talent_data.name,
                talent_data.info,
                hypnosis_data.max_hypnosis_degree,
                bool(talent[talent_id]),
            )
        )
    return tuple(rows)


def type_rows(target_id: int) -> tuple[TypeRow, ...]:
    """
    按 config_hypnosis_type 顺序返回各催眠类型展示行并判定可用性。
    玩家持有对应能力，且无目标（target_id 为 0）或 target_id > 0 时目标催眠深度不低于需求、
    未处于临产或产后状态，available 为 True。
    Keyword arguments:
    target_id -- int，当前交互目标角色编号，0 表示无目标
    Return arguments:
    tuple[TypeRow, ...] -- 催眠类型展示行元组
    """
    talent = abilities.talent(0)
    rows = []
    for type_id, type_data in game_config.config_hypnosis_type.items():
        need = type_data.hypnosis_degree
        available = bool(talent[type_data.talent_id]) and (
            target_id == 0
            or (
                target_id > 0
                and hypnosis.degree(target_id) >= need
                and not handle_premise.handle_self_parturient_or_postpartum(
                    target_id
                )
            )
        )
        rows.append(
            TypeRow(
                type_id,
                type_data.name,
                game_config.config_talent[type_data.talent_id].name,
                need,
                type_data.introduce,
                available,
            )
        )
    return tuple(rows)


def set_hypnosis_type(type_id: int) -> None:
    """
    将玩家（角色 0）的催眠类型设为指定编号。
    Keyword arguments:
    type_id -- int，目标催眠类型编号
    Return arguments:
    None -- 无返回值
    """
    player_ability.set(0, hypnosis_type=type_id)


def control_rows(mind: bool) -> tuple[ControlRow, ...]:
    """
    按 config_behavior 顺序筛选带“心控”或“体控”标签的控制指令行。
    Keyword arguments:
    mind -- bool，True 筛选心控指令，False 筛选体控指令
    Return arguments:
    tuple[ControlRow, ...] -- 匹配的控制指令行元组
    """
    tag = "心控" if mind else "体控"
    rows = []
    for behavior_id, behavior_data in game_config.config_behavior.items():
        if tag not in behavior_data.tag:
            continue
        sub_type_id = game_config.config_hypnosis_sub_type_by_behaivor.get(
            behavior_id, 0
        )
        introduce = None
        if sub_type_id > 0:
            introduce = game_config.config_hypnosis_sub_type[
                sub_type_id
            ].introduce
        rows.append(ControlRow(behavior_id, behavior_data.name, introduce))
    return tuple(rows)


def force_ovulation_blocked() -> bool:
    """
    判断玩家当前交互目标是否处于排卵日或受精/妊娠状态而阻止强制排卵。
    Return arguments:
    bool -- True 表示禁止强制排卵，False 表示允许
    """
    return bool(
        handle_premise.handle_t_reproduction_period_3(0)
        or handle_premise.handle_t_fertilization_or_pregnancy(0)
    )


def roleplay_catalog() -> RoleplayCatalog:
    """
    扫描 config_roleplay（跳过编号 0）构建角色扮演分组目录。
    子类型为“特殊”的条目归入特殊分组，其余条目按首次出现顺序归入各自类型分组。
    Return arguments:
    RoleplayCatalog -- 角色扮演分组目录对象
    """
    special_type = _("特殊")
    type_list: list[str] = []
    has_special = False
    for cid, roleplay_data in game_config.config_roleplay.items():
        if cid == 0:
            continue
        if roleplay_data.sub_type == special_type:
            has_special = True
        elif roleplay_data.type not in type_list:
            type_list.append(roleplay_data.type)
    members: dict[str, list[int]] = {name: [] for name in type_list}
    if has_special:
        members[special_type] = []
    for cid, roleplay_data in game_config.config_roleplay.items():
        if cid == 0:
            continue
        if roleplay_data.sub_type == special_type:
            members[special_type].append(cid)
        elif roleplay_data.type in members:
            members[roleplay_data.type].append(cid)
    return RoleplayCatalog(
        special_type,
        tuple(type_list),
        has_special,
        {name: tuple(cids) for name, cids in members.items()},
    )


def selected_names(selected: list[int]) -> tuple[str, ...]:
    """
    按顺序返回已选编号中存在于 config_roleplay 且名称不为“无”的角色扮演名称。
    Keyword arguments:
    selected -- list[int]，已选角色扮演编号列表
    Return arguments:
    tuple[str, ...] -- 过滤后的角色扮演名称元组
    """
    names = []
    for cid in selected:
        if cid not in game_config.config_roleplay:
            continue
        name = game_config.config_roleplay[cid].name
        if name != _("无"):
            names.append(name)
    return tuple(names)


def can_select(
    cid: int,
    selected_special_cid: int | None,
    selected_type_cid: dict[str, int],
    t: str,
    selected: list[int],
) -> bool:
    """
    判断指定角色扮演编号在当前选择状态下是否允许选中。
    已选特殊项、同分组已选他项、“非家庭”遇已选“家庭”、非“职业”且非“通用”/“无”子类型缺少同子类型已选“职业”，
    或名称为“同学”且已选“教师”时均返回 False。
    Keyword arguments:
    cid -- int，待判定的角色扮演编号
    selected_special_cid -- int | None，当前已选特殊项编号，无则为 None
    selected_type_cid -- dict[str, int]，各普通分组当前已选编号映射
    t -- str，当前分组名称
    selected -- list[int]，当前已选角色扮演编号列表
    Return arguments:
    bool -- 允许选中返回 True，否则返回 False
    """
    roleplay_data = game_config.config_roleplay[cid]
    main_type = roleplay_data.type
    sub_type = roleplay_data.sub_type
    if selected_special_cid is not None:
        return False
    if t in selected_type_cid and cid != selected_type_cid[t]:
        return False
    if sub_type == _("非家庭") and _("家庭") in selected_type_cid:
        return False
    if main_type != _("职业") and sub_type not in [_("通用"), _("无")]:
        if not any(
            other in game_config.config_roleplay
            and game_config.config_roleplay[other].type == _("职业")
            and game_config.config_roleplay[other].sub_type == sub_type
            for other in selected
        ):
            return False
    if roleplay_data.name == _("同学"):
        return not any(
            other in game_config.config_roleplay
            and game_config.config_roleplay[other].name == _("教师")
            for other in selected
        )
    return True


def roleplay_options(
    catalog: RoleplayCatalog, section: str, special: bool, selected: list[int]
) -> tuple[RoleplayOption, ...]:
    """
    构建指定角色扮演分组下的全部选项行及标签、可选与已选状态。
    特殊分组标签为“[cid]名称”，仅在已有其他特殊项时不可选且 chosen 恒为 False；
    普通分组按非“无”子类型附加“(子类型)”，已选或通过 can_select 判定时可选。
    Keyword arguments:
    catalog -- RoleplayCatalog，角色扮演分组目录
    section -- str，目标分组名称
    special -- bool，是否为特殊分组
    selected -- list[int]，当前已选角色扮演编号列表
    Return arguments:
    tuple[RoleplayOption, ...] -- 分组内各选项行元组
    """
    special_cids = catalog.members.get(catalog.special_type, ())
    selected_special_cid = next(
        (cid for cid in selected if cid in special_cids), None
    )
    selected_type_cid: dict[str, int] = {}
    for name in catalog.type_list:
        for cid in catalog.members[name]:
            if cid in selected:
                selected_type_cid[name] = cid
                break
    options = []
    for cid in catalog.members[section]:
        roleplay_data = game_config.config_roleplay[cid]
        if special:
            text = f"[{cid}]{roleplay_data.name}"
            selectable = (
                selected_special_cid is None or cid == selected_special_cid
            )
            chosen = False
        else:
            text = f"[{cid}]"
            if roleplay_data.sub_type != _("无"):
                text += f"({roleplay_data.sub_type})"
            text += roleplay_data.name
            chosen = cid in selected
            selectable = chosen or can_select(
                cid, selected_special_cid, selected_type_cid, section, selected
            )
        options.append(
            RoleplayOption(cid, text, roleplay_data.name, selectable, chosen)
        )
    return tuple(options)


def job_prefix(cid: int) -> str | None:
    """
    返回“职业”类角色扮演条目的非“无”子类型前缀，其余条目返回 None。
    Keyword arguments:
    cid -- int，角色扮演编号
    Return arguments:
    str | None -- 职业子类型名称，不适用时为 None
    """
    roleplay_data = game_config.config_roleplay[cid]
    if roleplay_data.type == _("职业") and roleplay_data.sub_type != _("无"):
        return roleplay_data.sub_type
    return None


def with_roleplay(
    catalog: RoleplayCatalog, selected: list[int], cid: int
) -> list[int]:
    """
    返回追加指定角色扮演编号后的新选择列表，不修改原列表。
    选中特殊项时先清空列表；选中“家庭”或“职业”项时先移除非“家庭”且非“职业”的已选项；最后追加 cid。
    Keyword arguments:
    catalog -- RoleplayCatalog，角色扮演分组目录
    selected -- list[int]，当前已选角色扮演编号列表
    cid -- int，待追加的角色扮演编号
    Return arguments:
    list[int] -- 更新后的角色扮演编号新列表
    """
    result = list(selected)
    roleplay_data = game_config.config_roleplay[cid]
    if cid != 0 and roleplay_data.sub_type == catalog.special_type:
        result.clear()
    anchor_types = [_("家庭"), _("职业")]
    if roleplay_data.type in anchor_types:
        result = [
            rid
            for rid in result
            if rid not in game_config.config_roleplay
            or game_config.config_roleplay[rid].type in anchor_types
        ]
    result.append(cid)
    return result


def settle_roleplay(
    target_id: int, selected: list[int]
) -> tuple[str, ...] | None:
    """
    将已选角色扮演列表写入目标角色状态并更新 unconscious_h 标志。
    selected 非空时先清空目标的催眠行为模式；写入后列表为空时若 unconscious_h 为 7 则归零并返回 None，
    否则将 unconscious_h 设为 7 并返回存在于配置中的名称元组。
    Keyword arguments:
    target_id -- int，目标角色编号
    selected -- list[int]，待结算的角色扮演编号列表
    Return arguments:
    tuple[str, ...] | None -- 生效的角色扮演名称元组，空列表结算时为 None
    """
    if selected:
        hypnosis_state.clear_hypnosis_behavior_mode(target_id)
    hypnosis.set_roleplay(target_id, selected)
    new_roleplay = hypnosis.roleplay(target_id)
    if not new_roleplay:
        if flags.get(target_id, "unconscious_h") == 7:
            flags.set(target_id, unconscious_h=0)
        return None
    flags.set(target_id, unconscious_h=7)
    return tuple(
        game_config.config_roleplay[cid].name
        for cid in new_roleplay
        if cid in game_config.config_roleplay
    )
