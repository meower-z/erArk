"""
个人课表服务（course_select_service）
=====================================
提供个人课表的单元格文本、选课选项、日程槽位标签以及一键选课、复制与清空操作。
本模块不导入 Script.UI 与 Script.Settle。
"""

from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import game_time
from Script.Modules.domains import growth, identity
from Script.Modules.gameplay_resolution.class_schedule_service import (
    get_period_time_text,
    get_teacher_absent_mark,
)
from Script.System.Education_System import auto_schedule, education_constant
from Script.System.Education_System import schedule_handle
from Script.System.Education_System import schedule_template_handle

_: FunctionType = get_text._
""" 本地化翻译函数。 """


@dataclass(frozen=True, slots=True)
class ClassroomRow:
    """选课页中单间教室在指定节次的展示文本、可选课表项与教师缺位标记。"""

    classroom: str
    """ 教室场景名称。 """
    text: str
    """ 该教室在选课页显示的课程与教师文本，本节无课时标明无课。 """
    choice: tuple[int, str] | None
    """ 选中该行时写入个人课表的 (课型编号, 教室名) 元组，本节无课时为 None。 """
    absent: bool
    """ 该节授课教师是否存在缺位标注，为 True 时界面以深灰样式绘制。 """


@dataclass(frozen=True, slots=True)
class TargetOption:
    """体育、兴趣或实习课内容选择页中的单个候选项数据。"""

    target: str | int
    """ 候选项的目标标识，按课型分别为地点名称、娱乐编号或岗位编号。 """
    text: str
    """ 候选项的按钮或置灰展示文本。 """
    enabled: bool
    """ 候选项是否可选，未开放或条件不符时为 False。 """


def cell_text(character_id: int, week_day: int, period: int) -> str:
    """
    构造个人课表单个格子的展示文本，个人课先判地点开放再判活动条件。
    Keyword arguments:
    character_id -- int，目标学生的角色编号
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    Return arguments:
    str -- 格子文本，未选课时为「--」，教室课读含临时课层的全局课表
    """
    course = schedule_handle.get_selected_course(character_id, week_day, period)
    if course is None:
        return "--"
    course_type, target = course[0], course[1]
    if course_type in education_constant.CLASSROOM_COURSE_TYPE_SET:
        cell = schedule_handle.get_class_cell(target, week_day, period)
        if cell is not None and cell[0] in game_config.config_ability:
            return f"{game_config.config_ability[cell[0]].name}/{target}"
        return _("{0}/已停课").format(target)
    short = education_constant.COURSE_TYPE_SHORT.get(course_type, "?")
    target_name = target
    if course_type == education_constant.COURSE_TYPE_INTEREST:
        target_name = game_config.config_entertainment[target].name
    elif course_type == education_constant.COURSE_TYPE_INTERN:
        target_name = game_config.config_work_type[target].name
    text = f"[{short}]{target_name}"
    course_data = {"course_type": course_type, "target": target}
    if not schedule_handle.get_course_place(course_data):
        return _("{0}/未开放").format(text)
    if not schedule_handle.judge_course_need_pass(character_id, course_data):
        return _("{0}/条件不符").format(text)
    return text


def auto_fill_text(character_id: int) -> str:
    """
    为指定学生的空课表格子执行一键选课，并生成结果提示文本。
    Keyword arguments:
    character_id -- int，目标学生的角色编号
    Return arguments:
    str -- 含成功选课节数、无教室开课节数或已选满说明的提示文本
    """
    filled_count, skip_count = auto_schedule.auto_fill_selected_course(
        character_id
    )
    name = identity.of(character_id).name
    if filled_count:
        text = _("\n已为{0}选上 {1} 节课").format(name, filled_count)
        if skip_count:
            text += _("；另有 {0} 节全岛都没有教室开课，留给日程模板").format(
                skip_count
            )
        return text + "\n"
    if skip_count:
        return _(
            "\n没能选上任何一节课：全岛课表上还没排课，先去「全局课表」排好再来\n"
        )
    return _("\n{0}的课表已经选满了\n").format(name)


