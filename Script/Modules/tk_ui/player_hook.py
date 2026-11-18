"""
tk_ui 的内核钩子：玩家的 PickNextAction
======================================
玩家的行动结束、队列里也没有排着的行动时，内核来问下一个：钩子反复跑一轮选择（player_pick.chooser），
直到界面经 player_pick.choose 定下行动（抛出 Chosen），把它交回内核。
一轮选择跑完而没有定下行动（例如翻看了一个零时间的面板）时，再跑一轮。
选择里读档会经 core.reset_state 中止这次选择；回到标题抛出 LeftGame，两者都直接穿过这里。
"""

from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions
from Script.Modules.tk_ui import player_pick


@core.input_hook(core.pick_next_action)
def pick_player_action(
    who: str,
) -> tuple[str] | core.Intercept[core.Action]:
    """
    玩家选下一个行动：跑选择直到界面定下行动
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Intercept -- 玩家定下的行动；干员原样交给内层
    """
    if who != actions.PLAYER:
        return (who,)
    while True:
        try:
            player_pick.chooser()
        except player_pick.Chosen as chosen:
            return core.Intercept(chosen.action)
