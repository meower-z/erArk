"""
群交模板编辑服务（group_sex_editor_service）
============================================
提供群交信息栏文本、编辑页数据构造、候选筛选与模板状态读写接口。
本模块不导入 Script.UI 与 Script.Settle。
"""

from collections.abc import Collection
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import handle_premise, map_handle
from Script.Modules.domains import activity, h_state, identity, modes
from Script.Modules.domains import scene_state
from Script.Modules.gameplay_resolution import group_sex_service

_: FunctionType = get_text._
""" 翻译函数。 """

SERVE = "侍奉"
""" 群交模板中侍奉栏使用的部位键常量。 """
BODY_PART_NAMES = {
    "mouth": _("嘴"),
    "L_hand": _("左手"),
    "R_hand": _("右手"),
    "penis": _("阴茎"),
    "anal": _("肛门"),
}
""" 群交对单部位键到界面显示名称的映射表。 """


@dataclass(frozen=True, slots=True)
class PartRow:
    """群交编辑页单行部位展示数据的不可变结构。"""

    key: str
    """ 部位键，取对单部位键或 SERVE。 """
    label: str
    """ 左侧补齐显示宽度的部位标签文本。 """
    target_text: str
    """ 交互对象按钮显示的文本。 """
    state_text: str
    """ 行为指令按钮显示的文本。 """


@dataclass(frozen=True, slots=True)
class Controls:
    """群交编辑页底部开关与选项文案的不可变结构。"""

    b_on: bool
    """ 副模板轮流开关是否启用。 """
    b_text: str
    """ 轮流用副模板按钮的状态文案。 """
    lock_text: str
    """ 锁定群交模板按钮的状态文案。 """
    npc_ai_text: str
    """ 调整干员行动按钮的当前模式文案。 """


@dataclass(frozen=True, slots=True)
class TargetChoice:
    """交互对象选择页单名候选角色数据的不可变结构。"""

    cid: int
    """ 候选角色编号。 """
    text: str
    """ 角色编号与姓名拼接后的展示文本。 """
    name: str
    """ 候选角色姓名，用作按钮键。 """
    watch_only: bool
    """ 是否因课堂体力不足仅能旁观而不可选中。 """
    selected: bool
    """ 该角色是否已位于当前部位的选中列表中。 """


def info_text(character_id: int) -> str:
    """
    按玩家群交模板 A 构造单行汇总文本，并以指定角色名为行首。
    Keyword arguments:
    character_id -- int，显示在行首的角色编号
    Return arguments:
    str -- 汇总文本与末尾换行，无已选行为时返回空字符串
    """
    template = h_state.view(0).group_sex_body_template_dict["A"]
    text = ""
    for body_part in template[0]:
        state_id = template[0][body_part][1]
        if state_id != -1:
            target_name = identity.of(template[0][body_part][0]).name
            state_name = game_config.config_behavior[state_id].name
            part_name = BODY_PART_NAMES[body_part]
            text += _("{0}-{1}-{2} ").format(part_name, state_name, target_name)
    serve_ids = template[1][0]
    state_id = template[1][1]
    if state_id != -1:
        state_name = game_config.config_behavior[state_id].name
        names = ""
        for target_id in serve_ids:
            names += identity.of(target_id).name
            if target_id != serve_ids[-1]:
                names += "、"
        if len(serve_ids) > 1:
            names += _("一起")
        text += _("阴茎正在被{0}{1} ").format(names, state_name)
    if text == "":
        return ""
    return identity.of(character_id).name + " " + text + "\n"


def _state_text(state_id: str | int) -> str:
    """返回行为状态编号对应的名称，为 -1 时返回未选择指令文案。"""
    if state_id == -1:
        return _("未选择指令")
    return game_config.config_behavior[str(state_id)].name


def _label(name: str) -> str:
    """在部位名前加两个空格并以全角空格右补至 8 个字符。"""
    return f"  {name.ljust(8, '　')}"


