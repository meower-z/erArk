"""
npc_action_choice 选出的行动：状态机交回的计划
==============================================
状态机不改缓存。它把选出的行为要写的值（自己的行为id、时长、状态、交互对象、标记，或别的角色的）、要去的场景、
要显示的文字和要调用的结算函数，按顺序记在 Plan 里交回；行动开始时，gameplay_resolution 的 npc_start 按同样的顺序执行。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from Script.Config import normal_config
from Script.Core import cache_control, game_type, get_text
from Script.Design import character_move, map_handle

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_ = get_text._
""" 翻译api """

type Op = tuple[object, ...]
""" 计划的一步：("set", 角色id, 属性路径, 值)、("move", 目标场景, 是否显示移动信息)、("draw", 文字, 是否等待, 样式)
或 ("effect", 结算函数, 位置参数, 关键字参数) """


class Plan:
    """一个角色选出的行动：按顺序记下的写入与移动"""

    def __init__(self, character_id: int) -> None:
        """
        Keyword arguments:
        character_id -- 选行动的角色id
        """
        self.character_id = character_id
        self.ops: list[Op] = []
        self._shadow: dict[str, object] = {}
        self._moves: list[int] = []

    def set(self, path: str, value: object) -> None:
        """
        记下一次写入：行动开始时把 value 写到角色数据的 path 上
        Keyword arguments:
        path -- 角色数据上的属性路径，如 "behavior.duration"
        value -- 要写的值
        """
        self.ops.append(("set", self.character_id, path, value))
        self._shadow[path] = value

    def set_for(self, character_id: int, path: str, value: object) -> None:
        """
        记下对别的角色的一次写入
        Keyword arguments:
        character_id -- 被写的角色id
        path -- 属性路径
        value -- 要写的值
        """
        self.ops.append(("set", character_id, path, value))

    def draw(
        self, text: str, wait: bool = False, style: str | None = None
    ) -> None:
        """
        记下行动开始时显示的一段文字
        Keyword arguments:
        text -- 文字
        wait -- 是否等玩家确认（WaitDraw）
        style -- 文字样式，None 为默认
        """
        self.ops.append(("draw", text, wait, style))

    def effect(
        self, settle: Callable[..., object], *args: object, **kwargs: object
    ) -> None:
        """
        记下行动开始时调用的一个结算函数
        Keyword arguments:
        settle -- 结算函数
        args -- 位置参数
        kwargs -- 关键字参数
        """
        self.ops.append(("effect", settle, args, kwargs))

    def follow(self, other: "Plan | None") -> None:
        """
        接上另一个状态机交回的计划
        Keyword arguments:
        other -- 计划
        """
        if other is not None:
            self.ops.extend(other.ops)
            self._shadow.update(other._shadow)
            self._moves.extend(other._moves)

    def get(self, path: str) -> Any:
        """
        读角色数据的 path：本计划已记下的值优先，否则读缓存
        Keyword arguments:
        path -- 属性路径
        Return arguments:
        Any -- 值，类型随属性
        """
        if path in self._shadow:
            return self._shadow[path]
        node: object = cache.character_data[self.character_id]
        for name in path.split("."):
            node = getattr(node, name)
        return node

    def move(self, target_scene: list, show_info_flag: bool = True) -> bool:
        """
        记下一次移动：行动开始时寻路前往 target_scene
        Keyword arguments:
        target_scene -- 目标场景(在地图系统下的绝对坐标)
        show_info_flag -- 是否显示移动信息
        Return arguments:
        bool -- 能否寻路到目标
        """
        self.ops.append(("move", list(target_scene), show_info_flag))
        self._moves.append(route_minutes(self.character_id, target_scene))
        return self._moves[-1] > 0

    def minutes(self) -> int:
        """
        选出的行动要花的分钟数：最后一次写入的时长或寻路时间，至少 1 分钟
        Return arguments:
        int -- 分钟数
        """
        minutes, moves = 0, iter(self._moves)
        for op in self.ops:
            if op[0] == "move":
                minutes = next(moves) or 1
            elif (
                op[0] == "set"
                and op[1:3] == (self.character_id, "behavior.duration")
                and isinstance(op[3], int | float)
            ):
                minutes = int(op[3])
        return max(minutes, 1)


def route_minutes(character_id: int, target_scene: list) -> int:
    """
    干员前往目标场景要花的分钟数，寻路失败时为0
    Keyword arguments:
    character_id -- 角色id
    target_scene -- 目标场景
    Return arguments:
    int -- 分钟数
    """
    scene = list(target_scene)
    scene_str = map_handle.get_map_system_path_str_for_list(scene)
    if (
        normal_config.config_normal.language != "zh_CN"
        and scene_str not in map_handle.scene_path_edge
    ):
        scene = [
            (
                "中枢"
                if part in (_("中枢"), _("控制中枢"))
                else _(part, revert_translation=True)
            )
            for part in scene
        ]
    return int(character_move.character_move(character_id, scene)[3])


@dataclass(frozen=True)
class Choice:
    """
    干员的选择：选中的状态机与它交回的计划；state_machine_id 为 0 时没有可做的行动
    """

    state_machine_id: int
    plan: Plan | None
