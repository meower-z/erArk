"""
gameplay_resolution 的行动开始（StartAction）
============================================
每种行动 gameplay_resolution.<kind> 由 starter(kind) 登记一个开始函数，内核按 action_id 分派到它。
开始函数统一经 behave 跑：
1. begin：来自队列的弹出队首；写 Behavior（此刻开始、时长）、状态、交互对象与 fields；移动；绘制 say。
2. 本种类自己的开始代码 extra(who, intent)，没有时跳过。
3. character_behavior.settle_start：结算状态与事件（judge_character_status），玩家另有记录、前置结算与睡觉刷新。
4. 交回把角色的 open 设为真的 StateChange。
内核在调用开始函数之前就定下了行动的时长。要换成别的行动的
（例如选好的食物或病人已被同一分钟里更早的开始拿走，退回 1 分钟的等待），
用 check(kind) 登记一个复查：它在开始门之后、内核定下行动之前运行，交回的行动换掉原来的。
通用种类 Behavior 的开始函数登记在这里，它没有自己的开始代码。
"""

from collections.abc import Callable, Mapping
from typing import cast

from Script.Core import cache_control, constant, game_type
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, intent, plan_queue
from Script.UI.Moudle import draw

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

type Extra = Callable[[int, intent.Intent], None]
""" 一种行动自己的开始代码：角色id、意图 """
type Check = Callable[[int, intent.Intent], core.Action | None]
""" 一种行动开始前的复查：角色id、意图；交回换上的行动，照旧开始时交回 None """

FIELD_ROOTS = ("behavior", "sp_flag", "action_info", "work")
""" Intent.fields 的路径可以用的根：角色自己身上的这几个对象 """
OPEN_MAP = "open_map"
""" Intent.args 的键：玩家这一段移动开始后仍打开地图面板 """

_checks: dict[str, Check] = {}
""" action_id 到它开始前的复查 """


def starter(kind: str) -> Callable[[Extra], Extra]:
    """
    登记一种行动的开始：内核开始 gameplay_resolution.<kind> 时调用 behave(act, fn)
    Keyword arguments:
    kind -- 行动的种类
    Return arguments:
    Callable -- 装饰器，原样交回被装饰的 fn(who, intent)
    """

    def register(fn: Extra) -> Extra:
        def start(act: core.Action) -> core.Effects:
            return behave(act, fn)

        core.action(intent.KIND_PREFIX + kind)(start)
        return fn

    return register


def check(kind: str) -> Callable[[Check], Check]:
    """
    登记一种行动开始前的复查：行动开始时（开始门之后、内核定下行动之前）调用 fn(who, intent)
    Keyword arguments:
    kind -- 行动的种类
    Return arguments:
    Callable -- 装饰器，原样交回被装饰的 fn
    """

    def register(fn: Check) -> Check:
        action_id = intent.KIND_PREFIX + kind
        if action_id in _checks:
            raise RuntimeError(f"{action_id} already has a check")
        _checks[action_id] = fn
        return fn

    return register


@core.input_hook(core.start_action)
def recheck(act: core.Action) -> tuple[core.Action]:
    """
    StartAction 的输入钩子：行动有复查时跑复查，复查交回的行动换掉原来的
    Keyword arguments:
    act -- 要开始的行动
    Return arguments:
    tuple -- 交给内层的行动
    """
    fn = _checks.get(act.action_id)
    if fn is None or not isinstance(act.action_data, Mapping):
        return (act,)
    replaced = fn(int(act.who), cast(intent.Intent, dict(act.action_data)))
    return (act if replaced is None else replaced,)


def plain(value: core.JSON) -> object:
    """
    冻结的 JSON 值换回缓存里用的值：元组换成列表，映射换成 dict
    Keyword arguments:
    value -- 行动数据里的值
    Return arguments:
    object -- 写进缓存的值
    """
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [plain(item) for item in value]
    return value


