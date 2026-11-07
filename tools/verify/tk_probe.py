#!/usr/bin/env python
"""
Tk 取证启动器与只读探针。不要直接运行，由 tk_game.py 调用。

固定随机种子，记录游戏当前等待的输入，然后运行当前目录（erArk checkout 根目录）的 game.py。
每 300ms 把下列内容原子地写到 ERARK_PROBE_JSON：
  buttons   可见按钮 {返回值: [x, y]}，取按钮首字符的中心，换算成游戏窗口内坐标
  awaiting  游戏当前等待的输入：askfor_all 与 askfor_int 的选项列表、
            askfor_wait 时为 "wait"（包括它内部调用的 askfor_str）、其余 askfor_str 时为 "text"、
            当前没有记录到等待输入时为 null（包括首次等待之前和两次等待之间）
  input     输入框中心的窗口内坐标
  ts        写入时间
探针只读取控件位置和等待列表，不改动任何游戏状态；同一种子下，有探针与没有探针的运行仍可对照。
"""

import importlib.abc
import importlib.util
import json
import os
import random
import runpy
import sys
import time
import tkinter
import traceback
from pathlib import Path

import numpy

PROBE_JSON = os.environ["ERARK_PROBE_JSON"]
SEED = int(os.environ["ERARK_SEED"])

_awaiting = None
_dump_failed = False


def _recorded(original, awaiting_of):
  """
  给一个 askfor 函数套一层只读记录：等待期间 _awaiting 为 awaiting_of 算出的值，返回后恢复调用前的值
  参数：
      original (function): 原 askfor 函数
      awaiting_of (function): 由调用参数算出等待内容的函数，参数与原函数相同
  返回：
      function: 包装后的函数
  """

  def wrapper(*args, **kwargs):
    """
    记录等待内容后调用原函数
    返回：
        原函数的返回值
    """
    global _awaiting
    previous = _awaiting
    _awaiting = awaiting_of(*args, **kwargs)
    try:
      return original(*args, **kwargs)
    finally:
      _awaiting = previous

  return wrapper


def _record_awaiting(flow_handle):
  """
  给 flow_handle 的 askfor_all、askfor_int、askfor_wait、askfor_str 套上等待记录
  参数：
      flow_handle (module): Script.Core.flow_handle
  """

  def listed(values):
    """
    等待内容为可接受的返回值列表
    参数：
        values (list): 本次等待接受的返回值
    返回：
        list: 字符串化的返回值
    """
    return [str(item) for item in values]

  # 两个 lambda 的参数名照抄原函数（askfor_all 的 input_list、askfor_int 的 list），按关键字传参时也能取到列表
  flow_handle.askfor_all = _recorded(
      flow_handle.askfor_all,
      lambda input_list, *args, **kwargs: listed(input_list),
  )
  flow_handle.askfor_int = _recorded(
      flow_handle.askfor_int, lambda list, *args, **kwargs: listed(list)
  )
  flow_handle.askfor_wait = _recorded(
      flow_handle.askfor_wait, lambda *args, **kwargs: "wait"
  )
  # askfor_wait 内部调用 askfor_str，这时 awaiting 仍是 "wait"；按钮回调里的 askfor_str（如睡眠面板输入时长）
  # 在 askfor_all 内部运行，仍记为 "text"
  flow_handle.askfor_str = _recorded(
      flow_handle.askfor_str,
      lambda *args, **kwargs: "wait" if _awaiting == "wait" else "text",
  )


class _FlowHandleHook(importlib.abc.MetaPathFinder):
  """
  在 Script.Core.flow_handle 首次加载完成时装上等待记录，早于任何模块拷走 askfor_all
  """

  def find_spec(self, name, path, target=None):
    """
    只拦截 Script.Core.flow_handle，包一层 exec_module
    参数：
        name (str): 模块全名
        path: 搜索路径
        target: 目标模块
    返回：
        ModuleSpec | None: 包装后的 spec，其他模块返回 None
    """
    if name != "Script.Core.flow_handle":
      return None
    sys.meta_path.remove(self)
    spec = importlib.util.find_spec(name)
    assert spec is not None and spec.loader is not None
    exec_module = spec.loader.exec_module

    def exec_and_record(module):
      """
      执行模块后装上等待记录
      参数：
          module (module): 刚加载的 flow_handle
      """
      exec_module(module)
      _record_awaiting(module)

    spec.loader.exec_module = exec_and_record
    return spec


def _dump(root):
  """
  写一次 probe.json，并安排 300ms 后再写；首次失败时把堆栈打到 stderr
  参数：
      root (tkinter.Misc): Tk 根窗口
  """
  global _dump_failed
  try:
    import Script.Core.main_frame as mf

    tb = mf.textbox
    ox, oy = (
        tb.winfo_rootx() - root.winfo_rootx(),
        tb.winfo_rooty() - root.winfo_rooty(),
    )
    buttons = {}
    for cmd_number, tag in list(mf.cmd_tag_map.items()):
      rng = tb.tag_ranges(tag)
      if not rng:
        continue
      # 首字符必在该按钮 tag 内，点它一定触发；范围尾端在换行时会跑到很靠右
      bbox = tb.bbox(rng[0])
      if not bbox:
        continue
      x, y, w, h = bbox
      buttons[str(cmd_number)] = [ox + x + max(w // 2, 4), oy + y + h // 2]
    box = mf.inputbox
    entry = [
        box.winfo_rootx() - root.winfo_rootx() + box.winfo_width() // 2,
        box.winfo_rooty() - root.winfo_rooty() + box.winfo_height() // 2,
    ]
    tmp = PROBE_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
      json.dump(
          {
              "ts": time.time(),
              "buttons": buttons,
              "awaiting": _awaiting,
              "input": entry,
          },
          f,
          ensure_ascii=False,
      )
    os.replace(tmp, PROBE_JSON)
  except Exception:
    if not _dump_failed:
      _dump_failed = True
      print("tk_probe: 写 probe.json 失败", file=sys.stderr)
      traceback.print_exc()
  root.after(300, lambda: _dump(root))


_real_mainloop = tkinter.Misc.mainloop


def _mainloop(self, *args, **kwargs):
  """
  进入 Tk 主循环前挂上探针
  参数：
      self (tkinter.Misc): Tk 根窗口
  返回：
      原 mainloop 的返回值
  """
  self.after(600, lambda: _dump(self))
  return _real_mainloop(self, *args, **kwargs)


sys.meta_path.insert(0, _FlowHandleHook())
tkinter.Misc.mainloop = _mainloop
random.seed(SEED)
numpy.random.seed(SEED)
sys.path.insert(0, str(Path.cwd()))
runpy.run_path("game.py", run_name="__main__")
