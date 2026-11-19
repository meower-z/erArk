"""
tk_ui 的玩家选择
================
玩家的 PickNextAction 钩子（player_hook）反复调用 chooser，直到它抛出 Chosen。
游戏里 chooser 是主面板循环的一轮：面板经 choose 定下玩家的行动时抛出 Chosen，
面板栈一路展开到钩子，面板不再往下跑；下一次玩家选行动时面板从头重画。
一轮面板跑完而回到了标题或建角色面板时抛出 LeftGame，穿过 core.step() 回到 start_flow 的主流程。
测试把 chooser 换成脚本。
"""

from collections.abc import Callable, Mapping, Sequence
from typing import NoReturn, cast

from Script.Core import cache_control, constant, game_type, py_cmd
from Script.Kernel import core
from Script.Modules.gameplay_resolution import intent

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

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


UI_STATE: frozenset[str] = frozenset(
    {
        "now_panel_id",
        "wframe_mouse",
        "cmd_data",
        "text_wait",
        "input_cache",
        "back_save_panel",
        "instruct_type_filter",
        "instruct_sex_type_filter",
        "instruct_index_filter",
        "instruct_type_filter_cache",
        "rhodes_island.makefood_filter_type",
        "rhodes_island.makefood_filter_difficulty",
        "rhodes_island.makefood_filter_time",
        "rhodes_island.makefood_sort_type",
        "rhodes_island.makefood_sort_order",
        "rhodes_island.makefood_cook_mode",
        "rhodes_island.makefood_make_count",
        "rhodes_island.makefood_data",
    }
)
""" 玩家选行动时可以写的缓存属性路径（界面状态）；其余缓存在选行动时只读 """


def _round() -> None:
    """
    主面板循环的一轮：显示当前面板id对应的面板
    面板把面板id换成了标题或建角色面板时抛出 LeftGame
    """
    py_cmd.clr_cmd()
    py_cmd.focus_cmd()
    constant.panel_data[cache.now_panel_id]()
    if cache.now_panel_id in PRE_GAME_PANELS:
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
