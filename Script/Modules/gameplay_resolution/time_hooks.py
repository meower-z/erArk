"""
gameplay_resolution 的时钟：5 分钟一次的 Tick、0 点的 NewDay，以及 TimeElapse 的输入钩子
==========================================================================================
游戏只有一个时钟，就是内核的 clock（游戏日历上的分钟数，game_time.now() 读它）。
随时间变化的数值不在 TimeElapse 里结算（那里 state().clock 还是旧的），而在两种事件里：
- Tick：时钟比 ticked 晚 5 分钟、或跨进了 ticked 之后的一天时，把每个角色从 ticked 结算到此刻，
  到点该提前结束的干员发 Interrupt，ticked 记成此刻。数值按 5 分钟调过（realtime_settle 的
  int(t / 6)），逐段按更短的间隔算会取整成 0。
- NewDay：时钟进了 settled_day 之后的一天时跑新一天的结算，settled_day 记成今天。
TimeElapse 的输入钩子让时钟最多走到下一次 Tick 与下一个 0 点，所以新一天的结算在 0 点、任何人选行动之前。
一个行动结束时（ActionOver）由 tick_one 把这个角色结算到此刻，Tick 只从 ticked 算起，同一段不会算两遍。
本模块不在顶层导入 gameplay_resolution 的模块：actions 在登记 ActionOver 之前导入本模块，
Tick、NewDay 因此排在事件表的最前面。
源石技艺中断（ArtsBreak）是事件：理智耗尽、还有技艺开着时，给玩家排上解除催眠与解除时停。
"""

import datetime
from dataclasses import replace
from types import MappingProxyType
from typing import cast

from Script.Core import cache_control, game_type
from Script.Design import game_time
from Script.Kernel import core

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

PLAYER = "0"
""" 玩家的角色键 """
TICK_MINUTES = 5
""" 两次 Tick 之间的分钟数 """
TICKED = "ticked"
""" GameState 的全局键：上一次 Tick 结算到的时钟（同 actions.TICKED） """
SETTLED_DAY = "settled_day"
""" GameState 的全局键：已跑过新一天结算的游戏日（同 actions.SETTLED_DAY） """

broke_arts = 0
""" ArtsBreak 触发的次数 """


@core.output_hook(core.reset)
def mark_clock(game: core.GameState) -> core.GameState:
    """
    kernel.Reset 的输出钩子：换进来的 GameState 没有 ticked / settled_day 时（没有这两项的旧内核状态），
    从它的时钟记起
    Keyword arguments:
    game -- 新的 GameState
    Return arguments:
    GameState -- 带上两项的 GameState
    """
    if TICKED in game.data and SETTLED_DAY in game.data:
        return game
    data = {
        TICKED: game.clock,
        SETTLED_DAY: game_time.day(game.clock),
        **game.data,
    }
    return replace(game, data=MappingProxyType(data))


def _ticked(game: core.GameState) -> int:
    """
    上一次 Tick 结算到的时钟
    Keyword arguments:
    game -- GameState
    Return arguments:
    int -- 内核时钟上的分钟数
    """
    return cast(int, game.data[TICKED])


def _settled_day(game: core.GameState) -> int:
    """
    已跑过新一天结算的游戏日
    Keyword arguments:
    game -- GameState
    Return arguments:
    int -- 游戏日序号（game_time.day）
    """
    return cast(int, game.data[SETTLED_DAY])


def _first(game: core.GameState, who: str) -> bool:
    """
    who 是否是名单上的第一个角色（玩家）；全局的事件只在他身上成立一次
    Keyword arguments:
    game -- GameState
    who -- 角色键
    Return arguments:
    bool -- 是第一个角色时为真
    """
    return who == next(iter(game.characters))


def _settle(character_id: int, since: int, until: int | None = None) -> bool:
    """
    把一个角色从 since 结算到 until（默认此刻）：随时间变化的数值与持续状态
    Keyword arguments:
    character_id -- 角色id
    since -- 从这一分钟算起
    until -- 结算到这一分钟；None 时到此刻
    Return arguments:
    bool -- 结算了时为真；角色不在缓存里或已死亡时为假
    """
    character_data = cache.character_data.get(character_id)
    if character_data is None or character_data.dead:
        return False
    from Script.Settle import realtime_settle

    now = game_time.now() if until is None else game_time.at(until)
    realtime_settle.character_aotu_change_value(
        character_id, now, game_time.at(since)
    )
    realtime_settle.change_character_persistent_state(character_id)
    return True


