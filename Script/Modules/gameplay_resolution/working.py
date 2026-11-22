"""
gameplay_resolution 的工作集：旧的命令式代码经它读写 GameState 里的数据
=======================================================================
领域模块用 register 登记自己的键。代码用 get 读，用 put（整值替换）或 change（交给规则的一次操作）写。
写入记在当前的缓冲区里。同一缓冲区里之后的 get 读得到这些写入，GameState 本身不变。缓冲区有三种：
- 一步结算中（core.in_settlement）是这一步的缓冲区，kernel.ApplyEffects 的输入钩子 flush 把它换成效果。
- 玩家选择的草稿里（player_pick.drafting）是选择的缓冲区。close_pick 交回的写入（含 forget）随定下的行动走，
  行动开始时 replay 把它们放进那一步的缓冲区。
- based_on(game) 里是以 game 为底的缓冲区（Reset 的每一步）。调用方把它的 effects() 套到结果上。
在别处写入报 RuntimeError，干员选行动时也一样。
角色在 GameState.characters 里时，这个角色的键存在角色数据里。不在时，键存在全局键 roster.offstage 里这个角色的一项下。
角色加入或离开花名册时，flush 把这个角色的数据搬过去。
缓冲区换成效果时比较 roster.offstage 的角色顺序，并只对本缓冲区停放、搬动或遗忘的角色用 same 比较新旧值。
两者只差键的顺序或值的类型时，也写入新值。
"""

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from fractions import Fraction
from typing import cast

from Script.Kernel import core

OFFSTAGE = "roster.offstage"
""" 不在 GameState.characters 里的角色的数据：角色键到 {键: 值} """

type Fold = Callable[[core.JSON, str, core.JSON], core.JSON]
""" 规则的一次操作：(旧值, 操作名, 操作数) -> 新值 """


@dataclass(frozen=True)
class _Key:
    default: core.JSON
    fold: Fold | None


_keys: dict[str, _Key] = {}


def register(key: str, default: core.JSON, fold: Fold | None = None) -> None:
    """
    登记一个键。给了 fold 时这个键由规则拥有，只能 change。没有 fold 时只能 put
    Keyword arguments:
    key -- 键名，登记过的键或 roster.offstage 报 RuntimeError
    default -- 没有这一项时读到的值
    fold -- 规则的一次操作：(旧值, 操作名, 操作数) -> 新值
    """
    if key in _keys or key == OFFSTAGE:
        raise RuntimeError(f"{key} is registered twice")
    _keys[key] = _Key(default, fold)


_ATOMS = frozenset((int, bool, float, str, Fraction, type(None)))
""" same 里不用再往下比的值的类型 """


def same(a: object, b: object) -> bool:
    """
    两个 JSON 值是否相同。映射要键、键的顺序与各项都相同。元组与列表要长度与各项都相同，元组和列表之间不区分。
    其余值要类型与值都相同
    Keyword arguments:
    a -- 值
    b -- 值
    Return arguments:
    bool -- 相同时为 True
    """
    if a is b:
        return True
    if type(a) is type(b) and type(a) in _ATOMS:
        return a == b
    if isinstance(a, Mapping) and isinstance(b, Mapping):
        return list(a) == list(b) and all(same(a[k], b[k]) for k in a)
    if isinstance(a, tuple | list) and isinstance(b, tuple | list):
        return len(a) == len(b) and all(map(same, a, b))
    return type(a) is type(b) and a == b


def fold_all(key: str, old: core.JSON, ops: Sequence[core.JSON]) -> core.JSON:
    """
    把一串操作依次套到 old 上，old 为 None 时从登记的默认值开始。规则与缓冲区都用它
    Keyword arguments:
    key -- 键名，登记时没有 fold 的键报 RuntimeError
    old -- 当前存的值
    ops -- (操作名, 操作数) 的序列
    Return arguments:
    JSON -- 新值
    """
    spec = _keys[key]
    if spec.fold is None:
        raise RuntimeError(f"{key} has no fold")
    value = spec.default if old is None else old
    for op in ops:
        name, operand = cast(tuple[str, core.JSON], op)
        value = spec.fold(value, name, operand)
    return value


