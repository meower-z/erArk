"""NPC 一方：行动前检查、到时选择行动、执行行动，以及陪等别人的双人行为"""

import datetime
from typing import Optional

from Script.Core import cache_control, constant, game_type
from Script.Design import game_time
from Script.Design.action_scheduler.action import WAIT_RECHECK_MINUTES, Action, behavior_end, continue_current, minutes_between, wait_action, wait_slice
from Script.Design.action_scheduler.settle import settle_action
from Script.Design.action_scheduler.timeline import Entry, Timeline

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
SLEEP_CHUNK_MINUTES = 30
""" NPC 睡眠每段至多的分钟数，段间重新判断是否醒来 """


def prepare(character_id: int, timeline: Timeline):
    """
    NPC 到时选择行动前的检查：离队或死亡的角色退出时间线，归队时由同步重新加入；其余运行行动前检查
    Keyword arguments:
    character_id -- 角色id
    timeline -- 时间线
    Return arguments:
    None
    """
    from Script.Design import handle_npc_ai

    if character_id not in cache.npc_id_got or cache.character_data[character_id].dead:
        timeline.drop(character_id)
        return
    # 行动前检查以玩家本次行动的开始时刻为基准，与旧主循环一致
    handle_npc_ai.run_npc_pre_behavior_checks(character_id, cache.character_data[0].behavior.start_time)


def decide(character_id: int, timeline: Timeline) -> Optional[Action]:
    """
    轮到 NPC 自己选择时决定行动：先续睡、续等和走完未完的行为，到期的行为先收尾，再交给 NPC AI
    Keyword arguments:
    character_id -- 角色id
    timeline -- 时间线
    Return arguments:
    Action | None -- 行动；AI 的状态机为该角色写入了立即待办时返回 None，本次让位
    """
    from Script.Design import character_behavior, handle_npc_ai

    now = cache.game_time
    character = cache.character_data[character_id]
    behavior = character.behavior
    # 睡眠按计划分段
    if behavior.behavior_id == constant.Behavior.SLEEP and can_continue_sleep(character_id, now):
        return continue_current(character, min(SLEEP_CHUNK_MINUTES, minutes_between(now, behavior.plan_end_time)))
    # 等待对方的双人行为：对方仍在对自己做该行为时，再等一段
    if behavior.behavior_id == constant.Behavior.WAIT and behavior.wait_on_behavior_id:
        owner = cache.character_data.get(character.target_character_id)
        if owner is not None and owner.behavior.behavior_id == behavior.wait_on_behavior_id and owner.target_character_id == character_id:
            return continue_current(character, wait_slice(minutes_between(now, behavior_end(owner.behavior))))
    finished_id = behavior.behavior_id
    if behavior.behavior_id != constant.Behavior.SHARE_BLANKLY:
        remaining = minutes_between(now, behavior_end(behavior))
        if remaining > 0:
            # 别人此刻写入的移动要结算才真正走动
            if behavior.behavior_id == constant.Behavior.MOVE and behavior.start_time >= now:
                return Action.of(character)
            # H 中或木头人的等待由行动前检查写成"等到玩家本次行动结束"，分段复查
            if behavior.behavior_id == constant.Behavior.WAIT and (character.sp_flag.is_h or character.hypnosis.blockhead):
                return continue_current(character, wait_slice(remaining))
            # 其余写入或已开始的行为只走完剩余时间
            return continue_current(character, remaining)
        character_behavior.judge_character_status_time_over(character_id, now, end_now=2)
    # 受限状态下等待到期后继续等待，定期复查
    if finished_id == constant.Behavior.WAIT and (character.sp_flag.is_h or character.hypnosis.blockhead):
        return wait_action(character.target_character_id, WAIT_RECHECK_MINUTES, continued=True)
    character.behavior.start_time = now
    handle_npc_ai.find_character_target(character_id, now)
    # 状态机（如撞见 H 的面板）可能已为本角色写入立即待办
    if timeline.has_immediate(character_id):
        return None
    # 只更新需求的状态机保持闲置，按原节奏等待后再选择
    if character.behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
        return wait_action(character_id, WAIT_RECHECK_MINUTES)
    return Action.of(character)


def can_continue_sleep(character_id: int, now: datetime.datetime) -> bool:
    """
    判断睡眠中的 NPC 是否接着睡下一段
    Keyword arguments:
    character_id -- 角色id
    now -- 当前时刻
    Return arguments:
    bool -- 是否继续睡
    """
    from Script.Design import handle_premise

    behavior = cache.character_data[character_id].behavior
    if behavior.plan_end_time <= now:
        return False
    # 仅原定八小时的整夜睡眠响应早安问候，到玩家醒来时刻即醒
    if (
        minutes_between(behavior.plan_start_time, behavior.plan_end_time) == 480
        and handle_premise.handle_self_not_sleep_pills(character_id)
        and handle_premise.handle_assistant_morning_salutation_on(character_id)
        and handle_premise.handle_morning_salutation_flag_0(character_id)
    ):
        hour, minute = cache.character_data[0].action_info.plan_to_wake_time
        wake = behavior.plan_start_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if wake <= behavior.plan_start_time:
            wake = game_time.get_sub_date(day=1, old_date=wake)
        if now >= wake:
            return False
    # 疲劳清零、体力气力全满、不在睡觉时间、未服安眠药且未醉酒时醒来
    recovered = handle_premise.handle_tired_le_0(character_id) and handle_premise.handle_hp_max(character_id) and handle_premise.handle_mp_max(character_id)
    return not (
        recovered
        and not handle_premise.handle_game_time_is_sleep_time(character_id)
        and handle_premise.handle_self_not_sleep_pills(character_id)
        and handle_premise.handle_drunk_level_0(character_id)
    )


def act(character_id: int, action: Action, timeline: Timeline) -> Optional[float]:
    """
    把行动写成 NPC 的行为并结算
    Keyword arguments:
    character_id -- 角色id
    action -- 行动
    timeline -- 时间线
    Return arguments:
    float | None -- 占用的分钟数；行动前置结算为该角色写入了立即待办时返回 None，本次让位
    """
    from Script.Design import handle_talent

    character = cache.character_data[character_id]
    now = cache.game_time
    action.apply(character, now)
    behavior_id = character.behavior.behavior_id
    if timeline.has_immediate(character_id):
        return None
    duration = settle_action(character_id, action)
    handle_talent.gain_talent(character_id, now_gain_type=0)
    # NPC 自己的结算把行为改写成此刻开始的移动（如撞见 H 后离开）时，此刻由 AI 按新移动结算
    if (
        character_id not in timeline
        and behavior_id != constant.Behavior.MOVE
        and character.behavior.behavior_id == constant.Behavior.MOVE
        and character.behavior.start_time >= now
    ):
        timeline.put(character_id, Entry(now))
    return duration


def companion_wait(owner_id: int, behavior_id: str) -> Action:
    """
    构造 NPC 陪等主体双人行为的等待：主体只是在等待时陪等其时长，否则分段复查；和旧代码的直接写入一样不结算一次性效果
    Keyword arguments:
    owner_id -- 主体id
    behavior_id -- 主体的行为id
    Return arguments:
    Action -- 等待行动
    """
    source = cache.character_data[owner_id].behavior
    if behavior_id == constant.Behavior.WAIT:
        return wait_action(owner_id, source.duration, continued=True)
    remaining = minutes_between(cache.game_time, behavior_end(source))
    return wait_action(owner_id, wait_slice(remaining), continued=True, wait_on_behavior_id=behavior_id)
