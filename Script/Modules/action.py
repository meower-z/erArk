"""一次行动的意图；Behavior 保存执行中的状态。"""

from copy import deepcopy
from dataclasses import dataclass, field


@dataclass
class Action:
    """动作编号、分钟数、目标和行为参数；延续段结算经过时间。"""

    behavior_id: str
    duration: float
    target: int
    params: dict = field(default_factory=dict)
    state: object = None
    continued: bool = False
    wait_on: tuple | None = None
    after: str | tuple | None = None
    followups: tuple = ()

    @classmethod
    def from_character(cls, character):
        """输入角色对象，返回包含独立行为参数的 Action 意图。"""
        params = {key: deepcopy(value) for key, value in vars(character.behavior).items() if key not in {"behavior_id", "duration", "start_time"}}
        return cls(character.behavior.behavior_id, max(character.behavior.duration, 1), character.target_character_id, params, character.state)

    def apply(self, character, now):
        """输入角色及开始时间，将行动安装为角色的 Behavior；返回 None。"""
        from Script.Core import game_type

        behavior = game_type.Behavior()
        behavior.__dict__.update(deepcopy(self.params))
        behavior.behavior_id = self.behavior_id
        behavior.duration = self.duration
        behavior.start_time = now
        character.behavior = behavior
        character.target_character_id = self.target
        character.state = self.state if self.state is not None else self.behavior_id
