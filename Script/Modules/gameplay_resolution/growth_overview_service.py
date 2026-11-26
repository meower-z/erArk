"""
养成总览服务（growth_overview_service）
=======================================
提供养成总览页各分区的展示文本、单元格数据与成绩单翻页信息。
本模块不导入 Script.UI 与 Script.Settle。
"""

import datetime
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import attr_calculation, game_time
from Script.Modules.domains import abilities, growth, identity, relations
from Script.System.Education_System import baby_growth_handle, class_ai
from Script.System.Education_System import education_constant
from Script.System.Education_System import growth_event_handle, semester_handle
from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle

_: FunctionType = get_text._
""" 翻译函数 """
GRAY = "deep_gray"
""" 灰色次要文本使用的绘制样式名。 """
HIGHLIGHT = "gold_enrod"
""" 本学期升级科目的高亮绘制样式名。 """
Cell = tuple[str, str]
""" 单个网格单元的文本与绘制样式二元组，空样式表示使用默认样式。 """


@dataclass(frozen=True)
class ReportCardPage:
    """单份学期成绩单翻页后的展示数据快照。"""

    index: int
    """ 校验并回落后的当前成绩单索引。 """
    count: int
    """ 角色历史成绩单总份数。 """
    summary: str
    """ 含学期名、评定与出勤统计的摘要行文本。 """
    reason: str
    """ 带「※」前缀的成绩单补充原因行，无原因时为空字符串。 """
    progress: str
    """ 该学期的科目升级进步文本或无升级提示文本。 """
    progress_style: str
    """ 进步文本行使用的绘制样式名，默认样式时为空字符串。 """


def stage_text(character_id: int) -> str:
    """
    生成孩子的母亲、当前阶段及下一阶段倒计时或状态说明文本。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    str -- 含母亲名、阶段名与下一阶段进度或毕业停滞说明的文本
    """
    talent = abilities.talent(character_id)
    stage_name = _("已成年")
    for talent_id in sorted(education_constant.STAGE_TALENT_NAME.keys()):
        if talent.get(talent_id, 0):
            stage_name = education_constant.STAGE_TALENT_NAME[talent_id]
            break
    mother = identity.get(relations.mother_id(character_id))
    mother_name = mother.name if mother is not None else _("未知")
    text = _("\n  母亲：{0}｜当前阶段：{1}").format(mother_name, stage_name)
    stage_total_day = pregnancy_handle.get_child_growth_stage_total_day(
        character_id
    )
    if not stage_total_day:
        return text + _("（已毕业，没有下一阶段）\n")
    left_day = max(
        0, stage_total_day - pregnancy_handle.get_child_grow_day(character_id)
    )
    next_stage_name = pregnancy_handle.get_child_next_stage_name(character_id)
    if talent.get(education_constant.GROWTH_STOP_TALENT_ID, 0):
        return text + _(
            "｜成长停滞中，阶段不会推进（解除后距成长为{0}还需 {1}）\n"
        ).format(next_stage_name, game_time.get_duration_text(left_day))
    predict_time = max(
        game_time.get_predict_date(left_day, game_time.now()),
        game_time.now(),
    )
    return text + _("｜距成长为{0}还有 {1}，预计在 {2}年{3}\n").format(
        next_stage_name,
        game_time.get_duration_text(left_day),
        predict_time.year,
        pregnancy_constant.format_season_date(predict_time),
    )


def prenatal_text(character_id: int) -> str:
    """
    生成孩子的胎教底子说明文本，无出生习得珠时返回空字符串。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    str -- 胎教次数与习得珠说明行，无胎教习得珠时为空字符串
    """
    prenatal_juel = baby_growth_handle.get_child_prenatal_juel(character_id)
    if not prenatal_juel:
        return ""
    return _("  胎教底子：孕期听过{0}次胎教，出生时带来 {1} 个{2}\n").format(
        baby_growth_handle.get_child_prenatal_count(character_id),
        prenatal_juel,
        baby_growth_handle.get_learn_juel_name(),
    )


