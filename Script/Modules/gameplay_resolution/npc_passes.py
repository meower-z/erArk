"""
gameplay_resolution 的干员结算顺序
==================================
一回合（一个玩家行动）里，干员按到期先后结算，同时刻按角色id：内核的顺序。
内核在干员的行动结束时经 npc_action_choice.choose 调用 settle_npc_pass；
回合末与结算途中嵌套的旧循环调用 run_npc_passes。
"""

import datetime

from Script.Core import cache_control, constant, game_type
from Script.Design import character_behavior, game_time

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """


def npc_due(
    character_id: int, pl_start_time: datetime.datetime
) -> datetime.datetime:
    """
    干员本回合下一次该结算的时刻：当前行为的结束（空闲时是它的开始），
    不早于玩家行动的开始、不晚于 cache.game_time
    Keyword arguments:
    character_id -- 角色id
    pl_start_time -- 玩家行动的开始时间
    Return arguments:
    datetime -- 到期时刻
    """
    behavior = cache.character_data[character_id].behavior
    end = behavior.start_time
    if behavior.behavior_id != constant.Behavior.SHARE_BLANKLY:
        end = game_time.get_sub_date(minute=behavior.duration, old_date=end)
    return min(max(end, pl_start_time), cache.game_time)


def settle_npc_pass(
    character_id: int, pl_start_time: datetime.datetime
) -> None:
    """
    干员的一次结算；结算后空闲到本回合结束的干员本回合结算完
    Keyword arguments:
    character_id -- 角色id
    pl_start_time -- 玩家行动的开始时间
    """
    character_behavior.character_behavior(
        character_id, cache.game_time, pl_start_time
    )
    behavior = cache.character_data[character_id].behavior
    if (
        behavior.behavior_id == constant.Behavior.SHARE_BLANKLY
        and behavior.start_time >= cache.game_time
    ):
        cache.over_behavior_character.add(character_id)


def run_npc_passes(
    id_list: tuple[int, ...], pl_start_time: datetime.datetime
) -> None:
    """
    按到期先后结算本回合还没结算完的干员，同时刻按角色id，直到都结算完
    Keyword arguments:
    id_list -- 本回合结算的干员，按id
    pl_start_time -- 玩家行动的开始时间
    """
    while True:
        todo = [c for c in id_list if c not in cache.over_behavior_character]
        if not todo:
            return
        character_id = min(todo, key=lambda c: (npc_due(c, pl_start_time), c))
        settle_npc_pass(character_id, pl_start_time)
