"""
npc_action_choice 的内核钩子：干员的 PickNextAction 输出钩子
==============================================================
内核本体给要选行动的角色一个 1 分钟的 Idle。这个输出钩子把干员的 Idle 换成 choose.choose 选出的行动。
外层的 tk_ui 截下玩家的选择，外层的计划队列截下队列里有行动的角色的选择，这两种选择都不经过这个钩子。
"""

from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions
from Script.Modules.npc_action_choice import choose


@core.output_hook(core.pick_next_action)
def pick_npc_action(idle: core.Action) -> core.Action:
    """
    干员选下一个行动
    Keyword arguments:
    idle -- 内层给出的行动
    Return arguments:
    Action -- 选出的行动
    """
    if idle.who == actions.PLAYER:
        return idle
    return choose.choose(int(idle.who))
