# -*- coding: UTF-8 -*-
"""游戏主流程：循环运行当前面板id对应的面板"""

from Script.Core import py_cmd, constant, cache_control, game_type

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """


def start_frame() -> None:
    """
    游戏主流程：标题与建角色面板在这里循环；进了游戏就跑内核，主面板循环在玩家的选择里
    """
    from Script.Design import update

    while True:
        if cache.now_panel_id in (
            constant.Panel.TITLE,
            constant.Panel.CREATOR_CHARACTER,
        ):
            py_cmd.clr_cmd()
            py_cmd.focus_cmd()
            constant.panel_data[cache.now_panel_id]()
        else:
            update.run_game()