def tick_one(who: int) -> None:
    """
    把一个角色结算到此刻（他的行动结束时调用；下一次 Tick 只从 ticked 算起）。
    时停中玩家此刻开始的行动在内核里是 0 分钟，从行动开始按缓存里的名义分钟数结算
    Keyword arguments:
    who -- 角色id
    """
    game = core.state()
    character_data = cache.character_data.get(who)
    if (
        who == 0
        and cache.time_stop_mode
        and character_data is not None
        and game_time.minutes(character_data.behavior.start_time) == game.clock
    ):
        _settle(who, game.clock, game.clock + character_data.behavior.duration)
        return
    _settle(who, _ticked(game))


def _tick_due(game: core.GameState, who: str) -> bool:
    """
    Tick 的条件：时钟比 ticked 晚了 5 分钟，或已进了 ticked 之后的一天
    Keyword arguments:
    game -- GameState
    who -- 角色键
    Return arguments:
    bool -- 该结算时为真（只在第一个角色身上）
    """
    ticked = _ticked(game)
    return _first(game, who) and (
        game.clock - ticked >= TICK_MINUTES
        or game_time.day(game.clock) > game_time.day(ticked)
    )


@core.event("gameplay_resolution.time_hooks.Tick", _tick_due)
def tick(who: str) -> core.Effects:
    """
    把每个角色从 ticked 结算到此刻；到点该提前结束的干员（休息够了、该去洗澡、学生该去上课）被打断
    Keyword arguments:
    who -- 第一个角色的键
    Return arguments:
    Effects -- 打断，与 ticked 记成此刻
    """
    game = core.state()
    since = _ticked(game)
    from Script.Design import handle_npc_ai

    stops: list[core.Effect] = []
    for key in game.characters:
        character_id = int(key)
        if (
            _settle(character_id, since)
            and character_id
            and handle_npc_ai.early_end(character_id)
        ):
            stops.append(core.Interrupt(key))
    return (*stops, core.StateChange(None, TICKED, since, game.clock))


def _new_day_due(game: core.GameState, who: str) -> bool:
    """
    NewDay 的条件：时钟进了 settled_day 之后的一天
    Keyword arguments:
    game -- GameState
    who -- 角色键
    Return arguments:
    bool -- 该跑新一天的结算时为真（只在第一个角色身上）
    """
    return _first(game, who) and game_time.day(game.clock) > _settled_day(game)


@core.event("gameplay_resolution.time_hooks.NewDay", _new_day_due)
def new_day(who: str) -> core.Effects:
    """
    新一天的结算（past_day_settle.update_new_day），settled_day 记成今天
    Keyword arguments:
    who -- 第一个角色的键
    Return arguments:
    Effects -- settled_day 的变化
    """
    game = core.state()
    from Script.Settle import past_day_settle

    past_day_settle.update_new_day()
    return (
        core.StateChange(
            None,
            SETTLED_DAY,
            _settled_day(game),
            game_time.day(game.clock),
        ),
    )


@core.input_hook(core.time_elapse)
def stop_at_tick(start: int, end: int) -> tuple[int, int]:
    """
    时钟最多走到下一次 Tick 与下一个 0 点
    Keyword arguments:
    start -- 流逝前的时钟
    end -- 流逝到的时钟（内核里最早的行动结束）
    Return arguments:
    tuple -- 交给内层的 (start, 终点)
    """
    return (
        start,
        min(
            end,
            _ticked(core.state()) + TICK_MINUTES,
            game_time.next_midnight(start),
        ),
    )


def _arts_break_due(game: core.GameState, who: str) -> bool:
    """
    ArtsBreak 的条件：玩家理智耗尽，还有源石技艺开着、解除还没排上
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 该中断技艺时为真
    """
    if who != PLAYER:
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
    随时间变化的数值（realtime_settle.character_aotu_change_value）
    Keyword arguments:
    character_id -- 角色id
    now_time -- 结算到的时间
    pl_start_time -- 从这一时刻算起
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
    学生赶去上课时把当前行为截到该动身的时刻（handle_npc_ai.judge_student_leave_truncate）
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 是否截短了当前行为
    """
    from Script.Design import handle_npc_ai

    return handle_npc_ai.judge_student_leave_truncate(character_id)


def judge_interrupt_character_behavior(character_id: int) -> int:
    """
    休息、睡觉、工作或娱乐是否就此结束（handle_npc_ai.judge_interrupt_character_behavior）
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 1 为结束了当前行为
    """
    from Script.Design import handle_npc_ai

    return handle_npc_ai.judge_interrupt_character_behavior(character_id)
