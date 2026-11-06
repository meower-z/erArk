#!/usr/bin/env python3
"""
操作由 tk_game.py 启动的游戏窗口。

type、click、scroll、advance 之后自动截一帧到证据目录的 frames/，并把动作写进 actions.log。
窗口、显示和证据目录从 limited_run.py 记下的运行状态读取；按钮坐标与游戏当前等待的输入从探针写的 probe.json 读取。
只有一个 Tk 实例在运行时操作它；有几个时用 --out <证据目录> 或 --slot <槽位> 指定，不指定就报错并列出它们。

用法（--out 与 --slot 写在动作之前）：
  tk.py [--out <证据目录> | --slot <槽位>] <动作> ...
  tk.py type <返回值>    在输入框输入返回值并回车；只接受游戏当前等待的返回值，自由文本输入时接受任意文字
  tk.py click <返回值>   点击可见的按钮
  tk.py scroll up|down [格数]
  tk.py advance          点一下输入框，推进等待提示
  tk.py shot [标签]      截当前画面
  tk.py keys             列出游戏当前等待的返回值与可见按钮
  tk.py doctor           体检：窗口尺寸、探针是否在更新、内存、字体
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import limited_run

SCROLL_POINT = (1050, 550)
MIN_WINDOW_WIDTH = 2000
PROBE_MAX_AGE_S = 5
MEMORY_WARN_RATIO = 0.97
# wait_for_probe_change 的三个秒数：探针内容一直与动作前相同时的等待上限、总的等待上限、两次读探针的间隔
CHANGE_LIMIT_S = 3.0
SETTLE_LIMIT_S = 20.0
POLL_INTERVAL_S = 0.1


def load_state(slot=None, out=None):
  """
  选出要操作的 Tk 实例并读取它的状态：给了槽位或证据目录就按它选，没给时要求恰好有一个 Tk 实例在运行
  参数：
      slot (int | None): 实例占的任一槽位
      out (Path | None): 实例的证据目录（tk_game.py --out）
  返回：
      dict: 含 display、window、probe、out、unit
  """
  runs = [run for run in limited_run.live_runs() if run.get("mode") == "tk"]
  if slot is not None:
    runs = [run for run in runs if slot in run["slots"]]
  if out is not None:
    runs = [
        run
        for run in runs
        if run.get("out") and Path(run["out"]) == out.expanduser().resolve()
    ]
  if not runs:
    sys.exit(
        "没有符合的 Tk 实例在运行。先用 tk_game.py --out <目录> 启动；"
        "--out 与 --slot 要与 limited_run.py status 列出的一致。"
    )
  if len(runs) > 1:
    sys.exit(
        "有几个 Tk 实例在运行，用 --out <证据目录> 或 --slot <槽位> 指定要操作的那个：\n"
        + "\n".join(limited_run.describe_run(run) for run in runs)
    )
  state = runs[0]
  if "window" not in state:
    sys.exit("这个 Tk 实例还没就绪，等 tk_game.py 打印 ready 事件后再操作。")
  return state


def xdo(state, *args):
  """
  在实例的显示上执行一条 xdotool 命令
  参数：
      state (dict): 实例状态
      args (str): xdotool 参数
  返回：
      str: 标准输出
  """
  return subprocess.run(
      ["xdotool", *args],
      check=True,
      capture_output=True,
      text=True,
      env={**os.environ, "DISPLAY": state["display"]},
  ).stdout


def click_at(state, x, y, button="1", repeat=1):
  """
  在窗口内坐标处点击鼠标
  参数：
      state (dict): 实例状态
      x (int): 窗口内横坐标
      y (int): 窗口内纵坐标
      button (str): 鼠标键，1 左键，4 上滚，5 下滚
      repeat (int): 次数
  """
  xdo(
      state,
      "mousemove",
      "--window",
      state["window"],
      str(x),
      str(y),
      "click",
      "--repeat",
      str(repeat),
      button,
  )


def read_probe(state):
  """
  读取探针最近一次写出的内容
  参数：
      state (dict): 实例状态
  返回：
      dict: 含 buttons、awaiting、input、ts；读不到时各项为空
  """
  try:
    return json.loads(Path(state["probe"]).read_text(encoding="utf-8"))
  except (OSError, ValueError):
    return {"buttons": {}, "awaiting": None, "input": None, "ts": 0}


def shot(state, label):
  """
  截取游戏窗口，存为证据目录下的下一帧
  参数：
      state (dict): 实例状态
      label (str): 写进文件名的标签
  返回：
      Path: 帧文件路径
  """
  frames = Path(state["out"]) / "frames"
  frames.mkdir(exist_ok=True)
  # 标签可能是 type 输入的任意文字：斜杠与空白换成下划线，免得斜杠被当成目录；只取前 40 个字符，
  # 免得文件名超长（全文在 actions.log 里）
  label = re.sub(r"[\s/]+", "_", label)[:40]
  path = frames / f"{len(list(frames.glob('*.png'))) + 1:03d}-{label}.png"
  subprocess.run(
      [
          "import",
          "-display",
          state["display"],
          "-window",
          state["window"],
          str(path),
      ],
      check=True,
  )
  return path


def awaits_input(probe: dict[str, Any]) -> bool:
  """
  判断探针内容是否表明游戏正在等输入
  参数：
      probe (dict): 探针内容
  返回：
      bool: 等待提示（"wait"）、自由文本输入（"text"），或等待列表里至少一个返回值是可见按钮时为 True
  """
  awaiting = probe["awaiting"]
  if awaiting in ("wait", "text"):
    return True
  # askfor_all 在自身内运行所选按钮的回调（如读档）。
  # 回调运行中、回调里没有正在进行的等待时，awaiting 是该按钮所在面板的列表。
  # 因此列表里的返回值没有一个是可见按钮时，不算游戏在等输入。
  return isinstance(awaiting, list) and any(
      key in probe["buttons"] for key in awaiting
  )


def wait_for_probe_change(state, before, input_sent=True):
  """
  动作后每 POLL_INTERVAL_S 秒读一次探针，下列任一条件成立时返回：
  - 探针内容（awaiting 与 buttons）与动作前不同过，当前内容已从 ts 不同的两份探针里连续读到，
    并且 input_sent 为 False 或当前内容通过 awaits_input
  - 超过 CHANGE_LIMIT_S 秒仍没读到与动作前不同的内容
  - 超过 SETTLE_LIMIT_S 秒
  参数：
      state (dict): 实例状态
      before (dict): 动作前的探针内容
      input_sent (bool): 为 True 时第一个条件还要求当前内容通过 awaits_input
  """
  start = time.monotonic()
  changed = False
  # 读到当前内容的第一份探针，内容一变就换成新读到的那份。
  # 之后读到的探针 ts 与它不同，说明探针又写出了一次相同的内容。
  first_seen: dict[str, Any] | None = None
  while True:
    now = read_probe(state)
    view = (now["awaiting"], now["buttons"])
    changed = changed or view != (before["awaiting"], before["buttons"])
    if first_seen is None or view != (
        first_seen["awaiting"],
        first_seen["buttons"],
    ):
      first_seen = now
    elif (
        changed
        and now["ts"] != first_seen["ts"]
        and (not input_sent or awaits_input(now))
    ):
      return
    elapsed = time.monotonic() - start
    if elapsed > SETTLE_LIMIT_S or (not changed and elapsed > CHANGE_LIMIT_S):
      return
    time.sleep(POLL_INTERVAL_S)


def describe_keys(probe):
  """
  把等待列表与可见按钮写成两行说明
  参数：
      probe (dict): 探针内容
  返回：
      str: 说明文字
  """
  awaiting = probe["awaiting"]
  if awaiting == "wait":
    head = "awaiting: 等待提示（用 advance 推进）"
  elif awaiting == "text":
    head = "awaiting: 自由文本输入（用 type 输入任意文字）"
  elif awaiting is None:
    head = "awaiting: 未知（游戏没在等待输入，或还没进入第一次等待）"
  else:
    head = f"awaiting ({len(awaiting)}): {' '.join(awaiting)}"
  visible = [
      key
      for key in probe["buttons"]
      if not isinstance(awaiting, list) or key in awaiting
  ]
  return f"{head}\nvisible ({len(visible)}): {' '.join(visible)}"


def act(state, description, label, before, input_sent=True):
  """
  动作之后的统一收尾：等重绘、截帧、记日志、打印帧与按键
  参数：
      state (dict): 实例状态
      description (str): 写进 actions.log 的动作描述
      label (str): 帧文件名标签
      before (dict): 动作前的探针内容
      input_sent (bool): 传给 wait_for_probe_change。scroll 传 False，因为滚动可能把按钮全部移出画面
  """
  wait_for_probe_change(state, before, input_sent)
  frame = shot(state, label)
  # 描述里的换行、制表符等控制字符按 JSON 字符串内部的写法写成转义（如 \n、\t）。
  # 这样每个动作在 actions.log 里正好是一行三列。
  escaped = json.dumps(description, ensure_ascii=False)[1:-1]
  with open(Path(state["out"]) / "actions.log", "a", encoding="utf-8") as f:
    f.write(f"{time.strftime('%H:%M:%S')}\t{escaped}\t{frame.name}\n")
  print(f"frame: {frame}")
  print(describe_keys(read_probe(state)))


def doctor(state):
  """
  检查实例是否值得操作，逐项打印 ok 或 FAIL
  参数：
      state (dict): 实例状态
  返回：
      bool: 全部通过时为 True
  """
  geometry = xdo(state, "getwindowgeometry", state["window"])
  size = geometry.split("Geometry:")[-1].strip()
  width = int(size.split("x")[0]) if "x" in size else 0
  age = time.time() - read_probe(state)["ts"]
  unit_dir = limited_run.scope_dir(state["unit"])
  # 文件缓存在到上限前会被回收，所以只看回收不了的部分，与启动时的余量检查同一口径；读不到时判 FAIL
  try:
    memory = limited_run.mib(
        limited_run.unreclaimable(
            limited_run.read_stat(unit_dir / "memory.stat")
        )
    )
  except (OSError, ValueError, KeyError):
    memory = None
  memory_text = "读不到" if memory is None else f"{memory} MiB"
  cap = state["mem_max_mib"]
  fonts = subprocess.run(["fc-list"], capture_output=True, text=True).stdout
  checks = [
      (width >= MIN_WINDOW_WIDTH, f"窗口 {size}（需宽于 {MIN_WINDOW_WIDTH}）"),
      (
          age < PROBE_MAX_AGE_S,
          f"probe.json {age:.1f} 秒前更新（需少于 {PROBE_MAX_AGE_S} 秒）",
      ),
      (
          memory is not None and memory < cap * MEMORY_WARN_RATIO,
          f"不可回收内存 {memory_text}（anon+shmem+kernel，需低于 {int(cap * MEMORY_WARN_RATIO)} MiB，上限 {cap}）",
      ),
      ("Sarasa" in fonts or "更纱" in fonts, "等距更纱黑体已安装"),
  ]
  for ok, text in checks:
    print(f"{'ok  ' if ok else 'FAIL'} {text}")
  return all(ok for ok, _ in checks)


def main():
  """
  命令行入口
  """
  parser = argparse.ArgumentParser(description="操作 tk_game.py 启动的游戏窗口")
  parser.add_argument(
      "--out",
      type=Path,
      help="要操作的实例的证据目录；有几个 Tk 实例在运行时用它或 --slot 指定",
  )
  parser.add_argument("--slot", type=int, help="要操作的实例占的任一槽位")
  sub = parser.add_subparsers(dest="action", required=True)
  sub.add_parser("type").add_argument("key")
  sub.add_parser("click").add_argument("key")
  scroll = sub.add_parser("scroll")
  scroll.add_argument("direction", choices=["up", "down"])
  scroll.add_argument("notches", nargs="?", type=int, default=1)
  sub.add_parser("advance")
  sub.add_parser("shot").add_argument("label", nargs="?", default="shot")
  sub.add_parser("keys")
  sub.add_parser("doctor")
  args = parser.parse_args()

  state = load_state(args.slot, args.out)
  probe = read_probe(state)
  if args.action == "doctor":
    sys.exit(0 if doctor(state) else 1)
  if args.action == "keys":
    print(describe_keys(probe))
  elif args.action == "shot":
    act(state, f"shot {args.label}", args.label, probe)
  elif args.action == "type":
    awaiting = probe["awaiting"]
    if awaiting != "text" and (
        not isinstance(awaiting, list) or args.key not in awaiting
    ):
      sys.exit(f"游戏当前不等待 {args.key}。{describe_keys(probe)}")
    # 先点输入框取得焦点，再按真实键盘事件输入；带 --window 的合成事件 Tk 会忽略
    click_at(state, *probe["input"])
    # "--" 之后才是要输入的文字，免得以 - 开头的自由文本被 xdotool 当成选项
    xdo(state, "type", "--delay", "40", "--", args.key)
    xdo(state, "key", "Return")
    act(state, f"type {args.key}", f"type-{args.key}", probe)
  elif args.action == "click":
    if args.key not in probe["buttons"]:
      sys.exit(
          f"按钮 {args.key} 不在当前画面上。滚动后用 keys 重新查看；一直找不到说明它的前提没满足。"
      )
    click_at(state, *probe["buttons"][args.key])
    act(
        state,
        f"click {args.key} at {probe['buttons'][args.key]}",
        f"click-{args.key}",
        probe,
    )
  elif args.action == "scroll":
    click_at(
        state,
        *SCROLL_POINT,
        button={"up": "4", "down": "5"}[args.direction],
        repeat=args.notches,
    )
    act(
        state,
        f"scroll {args.direction} {args.notches}",
        f"scroll-{args.direction}",
        probe,
        input_sent=False,
    )
  elif args.action == "advance":
    # 等待提示时，点中日志里按钮的左键不会结束等待。输入框在日志区外，上面没有按钮。
    click_at(state, *probe["input"])
    act(state, "advance", "advance", probe)


if __name__ == "__main__":
  main()
