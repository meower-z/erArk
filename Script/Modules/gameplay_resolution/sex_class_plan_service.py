"""
实操课排课服务（sex_class_plan_service）
========================================
提供临时性技实操课的草稿载入、排课信息文本、到场学生分类与必修名单计算。
本模块不导入 Script.UI 与 Script.Settle。
"""

import datetime
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import class_schedule_service
from Script.Modules.gameplay_resolution import class_tip_service
from Script.System.Education_System import education_constant, growth_handle
from Script.System.Education_System import schedule_handle, sex_class_handle
from Script.System.Pregnancy_System import pregnancy_constant

_: FunctionType = get_text._
""" 本地化翻译函数。 """


@dataclass(frozen=True, slots=True)
class TempClassDraft:
    """临时实操课编辑页的初始草稿状态。"""

    date_ordinal: int
    """ 该临时课对应日期的公历序数。 """
    exists: bool
    """ 该日期与节次是否已有临时实操课记录。 """
    other_classroom: str
    """ 已有临时课位于其他教室时的原教室名称，否则为空串。 """
    ability_id: int
    """ 当前选中的主修性技能力编号。 """
    must_attend: list[int]
    """ 当前点名必修的学生角色编号列表。 """


@dataclass(frozen=True, slots=True)
class MustRow:
    """指定必修学生页中单名候选学生的按钮与顶替说明数据。"""

    character_id: int
    """ 候选学生的角色编号。 """
    label: str
    """ 含选中标记、姓名与顶替星号的按钮文本。 """
    replace_text: str
    """ 点名后被顶替原课程的说明文本，无顶替时为空串。 """


def load_draft(classroom: str, week_day: int, period: int) -> TempClassDraft:
    """
    载入指定教室与时段对应的临时实操课草稿，未排课时默认选用首门性技科目。
    Keyword arguments:
    classroom -- str，当前打开编辑页的教室名称
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    Return arguments:
    TempClassDraft -- 含目标日期、已有状态、异室提示、主修科目与必修名单的草稿
    """
    date_ordinal = sex_class_handle.get_date_ordinal_by_week_day(
        week_day, period
    )
    now_class = sex_class_handle.get_temp_class(date_ordinal, period)
    other_classroom = ""
    if now_class is not None and now_class.get("classroom", "") != classroom:
        other_classroom = now_class.get("classroom", "")
    first_ability = education_constant.SEX_CLASS_ABILITY_LIST[0]
    ability_id = (
        now_class.get("ability_id", first_ability)
        if now_class
        else first_ability
    )
    must_attend = list(now_class.get("must_attend", [])) if now_class else []
    return TempClassDraft(
        date_ordinal,
        now_class is not None,
        other_classroom,
        ability_id,
        must_attend,
    )


def info_text(
    classroom: str, week_day: int, period: int, date_ordinal: int
) -> str:
    """
    构造临时实操课编辑页顶部的教室、季节日期与节次信息文本。
    Keyword arguments:
    classroom -- str，目标教室名称
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    date_ordinal -- int，目标日期的公历序数
    Return arguments:
    str -- 含教室、季节月日、星期与节次起止时间的说明文本
    """
    date_value = datetime.date.fromordinal(date_ordinal)
    date_text = pregnancy_constant.format_season_date(
        datetime.datetime(date_value.year, date_value.month, date_value.day)
    )
    return _("  教室：{0}\n  日期：{1}（{2}）\n  节次：第{3}节 {4}\n\n").format(
        classroom,
        date_text,
        education_constant.WEEK_NAME[week_day],
        period + 1,
        class_schedule_service.get_period_time_text(period),
    )


def subject_buttons(ability_id: int) -> list[tuple[str, int, bool]]:
    """
    构造临时实操课可选主修性技科目的按钮文本、能力编号与选中状态列表。
    Keyword arguments:
    ability_id -- int，当前选中的主修能力编号
    Return arguments:
    list[tuple[str, int, bool]] -- 各可选科目的 (按钮文本, 能力编号, 是否选中) 列表
    """
    buttons = []
    for now_ability_id in education_constant.SEX_CLASS_ABILITY_LIST:
        ability_name = game_config.config_ability[now_ability_id].name
        selected = now_ability_id == ability_id
        if selected:
            button_text = _("[{0}]").format(ability_name)
        else:
            button_text = _(" {0} ").format(ability_name)
        buttons.append((button_text, now_ability_id, selected))
    return buttons


def _names(character_ids: list[int]) -> list[str]:
    """
    按原顺序提取角色编号列表中有效角色的姓名。
    Keyword arguments:
    character_ids -- list[int]，待查询的角色编号列表
    Return arguments:
    list[str] -- 对应有效角色的姓名列表
    """
    return [
        identity.of(cid).name for cid in character_ids if identity.exists(cid)
    ]


