#!/usr/bin/env python
"""
Tk 取证启动器与只读探针。不要直接运行，由 tk_game.py 调用。

固定随机种子，记录游戏当前等待的输入，然后运行当前目录（erArk checkout 根目录）的 game.py。
每 300ms 把下列内容原子地写到 ERARK_PROBE_JSON：
  buttons   可见按钮 {返回值: [x, y]}，取按钮首字符的中心，换算成游戏窗口内坐标
  awaiting  游戏当前等待的输入：Tk 前端分页暂停输出时为 "wait"，否则为
            askfor_all 与 askfor_int 的选项列表、askfor_wait 时的 "wait"、
            askfor_str 时的 "text"，未记录到等待输入时为 null（包括首次等待之前和两次等待之间）
  page      Tk 前端已解除分页暂停的累计次数，每次解除暂停加 1
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
from typing import Any

import numpy

PROBE_JSON = os.environ["ERARK_PROBE_JSON"]
SEED = int(os.environ["ERARK_SEED"])

_awaiting = None
_dump_failed = False
_frontend: Any = None


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
    flow_handle.askfor_str = _recorded(
        flow_handle.askfor_str, lambda *args, **kwargs: "text"
    )


def _record_frontend(app):
    """
    包装 `TkFrontend.run`，在前端启动时把实例保存到 `_frontend`

    参数：
    app (module) -- 刚加载的 `Script.Frontend.Tk.app` 模块

    返回值类型：None
    """
    real_run = app.TkFrontend.run

    def run(self):
        """
        将当前 `TkFrontend` 实例记入 `_frontend` 后调用原 `run` 方法

        参数：
        self (TkFrontend) -- 当前 Tk 前端实例

        返回值类型：None
        """
        global _frontend
        _frontend = self
        return real_run(self)

    app.TkFrontend.run = run


class _ModuleHook(importlib.abc.MetaPathFinder):
    """一次性元路径导入钩子，在目标模块首次加载执行完成后触发记录回调。"""

    def __init__(self, name, record):
        """
        保存目标模块全名与加载完成后的回调函数

        参数：
        name (str) -- 要拦截的模块全名
        record (Callable) -- 模块执行完成后调用的回调

        返回值类型：None
        """
        self.name = name
        self.record = record

    def find_spec(self, name, path, target=None):
        """
        拦截目标模块的查找，移除自身并包装其 loader 的 `exec_module` 以在执行后调用回调

        参数：
        name (str) -- 正在导入的模块全名
        path (Sequence[str] | None) -- 搜索路径
        target (ModuleType | None) -- 目标模块对象

        返回值类型：ModuleSpec | None -- 命中目标模块时返回包装后的 spec，其他模块返回 None
        """
        if name != self.name:
            return None
        sys.meta_path.remove(self)
        spec = importlib.util.find_spec(name)
        assert spec is not None and spec.loader is not None
        exec_module = spec.loader.exec_module

        def exec_and_record(module):
            """
            执行目标模块后调用记录回调

            参数：
            module (module) -- 刚加载完成的目标模块

            返回值类型：None
            """
            exec_module(module)
            self.record(module)

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
        tb = _frontend.window.textbox
        ox, oy = (
            tb.winfo_rootx() - root.winfo_rootx(),
            tb.winfo_rooty() - root.winfo_rooty(),
        )
        buttons = {}
        for cmd_number, tag in list(_frontend.renderer.cmd_tag_map.items()):
            rng = tb.tag_ranges(tag)
            if not rng:
                continue
            # 首字符必在该按钮 tag 内，点它一定触发；范围尾端在换行时会跑到很靠右
            bbox = tb.bbox(rng[0])
            if not bbox:
                continue
            x, y, w, h = bbox
            buttons[str(cmd_number)] = [
                ox + x + max(w // 2, 4),
                oy + y + h // 2,
            ]
        box = _frontend.window.inputbox
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
                    "awaiting": (
                        "wait" if _frontend.pager.hold != "none" else _awaiting
                    ),
                    "page": _frontend.pager.turns,
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


sys.meta_path.insert(
    0, _ModuleHook("Script.Core.flow_handle", _record_awaiting)
)
sys.meta_path.insert(0, _ModuleHook("Script.Frontend.Tk.app", _record_frontend))
tkinter.Misc.mainloop = _mainloop
random.seed(SEED)
numpy.random.seed(SEED)
sys.path.insert(0, str(Path.cwd()))
runpy.run_path("game.py", run_name="__main__")
