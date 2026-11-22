# -*- coding: UTF-8 -*-
"""
行为快照的玩家动作表
====================
每个状态（tests/snapshot_states.py 的 BUILDERS）构建完后，按这里的动作表一步一步推进，每一步录一份快照。
"""

from tests.snapshot_states import (
    CLASSROOM,
    DINING_HALL,
    DOCTOR_ROOM,
    LIBRARY,
    NURSERY,
)


def waits(count: int) -> list:
    """
    动作表里连续 count 次「等待五分钟」
    Keyword arguments:
    count -- 次数
    Return arguments:
    list[tuple] -- 动作
    """
    return [("instruct", "wait", ())] * count


PLANS = {
    "time_stop_h": [
        ("instruct", "kiss_h", ("确定",)),
        ("instruct", "cunnilingus", ()),
        ("instruct", "breast_caress", ()),
        ("instruct", "vaginal_sex", ("正常位", "确定")),
        ("instruct", "normal_sex", ()),
    ]
    + waits(12)
    + [("walk", DINING_HALL)]
    + waits(24)
    + [("walk", LIBRARY)]
    + waits(36)
    + [("walk", DOCTOR_ROOM)]
    + [("until", "sleep", ("8小时", "确定"), 150)]
    + waits(36),
    "family_commission": waits(6)
    + [("walk", CLASSROOM)]
    + [("until", "teach", (), 36)]
    + waits(12)
    + [("walk", NURSERY)]
    + waits(24)
    + [("walk", DINING_HALL)]
    + waits(36)
    + [("walk", LIBRARY)]
    + waits(60)
    + [("walk", DOCTOR_ROOM)]
    + waits(180),
}
""" 状态名: 玩家动作表。动作是 ("instruct", 指令id, 之后按下的按钮)、("walk", 目标场景路径)，
或 ("until", 指令id, 之后按下的按钮, 最多等待的次数)：指令的前提不成立时「等待五分钟」再看，成立时执行它；
每次等待与最后的指令各算一步 """
