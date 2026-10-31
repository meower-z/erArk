# -*- coding: UTF-8 -*-
"""
导入 Tk 主窗口模块后，主窗口与屏幕同宽
======================================
载入游戏，再导入 Tk 主窗口模块 Script.Core.main_frame。导入时就创建主窗口，并设置它最大化。
主窗口宽度应在 SETTLE_SECONDS 秒内达到屏幕宽度。
X11 上的最大化请求由窗口管理器执行，所以测试需要带窗口管理器的显示。
是否有可用的显示由 setUp 里的一个临时 Tk 窗口判断。没有可用的显示时跳过测试。
导入主窗口模块时报的错让测试失败。不开新游戏。
"""

import signal
import time
import tkinter

from tests.slow import remove_parent_guard
from tests.slow.base import SlowTestCase
from tests.world import FullWorld

SETTLE_SECONDS = 5
""" 等待主窗口宽度达到屏幕宽度的最长秒数 """


class TkWindowMaximizedTest(SlowTestCase):
  """导入 Tk 主窗口模块后，主窗口宽度等于屏幕宽度"""

  def setUp(self) -> None:
    """
    设好时限，载入游戏，用一个临时 Tk 窗口确认有可用的显示
    Keyword arguments:
    无
    Return arguments:
    无
    """
    signal.signal(signal.SIGALRM, self._time_up)
    signal.alarm(self.time_limit)
    remove_parent_guard()
    self.world = FullWorld.load()
    try:
      tkinter.Tk().destroy()
    except tkinter.TclError as error:
      self.skipTest(f"没有可用的显示，无法创建 Tk 窗口：{error}")

  def test_window_fills_screen_width(self) -> None:
    """导入主窗口模块后，主窗口宽度在 SETTLE_SECONDS 秒内达到屏幕宽度"""
    from Script.Core import main_frame

    root = main_frame.root
    deadline = time.monotonic() + SETTLE_SECONDS
    root.update()
    while (
        root.winfo_width() != root.winfo_screenwidth()
        and time.monotonic() < deadline
    ):
      time.sleep(0.1)
      root.update()
    self.assertEqual(root.winfo_width(), root.winfo_screenwidth())
