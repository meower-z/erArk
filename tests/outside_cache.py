# -*- coding: UTF-8 -*-
"""
测试复原游戏缓存之外的进程状态
==============================
全局设置（save_load.settings、normal_config.system_setting 与 normal_config.ai_setting）
与界面临时状态（Script.UI.Moudle.view）不在游戏缓存里，
MinimalWorld 复原缓存时由 fresh 把它们也复原。本模块顶部不导入游戏模块（慢速层收集测试时不能载入游戏）。
"""

import contextlib
import importlib
import os
import tempfile

SETTINGS_DIR = tempfile.mkdtemp(prefix="erark-settings-")
""" 测试进程放 settings.json 的临时目录，fresh 把全局设置文件的路径换到这里 """


def fresh() -> None:
    """
    把全局设置（系统设置与文本生成 AI 设置）与界面临时状态复原到初始状态。
    函数把 settings.json 路径换到 SETTINGS_DIR 下并删除该文件，清空 settings 模块的装入与收下状态，再把
    normal_config.system_setting 与 normal_config.ai_setting 换成空对象，并重新载入 view。
    下一次 core.reset_state 时，settings 的输出钩子以默认值为底重新装好全局设置。
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Config import normal_config
    from Script.Core import game_type
    from Script.Modules.save_load import settings
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
