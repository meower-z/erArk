"""
gameplay_resolution 的计划队列
==============================
结算途中要让某个角色接着做的行动，不在当场开始，而是排进这个角色的队列（存在缓存里，随存档保存）。
PickNextAction 输入钩子排在 npc_action_choice 与 tk_ui 之外：角色下一次要选行动时，先答出队首。
- plan_next 排一个行动；给另一个角色排时可要求打断他当前的行动（Interrupt），让他马上来选。
- plan_has 查某个行动是否已经排上，供事件条件判断"还没排"。
- 干员的队首行动在它的 StartAction 里写进缓存并结算；玩家的队首行动交给玩家的行动结算（actions.behave）。
结算途中没法把 Interrupt 交回内核的旧代码，由这里的输出钩子在 StartAction、TimeElapse、PickNextAction 的结果里补上。
character_behavior 里玩家行动前的前置结算、隐奸流程与玩家的状态结算经这里的同名函数调用今天的代码。
"""

import datetime
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from Script.Core import cache_control, game_type
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions
from Script.Modules.tk_ui import player_hook


@dataclass(frozen=True)
class Planned:
    """排进队列的一个行动"""

    behavior_id: str
    """ 行为id """
    duration: int
    """ 名义分钟数 """
    target: int | None = None
    """ 交互对象的角色id，None 时不改 """
    state: int | str | None = None
    """ 开始时的角色状态，None 时为行为id """
    data: dict[str, object] = field(default_factory=dict)
    """ 开始时写进行为的字段（键为 Behavior 的属性名） """
    kernel_action: str | None = None
    """ 不是行为而是 gameplay_resolution 的另一个内核行动时，它的行动id """
    premises: tuple[str, ...] = ()
    """ 开始时都要成立的前提id，由开始门检查 """


calls = 0
""" 队首钩子被调用的次数 """
answered = 0
""" 队首钩子答出队首的次数 """

_pending: list[core.Interrupt] = []
""" 结算途中排下、还没交回内核的打断 """
_acting: str | None = None
""" 正在开始行动的角色键 """
_starting: dict[str, Planned] = {}
""" 选出、还没开始的干员队首行动 """


def forget() -> None:
    """读档、新周目或内核出错后，丢掉结算途中排下、还没交回内核的打断，丢掉选出、还没开始的干员队首行动，并清掉正在开始行动的角色"""
    global _acting
    _pending.clear()
    _starting.clear()
    _acting = None


def _queues() -> dict[int, list[Planned]]:
    """
    缓存里的计划队列，没有时建一个空的（旧存档里没有）
    Return arguments:
    dict -- 角色id到排队行动的列表
    """
    queues: dict[int, list[Planned]] = vars(cache_control.cache).setdefault(
        "plan_queue", {}
    )
    return queues


def plan_next(
    who: int | str,
    behavior_id: str,
    duration: int,
    *,
    target: int | None = None,
    state: int | str | None = None,
    data: Mapping[str, object] | None = None,
    premises: tuple[str, ...] = (),
    interrupt: bool = False,
) -> core.Interrupt | None:
    """
    给角色排下一个行动：角色下一次选行动时开始
    Keyword arguments:
    who -- 角色id（缓存的 int 或内核的 str）
    behavior_id -- 行为id
    duration -- 名义分钟数
    target -- 交互对象的角色id，None 时开始时不改
    state -- 开始时的角色状态，None 时为行为id
    data -- 开始时写进行为的字段（键为 Behavior 的属性名）
    premises -- 开始时都要成立的前提id；不成立时开始门把行动换成空闲
    interrupt -- 是否打断角色当前的行动，让他马上来选；玩家从不被打断
    Return arguments:
    Interrupt | None -- 要打断时交回内核的项；内核没在跑、角色是玩家、不在场或正在开始行动的就是他时为 None。
        调用方能交回效果时把它放进效果里；不能时这里的输出钩子会补上
    """
    item = Planned(
        behavior_id,
        int(duration),
        target,
        state,
        dict(data or {}),
        premises=tuple(premises),
    )
    return _append(int(who), item, interrupt)


