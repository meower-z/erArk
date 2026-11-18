"""
游戏流程：内核（Script/Kernel/core.py）在最外层推进时间，game_update_flow 只给玩家排行动
===========================================================================================
游戏里主面板循环跑在玩家的 PickNextAction 里（Script/Modules/tk_ui/player_hook.py）：界面定好玩家的行为后调用
game_update_flow(分钟数)，这一行动排进队列，玩家的选择随之结束，行动的结算在内核随后的 StartAction 里跑。
脚本（测试、无界面的检查）在内核外直接调用指令时，game_update_flow 排进行动后跑内核，直到玩家下一次要选行动。
"""

from Script.Core import cache_control, py_cmd
from Script.Design import character_behavior, game_time
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.gameplay_resolution import (
    actions,
    events,
    npc_start,
    plan_queue,
    pre_pick,
)
from Script.Modules.save_load import kernel_state
from Script.Modules.tk_ui import player_hook, player_pick

NESTED_RAISES = True
""" 玩家选择以外的结算途中调用 game_update_flow 时是否抛 NestedResolution。
关着时照旧嵌套：时间推进、整个行为循环再跑一遍，再往里一层直接返回 """


class NestedResolution(RuntimeError):
    """玩家选择以外的结算途中调用了 game_update_flow"""


def in_resolution() -> bool:
    """
    是否在玩家选择以外的结算里（行动开始、时间流逝、事件）
    Return arguments:
    bool -- 内核在跑且不在玩家的选择里时为真
    """
    return player_hook.running() and not player_hook.in_pick()


def game_update_flow(add_time: int) -> None:
    """
    给玩家排一个行动：玩家此刻的行为，名义上持续 add_time 分钟
    Keyword arguments:
    add_time -- 行动的分钟数
    """
    if in_resolution():
        if NESTED_RAISES:
            raise NestedResolution(
                f"game_update_flow({add_time}) 在结算途中被调用"
            )
        _nested_flow(add_time)
        return
    player_hook.queue_action(add_time)
    if player_hook.running():
        player_pick.end_pick()
        return
    run_kernel("script")
    py_cmd.focus_cmd()


def _nested_flow(add_time: int) -> None:
    """
    结算途中的 game_update_flow：时间推进 add_time，整个行为循环再跑一遍；在它里面再调用时直接返回
    Keyword arguments:
    add_time -- 推进的分钟数
    """
    cache = cache_control.cache
    if cache.game_update_flow_running:
        return
    cache.game_update_flow_running = 1
    try:
        game_time.sub_time_now(add_time)
        character_behavior.init_character_behavior()
        py_cmd.focus_cmd()
    finally:
        cache.game_update_flow_running = 0


def run_game() -> None:
    """游戏里跑内核：主面板循环在玩家的选择里，回到标题或读档后返回"""
    run_kernel("game")


def run_kernel(mode: str) -> None:
    """
    从缓存对齐的 GameState 跑内核，直到玩家的选择结束这次运行
    Keyword arguments:
    mode -- "game"（主面板循环在玩家的选择里）或 "script"（队列空时返回）
    """
    game = actions.resynced(kernel_state.take())
    player_hook.start(mode)
    try:
        core.run(game, load_order.LOAD_ORDER)
    except player_hook.PlayerTurn:
        return
    except BaseException:
        reset_kernel(None)
        raise
    finally:
        player_hook.stop()


def reset_kernel(saved: dict | None) -> None:
    """
    换了缓存（读档）或内核出错后，丢掉内核状态，下次跑内核时从存档数据或缓存重建
    Keyword arguments:
    saved -- 存档里的内核状态，没有时为 None
    """
    kernel_state.load_data(saved)
    actions.forget()
    plan_queue.forget()
    npc_start.forget()
    pre_pick.forget()
    events.forget()
    player_hook.clear()
