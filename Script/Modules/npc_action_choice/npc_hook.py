"""
npc_action_choice 的内核钩子：干员的 PickNextAction 输出钩子
==============================================================
内核本体给要选行动的角色一个 1 分钟的 Idle。
这个输出钩子把干员的 Idle 换成 gameplay_resolution 的 actions.npc_action 交回的行动。
到期且空闲的干员先由 choose.choose 选出行动，选择交给 npc_action，留到行动开始时写进缓存。
外层的 tk_ui 截下玩家的选择，外层的计划队列截下队列里有行动的角色的选择，这两种选择都不经过这个钩子。
"""

from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions
from Script.Modules.npc_action_choice import choose


@core.output_hook(core.pick_next_action)
def pick_npc_action(
    result: tuple[core.Action, core.Effects],
) -> tuple[core.Action, core.Effects]:
    """
    干员选下一个行动
    Keyword arguments:
    result -- 内层给出的行动与效果
    Return arguments:
    tuple -- 选出的行动，与内层的效果加上提前结束的行动
    """
    idle, effects = result
    who = idle.who
    if who == actions.PLAYER:
        return result
    character_id = int(who)
    chosen = None
    if actions.wants_choice(character_id):
        chosen = choose.choose(character_id)
    act = actions.npc_action(who, chosen)
    return (act, (*effects, *actions.resync(core.state(), skip=who)))
