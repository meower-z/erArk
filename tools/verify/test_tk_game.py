#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
tk_game.py 与 tk.py 的测试：经 limited_run.run 启动、传下的种子与默认内存、证据目录检查、拒绝 web 模式的 checkout、
与无头运行共用槽位、tk.py 选择要操作的实例、tk.py doctor 的内存检查；不启动游戏
另有 tk.py 动作后何时截帧的测试，同样不启动游戏

用法：
    python3 tools/verify/test_tk_game.py
"""

import contextlib
import io
import os
import pathlib
import sys
import tempfile
import time
import unittest
from typing import Any
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import limited_run
import tk
import tk_game


class TkGame(unittest.TestCase):
    """在临时证据目录和临时锁目录下运行 tk_game.main"""

    def setUp(self) -> None:
        """建临时目录并切换到其中，把 limited_run 的状态目录换到其中，并假定没有存活的 era-game scope"""
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        self.tmp = pathlib.Path(tmpdir.name).resolve()
        self.patch(limited_run, "STATE_DIR", self.tmp / "state")
        self.patch(limited_run, "active_game_units", return_value=[])
        self.patch(limited_run, "game_checkout", return_value=self.tmp)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.tmp)

    def patch(self, target, name: str, *args, **kwargs):
        """
        替换一个属性，测试结束时还原
        参数：target 被替换属性所在的对象；name (str) 属性名；args、kwargs 传给 mock.patch.object
        返回：替换后的值，没给替换值时为新建的 mock
        """
        patcher = mock.patch.object(target, name, *args, **kwargs)
        replaced = patcher.start()
        self.addCleanup(patcher.stop)
        return replaced

    def test_runs_through_limited_run(self) -> None:
        """tk_game 不自己建 scope，只调用 limited_run.run，带上 tk 模式、3G、证据目录与就绪检查；3G 占 2 个 2G 槽位"""
        run = self.patch(limited_run, "run", return_value=0)
        out = self.tmp / "run"
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(tk_game.main(["--out", str(out)]), 0)
        (
            mode,
            command,
            mem_max,
            timeout,
            extra,
            out_dir,
            ready_check,
            ready_timeout,
        ) = run.call_args.args
        self.assertEqual(
            (mode, mem_max, timeout, out_dir, ready_timeout),
            ("tk", 3 << 30, 600, out, 300),
        )
        self.assertEqual(limited_run.slots_needed(mem_max, self.tmp), 2)
        self.assertEqual(command[:2], ["bash", "-c"])
        self.assertIn(str(tk_game.PROBE), command[2])
        seed = limited_run.DEFAULT_SEED
        self.assertEqual(
            extra,
            {
                "ERARK_SEED": seed,
                "PYTHONHASHSEED": seed,
                "ERARK_PROBE_JSON": str(out / "probe.json"),
            },
        )
        self.assertIsNone(ready_check())

    def test_options_and_seed(self) -> None:
        """--mem、--timeout、--ready-timeout 与 ERARK_SEED 都传到 limited_run.run"""
        run = self.patch(limited_run, "run", return_value=0)
        with mock.patch.dict(os.environ, {"ERARK_SEED": "7"}, clear=True):
            tk_game.main(
                [
                    "--out",
                    str(self.tmp / "run"),
                    "--mem",
                    "6G",
                    "--timeout",
                    "900",
                    "--ready-timeout",
                    "60",
                ]
            )
        args = run.call_args.args
        self.assertEqual((args[2], args[3], args[7]), (6 << 30, 900, 60))
        self.assertEqual(
            (args[4]["ERARK_SEED"], args[4]["PYTHONHASHSEED"]), ("7", "7")
        )

    def test_nonempty_out_refused(self) -> None:
        """证据目录不空时报用法错误，不启动"""
        run = self.patch(limited_run, "run", return_value=0)
        out = self.tmp / "run"
        out.mkdir()
        (out / "probe.json").write_text("{}")
        with self.assertRaises(SystemExit) as caught, mock.patch("sys.stderr"):
            tk_game.main(["--out", str(out)])
        self.assertEqual(caught.exception.code, 2)
        run.assert_not_called()

    def test_web_mode_refused(self) -> None:
        """checkout 的 config.ini 设了 web_draw = 1 时以 2 退出，报出文件与设置，不占槽位、不启动，也不改 config.ini"""
        run = self.patch(limited_run, "run", return_value=0)
        take = self.patch(limited_run, "take_slots")
        config = self.tmp / "config.ini"
        config.write_text("[game]\nweb_draw = 1\n", encoding="utf8")
        with self.assertRaises(SystemExit) as caught, mock.patch(
            "sys.stderr"
        ) as stderr:
            tk_game.main(["--out", str(self.tmp / "run")])
        self.assertEqual(caught.exception.code, 2)
        message = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertIn(str(config), message)
        self.assertIn("web_draw = 0", message)
        run.assert_not_called()
        take.assert_not_called()
        self.assertFalse((self.tmp / "run").exists())
        self.assertEqual(
            config.read_text(encoding="utf8"), "[game]\nweb_draw = 1\n"
        )

    def test_shares_slots_with_limited_run(self) -> None:
        """无头运行占着的槽位只剩 1 个空着时，要 2 个的 tk_game 经 limited_run 以 75 退出，不建 scope"""
        holder = limited_run.take_slots(limited_run.SLOTS - 1)
        self.addCleanup(limited_run.release_slots, holder)
        popen = self.patch(limited_run.subprocess, "Popen")
        with self.assertRaises(SystemExit) as caught, mock.patch("sys.stderr"):
            tk_game.main(["--out", str(self.tmp / "run")])
        self.assertEqual(caught.exception.code, limited_run.EXIT_BUSY)
        popen.assert_not_called()

    def test_ready_check(self) -> None:
        """display.txt 与 probe.json 都在、窗口已出现时才就绪"""
        out = self.tmp / "run"
        out.mkdir()
        self.assertIsNone(tk_game.tk_ready(out))
        (out / "display.txt").write_text("51\n")
        (out / "probe.json").write_text("{}")
        with mock.patch.object(tk_game, "find_window", return_value="") as find:
            self.assertIsNone(tk_game.tk_ready(out))
        find.assert_called_once_with(":51")
        with mock.patch.object(tk_game, "find_window", return_value="123"):
            self.assertEqual(
                tk_game.tk_ready(out),
                {
                    "display": ":51",
                    "window": "123",
                    "probe": str(out / "probe.json"),
                },
            )


class TkSelect(unittest.TestCase):
    """tk.py 选择要操作的 Tk 实例；运行状态换成假的 live_runs 结果"""

    RUNS = [
        {
            "pid": 9001,
            "mode": "headless",
            "slots": [0],
            "unit": "era-game-9001",
            "mem_max_mib": 2048,
            "cwd": "/a",
            "command": "python3 x.py",
        },
        {
            "pid": 9002,
            "mode": "tk",
            "slots": [1, 2],
            "unit": "era-game-9002",
            "mem_max_mib": 3072,
            "cwd": "/b",
            "command": "tk game",
            "out": "/runs/b",
            "window": "11",
        },
        {
            "pid": 9003,
            "mode": "tk",
            "slots": [3, 4],
            "unit": "era-game-9003",
            "mem_max_mib": 3072,
            "cwd": "/c",
            "command": "tk game",
            "out": "/runs/c",
        },
    ]

    def select(
        self, runs: list[dict], slot: int | None = None, out: str | None = None
    ) -> dict | str:
        """
        在给定的运行下调用 tk.load_state
        参数：runs (list[dict]) 正在运行的实例；slot (int | None) --slot；out (str | None) --out
        返回：dict | str 选中的状态，或退出时的消息
        """
        with mock.patch.object(limited_run, "live_runs", return_value=runs):
            try:
                return tk.load_state(slot, pathlib.Path(out) if out else None)
            except SystemExit as caught:
                return str(caught.code)

    def test_only_tk_run(self) -> None:
        """只有一个 Tk 实例时不用指定，旁边的无头运行不算"""
        self.assertEqual(self.select(self.RUNS[:2])["pid"], 9002)

    def test_several_need_choice(self) -> None:
        """有两个 Tk 实例时不指定就报错并列出两个；--out 或 --slot 选中其中一个"""
        message = self.select(self.RUNS)
        self.assertIn("--out", message)
        self.assertIn("pid 9002", message)
        self.assertIn("pid 9003", message)
        self.assertEqual(self.select(self.RUNS, out="/runs/b")["pid"], 9002)
        self.assertEqual(self.select(self.RUNS, slot=2)["pid"], 9002)

    def test_not_ready_or_missing(self) -> None:
        """选中的实例还没有窗口时报未就绪；没有符合的 Tk 实例时报没有"""
        self.assertIn("还没就绪", self.select(self.RUNS, slot=3))
        self.assertIn("没有符合的 Tk 实例", self.select(self.RUNS, slot=0))
        self.assertIn("没有符合的 Tk 实例", self.select(self.RUNS[:1]))


class TkDoctor(unittest.TestCase):
    """tk.py doctor 的内存一项；窗口、探针、字体换成能通过的假结果，scope 目录换成临时目录"""

    STATE = {
        "unit": "era-game-9002",
        "mem_max_mib": 3072,
        "window": "11",
        "display": ":51",
    }

    def doctor(self, stat: dict | None) -> tuple[bool, str]:
        """
        在给定的 memory.stat 下调用 tk.doctor，memory.current 记成接近上限（大半是文件缓存）
        参数：stat (dict | None) memory.stat 各字段的 MiB 数，None 时不建这个文件
        返回：tuple[bool, str] doctor 的结果与打印的内存一行
        """
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        unit_dir = pathlib.Path(tmpdir.name)
        (unit_dir / "memory.current").write_text(str(3000 << 20))
        if stat is not None:
            (unit_dir / "memory.stat").write_text(
                "".join(f"{key} {value << 20}\n" for key, value in stat.items())
            )
        fonts = mock.Mock(stdout="Sarasa Mono SC")
        out = io.StringIO()
        with (
            mock.patch.object(
                tk, "xdo", return_value="Window 11\n  Geometry: 2100x1200"
            ),
            mock.patch.object(
                tk, "read_probe", return_value={"ts": time.time()}
            ),
            mock.patch.object(limited_run, "scope_dir", return_value=unit_dir),
            mock.patch.object(tk.subprocess, "run", return_value=fonts),
            contextlib.redirect_stdout(out),
        ):
            ok = tk.doctor(self.STATE)
        return ok, next(
            line for line in out.getvalue().splitlines() if "内存" in line
        )

    def test_page_cache_not_counted(self) -> None:
        """memory.current 因文件缓存接近上限、不可回收部分很少时通过，打印的是 anon+shmem+kernel"""
        ok, line = self.doctor(
            {"anon": 900, "file": 1900, "shmem": 100, "kernel": 50}
        )
        self.assertTrue(ok, line)
        self.assertTrue(line.startswith("ok"), line)
        self.assertIn("不可回收内存 1050 MiB", line)

    def test_unreclaimable_near_cap(self) -> None:
        """不可回收部分到了上限的 97% 时 FAIL"""
        ok, line = self.doctor(
            {"anon": 2900, "file": 0, "shmem": 50, "kernel": 50}
        )
        self.assertFalse(ok)
        self.assertTrue(line.startswith("FAIL"), line)

    def test_stat_missing(self) -> None:
        """读不到 memory.stat 时 FAIL，不当作 0"""
        ok, line = self.doctor(None)
        self.assertFalse(ok)
        self.assertTrue(line.startswith("FAIL"), line)
        self.assertIn("读不到", line)


class TkCapture(unittest.TestCase):
    """tk.py 动作后何时截帧：换掉 load_state、xdo、time、read_probe 与 shot 后运行 tk.main"""

    CONFIRM = {
        "awaiting": ["0", "1"],
        "buttons": {"0": [8, 750], "1": [8, 780]},
    }
    # 读档回调运行时的探针内容：「[000]读取 [001]删除 [002]返回」面板的等待列表与空的按钮表
    LOADING = {"awaiting": ["0", "1", "2"], "buttons": {}}
    DRAWING = {"awaiting": None, "buttons": {"阿米娅": [300, 100]}}
    MAIN = {
        "awaiting": ["阿米娅", "日常", "1", "1001"],
        "buttons": {
            "阿米娅": [300, 100],
            "日常": [180, 780],
            "1": [8, 910],
            "1001": [8, 830],
        },
    }

    def capture(
        self, timeline: list[tuple[float, dict[str, Any]]], *argv: str
    ) -> tuple[float, dict[str, Any]]:
        """
        以 argv 为命令行参数运行一次 tk.main。timeline 里 0 秒时的探针内容就是动作前的内容
        参数：timeline (list[tuple[float, dict[str, Any]]]) 各段的开始秒数与探针内容，按开始秒数排序，第一段从 0 秒开始
              argv (str) 依次传给 tk.py 的命令行参数，不含程序名
        返回：tuple[float, dict[str, Any]] 截帧时的秒数与当时的探针内容
        """
        clock = [0.0]

        def written(at: float) -> dict[str, Any]:
            """at 秒时假探针最近一次写出的内容，ts 为写出时的秒数"""
            ts = int(at / 0.3) * 0.3
            content = [probe for start, probe in timeline if start <= ts][-1]
            return {"input": [700, 1050], **content, "ts": ts}

        def sleep(seconds: float) -> None:
            """把假时钟推进 seconds 秒，不真的等待"""
            clock[0] += seconds

        captured = []

        def shot(state: dict[str, Any], label: str) -> pathlib.Path:
            """代替 tk.shot：记下截帧时的秒数与探针内容，返回帧路径而不生成文件"""
            captured.append((clock[0], written(clock[0])))
            return pathlib.Path(state["out"]) / "frames" / f"001-{label}.png"

        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        fake_time = mock.Mock(
            monotonic=lambda: clock[0], sleep=sleep, strftime=time.strftime
        )
        with (
            mock.patch.object(sys, "argv", ["tk.py", *argv]),
            mock.patch.object(
                tk,
                "load_state",
                return_value={
                    "out": tmpdir.name,
                    "window": "11",
                    "display": ":51",
                },
            ),
            mock.patch.object(tk, "xdo", return_value=""),
            mock.patch.object(tk, "time", fake_time),
            mock.patch.object(
                tk, "read_probe", lambda state: written(clock[0])
            ),
            mock.patch.object(tk, "shot", shot),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            tk.main()
        return captured[0]

    def test_slow_load(self) -> None:
        """确认读档后 5.1 秒主场景才出现时，截到的是主场景，不是读档途中的状态"""
        at, probe = self.capture(
            [
                (0.0, self.CONFIRM),
                (0.6, self.LOADING),
                (4.8, self.DRAWING),
                (5.1, self.MAIN),
            ],
            "type",
            "0",
        )
        self.assertEqual(probe["awaiting"], self.MAIN["awaiting"])
        self.assertGreaterEqual(at, 5.1)

    def test_screen_unchanged(self) -> None:
        """探针内容一直与动作前相同时，tk.py type 在 5 秒内截帧"""
        at, probe = self.capture([(0.0, self.CONFIRM)], "type", "0")
        self.assertEqual(probe["awaiting"], self.CONFIRM["awaiting"])
        self.assertLess(at, 5)

    def test_scroll_hides_buttons(self) -> None:
        """scroll up 后等待的按钮全部移出画面时，tk.py 仍在 2 秒内截帧"""
        scrolled = {"awaiting": self.MAIN["awaiting"], "buttons": {}}
        at, probe = self.capture(
            [(0.0, self.MAIN), (0.6, scrolled)], "scroll", "up", "3"
        )
        self.assertEqual(probe["buttons"], {})
        self.assertLess(at, 2)


if __name__ == "__main__":
    unittest.main()
