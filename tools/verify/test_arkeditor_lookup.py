#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
arkeditor.py 的测试：stop 按证据目录找运行时不取 mode 为 tk 的运行。
mode 为 tk 的运行由 tk_game.py 启动。
limited_run 的 live_runs 与 cmd_stop 换成替身。
测试不启动游戏，也不启动编辑器

用法（在 erArk checkout 根目录）：
    python3 -m unittest tools.verify.test_arkeditor_lookup
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from tools.verify import arkeditor


class TkRun(unittest.TestCase):
    """运行列表里只有一次 mode 为 tk 的运行，它的证据目录就是传给 stop 的目录"""

    def test_stop_leaves_tk_run_with_same_out(self) -> None:
        """stop 以提示先用 start 的消息退出，不调用 limited_run.cmd_stop()"""
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        out = pathlib.Path(tmpdir.name).resolve()
        runs = [{"mode": "tk", "out": str(out), "pid": 4321}]
        with mock.patch.object(
            arkeditor.limited_run, "live_runs", return_value=runs
        ), mock.patch.object(
            arkeditor.limited_run, "cmd_stop", return_value=0
        ) as stop, self.assertRaises(
            SystemExit
        ) as caught:
            arkeditor.main(["stop", "--out", str(out)])
        self.assertIn("start", str(caught.exception.code))
        stop.assert_not_called()
