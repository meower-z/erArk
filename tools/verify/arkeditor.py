#!/usr/bin/env python3
"""
经 limited_run 启动 erArk 的 ArkEditor（tools/ArkEditor/main.py），
用真实的鼠标与键盘事件操作它，并在每个动作后存一帧整屏截图。

start 经 limited_run.run() 启动一次有内存上限与运行时限的运行。
start 按 editor 模式运行，被 stop 停掉时退出码为 0。
这次运行里先由 xvfb-run 起一个虚拟 X 显示（Xvfb）。
编辑器以 -platform xcb 在这个显示上运行。
xvfb-run 在运行里面启动，因为 limited_run 不把 DISPLAY 传进运行。
xvfb-run 在这次运行的临时目录里生成 X 授权文件。
Xvfb 带 -nolisten tcp，不在 TCP 上监听。
运行里的脚本把 DISPLAY 与 XAUTHORITY 写进证据目录下的 display 文件。
就绪检查读 display 文件，并找到编辑器主窗口。
Xvfb 里没有窗口管理器来执行编辑器的 showMaximized()。
就绪检查因此把主窗口移到左上角，并拉到整屏大小。
就绪后 limited_run.run() 把 DISPLAY 与 XAUTHORITY 并入运行状态。
之后的每条动作命令是一个新进程。
动作命令按 --out 找到运行。
动作命令带着这两个变量运行 X 客户端程序。
输入由 xdotool 发出。截屏用 ImageMagick 的 import。
stop 请 limited_run 停掉这次运行。xvfb-run、Xvfb 与编辑器随运行一起结束。

run 子命令经 limited_run.run() 按 headless 模式运行任意命令，
例如导入 PySide6 的编辑器测试。
命令在 xvfb-run 起的虚拟 X 显示里运行，屏幕大小为 DEFAULT_SIZE。
xvfb-run 把命令的标准错误并入标准输出，并返回命令的退出码。

用法（在 erArk checkout 的根目录，用 .venv 的 python 运行本脚本）：
  arkeditor.py start --out <证据目录> [--mem 2G] [--timeout 600]
                     [--ready-timeout 120] [--size 2100x1100]
  arkeditor.py click|rclick|dclick|move --out <证据目录> X Y [--label L] [--wait 1]
  arkeditor.py drag --out <证据目录> X1 Y1 X2 Y2 [--label L] [--wait 1]
  arkeditor.py key --out <证据目录> KEY [KEY ...] [--label L] [--wait 1]
  arkeditor.py type --out <证据目录> TEXT [--label L] [--wait 1]
  arkeditor.py shot --out <证据目录> [--label L] [--wait 1]
  arkeditor.py stop --out <证据目录>
  arkeditor.py run [--mem 2G] [--timeout 600] -- <命令...>
KEY 是 KEYS 里的名字、+ 以外的单个可打印 ASCII 字符，
或 ctrl+s 这样用 + 连起来的组合。加号写 plus。
type 只收可打印 ASCII。
"""

import argparse
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import limited_run

DEFAULT_MEM = "2G"
DEFAULT_SIZE = "2100x1100"
# 就绪检查按这个开头匹配编辑器主窗口的标题。
# 标题在 tools/ArkEditor/ui/window.py 里设置
TITLE = "ErArk"
# 运行里的脚本把这两个变量写进证据目录下的 DISPLAY_FILE。
# 就绪后它们也在运行状态里。之后的动作命令从运行状态读取它们
X_VARS = ("DISPLAY", "XAUTHORITY")
DISPLAY_FILE = "display"

