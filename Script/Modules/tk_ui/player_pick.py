"""
tk_ui 的玩家选择
================
玩家的 PickNextAction 钩子（player_hook）反复调用 chooser，直到它抛出 Chosen。
游戏里 chooser 是主面板循环的一轮：面板经 choose 定下玩家的行动时抛出 Chosen，
面板栈一路展开到钩子，面板不再往下跑；下一次玩家选行动时面板从头重画。
一轮面板跑完而回到了标题或建角色面板时抛出 LeftGame，穿过 core.step() 回到 start_flow 的主流程。
测试把 chooser 换成脚本。
玩家选择里的面板（handle_panel.add_panel 登记，UNDRAFTED 之外）、一次指令或场景里的内嵌子面板运行在
草稿块（drafting）中，经选择缓冲区暂存 GameState 写入并记录计划打断；
退出时写入与打断随定下的行动走，没有定下行动时随一个 0 分钟的 Edit 走；取消（back）时什么也不留下。
"""

import random
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import NoReturn, cast

from Script.Core import constant, py_cmd
from Script.Kernel import core
from Script.Modules.gameplay_resolution import (
    edits,
    intent,
    plan_queue,
    working,
)
from Script.UI.Moudle import view

PRE_GAME_PANELS = (constant.Panel.TITLE, constant.Panel.CREATOR_CHARACTER)
""" 不在游戏里的面板：由 start_flow 的主流程显示，不经内核 """


class Chosen(BaseException):
    """
    界面定下了玩家的行动：从面板栈一路抛到玩家的 PickNextAction 钩子，由它交回内核。
    是 BaseException，面板里的 except Exception 拦不住
    """

    def __init__(self, action: core.Action) -> None:
        """
        Keyword arguments:
        action -- 定下的行动
        """
        super().__init__(action)
        self.action = action
        """ 定下的行动 """


class LeftGame(BaseException):
    """离开游戏回到标题，或测试脚本结束：穿过 core.step() 抛到驱动循环"""


class Back(BaseException):
    """
    玩家在任意一层取消了整个行动：抛到玩家的 PickNextAction 钩子，这一轮不定下行动。
    是 BaseException，面板里的 except Exception 拦不住
    """


def back() -> NoReturn:
    """取消整个行动，回到选择循环的场景面板：不定下行动，不空闲，时间不走"""
    raise Back


UNDRAFTED = frozenset(
    {
        constant.Panel.IN_SCENE,
        constant.Panel.TITLE,
        constant.Panel.CREATOR_CHARACTER,
        constant.Panel.SAVE,
    }
)
""" 不开选择缓冲区的面板：场景面板只读并由子面板处理，标题与建角色不在游戏里，存读档换掉整个 GameState """

ui_random = random.Random()
""" 只影响显示的随机数（例如列表的显示顺序）：不动游戏的随机数状态 """

_in_pick = False
""" 玩家的 PickNextAction 钩子正在跑一轮选择 """


def in_pick() -> bool:
    """玩家正在选行动时为 True"""
    return _in_pick


@contextmanager
def picking() -> Iterator[None]:
    """玩家的 PickNextAction 钩子跑一轮选择的期间：in_pick 为真"""
    global _in_pick
    _in_pick = True
    try:
        yield
    finally:
        _in_pick = False


def _carrying(
    act: core.Action,
    interrupts: list[str],
    effects: tuple[core.JSON, ...],
) -> core.Action:
    """
    让定下的行动带上选择期间的打断与写入：Edit 追加到自身列表中，带 behavior_id 的意图直接挂上这两项，
    其余行动抛 TypeError
    Keyword arguments:
    act -- 定下的行动
    interrupts -- 选择期间排下的打断角色键列表
    effects -- 选择期间暂存的 GameState 写入
    Return arguments:
    Action -- 带上打断与写入的行动
    """
    if not interrupts and not effects:
        return act
    data = act.action_data
    if not isinstance(data, Mapping):
        raise TypeError(f"{act.action_id} cannot carry pick writes")
    carried: dict[str, core.JSON]
    if act.action_id == edits.EDIT:
        carried = {
            **data,
            "interrupts": (
                *cast(Sequence[str], data["interrupts"]),
                *interrupts,
            ),
            "effects": (
                *cast(Sequence[core.JSON], data["effects"]),
                *effects,
            ),
        }
    elif "behavior_id" in data:
        carried = dict(data)
        if interrupts:
            carried["interrupts"] = tuple(interrupts)
        if effects:
            carried["effects"] = effects
    else:
        raise TypeError(f"{act.action_id} cannot carry pick writes")
    return core.Action(
        act.who,
        act.action_id,
        cast(core.JSON, carried),
        act.start,
        act.duration,
    )


