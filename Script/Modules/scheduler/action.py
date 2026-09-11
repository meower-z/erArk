"""Action：一个准备执行、尚未开始的行动。

游戏用角色身上的 Behavior 对象记录"正在做什么"（行动编号、开始时刻、时长、目标等）。
Action 是同一件事在开始之前的写法：行动编号、占用分钟数、目标角色编号，以及要写进 Behavior 的其他字段（params）。
调度器（scheduler 包，负责按时间执行行动）与 NPC AI 之间传递的是 Action；执行时用 apply() 把它写成角色的 Behavior。

params 里还可以带两个不写进 Behavior 的执行参数：state 是执行时写进角色 state 字段的值（不给则用行动编号）；
continued 表示本段延续上一段的同一行动（例如睡觉的第二个 30 分钟），不重复施加只在开始时发生一次的效果。
"""

from copy import deepcopy
from dataclasses import dataclass, field

STATE = "state"
""" 执行参数：安装行动时写入角色状态 """
CONTINUED = "continued"
""" 执行参数：本段延续上一段同一行动，不重复一次性结算 """
EXECUTION_PARAMS = {STATE, CONTINUED}
""" 不写入 Behavior 的执行参数 """


@dataclass
class Action:
    """一个准备执行、尚未开始的行动；各字段的含义见本文件开头的说明。"""

    behavior_id: str
    duration: float
    target: int
    params: dict = field(default_factory=dict)

    @property
    def continued(self) -> bool:
        """无需参数，返回本段是否延续上一段同一行动。"""
        return bool(self.params.get(CONTINUED, False))

    @classmethod
    def from_character(cls, character, **params):
        """输入角色对象及追加的执行参数，返回包含独立行为参数的 Action 意图。"""
        values = {key: deepcopy(value) for key, value in vars(character.behavior).items() if key not in {"behavior_id", "duration", "start_time"}}
        values[STATE] = character.state
        values.update(params)
        return cls(character.behavior.behavior_id, max(character.behavior.duration, 1), character.target_character_id, values)

    def apply(self, character, now):
        """输入角色及开始时间，将行动安装为角色的 Behavior；返回 None。"""
        from Script.Core import game_type

        params = deepcopy(self.params)
        state = params.pop(STATE, None)
        for key in EXECUTION_PARAMS:
            params.pop(key, None)
        behavior = game_type.Behavior()
        behavior.__dict__.update(params)
        behavior.behavior_id = self.behavior_id
        behavior.duration = self.duration
        behavior.start_time = now
        character.behavior = behavior
        character.target_character_id = self.target
        character.state = state if state is not None else self.behavior_id
