"""
gameplay_resolution 的内核钩子：玩家行动的回合、干员的结算，以及按缓存投影出的 GameState
==========================================================================================
游戏数据仍在旧缓存 cache 里，由本模块读写。内核的 GameState 给每个角色记下当前的行动（行为id、开始分钟、时长，
抄自缓存）。
内核时钟是游戏日历上的分钟数（game_time.get_play_time）。角色顺序是玩家在前，干员按id。
一个玩家行动是一回合：
- 玩家的行动开始时（behave）：缓存的游戏时间推进名义分钟数，跑玩家的结算。不在时停中时，记下本回合要结算的干员。
- 干员在内核里选行动时（npc_action，由 npc_action_choice 的 npc_hook 调用）：本回合到期的干员得到一个 0 分钟的结算行动，
  这个行动开始时（_npc_pass）跑干员的一次结算。其余干员得到一个到 due 给出的分钟为止的行动。
- 时钟走到玩家行动的结束时（elapse）：本回合还没结算完的干员各自结算到完，再跑自动存档请求与成就（_close_turn）。
  新一天由 time_hooks 的 TimeElapse 输出钩子跑。
- 每次结算之后，缓存里比内核更早结束的干员由 Interrupt 提前结束内核里的行动（resync），内核到时让它重新选行动。
跑内核之前，resynced 按缓存投影出 GameState。
"""

import datetime
from dataclasses import dataclass, replace
from types import FunctionType, MappingProxyType

from Script.Core import cache_control, constant, game_type, get_text
from Script.Design import character_behavior, game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import npc_passes, npc_start
from Script.Modules.npc_action_choice import choice

