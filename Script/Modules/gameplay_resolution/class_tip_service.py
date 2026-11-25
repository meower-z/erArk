"""
上课提示服务（class_tip_service）
=================================
本模块提供课程文本格式化与角色当前上课或翘课提示查询。
本模块公开函数 get_course_text 与 get_now_class_tip。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

from types import FunctionType

from Script.Config import game_config
from Script.Core import constant, get_text
from Script.Design import game_time, handle_premise, map_handle
from Script.Modules.domains import activity, flags, identity

_: FunctionType = get_text._
""" 翻译api """


def get_course_text(now_course: dict) -> str:
    """
    将单条课程信息格式化为展示文本。
    班级类课程在能力编号大于 0 时返回「课型·科目｜教室」，否则返回「课型｜教室」。
    其余课程返回「课型·目标」。
    兴趣课将目标解析为娱乐项目名称。
    实习课将目标解析为岗位名称。
    Keyword arguments:
    now_course -- dict，课程信息字典
    Return arguments:
    str -- 格式化后的课程文本
    """
    from Script.System.Education_System import education_constant

    type_name = education_constant.COURSE_TYPE_NAME.get(
        now_course["course_type"], _("课")
    )
    if (
        now_course["course_type"]
        in education_constant.CLASSROOM_COURSE_TYPE_SET
    ):
        if now_course["ability_id"] > 0:
            ability_name = game_config.config_ability[
                now_course["ability_id"]
            ].name
            return "{}·{}｜{}".format(
                type_name, ability_name, now_course["classroom"]
            )
        return "{}｜{}".format(type_name, now_course["classroom"])
    target = now_course["target"]
    if now_course["course_type"] == education_constant.COURSE_TYPE_INTEREST:
        target = game_config.config_entertainment[target].name
    elif now_course["course_type"] == education_constant.COURSE_TYPE_INTERN:
        target = game_config.config_work_type[target].name
    return f"{type_name}·{target}"


def get_now_class_tip(character_id: int) -> tuple[bool, str] | None:
    """
    查询角色当前的上课或翘课提示。
    判定顺序依次为翘课状态、授课行为、听课或自习行为，以及节次内身处非班级课程场地的情形。
    未命中上述情形时返回 None。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    tuple[bool, str] | None -- 命中时返回 (是否翘课, 提示文本)，未命中时返回 None
    """
    from Script.System.Education_System import (
        class_ai,
        education_constant,
        growth_handle,
        schedule_handle,
    )

    period = game_time.get_class_period(character_id)

    if (
        period != -1
        and not flags.get(character_id, "is_h")
        and class_ai.judge_skip_class_today(character_id)
        and class_ai.get_course_stage(character_id)
        == education_constant.COURSE_STAGE_SKIP
    ):
        now_course = schedule_handle.get_now_course(character_id)
        if now_course is not None:
            return True, _("翘课中：本该上 {0}（第{1}节）").format(
                get_course_text(now_course), period + 1
            )

    behavior_id = activity.behavior(character_id).behavior_id
    if behavior_id == constant.Behavior.TEACH:
        teaching = schedule_handle.get_now_teaching(character_id)
        if teaching is not None:
            ability_name = game_config.config_ability[
                teaching["ability_id"]
            ].name
            return False, _("授课中：{0}·{1}｜{2}｜第{3}节").format(
                education_constant.COURSE_TYPE_NAME.get(
                    teaching["course_type"], _("课")
                ),
                ability_name,
                teaching["classroom"],
                teaching["period"] + 1,
            )
        return False, _("授课中")

    if behavior_id in {
        constant.Behavior.ATTENT_CLASS,
        constant.Behavior.SELF_STUDY,
    }:
        listen_course = handle_premise.get_listen_manual_teach_course(
            character_id
        )
        if listen_course is not None:
            scene_path_str = map_handle.get_map_system_path_str_for_list(
                activity.position(character_id)
            )
            classroom = (
                constant.scene_data[scene_path_str].scene_name
                if scene_path_str in constant.scene_data
                else ""
            )
            listen_text = get_course_text(
                {
                    "course_type": listen_course[0],
                    "ability_id": listen_course[1],
                    "classroom": classroom,
                    "target": classroom,
                }
            )
            teacher_name = identity.of(0).name
            if period == -1:
                return False, _("{0}｜授课：{1}").format(
                    listen_text, teacher_name
                )
            return False, _("{0}｜授课：{1}｜第{2}节").format(
                listen_text, teacher_name, period + 1
            )
        now_course = schedule_handle.get_now_course(character_id)
        if now_course is None:
            if behavior_id == constant.Behavior.SELF_STUDY:
                return False, _("自习中（日程安排，此刻没课）")
            return False, _("上课中")
        text = get_course_text(now_course)
        if (
            now_course["course_type"]
            not in education_constant.CLASSROOM_COURSE_TYPE_SET
        ):
            return False, _("{0}｜第{1}节").format(text, period + 1)
        if (
            now_course["teacher_id"] == -1
            or behavior_id == constant.Behavior.SELF_STUDY
        ):
            return False, _("自习·{0}｜本节无教师，按自习收益｜第{1}节").format(
                text, period + 1
            )
        teacher_data: identity.Identity = identity.of(now_course["teacher_id"])
        return False, _("{0}｜授课：{1}｜第{2}节").format(
            text, teacher_data.name, period + 1
        )

    if period != -1:
        now_course = schedule_handle.get_now_course(character_id)
        if (
            now_course is not None
            and now_course["course_type"]
            not in education_constant.CLASSROOM_COURSE_TYPE_SET
        ):
            now_time = activity.behavior(character_id).start_time
            if (
                behavior_id == constant.Behavior.REST
                or flags.get(character_id, "is_h")
                or growth_handle.judge_absent_this_period(
                    character_id, now_time
                )
            ):
                return None
            to_place = schedule_handle.get_course_place(now_course)
            now_scene_str = map_handle.get_map_system_path_str_for_list(
                activity.position(character_id)
            )
            if (
                to_place
                and now_scene_str
                == map_handle.get_map_system_path_str_for_list(to_place)
            ):
                text = get_course_text(now_course)
                if (
                    now_course["course_type"]
                    == education_constant.COURSE_TYPE_INTERN
                ):
                    mentor_id = schedule_handle.get_intern_mentor(
                        character_id, now_course["target"]
                    )
                    if mentor_id == -1:
                        return False, _(
                            "{0}｜本节无人在岗，降为见习｜第{1}节"
                        ).format(text, period + 1)
                    mentor_data: identity.Identity = identity.of(mentor_id)
                    return False, _("{0}｜带教：{1}｜第{2}节").format(
                        text, mentor_data.name, period + 1
                    )
                return False, _("{0}｜第{1}节").format(text, period + 1)

    return None
