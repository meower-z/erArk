"""NPC 自主行动入口；需求链和状态机负责具体选择。"""

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime

from Script.Core import cache_control, constant
from Script.Design import game_time, handle_npc_ai, handle_premise
from Script.Modules.action import Action, ActionProgress


@dataclass
class DecisionState:
    """NPC 自己维护的决策记录：已读取的执行记录及剩余睡眠计划。"""

    progress: ActionProgress | None = None
    plan: Action | None = None


def _sleep_plan(actor: int) -> Action | None:
    """输入角色编号，读取执行进度并更新自身计划，返回剩余睡眠行动或 None。"""
    character = cache_control.cache.character_data[actor]
    progress = getattr(character, "action_progress", None)
    state = getattr(character, "npc_ai_state", None)
    if state is None or state.progress is not progress:
        plan = deepcopy(progress.action) if progress is not None and progress.action.behavior_id == constant.Behavior.SLEEP else None
        state = character.npc_ai_state = DecisionState(progress, plan)
    if state.plan is not None:
        # 依据累计执行量计算，重复查询同一记录也得到相同的剩余时长。
        state.plan.duration = max(progress.action.duration - progress.elapsed, 0)
    return state.plan


def _can_continue(actor: int, plan: Action) -> bool:
    """输入 NPC 编号及剩余恢复计划，返回当前状态是否允许继续睡眠。"""
    character = cache_control.cache.character_data[actor]
    # 睡眠计划通过剩余时长、行为类型和目标判断是否继续。
    if plan.duration <= 0 or character.behavior.behavior_id != plan.behavior_id or character.target_character_id != plan.target:
        return False
    recovered = handle_premise.handle_tired_le_0(actor) and handle_premise.handle_hp_max(actor) and handle_premise.handle_mp_max(actor)
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


def choose_next(actor: int, now: datetime) -> Action:
    """输入 NPC 编号和时刻，读取世界及自身决策记录，返回当前行动意图。"""
    character = cache_control.cache.character_data[actor]
    plan = _sleep_plan(actor)
    if plan is not None:
        if _can_continue(actor, plan):
            return replace(plan, duration=min(30, plan.duration), continued=True)
        # 执行侧先完成醒来收尾；下一次选择读取收尾后的状态。
        return Action("finish_current", 0, actor)
    from Script.Modules.group_intent import prepare_group_options, choose_group_action

    options = prepare_group_options(actor)
    if options is not None:
        return choose_group_action(actor, options)
    # 受限状态通过等待行动定期重新检查。
    if character.behavior.behavior_id == constant.Behavior.WAIT and (character.sp_flag.is_h or character.hypnosis.blockhead):
        return Action(constant.Behavior.WAIT, 5, character.target_character_id, state=constant.CharacterStatus.STATUS_WAIT, continued=True)
    if character.behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
        return handle_npc_ai.choose_character_target(actor, now)
    return Action.from_character(character)
