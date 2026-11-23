# -*- coding: UTF-8 -*-
"""
测试复原内核状态之外的进程状态
==============================
全局设置（save_load.settings、normal_config.system_setting 与 normal_config.ai_setting）、
界面临时状态（Script.UI.Moudle.view）与未结算玩家输入（Script.Modules.tk_ui.orders._unsettled）
不在 GameState 中，由 fresh 复原到初始状态。
本模块顶部不导入游戏模块，以免收集慢速层测试时提前载入游戏。
"""

import contextlib
import importlib
import os
import tempfile

SETTINGS_DIR = tempfile.mkdtemp(prefix="erark-settings-")
""" 测试进程放 settings.json 的临时目录，fresh 把全局设置文件的路径换到这里 """


def fresh() -> None:
    """
    将全局设置（系统设置与文本生成 AI 设置）、界面临时状态与未结算玩家输入复原到初始状态。
    函数将 settings.json 路径指向 SETTINGS_DIR 并删除该文件，同时清空 settings 模块的装入与收下状态。
    随后函数把 normal_config.system_setting 与 normal_config.ai_setting 换成空对象，
    重新载入 view 并清空 orders._unsettled。
    下一次 core.reset_state 时，settings 的输出钩子以默认值为底重新装好全局设置。
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Config import normal_config
    from Script.Core import game_type
    from Script.Modules.save_load import settings
    from Script.Modules.tk_ui import orders
    from Script.UI.Moudle import view

    settings.path = os.path.join(SETTINGS_DIR, "settings.json")
    with contextlib.suppress(FileNotFoundError):
        os.remove(settings.path)
    settings._live = None
    settings._saved = None
    settings._has_preferences = False
    settings._has_ai = False
    settings._pending_ai = None
    normal_config.system_setting = game_type.System_Setting()
    normal_config.ai_setting = game_type.Ai_Setting()
    importlib.reload(view)
    orders._unsettled.clear()