PLAYER = "0"
""" 玩家在 GameState.characters 里的键 """

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """


@dataclass
class Turn:
    """一回合（一个玩家行动）里的结算状态"""

    pl_start: datetime.datetime
    """ 玩家行动的开始时间 """
    id_list: tuple[int, ...]
    """ 本回合结算的干员，按id """
    end: int
    """ 玩家行动在内核里的结束时刻 """
    closed: bool = False
    """ 回合末的结算是否已跑 """


_turn: Turn | None = None
""" 当前回合；时停中与回合外为 None """


def minutes(when: datetime.datetime) -> int:
    """
    游戏时间换成内核时钟的分钟数
    Keyword arguments:
    when -- 游戏时间
    Return arguments:
    int -- 游戏日历上的分钟数
    """
    return int(game_time.get_play_time(when) / datetime.timedelta(minutes=1))


def mirror(behavior: game_type.Behavior, **extra: core.JSON) -> core.JSON:
    """
    缓存里的一个行为写成内核行动的数据
    Keyword arguments:
    behavior -- 缓存里的行为
    extra -- 另加的键
    Return arguments:
    JSON -- 行为id、开始分钟、时长，以及另加的键
    """
    return MappingProxyType(
        {
            "behavior_id": behavior.behavior_id,
            "start": minutes(behavior.start_time),
            "duration": int(behavior.duration),
            **extra,
        }
    )


def _cache_end(character_id: int) -> int:
    """
    缓存里角色当前行为的结束分钟：空闲时是它的开始
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 结束分钟
    """
    behavior = cache.character_data[character_id].behavior
    start = minutes(behavior.start_time)
    if behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
        return start
    return start + int(behavior.duration)


def due(character_id: int) -> int:
    """
    干员在内核里该结束的分钟：本回合还要结算的干员是它的到期时刻
    （npc_passes.npc_due），其余的是缓存里的结束，不早于玩家行动的结束；
    回合外（时停中）至少到下一分钟，干员不在这时结算
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 分钟
    """
    turn = _turn
    if (
        turn is not None
        and character_id in turn.id_list
        and character_id not in cache.over_behavior_character
    ):
        return minutes(npc_passes.npc_due(character_id, turn.pl_start))
    end = _cache_end(character_id)
    if turn is None:
        return max(end, core.state().clock + 1)
    return max(end, turn.end)


def needs_pass(character_id: int) -> bool:
    """
    干员本回合还要结算且已到期：它在本回合的名单里，还不在 cache.over_behavior_character 里，到期时刻不晚于内核时钟
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 要结算时为 True
    """
    turn = _turn
    return (
        turn is not None
        and character_id in turn.id_list
        and character_id not in cache.over_behavior_character
        and due(character_id) <= core.state().clock
    )


def wants_choice(character_id: int) -> bool:
    """
    干员要结算，且缓存里的行为是发呆（SHARE_BLANKLY）：这次结算要给它选新的行动
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 要选行动时为 True
    """
    behavior = cache.character_data[character_id].behavior
    return (
        needs_pass(character_id)
        and behavior.behavior_id == constant.Behavior.SHARE_BLANKLY
    )


def npc_action(who: str, chosen: "choice.Choice | None") -> core.Action:
    """
    干员在内核里选行动时交回的行动，由 npc_action_choice 的 npc_hook 调用。
    要结算的干员得到一个 0 分钟的结算行动，行动数据带 npc_pass。选出的行动由 npc_start.hold 留到这个行动开始时用。
    其余干员得到一个到 due 给出的分钟为止的行动。
    Keyword arguments:
    who -- 干员在 GameState.characters 里的键
    chosen -- npc_action_choice 选出的行动，没选行动时为 None
    Return arguments:
    Action -- 交给内核的行动
    """
    character_id = int(who)
    behavior = cache.character_data[character_id].behavior
    if needs_pass(character_id):
        if chosen is not None:
            npc_start.hold(character_id, chosen)
        return core.new_action(behave, who, 0, mirror(behavior, npc_pass=True))
    clock = core.state().clock
    return core.new_action(
        behave, who, max(due(character_id) - clock, 0), mirror(behavior)
    )


def resync(game: core.GameState, skip: str = "") -> core.Effects:
    """
    结算之后，缓存里该比内核更早结束的干员：Interrupt 提前结束它在内核里的行动，到时重排。
    已不在 cache.npc_id_got 里的干员（例如被删掉的角色）从 GameState 里移除
    Keyword arguments:
    game -- 当前的 GameState
    skip -- 不看的角色键（正在选行动的干员）
    Return arguments:
    Effects -- Interrupt，与移除干员的 Change
    """
    effects: list[core.Effect] = []
    present = set(roster())
    gone: list[str] = []
    for who, character in game.characters.items():
        if who in (PLAYER, skip):
            continue
        if who not in present:
            gone.append(who)
            continue
        end = character.action.start + character.action.duration
        if end > game.clock and due(int(who)) < end:
            effects.append(core.Interrupt(who))
    if gone:
        effects.append(core.Change(None, "roster", "remove", tuple(gone)))
    return tuple(effects)


@core.action("gameplay_resolution.Behavior")
def behave(act: core.Action) -> core.Effects:
    """
    gameplay_resolution.Behavior 行动的开始。干员的行动交给 _npc_pass。
    玩家的行动开始一个回合：缓存的游戏时间推进行动数据里的名义分钟数，再结算玩家的这一行动。
    时停中游戏时间退回玩家行为的时长，只跑成就，玩家的行动当场结束。
    不在时停中时，刷新外勤委托，记下本回合要结算的干员，把内核里还没有的干员加进来。
    玩家的行动在内核里是 0 分钟时，回合末的结算当场跑。
    Keyword arguments:
    act -- 开始的行动，玩家的行动数据带 minutes（名义分钟数）
    Return arguments:
    Effects -- 加入干员的 Change 与提前结束内核行动的 Interrupt，时停中是结束玩家行动的 Interrupt
    """
    global _turn
    if act.who != PLAYER:
        return _npc_pass(act)
    data = act.action_data
    assert isinstance(data, MappingProxyType)
    nominal = data["minutes"]
    assert isinstance(nominal, int)
    _turn = None
    game_time.sub_time_now(nominal)
    cache.over_behavior_character = set()
    player = cache.character_data[0]
    pl_start_time, pl_duration = cache.game_time, 0
    while 0 not in cache.over_behavior_character:
        pl_start_time = player.behavior.start_time
        pl_duration = player.behavior.duration
        character_behavior.character_behavior(0, cache.game_time, pl_start_time)
    if cache.time_stop_mode:
        cache.achievement.time_stop_duration += pl_duration
        game_time.sub_time_now(minute=pl_duration * -1)
        _achievements()
        return (core.Interrupt(PLAYER),)
    from Script.System.Field_Commission_System import field_commission_function

    field_commission_function.update_field_commission()
    id_list = tuple(sorted(cid for cid in cache.npc_id_got if cid != 0))
    _turn = Turn(pl_start_time, id_list, act.start + act.duration)
    game = core.state()
    effects: list[core.Effect] = []
    missing = tuple(
        str(cid) for cid in id_list if str(cid) not in game.characters
    )
    if missing:
        effects.append(core.Change(None, "roster", "add", missing))
    if act.duration == 0:
        _close_turn()
    effects.extend(resync(game))
    return tuple(effects)


def _npc_pass(act: core.Action) -> core.Effects:
    """
    干员结算行动的开始：跑这名干员的一次结算（npc_passes.settle_npc_pass）。
    干员空闲时，这次结算选出行动并开始它，选择里留下了行动时用留下的那个。
    结算之后丢掉没用到的选择，缓存里比内核更早结束的干员提前结束内核里的行动。
    行动数据不带 npc_pass 时什么都不做。
    Keyword arguments:
    act -- 开始的行动
    Return arguments:
    Effects -- 提前结束内核行动的 Interrupt
    """
    data = act.action_data
    turn = _turn
    if not isinstance(data, MappingProxyType) or not data.get("npc_pass"):
        return ()
    assert turn is not None
    character_id = int(act.who)
    npc_passes.settle_npc_pass(character_id, turn.pl_start)
    npc_start.drop(character_id)
    return resync(core.state())


def _close_turn() -> None:
    """
    回合末的结算。本回合还没结算完的干员按到期先后结算到完。玩家睡觉留下了存档标记时，向 save_load 提出自动存档。
    最后跑时停与群交的成就
    """
    turn = _turn
    assert turn is not None
    turn.closed = True
    npc_passes.run_npc_passes(turn.id_list, turn.pl_start)
    if cache.pl_sleep_save_flag:
        cache.pl_sleep_save_flag = False
        from Script.Modules.save_load import autosave

        autosave.update_save()
    _achievements()


def _achievements() -> None:
    """时停与群交的成就（今天每回合结束时跑）"""
    from Script.UI.Panel import achievement_panel

    achievement_panel.achievement_flow(_("时停"))
    achievement_panel.achievement_flow(_("群交"))


@core.input_hook(core.time_elapse)
def elapse(
    start: int, end: int
) -> tuple[int, int] | core.Intercept[tuple[int, core.Effects]]:
    """
    时间流逝：走到玩家行动的结束时跑回合末的结算；别的时候不结算
    Keyword arguments:
    start -- 流逝前的时钟
    end -- 流逝到的时钟（最早的行动结束）
    Return arguments:
    Intercept -- 新时钟与提前结束的行动；别的时候原样交给内层
    """
    turn = _turn
    if turn is None or turn.closed or end < turn.end:
        return (start, end)
    _close_turn()
    game = replace(core.state(), clock=end)
    return core.Intercept((end, resync(game)))


def change_roster(game: core.GameState, change: core.Change) -> core.GameState:
    """
    在场角色的规则：op 为 add 时加上本回合新来的干员（此刻结束，马上选行动），为 remove 时移除干员；
    角色按玩家在前、干员按id重排
    Keyword arguments:
    game -- 当前的 GameState
    change -- 要加或要移除的干员键
    Return arguments:
    GameState -- 新的 GameState
    """
    keys = change.operand
    assert isinstance(keys, tuple)
    characters = dict(game.characters)
    for who in keys:
        assert isinstance(who, str)
        if change.op == "remove":
            characters.pop(who, None)
            continue
        behavior = cache.character_data[int(who)].behavior
        act = core.Action(who, behave.name, mirror(behavior), game.clock, 0)
        characters[who] = core.Character(act, MappingProxyType({}))
    ordered = sorted(characters, key=int)
    return replace(
        game,
        characters=MappingProxyType({who: characters[who] for who in ordered}),
    )


core.rule("roster")(change_roster)


def roster() -> tuple[str, ...]:
    """
    在场的角色：玩家在前，干员按id
    Return arguments:
    tuple -- 角色键
    """
    npcs = sorted(cid for cid in cache.npc_id_got if cid != 0)
    return (PLAYER, *(str(cid) for cid in npcs))


def resynced(game: core.GameState) -> core.GameState:
    """
    跑内核前由缓存投影出 GameState：时钟取缓存的游戏时间；玩家的行动此刻结束（内核总从玩家的选择开始）；
    干员的行动到缓存里的结束为止（空闲的到它的开始）
    Keyword arguments:
    game -- 上次跑完的 GameState（只留角色的数据）
    Return arguments:
    GameState -- 投影出的 GameState
    """
    global _turn
    _turn = None
    clock = minutes(cache.game_time)
    characters: dict[str, core.Character] = {}
    for who in roster():
        behavior = cache.character_data[int(who)].behavior
        end = clock if who == PLAYER else _cache_end(int(who))
        act = core.Action(
            who, behave.name, mirror(behavior), clock, max(end - clock, 0)
        )
        old = game.characters.get(who)
        data = old.data if old else MappingProxyType({})
        characters[who] = core.Character(act, data)
    return replace(game, clock=clock, characters=MappingProxyType(characters))


def forget() -> None:
    """读档或内核出错后，丢掉当前回合"""
    global _turn
    _turn = None
