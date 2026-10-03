"""结算：结算已写到角色身上、开始时刻为此刻的行为，返回它占用的分钟数"""

import datetime

from Script.Core import cache_control, constant, game_type
from Script.Design import game_time
from Script.Design.action_scheduler.action import Action, minutes_between

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """


def settle_action(character_id: int, action: Action) -> float:
    """
    结算角色此刻开始的行动：整段效果在开始时一次结算；是否按睡眠结算看行动本身，不看行动前置结算改写后的行为
    Keyword arguments:
    character_id -- 角色id
    action -- 已写到角色身上的行动；延续片段只结算经过时间，一次性效果由首段结算
    Return arguments:
    float -- 行为占用的分钟数
    """
    from Script.Design import character_behavior
    from Script.Settle import realtime_settle
    from Script.System.Education_System import class_ai

    now = cache.game_time
    continued = action.continued
    character = cache.character_data[character_id]
    if character_id:
        # 学生岗赶去上课：整段行动在开始时一次结算，故在结算前截到应离开的时刻
        leave_time = class_ai.get_student_leave_time(character_id)
        if leave_time is not None:
            character.behavior.duration = max(1, int(minutes_between(now, leave_time)))
    duration = character.behavior.duration
    if action.behavior.behavior_id == constant.Behavior.SLEEP:
        settle_sleep(character_id, duration, continued, now)
        return duration
    if not continued:
        character_behavior.judge_character_status(character_id)
    realtime_settle.character_aotu_change_value(character_id, game_time.get_sub_date(minute=duration, old_date=now), now)
    return duration


def settle_sleep(character_id: int, minutes: float, continued: bool, now: datetime.datetime):
    """
    结算一段睡眠：首段结算入睡效果，后续各段只补睡眠恢复；每段都按时长结算随时间变化的数值
    Keyword arguments:
    character_id -- 角色id
    minutes -- 本段分钟数
    continued -- 是否为后续段
    now -- 本段开始时刻
    Return arguments:
    None
    """
    from Script.Design import character_behavior
    from Script.Settle import default, realtime_settle, sleep_settle

    end = game_time.get_sub_date(minute=minutes, old_date=now)
    if continued:
        changes = game_type.CharacterStatusChange()
        default.handle_add_small_sanity_point(character_id, minutes, changes, end)
        default.handle_add_small_semen_point(character_id, minutes, changes, end)
    else:
        character_behavior.judge_character_status(character_id)
    realtime_settle.character_aotu_change_value(character_id, end, now)
    if character_id == 0 and not continued:
        sleep_settle.update_sleep()
