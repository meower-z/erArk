# -*- coding: UTF-8 -*-
"""游戏主流程：唯一的循环，标题与建角色面板在这里显示，进了游戏就一步一步推进内核"""

from Script.Core import py_cmd, constant, cache_control, game_type

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """


def start_frame() -> None:
    """
    游戏主流程：加载内核的模块一次，然后不在游戏里时显示当前面板，在游戏里时推进内核一步。
    玩家的选择在内核的一步里跑主面板（tk_ui 的 player_hook）；回到标题时它抛出 LeftGame，在这里接住
    """
    from Script.Kernel import core
    from Script.Modules import load_order
    from Script.Modules.tk_ui import player_pick

    core.load(load_order.LOAD_ORDER)
    while True:
        if cache.now_panel_id in player_pick.PRE_GAME_PANELS:
            py_cmd.clr_cmd()
            py_cmd.focus_cmd()
            constant.panel_data[cache.now_panel_id]()
            continue
        try:
            core.step()
        except player_pick.LeftGame:
            pass