@contextmanager
def drafting(origin: str) -> Iterator[None]:
    """
    玩家选择中的草稿上下文：打开选择缓冲区（working.open_pick）并记下当前待打断位置（plan_queue.mark），
    正常退出且有写入或打断时定下 0 分钟 Edit（抛 Chosen）；
    块内定下行动时把写入与打断附到该行动上；遇到 Back 或异常时丢弃两者。
    不在玩家选择中时直接运行块，外层已有选择缓冲区时并入外层
    Keyword arguments:
    origin -- 写入来源标识（面板或指令），记入生成的 Edit
    """
    if not _in_pick or working.picking():
        yield
        return
    mark = plan_queue.mark()
    buffer = working.open_pick()
    try:
        yield
    except Chosen as chosen:
        effects = working.close_pick(buffer)
        interrupts = plan_queue.take_since(mark)
        raise Chosen(_carrying(chosen.action, interrupts, effects)) from None
    except BaseException:
        working.close_pick(buffer)
        plan_queue.take_since(mark)
        raise
    effects = working.close_pick(buffer)
    interrupts = plan_queue.take_since(mark)
    if interrupts or effects:
        raise Chosen(edits.edit_action(origin, interrupts, effects))


def commit_edit(name: str, args: Mapping[str, core.JSON]) -> NoReturn:
    """
    定下一个具名编辑（edits.edit 登记的效果代码），抛出 Chosen；在选择草稿里时选择写入与打断一起带上
    Keyword arguments:
    name -- 具名编辑的名字
    args -- 参数
    """
    raise Chosen(edits.edit_action(name, name=name, args=args))


def _round() -> None:
    """
    主面板循环的一轮：显示当前面板id对应的面板
    面板把面板id换成了标题或建角色面板时抛出 LeftGame
    """
    py_cmd.clr_cmd()
    constant.panel_data[view.now_panel_id]()
    if view.now_panel_id in PRE_GAME_PANELS:
        raise LeftGame


def choose(
    behavior_id: str,
    minutes: int,
    *,
    kind: str = "Behavior",
    target: int | None = None,
    state: int | str | None = None,
    fields: Mapping[str, object] | None = None,
    args: Mapping[str, object] | None = None,
    move: intent.Move | None = None,
    say: str | None = None,
    premises: Sequence[str] = (),
    judge: str | None = None,
) -> NoReturn:
    """
    定下玩家的行动，抛出 Chosen
    Keyword arguments:
    behavior_id -- 行为id
    minutes -- 名义分钟数
    kind -- 行动的种类
    target -- 交互对象的角色id，None 时为自己
    state -- 开始时的角色状态，None 时为行为id
    fields -- 开始时写在玩家自己身上的值，键是 Intent.fields 的路径（如 "behavior.food_name"）
    args -- 本种类自己的参数（Intent.args）
    move -- 开始时的移动（Intent.move）
    say -- 开始时绘制的文本（Intent.say）
    premises -- 开始时都要成立的前提id，由开始门检查
    judge -- 玩家指令的判定名（Intent.judge），由开始门检查
    """
    chosen = intent.Intent(behavior_id=behavior_id, minutes=minutes)
    if target is not None:
        chosen["target"] = target
    if state is not None:
        chosen["state"] = state
    if fields:
        chosen["fields"] = {
            path: cast(core.JSON, value) for path, value in fields.items()
        }
    if args:
        chosen["args"] = {
            key: cast(core.JSON, value) for key, value in args.items()
        }
    if move is not None:
        chosen["move"] = move
    if say is not None:
        chosen["say"] = say
    if premises:
        chosen["premises"] = list(premises)
    if judge is not None:
        chosen["judge"] = judge
    raise Chosen(intent.behavior_action(0, chosen, kind))


chooser: Callable[[], None] = _round
""" 玩家的一轮选择：游戏里是主面板循环的一轮，测试里换成脚本 """
