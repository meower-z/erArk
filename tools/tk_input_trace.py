# -*- coding: UTF-8 -*-
"""
Tk 窗口版输入卡死的诊断启动器（临时排查用，不改动游戏代码）。

用法：在游戏根目录执行 `python tools/tk_input_trace.py`，照常游玩并复现卡死，
然后把游戏根目录下生成的 tk_input_trace.log 发出来。

它只是包了一层日志再去跑 game.py，记录以下几件事：
每次左键点击进入/离开输入处理时的门禁状态、每次提交输入、每次"重新开放输入"的
标记入队与真正生效、以及任何线程里未捕获的异常。日志随写随落盘，卡死后直接关窗口也不会丢。
"""
import os
import runpy
import sys
import threading
import time
import tkinter
import traceback

LOG_PATH = os.path.join(os.getcwd(), "tk_input_trace.log")
""" 日志文件路径，固定写在游戏根目录 """

_fp = open(LOG_PATH, "a", encoding="utf-8", buffering=1)


def _log(message: str):
    """
    参数：message(str) 为要记录的一行内容；返回：None；
    用途：带单调时钟时间戳写入一行日志，行缓冲保证卡死时已写内容不会丢失。
    """
    _fp.write("%.3f %s\n" % (time.monotonic(), message))


def _flow_stack() -> str:
    """
    参数：无；返回：str 为游戏逻辑线程最内层几层调用；
    用途：卡死时用来判断逻辑线程停在哪里，线程已退出则返回 DEAD。
    """
    try:
        thread = None
        for item in threading.enumerate():
            if item.name == "flowthread":
                thread = item
                break
        if thread is None:
            return "DEAD"
        frame = sys._current_frames().get(thread.ident)
        names = []
        while frame is not None and len(names) < 4:
            names.append("%s:%s" % (os.path.basename(frame.f_code.co_filename), frame.f_code.co_name))
            frame = frame.f_back
        return " < ".join(names)
    except Exception:
        return "?"


def _install():
    """
    参数：无；返回：None；
    用途：在 Tk 主循环启动后给输入相关的几个函数包一层日志，并重新绑定左键
          （原绑定持有的是未包装的函数对象，不重绑就记不到点击）。
    """
    from Script.Core import cache_control, io_init, key_listion_event, main_frame

    cache = cache_control.cache
    origin_send_input = main_frame.send_input

    def send_input(*args, **kwargs):
        """包一层日志的输入提交，参数与原函数一致，无返回值。"""
        _log("submit ENTER armed=%s wait_flag=%s order=%r" % (main_frame.input_armed, cache.wframe_mouse.w_frame_up, main_frame.get_order()))
        try:
            result = origin_send_input(*args, **kwargs)
        except Exception:
            _log("submit RAISED\n" + traceback.format_exc())
            raise
        _log("submit EXIT  armed=%s" % main_frame.input_armed)
        return result

    main_frame.send_input = send_input

    origin_arm_input = io_init.arm_input

    def arm_input(*args, **kwargs):
        """包一层日志的"重新开放输入"标记入队，参数与原函数一致，无返回值。"""
        _log("rearm PUSH flow=%s" % _flow_stack())
        return origin_arm_input(*args, **kwargs)

    io_init.arm_input = arm_input

    origin_do_arm = main_frame._do_arm

    def do_arm(*args, **kwargs):
        """包一层日志的"重新开放输入"真正生效，参数与原函数一致，无返回值。"""
        result = origin_do_arm(*args, **kwargs)
        _log("rearm DONE armed=%s" % main_frame.input_armed)
        return result

    main_frame._do_arm = do_arm

    origin_mouse_left_check = key_listion_event.mouse_left_check

    def mouse_left_check(event):
        """包一层日志的左键处理，参数 event 为 Tk 事件对象，无返回值。"""
        _log("click ENTER armed=%s wait_flag=%s xy=(%s,%s) widget=%s" % (main_frame.input_armed, cache.wframe_mouse.w_frame_up, event.x_root, event.y_root, event.widget))
        try:
            result = origin_mouse_left_check(event)
        except Exception:
            _log("click RAISED\n" + traceback.format_exc())
            raise
        _log("click EXIT  armed=%s wait_flag=%s" % (main_frame.input_armed, cache.wframe_mouse.w_frame_up))
        return result

    key_listion_event.mouse_left_check = mouse_left_check
    key_listion_event.wframe.bind("<ButtonPress-1>", mouse_left_check)
    _log("tracer installed")


def _heartbeat(root):
    """
    参数：root 为 Tk 根窗口；返回：None；
    用途：每秒记录一次门禁状态与逻辑线程位置，卡死后可据此看出是谁停住了。
    """
    from Script.Core import cache_control, io_init, main_frame

    try:
        _log("state armed=%s pending=%s wait_flag=%s order_queue=%d flow=%s" % (
            main_frame.input_armed,
            main_frame._arm_after_id is not None,
            cache_control.cache.wframe_mouse.w_frame_up,
            io_init._order_queue.qsize(),
            _flow_stack(),
        ))
    except Exception:
        pass
    root.after(1000, lambda: _heartbeat(root))


def _thread_excepthook(args):
    """参数：args 为线程异常信息对象；返回：None；用途：记录任何线程里未捕获的异常。"""
    _log("THREAD EXCEPTION in %s\n%s" % (getattr(args.thread, "name", "?"), "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))))


threading.excepthook = _thread_excepthook

_origin_mainloop = tkinter.Misc.mainloop


def _mainloop(self, *args, **kwargs):
    """参数与 Tk 原 mainloop 一致；返回：原返回值；用途：在主循环开始后装日志和心跳。"""
    try:
        self.after(800, _install)
        self.after(1000, lambda: _heartbeat(self))
    except Exception:
        pass
    return _origin_mainloop(self, *args, **kwargs)


tkinter.Misc.mainloop = _mainloop

if sys.platform != "win32":
    # 非 Windows 的 Tk 不认最大化状态 "zoomed"，这里翻译成等价写法，
    # 否则窗口创建就会失败，本工具在 Linux/macOS 上也就没法用来复现
    _origin_wm_state = tkinter.Wm.wm_state

    def _wm_state(window, newstate=None):
        """参数与 Tk 原 wm_state 一致；返回：原返回值；用途：把 zoomed 映射为 -zoomed 属性。"""
        if newstate == "zoomed":
            window.attributes("-zoomed", True)
            return None
        return _origin_wm_state(window, newstate)

    tkinter.Wm.wm_state = _wm_state
    tkinter.Wm.state = _wm_state

sys.path.insert(0, os.getcwd())
runpy.run_path("game.py", run_name="__main__")
