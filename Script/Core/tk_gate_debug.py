# -*- coding: UTF-8 -*-
"""
Tk 输出泵与渲染期输入门禁的本地诊断日志。

仅用于追查偶发的"画面停在完整一屏、点按钮只回显数字、回车无效"的静默卡死，
不随修复一起提交上游。日志尾部可直接回答一个关键问题：上膛标记之后，
究竟是谁又往输出队列里画了东西（PUT 行带调用链）。

日志文件：仓库根目录 tk_gate_debug.log，写满 MAX_BYTES 后转存为 tk_gate_debug.log.1
并重新开始，磁盘占用恒定在两个文件以内。

不使用标准库 logging：实测其单条开销约 32us，而输出队列每渲染一屏要走数百条消息，
会明显拖慢渲染；这里直接写行缓冲文件，单条开销约 2us。
"""
import os
import sys
import time

LOG_PATH = os.path.join(os.getcwd(), "tk_gate_debug.log")
""" 日志文件路径 """

MAX_BYTES = 4 * 1024 * 1024
""" 单个日志文件的体积上限，字节；跨界的最后一条记录允许超出，连同一份转存的旧日志，总占用约为其两倍 """

_fp = None
""" 当前打开的日志文件对象，None 表示尚未打开或已放弃记录 """

_written = 0
""" 当前日志文件已写入的字节数，自行累计以避免每条都做一次 tell() 系统调用 """

_disabled = False
""" 打开失败（如目录只读）后置真，此后静默跳过全部记录 """


def _open():
    """
    打开日志文件。

    参数：无
    返回值类型：无
    功能描述：以追加方式行缓冲打开日志文件，使每条记录立即落盘——静默卡死时玩家多半
              是直接关窗口退出（close_window 走 os._exit，不会冲刷用户态缓冲区），
              带缓冲会丢掉最有价值的日志尾巴。打开失败则永久停用记录。
    """
    global _fp, _written, _disabled
    try:
        _fp = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        _written = _fp.tell()
    except Exception:
        _fp = None
        _disabled = True


def _rotate():
    """
    转存写满的日志并重新开始。

    参数：无
    返回值类型：无
    功能描述：把当前日志改名为 .1（覆盖上一份），随后重新打开一个空文件。
    """
    global _fp, _written
    try:
        _fp.close()
    except Exception:
        pass
    try:
        os.replace(LOG_PATH, LOG_PATH + ".1")
    except Exception:
        pass
    _fp = None
    _written = 0
    _open()


def log(message: str):
    """
    追加一条诊断日志。

    参数：
    message (str) -- 日志正文

    返回值类型：无
    功能描述：写入带时间戳的一行，并在超过体积上限时滚动；
              任何异常都被吞掉，诊断日志绝不能影响游戏本身。
    """
    global _written
    if _disabled:
        return
    try:
        if _fp is None:
            _open()
            if _fp is None:
                return
        now = time.time()
        line = "%s.%03d %s\n" % (time.strftime("%H:%M:%S", time.localtime(now)), int(now % 1 * 1000), message)
        _fp.write(line)
        _written += len(line)
        if _written >= MAX_BYTES:
            _rotate()
    except Exception:
        pass


def caller_chain(skip: int = 2, depth: int = 4) -> str:
    """
    取当前调用链的简短文本。

    参数：
    skip (int) -- 跳过的栈帧数，默认跳过本函数与其直接调用者
    depth (int) -- 最多回溯的栈帧数

    返回值类型：str
    功能描述：用 sys._getframe 逐层取 "文件名:行号:函数名"，不读取源码行，
              开销远低于 traceback.extract_stack，可在每条队列消息上调用。
    """
    parts = []
    try:
        frame = sys._getframe(skip)
    except ValueError:
        return "?"
    while frame is not None and len(parts) < depth:
        code = frame.f_code
        parts.append("%s:%d:%s" % (os.path.basename(code.co_filename), frame.f_lineno, code.co_name))
        frame = frame.f_back
    return " < ".join(parts)
