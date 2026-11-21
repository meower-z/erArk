"""
gameplay_resolution 的时钟：5 分钟一次的 Tick、0 点的 NewDay，以及 TimeElapse 的输入钩子
==========================================================================================
游戏只有一个时钟，就是内核的 clock（游戏日历上的分钟数，game_time.now() 读它）。
随时间变化的数值不在 TimeElapse 里结算（那里 state().clock 还是旧的），而在两种事件里：
- Tick：时钟比 ticked 晚 5 分钟、或跨进了 ticked 之后的一天时，把每个角色从 ticked 结算到此刻，
  到点该提前结束的干员发 Interrupt，再结算外勤委托，ticked 记成此刻。数值按分钟的比率精确累加，
  5 分钟只是结算的间隔：怎样切段，合计都一样；没有经过时间的一段什么也不写，所以同一时刻再结算一次不改任何值。
  结算里掷骰被吵醒的角色（needs.sleep_noise）在同一步里醒来（_wake_the_woken）。
- NewDay：时钟进了 settled_day 之后的一天时跑新一天的结算，settled_day 记成今天。
TimeElapse 的输入钩子让时钟最多走到下一次 Tick 与下一个 0 点，所以新一天的结算在 0 点、任何人选行动之前。
一个行为结束时（actions.wrap_up）由 tick_one 把这个角色结算到此刻，Tick 只从 ticked 算起，同一段不会算两遍。
本模块不在顶层导入 gameplay_resolution 的模块：actions 在登记 TargetLeft 之前导入本模块，
Tick、NewDay 因此排在事件表的最前面。
源石技艺中断（ArtsBreak）是事件：理智耗尽、还有技艺开着时，给玩家排上解除催眠与解除时停。
幽灵课堂（OrphanClass）是事件：课堂模式开着而玩家已不在 H 时下课，在任何人选行动之前。
这四个是全局的事件，不按角色检查。内核不保证同时成立的事件的先后，先后由条件写明：
NewDay 等 Tick 结算到此刻（ticked 等于时钟）；别的事件等这一分钟的 Tick 与 NewDay（clock_settled），
给玩家排结束的事件等 ArtsBreak（arts_settled）。
"""

from dataclasses import replace
from types import MappingProxyType
from typing import cast

from Script.Core import cache_control, game_type
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import flags, modes, needs

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

TICK_MINUTES = 5
""" 两次 Tick 之间的分钟数 """
TICKED = "ticked"
""" GameState 的全局键：上一次 Tick 结算到的时钟（同 actions.TICKED） """
SETTLED_DAY = "settled_day"
""" GameState 的全局键：已跑过新一天结算的游戏日（同 actions.SETTLED_DAY） """


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


def _wake_the_woken() -> None:
    """时间结算里被吵醒的角色（needs.sleep_noise）在这一步醒来：按角色id依次结算，取出各自的记录"""
    from Script.Design import handle_npc_ai_in_h

    for cid in sorted(needs.noise_woken()):
        handle_npc_ai_in_h.wake_by_noise(needs.take_woken(cid), cid)


def tick_one(who: int) -> None:
    """
    把一个角色结算到此刻（他的行为结束时调用；下一次 Tick 只从 ticked 算起），被吵醒的角色随即醒来。
    时停中玩家此刻开始的行动在内核里是 0 分钟，从行动开始按缓存里的名义分钟数结算
    Keyword arguments:
    who -- 角色id
    """
    game = core.state()
    character_data = cache.character_data.get(who)
    if (
        who == 0
        and modes.time_stop()
        and character_data is not None
        and game_time.minutes(character_data.behavior.start_time) == game.clock
    ):
        _settle(who, game.clock, game.clock + character_data.behavior.duration)
    else:
        _settle(who, _ticked(game))
    _wake_the_woken()


def _tick_due(game: core.GameState) -> bool | None:
    """
    Tick 的触发：时钟比 ticked 晚了 5 分钟，或已进了 ticked 之后的一天
    Keyword arguments:
    game -- GameState
    Return arguments:
    bool | None -- 该结算时为 True，否则为 None
    """
    ticked = _ticked(game)
    if game.clock - ticked >= TICK_MINUTES or game_time.day(
        game.clock
    ) > game_time.day(ticked):
        return True
    return None