def subject_cells(character_id: int) -> list[Cell]:
    """
    生成「科目水平」分区的各科目名称、评级、本学期增幅与样式列表。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    list[Cell] -- 按 SUBJECT_ABILITY_LIST 顺序排列的科目单元格列表
    """
    level_change = semester_handle.get_semester_level_change(character_id)
    cells: list[Cell] = []
    for ability_id in education_constant.SUBJECT_ABILITY_LIST:
        level = int(abilities.ability(character_id).get(ability_id, 0))
        name = game_config.config_ability[ability_id].name
        grade_text = attr_calculation.judge_grade(level)
        if ability_id in level_change:
            old_level, new_level = level_change[ability_id]
            text = _(" {0}：{1}（本学期+{2}）").format(
                name, grade_text, new_level - old_level
            )
            cells.append((text, HIGHLIGHT))
        else:
            text = _(" {0}：{1}").format(name, grade_text)
            cells.append((text, GRAY if level == 0 else ""))
    return cells


def attendance_texts(character_id: int) -> tuple[str, str] | None:
    """
    生成「出勤」分区的累计与本学期出勤统计两行文本。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    tuple[str, str] | None -- 累计与本学期出勤文本二元组，无养成数据时为 None
    """
    growth_data = growth.of(character_id)
    if growth_data is None:
        return None
    total = growth_data.attend_class_count + growth_data.absent_count
    rate = growth_data.attend_class_count / total if total else 1.0
    total_text = _("  累计：听课 {0} 节，缺课 {1} 节（出勤率 {2}%）\n").format(
        growth_data.attend_class_count,
        growth_data.absent_count,
        int(rate * 100),
    )
    attend, absent = semester_handle.get_semester_attend(character_id)
    semester_text = _(
        "  本学期：听课 {0} 节，缺课 {1} 节（出勤率 {2}%）\n"
    ).format(
        attend,
        absent,
        semester_handle.get_semester_attend_rate(attend, absent),
    )
    return total_text, semester_text


def report_card_page(character_id: int, index: int) -> ReportCardPage | None:
    """
    读取指定索引的「学期成绩单」展示数据，越界时回落至最新一份。
    Keyword arguments:
    character_id -- int，目标角色编号
    index -- int，待查看的成绩单索引
    Return arguments:
    ReportCardPage | None -- 对应成绩单的展示快照，无历史记录时为 None
    """
    history_list = semester_handle.get_report_card_history(character_id)
    if not history_list:
        return None
    if not 0 <= index < len(history_list):
        index = len(history_list) - 1
    report_data = history_list[index]
    summary = _(
        "  {0}　评定：{1}　出勤 {2} 节／缺课 {3} 节（出勤率 {4}%）\n"
    ).format(
        semester_handle.get_semester_name(
            report_data.get("year", 0), report_data.get("month", 0)
        ),
        education_constant.REPORT_GRADE_NAME.get(
            report_data.get("grade", education_constant.REPORT_GRADE_NO_CLASS),
            _("无课可评"),
        ),
        report_data.get("attend", 0),
        report_data.get("absent", 0),
        report_data.get("rate", 100),
    )
    reason = ""
    if report_data.get("reason", ""):
        reason = _("  ※ {0}\n").format(report_data["reason"])
    level_text = semester_handle.get_level_change_text(
        report_data.get("level_change", {})
    )
    if level_text:
        progress = _("  那个学期的进步：{0}\n").format(level_text)
        progress_style = ""
    else:
        progress = _("  那个学期没有科目升级\n")
        progress_style = GRAY
    return ReportCardPage(
        index, len(history_list), summary, reason, progress, progress_style
    )


def report_card_index_text(page: ReportCardPage) -> str:
    """
    生成「学期成绩单」翻页栏中部的页码计数文本。
    Keyword arguments:
    page -- ReportCardPage，当前成绩单展示快照
    Return arguments:
    str -- 含当前序号与总份数的页码文本
    """
    return _("第 {0} / {1} 份（含最近一份）").format(page.index + 1, page.count)