def _stored(game: core.GameState, who: str | None, key: str) -> core.JSON:
    if who is None or who in game.characters:
        return core.value(game, who, key)
    offstage = cast(
        Mapping[str, Mapping[str, core.JSON]],
        core.value(game, None, OFFSTAGE) or {},
    )
    return offstage.get(who, {}).get(key)


@dataclass
class _Pending:
    raw: core.JSON
    value: core.JSON
    ops: list[tuple[str, core.JSON]] = field(default_factory=list)


@dataclass
class _Buffer:
    base: core.GameState | None
    pick: bool = False
    pending: dict[tuple[str | None, str], _Pending] = field(
        default_factory=dict
    )
    forgotten: list[str] = field(default_factory=list)

    def game(self) -> core.GameState:
        return core.state() if self.base is None else self.base

    def read(self, who: str | None, key: str) -> core.JSON:
        hit = self.pending.get((who, key))
        if hit is not None:
            return hit.value
        return _stored(self.game(), who, key)

    def entry(self, who: str | None, key: str) -> _Pending:
        hit = self.pending.get((who, key))
        if hit is None:
            raw = _stored(self.game(), who, key)
            hit = self.pending[(who, key)] = _Pending(raw, raw)
        return hit

    def put(self, who: str | None, key: str, new: core.JSON) -> None:
        if _keys[key].fold is not None:
            raise RuntimeError(f"{key} changes only by its rule")
        self.entry(who, key).value = new

    def change(
        self, who: str | None, key: str, op: str, operand: core.JSON
    ) -> None:
        hit = self.entry(who, key)
        hit.value = fold_all(key, hit.value, ((op, operand),))
        hit.ops.append((op, operand))

    def carried(self) -> tuple[core.JSON, ...]:
        out: list[core.JSON] = []
        for (who, key), hit in self.pending.items():
            if _keys[key].fold is None:
                out.append(
                    {"who": who, "key": key, "old": hit.raw, "new": hit.value}
                )
            else:
                out.extend(
                    {"who": who, "key": key, "op": op, "operand": operand}
                    for op, operand in hit.ops
                )
        out.extend({"forget": who} for who in self.forgotten)
        return tuple(out)

    def _move(
        self,
        e: core.Effect,
        offstage: dict[str, Mapping[str, core.JSON]],
        parked: dict[str, dict[str, core.JSON]],
        moved: set[str],
    ) -> core.Effect:
        game = self.game()
        if isinstance(e, core.AddCharacter):
            if e.who.isdigit() and int(e.who) != 0:
                from Script.Modules.domains import roster

                pushed = _reading() is not self
                if pushed:
                    _stack.append(self)
                try:
                    roster.require_eligible(int(e.who))
                finally:
                    if pushed:
                        _stack.remove(self)
            if e.who in offstage or e.who in parked:
                if e.data:
                    raise RuntimeError(
                        f"{e.who} joins with data and parked data"
                    )
                data = parked.pop(e.who, None) or dict(offstage[e.who])
                offstage.pop(e.who, None)
                moved.add(e.who)
                return core.AddCharacter(e.who, data)
            return e
        if isinstance(e, core.RemoveCharacter) and e.who in game.characters:
            kept = dict(game.characters[e.who].data)
            for (who, key), hit in self.pending.items():
                if who == e.who:
                    kept[key] = hit.value
            moved.add(e.who)
            from Script.Modules.domains import identity

            present = self.read(None, identity.KEY) or {}
            if kept and e.who in cast(Mapping[str, core.JSON], present):
                offstage[e.who] = kept
        return e

    def effects(self, given: core.Effects = ()) -> core.Effects:
        game = self.game()
        raw_offstage = core.value(game, None, OFFSTAGE)
        offstage = dict(
            cast(Mapping[str, Mapping[str, core.JSON]], raw_offstage or {})
        )
        parked: dict[str, dict[str, core.JSON]] = {}
        for (who, key), hit in self.pending.items():
            if who is not None and who not in game.characters:
                parked.setdefault(who, dict(offstage.get(who, {})))[
                    key
                ] = hit.value
        moved: set[str] = set()
        rewritten = [self._move(e, offstage, parked, moved) for e in given]
        for who in self.forgotten:
            offstage.pop(who, None)
            parked.pop(who, None)
        offstage.update(parked)
        out: list[core.Effect] = []
        for (who, key), hit in self.pending.items():
            if who in moved or (who is not None and who not in game.characters):
                continue
            if _keys[key].fold is None:
                out.append(core.StateChange(who, key, hit.raw, hit.value))
            else:
                out.append(core.Change(who, key, "ops", tuple(hit.ops)))
        raw = cast(Mapping[str, core.JSON], raw_offstage or {})
        touched = {*parked, *moved, *self.forgotten}
        if list(offstage) != list(raw) or not all(
            same(offstage.get(who), raw.get(who)) for who in touched
        ):
            out.append(core.StateChange(None, OFFSTAGE, raw_offstage, offstage))
        return (*rewritten, *out)


