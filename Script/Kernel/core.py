"""
事件内核
========
游戏状态 GameState 不可变，含时钟（分钟）、角色表与全局数据。每个角色同时只有一个行动。
step() 每次结算一件事：一个触发的事件，否则是行动已结束、种类登记了结束函数的第一个角色的收尾，
否则是行动已结束的第一个角色（同一步里选下一个行动并开始），
否则由 kernel.TimeElapse 推进时钟。插件模块按 load() 的顺序给钩子点挂输入钩子与输出钩子。
行动、事件与钩子返回的效果（Effects）由 kernel.ApplyEffects 应用到状态上。
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from types import MappingProxyType, ModuleType
from typing import Any, Literal, NoReturn, cast

type JSON = (
    None | bool | int | float | str | tuple[JSON, ...] | Mapping[str, JSON]
)
type Hooks = dict[tuple[str, str], list[Callable[..., Any]]]


@dataclass(frozen=True)
class Action:
    """
    一个角色的行动
    who 为角色键，action_id 为行动名，action_data 为行动的数据，
    start 为开始的分钟，duration 为持续的分钟数
    """

    who: str
    action_id: str
    action_data: JSON
    start: int
    duration: int


@dataclass(frozen=True)
class Character:
    """角色：action 为当前的行动，data 为角色的数据"""

    action: Action
    data: Mapping[str, JSON]


@dataclass(frozen=True)
class GameState:
    """
    游戏状态：clock 为当前分钟，characters 为角色键到角色的映射，data 为全局数据
    characters 的插入顺序就是花名册顺序
    """

    clock: int
    characters: Mapping[str, Character]
    data: Mapping[str, JSON]


@dataclass(frozen=True)
class StateChange:
    """
    直接改一项数据的效果：把 who 的 key 从 old 改为 new，who 为 None 时改全局数据
    old 必须等于当前值，key 不能归某条规则所有
    """

    who: str | None  # None: a global entry
    key: str
    old: JSON
    new: JSON


@dataclass(frozen=True)
class Change:
    """
    经 key 的所有者规则（rule）应用的效果，who 为 None 时作用于全局数据
    op、operand 与 reason 由那条规则解释
    """

    who: str | None
    key: str
    op: str
    operand: JSON
    reason: JSON = None


@dataclass(frozen=True)
class Intercept[R]:
    """输入钩子返回它时，跳过本体与更里层的钩子，value 代替本体的结果交给外层的输出钩子"""

    value: R


@dataclass(frozen=True)
class AddCharacter:
    """
    加入角色的效果：who 为角色键，data 为初始数据
    新角色的行动是从当前分钟开始、持续 0 分钟的 kernel.Idle
    """

    who: str
    data: Mapping[str, JSON] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True)
class RemoveCharacter:
    """移除角色 who 的效果"""

    who: str


type Phase = Literal["idle", "pick", "settle"]


@dataclass
class _RunContext:
    state: GameState
    boundary: GameState
    plugins: tuple[str, ...] = ()
    phase: Phase = "idle"
    dead: list[tuple[object, ...]] = field(default_factory=list)
    sub: int = 0
    unsettled: int = 0


class DroppedChanges(RuntimeError):
    """一步里有钩子返回的效果被丢掉、没有进入这一步的结果时抛出"""

    pass


class _PickAborted(BaseException):
    pass


class EventCycle(RuntimeError):
    """两次行动开始或时间流逝之间结算的事件与收尾步数超过 CYCLE_LIMIT 时抛出"""

    pass


CYCLE_LIMIT = 2000


_EMPTY = GameState(0, MappingProxyType({}), MappingProxyType({}))
_context = _RunContext(_EMPTY, _EMPTY)
_bodies: dict[str, Callable[..., Any]] = {}
_inputs: Hooks = {}
_outputs: Hooks = {}
_hook_only: set[str] = set()
_actions: set[str] = set()


def _send(name: str, args: tuple[object, ...]) -> object:
    entered: list[str] = []
    for module in reversed(_context.plugins):
        for hook in reversed(_inputs.get((name, module), [])):
            args = hook(*args)
            if isinstance(args, Intercept):
                return _outputs_of(entered, name, args.value)
        entered.append(module)
    return _outputs_of(entered, name, _bodies[name](*args))


def _outputs_of(entered: list[str], name: str, result: object) -> object:
    result = _tracked(result)
    for module in reversed(entered):
        for hook in _outputs.get((name, module), []):
            result = _tracked(hook(result))
    return result


class Changelist(tuple["Effect", ...]):
    """钩子返回的效果元组：没有标记为已结算就被回收时，其中的效果记作被丢掉，由这一步检查"""

    def __del__(self) -> None:
        """被回收时，没有已结算的标记就把自己的效果记进这一步被丢掉的列表"""
        if not self.__dict__.get("settled"):
            _context.dead.append(tuple(self))


def _is_effect(e: object) -> bool:
    return isinstance(
        e,
        StateChange
        | Change
        | Interrupt
        | AddCharacter
        | RemoveCharacter
        | Notice,
    )


def _tracked(result: object) -> object:
    if not isinstance(result, tuple) or isinstance(result, Changelist):
        return result
    if result and all(_is_effect(e) for e in result):
        return Changelist(result)
    return tuple(_tracked(part) for part in result)


def _items(result: object) -> list[object]:
    if _is_effect(result):
        return [result]
    if isinstance(result, Changelist):
        result.__dict__["settled"] = True
    if isinstance(result, tuple):
        return [e for part in result for e in _items(part)]
    return []


@dataclass(frozen=True)
class HookOnly[*Ts, R]:
    """钩子点的句柄，name 为钩子点名：句柄本身不能调用，钩子点由内核循环调用，插件给它挂钩子"""

    name: str


@dataclass(frozen=True)
class Interrupt:
    """打断角色 who 当前行动的效果：行动在当前分钟结束，不晚于原定的结束"""

    who: str


@dataclass(frozen=True)
class Notice[*Ts]:
    """通知的效果：效果应用之后，内核以 args 调用钩子点 port"""

    port: HookOnly[*Ts, None]
    args: tuple[*Ts]


type Effect = (
    StateChange
    | Change
    | Interrupt
    | AddCharacter
    | RemoveCharacter
    | Notice[*tuple[Any, ...]]
)
type Effects = tuple[Effect, ...]


class Export[*Ts, R](HookOnly[*Ts, R]):
    """可以直接调用的钩子点句柄：调用时依次经过输入钩子、本体与输出钩子"""

    def __call__(self, *args: *Ts) -> R:
        """
        经各模块的钩子调用这个钩子点，钩子点登记为只由内核循环调用时报错
        Keyword arguments:
        args -- 调用参数
        Return arguments:
        R -- 经输出钩子处理后的结果
        """
        if self.name in _hook_only:
            raise RuntimeError(f"{self.name} is called only by the kernel loop")
        return cast(R, _send(self.name, tuple(args)))


def export[*Ts, R](
    name: str,
) -> Callable[[Callable[[*Ts], R]], Export[*Ts, R]]:
    """
    装饰器：把函数登记为钩子点 name 的本体，返回可以直接调用的句柄 Export
    Keyword arguments:
    name -- 钩子点名
    Return arguments:
    Callable -- 装饰器
    """

    def register(fn: Callable[[*Ts], R]) -> Export[*Ts, R]:
        _bodies[name] = fn
        return Export(name)

    return register


def hook_only[*Ts, R](
    name: str,
) -> Callable[[Callable[[*Ts], R]], HookOnly[*Ts, R]]:
    """
    装饰器：把函数登记为钩子点 name 的本体，这个钩子点只由内核循环调用，返回句柄 HookOnly
    Keyword arguments:
    name -- 钩子点名
    Return arguments:
    Callable -- 装饰器
    """

    def register(fn: Callable[[*Ts], R]) -> HookOnly[*Ts, R]:
        _bodies[name] = fn
        _hook_only.add(name)
        return HookOnly(name)

    return register


def _loop_calls[*Ts, R](fn: HookOnly[*Ts, R], *args: *Ts) -> R:
    return cast(R, _send(fn.name, tuple(args)))


type InputHook[*Ts, R] = Callable[[*Ts], tuple[*Ts] | Intercept[R]]
type OutputHook[R] = Callable[[R], R]


def input_hook[*Ts, R](
    target: HookOnly[*Ts, R],
) -> Callable[[InputHook[*Ts, R]], InputHook[*Ts, R]]:
    """
    装饰器：把函数登记为 target 的输入钩子，钩子属于函数所在的模块
    调用 target 时，各模块的输入钩子按加载顺序从后往前运行，同一模块内后登记的先运行
    输入钩子收到参数，返回新的参数元组；返回 Intercept 时跳过本体与更里层的钩子
    Keyword arguments:
    target -- 钩子点的句柄
    Return arguments:
    Callable -- 装饰器
    """
    return lambda fn: _hook(_inputs, target.name, fn)


def output_hook[*Ts, R](
    target: HookOnly[*Ts, R],
) -> Callable[[OutputHook[R]], OutputHook[R]]:
    """
    装饰器：把函数登记为 target 的输出钩子，钩子属于函数所在的模块
    调用 target 时，结果从里往外经过输入一侧已走过的模块：先加载的先运行，同一模块内按登记顺序
    输出钩子收到结果，返回新的结果
    Keyword arguments:
    target -- 钩子点的句柄
    Return arguments:
    Callable -- 装饰器
    """
    return lambda fn: _hook(_outputs, target.name, fn)


def _hook[F: Callable[..., Any]](hooks: Hooks, name: str, fn: F) -> F:
    hooks.setdefault((name, fn.__module__), []).append(fn)
    return fn


def state() -> GameState:
    """
    这一步开始时的游戏状态，这一步里的改动到这一步结束才看得到
    Reset 钩子运行时是换入的状态
    Return arguments:
    GameState -- 游戏状态
    """
    return _context.boundary


def instant() -> tuple[int, int]:
    """
    当前时刻
    Return arguments:
    tuple -- (分钟, 这一分钟里的第几步)
    """
    return (_context.boundary.clock, _context.sub)


def in_settlement() -> bool:
    """
    是否在结算阶段：一步的结算部分或 reset_state 运行中
    Return arguments:
    bool -- 在结算阶段时为 True
    """
    return _context.phase == "settle"


def _frozen(value: JSON) -> JSON:
    if isinstance(value, Mapping):
        return _frozen_data(value)
    if isinstance(value, tuple | list):
        return tuple(_frozen(item) for item in value)
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise TypeError(f"{value!r} is not JSON")


def _frozen_data(data: Mapping[str, JSON]) -> Mapping[str, JSON]:
    for key in data:
        if not isinstance(key, str):
            raise TypeError(f"JSON key {key!r} is not a str")
    return MappingProxyType({key: _frozen(item) for key, item in data.items()})


def _frozen_action(act: Action) -> Action:
    return replace(act, action_data=_frozen(act.action_data))


def _with(game: GameState, who: str, **parts: Any) -> GameState:
    doer = replace(game.characters[who], **parts)
    characters = {**game.characters, who: doer}
    return replace(game, characters=MappingProxyType(characters))


def _end(act: Action) -> int:
    return act.start + act.duration


class Start(HookOnly[Action, Effects]):
    """行动的句柄：钩子点的参数是行动，结果是行动开始时的效果"""

    pass


def action(name: str) -> Callable[[Callable[[Action], Effects]], Start]:
    """
    装饰器：把函数登记为行动 name 的开始函数，返回行动的句柄 Start
    开始函数收到的行动的 action_id 不是 name 时报错
    Keyword arguments:
    name -- 行动名
    Return arguments:
    Callable -- 装饰器
    """

    def register(fn: Callable[[Action], Effects]) -> Start:
        def checked(act: Action) -> Effects:
            if act.action_id != name:
                raise RuntimeError(f"{name} got an action of {act.action_id}")
            return fn(act)

        hook_only(name)(checked)
        _actions.add(name)
        return Start(name)

    return register


def new_action(fn: Start, who: str, duration: int, data: JSON = None) -> Action:
    """
    建一个从当前分钟开始的行动
    Keyword arguments:
    fn -- 行动的句柄
    who -- 角色键
    duration -- 持续的分钟数
    data -- 行动的数据
    Return arguments:
    Action -- 新行动
    """
    return Action(who, fn.name, data, _context.state.clock, duration)


class End(HookOnly[Action, Effects]):
    """行动结束函数的句柄：参数是结束的行动，结果是收尾的效果"""

    pass


_ends: set[str] = set()


def action_end(start: Start) -> Callable[[Callable[[Action], Effects]], End]:
    """
    装饰器：把函数登记为行动 start 的结束函数（钩子点 "<行动名>.end"）
    行动用完时间（结束或被打断）后，内核在这一分钟的事件之后、任何角色选行动之前运行它一次
    行动没有登记或已有结束函数时报错
    Keyword arguments:
    start -- 行动的句柄
    Return arguments:
    Callable -- 装饰器
    """

    def register(fn: Callable[[Action], Effects]) -> End:
        if start.name not in _actions:
            raise RuntimeError(f"{start.name} is not a registered action")
        if start.name in _ends:
            raise RuntimeError(f"{start.name} already has an end")
        hook_only(f"{start.name}.end")(fn)
        _ends.add(start.name)
        return End(f"{start.name}.end")

    return register


def has_end(act: Action) -> bool:
    """
    这个行动的种类是否登记了结束函数
    Keyword arguments:
    act -- 行动
    Return arguments:
    bool -- 登记了时为 True
    """
    return act.action_id in _ends


@action("kernel.Idle")
def idle(act: Action) -> Effects:
    """
    kernel.Idle 行动的开始：什么也不做
    Keyword arguments:
    act -- 行动
    Return arguments:
    Effects -- 空
    """
    return ()


@hook_only("kernel.PickNextAction")
def pick_next_action(who: str) -> Action:
    """
    钩子点 kernel.PickNextAction：给行动已结束的角色选下一个行动
    本体选持续 1 分钟的 kernel.Idle，插件用钩子换掉
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Action -- 选出的行动
    """
    return new_action(idle, who, 1)


@hook_only("kernel.StartAction")
def start_action(act: Action) -> Effects:
    """
    钩子点 kernel.StartAction：开始一个行动
    行动的开始改为当前分钟，数据冻结后写进角色，再运行这个行动的开始函数。行动没有登记时报错
    Keyword arguments:
    act -- 要开始的行动
    Return arguments:
    Effects -- 开始函数返回的效果
    """
    if act.action_id not in _actions:
        raise RuntimeError(f"{act.action_id} is not a registered action")
    act = _frozen_action(replace(act, start=_context.state.clock))
    _context.state = _with(_context.state, act.who, action=act)
    return cast(Effects, _send(act.action_id, (act,)))


@hook_only("kernel.EndAction")
def end_action(act: Action) -> Effects:
    """
    钩子点 kernel.EndAction：行动结束时调用这个行动登记的结束函数，插件可以在这里钩住所有行动的结束
    Keyword arguments:
    act -- 结束的行动，被打断时 duration 已缩短到打断的分钟
    Return arguments:
    Effects -- 结束函数返回的效果
    """
    return cast(Effects, _send(f"{act.action_id}.end", (act,)))


@hook_only("kernel.TimeElapse")
def time_elapse(start: int, end: int) -> tuple[int, Effects]:
    """
    钩子点 kernel.TimeElapse：没有事件、也没有角色要选行动时推进时间
    本体直接走到 end，不产生效果
    Keyword arguments:
    start -- 当前分钟
    end -- 最早结束的行动的结束分钟
    Return arguments:
    tuple -- (推进后的分钟, 推进中产生的效果)
    """
    return (end, ())


type Rule = Callable[[GameState, Change], GameState]
type Data = Mapping[str, JSON]
_owners: dict[str, str] = {}


def rule(key: str) -> Callable[[Rule], HookOnly[GameState, Change, GameState]]:
    """
    装饰器：把函数登记为数据项 key 的所有者规则，规则收到状态与 Change，返回新状态
    每个 key 只归一个模块，另一个模块再登记时报错。装饰后得到钩子点 "apply <key>" 的句柄
    Keyword arguments:
    key -- 数据项名
    Return arguments:
    Callable -- 装饰器
    """

    def register(fn: Rule) -> HookOnly[GameState, Change, GameState]:
        if _owners.setdefault(key, fn.__module__) != fn.__module__:
            raise RuntimeError(f"{key} is owned by {_owners[key]}")
        return hook_only(f"apply {key}")(fn)

    return register


def _character(game: GameState, who: str) -> Character:
    if who not in game.characters:
        raise RuntimeError(f"{who} is not in the game")
    return game.characters[who]


def _with_characters(
    game: GameState, characters: Mapping[str, Character]
) -> GameState:
    return replace(game, characters=MappingProxyType(dict(characters)))


def _data_of(game: GameState, who: str | None) -> Data:
    return game.data if who is None else game.characters[who].data


def _with_data(game: GameState, who: str | None, data: Data) -> GameState:
    if who is None:
        return replace(game, data=_frozen_data(data))
    return _with(game, who, data=_frozen_data(data))


def value(game: GameState, who: str | None, key: str) -> JSON:
    """
    读一项数据
    Keyword arguments:
    game -- 游戏状态
    who -- 角色键，None 为全局数据
    key -- 数据项名
    Return arguments:
    JSON -- 数据值，没有这一项时为 None
    """
    return _data_of(game, who).get(key)


def with_value(
    game: GameState, who: str | None, key: str, new: JSON
) -> GameState:
    """
    返回改了一项数据的新状态，数据冻结后存入
    Keyword arguments:
    game -- 游戏状态
    who -- 角色键，None 为全局数据
    key -- 数据项名
    new -- 新值
    Return arguments:
    GameState -- 新状态
    """
    return _with_data(game, who, {**_data_of(game, who), key: new})


def _round(game: GameState, effects: Effects) -> GameState:
    for e in effects:
        if isinstance(e, StateChange):
            if e.key in _owners:
                raise RuntimeError(f"{e.key} changes only by its owner's rule")
            if value(game, e.who, e.key) != e.old:
                raise RuntimeError(
                    f"{e} does not follow {value(game, e.who, e.key)!r}"
                )
            game = with_value(game, e.who, e.key, e.new)
        elif isinstance(e, Change):
            if e.key not in _owners:
                raise RuntimeError(f"{e.key} has no owner's rule")
            new = _send(f"apply {e.key}", (game, e))
            if not isinstance(new, GameState):
                raise RuntimeError(f"{e.key}'s rule returned {new!r}")
            game = new
        elif isinstance(e, Interrupt):
            act = _character(game, e.who).action
            end = min(act.duration, game.clock - act.start)
            game = _with(game, e.who, action=replace(act, duration=end))
        elif isinstance(e, AddCharacter):
            if e.who in game.characters:
                raise RuntimeError(f"{e.who} is already in the game")
            act = Action(e.who, idle.name, None, game.clock, 0)
            added = Character(act, _frozen_data(e.data))
            game = _with_characters(game, {**game.characters, e.who: added})
        elif isinstance(e, RemoveCharacter):
            _character(game, e.who)
            kept = {k: c for k, c in game.characters.items() if k != e.who}
            game = _with_characters(game, kept)
    return game


def preview(game: GameState, effects: Effects) -> GameState:
    """
    算出效果应用后的状态，不改内核的状态，也不发通知
    Keyword arguments:
    game -- 起点状态
    effects -- 效果
    Return arguments:
    GameState -- 应用后的状态
    """
    return _round(game, effects)


@hook_only("kernel.ApplyEffects")
def apply_effects(effects: Effects) -> bool:
    """
    钩子点 kernel.ApplyEffects：把效果应用到内核当前的状态上，再依次发出其中的通知
    Keyword arguments:
    effects -- 效果
    Return arguments:
    bool -- 本体返回 True
    """
    _context.state = _round(_context.state, effects)
    for e in effects:
        if isinstance(e, Notice):
            _loop_calls(e.port, *e.args)
    return True


def _frozen_game(game: GameState) -> GameState:
    characters = {
        who: Character(_frozen_action(c.action), _frozen_data(c.data))
        for who, c in game.characters.items()
    }
    return GameState(
        game.clock, MappingProxyType(characters), _frozen_data(game.data)
    )


def _checked(game: GameState) -> GameState:
    if not isinstance(game, GameState) or type(game.clock) is not int:
        raise RuntimeError(f"{game!r} is not a GameState with an int clock")
    for who, c in game.characters.items():
        act = c.action
        if not isinstance(who, str) or act.who != who:
            raise RuntimeError(f"{who!r} holds an action of {act.who!r}")
        if act.action_id not in _actions:
            raise RuntimeError(f"{act.action_id} is not a registered action")
        if type(act.start) is not int or type(act.duration) is not int:
            raise RuntimeError(
                f"{who}'s action has a non-int start or duration"
            )
        if act.duration < 0:
            raise RuntimeError(f"{who}'s action has a negative duration")
    return _frozen_game(game)


@hook_only("kernel.Reset")
def reset(new: GameState, why: Mapping[str, JSON]) -> GameState:
    """
    钩子点 kernel.Reset：换入整个游戏状态时修整换入的状态，本体原样返回
    Keyword arguments:
    new -- 换入的状态
    why -- 换入的原因
    Return arguments:
    GameState -- 修整后的状态
    """
    return new


def reset_state(
    new: GameState, why: Mapping[str, JSON] = MappingProxyType({})
) -> None:
    """
    换掉整个游戏状态（读档、新周目、新游戏），结算中调用时报错
    Reset 钩子运行时，state() 与它的时钟就是换入的状态。结果经检查并冻结后成为当前状态，这一分钟的步数归 0
    出错时（包括钩子改了时钟）恢复原来的状态并抛出。在选行动时调用时，这一步就此结束
    Keyword arguments:
    new -- 换入的状态
    why -- 换入的原因，交给 Reset 钩子
    """
    if _context.phase == "settle":
        raise RuntimeError("reset_state is forbidden during settlement")
    in_pick, _context.phase = _context.phase == "pick", "settle"
    before = _context.state, _context.boundary
    try:
        incoming = _checked(new)
        # Reset hooks read the incoming state and its clock through state()
        _context.state = _context.boundary = incoming
        game = _checked(_loop_calls(reset, incoming, _frozen_data(why)))
        if game.clock != incoming.clock:
            raise RuntimeError("a Reset hook changed the clock")
    except BaseException:
        _context.state, _context.boundary = before
        raise
    finally:
        _context.phase = "pick" if in_pick else "idle"
    _context.state = _context.boundary = game
    _context.sub = 0
    _context.unsettled = 0
    if in_pick:
        # A BaseException passes the plugins' `except Exception` up to step()
        raise _PickAborted


def _resolve[*Ts, R](fn: HookOnly[*Ts, R], *args: *Ts) -> R:
    _context.dead = []
    result = _loop_calls(fn, *args)
    final = {id(e) for e in _items(result)}
    for items in _context.dead:
        for e in items:
            if id(e) not in final:
                raise DroppedChanges(f"{e} was returned and then dropped")
    return result


class Event[D](HookOnly[D, Effects]):
    """事件的句柄：钩子点的参数是触发函数交回的数据，结果是事件的效果"""

    pass


type Trigger[D] = Callable[[GameState], D | None]
_events: list[str] = []


class EventStillTrue(RuntimeError):
    """事件的效果应用之后，它的触发函数仍交回同样的数据时抛出"""

    pass


def event[D](
    name: str, trigger: Trigger[D]
) -> Callable[[Callable[[D], Effects]], Event[D]]:
    """
    装饰器：把函数登记为事件 name 的处理函数，trigger 为它的触发函数，返回事件的句柄 Event
    触发函数读状态，交回一份数据（成立）或 None（不成立）；处理函数收到这份数据，交回效果。
    内核不按角色找事件：要按角色检查的插件在自己的触发函数里遍历角色，交回第一个成立的。
    同时成立的事件谁先结算没有保证；一个事件要等另一个先结算，就把这个前提写进自己的触发函数。
    事件是可以在同一状态上反复求值的纯粹检查：
    (a) 触发函数只读状态，什么也不写（模块变量也不写），不抽随机数
    (b) 结算之后，触发函数不再交回同样的数据（否则抛出 EventStillTrue）
    (c) 处理函数只改游戏状态（缓存、效果与计划队列），不写文件、不请求存档、不让玩家选择、不改模块计数，绘制文字可以
    (d) 随机数可以决定结果的大小，不能决定事件是否触发，随机遭遇在掷骰的那一步里结算
    Keyword arguments:
    name -- 事件名
    trigger -- 触发函数，收到状态，交回数据或 None
    Return arguments:
    Callable -- 装饰器
    """

    def register(fn: Callable[[D], Effects]) -> Event[D]:
        hook_only(f"{name}.trigger")(trigger)
        hook_only(name)(fn)
        _events.append(name)
        return Event(name)

    return register


def trigger[D](ev: Event[D]) -> HookOnly[GameState, D | None]:
    """
    事件触发函数的钩子点句柄，用来给触发函数挂钩子
    Keyword arguments:
    ev -- 事件的句柄
    Return arguments:
    HookOnly -- 钩子点 "<事件名>.trigger" 的句柄
    """
    return HookOnly(f"{ev.name}.trigger")


def _trigger(name: str, game: GameState) -> object:
    data = _send(f"{name}.trigger", (game,))
    if data is False:
        raise RuntimeError(f"{name}'s trigger returned False, not None")
    return data


def _fire_event() -> bool:
    for name in _events:
        data = _trigger(name, _context.state)
        if data is not None:
            _loop_calls(apply_effects, _resolve(Event[object](name), data))
            if _trigger(name, _context.state) == data:
                raise EventStillTrue(f"{name} for {data} is still true")
            return True
    return False


def _step() -> None:
    """
    One step settles one thing at instant(), the first that applies of:
    1. an Event whose trigger returns data: its handler runs on that data.
       No order is promised between Events true at once; an Event that
       must follow another says so in its own trigger. Triggers are asked
       in registration order, so a run is reproducible;
    2. else the end of the first character in roster order whose action has
       run out and whose kind registered an end (action_end): the end runs
       on the ended action, the character then holds a 0-minute kernel.Idle
       ("closed": waiting to pick, the shape AddCharacter gives a newcomer),
       and the end's effects apply;
    3. else the first character in roster order whose action has run out,
       which picks and starts in this same step;
    4. else TimeElapse.
    So within one minute A picks and starts at (m, k) and B picks at (m, k + 1)
    on the state A's start made, never all picks then all starts. A 0-minute
    action of a kind without an end goes straight to its owner's next pick at
    m. Events come first in every step, so an Event that an end makes true
    fires before that character picks. More than CYCLE_LIMIT Event or end
    steps without a pick or an elapse raise EventCycle. Roster order is the
    insertion order of GameState.characters.
    """
    _context.phase = "settle"
    if _fire_event() or _end_one():
        _context.unsettled += 1
        if _context.unsettled > CYCLE_LIMIT:
            raise EventCycle(
                f"两次行动开始或时间流逝之间结算了超过 {CYCLE_LIMIT} 步事件或收尾"
            )
        return
    _context.unsettled = 0
    game = _context.state
    for who, character in game.characters.items():
        if _end(character.action) <= game.clock:
            _context.phase = "pick"
            act = _resolve(pick_next_action, who)
            _context.phase = "settle"
            if not isinstance(act, Action) or act.who != who:
                raise RuntimeError(f"{who}'s pick returned {act!r}")
            _loop_calls(apply_effects, _resolve(start_action, act))
            return
    end, elapsed = _resolve(
        time_elapse,
        game.clock,
        min(_end(c.action) for c in game.characters.values()),
    )
    _context.state = replace(_context.state, clock=end)
    _loop_calls(apply_effects, elapsed)


def _end_one() -> bool:
    game = _context.state
    for who, character in game.characters.items():
        act = character.action
        if _end(act) <= game.clock and has_end(act):
            effects = _resolve(end_action, act)
            closed = Action(who, idle.name, None, game.clock, 0)
            _context.state = _with(_context.state, who, action=closed)
            _loop_calls(apply_effects, effects)
            return True
    return False


def load(load_order: Sequence[ModuleType]) -> None:
    """
    定下插件模块的顺序：内核自己排第一，其后依次是 load_order。在一步之内调用时报错
    Keyword arguments:
    load_order -- 插件模块
    """
    if _context.phase != "idle":
        raise RuntimeError("load() inside a step")
    _context.plugins = (__name__, *(m.__name__ for m in load_order))


def step() -> None:
    """
    走一步（见 _step），时钟没动时这一分钟的步数加一，动了就归 0。在一步之内调用时报错
    一步中抛出异常时恢复这一步之前的状态再抛出。选行动时换掉了整个状态，这一步就此结束
    """
    if _context.phase != "idle":
        raise RuntimeError("step() inside a step")
    before = _context.boundary = _context.state
    try:
        _step()
        moved = _context.state.clock != before.clock
        _context.sub = 0 if moved else _context.sub + 1
    except _PickAborted:
        pass
    except BaseException:
        _context.state = before
        raise
    finally:
        _context.phase = "idle"
        _context.boundary = _context.state


def run(game: GameState, load_order: Sequence[ModuleType]) -> NoReturn:
    """
    定下插件顺序、换入初始状态，然后一直走下去，不返回
    Keyword arguments:
    game -- 初始状态
    load_order -- 插件模块
    """
    load(load_order)
    reset_state(game)
    while True:
        step()