# key 认的键名。ctrl、shift、alt 是 xdotool 给左侧修饰键起的别名，
# 其余是 X 的 keysym 名
KEYS = (
    "Return",
    "Tab",
    "Escape",
    "BackSpace",
    "Delete",
    "Home",
    "End",
    "Left",
    "Up",
    "Right",
    "Down",
    "Page_Up",
    "Page_Down",
    "F10",
    "Menu",
    "space",
    "plus",
    "ctrl",
    "shift",
    "alt",
)
# 指针动作移到坐标之后接的 xdotool 命令。X 的按键 1 是左键，3 是右键。
# move 只移动，不点击
BUTTONS = {
    "click": ["click", "1"],
    "dclick": ["click", "--repeat", "2", "1"],
    "rclick": ["click", "3"],
    "move": [],
}
# drag 按住左键后分几步移到终点；每步之间的秒数。Qt 要按住时收到移过拖动起始距离的指针事件，才开始拖动
DRAG_STEPS = 20
DRAG_STEP_WAIT = 0.03


def xvfb(size: str) -> list[str]:
  """
  拼出 xvfb-run 的命令前缀
  前缀让 xvfb-run 选一个空闲的显示号，按给定大小建 24 位色深的屏幕，
  并让 Xvfb 不在 TCP 上监听
  参数：
      size (str): 屏幕大小，形如 2100x1100
  返回：
      list[str]: argv 前缀，后面接要运行的命令
  """
  return ["xvfb-run", "-a", "-s", f"-screen 0 {size}x24 -nolisten tcp"]


def editor_command(
    root: Path, out_dir: Path, python: str, size: str
) -> list[str]:
  """
  拼出 start 交给 limited_run.run() 的命令
  命令在 xvfb-run 起的显示里运行一段 bash 脚本。脚本进入 tools/ArkEditor，
  把 DISPLAY 与 XAUTHORITY 写进 display 文件，再以 xcb 平台运行编辑器。
  编辑器的输出追加到 editor.log
  参数：
      root (Path): erArk checkout 的根目录
      out_dir (Path): 证据目录
      python (str): 运行编辑器的 python 解释器
      size (str): 屏幕大小，形如 2100x1100
  返回：
      list[str]: 命令的 argv
  """
  script = f"""
cd {shlex.quote(str(root / "tools" / "ArkEditor"))} || exit 9
echo "$DISPLAY $XAUTHORITY" >{shlex.quote(str(out_dir / DISPLAY_FILE))}
exec {shlex.quote(python)} -u main.py -platform xcb \
>>{shlex.quote(str(out_dir / "editor.log"))} 2>&1
"""
  return [*xvfb(size), "bash", "-c", script]


def x_client(
    x_env: dict[str, str], *command: str
) -> subprocess.CompletedProcess[str]:
  """
  带着一次运行的 DISPLAY 与 XAUTHORITY 运行一个 X 客户端程序，
  捕获它的输出，不检查退出码
  参数：
      x_env (dict[str, str]): 这次运行的 DISPLAY 与 XAUTHORITY，
          覆盖当前环境里的同名变量
      command (str): 程序名及其参数，例如 xdotool 或 import 的命令行
  返回：
      subprocess.CompletedProcess[str]: 运行结果，含文本形式的标准输出与标准错误
  """
  return subprocess.run(
      command,
      env={**os.environ, **x_env},
      capture_output=True,
      text=True,
      check=False,
  )


def editor_ready(out_dir: Path, size: str) -> dict[str, str] | None:
  """
  就绪检查，limited_run.run() 每 0.2 秒调用一次，直到就绪或等待超时
  它从 display 文件读出 DISPLAY 与 XAUTHORITY，用 xdotool 找标题以 TITLE
  开头的可见窗口，把窗口移到左上角并拉到整屏大小
  参数：
      out_dir (Path): 证据目录
      size (str): 屏幕大小，形如 2100x1100
  返回：
      dict[str, str] | None: 窗口调整好时为 DISPLAY 与 XAUTHORITY，
          limited_run.run() 把它们并入运行状态。否则为 None
  """
  try:
    x_env = dict(
        zip(X_VARS, (out_dir / DISPLAY_FILE).read_text().split(), strict=True)
    )
  except (FileNotFoundError, ValueError):
    return None
  width, height = size.split("x")
  found = x_client(
      x_env,
      *["xdotool", "search", "--onlyvisible", "--name", f"^{TITLE}"],
      *["windowmove", "%1", "0", "0", "windowsize", "%1", width, height],
  )
  return x_env if found.returncode == 0 else None


