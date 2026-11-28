#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
测试 tk.py 的推进落点、等待态点击拦截、翻页变化检测及 tk_probe 的分页停顿上报
不启动游戏

用法（在 erArk checkout 根目录）：
    python3 -m unittest tools.verify.test_tk_advance
"""

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tools.verify import tk, tk_probe


class TkAdvance(unittest.TestCase):
    """检查 tk.py 的推进落点、等待态点击拦截与翻页变化检测，相关依赖替换为替身。"""

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
                return_value={
                    "out": tmpdir.name,
                    "window": "11",
                    "display": ":51",
                },
            ),
            mock.patch.object(tk, "xdo", xdo),
            mock.patch.object(tk, "read_probe", return_value=probe),
            mock.patch.object(tk, "act"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            tk.main()
        moves = [
            [int(args[3]), int(args[4])]
            for args in calls
            if args[0] == "mousemove"
        ]
        self.assertEqual(moves, [probe["input"]])

    def run_tk(self, probe: dict, *argv: str) -> list:
        """
        用替身替换 load_state、read_probe、xdo 与 act 后运行一次 tk.main
        参数：
            probe (dict): read_probe 返回的探针内容
            argv (str): 传给 tk.py 的动作与参数
        返回：
            list: xdo 收到的调用参数列表
        """
        calls = []
        with (
            mock.patch.object(sys, "argv", ["tk.py", *argv]),
            mock.patch.object(
                tk, "load_state", return_value={"out": ".", "window": "1"}
            ),
            mock.patch.object(
                tk, "xdo", lambda state, *args: calls.append(args)
            ),
            mock.patch.object(tk, "read_probe", return_value=probe),
            mock.patch.object(tk, "act"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            tk.main()
        return calls

    def test_click_waits_out_a_page_hold(self) -> None:
        """等待提示下 click 报错退出，awaiting 恢复为选项列表后再点击对应按钮坐标"""
        probe = {
            "awaiting": "wait",
            "buttons": {"1": [5, 6]},
            "page_turns": 1,
            "input": [7, 8],
            "ts": 0,
        }
        with self.assertRaises(SystemExit):
            self.run_tk(probe, "click", "1")
        calls = self.run_tk({**probe, "awaiting": ["1"]}, "click", "1")
        self.assertEqual([args[3:5] for args in calls], [("5", "6")])

    def test_page_turn_counts_as_a_change(self) -> None:
        """awaiting 与 buttons 不变时，page_turns 递增且连续两次读到新时间戳即结束等待"""
        page = {"awaiting": "wait", "buttons": {}, "page_turns": 0, "ts": 0}
        reads = iter([{**page, "page_turns": 1, "ts": ts} for ts in (1, 2)])
        with (
            mock.patch.object(tk, "read_probe", lambda state: next(reads)),
            mock.patch.object(tk.time, "sleep"),
        ):
            tk.wait_for_probe_change({}, page)
        self.assertIsNone(next(reads, None))


class TkProbeHold(unittest.TestCase):
    """检查 tk_probe._dump 在分页停顿与释放后写出的 awaiting 与 page_turns，前端与根窗口替换为替身。"""

    def dump(self, hold: str, turns: int) -> dict:
        """
        以给定的分页停顿状态和翻页计数调用 tk_probe._dump 并读回写出的 JSON
        参数：
            hold (str): 替身前端的 pager.hold
            turns (int): 替身前端的 pager.turns
        返回：
            dict: 从临时 probe.json 读回的探针字典
        """
        widget = SimpleNamespace(
            winfo_rootx=lambda: 0,
            winfo_rooty=lambda: 0,
            winfo_width=lambda: 10,
            winfo_height=lambda: 10,
        )
        frontend = SimpleNamespace(
            pager=SimpleNamespace(hold=hold, turns=turns),
            window=SimpleNamespace(textbox=widget, inputbox=widget),
            renderer=SimpleNamespace(cmd_tag_map={}),
        )
        root = SimpleNamespace(
            winfo_rootx=lambda: 0,
            winfo_rooty=lambda: 0,
            after=lambda ms, fn: None,
        )
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = str(Path(tmpdir.name) / "probe.json")
        with (
            mock.patch.object(tk_probe, "_frontend", frontend),
            mock.patch.object(tk_probe, "_awaiting", ["1", "2"]),
        ):
            tk_probe._dump(root, path)
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def test_hold_reports_wait_until_released(self) -> None:
        """停顿状态为 unit 或 page 时 awaiting 为 "wait"，为 none 时恢复游戏等待列表并写出 page_turns"""
        for hold in ("unit", "page"):
            with self.subTest(hold):
                held = self.dump(hold, 2)
                self.assertEqual(held["awaiting"], "wait")
                self.assertEqual(held["page_turns"], 2)
        released = self.dump("none", 3)
        self.assertEqual(released["awaiting"], ["1", "2"])
        self.assertEqual(released["page_turns"], 3)


if __name__ == "__main__":
    unittest.main()
