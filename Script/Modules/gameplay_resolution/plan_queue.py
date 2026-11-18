"""
gameplay_resolution 的计划队列与打断：旧结算代码和内核之间的桥
================================================================
结算途中要让某个角色接着做的行动，不在当场开始，而是作为意图（intent.Intent）排进这个角色的队列
（存在缓存里，随存档保存）。
- plan_next 排一个行动；要求打断时，角色当前的行动在这一步结束，他马上来选。
- interrupt 只打断，不排行动：角色在自己的 ActionOver 里收尾，再按自己的选择接着做。
- 角色选行动时，PickNextAction 的输入钩子 queue_head 先看队首：有时交回队首的行动，只读不弹；
  行动开始时（starts.behave 的 begin）用 pop 弹出队首。
- 每一步唯一一次 ApplyEffects 之前，输入钩子 drain 补上这一步里排下的打断，以及在场角色的加入与移除，
  所以排下的打断总在同一步生效，不管事件或开始函数交回了什么。
除了角色自己的开始与 ActionOver，别的代码不写角色缓存里的行为，而是经这里排行动或打断。
"""

from collections.abc import Mapping, Sequence
from typing import cast

from Script.Core import cache_control
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, intent

FIELD_ROOTS = frozenset({"behavior", "sp_flag", "action_info", "work"})
""" Intent.fields 的路径可以用的根 """

type Queued = tuple[str, intent.Intent]
""" 队列里的一项：行动的种类与意图 """


_pending: list[core.Interrupt] = []
""" 这一步里排下、还没交给内核的打断 """
acting: str | None = None
""" 正在开始行动的角色键 """


def forget() -> None:
    """丢掉还没交给内核的打断，清掉正在开始行动的角色"""
    global acting
    _pending.clear()
    acting = None


@core.output_hook(core.reset)
def forget_on_reset(game: core.GameState) -> core.GameState:
    """
    kernel.Reset 的输出钩子：换了 GameState（读档、新游戏、改时钟）后，上一个状态里排下的打断作废
    Keyword arguments:
    game -- 新的 GameState
    Return arguments:
    GameState -- 原样交回
    """
    forget()
    return game


def _queue(who: int) -> list[Queued]:
    """
    角色在缓存里的队列，只读；没有时为空列表
    Keyword arguments:
    who -- 角色id
    Return arguments:
    list -- 队首在前
    """
    queue: list[Queued] = cache_control.cache.plan_queue.get(who, [])
    return queue


def _json(value: object) -> core.JSON:
    """
    检查并换成 JSON 原生的值，元组换成列表：开始时照着写进缓存的值和选行动时给的一样是列表
    （core.JSON 里没有列表，内核冻结 action_data 时才换成元组）
    Keyword arguments:
    value -- 值
    Return arguments:
    JSON -- 同一个值
    """
    if isinstance(value, list | tuple):
        return cast(core.JSON, [_json(item) for item in value])
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError(f"{value!r} has a key that is not a str")
        return {key: _json(item) for key, item in value.items()}
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise TypeError(f"{value!r} is not JSON")


def _fields(fields: Mapping[str, object]) -> dict[str, core.JSON]:
    """
    检查 Intent.fields：路径的根要在 FIELD_ROOTS 里，值要是 JSON
    Keyword arguments:
    fields -- 路径到值
    Return arguments:
    dict -- 路径到 JSON 值
    """
    checked: dict[str, core.JSON] = {}
    for path, value in fields.items():
        root, dot, name = path.partition(".")
        if root not in FIELD_ROOTS or not dot or not name:
            raise ValueError(f"Intent.fields 不能写 {path}")
        checked[path] = _json(value)
    return checked


def plan_next(
    who: int,
    behavior_id: str,
    minutes: int,
    *,
    kind: str = "Behavior",
    target: int | None = None,
    state: int | str | None = None,
    interrupt: bool = False,
    fields: Mapping[str, object] | None = None,
    args: Mapping[str, object] | None = None,
    move: intent.Move | None = None,
    say: str | None = None,
    premises: Sequence[str] = (),
) -> None:
    """
    给角色排下一个行动：角色下一次选行动时开始
    Keyword arguments:
    who -- 角色id
    behavior_id -- 行为id
    minutes -- 名义分钟数
    kind -- 行动的种类，action_id 为 gameplay_resolution.<kind>
    target -- 交互对象的角色id，None 时为自己
    state -- 开始时的角色状态，None 时为行为id
    interrupt -- 是否打断角色当前的行动，让他马上来选
    fields -- 开始时写在角色自己身上的值，路径（如 "behavior.move_target"）到 JSON 值
    args -- 本种类自己的参数
    move -- 开始时的移动
    say -- 开始时绘制的文本
    premises -- 开始时都要成立的前提id，由开始门检查
    """
    planned_intent = intent.Intent(
        behavior_id=behavior_id, minutes=int(minutes), queued=True
    )
    if target is not None:
        planned_intent["target"] = int(target)
    if state is not None:
        planned_intent["state"] = state
    if fields:
        planned_intent["fields"] = _fields(fields)
    if args:
        planned_intent["args"] = {
            key: _json(value) for key, value in args.items()
        }
    if move is not None:
        planned_intent["move"] = intent.Move(
            to=[str(part) for part in move["to"]], show=bool(move["show"])
        )
    if say is not None:
        planned_intent["say"] = say
    if premises:
        planned_intent["premises"] = list(premises)
    queues = cache_control.cache.plan_queue
    queues.setdefault(int(who), []).append((kind, planned_intent))
    if interrupt:
        _pending.append(core.Interrupt(str(who)))