def xdotool_key(spec: str) -> str:
  """
  把 ctrl+s 这样的一个 KEY 写法换成 xdotool key 的写法
  KEYS 里的名字照写。单个可打印 ASCII 字符写成十六进制 keysym，
  ASCII 字符的 keysym 等于它的码位。
  单个字符不照写，因为 xdotool 把 , 这样的字符当键名查，
  查不到时打印警告并跳过这个键，退出码仍为 0。
  遇到不认识的键时抛出 ValueError
  参数：
      spec (str): KEY 写法，组合里的各键用 + 连接
  返回：
      str: xdotool key 的按键写法
  """
  parts = []
  for part in spec.split("+"):
    if part in KEYS:
      parts.append(part)
    elif len(part) == 1 and " " <= part <= "~":
      parts.append(f"0x{ord(part):x}")
    else:
      raise ValueError(
          f"不认识的按键 {part!r}（在 {spec!r} 里）；"
          f"可用：{' '.join(KEYS)}，或单个 ASCII 字符"
      )
  return "+".join(parts)


def find_run(out_dir: Path) -> dict[str, object]:
  """
  按证据目录找出以它启动、仍在运行的那次运行
  参数：
      out_dir (Path): 证据目录
  返回：
      dict[str, object]: limited_run 的运行状态
  """
  runs = [
      run
      for run in limited_run.live_runs()
      if run.get("out") and Path(run["out"]) == out_dir
  ]
  if not runs:
    sys.exit(
        f"没有以 --out {out_dir} 启动、仍在运行的编辑器。先用 start 启动；limited_run.py status 列出正在运行的实例。"
    )
  return dict(runs[0])


def x_run(x_env: dict[str, str], *command: str) -> None:
  """
  运行一个 X 客户端程序，退出码不为 0 时带着它的标准错误退出
  参数：
      x_env (dict[str, str]): 这次运行的 DISPLAY 与 XAUTHORITY
      command (str): 程序名及其参数
  """
  result = x_client(x_env, *command)
  if result.returncode != 0:
    sys.exit(
        f"{command[0]} 失败（{result.returncode}）：{result.stderr.strip()}"
    )


def save_frame(
    out_dir: Path, x_env: dict[str, str], label: str, description: str
) -> Path:
  """
  用 import 截整屏，存为证据目录 frames 下的下一帧，
  并在 actions.log 追加一行，记下时间、动作描述与帧文件名
  参数：
      out_dir (Path): 证据目录
      x_env (dict[str, str]): 这次运行的 DISPLAY 与 XAUTHORITY
      label (str): 写进帧文件名的标签
      description (str): 写进 actions.log 的动作描述
  返回：
      Path: 帧文件路径
  """
  frames = out_dir / "frames"
  frames.mkdir(exist_ok=True)
  # 斜杠与空白换成下划线，免得斜杠被当成目录；只取前 40 个字符；动作的完整描述写在 actions.log 里
  label = re.sub(r"[\s/]+", "_", label)[:40]
  path = frames / f"{len(list(frames.glob('*.png'))) + 1:03d}-{label}.png"
  x_run(x_env, "import", "-window", "root", str(path))
  with open(out_dir / "actions.log", "a", encoding="utf-8") as log:
    log.write(f"{time.strftime('%H:%M:%S')}\t{description}\t{path.name}\n")
  return path


def drag_words(x1: int, y1: int, x2: int, y2: int) -> list[str]:
  """
  拼出 drag 的 xdotool 参数
  这些参数让 xdotool 在起点按下左键，按住时分 DRAG_STEPS 步移到终点，
  再松开左键
  参数：
      x1 (int): 起点横坐标
      y1 (int): 起点纵坐标
      x2 (int): 终点横坐标
      y2 (int): 终点纵坐标
  返回：
      list[str]: xdotool 的参数
  """
  words = ["mousemove", f"{x1}", f"{y1}", "sleep", "0.1"]
  words += ["mousedown", "1", "sleep", "0.1"]
  for step in range(1, DRAG_STEPS + 1):
    x = x1 + (x2 - x1) * step // DRAG_STEPS
    y = y1 + (y2 - y1) * step // DRAG_STEPS
    words += ["mousemove", f"{x}", f"{y}", "sleep", f"{DRAG_STEP_WAIT}"]
  return [*words, "sleep", "0.2", "mouseup", "1"]


