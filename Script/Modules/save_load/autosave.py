"""
save_load 的自动存档
====================
玩家的睡觉结算完时经 update_save 记下"要自动存档"；PickNextAction 的输入钩子排在最外层，
到玩家下一次选行动时（睡觉这一行动已经结束）存档，再原样放行。
存档里因此是玩家选行动那一刻的 GameState，读档后从玩家的选择接着跑。
"""

from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions

calls = 0
""" 钩子被调用的次数 """
_requested = False
""" 玩家的睡觉结算完、还没存的自动存档 """


def update_save() -> None:
    """睡觉结算完：记下自动存档，到玩家下一次选行动时再存"""
    global _requested
    _requested = True


@core.input_hook(core.pick_next_action)
def before_pick(
    who: str,
) -> tuple[str] | core.Intercept[core.Action]:
    """
    轮到玩家选行动且记着自动存档时，经 sleep_settle.update_save 存档，然后原样放行
    Keyword arguments:
    who -- 角色键
    Return arguments:
    tuple -- 原样交给内层的参数
    """
    global calls, _requested
    calls += 1
    if who == actions.PLAYER and _requested:
        _requested = False
        from Script.Settle import sleep_settle

        sleep_settle.update_save()
    return (who,)