def interrupt(who: int) -> None:
    """
    打断角色当前的行动：这一步的 ApplyEffects 让它在此刻结束，角色在自己的 ActionOver 里收尾后再选
    Keyword arguments:
    who -- 角色id
    """
    _pending.append(core.Interrupt(str(who)))


def plan_has(who: int, behavior_id: str) -> bool:
    """
    角色的队列里是否已经排着这个行动
    Keyword arguments:
    who -- 角色id
    behavior_id -- 行为id
    Return arguments:
    bool -- 排着时为真
    """
    return any(item["behavior_id"] == behavior_id for _, item in _queue(who))


def planned(who: int) -> list[intent.Intent]:
    """
    角色排着的行动的意图，队首在前（副本）
    Keyword arguments:
    who -- 角色id
    Return arguments:
    list -- 意图
    """
    return [intent.Intent(**item) for _, item in _queue(int(who))]


def pop(who: int) -> intent.Intent:
    """
    弹出角色的队首：行动开始时（begin）对 queued 的意图调用
    Keyword arguments:
    who -- 角色id
    Return arguments:
    Intent -- 弹出的意图
    """
    queues = cache_control.cache.plan_queue
    _, item = queues[int(who)].pop(0)
    if not queues[int(who)]:
        del queues[int(who)]
    return item


@core.input_hook(core.pick_next_action)
def queue_head(
    who: str,
) -> tuple[str] | core.Intercept[core.Action]:
    """
    角色选下一个行动：队列里有时答出队首的行动（不弹出，开始时才弹），队列空时原样交给内层
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Intercept -- 队首的行动；队列空时为原样交给内层的参数
    """
    queue = _queue(int(who))
    if not queue:
        return (who,)
    kind, head = queue[0]
    return core.Intercept(intent.behavior_action(int(who), head, kind))


@core.input_hook(core.start_action)
def note_actor(act: core.Action) -> tuple[core.Action]:
    """
    记下正在开始行动的角色：这一步里给他排的打断作废（他刚开始新行动）
    Keyword arguments:
    act -- 要开始的行动
    Return arguments:
    tuple -- 原样交给内层的参数
    """
    global acting
    acting = act.who
    return (act,)


@core.input_hook(core.apply_effects)
def drain(effects: core.Effects) -> tuple[core.Effects]:
    """
    每一步唯一一次套用效果之前，补上这一步里排下的打断，以及在场角色的加入与移除。
    不在内核里、这一步被移除或正在开始行动的角色，他的打断作废
    Keyword arguments:
    effects -- 这一步的效果
    Return arguments:
    tuple -- 补上之后的效果
    """
    global acting
    roster = roster_changes(effects)
    removed = {
        e.who
        for e in (*effects, *roster)
        if isinstance(e, core.RemoveCharacter)
    }
    known = core.state().characters
    extra: list[core.Interrupt] = []
    for item in _pending:
        if item.who not in known or item.who in removed or item.who == acting:
            continue
        if item not in effects and item not in extra:
            extra.append(item)
    _pending.clear()
    acting = None
    return ((*effects, *extra, *roster),)


def roster_changes(effects: core.Effects = ()) -> core.Effects:
    """
    缓存里在场的角色（actions.roster）与 state().characters 比出的加入与移除，effects 里已有的不再给
    Keyword arguments:
    effects -- 这一步已有的效果
    Return arguments:
    Effects -- 新来的角色的 AddCharacter，已不在场的角色的 RemoveCharacter
    """
    present = actions.roster()
    known = core.state().characters
    given = {
        e.who
        for e in effects
        if isinstance(e, core.AddCharacter | core.RemoveCharacter)
    }
    added = [
        core.AddCharacter(who)
        for who in present
        if who not in known and who not in given
    ]
    gone = [
        core.RemoveCharacter(who)
        for who in known
        if who not in present and who not in given
    ]
    return (*added, *gone)
