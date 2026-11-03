#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
arkeditor.py 的测试
Editor 类用 start 的真实命令在 Xvfb 里启动一个假编辑器，
假编辑器是一个记下收到的 X 事件的 Tk 窗口。
这些测试检查就绪后的窗口位置与大小、各动作送到窗口的事件、
存下的帧与 actions.log，以及不合要求的输入不发事件。
Lookup 类检查动作与 stop 怎样按证据目录找运行。
Launch 类检查 start 拒绝不空的证据目录，
以及 run 让命令连上 X 显示并返回它的退出码。
测试把 limited_run 的 run、live_runs、cmd_stop 换成替身，
测试不建受限运行，也不启动游戏或真正的编辑器

用法：
    python3 tools/verify/test_arkeditor.py
"""

import contextlib
import io
import os
import pathlib
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from typing import Any
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import arkeditor
import limited_run

# 假编辑器的 main.py，是一个标题与编辑器主窗口相同的 Tk 窗口。
# 每收到一个按键、鼠标按键的按下或松开、按住左键时的移动，
# 它就向 events.log 追加一行。按键行带着当时按住的 ctrl 与 shift
RECORDER = """
import tkinter
root = tkinter.Tk()
root.title("ErArk编辑器")
log = open("events.log", "a", encoding="utf-8")
def record(*fields):
  log.write(" ".join(map(str, fields)) + "\\n")
  log.flush()
def mods(event):
  held = [name for bit, name in ((4, "ctrl"), (1, "shift")) if event.state & bit]
  return "+".join(held) or "-"
