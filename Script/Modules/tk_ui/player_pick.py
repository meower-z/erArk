"""
tk_ui 的玩家选择
================
主面板循环跑在自己的界面线程里，和跑内核的线程轮流执行，同一时刻只有一个在跑。
player_hook 的 PickNextAction 钩子在游戏里调用 pick：界面线程从上次停下的地方接着跑，到下一个停点把控制交回内核。
停点有两个：
- 一轮面板跑完：player_hook 随后检查读档、回标题，没有行动时再调用 pick；
- 界面经 update.game_update_flow 定下了玩家的行动（end_pick）：内核结算这一行动、推进时间，
  到玩家下一次选择时界面从 game_update_flow 之后接着跑，所以面板总在行动结算之后才往下走、重画。
每一轮面板经 gameplay_resolution 的玩家回合入口 player_turn.run 执行，面板里改游戏数据的语句都在它里面。
"""

import threading

from Script.Core import cache_control, constant, game_type, py_cmd
from Script.Modules.gameplay_resolution import player_turn

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

calls = 0
""" 跑过的面板轮数 """


class _UiThread:
    """跑主面板循环的界面线程，与内核线程用两个信号量交接控制"""

    def __init__(self) -> None:
        """建好线程与信号量，线程在第一次 resume 时开始跑面板"""
        self.ui_turn = threading.Semaphore(0)
        """ 内核线程放行界面线程 """
        self.kernel_turn = threading.Semaphore(0)
        """ 界面线程把控制交回内核线程 """
        self.error: BaseException | None = None
        """ 界面线程里抛出、要在内核线程里重新抛出的异常 """
        self.thread = threading.Thread(
            target=self._main, name="tk_ui", daemon=True
        )
        """ 界面线程 """
        self.thread.start()

    def _main(self) -> None:
        """界面线程：一轮一轮跑面板，每轮之后交回控制；异常交给内核线程，线程随之结束"""
        self.ui_turn.acquire()
        try:
            while True:
                player_turn.run(_round)
                self.hand_back()
        except BaseException as error:
            self.error = error
            self.kernel_turn.release()

    def hand_back(self) -> None:
        """在界面线程里调用：控制交回内核，等玩家下一次选择时再接着跑"""
        self.kernel_turn.release()
        self.ui_turn.acquire()

    def resume(self) -> None:
        """
        在内核线程里调用：界面线程跑到下一个停点
        界面线程抛出的异常在这里重新抛出
        """
        global _ui
        self.ui_turn.release()
        self.kernel_turn.acquire()
        if self.error is not None:
            error, self.error = self.error, None
            _ui = None
            raise error


_ui: _UiThread | None = None
""" 界面线程；还没开始或上一个因异常结束时为 None """


def _round() -> None:
    """主面板循环的一轮：显示当前面板id对应的面板"""
    global calls
    calls += 1
    py_cmd.clr_cmd()
    py_cmd.focus_cmd()
    constant.panel_data[cache.now_panel_id]()


def pick() -> None:
    """玩家的选择：界面线程跑到下一个停点（一轮面板跑完，或定下了玩家的行动）"""
    global _ui
    if _ui is None:
        _ui = _UiThread()
    _ui.resume()


def end_pick() -> None:
    """
    界面定下了玩家的行动（update.game_update_flow 已把它排进队列）：
    在界面线程里时停在这里，控制交回内核；内核结算这一行动后、玩家下一次选择时从这里返回
    不在界面线程里（脚本直接调用指令）时什么也不做
    """
    ui = _ui
    if ui is not None and threading.current_thread() is ui.thread:
        ui.hand_back()
