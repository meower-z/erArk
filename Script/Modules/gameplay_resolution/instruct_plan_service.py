"""
指令规划服务（instruct_plan_service）
=====================================
提供无界面依赖的指令判定、时长解析、同场景群交成员查询与判定、交互对象等待排入、
结算途中通用指令入队以及综合指令状态效果结算逻辑。
供行为结算、实时结算与交互指令模块调用。
"""

import datetime
from types import FunctionType

from Script.Config import game_config
from Script.Core import constant, game_type, get_text
from Script.Design import instuct_judege, map_handle
from Script.Kernel import core
from Script.Modules.domains import action_info, activity, roster, scene_state
from Script.Modules.gameplay_resolution import group_sex_service, plan_queue

_: FunctionType = get_text._
""" 翻译api """


def group_members(character_id: int) -> list[int]:
    """
    邀请群交的对象：角色所在场景里除玩家外的角色
    Keyword arguments:
    character_id -- 邀请的角色id
    Return arguments:
    list -- 角色id
    """
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    return [c for c in scene_state.occupants(scene_path_str) if c != 0]


def judged_group_sex(behavior_id: str, character_id: int) -> str:
    """
    邀请群交的判定：场景里的干员逐个判定实行值，催眠补正的代价逐个结算；有人拒绝时记下拒绝的人
    Keyword arguments:
    behavior_id -- 行为id
    character_id -- 邀请的角色id
    Return arguments:
    str -- 都同意时为 behavior_id，有人拒绝时为邀请群交失败
    """
    refused = [
        chara_id
        for chara_id in group_members(character_id)
        if not instuct_judege.calculation_instuct_judege(
            character_id, chara_id, _("群交"), not_draw_flag=True
        )[0]
    ]
    if not refused:
        return behavior_id
    action_info.set(character_id, "ask_group_sex_refuse_chara_id_list", refused)
    return constant.Behavior.ASK_GROUP_SEX_FAIL


def judged_behavior_id(
    behavior_id: str, character_id: int, target_character_id: int, judge: str
) -> str:
    """
    有判断条件时先判断：失败时换成对应的失败行为
    Keyword arguments:
    behavior_id -- 行为id
    character_id -- 角色id
    target_character_id -- 交互对象的角色id
    judge -- 判断条件，为空时不判断
    Return arguments:
    str -- 要执行的行为id
    """
    if judge == "":
        return behavior_id
    if judge == _("群交"):
        return judged_group_sex(behavior_id, character_id)
    judge_list = instuct_judege.calculation_instuct_judege(
        character_id, target_character_id, judge
    )
    if judge_list[0] != 0:
        return behavior_id
    judge_to_behavior_id = {
        _("初级骚扰"): constant.Behavior.LOW_OBSCENITY_ANUS,
        _("道具"): constant.Behavior.LOW_OBSCENITY_ANUS,
        _("口交"): constant.Behavior.LOW_OBSCENITY_ANUS,
        _("严重骚扰"): constant.Behavior.HIGH_OBSCENITY_ANUS,
        _("药物"): constant.Behavior.HIGH_OBSCENITY_ANUS,
        _("SM"): constant.Behavior.HIGH_OBSCENITY_ANUS,
        _("性交"): constant.Behavior.HIGH_OBSCENITY_ANUS,
        _("A性交"): constant.Behavior.HIGH_OBSCENITY_ANUS,
        _("U开发"): constant.Behavior.HIGH_OBSCENITY_ANUS,
        _("U性交"): constant.Behavior.HIGH_OBSCENITY_ANUS,
        _("亲吻"): constant.Behavior.KISS_FAIL,
        _("H模式"): constant.Behavior.DO_H_FAIL,
        _("告白"): constant.Behavior.CONFESSION_FAILED,
        _("戴上项圈"): constant.Behavior.GIVE_NECKLACE_FAILED,
        _("隐奸"): constant.Behavior.ASK_HIDDEN_SEX_FAIL,
        _("露出"): constant.Behavior.ASK_EXHIBITIONISM_SEX_FAIL,
    }
    return judge_to_behavior_id.get(judge, behavior_id)


