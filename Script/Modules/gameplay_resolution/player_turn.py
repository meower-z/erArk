"""
gameplay_resolution 的玩家回合入口
==================================
内核等玩家选行动时，界面（管理面板、调试面板、设置、聊天 AI 的指令）改游戏数据都经过这一个入口：
tk_ui 的每一轮面板在 run 里执行，面板里改数据的语句照旧直接写缓存，即时生效。
结算途中弹出的面板（射精、被撞见、事件选项）不经过这里，它们的写入本来就属于结算。
"""

from collections.abc import Callable

calls = 0
""" 经过入口的次数 """


def run(write: Callable[[], None]) -> None:
    """
    在玩家的回合里改游戏数据
    Keyword arguments:
    write -- 改数据的函数（tk_ui 的一轮面板）
    """
    global calls
    calls += 1
    write()