def _append(
    character_id: int, item: Planned, interrupt: bool
) -> core.Interrupt | None:
    """
    排进角色的队列；要打断时记下打断
    Keyword arguments:
    character_id -- 角色id
    item -- 排队的行动
    interrupt -- 是否打断角色当前的行动
    Return arguments:
    Interrupt | None -- 同 plan_next
    """
    _queues().setdefault(character_id, []).append(item)
    # 玩家从不被打断：打断会让下一个 behave 换掉回合而不跑回合末的结算，排给玩家的行动就是他的下一个行动
    if not interrupt or character_id == 0 or not player_hook.running():
        return None
    key = str(character_id)
    if key == _acting or key not in core.state().characters:
        return None
    interrupt_item = core.Interrupt(key)
    if interrupt_item not in _pending:
        _pending.append(interrupt_item)
    return interrupt_item


def plan_action(
    who: int | str, action_id: str, duration: int, *, interrupt: bool = False
) -> core.Interrupt | None:
    """
    给干员排一个 gameplay_resolution 自己的内核行动（不是行为），干员下一次选行动时开始
    Keyword arguments:
    who -- 角色id
    action_id -- 用 core.action 注册的行动id
    duration -- 分钟数
    interrupt -- 是否打断角色当前的行动，让他马上来选
    Return arguments:
    Interrupt | None -- 同 plan_next
    """
    item = Planned(action_id, int(duration), kernel_action=action_id)
    return _append(int(who), item, interrupt)


def plan_has(who: int | str, behavior_id: str) -> bool:
    """
    角色的队列里是否已经排着这个行动
    Keyword arguments:
    who -- 角色id
    behavior_id -- 行为id
    Return arguments:
    bool -- 排着时为真
    """
    queue = _queues().get(int(who), [])
    return any(p.behavior_id == behavior_id for p in queue)


def planned(who: int | str) -> tuple[Planned, ...]:
    """
    角色排着的行动，队首在前
    Keyword arguments:
    who -- 角色id
    Return arguments:
    tuple -- 排着的行动
    """
    return tuple(_queues().get(int(who), []))


def _begin(character_id: int, item: Planned) -> game_type.Behavior:
    """
    把排队的行动写进缓存，成为角色当前的行为，从此刻开始
    Keyword arguments:
    character_id -- 角色id
    item -- 排队的行动
    Return arguments:
    Behavior -- 写进去的行为
    """
    cache = cache_control.cache
    character_data = cache.character_data[character_id]
    behavior = game_type.Behavior()
    behavior.behavior_id = item.behavior_id
    behavior.duration = item.duration
    behavior.start_time = cache.game_time.replace(second=0, microsecond=0)
    behavior.move_src = character_data.behavior.move_src
    for key, value in item.data.items():
        if not hasattr(behavior, key):
            raise KeyError(f"行为没有字段 {key}")
        setattr(behavior, key, value)
    character_data.behavior = behavior
    character_data.state = (
        item.behavior_id if item.state is None else item.state
    )
    if item.target is not None:
        character_data.target_character_id = item.target
    return behavior


def _clock_time(clock: int) -> datetime.datetime:
    """
    内核时钟的分钟换成游戏时间。回合里缓存的游戏时间已是玩家行动的结束，干员的行动在内核时钟上开始，可能更早
    Keyword arguments:
    clock -- 内核时钟的分钟数
    Return arguments:
    datetime -- 那一分钟的游戏时间
    """
    now = cache_control.cache.game_time.replace(second=0, microsecond=0)
    return now - datetime.timedelta(minutes=actions.minutes(now) - clock)


@core.action("gameplay_resolution.Planned")
def start_planned(act: core.Action) -> core.Effects:
    """
    干员排队行动的开始：写进缓存并结算行为与事件。行为的开始时间是内核里这个行动的开始，不是缓存的游戏时间
    Keyword arguments:
    act -- 开始的行动
    Return arguments:
    Effects -- 空（打断由输出钩子补上）
    """
    from Script.Design import character_behavior

    item = _starting.pop(act.who)
    character_id = int(act.who)
    behavior = _begin(character_id, item)
    behavior.start_time = _clock_time(act.start)
    character_behavior.judge_character_status(character_id)
    return ()


