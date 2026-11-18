"""
gameplay_resolution 的时间流逝钩子
==================================
输入钩子：时钟只走到最早的"缓存里该结束"的时刻。干员在缓存里的行为可能早于它在内核里的行动结束
（别人的结算改短了它、睡觉被截到玩家起床的时刻），学生也可能到了该动身去上课的时刻；内核不知道这些，
所以在这一刻停下。
输出钩子：在新时钟上给缓存里已该结束的干员发 Interrupt，内核的结束跟上缓存；
时钟跨过 0 点而缓存还没过新的一天时，跑新一天的结算。
连续结算（随时间变化的数值）不在这里跑：内核在每个干员的行动结束处停表，间隔常常只有几分钟，
按分钟取整的数值逐段算会变成 0，掷骰会按段数翻倍；它按玩家的这段行动在角色的结算里跑一次。
源石技艺中断（ArtsBreak）是事件：理智耗尽、还有技艺开着时，给玩家排上解除催眠与解除时停。
"""

import datetime

from Script.Core import cache_control, constant, game_type
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

MINUTES_PER_DAY = 24 * 60
""" 内核时钟一天的分钟数（时钟是游戏日历上的分钟数，0 点落在整天上） """

calls = 0
""" 钩子被调用的次数 """
lowered = 0
""" 输入钩子压低流逝终点的次数 """
interrupted = 0
""" 输出钩子发出的 Interrupt 个数 """
broke_arts = 0
""" ArtsBreak 触发的次数 """


def due_minute(character_id: int) -> int | None:
    """
    干员在缓存里最早该结束当前行为的时刻：行为的结束、学生该动身去上课的时刻，或早安问候的助理该醒的时刻
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int | None -- 内核时钟上的分钟数；角色不在或已死亡时为 None
    """
    character_data = cache.character_data.get(character_id)
    if character_data is None or character_data.dead:
        return None
    behavior = character_data.behavior
    due = actions.minutes(behavior.start_time)
    if behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
        return due
    start = due
    due += int(behavior.duration)
    from Script.Design import handle_npc_ai
    from Script.System.Education_System import class_ai

    for when in (
        class_ai.get_student_leave_time(character_id),
        handle_npc_ai.get_salutation_wake_time(character_id),
    ):
        if when is not None and actions.minutes(when) > start:
            due = min(due, actions.minutes(when))
    return due


def _npc_ids(game: core.GameState) -> list[int]:
    """
    内核里的干员
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    list -- 干员的角色id
    """
    return [int(who) for who in game.characters if who != actions.PLAYER]


@core.input_hook(core.time_elapse)
def before_elapse(
    start: int, end: int
) -> tuple[int, int] | core.Intercept[tuple[int, core.Effects]]:
    """
    流逝的终点压到 (start, end) 之内最早的干员该结束时刻
    Keyword arguments:
    start -- 流逝前的时钟
    end -- 流逝到的时钟（内核里最早的行动结束）
    Return arguments:
    tuple -- 交给内层的 (start, 终点)
    """
    global calls, lowered
    calls += 1
    new_end = end
    for character_id in _npc_ids(core.state()):
        due = due_minute(character_id)
        if due is not None and start < due < new_end:
            new_end = due
    if new_end != end:
        lowered += 1
    return (start, new_end)


@core.output_hook(core.time_elapse)
def after_elapse(
    result: tuple[int, core.Effects],
) -> tuple[int, core.Effects]:
    """
    新时钟上：缓存里已该结束、内核里还没结束的干员发 Interrupt；跨过 0 点时跑新一天的结算
    Keyword arguments:
    result -- 新时钟与内层的效果
    Return arguments:
    tuple -- 新时钟，内层的效果加上 Interrupt
    """
    global calls, interrupted
    calls += 1
    clock, effects = result
    game = core.state()
    stops: list[core.Effect] = []
    for character_id in _npc_ids(game):
        act = game.characters[str(character_id)].action
        if act.start + act.duration <= clock:
            continue
        due = due_minute(character_id)
        if due is not None and due <= clock:
            stops.append(core.Interrupt(str(character_id)))
    interrupted += len(stops)
    new_day(clock)
    if not stops:
        return result
    return (clock, (*effects, *stops))


def new_day(clock: int) -> None:
    """
    内核时钟与缓存的游戏时间都进了缓存还没刷新过的一天时，跑新一天的结算（它读缓存的游戏时间）
    Keyword arguments:
    clock -- 内核时钟
    """
    settled_day = actions.minutes(cache.pre_game_time) // MINUTES_PER_DAY
    cache_day = actions.minutes(cache.game_time) // MINUTES_PER_DAY
    if min(clock // MINUTES_PER_DAY, cache_day) <= settled_day:
        return
    from Script.Settle import past_day_settle

    past_day_settle.update_new_day()


def _arts_break_due(game: core.GameState, who: str) -> bool:
    """
    ArtsBreak 的条件：玩家理智耗尽，还有源石技艺开着、解除还没排上
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 该中断技艺时为真
    """
    if who != actions.PLAYER:
        return False
    from Script.Settle import realtime_settle

    return realtime_settle.arts_break_due()


@core.event("gameplay_resolution.time_hooks.ArtsBreak", _arts_break_due)
def arts_break(who: str) -> core.Effects:
    """
    源石技艺中断：关透视，给玩家排上解除催眠与解除时停，在玩家接下来的选择里开始
    Keyword arguments:
    who -- 角色键（玩家）
    Return arguments:
    Effects -- 排行动时要交回内核的打断
    """
    global broke_arts
    broke_arts += 1
    from Script.Settle import realtime_settle

    return realtime_settle.break_arts()


def character_aotu_change_value(
    character_id: int,
    now_time: datetime.datetime,
    pl_start_time: datetime.datetime,
) -> None:
    """
    随时间变化的数值，按玩家这段行动结算一次（realtime_settle.character_aotu_change_value）
    Keyword arguments:
    character_id -- 角色id
    now_time -- 结算到的时间
    pl_start_time -- 玩家这段行动的开始
    """
    from Script.Settle import realtime_settle

    realtime_settle.character_aotu_change_value(
        character_id, now_time, pl_start_time
    )


def change_character_persistent_state(character_id: int) -> None:
    """
    持续状态是否结束（realtime_settle.change_character_persistent_state）
    Keyword arguments:
    character_id -- 角色id
    """
    from Script.Settle import realtime_settle

    realtime_settle.change_character_persistent_state(character_id)


def update_sleep() -> None:
    """玩家开始睡觉时的刷新（sleep_settle.update_sleep）"""
    from Script.Settle import sleep_settle

    sleep_settle.update_sleep()


def judge_student_leave_truncate(character_id: int) -> bool:
    """
    学生赶去上课时把当前行为截到该动身的时刻（handle_npc_ai.judge_student_leave_truncate）；
    输入钩子已让时钟停在这一刻，输出钩子让内核的行动在这一刻结束
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 是否截短了当前行为
    """
    from Script.Design import handle_npc_ai

    return handle_npc_ai.judge_student_leave_truncate(character_id)


def judge_interrupt_character_behavior(character_id: int) -> int:
    """
    休息、睡觉、工作或娱乐是否就此结束（handle_npc_ai.judge_interrupt_character_behavior）；
    缓存里改短的结束由输入、输出钩子带进内核
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 1 为结束了当前行为
    """
    from Script.Design import handle_npc_ai

    return handle_npc_ai.judge_interrupt_character_behavior(character_id)
