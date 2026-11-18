"""
游戏流程
========
内核（Script/Kernel/core.py）一步一步推进游戏。in_resolution 告诉调用方，内核此刻是否在一步的结算里。
调用方在结算里经 plan_queue 把行动排进计划队列，不在结算里时经 player_pick.choose 当场定下玩家的行动。
"""

from Script.Kernel import core


def in_resolution() -> bool:
    """
    是否在结算里（事件、行动开始、时间流逝），不在玩家的选择里
    Return arguments:
    bool -- 内核在一步的结算里时为真
    """
    return core.in_settlement()
