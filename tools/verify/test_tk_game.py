#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
tk_game.py 与 tk.py 的测试：经 limited_run.run 启动、传下的种子与默认内存、证据目录检查、拒绝 web 模式的 checkout、与无头运行共用槽位、tk.py 选择要操作的实例、tk.py doctor 的内存检查；不启动游戏
另测含换行的动作描述在 tk.py 写的 actions.log 里只占一行

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
          {"display": ":51", "window": "123", "probe": str(out / "probe.json")},
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
        mock.patch.object(tk, "read_probe", return_value={"ts": time.time()}),
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
    ok, line = self.doctor({"anon": 2900, "file": 0, "shmem": 50, "kernel": 50})
    self.assertFalse(ok)
    self.assertTrue(line.startswith("FAIL"), line)

  def test_stat_missing(self) -> None:
    """读不到 memory.stat 时 FAIL，不当作 0"""
    ok, line = self.doctor(None)
    self.assertFalse(ok)
    self.assertTrue(line.startswith("FAIL"), line)
    self.assertIn("读不到", line)


class TkActionsLog(unittest.TestCase):
  """检查 tk.act 写进 actions.log 的行。等待用的时钟、读探针和截图都换成假的。"""

  def test_key_with_newline(self) -> None:
    """描述含换行的动作（如 type 加返回值 "\\n0"）在 actions.log 里只占一行。行里的这个换行是反斜杠加 n 两个字符。"""
    tmpdir = tempfile.TemporaryDirectory()
    self.addCleanup(tmpdir.cleanup)
    out = pathlib.Path(tmpdir.name)
    probe = {"awaiting": ["\n0", "返回"], "buttons": {}, "ts": 0}
    clock = [0.0]

    def sleep(seconds: float) -> None:
      """
      只把假时钟推进 seconds 秒
      参数：seconds (float) 要推进的秒数
      """
      clock[0] += seconds

    frames = iter(["001-type-_0.png", "002-advance.png"])
    fake_time = mock.Mock(
        monotonic=lambda: clock[0], sleep=sleep, strftime=time.strftime
    )
    with (
        mock.patch.object(tk, "time", fake_time),
        mock.patch.object(tk, "read_probe", return_value=probe),
        mock.patch.object(
            tk, "shot", side_effect=lambda state, label: out / next(frames)
        ),
        contextlib.redirect_stdout(io.StringIO()),
    ):
      tk.act({"out": str(out)}, "type \n0", "type-\n0", probe)
      tk.act({"out": str(out)}, "advance", "advance", probe)
    lines = (out / "actions.log").read_text(encoding="utf-8").splitlines()
    self.assertEqual(
        [line.split("\t")[1:] for line in lines],
        [["type \\n0", "001-type-_0.png"], ["advance", "002-advance.png"]],
    )


if __name__ == "__main__":
  unittest.main()