def act(out_dir: Path, x_env: dict[str, str], args: argparse.Namespace) -> Path:
  """
  发出一个动作的输入，等 --wait 秒后存一帧
  shot 以外的动作先用 xdotool 发输入。
  type 的文字含可打印 ASCII 以外的字符，或 key 有不认识的键时，
  函数不发输入也不存帧，直接退出
  参数：
      out_dir (Path): 证据目录
      x_env (dict[str, str]): 这次运行的 DISPLAY 与 XAUTHORITY
      args (argparse.Namespace): 命令行参数
  返回：
      Path: 帧文件路径
  """
  action = args.action
  if action in BUTTONS:
    description = f"{action} {args.x} {args.y}"
    words = ["mousemove", f"{args.x}", f"{args.y}", "sleep", "0.1"]
    words += BUTTONS[action]
  elif action == "drag":
    description = f"drag {args.x1} {args.y1} {args.x2} {args.y2}"
    words = drag_words(args.x1, args.y1, args.x2, args.y2)
  elif action == "key":
    description = f"key {' '.join(args.keys)}"
    try:
      words = ["key", "--delay", "100", *map(xdotool_key, args.keys)]
    except ValueError as error:
      sys.exit(str(error))
  elif action == "type":
    if not all(" " <= ch <= "~" for ch in args.text):
      sys.exit("type 只收可打印 ASCII")
    description = f"type {args.text}"
    words = ["type", "--", args.text]
  else:
    description = "shot"
    words = []
  if words:
    x_run(x_env, "xdotool", *words)
  time.sleep(args.wait)
  return save_frame(
      out_dir, x_env, args.label or description.replace(" ", "-"), description
  )


def start(out_dir: Path, args: argparse.Namespace) -> int:
  """
  经 limited_run.run() 按 editor 模式启动编辑器，运行结束后返回
  编辑器窗口出现并调整到整屏大小后，limited_run.run() 打印 ready 事件。
  找不到 tools/ArkEditor/main.py、证据目录不空或 --size 写法不对时，
  函数不启动编辑器，直接退出
  参数：
      out_dir (Path): 证据目录，必须不存在或为空
      args (argparse.Namespace): 命令行参数
  返回：
      int: limited_run.run() 的退出码，被 stop 停掉时为 0
  """
  root = limited_run.game_checkout()
  if not (root / "tools" / "ArkEditor" / "main.py").is_file():
    sys.exit(f"{root} 下没有 tools/ArkEditor/main.py")
  if out_dir.exists() and any(out_dir.iterdir()):
    sys.exit(
        f"{out_dir} 不是空目录。每次启动用一个新目录，免得读到上一次的帧。"
    )
  if not re.fullmatch(r"\d+x\d+", args.size):
    sys.exit(f"--size 要写成 宽x高，例如 {DEFAULT_SIZE}")
  out_dir.mkdir(parents=True, exist_ok=True)
  code: int = limited_run.run(
      "editor",
      editor_command(root, out_dir, sys.executable, args.size),
      args.mem,
      args.timeout,
      {},
      out_dir,
      lambda: editor_ready(out_dir, args.size),
      args.ready_timeout,
  )
  return code


