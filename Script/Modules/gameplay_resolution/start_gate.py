"""
gameplay_resolution 的开始门
============================
gate 是 StartAction 输入钩子。start_gate 在 LOAD_ORDER 里紧挨着 actions，内层没有别的 StartAction 输入钩子，
所以 gate 看到的是最终要开始的行动。
gate 只检查两种行动：行为（actions.behave）与计划队列里干员的行动（plan_queue.start_planned）。
行动开始前按 GATES 的顺序检查。第一道关上的闸把行动换成 1 分钟的发呆（一个 behave 行动），缓存里的行为也换成发呆。
计划队列排下的行动在行动数据里可以另带两个键，由 plan_queue 写入：
- target：交互对象id。没有这个键时，幼年阶段与处女两道闸看缓存里角色当前的交互对象。
- premises：前提id的元组，行动开始时每个前提都要成立。
不带这两个键的行动（玩家选出的行动、干员的结算行动）只会被幼年阶段与处女两道闸关上。
时停中玩家的行动在内核里是 0 分钟，时钟不走，名义分钟数留在行动数据的 minutes 里。
"""

from collections.abc import Callable, Mapping
from dataclasses import replace
from types import MappingProxyType

from Script.Config import game_config
from Script.Core import cache_control, constant, game_type
from Script.Design import child_stage_gate, handle_premise, virgin_break_gate
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, plan_queue

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

TARGET = "target"
""" 行动数据里交互对象id的键 """
PREMISES = "premises"
""" 行动数据里前提id元组的键 """
MINUTES = "minutes"
""" 行动数据里名义分钟数的键（玩家的行动带它） """
GATE = "gate"
""" 换成发呆的行动数据里，记下没过的那条检查的键 """

calls = 0
""" 钩子被调用的次数 """

type Data = Mapping[str, core.JSON]
type Check = Callable[[int, str, Data], bool]


def _target(who: int, data: Data) -> int:
    """
    行动的交互对象
    Keyword arguments:
    who -- 行动的角色id
    data -- 行动数据
    Return arguments:
    int -- 行动数据的 target；没有时为缓存里角色当前的交互对象
    """
    target = data.get(TARGET)
    if isinstance(target, int):
        return target
    return cache.character_data[who].target_character_id


def target_gone(who: int, behavior_id: str, data: Data) -> bool:
    """
    行动数据写明的交互对象已不在：不存在、已死亡，或是不在场的干员
    Keyword arguments:
    who -- 行动的角色id
    behavior_id -- 行为id
    data -- 行动数据
    Return arguments:
    bool -- 对象不在时为 True；行动数据没有 target 时为 False
    """
    target = data.get(TARGET)
    if not isinstance(target, int):
        return False
    target_data = cache.character_data.get(target)
    if target_data is None or target_data.dead:
        return True
    return target != 0 and target not in cache.npc_id_got


def premise_fails(who: int, behavior_id: str, data: Data) -> bool:
    """
    行动数据里的前提有一个不成立
    Keyword arguments:
    who -- 行动的角色id
    behavior_id -- 行为id
    data -- 行动数据
    Return arguments:
    bool -- 有前提不成立时为 True
    """
    premises = data.get(PREMISES) or ()
    assert isinstance(premises, tuple)
    return not all(
        handle_premise.handle_premise(str(premise), who) for premise in premises
    )


def child_stage_h(who: int, behavior_id: str, data: Data) -> bool:
    """
    幼年阶段的H闸：H类行为，而角色自己或交互对象处于幼年阶段
    Keyword arguments:
    who -- 行动的角色id
    behavior_id -- 行为id
    data -- 行动数据
    Return arguments:
    bool -- 闸关上时为 True
    """
    return child_stage_gate.is_h_behavior(behavior_id) and (
        child_stage_gate.is_child_stage(who)
        or child_stage_gate.is_child_stage(_target(who, data))
    )


def takes_virginity(who: int, behavior_id: str, data: Data) -> bool:
    """
    处女闸：干员对另一名干员做的行为会夺走对方仍有的处女素质；玩家做的行为是玩家自己选的，不受限
    Keyword arguments:
    who -- 行动的角色id
    behavior_id -- 行为id
    data -- 行动数据
    Return arguments:
    bool -- 闸关上时为 True
    """
    target = _target(who, data)
    if who == 0 or target in (0, who):
        return False
    behavior_config = game_config.config_behavior.get(behavior_id)
    target_data = cache.character_data.get(target)
    if behavior_config is None or target_data is None:
        return False
    return virgin_break_gate.takes_kept_virginity(
        behavior_config.tag.split("|"), target_data.talent
    )


GATES: tuple[tuple[str, Check], ...] = (
    ("target", target_gone),
    ("premises", premise_fails),
    ("child_stage", child_stage_h),
    ("virginity", takes_virginity),
)
""" 行动开始前依次检查的条件：(名字, 不成立时为 True 的函数) """


def _idle(act: core.Action, who: int, gate_name: str) -> core.Action:
    """
    把行动换成 1 分钟的发呆，缓存里的行为一起换；玩家的交互对象不变
    Keyword arguments:
    act -- 原来的行动
    who -- 行动的角色id
    gate_name -- 没过的那条检查
    Return arguments:
    Action -- 发呆的行动
    """
    character_data = cache.character_data[who]
    target = character_data.target_character_id
    child_stage_gate.reset_to_idle(who)
    if who == 0:
        character_data.target_character_id = target
    extra: dict[str, core.JSON] = {GATE: gate_name}
    if isinstance(act.action_data, Mapping) and MINUTES in act.action_data:
        extra[MINUTES] = 1
    data = actions.mirror(character_data.behavior, **extra)
    if act.action_id != actions.behave.name:
        return core.new_action(actions.behave, act.who, 1, data)
    return replace(act, duration=1, action_data=data)


def _time_stopped(act: core.Action) -> core.Action:
    """
    时停中玩家的行动：内核里 0 分钟，名义分钟数留在 minutes 里
    Keyword arguments:
    act -- 玩家的行动
    Return arguments:
    Action -- 0 分钟的行动
    """
    data = act.action_data
    assert isinstance(data, Mapping)
    nominal = data.get(MINUTES, act.duration)
    return replace(
        act,
        duration=0,
        action_data=MappingProxyType({**data, MINUTES: nominal}),
    )


@core.input_hook(core.start_action)
def gate(
    act: core.Action,
) -> tuple[core.Action] | core.Intercept[core.Effects]:
    """
    行动开始前检查它的条件，不成立的换成 1 分钟的发呆；时停中玩家的行动换成 0 分钟。
    解除时停（TIME_STOP_OFF）不换：它的结算关掉时停，缓存的游戏时间照名义分钟数前进，内核时钟要一起走
    Keyword arguments:
    act -- 要开始的行动
    Return arguments:
    tuple -- 交给内层的行动
    """
    global calls
    calls += 1
    data = act.action_data
    gated = (actions.behave.name, plan_queue.start_planned.name)
    if act.action_id not in gated or not isinstance(data, Mapping):
        return (act,)
    who = int(act.who)
    behavior_id = str(data.get("behavior_id", ""))
    for gate_name, closed in GATES:
        if closed(who, behavior_id, data):
            act = _idle(act, who, gate_name)
            break
    if (
        act.who == actions.PLAYER
        and cache.time_stop_mode
        and behavior_id != constant.Behavior.TIME_STOP_OFF
    ):
        act = _time_stopped(act)
    return (act,)