def clear_student(character_id: int) -> None:
    """
    清空指定学生一周全部星期与节次的个人课表。
    Keyword arguments:
    character_id -- int，待清空课表的学生角色编号
    Return arguments:
    None -- 无返回值
    """
    for week_day in range(len(education_constant.WEEK_NAME)):
        for period in range(len(game_time.CLASS_PERIOD_START)):
            schedule_handle.clear_selected_course(
                character_id, week_day, period
            )


def copy_schedule(source_id: int, target_id: int) -> None:
    """
    清空目标学生的个人课表，并将来源学生已选的全部节次复制到目标学生。
    Keyword arguments:
    source_id -- int，来源学生的角色编号
    target_id -- int，目标学生的角色编号
    Return arguments:
    None -- 无返回值
    """
    clear_student(target_id)
    for week_day in range(len(education_constant.WEEK_NAME)):
        for period in range(len(game_time.CLASS_PERIOD_START)):
            course = schedule_handle.get_selected_course(
                source_id, week_day, period
            )
            if course is None:
                continue
            schedule_handle.set_selected_course(
                target_id, week_day, period, course[0], course[1]
            )


def copy_targets(
    character_id: int, student_list: list[int]
) -> list[tuple[str, int]]:
    """
    从学生名单中排除当前学生，构造可复制课表的按钮标签与编号列表。
    Keyword arguments:
    character_id -- int，当前学生的角色编号
    student_list -- list[int]，候选学生角色编号列表
    Return arguments:
    list[tuple[str, int]] -- 形如 ([姓名], 角色编号) 的目标学生列表
    """
    return [
        (_("[{0}]").format(identity.of(other_id).name), other_id)
        for other_id in student_list
        if other_id != character_id
    ]


def apply_choice(
    character_id: int,
    week_day: int,
    period: int,
    choice: tuple[int, str | int] | str,
) -> None:
    """
    将选课页返回的选项写入或清空指定学生的单个课表格子。
    Keyword arguments:
    character_id -- int，目标学生的角色编号
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    choice -- tuple[int, str | int] | str，(课型编号, 目标) 元组或清空标记字符串
    Return arguments:
    None -- 无返回值
    """
    if isinstance(choice, str):
        schedule_handle.clear_selected_course(character_id, week_day, period)
        return
    schedule_handle.set_selected_course(
        character_id, week_day, period, choice[0], choice[1]
    )


def slot_labels(character_id: int) -> list[str]:
    """
    构造学生日程页三个时段的按钮文本，存在单槽覆盖时附加单独指定标注。
    Keyword arguments:
    character_id -- int，目标学生的角色编号
    Return arguments:
    list[str] -- 按时段顺序排列的三个按钮展示文本列表
    """
    labels = []
    for slot in range(education_constant.SLOT_COUNT):
        now_name = schedule_template_handle.get_child_slot_activity_text(
            character_id, slot
        )
        growth_data = growth.of(character_id)
        override_mark = ""
        if growth_data is not None and slot in growth_data.schedule_override:
            override_mark = _("（单独指定）")
        labels.append(
            _(" [{0}：{1}{2}]").format(
                education_constant.SLOT_NAME[slot], now_name, override_mark
            )
        )
    return labels


def course_head_text(character_id: int, week_day: int, period: int) -> str:
    """
    构造选课页顶部的学生姓名、星期、节次与起止时间标题文本。
    Keyword arguments:
    character_id -- int，目标学生的角色编号
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    Return arguments:
    str -- 含姓名、星期、节号与起止时间的标题行文本
    """
    return _("  {0}｜{1} 第{2}节 {3}\n\n").format(
        identity.of(character_id).name,
        education_constant.WEEK_NAME[week_day],
        period + 1,
        get_period_time_text(period),
    )