def run_command(args: argparse.Namespace) -> int:
  """
  经 limited_run.run() 按 headless 模式运行 -- 之后的命令
  命令在 xvfb-run 起的默认大小的屏幕里运行。
  PYTHONHASHSEED 取当前环境里的值，没有时取 limited_run.seed() 的值。
  -- 之后没有命令时，函数不运行，直接退出
  参数：
      args (argparse.Namespace): 命令行参数
  返回：
      int: limited_run.run() 的退出码。命令自己结束时，它就是命令的退出码
  """
  if args.command[:1] != ["--"] or len(args.command) < 2:
    sys.exit("在 -- 之后给出要运行的命令")
  limited_run.game_checkout()
  seed = {
      "PYTHONHASHSEED": os.environ.get("PYTHONHASHSEED", limited_run.seed())
  }
  code: int = limited_run.run(
      "headless",
      [*xvfb(DEFAULT_SIZE), *args.command[1:]],
      args.mem,
      args.timeout,
      seed,
  )
  return code


def main(argv: list[str] | None = None) -> int:
  """
  命令行入口
  参数：
      argv (list[str] | None): 命令行参数，不含脚本名；为 None 时读 sys.argv
  返回：
      int: 退出码
  """
  parser = argparse.ArgumentParser(
      prog="arkeditor.py",
      description=(
          "经 limited_run 在虚拟 X 显示里启动 ArkEditor 并用真实输入操作它，"
          "或在虚拟 X 显示里运行任意命令"
      ),
  )
  sub = parser.add_subparsers(dest="action", required=True)
  limits = argparse.ArgumentParser(add_help=False)
  limits.add_argument(
      "--mem",
      type=limited_run.parse_size,
      default=DEFAULT_MEM,
      help=f"内存上限，默认 {DEFAULT_MEM}",
  )
  limits.add_argument(
      "--timeout", type=int, default=600, help="运行时限（秒），默认 600"
  )
  out = argparse.ArgumentParser(add_help=False)
  out.add_argument(
      "--out",
      required=True,
      type=Path,
      help="证据目录：start 时必须不存在或为空，之后的命令用它找到这次运行",
  )
  frame = argparse.ArgumentParser(add_help=False, parents=[out])
  frame.add_argument("--label", help="写进帧文件名的标签")
  frame.add_argument(
      "--wait", type=float, default=1.0, help="动作后等多少秒再取帧，默认 1"
  )
  launch = sub.add_parser(
      "start",
      parents=[out, limits],
      help="启动编辑器并一直运行到 stop 或时限为止；它占着终端，要接着发动作就在命令后加 & 放到后台",
  )
  launch.add_argument(
      "--ready-timeout",
      type=int,
      default=120,
      help="等编辑器窗口出现的秒数，默认 120",
  )
  launch.add_argument(
      "--size", default=DEFAULT_SIZE, help=f"屏幕大小，默认 {DEFAULT_SIZE}"
  )
  for name in BUTTONS:
    pointer = sub.add_parser(name, parents=[frame])
    pointer.add_argument("x", type=int)
    pointer.add_argument("y", type=int)
  drag = sub.add_parser("drag", parents=[frame])
  for name in ("x1", "y1", "x2", "y2"):
    drag.add_argument(name, type=int)
  sub.add_parser("key", parents=[frame]).add_argument("keys", nargs="+")
  sub.add_parser("type", parents=[frame]).add_argument("text")
  sub.add_parser("shot", parents=[frame])
  sub.add_parser("stop", parents=[out])
  sub.add_parser(
      "run",
      parents=[limits],
      help="在 limited_run 下用 xvfb-run 运行 -- 之后的命令",
  ).add_argument("command", nargs=argparse.REMAINDER)
  args = parser.parse_args(argv)
  if args.action == "run":
    return run_command(args)
  out_dir = args.out.expanduser().resolve()
  if args.action == "start":
    return start(out_dir, args)
  run = find_run(out_dir)
  if args.action == "stop":
    return limited_run.cmd_stop(str(run["pid"]))
  if any(name not in run for name in X_VARS):
    sys.exit("编辑器还没就绪，等 start 打印 ready 事件后再操作。")
  x_env = {name: str(run[name]) for name in X_VARS}
  print(f"frame: {act(out_dir, x_env, args)}")
  return 0


if __name__ == "__main__":
  sys.exit(main())
