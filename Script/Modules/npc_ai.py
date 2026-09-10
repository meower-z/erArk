"""NPC 自主行动入口；需求链和状态机负责具体选择。"""

from datetime import datetime

from Script.Core import cache_control, constant
from Script.Design import game_time, handle_npc_ai, handle_premise
from Script.Modules.scheduler.action import Action, CONTINUED, STATE


def _can_continue_sleep(actor: int, now: datetime) -> bool:
    """输入 NPC 编号和时刻，按睡眠计划与自身状态返回是否继续睡下一段。"""
    character = cache_control.cache.character_data[actor]
    behavior = character.behavior
    if behavior.plan_end_time <= now:
        return False
    # 仅原定八小时的整夜睡眠响应早安问候，普通小睡不受影响。
    if (
        game_time.elapsed_minutes(behavior.plan_start_time, behavior.plan_end_time) == 480
        and handle_premise.handle_self_not_sleep_pills(actor)
        and handle_premise.handle_assistant_morning_salutation_on(actor)
        and handle_premise.handle_morning_salutation_flag_0(actor)
    ):
        hour, minute = cache_control.cache.character_data[0].action_info.plan_to_wake_time
        wake = behavior.plan_start_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if wake <= behavior.plan_start_time:
            wake = game_time.get_sub_date(day=1, old_date=wake)
        if now >= wake:
            return False
    recovered = handle_premise.handle_tired_le_0(actor) and handle_premise.handle_hp_max(actor) and handle_premise.handle_mp_max(actor)
    return not (recovered and not handle_premise.handle_game_time_is_sleep_time(actor) and handle_premise.handle_self_not_sleep_pills(actor) and handle_premise.handle_drunk_level_0(actor))


def _continue_current(character, minutes: float) -> Action:
    """输入角色对象和分钟数，返回延续当前行为的片段。"""
    action = Action.from_character(character, continued=True)
    action.duration = max(minutes, 1)
    return action


def choose_next(actor: int, now: datetime) -> Action:
    """输入 NPC 编号和时刻，读取世界及自身行为，返回当前行动意图。"""
    from Script.Design import character_behavior
    from Script.Design.handle_npc_ai_in_h import npc_ai_in_group_sex

    character = cache_control.cache.character_data[actor]
    behavior = character.behavior
    # 睡眠按计划分段，每段最多 30 分钟，段间重新检查是否醒来。
    if behavior.behavior_id == constant.Behavior.SLEEP and _can_continue_sleep(actor, now):
        return _continue_current(character, min(30, game_time.elapsed_minutes(now, behavior.plan_end_time)))
    # 等待主体的双人行为：主体仍在对自己执行该行为时再等五分钟。
    if behavior.behavior_id == constant.Behavior.WAIT and behavior.wait_on_behavior_id:
        owner = cache_control.cache.character_data.get(character.target_character_id)
        if owner is not None and owner.behavior.behavior_id == behavior.wait_on_behavior_id and owner.target_character_id == actor:
            return _continue_current(character, 5)
    finished_id = behavior.behavior_id
    if behavior.behavior_id != constant.Behavior.SHARE_BLANKLY:
        remaining = game_time.elapsed_minutes(now, game_time.get_sub_date(minute=behavior.duration, old_date=behavior.start_time))
        if remaining > 0:
            # 他人此刻写入的移动要靠结算才真正走动；其余写入或已开始的行为只走完剩余时间，与旧主循环一致。
            if behavior.behavior_id == constant.Behavior.MOVE and behavior.start_time >= now:
                return Action.from_character(character)
            return _continue_current(character, remaining)
        # 已到期的行为由自己收尾，再从闲置状态选择。
        character_behavior.judge_character_status_time_over(actor, now, end_now=2)
    action = npc_ai_in_group_sex(actor)
    if action is not None:
        return action
    # 受限状态下等待到期后继续等待，定期重新检查。
    if finished_id == constant.Behavior.WAIT and (character.sp_flag.is_h or character.hypnosis.blockhead):
        return Action(constant.Behavior.WAIT, 5, character.target_character_id, params={STATE: constant.CharacterStatus.STATUS_WAIT, CONTINUED: True})
    character.behavior.start_time = now
    return handle_npc_ai.choose_character_target(actor, now)
