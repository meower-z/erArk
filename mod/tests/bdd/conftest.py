#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BDD 端到端测试的 pytest 夹具

以真实 game.py 子进程（web_draw=1）为被测系统；整个测试会话共享一个游戏进程，
按序执行场景。需要 .venv 中安装 pytest、requests、python-socketio[client]。
"""

import os
import sys
import threading

import pytest

# 仓库根目录（mod/tests/bdd/ 向上三级）
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from mod.tests.bdd.web_game_driver import WebGameDriver  # noqa: E402

_PYTEST_EXIT_STATUS = 1
"""最近一次 pytest 会话退出码；缺失 sessionfinish 时保守按失败处理。"""


def pytest_sessionfinish(session, exitstatus):
    """参数：pytest会话与退出码；返回：None；用途：在强制终止非守护线程前保留真实测试结果。"""
    global _PYTEST_EXIT_STATUS

    _PYTEST_EXIT_STATUS = int(exitstatus)


def pytest_unconfigure(config):
    """
    卸载钩子：在全部报告输出与会话夹具销毁之后强制退出解释器

    参数:
    config: pytest 配置对象

    返回值类型：无
    功能描述：近真实引导会 import Script.System.Instruct_System.handle_instruct，
    其在模块加载时启动了一个无退出条件的非守护线程 init_instruct_handle_thread
    （见 handle_instruct.py:24-36），会阻止解释器自然退出。pytest_unconfigure 在
    终端汇总/失败回溯打印完毕、会话级夹具销毁之后调用，因此此处 os._exit 不会吞掉
    任何输出。仅当该线程存在时才硬退出，避免影响不触发近真实引导的纯 Web 驱动运行。
    """
    for thread in threading.enumerate():
        if "init_instruct_handle_thread" in thread.name:
            os.sys.stdout.flush()
            os.sys.stderr.flush()
            os._exit(_PYTEST_EXIT_STATUS)


@pytest.fixture(scope="session")
def game_driver():
    """
    会话级游戏进程夹具

    返回值类型：WebGameDriver
    功能描述：启动真实游戏进程并建立驱动连接；会话结束时停止进程。
    启动失败时输出启动日志尾部便于定位。
    """
    driver = WebGameDriver(REPO_ROOT, python_exe=sys.executable)
    try:
        driver.start()
    except Exception:
        print("\n".join(driver.stdout_lines[-40:]))
        driver.stop()
        raise
    yield driver
    driver.stop()


@pytest.fixture(scope="session")
def main_scene(game_driver):
    """
    会话级主场景夹具：开新档（debug 模式）直至进入主场景

    返回值类型：dict，主场景 new_ui_container 的 game_state
    """
    return game_driver.new_game(player_name="Doctor", enable_debug=True)
