#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
  tk.py advance          在日志区点一下，推进等待提示
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import limited_run

# 日志文字列内的空白处：点这里推进等待提示；最右侧边距不在可点击区域内。坐标针对 tk_game.SCREEN 的 2100 宽窗口
ADVANCE_POINT = (700, 550)
SCROLL_POINT = (1050, 550)
MIN_WINDOW_WIDTH = 2000
PROBE_MAX_AGE_S = 5
MEMORY_WARN_RATIO = 0.97


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
        "没有符合的 Tk 实例在运行。先用 tk_game.py --out <目录> 启动；--out 与 --slot 要与 limited_run.py status 列出的一致。"
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
  # 标签可能是 type 输入的任意文字：斜杠与空白换成下划线，免得斜杠被当成目录；只取前 40 个字符，免得文件名超长（全文在 actions.log 里）
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


def wait_for_probe_change(state, before, limit=3.0):
  """
  等探针内容（按钮或等待列表）与动作前不同，最多 limit 秒，然后再等 0.5 秒让 Tk 画完
  参数：
      state (dict): 实例状态
      before (dict): 动作前的探针内容
      limit (float): 最长等待秒数
  """
  deadline = time.monotonic() + limit
  while time.monotonic() < deadline:
    now = read_probe(state)
    if (
        now["buttons"] != before["buttons"]
        or now["awaiting"] != before["awaiting"]
    ):
      break
    time.sleep(0.2)
  time.sleep(0.5)


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


def act(state, description, label, before):
  """
  动作之后的统一收尾：等重绘、截帧、记日志、打印帧与按键
  参数：
      state (dict): 实例状态
      description (str): 写进 actions.log 的动作描述
      label (str): 帧文件名标签
      before (dict): 动作前的探针内容
  """
  wait_for_probe_change(state, before)
  frame = shot(state, label)
  with open(Path(state["out"]) / "actions.log", "a", encoding="utf-8") as f:
    f.write(f"{time.strftime('%H:%M:%S')}\t{description}\t{frame.name}\n")
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
    )
  elif args.action == "advance":
    click_at(state, *ADVANCE_POINT)
    act(state, "advance", "advance", probe)


if __name__ == "__main__":
  main()
