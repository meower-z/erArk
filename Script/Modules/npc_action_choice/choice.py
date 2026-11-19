"""
npc_action_choice 选出的行动：状态机交回的计划
==============================================
状态机只读缓存。它把选出的行为（行为id、分钟数、状态、交互对象、自己身上的标记）、要去的场景、
要显示的文字、行动的种类与种类的参数记在 Plan 里交回；Plan.action 把它变成一个内核行动，
行动数据是 gameplay_resolution 的 Intent，只含 JSON 值。行动开始时由 gameplay_resolution 的 starts 照着写进缓存。
"""

from typing import Any, cast

from Script.Config import normal_config
from Script.Core import cache_control, constant, game_type, get_text
from Script.Design import character_move, map_handle
from Script.Kernel import core
from Script.Modules.gameplay_resolution import intent

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_ = get_text._
""" 翻译api """

FIELD_ROOTS = ("behavior", "sp_flag", "action_info", "work")
""" Plan.set 能写的角色数据的根 """


def to_json(value: object) -> core.JSON:
    """
    检查 value 是 JSON 值并交回它（列表换成元组，与内核冻结后的形状一样）
    Keyword arguments:
    value -- 要记进意图的值
    Return arguments:
    JSON -- 同一个值
    """
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, list | tuple):
        return tuple(to_json(item) for item in value)
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return {k: to_json(v) for k, v in value.items()}
    raise TypeError(f"意图里只能记 JSON 值：{value!r}")


class Plan:
    """一个角色选出的行动：意图的构造器"""

    def __init__(self, character_id: int) -> None:
        """
        Keyword arguments:
        character_id -- 选行动的角色id
        """
        self.character_id = character_id
        self.intent: intent.Intent = {
            "behavior_id": constant.Behavior.SHARE_BLANKLY,
            "minutes": 1,
        }
        self.action_kind = "Behavior"
        self._shadow: dict[str, object] = {}

    def set(self, path: str, value: object) -> None:
        """
        记下行动开始时写在自己身上的一个值
        Keyword arguments:
        path -- 属性路径："target_character_id"、"state"，或以 behavior、sp_flag、action_info、work 开头，
            如 "behavior.duration"
        value -- 要写的 JSON 值
        """
        data = to_json(value)
        if path == "target_character_id":
            self.intent["target"] = int(cast(int, data))
        elif path == "state":
            self.intent["state"] = cast(int | str, data)
        elif path == "behavior.behavior_id":
            self.intent["behavior_id"] = str(data)
        elif path == "behavior.duration":
            self.intent["minutes"] = int(cast(int, data))
        elif path.split(".")[0] in FIELD_ROOTS and "." in path:
            self.intent.setdefault("fields", {})[path] = data
        else:
            raise ValueError(f"Plan.set 不能写 {path!r}")
        self._shadow[path] = value

    def draw(
        self, text: str, wait: bool = False, style: str | None = None
    ) -> None:
        """
        记下行动开始时显示的一段文字
        Keyword arguments:
        text -- 文字
        wait -- 是否等玩家确认（WaitDraw），记在参数 say_wait
        style -- 文字样式，None 为默认，记在参数 say_style
        """
        self.intent["say"] = text
        if wait:
            self.arg("say_wait", True)
        if style is not None:
            self.arg("say_style", style)

    def kind(self, name: str) -> None:
        """
        定下行动的种类：内核行动是 gameplay_resolution.<name>，开始时跑这个种类的开始代码
        Keyword arguments:
        name -- 种类
        """
        self.action_kind = name

    def arg(self, key: str, value: object) -> None:
        """
        记下种类自己的一个参数
        Keyword arguments:
        key -- 参数名
        value -- JSON 值
        """
        self.intent.setdefault("args", {})[key] = to_json(value)

    def follow(self, other: "Plan") -> None:
        """
        接上另一个状态机交回的计划：它记下的值盖过本计划的
        Keyword arguments:
        other -- 计划
        """
        fields = {
            **self.intent.get("fields", {}),
            **other.intent.get("fields", {}),
        }
        args = {**self.intent.get("args", {}), **other.intent.get("args", {})}
        self.intent.update(other.intent)
        if fields:
            self.intent["fields"] = fields
        if args:
            self.intent["args"] = args
        if other.action_kind != "Behavior":
            self.action_kind = other.action_kind
        self._shadow.update(other._shadow)

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
        记下一次移动：行动开始时寻路前往 target_scene；寻路失败时改记原地等待1分钟
        Keyword arguments:
        target_scene -- 目标场景(在地图系统下的绝对坐标)
        show_info_flag -- 是否显示移动信息
        Return arguments:
        bool -- 能否寻路到目标
        """
        minutes = route_minutes(self.character_id, target_scene)
        self.intent["target"] = self.character_id
        if minutes <= 0:
            self.intent.pop("move", None)
            self.intent["behavior_id"] = constant.Behavior.WAIT
            self.intent["minutes"] = 1
            self.intent["state"] = constant.CharacterStatus.STATUS_WAIT
            return False
        self.intent["move"] = {
            "to": [str(part) for part in target_scene],
            "show": show_info_flag,
        }
        self.intent["behavior_id"] = constant.Behavior.MOVE
        self.intent["minutes"] = minutes
        self.intent["state"] = constant.CharacterStatus.STATUS_MOVE
        return True

    def action(self) -> core.Action:
        """
        选出的行动：从此刻开始，时长是意图的分钟数，干员至少 1 分钟
        Return arguments:
        Action -- 内核行动
        """
        return intent.behavior_action(
            self.character_id, self.intent, self.action_kind
        )


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
