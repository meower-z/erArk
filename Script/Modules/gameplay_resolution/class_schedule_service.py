"""
课表服务（class_schedule_service）
==================================
提供全局课表的单元格文本、教师缺位标注、自动排课结果及选课与选师数据。
本模块不导入 Script.UI 与 Script.Settle。
"""

from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text, text_handle
from Script.Design import attr_calculation, game_time
from Script.Modules.domains import abilities, chara_life, flags, identity
from Script.Modules.domains import roster
from Script.System.Education_System import auto_schedule, education_constant
from Script.System.Education_System import schedule_handle, sex_class_handle

_: FunctionType = get_text._
""" 本地化翻译函数。 """
HEAD_WIDTH = 14
""" 周表左侧节次列固定显示宽度（14 列）。 """


@dataclass(frozen=True, slots=True)
class WeekCell:
    """周表中单个课表格子的展示文本、缺位标记与悬停提示。"""

    text: str
    """ 格子上显示的课程与教师文本，未排课时为「--」。 """
    absent: bool
    """ 该格排定教师是否处于长期缺位状态，为 True 时以深灰绘制。 """
    tooltip: str
    """ 教师缺位时的完整原因与后果悬停提示，无缺位时为空串。 """


@dataclass(frozen=True, slots=True)
class TeacherRow:
    """选教师页中单名候选教师的展示数据与冲突说明。"""

    teacher_id: int
    """ 候选教师的角色编号。 """
    name: str
    """ 候选教师的显示姓名。 """
    label: str
    """ 含姓名、对应科目等级与本周已排节数的展示标签，冲突时带「※」。 """
    conflict: str
    """ 该教师本节在其他教室的冲突描述，无冲突时为空串。 """


def get_period_time_text(period: int) -> str:
    """
    按节次索引计算该节课的起止时间文本。
    Keyword arguments:
    period -- int，节次索引（0 至 8）
    Return arguments:
    str -- 形如「09:00~09:45」的起止时间文本
    """
    hour, minute = game_time.CLASS_PERIOD_START[period]
    end_minute = minute + game_time.CLASS_PERIOD_MINUTE
    end_hour = hour + end_minute // 60
    end_minute = end_minute % 60
    return f"{hour:02d}:{minute:02d}~{end_hour:02d}:{end_minute:02d}"


def get_teacher_absent_mark(teacher_id: int, short: bool = False) -> str:
    """
    按离岗、监禁、不在岛上的顺序返回教师长期缺位标注，供周表与选课页共用。
    Keyword arguments:
    teacher_id -- int，教师角色编号，小于等于 0 或不存在时返回空串
    short -- bool，为 True 时返回短标注以适配窄格，默认为 False
    Return arguments:
    str -- 缺位标注文本（离岗/监禁/离岛或全称），正常在岗时为空串
    """
    if teacher_id <= 0 or not identity.exists(teacher_id):
        return ""
    if chara_life.work_type(teacher_id) != education_constant.TEACHER_WORK_TYPE:
        return _("（离岗）") if short else _("（已离岗）")
    if flags.get(teacher_id, "imprisonment"):
        return _("（监禁）") if short else _("（被监禁）")
    if not roster.has(teacher_id):
        return _("（离岛）") if short else _("（不在岛上）")
    return ""


def fit_text_width(text: str, width: int) -> str:
    """
    按终端显示宽度截断文本，使其总宽度不超过上限。
    Keyword arguments:
    text -- str，待截断的原始文本
    width -- int，允许的最大显示宽度，小于 0 时返回空串
    Return arguments:
    str -- 截断后的文本，原文本未超宽时原样返回
    """
    if text_handle.get_text_index(text) <= width:
        return text
    now_text = ""
    for char in text:
        if text_handle.get_text_index(now_text + char) > width:
            break
        now_text += char
    return now_text


def cell_width(width: int) -> int:
    """
    按面板总宽度计算周表中每一天列的单元格宽度，下限为 8 列。
    Keyword arguments:
    width -- int，面板可用总显示宽度
    Return arguments:
    int -- 单列课表格子的显示宽度
    """
    return max(8, int((width - HEAD_WIDTH) / len(education_constant.WEEK_NAME)))


def period_head_text(period: int) -> str:
    """
    构造周表左侧节次列的节号与开课时间文本。
    Keyword arguments:
    period -- int，节次索引（0 至 8）
    Return arguments:
    str -- 形如「  1 09:00 」的节次列文本
    """
    return f"  {period + 1} {get_period_time_text(period)[:5]} "


