"""
gameplay_resolution 的开始门
============================
gate 是 StartAction 输入钩子，在 starts 的复查（recheck）之外。行动数据带 behavior_id 的行动都要过门：
玩家选出的、状态机选出的与计划队列排下的，一样检查。
- 玩家的行动带 judge（指令的判定名）时先判定：不能执行时换成发呆，失败时换成失败的行为。
- 再按 GATES 的顺序检查。第一道关上的闸把行动换成 1 分钟的发呆（通用种类 Behavior），干员的交互对象改回自己，
  没过的闸记在意图的 args 的 gate 里。门不写缓存：发呆由 starts.begin 写进去。
- 行动数据里的 target 是交互对象id。没有这个键时，幼年阶段与处女两道闸看缓存里角色当前的交互对象。
  premises 是前提id，行动开始时每个前提都要成立。
- 时停中玩家的行动在内核里是 0 分钟，时钟不走，名义分钟数留在意图的 minutes 里。
"""

from collections.abc import Callable, Mapping
from dataclasses import replace

from Script.Config import game_config
from Script.Core import cache_control, constant, game_type
from Script.Design import child_stage_gate, handle_premise, virgin_break_gate
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, intent

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

TARGET = "target"
""" 行动数据里交互对象id的键 """
PREMISES = "premises"
""" 行动数据里前提id元组的键 """
JUDGE = "judge"
""" 行动数据里玩家指令判定名的键 """
GATE = "gate"
""" 换成发呆的意图里，args 下记下没过的那条检查的键 """

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
    assert isinstance(premises, tuple | list)
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
    把行动换成 1 分钟的发呆；干员的交互对象改回自己，玩家的不变。
    来自队列的行动换上的发呆仍标着 queued，开始时照样弹出队首
    Keyword arguments:
    act -- 原来的行动
    who -- 行动的角色id
    gate_name -- 没过的那条检查
    Return arguments:
    Action -- 发呆的行动
    """
    idle = intent.Intent(
        behavior_id=constant.Behavior.SHARE_BLANKLY,
        minutes=1,
        state=constant.CharacterStatus.STATUS_ARDER,
        args={GATE: gate_name},
    )
    if who != 0:
        idle["target"] = who
    data = act.action_data
    if isinstance(data, Mapping) and data.get("queued"):
        idle["queued"] = True
    return replace(intent.behavior_action(who, idle), start=act.start)


def _judged(act: core.Action, who: int, data: Data) -> core.Action:
    """
    玩家指令的判定（handle_instruct._judged_behavior_id）：不能执行时换成发呆，失败时换成失败的行为
    Keyword arguments:
    act -- 玩家的行动
    who -- 行动的角色id
    data -- 行动数据
    Return arguments:
    Action -- 判定之后要开始的行动
    """
    from Script.System.Instruct_System import handle_instruct

    behavior_id = str(data["behavior_id"])
    judged = handle_instruct._judged_behavior_id(
        behavior_id, who, _target(who, data), str(data[JUDGE])
    )
    if judged is None:
        return _idle(act, who, JUDGE)
    rest = {key: value for key, value in data.items() if key != JUDGE}
    return replace(act, action_data={**rest, "behavior_id": judged})


@core.input_hook(core.start_action)
def gate(act: core.Action) -> tuple[core.Action]:
    """
    行动开始前先判定玩家的指令，再检查它的条件，不成立的换成 1 分钟的发呆；时停中玩家的行动换成 0 分钟。
    解除时停（TIME_STOP_OFF）不换：它的结算关掉时停，时钟照名义分钟数前进
    Keyword arguments:
    act -- 要开始的行动
    Return arguments:
    tuple -- 交给内层的行动
    """
    global calls
    calls += 1
    data = act.action_data
    if not isinstance(data, Mapping) or "behavior_id" not in data:
        return (act,)
    who = int(act.who)
    if who == 0 and JUDGE in data:
        act = _judged(act, who, data)
        data = act.action_data
        assert isinstance(data, Mapping)
    behavior_id = str(data["behavior_id"])
    for gate_name, closed in GATES:
        if closed(who, behavior_id, data):
            act = _idle(act, who, gate_name)
            break
    if (
        act.who == actions.PLAYER
        and cache.time_stop_mode
        and behavior_id != constant.Behavior.TIME_STOP_OFF
    ):
        act = replace(act, duration=0)
    return (act,)
