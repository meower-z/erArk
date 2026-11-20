"""
gameplay_resolution 的界面编辑（Edit）
======================================
玩家在面板里改了游戏状态而没有定下行动时，选择的草稿随一个 0 分钟的 Edit 行动交给内核。
Edit 开始时写入草稿，重新排上选择时计划的打断，再运行具名编辑（edit 登记的效果代码）。
Edit 没有结束函数：它不收尾，玩家在同一分钟里结算完事件后接着选行动。
"""

from collections.abc import Callable, Mapping, Sequence
from typing import cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import (
    draft,
    intent,
    plan_queue,
    working,
)

EDIT = intent.KIND_PREFIX + "Edit"
""" Edit 的 action_id """

type Apply = Callable[[int, Mapping[str, core.JSON]], None]
""" 具名编辑：角色id、参数 """
_named: dict[str, Apply] = {}
""" 名字到具名编辑 """


def edit(name: str) -> Callable[[Apply], Apply]:
    """
    装饰器：登记一个具名编辑（Edit 开始时在草稿之后运行的效果代码），重复登记时报错
    Keyword arguments:
    name -- 名字
    Return arguments:
    Callable -- 装饰器，原样交回被装饰的 fn(who, args)
    """

    def register(fn: Apply) -> Apply:
        if name in _named:
            raise RuntimeError(f"edit {name} is registered twice")
        _named[name] = fn
        return fn

    return register


def edit_action(
    origin: str,
    changes: Sequence[draft.Change],
    interrupts: Sequence[str] = (),
    effects: Sequence[core.JSON] = (),
    *,
    name: str | None = None,
    args: Mapping[str, core.JSON] | None = None,
) -> core.Action:
    """
    玩家此刻开始的 0 分钟 Edit 行动
    Keyword arguments:
    origin -- 编辑来自哪里（面板或指令），只供查看
    changes -- 草稿
    interrupts -- 选择时排下打断的角色键
    effects -- 选择时写 GameState 数据的写入（working.close_pick 交回的）
    name -- 具名编辑的名字，没有时为 None
    args -- 具名编辑的参数
    Return arguments:
    Action -- data 为 origin、draft、interrupts、effects，具名编辑时另有 edit 与 args
    """
    data: dict[str, core.JSON] = {
        "origin": origin,
        "draft": tuple(changes),
        "interrupts": tuple(interrupts),
        "effects": tuple(effects),
    }
    if name is not None:
        data["edit"] = name
        data["args"] = dict(args or {})
    return core.Action("0", EDIT, data, core.state().clock, 0)


@core.action(EDIT)
def start_edit(act: core.Action) -> core.Effects:
    """
    Edit 的开始：先用 working.replay 把选择时的写入放进这一步的缓冲区，再写入草稿，
    重新排上选择时计划的打断，最后运行具名编辑
    Keyword arguments:
    act -- Edit 行动
    Return arguments:
    Effects -- 空，打断由计划队列在这一步交给内核
    """
    data = cast(Mapping[str, core.JSON], act.action_data)
    working.replay(cast(Sequence[core.JSON], data.get("effects", ())))
    draft.apply(cast(Sequence[draft.Change], data["draft"]))
    for who in cast(Sequence[str], data["interrupts"]):
        plan_queue.interrupt(int(who))
    if "edit" in data:
        args = cast(Mapping[str, core.JSON], data["args"])
        _named[str(data["edit"])](int(act.who), args)
    return ()