def write_field(who: int, path: str, value: core.JSON) -> None:
    """
    把一个值写在角色自己身上
    Keyword arguments:
    who -- 角色id
    path -- 路径，根是 FIELD_ROOTS 之一，例如 "behavior.move_target"
    value -- JSON 值
    """
    root, *names = path.split(".")
    if root not in FIELD_ROOTS or not names:
        raise ValueError(f"Intent.fields 不能写 {path}")
    node: object = getattr(cache.character_data[who], root)
    *parents, last = names
    for name in parents:
        node = getattr(node, name)
    if not hasattr(node, last):
        raise AttributeError(f"{path} 不是角色身上已有的字段")
    setattr(node, last, plain(value))


def begin(who: int, act: core.Action, chosen: intent.Intent) -> None:
    """
    行动开始时照着意图写缓存：来自队列的弹出队首；换上新的 Behavior（此刻开始，时长同内核；
    时停中玩家的 0 分钟行动用名义分钟数；保留移动的来源与最终目标）、状态与交互对象（意图没写交互对象时不改）；
    写 fields；移动；绘制 say（参数 say_wait 为真时等玩家确认，say_style 为样式）。玩家的面板回到场景主面板
    Keyword arguments:
    who -- 角色id
    act -- 开始的行动
    chosen -- 行动的意图
    """
    if chosen.get("queued"):
        plan_queue.pop(who)
    character_data = cache.character_data[who]
    behavior = game_type.Behavior()
    behavior.behavior_id = chosen["behavior_id"]
    behavior.duration = act.duration or chosen["minutes"]
    behavior.start_time = game_time.at(act.start)
    behavior.move_src = character_data.behavior.move_src
    behavior.move_final_target = character_data.behavior.move_final_target
    character_data.behavior = behavior
    character_data.state = chosen.get("state", chosen["behavior_id"])
    if "target" in chosen:
        character_data.target_character_id = chosen["target"]
    for path, value in chosen.get("fields", {}).items():
        write_field(who, path, value)
    move = chosen.get("move")
    if move is not None:
        from Script.StateMachine import default as state_machine_default

        state_machine_default.general_movement_module(
            who, list(move["to"]), show_info_flag=move["show"]
        )
        character_data.behavior.start_time = behavior.start_time
        character_data.behavior.duration = act.duration
        character_data.action_info.last_move_time = behavior.start_time
    say = chosen.get("say")
    if say is not None:
        args = chosen.get("args", {})
        now_draw = (
            draw.WaitDraw() if args.get("say_wait") else draw.NormalDraw()
        )
        now_draw.text = say
        style = args.get("say_style")
        if isinstance(style, str):
            now_draw.style = style
        now_draw.draw()
    if who == 0:
        cache.now_panel_id = (
            constant.Panel.SEE_MAP
            if chosen.get("args", {}).get(OPEN_MAP)
            else constant.Panel.IN_SCENE
        )


def behave(act: core.Action, extra: Extra | None = None) -> core.Effects:
    """
    一个行动的开始：begin，本种类的开始代码，结算，打开 open
    Keyword arguments:
    act -- 开始的行动，action_data 是 Intent
    extra -- 本种类自己的开始代码，没有时为 None
    Return arguments:
    Effects -- 把角色的 open 设为真的 StateChange
    """
    from Script.Design import character_behavior

    plan_queue.acting = act.who
    who = int(act.who)
    if not isinstance(act.action_data, Mapping):
        raise TypeError(f"{act.action_id} 的行动数据不是 Intent")
    chosen = cast(intent.Intent, dict(act.action_data))
    begin(who, act, chosen)
    if extra is not None:
        extra(who, chosen)
    character_behavior.settle_start(who, act.duration)
    was = core.value(core.state(), act.who, actions.OPEN)
    return (core.StateChange(act.who, actions.OPEN, was, True),)


@starter("Behavior")
def general(who: int, chosen: intent.Intent) -> None:
    """
    通用种类 Behavior：没有自己的开始代码，begin 与结算就是全部
    Keyword arguments:
    who -- 角色id
    chosen -- 行动的意图
    """