def classroom_info_text(classroom: str) -> str:
    """
    构造当前教室名称及其承载课型的顶部说明文本。
    Keyword arguments:
    classroom -- str，目标教室名称
    Return arguments:
    str -- 含教室名与承载课型的说明行，未识别课型时显示「未知」
    """
    course_type = schedule_handle.get_course_type_by_classroom(classroom)
    return _("  {0}｜承载课型：{1}\n").format(
        classroom,
        education_constant.COURSE_TYPE_NAME.get(course_type, _("未知")),
    )


def week_cell(
    classroom: str, week_day: int, period: int, width: int
) -> WeekCell:
    """
    构造指定教室与时段周表格子的显示文本、缺位标记与悬停提示。
    Keyword arguments:
    classroom -- str，目标教室名称
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    width -- int，该格子的显示宽度，教师缺位时用于截断姓名以保留标注
    Return arguments:
    WeekCell -- 含格子文本、是否缺位与悬停提示的展示数据
    """
    cell = schedule_handle.get_class_cell(classroom, week_day, period)
    if cell is None:
        return WeekCell("--", False, "")
    ability_name = game_config.config_ability[cell[0]].name
    temp_class = schedule_handle.get_today_temp_class(week_day, period)
    temp_prefix = (
        _("[临]")
        if temp_class is not None
        and temp_class.get("classroom", "") == classroom
        else ""
    )
    if not identity.exists(cell[1]):
        text = "{}{}/{}".format(temp_prefix, ability_name, _("待定"))
        return WeekCell(text, False, "")
    teacher_name = identity.of(cell[1]).name
    absent_mark = get_teacher_absent_mark(cell[1], short=True)
    tooltip = ""
    if absent_mark:
        tooltip = _(
            "{0}{1}：她来不了，这一节学生会降级为自习；点格子可改排教师"
        ).format(teacher_name, get_teacher_absent_mark(cell[1]))
        name_width = width - text_handle.get_text_index(
            temp_prefix + ability_name + "/" + absent_mark
        )
        teacher_name = fit_text_width(teacher_name, name_width)
    text = f"{temp_prefix}{ability_name}/{teacher_name}{absent_mark}"
    return WeekCell(text, bool(absent_mark), tooltip)


def auto_fill() -> str:
    """
    为全部已开放教室的周一至周五空格自动排课并按排入与留空节数生成提示文本。
    Keyword arguments:
    无
    Return arguments:
    str -- 展示给玩家的自动排课结果说明文本
    """
    filled_count, skip_count = auto_schedule.auto_fill_class_schedule()
    if filled_count:
        text = _("\n已自动排课 {0} 节（周一~周五）").format(filled_count)
        if skip_count:
            text += _("；另有 {0} 节因为当时没有空闲教师而留空").format(
                skip_count
            )
        return text + "\n"
    if skip_count:
        return _(
            "\n没能排上任何一节课：{0} 个空格子在当时都找不到空闲教师\n"
        ).format(skip_count)
    return _("\n课表已经排满了，没有空格子可排\n")


def clear_room(classroom: str) -> None:
    """
    清空指定教室一周全部星期与节次的每周课表格子。
    Keyword arguments:
    classroom -- str，待清空的教室名称
    Return arguments:
    None -- 无返回值
    """
    for week_day in range(len(education_constant.WEEK_NAME)):
        for period in range(len(game_time.CLASS_PERIOD_START)):
            schedule_handle.clear_class_cell(classroom, week_day, period)


def subject_header_text(classroom: str, week_day: int, period: int) -> str:
    """
    构造选科目页顶部的教室、星期、节次与时间段标题文本。
    Keyword arguments:
    classroom -- str，目标教室名称
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    Return arguments:
    str -- 选科目页顶部位置与时间说明文本
    """
    return _("  {0}｜{1} 第{2}节 {3}\n").format(
        classroom,
        education_constant.WEEK_NAME[week_day],
        period + 1,
        get_period_time_text(period),
    )