_stack: list[_Buffer] = []
_step = _Buffer(None)


def active() -> bool:
    """当前是否处于可写 GameState 数据的步、挑选或缓冲区内"""
    return bool(_stack) or core.in_settlement()


def _active() -> _Buffer:
    if _stack:
        return _stack[-1]
    if core.in_settlement():
        return _step
    raise RuntimeError(
        "GameState data is written outside a step, a pick or a Reset"
    )


def _reading() -> _Buffer:
    if _stack:
        return _stack[-1]
    return _step


def get(
    who: str | None, key: str, game: core.GameState | None = None
) -> core.JSON:
    """
    读一项数据。给了 game 时只读 game，否则读当前缓冲区的底加上缓冲区里还没套用的写入。
    不在花名册里的角色从 roster.offstage 读。没有这一项时为登记的默认值
    Keyword arguments:
    who -- 角色键，None 为全局数据
    key -- 键名
    game -- 给出时只读这个状态
    Return arguments:
    JSON -- 值
    """
    value = (
        _stored(game, who, key)
        if game is not None
        else _reading().read(who, key)
    )
    return _keys[key].default if value is None else value


def put(who: str | None, key: str, new: core.JSON) -> None:
    """
    整值替换一项数据，写进当前缓冲区。规则拥有的键报 RuntimeError
    Keyword arguments:
    who -- 角色键，None 为全局数据
    key -- 键名
    new -- 新值
    """
    _active().put(who, key, new)


def change(who: str | None, key: str, op: str, operand: core.JSON) -> None:
    """
    给规则拥有的一项数据记一次操作，写进当前缓冲区。缓冲区里这一项的值随即按 fold 更新
    Keyword arguments:
    who -- 角色键，None 为全局数据
    key -- 键名
    op -- 操作名
    operand -- 操作数
    """
    _active().change(who, key, op, operand)


def forget(cid: int) -> None:
    """
    角色从缓存里删掉时调用：在当前缓冲区记下这个角色，换成效果时丢掉这个角色停放在 roster.offstage 里的数据。
    在玩家选择里调用时，记下的角色随定下的行动走，行动开始时由 replay 放进那一步的缓冲区
    Keyword arguments:
    cid -- 角色id
    """
    _active().forgotten.append(str(cid))


@contextmanager
def based_on(game: core.GameState) -> Iterator[_Buffer]:
    """
    以 game 为底开一个缓冲区。with 块里的读写都对着它，调用方用它的 effects() 取出写入换成的效果
    Keyword arguments:
    game -- 底
    Return arguments:
    Iterator -- 缓冲区
    """
    buffer = _Buffer(game)
    _stack.append(buffer)
    try:
        yield buffer
    finally:
        _stack.remove(buffer)


