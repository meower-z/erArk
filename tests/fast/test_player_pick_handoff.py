# -*- coding: UTF-8 -*-
"""
玩家的选择在界面线程里跑面板，定下行动时停下
============================================
player_pick.pick 让界面线程跑到下一个停点：一轮面板跑完，或面板经 update.game_update_flow 定下了玩家的行动。
停在 game_update_flow 里的面板在下一次 pick 时从那里接着跑；面板里抛出的异常在调用 pick 的线程里重新抛出。
测试用假面板代替真面板，不跑内核：player_hook 的状态设成游戏里玩家的选择之中。
"""

import threading
from collections.abc import Callable
from unittest import mock

from Script.Core import constant, io_init
from Script.Design import update
from Script.Modules.gameplay_resolution import player_turn
from Script.Modules.tk_ui import player_hook, player_pick
from tests.fast.base import FastTestCase

PANEL = 9001
""" 假面板的面板id """


class EndThread(Exception):
    """让界面线程结束的异常"""


class PlayerPickHandoffTest(FastTestCase):
    """pick 与 end_pick 在内核线程与界面线程之间交接控制"""

    def setUp(self) -> None:
        """
        造出玩家，换上假面板，界面输出不送往界面
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.log: list[str] = []
        self.panel: Callable[[], None] = self.choose_then_continue
        self.enterContext(
            mock.patch.dict(constant.panel_data, {PANEL: self.run_panel})
        )
        self.enterContext(
            mock.patch.object(io_init, "put_queue", lambda message: None)
        )
        self.enterContext(mock.patch.object(self.cache, "now_panel_id", PANEL))
        self.enterContext(mock.patch.object(player_hook, "_mode", "game"))
        self.enterContext(mock.patch.object(player_hook, "_in_pick", True))
        self.enterContext(mock.patch.object(player_hook, "_queued", []))
        self.addCleanup(self.end_ui_thread)

    def run_panel(self) -> None:
        """
        面板id PANEL 对应的面板：跑测试此刻换上的假面板
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.panel()

    def end_ui_thread(self) -> None:
        """
        让留下的界面线程跑完手上的一轮，在下一轮结束，下一个测试从新线程开始
        Keyword arguments:
        无
        Return arguments:
        无
        """
        if player_pick._ui is None:
            return

        def end() -> None:
            raise EndThread

        self.panel = end
        for _ in range(2):
            try:
                player_pick.pick()
            except EndThread:
                return
        self.fail("界面线程停在一轮面板中途，两次选择后仍没有结束")

    def choose_then_continue(self) -> None:
        """
        假面板：定下行动，结算之后再往下走
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.log.append(f"选择 {threading.current_thread().name}")
        update.game_update_flow(5)
        self.log.append(f"结算之后 排队 {len(player_hook._queued)}")
        player_hook._queued.clear()

    def test_panel_stops_at_chosen_action(self) -> None:
        """第一次 pick 停在定下行动处，第二次从那里接着跑完这一轮；面板跑在界面线程里，经玩家回合入口"""
        rounds = player_turn.calls
        player_pick.pick()
        self.assertEqual(self.log, ["选择 tk_ui"], "停在定下行动处")
        self.assertEqual(len(player_hook._queued), 1, "行动已排进队列")
        player_pick.pick()
        self.assertEqual(
            self.log, ["选择 tk_ui", "结算之后 排队 1"], "下一次选择时接着跑"
        )
        self.assertEqual(
            player_turn.calls - rounds, 1, "一轮面板经过玩家回合入口一次"
        )
        player_pick.pick()
        self.assertEqual(self.log[2], "选择 tk_ui", "再下一次选择跑新的一轮")

    def test_end_pick_outside_ui_thread_returns(self) -> None:
        """不在界面线程里调用 end_pick（脚本直接调用指令）时立即返回"""
        player_pick.end_pick()
        self.assertEqual(self.log, [])

    def test_panel_error_raised_in_pick(self) -> None:
        """面板里抛出的异常在 pick 里重新抛出；之后的 pick 换一个新的界面线程照常跑"""

        def broken() -> None:
            raise ValueError("面板出错")

        self.panel = broken
        with self.assertRaises(ValueError):
            player_pick.pick()
        self.assertIsNone(player_pick._ui)
        self.panel = self.choose_then_continue
        player_pick.pick()
        self.assertEqual(self.log, ["选择 tk_ui"])
