# -*- coding: UTF-8 -*-
"""
拦下绕开 limited_run.py 的危险游戏进程
=======================================
由 venv 里的 game_runner_guard.pth 在每个 Python 进程启动时导入（安装见 install_guard.sh）。
进程第一次导入下面三个模块之一时，若没有 limited_run.py 设的环境变量 USE_GAME_RUNNER=1，就打印说明并以退出码 3 结束：
    Script.Core.era_image   -- 导入即建图片索引，Tk 显示过的图片都留在内存里直到进程结束
    Script.Core.web_server  -- 可启动 Web 游戏的服务器：其 start_server() 在 5000 起的端口上提供服务
    Script.Core.game_init   -- 启动 Tk 游戏，启动时不到 2 GB，显示的图片越多占用越大
导入时连带导入这三个模块之一的模块同样被拦下，
例如在模块顶部导入 web_server 的 Script.Design.talk 与 Script.Design.settle_behavior，
所以读档、跑行为结算的脚本也要经 limited_run.py 运行；不连带导入它们的模块照常导入。
"""

import os
import sys
import importlib.abc

GUARDED = frozenset(
    {"Script.Core.era_image", "Script.Core.web_server", "Script.Core.game_init"}
)
""" 需要经 limited_run.py 才能导入的模块 """
MESSAGE = (
    "Blocked: importing {name} without limited_run.py. This module {why}, so "
    "the process must run under "
    "limited_run.py's memory cap and time limit (the Tk game runs through "
    "tk_game.py, which uses it):\n"
    "  <venv>/bin/python tools/verify/limited_run.py -- <venv>/bin/python -u <script>\n"
    "from the erArk checkout root.\n"
)
WHY = {
    "Script.Core.era_image": (
        "keeps every image that Tk shows in memory until the process ends"
    ),
    "Script.Core.web_server": (
        "can start the web game's server (its start_server() serves on a port "
        "from 5000 up)"
    ),
    "Script.Core.game_init": (
        "starts the Tk game (under 2 GB at start, more as it shows images)"
    ),
}
""" 各模块被拦下的原因 """


class GameRunnerGuard(importlib.abc.MetaPathFinder):
    """在导入受保护模块前检查 USE_GAME_RUNNER；本身不负责查找模块"""

    def find_spec(self, fullname, path, target=None):
        """
        受保护模块且没有启动器标记时结束进程，否则交给后面的查找器
        参数：fullname (str) 模块全名；path、target 由导入系统传入，不使用
        返回：None，总是让导入系统继续用其他查找器
        """
        if fullname in GUARDED and os.environ.get("USE_GAME_RUNNER") != "1":
            sys.stderr.write(MESSAGE.format(name=fullname, why=WHY[fullname]))
            sys.stderr.flush()
            os._exit(3)
        return None


if not any(isinstance(finder, GameRunnerGuard) for finder in sys.meta_path):
    sys.meta_path.insert(0, GameRunnerGuard())
