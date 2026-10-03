"""行动与时间工具：一个尚未开始的行动（Action），以及按游戏日历计算时长的几个函数"""

import datetime
from copy import deepcopy
from dataclasses import dataclass

from Script.Core import constant, game_type
from Script.Design import game_time

WAIT_RECHECK_MINUTES = 5
""" 等待别人的行动时，相邻两次复查至多相隔的分钟数 """


@dataclass
class Action:
    """
    一个尚未开始的行动：要写到角色身上的行为副本、交互对象、状态，以及是否延续上一段\n
    continued 为真时本段延续上一段同一行动（如睡眠的第二个 30 分钟），不重复结算只在开始时发生一次的效果
    """

    behavior: game_type.Behavior
    target: int
    state: int
    continued: bool = False

    @classmethod
    def of(cls, character: game_type.Character, continued: bool = False):
        """
        复制角色身上已写好的行为，作为一个行动
        Keyword arguments:
        character -- 角色对象
        continued -- 是否延续上一段同一行动
        Return arguments:
        Action -- 行动，时长至少 1 分钟
        """
        behavior = deepcopy(character.behavior)
        behavior.duration = max(behavior.duration, 1)
        return cls(behavior, character.target_character_id, character.state, continued)

    def apply(self, character: game_type.Character, now: datetime.datetime):
        """
        把行动写成角色当前的行为，开始时刻为 now
        Keyword arguments:
        character -- 角色对象
        now -- 开始时刻
        Return arguments:
        None
        """
        character.behavior = deepcopy(self.behavior)
        character.behavior.start_time = now
        character.target_character_id = self.target
        character.state = self.state


def minutes_between(start: datetime.datetime, end: datetime.datetime) -> float:
    """
    按游戏日历计算两个时刻之间的分钟数
    Keyword arguments:
    start -- 起始时刻
    end -- 结束时刻
    Return arguments:
    float -- 分钟数，end 早于 start 时为负
    """
    return (game_time.to_game_time(end) - start).total_seconds() / 60


def behavior_end(behavior: game_type.Behavior) -> datetime.datetime:
    """
    取行为的结束时刻
    Keyword arguments:
    behavior -- 行为对象
    Return arguments:
    datetime.datetime -- 开始时刻加时长
    """
    return game_time.get_sub_date(minute=behavior.duration, old_date=behavior.start_time)


def wait_slice(remaining: float) -> float:
    """
    等待别人的行动时本段等多久：至多五分钟、至少一分钟，对方行动结束时恰好放开
    Keyword arguments:
    remaining -- 对方行动的剩余分钟数
    Return arguments:
    float -- 本段等待的分钟数
    """
    return max(1, min(WAIT_RECHECK_MINUTES, remaining))


def wait_action(target: int, minutes: float, continued: bool = False, wait_on_behavior_id: str = "") -> Action:
    """
    构造一个等待行动
    Keyword arguments:
    target -- 交互对象id
    minutes -- 等待分钟数
    continued -- 是否不结算一次性效果
    wait_on_behavior_id -- 所等待的对方行为id，空串表示不复查对方
    Return arguments:
    Action -- 等待行动
    """
    behavior = game_type.Behavior()
    behavior.behavior_id = constant.Behavior.WAIT
    behavior.duration = minutes
    behavior.wait_on_behavior_id = wait_on_behavior_id
    return Action(behavior, target, constant.CharacterStatus.STATUS_WAIT, continued)


def continue_current(character: game_type.Character, minutes: float) -> Action:
    """
    构造延续角色当前行为的一段
    Keyword arguments:
    character -- 角色对象
    minutes -- 本段分钟数
    Return arguments:
    Action -- 延续片段，时长至少 1 分钟
    """
    action = Action.of(character, continued=True)
    action.behavior.duration = max(minutes, 1)
    return action