@core.input_hook(core.pick_next_action)
def queue_head(
    who: str,
) -> tuple[str] | core.Intercept[tuple[core.Action, core.Effects]]:
    """
    角色选下一个行动：队列里有时答出队首，干员至少 1 分钟；队列空时原样交给内层。
    玩家的队列空而还在寻路途中时，先排上下一段
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Intercept -- 队首的行动；队列空时为原样交给内层的参数
    """
    global calls, answered
    calls += 1
    if who == actions.PLAYER and not _queues().get(0):
        from Script.Design import character_move

        character_move.continue_player_route()
    queue = _queues().get(int(who))
    if not queue:
        return (who,)
    answered += 1
    item = queue.pop(0)
    _drop_pending(who)
    if item.kernel_action is not None:
        act = core.new_action(
            core.Start(item.kernel_action),
            who,
            max(item.duration, 1),
            MappingProxyType({}),
        )
        return core.Intercept((act, ()))
    if who == actions.PLAYER:
        behavior = _begin(0, item)
        act = core.new_action(
            actions.behave,
            who,
            max(item.duration, 0),
            actions.mirror(
                behavior, minutes=item.duration, **_preconditions(item)
            ),
        )
        return core.Intercept((act, ()))
    _starting[who] = item
    act = core.new_action(
        start_planned,
        who,
        max(item.duration, 1),
        MappingProxyType(
            {
                "behavior_id": item.behavior_id,
                "duration": item.duration,
                **_preconditions(item),
            }
        ),
    )
    return core.Intercept((act, ()))


def _preconditions(item: Planned) -> dict[str, core.JSON]:
    """
    开始门要检查的前提，写进行动的数据：target（交互对象）与 premises（前提id）
    Keyword arguments:
    item -- 排队的行动
    Return arguments:
    dict -- 有的才写
    """
    found: dict[str, core.JSON] = {}
    if item.target is not None:
        found["target"] = item.target
    if item.premises:
        found["premises"] = item.premises
    return found


def _drop_pending(who: str) -> None:
    """
    角色的行动已经结束、要开始下一个时，他排着的打断作废
    Keyword arguments:
    who -- 角色键
    """
    _pending[:] = [i for i in _pending if i.who != who]


def _flushed(effects: core.Effects) -> core.Effects:
    """
    把结算途中排下的打断补进效果
    Keyword arguments:
    effects -- 内层交回的效果
    Return arguments:
    Effects -- 补上打断后的效果
    """
    if not _pending:
        return effects
    extra = tuple(i for i in _pending if i not in effects)
    _pending.clear()
    return (*effects, *extra)


@core.input_hook(core.start_action)
def note_actor(act: core.Action) -> tuple[core.Action]:
    """
    记下正在开始行动的角色：结算途中给他自己排的行动不打断他
    Keyword arguments:
    act -- 要开始的行动
    Return arguments:
    tuple -- 原样交给内层的参数
    """
    global _acting
    _acting = act.who
    return (act,)


@core.output_hook(core.start_action)
def flush_after_start(effects: core.Effects) -> core.Effects:
    """
    行动开始后补上打断
    Keyword arguments:
    effects -- 开始结算的效果
    Return arguments:
    Effects -- 补上打断后的效果
    """
    global _acting
    _acting = None
    return _flushed(effects)


@core.output_hook(core.time_elapse)
def flush_after_elapse(
    result: tuple[int, core.Effects],
) -> tuple[int, core.Effects]:
    """
    时间流逝后补上打断
    Keyword arguments:
    result -- 新时钟与效果
    Return arguments:
    tuple -- 新时钟与补上打断后的效果
    """
    end, effects = result
    return (end, _flushed(effects))


@core.output_hook(core.pick_next_action)
def flush_after_pick(
    result: tuple[core.Action, core.Effects],
) -> tuple[core.Action, core.Effects]:
    """
    选行动后补上打断
    Keyword arguments:
    result -- 选出的行动与效果
    Return arguments:
    tuple -- 选出的行动与补上打断后的效果
    """
    act, effects = result
    _drop_pending(act.who)
    return (act, _flushed(effects))


def judge_before_pl_behavior() -> None:
    """玩家行动前的前置结算（今天的 character_behavior.judge_before_pl_behavior）"""
    from Script.Design import character_behavior

    character_behavior.judge_before_pl_behavior()


def judge_character_status(character_id: int) -> int:
    """
    结算角色状态与事件（今天的 character_behavior.judge_character_status）
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 结算是否成功
    """
    from Script.Design import character_behavior

    return character_behavior.judge_character_status(character_id)


def handle_hidden_sex_flow() -> None:
    """隐奸被察觉的结算（今天的 hidden_sex_panel.handle_hidden_sex_flow）"""
    from Script.System.Sex_System import hidden_sex_panel

    hidden_sex_panel.handle_hidden_sex_flow()