root.bind_all("<KeyPress>", lambda e: record("key", e.keysym, mods(e)))
root.bind_all("<ButtonPress>", lambda e: record("press", e.num, e.x_root, e.y_root))
root.bind_all("<ButtonRelease>", lambda e: record("release", e.num, e.x_root, e.y_root))
root.bind_all("<B1-Motion>", lambda e: record("motion", e.x_root, e.y_root))
root.mainloop()
"""
SIZE = (320, 240)
MODIFIERS = {"Control_L", "Shift_L"}


def png_size(path: pathlib.Path) -> tuple[int, int]:
  """
  读 PNG 文件头里的宽与高
  参数：path (pathlib.Path) PNG 文件
  返回：tuple[int, int] 宽、高
  """
  data = path.read_bytes()
  assert data[:8] == b"\x89PNG\r\n\x1a\n"
  width, height = struct.unpack(">II", data[16:24])
  return width, height


def fake_checkout(root: pathlib.Path, editor: str) -> None:
  """
  在 root 下建一个假 checkout，含空的 game.py 与内容为 editor 的
  tools/ArkEditor/main.py。limited_run.game_checkout() 凭 game.py 认出 checkout
  参数：root (pathlib.Path) checkout 的根目录；editor (str) main.py 的内容
  """
  (root / "tools" / "ArkEditor").mkdir(parents=True)
  (root / "tools" / "ArkEditor" / "main.py").write_text(
      editor, encoding="utf-8"
  )
  (root / "game.py").touch()


class Editor(unittest.TestCase):
  """start 在 Xvfb 里启动假编辑器，各测试经 main() 操作它并读它记下的事件"""

  runs: list[dict[str, object]] = []
  stop_requested = threading.Event()
  events: pathlib.Path
  out: pathlib.Path

  @classmethod
  def setUpClass(cls) -> None:
    """
    建假 checkout，把 limited_run 的 run、live_runs、cmd_stop 换成替身，
    在后台线程里运行 start --size 320x240，等到运行就绪。
    30 秒内没有就绪时抛出 RuntimeError
    """
    tmpdir = tempfile.TemporaryDirectory()
    cls.addClassCleanup(tmpdir.cleanup)
    root = pathlib.Path(tmpdir.name).resolve()
    fake_checkout(root, RECORDER)
    cls.events = root / "tools" / "ArkEditor" / "events.log"
    cls.out = root / "run"
    cls.addClassCleanup(os.chdir, os.getcwd())
    os.chdir(root)
    for name, value in (
        ("run", cls.fake_run),
        ("live_runs", lambda: list(cls.runs)),
        ("cmd_stop", cls.fake_stop),
    ):
      patcher = mock.patch.object(limited_run, name, value)
      patcher.start()
      cls.addClassCleanup(patcher.stop)
    width, height = SIZE
    thread = threading.Thread(
        target=arkeditor.main,
        args=(["start", "--out", str(cls.out), "--size", f"{width}x{height}"],),
    )
    thread.start()
    cls.addClassCleanup(thread.join, 30)
    cls.addClassCleanup(arkeditor.main, ["stop", "--out", str(cls.out)])
    deadline = time.monotonic() + 30
    while not cls.runs and thread.is_alive() and time.monotonic() < deadline:
      time.sleep(0.2)
    if not cls.runs:
      raise RuntimeError("假编辑器没有就绪")

  @classmethod
  def fake_run(cls, *args: Any) -> int:
    """
    代替 limited_run.run()，并检查模式、内存上限与时限是 start 的默认值。
    它用 limited_run.scope_env() 给的环境变量在新的进程会话里运行命令，
    反复调用就绪检查，就绪后把运行状态交给替身 live_runs。
    收到停止请求或等满 60 秒后，它停掉整个会话
    参数：args (Any) 与 limited_run.run() 相同的位置参数
    返回：int 就绪后停下时为 0，命令先结束或等就绪超时时为 77
    """
    mode, command, mem_max, timeout, extra_env, out_dir, ready_check, wait = (
        args
    )
    assert (mode, mem_max, timeout) == ("editor", 2 << 30, 600)
    proc = subprocess.Popen(
        command, env=limited_run.scope_env(extra_env), start_new_session=True
    )
    try:
      deadline = time.monotonic() + wait
      while (fields := ready_check()) is None:
        if proc.poll() is not None or time.monotonic() > deadline:
          return 77
        time.sleep(0.2)
      cls.runs.append({"out": str(out_dir), "pid": 4321, **fields})
      cls.stop_requested.wait(60)
      return 0
    finally:
      with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
      proc.wait()

  @classmethod
  def fake_stop(cls, pid: str) -> int:
    """
    代替 limited_run.cmd_stop()，检查 pid 是 fake_run 写进运行状态的 4321，
    再让 fake_run 停掉会话
    参数：pid (str) 要停的运行的 pid
    返回：int 0
    """
    assert pid == "4321"
    cls.stop_requested.set()
    return 0

  def x_env(self) -> dict[str, str]:
    """返回：dict[str, str] 运行状态里的 DISPLAY 与 XAUTHORITY"""
    return {name: str(self.runs[0][name]) for name in arkeditor.X_VARS}

  def drive(self, *args: str, count: int) -> tuple[str, list[list[str]]]:
    """
    带 --wait 0 运行 main()，检查它返回 0，再等假编辑器记下 count 行新事件。
    5 秒内等不到时测试失败
    参数：args (str) 子命令与 --out 之后的参数；count (int) 要等的新事件行数
    返回：tuple[str, list[list[str]]] main() 的标准输出、新事件（每行按空格拆开）
    """
    before = len(self.read_events())
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
      self.assertEqual(
          arkeditor.main(
              [args[0], "--out", str(self.out), "--wait", "0", *args[1:]]
          ),
          0,
      )
    deadline = time.monotonic() + 5
    while len(self.read_events()) < before + count:
      self.assertLess(time.monotonic(), deadline, self.read_events()[before:])
      time.sleep(0.05)
    time.sleep(0.2)
    return stdout.getvalue(), self.read_events()[before:]

  def read_events(self) -> list[list[str]]:
    """
    返回：list[list[str]] events.log 里的事件，每行按空格拆开，
    去掉左 ctrl 键与左 shift 键自身的按键事件
    """
    if not self.events.exists():
      return []
    events = [line.split() for line in self.events.read_text().splitlines()]
    return [event for event in events if event[1] not in MODIFIERS]

  def keys(self, events: list[list[str]]) -> list[tuple[str, str]]:
    """
    从事件里取出各按键事件的键名与当时按住的修饰键
    参数：events (list[list[str]]) read_events() 给的事件
    返回：list[tuple[str, str]] 键名、修饰键（没有按住修饰键时为 -）
    """
    return [(event[1], event[2]) for event in events if event[0] == "key"]

  def test_ready_window_fills_screen_and_shot_saves_full_screen(self) -> None:
    """
    就绪后运行状态里的 DISPLAY 与 XAUTHORITY 等于 display 文件的内容，
    编辑器窗口在 0,0 且与屏幕一样大。shot 存下与屏幕一样大的帧
    """
    display = (self.out / arkeditor.DISPLAY_FILE).read_text().split()
    self.assertEqual(display, list(self.x_env().values()))
    geometry = arkeditor.x_client(
        self.x_env(),
        *["xdotool", "search", "--name", "^ErArk", "getwindowgeometry"],
    ).stdout
    self.assertIn("Position: 0,0", geometry)
    self.assertIn(f"Geometry: {SIZE[0]}x{SIZE[1]}", geometry)
    printed, _ = self.drive("shot", "--label", "full", count=0)
    frame = pathlib.Path(printed.removeprefix("frame: ").strip())
    self.assertRegex(frame.name, r"^\d{3}-full\.png$")
    self.assertEqual(png_size(frame), SIZE)

  def test_click_presses_and_releases_left_button_and_logs_frame(self) -> None:
    """
    click 在坐标处按下并松开左键。帧存在 frames 下，帧名带清理过的标签，
    actions.log 的最后一行记下动作与帧名
    """
    printed, events = self.drive(
        "click", "30", "20", "--label", "a/b c", count=2
    )
    self.assertEqual(
        events, [["press", "1", "30", "20"], ["release", "1", "30", "20"]]
    )
    frame = pathlib.Path(printed.removeprefix("frame: ").strip())
    self.assertEqual(frame.parent, self.out / "frames")
    self.assertTrue(frame.name.endswith("-a_b_c.png"))
    last = (
        (self.out / "actions.log").read_text(encoding="utf-8").splitlines()[-1]
    )
    self.assertEqual(last.split("\t")[1:], ["click 30 20", frame.name])

  def test_dclick_presses_left_twice_and_rclick_presses_right(self) -> None:
    """dclick 按下并松开左键两次，rclick 按下并松开右键"""
    _, events = self.drive("dclick", "40", "40", count=4)
    self.assertEqual(
        [event[:2] for event in events], [["press", "1"], ["release", "1"]] * 2
    )
    _, events = self.drive("rclick", "40", "40", count=2)
    self.assertEqual(
        [event[:2] for event in events], [["press", "3"], ["release", "3"]]
    )

  def test_drag_holds_left_button_from_start_to_end(self) -> None:
    """drag 在起点按下左键，按住时经至少 10 个不同的点依次移向终点，在终点松开"""
    _, events = self.drive("drag", "10", "40", "200", "100", count=3)
    self.assertEqual(events[0], ["press", "1", "10", "40"])
    self.assertEqual(events[-1], ["release", "1", "200", "100"])
    path = [
        tuple(map(int, event[1:])) for event in events if event[0] == "motion"
    ]
    self.assertGreaterEqual(len(set(path)), 10)
    self.assertEqual(path, sorted(path))
    self.assertEqual(path[-1], (200, 100))

  def test_key_combos_hold_modifiers_only_for_their_key(self) -> None:
    """
    key ctrl+s Return ctrl+plus , Menu 的五个键依次到达窗口。
    s 与 plus 到达时按住 ctrl，Return、逗号与 Menu 到达时不按修饰键。
    plus 到达时还按住 shift
    """
    _, events = self.drive(
        "key", "ctrl+s", "Return", "ctrl+plus", ",", "Menu", count=5
    )
    self.assertEqual(
        self.keys(events),
        [
            ("s", "ctrl"),
            ("Return", "-"),
            ("plus", "ctrl+shift"),
            ("comma", "-"),
            ("Menu", "-"),
        ],
    )

  def test_type_sends_each_character(self) -> None:
    """type aB+/, 逐个送出五个字符，B 与 + 到达时按住 shift"""
    _, events = self.drive("type", "aB+/,", count=5)
    self.assertEqual(
        self.keys(events),
        [
            ("a", "-"),
            ("B", "shift"),
            ("plus", "shift"),
            ("slash", "-"),
            ("comma", "-"),
        ],
    )

  def test_bad_input_sends_nothing_and_saves_no_frame(self) -> None:
    """
    type 非 ASCII 文字、key ctrl+Hyper、key ctrl++ 都直接退出，
    窗口收不到事件，frames 下也没有新帧
    """
    frames = sorted((self.out / "frames").glob("*.png"))
    before = self.read_events()
    for args in (["type", "前提"], ["key", "ctrl+Hyper"], ["key", "ctrl++"]):
      with self.subTest(args=args), self.assertRaises(SystemExit):
        arkeditor.main([args[0], "--out", str(self.out), *args[1:]])
    time.sleep(0.3)
    self.assertEqual(self.read_events(), before)
    self.assertEqual(sorted((self.out / "frames").glob("*.png")), frames)


class Lookup(unittest.TestCase):
  """动作与 stop 按证据目录找运行，运行列表由替身 live_runs 给出"""

  def setUp(self) -> None:
    """建一个临时证据目录"""
    tmpdir = tempfile.TemporaryDirectory()
    self.addCleanup(tmpdir.cleanup)
    self.out = pathlib.Path(tmpdir.name).resolve()

  def test_not_ready_and_unknown_out(self) -> None:
    """
    运行状态里还没有 DISPLAY 时，动作命令说明编辑器还没就绪。
    没有以该目录启动的运行时，动作命令提示先用 start
    """
    with mock.patch.object(
        limited_run,
        "live_runs",
        return_value=[{"out": str(self.out), "pid": 1}],
    ):
      with self.assertRaises(SystemExit) as caught:
        arkeditor.main(["shot", "--out", str(self.out)])
      self.assertIn("还没就绪", str(caught.exception.code))
      with self.assertRaises(SystemExit) as caught:
        arkeditor.main(["shot", "--out", str(self.out / "other")])
      self.assertIn("start", str(caught.exception.code))

  def test_stop_asks_limited_run_to_stop_that_pid(self) -> None:
    """stop 按证据目录找到运行，把它的 pid 交给 limited_run.cmd_stop()"""
    with mock.patch.object(
        limited_run,
        "live_runs",
        return_value=[{"out": str(self.out), "pid": 4321}],
    ), mock.patch.object(limited_run, "cmd_stop", return_value=0) as stop:
      self.assertEqual(arkeditor.main(["stop", "--out", str(self.out)]), 0)
    stop.assert_called_once_with("4321")


class Launch(unittest.TestCase):
  """start 拒绝不空的证据目录，run 在 xvfb-run 下运行命令"""

  def setUp(self) -> None:
    """建一个假 checkout 并把当前目录切换进去"""
    tmpdir = tempfile.TemporaryDirectory()
    self.addCleanup(tmpdir.cleanup)
    self.root = pathlib.Path(tmpdir.name).resolve()
    fake_checkout(self.root, "")
    self.addCleanup(os.chdir, os.getcwd())
    os.chdir(self.root)

  def test_start_refuses_non_empty_out(self) -> None:
    """证据目录不空时 start 退出，不调用 limited_run.run()"""
    (self.root / "b").mkdir()
    (self.root / "b" / "editor.log").touch()
    with mock.patch.object(limited_run, "run") as run:
      with self.assertRaises(SystemExit):
        arkeditor.main(["start", "--out", str(self.root / "b")])
    run.assert_not_called()

  def test_run_gives_the_command_a_display_and_returns_its_code(self) -> None:
    """
    run 按 headless 模式、带固定的 PYTHONHASHSEED 运行命令。
    命令连得上 2100x1100 的默认屏幕，run 原样返回命令的退出码。
    -- 之后没有命令时，run 退出，不调用 limited_run.run()
    """
    calls = []

    def fake_run(
        mode: str,
        command: list[str],
        mem_max: int,
        timeout: int,
        extra_env: dict[str, str],
    ) -> int:
      """
      代替 limited_run.run()，用 limited_run.scope_env() 给的环境变量直接运行命令，
      记下模式、内存上限、时限、额外变量与标准输出
      参数：mode、command、mem_max、timeout、extra_env 同 limited_run.run()
      返回：int 命令的退出码
      """
      result = subprocess.run(
          command,
          env=limited_run.scope_env(extra_env),
          capture_output=True,
          text=True,
          check=False,
      )
      calls.append((mode, mem_max, timeout, extra_env, result.stdout))
      return result.returncode

    with mock.patch.object(limited_run, "run", fake_run), mock.patch.dict(
        os.environ, {"PATH": os.environ["PATH"]}, clear=True
    ):
      self.assertEqual(
          arkeditor.main(
              ["run", "--mem", "3G", "--", "xdotool", "getdisplaygeometry"]
          ),
          0,
      )
      self.assertEqual(arkeditor.main(["run", "--", "sh", "-c", "exit 5"]), 5)
      with self.assertRaises(SystemExit):
        arkeditor.main(["run"])
    seed = {"PYTHONHASHSEED": limited_run.DEFAULT_SEED}
    self.assertEqual(calls[0], ("headless", 3 << 30, 600, seed, "2100 1100\n"))
    self.assertEqual(len(calls), 2)


if __name__ == "__main__":
  unittest.main()