def open_pick() -> _Buffer:
    """
    开玩家选择的缓冲区
    Return arguments:
    _Buffer -- 缓冲区，选择结束时交给 close_pick
    """
    buffer = _Buffer(None, pick=True)
    _stack.append(buffer)
    return buffer


def close_pick(buffer: _Buffer) -> tuple[core.JSON, ...]:
    """
    关上选择的缓冲区，交回要随行动走的写入。缓冲区已被丢掉（换了 GameState）时交回空元组
    Keyword arguments:
    buffer -- open_pick 开的缓冲区
    Return arguments:
    tuple -- 写入，整值替换为 {"who", "key", "old", "new"}，一次操作为 {"who", "key", "op", "operand"}，
    forget 为 {"forget": 角色键}
    """
    if buffer not in _stack:
        return ()
    _stack.remove(buffer)
    return buffer.carried()


def replay(carried: Sequence[core.JSON]) -> None:
    """
    行动开始时把选择里的写入与 forget 记下的角色放进当前缓冲区。整值替换的 old 与现在读到的值不同时报 RuntimeError
    Keyword arguments:
    carried -- close_pick 交回的写入
    """
    buffer = _active()
    for item in carried:
        entry = cast(Mapping[str, core.JSON], item)
        if "forget" in entry:
            buffer.forgotten.append(str(entry["forget"]))
            continue
        who, key = cast(str | None, entry["who"]), str(entry["key"])
        if "op" in entry:
            buffer.change(who, key, str(entry["op"]), entry["operand"])
            continue
        if buffer.read(who, key) != entry["old"]:
            raise RuntimeError(f"{key} of {who} does not follow the pick")
        buffer.put(who, key, entry["new"])


def _clear() -> None:
    global _step
    _step = _Buffer(None)


@core.input_hook(core.apply_effects)
def flush(effects: core.Effects) -> tuple[core.Effects]:
    """
    这一步唯一一次套用效果之前，把这一步缓冲区里的写入换成效果，并搬动加入或离开花名册的角色的数据
    Keyword arguments:
    effects -- 这一步的效果
    Return arguments:
    tuple -- 换过之后的效果。每个 (角色, 键) 一个效果，规则拥有的键为 Change，其余为 StateChange
    """
    buffer = _step
    _clear()
    return (buffer.effects(effects),)


@core.input_hook(core.step_failed)
def drop_on_failure() -> tuple[()]:
    """
    一步出错时（kernel.StepFailed）丢掉这一步缓冲区里的写入
    Return arguments:
    tuple -- 空参数
    """
    _clear()
    return ()


@core.output_hook(core.reset)
def drop_on_reset(game: core.GameState) -> core.GameState:
    """
    换了 GameState 后（kernel.Reset 的输出钩子）丢掉这一步的缓冲区与玩家选择的缓冲区
    Keyword arguments:
    game -- 新的 GameState
    Return arguments:
    GameState -- 原样交回
    """
    _clear()
    _stack[:] = [buffer for buffer in _stack if not buffer.pick]
    return game


def reconcile(game: core.GameState) -> core.GameState:
    """
    Reset 步骤用：roster.offstage 里花名册上的角色的数据搬进角色数据，缓存里还有的其余角色留在 roster.offstage，
    缓存里已没有的角色的数据丢掉。同一个键两处都有时报 RuntimeError
    Keyword arguments:
    game -- 换入的状态
    Return arguments:
    GameState -- 每个角色的数据只在一处的状态
    """
    from Script.Modules.domains import identity

    raw = cast(
        Mapping[str, Mapping[str, core.JSON]],
        core.value(game, None, OFFSTAGE) or {},
    )
    offstage: dict[str, Mapping[str, core.JSON]] = {}
    for who, data in raw.items():
        if who in game.characters:
            held = game.characters[who].data
            if set(held) & set(data):
                raise RuntimeError(f"{who}'s data is in two places")
            for key, value in data.items():
                game = core.with_value(game, who, key, value)
        elif identity.exists(int(who), game):
            offstage[who] = data
    if offstage or raw:
        game = core.with_value(game, None, OFFSTAGE, offstage)
    return game
