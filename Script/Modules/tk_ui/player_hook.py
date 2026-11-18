"""
tk_ui 的内核钩子：玩家的 PickNextAction
======================================
内核在最外层跑。玩家的行动结束时内核来问下一个：
- 游戏里（update.run_game 启动的内核），这个钩子跑主面板循环，
  直到界面经 update.game_update_flow(分钟数) 定下玩家的行动；
  回到标题或读档后抛 PlayerTurn，结束这次 core.run。
- 脚本里（测试直接调用指令，update.game_update_flow 启动的内核），队列空了就抛 PlayerTurn，回到脚本。
game_update_flow 把玩家此刻的行为排进队列，钩子取队首交回内核，它的结算在内核随后的 StartAction 里跑。
"""

from Script.Core import cache_control, constant, game_type
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions
from Script.Modules.tk_ui import player_pick

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

PRE_GAME_PANELS = (constant.Panel.TITLE, constant.Panel.CREATOR_CHARACTER)
""" 不在游戏里的面板：主面板循环走到这里时内核停下 """

_queued: list[tuple[game_type.Behavior, int]] = []
""" 排队的玩家行动：(行为, 名义分钟数) """
_mode: str | None = None
""" 内核在跑时为 "game"（主面板循环在玩家的选择里）或 "script"（脚本调用指令），不在跑时为 None """
_in_pick = False
""" 是否在玩家的选择里（主面板循环或取队首） """
_restart = False
""" 读档等换了缓存：下一次玩家的选择结束这次 core.run """


class PlayerTurn(Exception):
    """轮到玩家选行动而界面没有给出（脚本里），或游戏离开了主面板循环：结束这次 core.run"""


def running() -> bool:
    """
    内核是否在跑
    Return arguments:
    bool -- 在跑时为真
    """
    return _mode is not None


def in_pick() -> bool:
    """
    是否在玩家的选择里
    Return arguments:
    bool -- 在玩家的选择里时为真
    """
    return _in_pick


def start(mode: str) -> None:
    """
    内核开始跑
    Keyword arguments:
    mode -- "game" 或 "script"
    """
    global _mode, _restart
    _mode, _restart = mode, False


def stop() -> None:
    """内核停下"""
    global _mode
    _mode = None


def clear() -> None:
    """清空队列；内核在跑时让它在玩家的下一次选择结束（读档、出错后）"""
    global _restart
    _queued.clear()
    _restart = running()


def queue_action(add_time: int) -> None:
    """
    把玩家此刻的行为排进队列，行动的名义分钟数为 add_time
    Keyword arguments:
    add_time -- 名义分钟数
    """
    _queued.append((cache.character_data[0].behavior, add_time))


@core.input_hook(core.pick_next_action)
def pick_player_action(
    who: str,
) -> tuple[str] | core.Intercept[tuple[core.Action, core.Effects]]:
    """
    玩家选下一个行动：取队首；队列空时游戏里跑主面板循环等界面定下，脚本里结束这次 core.run
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Intercept -- 队首的行动；干员原样交给内层
    """
    global _in_pick
    if who != actions.PLAYER:
        return (who,)
    _in_pick = True
    try:
        while not _queued:
            if _mode != "game" or _restart:
                raise PlayerTurn
            if cache.now_panel_id in PRE_GAME_PANELS:
                raise PlayerTurn
            player_pick.pick()
    finally:
        _in_pick = False
    behavior, nominal = _queued.pop(0)
    if cache.character_data[0].behavior is not behavior:
        cache.character_data[0].behavior = behavior
    duration = max(nominal, 0)
    act = core.new_action(
        actions.behave,
        who,
        duration,
        actions.mirror(behavior, minutes=nominal),
    )
    return core.Intercept((act, ()))
