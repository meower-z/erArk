"""
gameplay_resolution 的行为收尾与角色行动投影
============================================
游戏数据存在内核的 GameState 里，经 domains 下的领域模块读写。GameState 给每个角色记下当前的行动：
action_id 是行动的种类，action_data 是意图（intent.Intent），开始分钟与时长同角色的当前行为
（activity.behavior）。内核时钟是游戏日历上的分钟数（game_time.minutes）。
一个行为的一生是三步，玩家与干员一样：
- PickNextAction：只读，交回一个行动（队首、玩家的选择或状态机）。
- StartAction：开始门（start_gate）、开始前的复查（starts.recheck）、时停（time_stop，最里层），
  再由 starts.behave 照着意图写游戏状态并结算。
- 行为的结束（wrap_up，每种行为由 starts.starter 登记为结束函数）：行为用完时间（结束或被打断）后，
  内核在这一分钟的事件之后、任何角色选行动之前运行它一次。把角色结算到此刻（time_hooks.tick_one），
  收掉行为（character_behavior.end_action），再跑选行动之前的检查。
0 分钟的编辑（edits.EDIT）与 kernel.Idle 没有结束函数，所以不收尾。
事件 TargetLeft：干员的交互对象离开了它所在的场景，它的行为在此刻结束。
"""

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import cast

from Script.Core import constant, get_text
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import time_hooks
from Script.Modules.gameplay_resolution import intent
from Script.Modules.domains import modes, roster as roster_domain
from Script.Modules.domains import activity

PLAYER = "0"
""" 玩家在 GameState.characters 里的键 """

_ = get_text._
""" 翻译api """

OPEN = "open"
""" 存档的内核状态里可能带的角色数据键：为真表示行为开始了、还没收尾；读档时由 project 换掉 """
TICKED = "ticked"
""" 全局数据的键：上一次 Tick 结算到的时钟 """
SETTLED_DAY = "settled_day"
""" 全局数据的键：已结算新一天的游戏日序号 """

behave = core.Start(intent.KIND_PREFIX + "Behavior")
""" 通用种类 Behavior 的行动；开始函数由 starts 登记 """

minutes = game_time.minutes
""" 游戏时间换成内核时钟的分钟数 """


@core.input_hook(core.start_action)
def time_stop(act: core.Action) -> tuple[core.Action]:
    """
    StartAction 最里层的输入钩子：时停中玩家的行动在内核里是 0 分钟，名义分钟数留在行动数据里。
    它在开始门与开始前的复查（starts.recheck）之后运行，门或复查换上的行动同样是 0 分钟，时钟不动。
    开始的是解除时停（TIME_STOP_OFF）时不换：它的结算关掉时停，时钟照名义分钟数前进
    Keyword arguments:
    act -- 要开始的行动
    Return arguments:
    tuple -- 交给内层的行动
    """
    data = act.action_data
    if (
        act.who == PLAYER
        and modes.time_stop()
        and isinstance(data, Mapping)
        and "behavior_id" in data
        and data["behavior_id"] != constant.Behavior.TIME_STOP_OFF
    ):
        return (replace(act, duration=0),)
    return (act,)


def roster() -> tuple[str, ...]:
    """
    在场的角色：玩家在前，干员按id；101/102 阶段角色由 require_eligible 拦截
    Return arguments:
    tuple -- 角色键
    """
    npcs = [
        int(roster_domain.require_eligible(cid))
        for cid in roster_domain.active_sorted()
        if cid != 0
    ]
    return (PLAYER, *(str(cid) for cid in npcs))


def wrap_up(act: core.Action) -> core.Effects:
    """
    行为的结束函数：结算到此刻，收掉行为；玩家另跑寻路的下一段、交互对象、实时数据、自动存档与成就，
    干员另跑选行动前的检查（handle_npc_ai.before_pick）
    Keyword arguments:
    act -- 结束的行动
    Return arguments:
    Effects -- 空
    """
    from Script.Design import character_behavior, handle_npc_ai

    who = int(act.who)
    time_hooks.tick_one(who)
    character_behavior.end_action(who)
    if who == 0:
        character_behavior.player_after_end()
    else:
        handle_npc_ai.before_pick(who)
    return ()