def classroom_rows(week_day: int, period: int) -> list[ClassroomRow]:
    """
    按已开放教室顺序构造本节各教室的常规周课展示行，不计入一次性临时实操课。
    Keyword arguments:
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    Return arguments:
    list[ClassroomRow] -- 各教室的展示文本、可选课表项与教师缺位状态列表
    """
    rows = []
    for classroom in schedule_handle.get_classroom_list():
        cell = schedule_handle.get_class_cell(
            classroom, week_day, period, include_temp=False
        )
        if cell is None:
            text = _(" {0}（本节没有课）").format(classroom)
            rows.append(ClassroomRow(classroom, text, None, False))
            continue
        teacher_name = _("无教师（自习）")
        absent_mark = ""
        if identity.exists(cell[1]):
            absent_mark = get_teacher_absent_mark(cell[1])
            teacher_name = identity.of(cell[1]).name + absent_mark
        course_type = schedule_handle.get_course_type_by_classroom(classroom)
        text = _("[{0}] {1}/{2}（{3}）").format(
            classroom,
            game_config.config_ability[cell[0]].name,
            teacher_name,
            education_constant.COURSE_TYPE_NAME.get(course_type, _("未知")),
        )
        choice = (course_type, classroom)
        rows.append(ClassroomRow(classroom, text, choice, bool(absent_mark)))
    return rows


def _option(target: str | int, name: str, gray_text: str) -> TargetOption:
    """
    根据置灰原因文本构造可选或不可选的个人课候选项。
    Keyword arguments:
    target -- str | int，候选项的目标标识
    name -- str，候选项的显示名称
    gray_text -- str，不可选时的完整置灰文本，为空串时生成可选按钮文本
    Return arguments:
    TargetOption -- 含目标标识、展示文本与可选标记的候选项对象
    """
    if gray_text:
        return TargetOption(target, gray_text, False)
    return TargetOption(target, _("[{0}]").format(name), True)


def _closed_text(course_type: int, target: str | int, name: str) -> str:
    """
    检查个人课目标是否存在已开放的上课地点，不可达时返回未开放置灰文本。
    Keyword arguments:
    course_type -- int，个人式课型编号
    target -- str | int，候选项的目标标识
    name -- str，候选项的显示名称
    Return arguments:
    str -- 地点未开放时返回带标注的置灰文本，已开放时返回空串
    """
    if schedule_handle.get_course_place(
        {"course_type": course_type, "target": target}
    ):
        return ""
    return _(" {0}（未开放）").format(name)


def target_options(character_id: int, course_type: int) -> list[TargetOption]:
    """
    按课型生成体育、兴趣或实习课的候选项列表，先判地点开放再判兴趣活动条件。
    Keyword arguments:
    character_id -- int，目标学生的角色编号
    course_type -- int，个人式课型编号
    Return arguments:
    list[TargetOption] -- 候选项列表，未开放或条件不符的条目处于不可选状态
    """
    options = []
    if course_type == education_constant.COURSE_TYPE_PE:
        for place_name in education_constant.PE_PLACE_DATA:
            gray_text = _closed_text(course_type, place_name, place_name)
            options.append(_option(place_name, place_name, gray_text))
    elif course_type == education_constant.COURSE_TYPE_INTEREST:
        for cid in game_config.config_entertainment:
            if not game_config.config_entertainment[cid].class_ok:
                continue
            name = game_config.config_entertainment[cid].name
            gray_text = _closed_text(course_type, cid, name)
            if (
                not gray_text
                and not schedule_template_handle.judge_activity_need_pass(
                    character_id, cid
                )
            ):
                gray_text = _(" {0}（条件不符）").format(name)
            options.append(_option(cid, name, gray_text))
    else:
        for cid in game_config.config_work_type:
            work_data = game_config.config_work_type[cid]
            if (
                work_data.tag
                or cid in education_constant.EXCLUDE_INTERN_WORK_TYPE
                or not work_data.ability_id
            ):
                continue
            gray_text = _closed_text(course_type, cid, work_data.name)
            options.append(_option(cid, work_data.name, gray_text))
    return options