@core.event("gameplay_resolution.time_hooks.Tick", _tick_due)
def tick(_due: bool) -> core.Effects:
    """
    把每个角色从 ticked 结算到此刻；到点该提前结束的干员（休息够了、该去洗澡、学生该去上课）被打断；
    然后判断外勤委托的完成（时停中没有 Tick，委托也不结算），最后结算里被吵醒的角色醒来。
    结算的起点读状态里的 ticked，所以同一状态上再跑一次什么也不结算
    Keyword arguments:
    _due -- 触发交回的 True
    Return arguments:
    Effects -- 打断，与 ticked 记成此刻
    """
    game = core.state()
    since = _ticked(game)
    from Script.Design import handle_npc_ai
    from Script.System.Field_Commission_System import field_commission_function

    stops: list[core.Effect] = []
    for key in game.characters:
        character_id = int(key)
        if (
            _settle(character_id, since)
            and character_id
            and handle_npc_ai.early_end(character_id)
        ):
            stops.append(core.Interrupt(key))
    field_commission_function.update_field_commission()
    _wake_the_woken()
    return (*stops, core.StateChange(None, TICKED, since, game.clock))


def _new_day_due(game: core.GameState) -> int | None:
    """
    NewDay 的触发：时钟进了 settled_day 之后的一天，且 Tick 已把每个角色结算到此刻（ticked 等于时钟）
    Keyword arguments:
    game -- GameState
    Return arguments:
    int | None -- 该跑新一天的结算时为今天的游戏日，否则为 None
    """
    today = game_time.day(game.clock)
    if today > _settled_day(game) and _ticked(game) == game.clock:
        return today
    return None


@core.event("gameplay_resolution.time_hooks.NewDay", _new_day_due)
def new_day(today: int) -> core.Effects:
    """
    新一天的结算（past_day_settle.update_new_day），settled_day 记成今天
    Keyword arguments:
    today -- 今天的游戏日
    Return arguments:
    Effects -- settled_day 的变化
    """
    from Script.Settle import past_day_settle

    settled = _settled_day(core.state())
    past_day_settle.update_new_day()
    return (core.StateChange(None, SETTLED_DAY, settled, today),)


def clock_settled(game: core.GameState) -> bool:
    """
    这一分钟时钟的结算（Tick 与 NewDay）是否都已跑完；别的事件以此为前提
    Keyword arguments:
    game -- GameState
    Return arguments:
    bool -- Tick 与 NewDay 都不成立时为真
    """
    return _tick_due(game) is None and _new_day_due(game) is None


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


def _arts_break_due(game: core.GameState) -> bool | None:
    """
    ArtsBreak 的触发：这一分钟时钟的结算跑完了，玩家理智耗尽，还有源石技艺开着、解除还没排上
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    bool | None -- 该中断技艺时为 True，否则为 None
    """
    from Script.Settle import realtime_settle

    if clock_settled(game) and realtime_settle.arts_break_due(game):
        return True
    return None


def arts_settled(game: core.GameState) -> bool:
    """
    源石技艺中断是否已结算；给玩家排结束的事件以此为前提，玩家的解除技艺排在这些结束之前
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    bool -- ArtsBreak 不成立时为真
    """
    return _arts_break_due(game) is None


@core.event("gameplay_resolution.time_hooks.ArtsBreak", _arts_break_due)
def arts_break(_due: bool) -> core.Effects:
    """
    源石技艺中断：关透视，给玩家排上解除催眠与解除时停，在玩家接下来的选择里开始
    Keyword arguments:
    _due -- 触发交回的 True
    Return arguments:
    Effects -- 排行动时要交回内核的打断
    """
    from Script.Settle import realtime_settle

    return realtime_settle.break_arts()


def _orphan_class_due(game: core.GameState) -> bool | None:
    """
    OrphanClass 的触发：这一分钟时钟的结算跑完了，课堂模式开着，玩家却已不在 H（课堂 H 以别的方式结束了）
    Keyword arguments:
    game -- 当前的 GameState
    Return arguments:
    bool | None -- 该下课时为 True，否则为 None
    """
    player = cache.character_data.get(0)
    if (
        clock_settled(game)
        and modes.sex_class(game)
        and player is not None
        and not flags.get(player.cid, "is_h", game)
    ):
        return True
    return None


@core.event("gameplay_resolution.time_hooks.OrphanClass", _orphan_class_due)
def orphan_class(_due: bool) -> core.Effects:
    """
    幽灵课堂下课（sex_class_handle.settle_orphan_class）
    Keyword arguments:
    _due -- 触发交回的 True
    Return arguments:
    Effects -- 无
    """
    from Script.System.Education_System import sex_class_handle

    sex_class_handle.settle_orphan_class()
    return ()
