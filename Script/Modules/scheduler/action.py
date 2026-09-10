"""一次行动的意图；Behavior 保存执行中的状态。"""

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
    """动作编号、分钟数、目标和参数；参数为 Behavior 字段加执行参数 state、continued。"""

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
