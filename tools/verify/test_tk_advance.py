#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
测试 tk.py advance 在等待提示时点的位置
不启动游戏

用法（在 erArk checkout 根目录）：
    python3 -m unittest tools.verify.test_tk_advance
"""

import contextlib
import io
import sys
import tempfile
import unittest
from unittest import mock

from tools.verify import tk


class TkAdvance(unittest.TestCase):
  """检查 tk.py advance 的鼠标落点。load_state、read_probe、xdo 与 act 都换成假的。"""

  def test_button_over_log(self) -> None:
    """日志里有按钮的等待提示下，advance 只把鼠标移到输入框中心"""
    probe = {
        "awaiting": "wait",
        "buttons": {
            "阿米娅": [9, 544],
            "可露希尔": [639, 544],
            "陈": [1269, 544],
            "黎": [639, 572],
            "返回": [9, 628],
        },
        "input": [619, 1066],
        "ts": 0,
    }
    calls = []

    def xdo(state: dict, *args: str) -> str:
      """
      代替 tk.xdo，记下参数而不运行 xdotool
      参数：
          state (dict): 实例状态
          args (str): xdotool 参数
      返回：
          str: 空串
      """
      calls.append(args)
      return ""

    tmpdir = tempfile.TemporaryDirectory()
    self.addCleanup(tmpdir.cleanup)
    with (
        mock.patch.object(sys, "argv", ["tk.py", "advance"]),
        mock.patch.object(
            tk,
            "load_state",
            return_value={"out": tmpdir.name, "window": "11", "display": ":51"},
        ),
        mock.patch.object(tk, "xdo", xdo),
        mock.patch.object(tk, "read_probe", return_value=probe),
        mock.patch.object(tk, "act"),
        contextlib.redirect_stdout(io.StringIO()),
    ):
      tk.main()
    moves = [
        [int(args[3]), int(args[4])] for args in calls if args[0] == "mousemove"
    ]
    self.assertEqual(moves, [probe["input"]])


if __name__ == "__main__":
  unittest.main()