def personality_cells(character_id: int) -> list[Cell] | None:
    """
    生成「性格倾向」分区的各对性格倾向文本与样式列表。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    list[Cell] | None -- 按倾向对键序排列的单元格列表，无养成数据时为 None
    """
    growth_data = growth.of(character_id)
    if growth_data is None:
        return None
    cells: list[Cell] = []
    for pair_id in sorted(education_constant.PERSONALITY_PAIR_NAME.keys()):
        point = growth_data.personality_point.get(pair_id, 0.0)
        front, back = education_constant.PERSONALITY_PAIR_NAME[pair_id]
        if point > 0:
            cells.append((_(" 偏{0}（{1:.0f}）").format(front, point), ""))
        elif point < 0:
            cells.append((_(" 偏{0}（{1:.0f}）").format(back, -point), ""))
        else:
            cells.append((_(" {0}/{1}：尚未形成").format(front, back), GRAY))
    return cells


def event_history(character_id: int) -> tuple[str, list[str]] | None:
    """
    生成「养成履历」分区的省略提示行与近期事件选择记录行列表。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    tuple[str, list[str]] | None -- 省略提示与记录行列表，无养成数据或履历时为 None
    """
    growth_data = growth.of(character_id)
    if growth_data is None or not growth_data.event_history:
        return None
    history_list = sorted(
        growth_data.event_history.items(),
        key=lambda one: one[1].get("time") or datetime.datetime(1, 1, 1),
    )
    omit_text = ""
    show_max = education_constant.HISTORY_SHOW_MAX
    if len(history_list) > show_max:
        omit_text = _("  （更早的 {0} 条已略去）\n").format(
            len(history_list) - show_max
        )
        history_list = history_list[-show_max:]
    rows = []
    for uid, record in history_list:
        event_data = game_config.config_official_event.get(uid)
        if event_data is None:
            continue
        choice_index = record.get("choice", 0)
        choice_text = event_data.get(
            f"option_{choice_index}", _("（未作选择）")
        )
        time_data = record.get("time")
        time_text = (
            time_data.strftime("%Y/%m/%d")
            if hasattr(time_data, "strftime")
            else ""
        )
        title = event_data.get("text", "").split("\n")[0]
        rows.append(
            _("  {0} {1} → {2}\n").format(
                time_text,
                title[: education_constant.HISTORY_TEXT_MAX],
                choice_text,
            )
        )
    return omit_text, rows


def pending_texts(character_id: int) -> list[str]:
    """
    生成「待处理」分区的待查看成绩单、待炫耀进步、翘课与待决断事件行列表。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    list[str] -- 带圆点前缀的待处理提示行列表，无养成数据时为空列表
    """
    growth_data = growth.of(character_id)
    if growth_data is None:
        return []
    text_list = []
    if growth_data.report_card_flag:
        report_data = semester_handle.get_last_report_card(character_id)
        if report_data.get("year") and report_data.get("month"):
            semester_text = semester_handle.get_semester_name(
                report_data["year"], report_data["month"]
            )
            text_list.append(
                _("{0}的成绩单待查看（用「检查成绩单」指令）").format(
                    semester_text
                )
            )
        else:
            text_list.append(_("新的成绩单待查看（用「检查成绩单」指令）"))
    if growth_data.show_off_ability:
        name_list = [
            game_config.config_ability[ability_id].name
            for ability_id in growth_data.show_off_ability
            if ability_id in game_config.config_ability
        ]
        text_list.append(
            _("有想炫耀的进步：{0}（下次见到你时会说）").format(
                "、".join(name_list)
            )
        )
    if class_ai.judge_skip_class_today(character_id, game_time.now()):
        text_list.append(_("今天正在翘课"))
    wait_count = growth_event_handle.get_growth_event_queue_count(character_id)
    if wait_count:
        text_list.append(
            _("有 {0} 件关于她的事等你在博士办公室「处理公务」时决断").format(
                wait_count
            )
        )
    return [f"  ○{text}\n" for text in text_list]
