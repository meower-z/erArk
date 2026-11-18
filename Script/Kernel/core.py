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
    who: str
    action_id: str
    action_data: JSON
    start: int
    duration: int


@dataclass(frozen=True)
class Character:
    action: Action
    data: Mapping[str, JSON]


@dataclass(frozen=True)
class GameState:
    clock: int
    characters: Mapping[str, Character]
    data: Mapping[str, JSON]


@dataclass(frozen=True)
class StateChange:
    who: str | None  # None: a global entry
    key: str
    old: JSON
    new: JSON


@dataclass(frozen=True)
class Change:
    who: str | None
    key: str
    op: str
    operand: JSON
    reason: JSON = None


@dataclass(frozen=True)
class Intercept[R]:
    value: R


@dataclass(frozen=True)
class AddCharacter:
    who: str
    data: Mapping[str, JSON] = field(
        default_factory=lambda: MappingProxyType({})
    )


@dataclass(frozen=True)
class RemoveCharacter:
    who: str


type Phase = Literal["idle", "pick", "settle"]


@dataclass
class _RunContext:
    state: GameState
    boundary: GameState
    plugins: tuple[str, ...] = ()
    phase: Phase = "idle"
    dead: list[tuple[object, ...]] = field(default_factory=list)


class DroppedChanges(RuntimeError):
    pass


class _PickAborted(BaseException):
    pass


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
    def __del__(self) -> None:
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


def discard_all_changes(effects: "Effects") -> None:
    if isinstance(effects, Changelist):
        effects.__dict__["settled"] = True


@dataclass(frozen=True)
class HookOnly[*Ts, R]:
    name: str


@dataclass(frozen=True)
class Interrupt:
    who: str


@dataclass(frozen=True)
class Notice[*Ts]:
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
    def __call__(self, *args: *Ts) -> R:
        if self.name in _hook_only:
            raise RuntimeError(f"{self.name} is called only by the kernel loop")
        return cast(R, _send(self.name, tuple(args)))


def export[*Ts, R](
    name: str,
) -> Callable[[Callable[[*Ts], R]], Export[*Ts, R]]:
    def register(fn: Callable[[*Ts], R]) -> Export[*Ts, R]:
        _bodies[name] = fn
        return Export(name)

    return register


def hook_only[*Ts, R](
    name: str,
) -> Callable[[Callable[[*Ts], R]], HookOnly[*Ts, R]]:
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
    return lambda fn: _hook(_inputs, target.name, fn)


def output_hook[*Ts, R](
    target: HookOnly[*Ts, R],
) -> Callable[[OutputHook[R]], OutputHook[R]]:
    return lambda fn: _hook(_outputs, target.name, fn)


def _hook[F: Callable[..., Any]](hooks: Hooks, name: str, fn: F) -> F:
    hooks.setdefault((name, fn.__module__), []).append(fn)
    return fn


def state() -> GameState:
    return _context.boundary


def in_settlement() -> bool:
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
    pass


def action(name: str) -> Callable[[Callable[[Action], Effects]], Start]:
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
    return Action(who, fn.name, data, _context.state.clock, duration)


@action("kernel.Idle")
def idle(act: Action) -> Effects:
    return ()


@hook_only("kernel.PickNextAction")
def pick_next_action(who: str) -> Action:
    return new_action(idle, who, 1)


@hook_only("kernel.StartAction")
def start_action(act: Action) -> Effects:
    if act.action_id not in _actions:
        raise RuntimeError(f"{act.action_id} is not a registered action")
    act = _frozen_action(replace(act, start=_context.state.clock))
    _context.state = _with(_context.state, act.who, action=act)
    return cast(Effects, _send(act.action_id, (act,)))


@hook_only("kernel.TimeElapse")
def time_elapse(start: int, end: int) -> tuple[int, Effects]:
    return (end, ())


type Rule = Callable[[GameState, Change], GameState]
type Data = Mapping[str, JSON]
_owners: dict[str, str] = {}


def rule(key: str) -> Callable[[Rule], HookOnly[GameState, Change, GameState]]:
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
    return _data_of(game, who).get(key)


def with_value(
    game: GameState, who: str | None, key: str, new: JSON
) -> GameState:
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
    return _round(game, effects)


@hook_only("kernel.ApplyEffects")
def apply_effects(effects: Effects) -> bool:
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


@hook_only("kernel.Reset")
def reset(new: GameState) -> GameState:
    return new


def reset_state(new: GameState) -> None:
    if _context.phase == "settle":
        raise RuntimeError("reset_state is forbidden during settlement")
    in_pick, _context.phase = _context.phase == "pick", "settle"
    try:
        game = _frozen_game(_loop_calls(reset, new))
    finally:
        _context.phase = "pick" if in_pick else "idle"
    _context.state = _context.boundary = game
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


class Event(HookOnly[str, Effects]):
    pass


type Trigger = Callable[[GameState, str], bool]
_events: list[str] = []


class EventStillTrue(RuntimeError):
    pass


def event(
    name: str, when: Trigger
) -> Callable[[Callable[[str], Effects]], Event]:
    def register(fn: Callable[[str], Effects]) -> Event:
        hook_only(f"{name}.when")(when)
        hook_only(name)(fn)
        _events.append(name)
        return Event(name)

    return register


def condition(ev: Event) -> HookOnly[GameState, str, bool]:
    return HookOnly(f"{ev.name}.when")


def _holds(name: str, game: GameState, who: str) -> bool:
    held = _send(f"{name}.when", (game, who))
    if not isinstance(held, bool):
        raise RuntimeError(f"{name}'s condition returned {held!r}")
    return held


def _fire_event() -> bool:
    game = _context.state
    for name in _events:
        for who in game.characters:
            if _holds(name, game, who):
                _loop_calls(apply_effects, _resolve(Event(name), who))
                now = _context.state
                if who in now.characters and _holds(name, now, who):
                    raise EventStillTrue(f"{name} for {who} is still true")
                return True
    return False


def _step() -> None:
    _context.phase = "settle"
    if _fire_event():
        return
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


def load(load_order: Sequence[ModuleType]) -> None:
    if _context.phase != "idle":
        raise RuntimeError("load() inside a step")
    _context.plugins = (__name__, *(m.__name__ for m in load_order))


def step() -> None:
    if _context.phase != "idle":
        raise RuntimeError("step() inside a step")
    before = _context.boundary = _context.state
    try:
        _step()
    except _PickAborted:
        pass
    except BaseException:
        _context.state = before
        raise
    finally:
        _context.phase = "idle"
        _context.boundary = _context.state


def run(game: GameState, load_order: Sequence[ModuleType]) -> NoReturn:
    load(load_order)
    reset_state(game)
    while True:
        step()