def overlay_text(classroom: str, week_day: int, period: int) -> str:
    """
    构造当日临时实操课顶替当前格时的双行提示，未顶替时返回空串。
    Keyword arguments:
    classroom -- str，目标教室名称
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    Return arguments:
    str -- 说明临时课主修科目与底层每周课表状态的提示文本，无顶替时为空串
    """
    temp_class = schedule_handle.get_today_temp_class(week_day, period)
    if temp_class is None or temp_class.get("classroom", "") != classroom:
        return ""
    week_cell_data = schedule_handle.get_class_cell(
        classroom, week_day, period, include_temp=False
    )
    if week_cell_data is None:
        week_text = _("未排课")
    elif identity.exists(week_cell_data[1]):
        week_text = (
            f"{game_config.config_ability[week_cell_data[0]].name}/"
            f"{identity.of(week_cell_data[1]).name}"
            f"{get_teacher_absent_mark(week_cell_data[1])}"
        )
    else:
        week_text = "{}/{}".format(
            game_config.config_ability[week_cell_data[0]].name, _("待定")
        )
    return _(
        "  今天这一节由临时实操课（主修{0}）顶替；每周课表这一格：{1}\n  下面选科目、"
        "清空改的都是每周课表这一格；临时课请从「排一节性技实操课」进去修改或删除\n"
    ).format(
        sex_class_handle.get_ability_name(temp_class.get("ability_id", -1)),
        week_text,
    )


def subject_labels() -> list[tuple[str, int]]:
    """
    按课程科目表顺序构造带序号的科目按钮标签与能力编号列表。
    Keyword arguments:
    无
    Return arguments:
    list[tuple[str, int]] -- 形如 ([序号]科目名, 能力编号) 的列表
    """
    return [
        (
            _("[{0}]{1}").format(
                index, game_config.config_ability[ability_id].name
            ),
            ability_id,
        )
        for index, ability_id in enumerate(
            education_constant.SUBJECT_ABILITY_LIST
        )
    ]


def has_sex_class_entry(classroom: str) -> bool:
    """
    判断指定教室是否开放性技实操课入口（实践课与公开课教室为 True）。
    Keyword arguments:
    classroom -- str，目标教室名称
    Return arguments:
    bool -- 教室课型为实践课或公开课返回 True，否则返回 False
    """
    return schedule_handle.get_course_type_by_classroom(classroom) in (
        education_constant.COURSE_TYPE_PRACTICE,
        education_constant.COURSE_TYPE_PUBLIC,
    )


def ability_label(ability_id: int) -> str:
    """
    按能力编号查询科目名称，编号不存在时回落为「该科目」。
    Keyword arguments:
    ability_id -- int，科目对应的能力编号
    Return arguments:
    str -- 科目显示名称或默认占位文本「该科目」
    """
    if ability_id in game_config.config_ability:
        return game_config.config_ability[ability_id].name
    return _("该科目")


def teacher_rows(
    ability_id: int,
    week_day: int,
    period: int,
    classroom: str,
    sort_desc: bool,
) -> list[TeacherRow]:
    """
    按指定科目等级排序构造选教师页候选行，含评级、本周排课节数与冲突标注。
    Keyword arguments:
    ability_id -- int，目标科目能力编号
    week_day -- int，星期索引（0 至 6）
    period -- int，节次索引（0 至 8）
    classroom -- str，目标教室名称
    sort_desc -- bool，是否按科目等级降序排列，为 True 时同级按编号升序
    Return arguments:
    list[TeacherRow] -- 排序后的候选教师展示行列表
    """
    teacher_list = sorted(
        schedule_handle.get_teacher_candidate_list(),
        key=lambda cid: (
            int(abilities.ability(cid).get(ability_id, 0)),
            -cid,
        ),
        reverse=sort_desc,
    )
    rows = []
    for teacher_id in teacher_list:
        name = identity.of(teacher_id).name
        level = int(abilities.ability(teacher_id).get(ability_id, 0))
        week_load = sum(
            len(one)
            for one in schedule_handle.get_teacher_week_schedule(
                teacher_id
            ).values()
        )
        level_text = (
            f"{attr_calculation.judge_grade(level)}{level}/{week_load}节"
        )
        conflict = schedule_handle.judge_teacher_conflict(
            teacher_id, week_day, period, classroom
        )
        if conflict:
            label = _(" {0} {1}※").format(name, level_text)
        else:
            label = _("[{0} {1}]").format(name, level_text)
        rows.append(TeacherRow(teacher_id, name, label, conflict))
    return rows


def conflict_summary(rows: list[TeacherRow]) -> str:
    """
    将候选教师列表中存在时段冲突的条目汇总为底部说明行。
    Keyword arguments:
    rows -- list[TeacherRow]，候选教师展示行列表
    Return arguments:
    str -- 汇总冲突教师与去向的说明文本，无人冲突时返回空串
    """
    conflict_text_list = [
        f"{row.name}（{row.conflict}）" for row in rows if row.conflict
    ]
    if not conflict_text_list:
        return ""
    return _("  ※本节已有课：{0}\n").format("、".join(conflict_text_list))