def _target_left_when(game: core.GameState) -> str | None:
    """
    TargetLeft 的触发：干员的行为还在进行，它的交互对象已不在它所在的场景。只在这一分钟时钟的结算之后成立
    Keyword arguments:
    game -- 当前的 GameState，交给 character_behavior.target_left
    Return arguments:
    str | None -- 名单顺序里第一个该提前结束的干员的键
    """
    if not time_hooks.clock_settled(game):
        return None
    from Script.Design import character_behavior

    for who, character in game.characters.items():
        act = character.action
        if (
            who != PLAYER
            and core.has_end(act)
            and act.start + act.duration > game.clock
            and character_behavior.target_left(int(who), game)
        ):
            return who
    return None


@core.event("gameplay_resolution.actions.TargetLeft", _target_left_when)
def target_left(who: str) -> core.Effects:
    """
    交互对象离开了：干员的行为在此刻结束，随后由它的结束函数（wrap_up）收尾
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Effects -- 结束行动的 Interrupt
    """
    return (core.Interrupt(who),)


def _intent_of(behavior: activity.Behavior) -> intent.Intent:
    """
    角色的当前行为写成意图（新游戏、没有内核状态的旧存档）
    Keyword arguments:
    behavior -- 读出的当前行为
    Return arguments:
    Intent -- 行为id与分钟数
    """
    return intent.Intent(
        behavior_id=behavior.behavior_id, minutes=int(behavior.duration)
    )


def state_from_cache(clock: int | None = None) -> core.GameState:
    """
    由在编名单与角色的当前行为在 clock 这一分钟投影出新的 GameState（新游戏、新周目、没有内核状态的旧存档）
    名单上每个角色（玩家与 roster.active() 里的干员）的行动取 activity.behavior 的开始时间与分钟数，
    开始时间没设过时从 clock 开始。干员的行动是 Behavior，到时由 wrap_up 收尾；
    玩家的是同样起止的 kernel.Idle，到时不收尾，直接选下一个行动。
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
        behavior = activity.behavior(int(who))
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
        if who == PLAYER:
            act = _idle(act)
        characters[who] = core.Character(act, MappingProxyType({}))
    data: dict[str, core.JSON] = {
        TICKED: clock,
        SETTLED_DAY: game_time.day(clock),
    }
    return core.GameState(
        clock, MappingProxyType(characters), MappingProxyType(data)
    )


def _idle(act: core.Action) -> core.Action:
    """
    同样起止的 kernel.Idle：到时不收尾
    Keyword arguments:
    act -- 行动
    Return arguments:
    Action -- 换成 kernel.Idle 的行动
    """
    return core.Action(act.who, core.idle.name, None, act.start, act.duration)


def drifted() -> list[int]:
    """
    行为还在进行（有结束函数且还没结束）的角色里，activity.behavior 的开始或分钟数与 GameState 里的行动不一致的角色。
    行为已结束、等着收尾或选下一个行动的角色不比：收尾换掉了 activity.behavior，打断改短了 GameState 里的行动
    Return arguments:
    list -- 角色id
    """
    game = core.state()
    found = []
    for who, c in game.characters.items():
        act = c.action
        if not core.has_end(act) or act.start + act.duration <= game.clock:
            continue
        behavior = activity.behavior(int(who))
        if (
            minutes(behavior.start_time) != act.start
            or behavior.duration != act.duration
        ):
            found.append(int(who))
    return found


def project(new: core.GameState) -> core.GameState:
    """
    Reset 步骤：new 没有角色时由领域数据在 new 的时钟投影出角色（state_from_cache），全局数据以 new 的为准，
    new 没有的 ticked 与 settled_day 取投影的。new 有角色（存档里的 GameState）时照原样，
    只换掉角色数据里的 open：open 不为真的角色（行为已收尾或没开始过）换成同样起止的 kernel.Idle，
    open 为真的保留行为，到时收尾；open 一律去掉
    Keyword arguments:
    new -- 换入的 GameState
    Return arguments:
    GameState -- 带角色的 GameState
    """
    if new.characters:
        for who in new.characters:
            if who != PLAYER and who.isdigit():
                roster_domain.require_eligible(int(who))
        if not any(OPEN in c.data for c in new.characters.values()):
            return new
        characters = {
            who: core.Character(
                c.action if c.data.get(OPEN) is True else _idle(c.action),
                MappingProxyType(
                    {k: v for k, v in c.data.items() if k != OPEN}
                ),
            )
            for who, c in new.characters.items()
        }
        return core.GameState(new.clock, MappingProxyType(characters), new.data)
    projected = state_from_cache(new.clock)
    data = {**projected.data, **new.data}
    return core.GameState(
        new.clock, projected.characters, MappingProxyType(data)
    )