def part_rows() -> list[PartRow]:
    """
    按玩家模板 A 的部位顺序生成编辑页行列表，并在 penis 行后插入侍奉行。
    未选角色或指令时填入对应缺省文案，侍奉多位角色以空格拼接。
    """
    template = h_state.view(0).group_sex_body_template_dict["A"]
    rows = []
    for body_part in template[0]:
        name = BODY_PART_NAMES[body_part]
        if body_part == "penis":
            name = _("阴茎（插入）")
        target_id = template[0][body_part][0]
        if target_id == -1:
            target_text = _("未选择角色")
        else:
            target_text = identity.of(target_id).name
        state_text = _state_text(template[0][body_part][1])
        rows.append(PartRow(body_part, _label(name), target_text, state_text))
        if body_part == "penis":
            serve_ids = template[1][0]
            if -1 in serve_ids:
                serve_text = _("未选择角色")
            else:
                serve_text = ""
                for target_id in serve_ids:
                    serve_text += identity.of(target_id).name + " "
            rows.append(
                PartRow(
                    SERVE,
                    _label(_("阴茎（侍奉）")),
                    serve_text,
                    _state_text(template[1][1]),
                )
            )
    return rows


def controls() -> Controls:
    """读取玩家副模板开关、模板锁定与干员行动设置，返回编辑页控件文案。"""
    b_on = bool(handle_premise.handle_all_group_sex_temple_run_on(0))
    lock_text = _("已锁定")
    if not h_state.get(0, "group_sex_lock_flag"):
        lock_text = _("未锁定")
    npc_ai_text = _("无行动")
    if handle_premise.handle_npc_ai_type_1_in_group_sex(0):
        npc_ai_text = _("自慰")
    elif handle_premise.handle_npc_ai_type_2_in_group_sex(0):
        npc_ai_text = _("优先补空位，无空位则自慰")
    elif handle_premise.handle_npc_ai_type_3_in_group_sex(0):
        npc_ai_text = _("随机抢占替换当前位置，无位则自慰")
    b_text = _("已启用") if b_on else _("未启用")
    return Controls(b_on, b_text, lock_text, npc_ai_text)


def scene_occupants() -> Collection[int]:
    """返回玩家当前所在场景中的角色编号集合。"""
    return scene_state.occupants(
        map_handle.get_map_system_path_str_for_list(activity.position(0))
    )


def _selected(temple_id: str, body_part: str) -> list[int]:
    """返回指定模板与部位当前已选角色编号列表，对单部位以单元素列表返回。"""
    entry = h_state.view(0).group_sex_body_template_dict[temple_id]
    if body_part != SERVE:
        return [entry[0][body_part][0]]
    return entry[1][0]


def target_choices(temple_id: str, body_part: str) -> list[TargetChoice]:
    """
    筛选指定模板与部位可选的同场景角色，排除玩家与其他槽位已占角色。
    仅课堂模式限定在课名单并将体力不足学生标为仅旁观。
    函数内延迟导入 sex_class_handle，避免顶层循环导入。
    Keyword arguments:
    temple_id -- str，模板键（"A" 或 "B"）
    body_part -- str，部位键或 SERVE
    Return arguments:
    list[TargetChoice] -- 候选角色条目列表
    """
    from Script.System.Education_System import sex_class_handle

    scene_ids = scene_occupants()
    in_template = group_sex_service.count_group_sex_character_list()
    selected = _selected(temple_id, body_part)
    taken = [cid for cid in in_template if cid not in selected]
    candidates = [cid for cid in scene_ids if cid != 0 and cid not in taken]
    if modes.sex_class():
        members = set(sex_class_handle.get_class_member_list())
        candidates = [cid for cid in candidates if cid in members]
    choices = []
    for cid in candidates:
        data = identity.of(cid)
        watch_only = (
            modes.sex_class() and sex_class_handle.judge_hp_low_only_watch(cid)
        )
        choices.append(
            TargetChoice(
                cid,
                f"[{str(data.adv).rjust(4, '0')}]{data.name}",
                data.name,
                watch_only,
                cid in selected,
            )
        )
    return choices


def status_choices(
    temple_id: str, body_part: str
) -> list[tuple[str, str, str]]:
    """
    查询指定模板与部位当前可用的行为选项列表。
    若槽位已选对象，筛选期间临时以末位已选对象作为玩家目标供处女检查读取，退出后恢复原目标。
    Keyword arguments:
    temple_id -- str，模板键（"A" 或 "B"）
    body_part -- str，部位键或 SERVE
    Return arguments:
    list[tuple[str, str, str]] -- (行为编号, 编号与名称展示文本, 行为名称) 列表
    """
    with activity.target_as(0, activity.target(0)):
        selected = _selected(temple_id, body_part)
        if -1 not in selected:
            activity.set_target(0, selected[-1])
        status_ids = (
            group_sex_service.get_status_id_list_from_group_sex_body_part(
                body_part
            )
        )
    choices = []
    for status_id in status_ids:
        name = game_config.config_behavior[status_id].name
        text = f"[{status_id.rjust(4, '0')}]{name}"
        choices.append((status_id, text, name))
    return choices


