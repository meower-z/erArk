# -*- coding: UTF-8 -*-
"""
测试复原游戏缓存之外的进程状态
==============================
全局设置（save_load.settings 与 normal_config.system_setting）与界面临时状态（Script.UI.Moudle.view）不在游戏缓存里，
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
    全局设置回到还没装过的样子：settings.json 换到 SETTINGS_DIR 下并删掉，settings 模块记下的设置清空，
    normal_config 上换成空的设置对象；界面临时状态回到模块载入时的初值。
    下一次 core.reset_state 时，settings 的输出钩子以默认值为底重新装好全局设置
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
    normal_config.system_setting = game_type.System_Setting()
    importlib.reload(view)
