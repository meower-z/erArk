"""NPC 自主行动入口；需求链和状态机负责具体选择。"""

from dataclasses import replace
from datetime import datetime

from Script.Core import cache_control, constant
from Script.Design import game_time, handle_npc_ai, handle_premise
from Script.Modules.action import Action


def _continue_recovery(actor: int, plan: Action) -> bool:
    """输入 NPC 编号及剩余恢复计划，返回当前状态是否允许继续休息或睡眠。"""
    character = cache_control.cache.character_data[actor]
    # 恢复计划通过剩余时长、行为类型和目标判断是否继续。
    if plan.duration <= 0 or character.behavior.behavior_id != plan.behavior_id or character.target_character_id != plan.target:
        return False
    recovered = handle_premise.handle_tired_le_0(actor) and handle_premise.handle_hp_max(actor) and handle_premise.handle_mp_max(actor)
    if plan.behavior_id == constant.Behavior.REST:
        return not recovered
    if plan.behavior_id == constant.Behavior.SLEEP:
        # 助理在睡眠片段跨过约定问候时刻后醒来。
        if handle_premise.handle_self_not_sleep_pills(actor) and handle_premise.handle_assistant_morning_salutation_on(actor) and handle_premise.handle_morning_salutation_flag_0(actor):
            hour, minute = cache_control.cache.character_data[0].action_info.plan_to_wake_time
            start = character.behavior.start_time
            wake = start.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if wake <= start:
                wake = game_time.get_sub_date(day=1, old_date=wake)
            if cache_control.cache.game_time >= wake:
                return False
        return not (recovered and not handle_premise.handle_game_time_is_sleep_time(actor) and handle_premise.handle_self_not_sleep_pills(actor) and handle_premise.handle_drunk_level_0(actor))
    return False


def choose_next(actor: int, now: datetime) -> Action | None:
    """输入 NPC 编号和当前时间，返回下一行动；检查已提交强制后续时返回 None。"""
    from Script.Modules.game_actions import get_runtime

    runtime = get_runtime()
    character = cache_control.cache.character_data[actor]
    plan = runtime.plans.get(actor)
    if plan is not None:
        # 睡眠与休息期间维护强制位置和助理问候标志。
        handle_npc_ai.judge_character_cant_move(actor)
        handle_npc_ai.judge_assistant_character(actor)
    # 每个片段边界重新判断是否继续，保留睡眠状态直到真正结束。
    if plan is not None and _continue_recovery(actor, plan):
        return replace(plan, duration=min(30, plan.duration), continued=True)
    runtime.plans.pop(actor, None)
    runtime.finish_current(actor, now)

    # 行为前置检查优先确定强制移动、等待及后续。
    handle_npc_ai.run_npc_pre_behavior_checks(actor, now)
    if runtime.scheduler.pending(actor) is not None:
        return None

    # H 或木头人状态下通过静默等待片段检查状态并结算时间。
    if character.behavior.behavior_id == constant.Behavior.WAIT and (character.sp_flag.is_h or character.hypnosis.blockhead):
        return Action(constant.Behavior.WAIT, 5, character.target_character_id, state=constant.CharacterStatus.STATUS_WAIT, continued=True)
    if character.behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
        handle_npc_ai.find_character_target(actor, now)
    if runtime.scheduler.pending(actor) is not None:
        return None

    # AI 无可用目标时等待五分钟，再次选择。
    if character.behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
        return Action(constant.Behavior.WAIT, 5, actor, state=constant.CharacterStatus.STATUS_WAIT)
    return Action.from_character(character)
