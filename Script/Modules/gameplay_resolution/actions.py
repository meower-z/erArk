"""
gameplay_resolution 的行动收尾与按缓存投影出的 GameState
======================================================
游戏数据仍在旧缓存 cache 里。内核的 GameState 给每个角色记下当前的行动：action_id 是行动的种类，
action_data 是意图（intent.Intent），开始分钟与时长同缓存里的行为。内核时钟是游戏日历上的分钟数（game_time.minutes）。
一个行动的一生是三步，玩家与干员一样：
- 事件 ActionOver：行动开始过（角色数据 open 为真）且已结束。把角色结算到此刻（time_hooks.tick_one），
  收掉行为（character_behavior.end_action），再跑选行动之前的检查，最后关上 open。
- PickNextAction：只读，交回一个行动（队首、玩家的选择或状态机）。
- StartAction：开始门（start_gate），再由 starts.behave 照着意图写缓存并结算。
事件 TargetLeft：干员的交互对象离开了它所在的场景，它的行动在此刻结束。
事件的登记顺序是 Tick、NewDay、ActionOver（time_hooks 先导入），一天最后几分钟先结算，选行动之前的检查看到的是新的一天。
"""

from types import MappingProxyType
from typing import cast

from Script.Core import cache_control, game_type, get_text
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import time_hooks
from Script.Modules.gameplay_resolution import intent

PLAYER = "0"
""" 玩家在 GameState.characters 里的键 """

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_ = get_text._
""" 翻译api """

OPEN = "open"
""" 角色数据的键：开始了、还没收尾（ActionOver）的行动为 True，否则为 None """
TICKED = "ticked"
""" 全局数据的键：上一次 Tick 结算到的时钟 """
SETTLED_DAY = "settled_day"
""" 全局数据的键：已结算新一天的游戏日序号 """

behave = core.Start(intent.KIND_PREFIX + "Behavior")
""" 通用种类 Behavior 的行动；开始函数由 starts 登记 """

minutes = game_time.minutes
""" 游戏时间换成内核时钟的分钟数 """


def roster() -> tuple[str, ...]:
    """
    在场的角色：玩家在前，干员按id
    Return arguments:
    tuple -- 角色键
    """
    npcs = sorted(cid for cid in cache.npc_id_got if cid != 0)
    return (PLAYER, *(str(cid) for cid in npcs))


def _over_when(game: core.GameState, who: str) -> bool:
    """
    ActionOver 的条件：行动开始过、还没收尾，且已结束
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 该收尾时为真
    """
    act = game.characters[who].action
    return (
        core.value(game, who, OPEN) is True
        and act.start + act.duration <= game.clock
    )


@core.event("gameplay_resolution.actions.ActionOver", _over_when)
def action_over(who: str) -> core.Effects:
    """
    行动收尾：结算到此刻，收掉行为，跑选行动之前的检查，关上 open。
    玩家另跑寻路的下一段、实时数据与收尾的存档和成就；干员另跑行动前检查（handle_npc_ai.before_pick）
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Effects -- 关上 open 的 StateChange
    """
    from Script.Design import character_behavior, handle_npc_ai

    character_id = int(who)
    time_hooks.tick_one(character_id)
    character_behavior.end_action(character_id)
    if character_id == 0:
        character_behavior.player_after_end()
    else:
        handle_npc_ai.before_pick(character_id)
    return (core.StateChange(who, OPEN, True, None),)


def _target_left_when(game: core.GameState, who: str) -> bool:
    """
    TargetLeft 的条件：干员的行动还在进行，它的交互对象已不在它所在的场景
    Keyword arguments:
    game -- 当前的 GameState
    who -- 角色键
    Return arguments:
    bool -- 该提前结束时为真
    """
    if who == PLAYER or core.value(game, who, OPEN) is not True:
        return False
    act = game.characters[who].action
    if act.start + act.duration <= game.clock:
        return False
    from Script.Design import character_behavior

    return character_behavior.target_left(int(who))


@core.event("gameplay_resolution.actions.TargetLeft", _target_left_when)
def target_left(who: str) -> core.Effects:
    """
    交互对象离开了：干员的行动在此刻结束，随后由 ActionOver 收尾
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Effects -- 结束行动的 Interrupt
    """
    return (core.Interrupt(who),)


def _intent_of(behavior: game_type.Behavior) -> intent.Intent:
    """
    缓存里的行为写成意图（新游戏、没有内核状态的旧存档）
    Keyword arguments:
    behavior -- 缓存里的行为
    Return arguments:
    Intent -- 行为id与分钟数
    """
    return intent.Intent(
        behavior_id=behavior.behavior_id, minutes=int(behavior.duration)
    )


def state_from_cache(clock: int | None = None) -> core.GameState:
    """
    由缓存在 clock 这一分钟投影出新的 GameState（新游戏、新周目、没有文件 "2" 的旧存档）
    名单上每个角色（玩家与 cache.npc_id_got 里的干员）的行动取缓存里行为的行为id、分钟数与开始时间，
    开始时间没设过时从 clock 开始。
    干员的 open 为 True，表示行动已开始、还没收尾。玩家的 open 为 None，玩家这个行动到时不经 ActionOver 收尾。
    全局数据的 ticked 是 clock，settled_day 是 clock 所在的游戏日
    Keyword arguments:
    clock -- 投影的时钟（分钟），None 时为内核此刻的时钟
    Return arguments:
    GameState -- 投影出的 GameState
    """
    if clock is None:
        clock = minutes(game_time.now())
    characters: dict[str, core.Character] = {}
    for who in roster():
        behavior = cache.character_data[int(who)].behavior
        start = clock
        if behavior.start_time.year > 1:
            start = minutes(behavior.start_time)
        act = core.Action(
            who,
            behave.name,
            cast(core.JSON, dict(_intent_of(behavior))),
            start,
            int(behavior.duration),
        )
        opened: dict[str, core.JSON] = {OPEN: None if who == PLAYER else True}
        characters[who] = core.Character(act, MappingProxyType(opened))
    data: dict[str, core.JSON] = {
        TICKED: clock,
        SETTLED_DAY: game_time.day(clock),
    }
    return core.GameState(
        clock, MappingProxyType(characters), MappingProxyType(data)
    )


def drifted() -> list[int]:
    """
    行动还在进行（open 为真且还没结束）的角色里，缓存里行为的开始或分钟数与内核里的行动不一致的角色。
    行动已结束、等着收尾或选下一个行动的角色不比：收尾换掉了缓存里的行为，打断改短了内核里的行动
    Return arguments:
    list -- 角色id
    """
    game = core.state()
    found = []
    for who, c in game.characters.items():
        act = c.action
        if (
            c.data.get(OPEN) is not True
            or act.start + act.duration <= game.clock
        ):
            continue
        behavior = cache.character_data[int(who)].behavior
        if (
            minutes(behavior.start_time) != act.start
            or behavior.duration != act.duration
        ):
            found.append(int(who))
    return found


def project(new: core.GameState) -> core.GameState:
    """
    Reset 步骤：new 没有角色时由缓存在 new 的时钟投影出角色（state_from_cache），全局数据以 new 的为准，
    new 没有的 ticked 与 settled_day 取投影的；new 有角色（存档里的 GameState）时原样返回
    Keyword arguments:
    new -- 换入的 GameState
    Return arguments:
    GameState -- 带角色的 GameState
    """
    if new.characters:
        return new
    projected = state_from_cache(new.clock)
    data = {**projected.data, **new.data}
    return core.GameState(
        new.clock, projected.characters, MappingProxyType(data)
    )