def instruct_duration(behavior_id: str, duration: int) -> int:
    """
    行动的持续时间：为 0 时查表，表里不大于 0 时为 1
    Keyword arguments:
    behavior_id -- 行为id
    duration -- 指定的分钟数，0 为查表
    Return arguments:
    int -- 分钟数
    """
    if duration == 0:
        duration = game_config.config_behavior[behavior_id].duration
        if duration <= 0:
            duration = 1
    return duration


def plan_target_wait(target: int, minutes: int) -> None:
    """
    交互对象排上同样分钟数的等待，并被打断来接着做。
    不在场的对象（不是玩家、也不在在编名册内）不在内核里，不排：
    排下的等待会留到她上线以后才开始，例如从袋中放出来之后再等上同样的分钟数
    Keyword arguments:
    target -- 交互对象的角色id
    minutes -- 分钟数
    """
    if target != 0 and not roster.has(target):
        return
    plan_queue.plan_next(
        target,
        constant.Behavior.WAIT,
        minutes,
        state=constant.CharacterStatus.STATUS_WAIT,
        interrupt=True,
    )


def plan_instruct_common_settle(
    behavior_id: str,
    character_id: int = 0,
    target_character_id: int = 0,
    duration: int = 0,
    judge: str = "",
    force_taget_wait: bool = False,
) -> tuple[core.Interrupt, ...]:
    """
    结算途中用的指令通用结算：不当场开始，把行动排进角色的计划队列（干员会被打断来接着做）
    Keyword arguments:
    behavior_id -- 行为id
    character_id -- 角色id
    target_character_id -- 交互对象的角色id，0 时用角色当前的交互对象
    duration -- 分钟数，0 为查表
    judge -- 判断条件，为空时不判断
    force_taget_wait -- 是否让交互对象也排上等待
    Return arguments:
    tuple -- 空元组：排下的打断由计划队列在这一步交给内核
    """
    if target_character_id == 0:
        target_character_id = activity.target(character_id)
    judged = judged_behavior_id(
        behavior_id, character_id, target_character_id, judge
    )
    duration = instruct_duration(judged, duration)
    if target_character_id != character_id and force_taget_wait:
        plan_target_wait(target_character_id, duration)
    group_sex_service.group_sex_settle(
        character_id, target_character_id, judged
    )
    plan_queue.plan_next(
        character_id,
        judged,
        duration,
        target=target_character_id,
        interrupt=character_id != 0,
    )
    return ()


def handle_comprehensive_state_effect(
    effect_all_value_list: list,
    character_id: int,
    add_time: int,
    change_data: game_type.CharacterStatusChange,
    now_time: datetime.datetime,
) -> int | None:
    """
    综合指令行为结算：按主体标记 A1（自己）、A2（交互对象）或 A3|<id>（指定角色）解析目标，
    并把指定行为排进玩家的计划队列；无有效目标或未持有指定角色时返回 0，时长为 0 或排入完成后返回 None
    Keyword arguments:
    effect_all_value_list -- 结算的各项数值
    character_id -- 角色id
    add_time -- 结算时间
    change_data -- 状态变更信息记录对象
    now_time -- 结算的时间
    """
    if not add_time:
        return None
    if effect_all_value_list[0] == "A1":
        target_character_id = 0
    elif effect_all_value_list[0] == "A2":
        if character_id != 0 and character_id != activity.target(0):
            activity.set_target(0, character_id)
        if activity.target(0) == 0:
            return 0
        target_character_id = activity.target(0)
    else:
        target_character_id = int(effect_all_value_list[0][3:])
        if not roster.has(target_character_id):
            return 0

    behavior_id = effect_all_value_list[1]
    plan_instruct_common_settle(
        behavior_id, target_character_id=target_character_id
    )
    return None