def attendance_lines(
    classroom: str, week_day: int, period: int, must_attend: list[int]
) -> list[tuple[str, str]]:
    """
    按选修到场、状态受阻、未修前置课与必修名单分段生成出勤预览文本与样式。
    Keyword arguments:
    classroom -- str，目标教室名称
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    must_attend -- list[int]，当前指定的必修学生角色编号列表
    Return arguments:
    list[tuple[str, str]] -- 逐行 (展示文本, 样式名) 列表，常规行样式为空串
    """
    all_selected_list = [
        cid
        for cid in sex_class_handle.get_selected_student_list(
            classroom, week_day, period
        )
        if cid not in must_attend
    ]
    course_ok_list = [
        cid
        for cid in all_selected_list
        if sex_class_handle.judge_has_sex_skill_course(cid)
    ]
    selected_list = [
        cid
        for cid in course_ok_list
        if sex_class_handle.judge_can_join_sex_class(cid, check_course=False)
    ]
    if selected_list:
        count_text = _("  本节选修本教室的学生：{0} 人（{1}）\n").format(
            len(selected_list), "、".join(_names(selected_list))
        )
    elif all_selected_list:
        count_text = _(
            "  本节选修本教室的学生：0 人 —— 选修的人都进不了课堂（见下），建议指定必修学生\n"
        )
    elif must_attend:
        count_text = _(
            "  本节选修本教室的学生：0 人（点名必修的学生照常会来，见下）\n"
        )
    else:
        count_text = _(
            "  本节选修本教室的学生：0 人 —— 没有学生会来，建议指定必修学生\n"
        )
    lines = [(count_text, "")]
    blocked_name_list = _names(
        [cid for cid in course_ok_list if cid not in selected_list]
    )
    blocked_name_list += _names(
        [
            cid
            for cid in must_attend
            if identity.exists(cid)
            and not sex_class_handle.judge_can_join_sex_class(
                cid, check_course=False
            )
        ]
    )
    if blocked_name_list:
        lines.append(
            (
                _(
                    "  另有 {0} 人会到场，但此刻进不了课堂（实行值不足或状态异常）：{1}\n"
                ).format(len(blocked_name_list), "、".join(blocked_name_list)),
                "deep_gray",
            )
        )
    no_course_name_list = _names(
        [cid for cid in all_selected_list if cid not in course_ok_list]
    )
    if no_course_name_list:
        lines.append(
            (
                _(
                    "  另有 {0} 人会到场但没修过性技科目的课，不能参加（点名必修可豁免）：{1}\n"
                ).format(
                    len(no_course_name_list), "、".join(no_course_name_list)
                ),
                "deep_gray",
            )
        )
    must_name_list = _names(must_attend)
    lines.append(
        (
            _("  必修（无论原本排了什么都来，且不会翘课）：{0}\n\n").format(
                "、".join(must_name_list) if must_name_list else _("无")
            ),
            "",
        )
    )
    return lines


def _replace_text(character_id: int, week_day: int, period: int) -> str:
    """
    生成学生被点名必修时将顶替的原有课程说明，无实际课程可顶替时返回空串。
    Keyword arguments:
    character_id -- int，目标学生角色编号
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    Return arguments:
    str -- 形如「姓名→原课程」的顶替说明，无顶替时为空串
    """
    name = identity.of(character_id).name
    old_course = schedule_handle.get_selected_course(
        character_id, week_day, period
    )
    if old_course is None:
        return ""
    if old_course[0] in education_constant.CLASSROOM_COURSE_TYPE_SET:
        old_cell = schedule_handle.get_class_cell(
            old_course[1], week_day, period, include_temp=False
        )
        if old_cell is not None and old_cell[0] in game_config.config_ability:
            return _("{0}→{1}的{2}").format(
                name,
                old_course[1],
                game_config.config_ability[old_cell[0]].name,
            )
        if old_cell is not None:
            return _("{0}→{1}").format(name, old_course[1])
        return ""
    old_course_data = {"course_type": old_course[0], "target": old_course[1]}
    if schedule_handle.judge_personal_course_real(
        character_id, old_course_data
    ):
        return _("{0}→{1}").format(
            name, class_tip_service.get_course_text(old_course_data)
        )
    return ""


def must_rows(
    must_attend: list[int], week_day: int, period: int
) -> list[MustRow]:
    """
    筛选忽略前置修习后可参加实操课的候选学生，构造按钮标签与顶替说明。
    Keyword arguments:
    must_attend -- list[int]，当前已选中的必修学生角色编号列表
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    Return arguments:
    list[MustRow] -- 候选学生的必修选项展示行列表
    """
    rows = []
    for character_id in growth_handle.get_course_candidate_list():
        if not sex_class_handle.judge_can_join_sex_class(
            character_id, check_course=False
        ):
            continue
        mark = "√" if character_id in must_attend else "  "
        replace_text = _replace_text(character_id, week_day, period)
        label = _("[{0}{1}{2}]").format(
            mark,
            identity.of(character_id).name,
            "*" if replace_text else "",
        )
        rows.append(MustRow(character_id, label, replace_text))
    return rows


def replace_summary(rows: list[MustRow]) -> str:
    """
    汇总候选学生列表中会被点名顶替的原课程说明行。
    Keyword arguments:
    rows -- list[MustRow]，候选学生展示行列表
    Return arguments:
    str -- 底部顶替课程汇总文本，无顶替项时返回空串
    """
    replace_text_list = [row.replace_text for row in rows if row.replace_text]
    if not replace_text_list:
        return ""
    return _("  *会顶替原本的课：{0}\n").format("、".join(replace_text_list))


def toggled(must_attend: list[int], character_id: int) -> list[int]:
    """
    返回切换指定学生在必修名单中选中状态后的新列表，不修改原列表。
    Keyword arguments:
    must_attend -- list[int]，原必修学生角色编号列表
    character_id -- int，待切换状态的学生角色编号
    Return arguments:
    list[int] -- 增删该角色编号后的新列表
    """
    result = list(must_attend)
    if character_id in result:
        result.remove(character_id)
    else:
        result.append(character_id)
    return result