def set_target_chara(
    temple_id: str, body_part: str, target_chara_id: int
) -> None:
    """
    写入指定模板与部位的交互对象，并在 penis 与侍奉之间互斥清空另一项。
    写入侍奉时切换该角色的选中状态，最多保留四名角色并移除 -1 占位值。
    Keyword arguments:
    temple_id -- str，模板键（"A" 或 "B"）
    body_part -- str，部位键或 SERVE
    target_chara_id -- int，要写入或切换的角色编号
    Return arguments:
    None -- 无返回值
    """
    with h_state.editing(0) as hs:
        template = hs.group_sex_body_template_dict[temple_id]
        if body_part != SERVE:
            template[0][body_part][0] = target_chara_id
            if body_part == "penis":
                template[1] = [[-1], -1]
        else:
            serve_ids = template[1][0]
            if target_chara_id in serve_ids:
                serve_ids.remove(target_chara_id)
                if len(serve_ids) == 0:
                    serve_ids.append(-1)
            else:
                serve_ids.append(target_chara_id)
                if len(serve_ids) > 4:
                    serve_ids.pop(0)
                if -1 in serve_ids:
                    serve_ids.remove(-1)
            template[0]["penis"] = [-1, -1]


def set_status(temple_id: str, body_part: str, status_id: str) -> None:
    """
    写入指定模板与部位的行为状态编号，并在 penis 与侍奉之间互斥清空另一项。
    Keyword arguments:
    temple_id -- str，模板键（"A" 或 "B"）
    body_part -- str，部位键或 SERVE
    status_id -- str，行为编号
    Return arguments:
    None -- 无返回值
    """
    with h_state.editing(0) as hs:
        template = hs.group_sex_body_template_dict[temple_id]
        if body_part != SERVE:
            template[0][body_part][1] = status_id
            if body_part == "penis":
                template[1] = [[-1], -1]
        else:
            template[1][1] = status_id
            template[0]["penis"] = [-1, -1]


def reset_template() -> None:
    """将玩家群交模板 A 的全部部位与侍奉槽位重置为未选状态，不修改模板 B。"""
    with h_state.editing(0) as hs:
        template = hs.group_sex_body_template_dict["A"]
        for key in template[0]:
            template[0][key] = [-1, -1]
        template[1] = [[-1], -1]


def change_lock_flag() -> None:
    """切换玩家群交模板的锁定标志。"""
    h_state.set(
        0, group_sex_lock_flag=not h_state.get(0, "group_sex_lock_flag")
    )


def change_npc_ai() -> None:
    """将玩家群交的干员行动模式编号在 0 至 3 之间循环递增。"""
    nxt = h_state.get(0, "npc_ai_type_in_group_sex") + 1
    h_state.set(0, npc_ai_type_in_group_sex=0 if nxt >= 4 else nxt)


def change_b_temple_flag() -> None:
    """切换玩家轮流用副模板的启用标志。"""
    h_state.set(
        0,
        all_group_sex_temple_run=not h_state.get(0, "all_group_sex_temple_run"),
    )


def change_temple() -> None:
    """互换玩家群交模板 A 与模板 B 的内容。"""
    with h_state.editing(0) as hs:
        tpl = hs.group_sex_body_template_dict
        tpl["A"], tpl["B"] = tpl["B"], tpl["A"]


def reset_unfinish_select() -> None:
    """
    清空玩家群交模板 A 中仅选了角色或仅选了指令的半成品槽位。
    副模板轮流开关启用时同时清理模板 B，未启用时不修改模板 B。
    """
    with h_state.editing(0) as hs:
        tpl = hs.group_sex_body_template_dict
        templates = [tpl["A"]]
        if handle_premise.handle_all_group_sex_temple_run_on(0):
            templates.append(tpl["B"])
        for template in templates:
            for body_part in template[0]:
                target_chara_id, state_id = template[0][body_part][:2]
                if state_id == -1 or target_chara_id == -1:
                    template[0][body_part] = [-1, -1]
            if template[1][1] == -1 or -1 in template[1][0]:
                template[1] = [[-1], -1]
