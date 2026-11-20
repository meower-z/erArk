# -*- coding: UTF-8 -*-
"""
erArk 的测试
fast 是不启动游戏的快速层，用 tests.world.MinimalWorld。
导入本包时设置 normal_config.DEFAULTS_ONLY_ENV 指定的环境变量。
这个变量让 init_normal_config 只读 config.ini。
本进程起的子进程继承这个变量。
"""

import os

# 让测试读到的配置与玩过游戏后留下的 config.local.ini 无关
os.environ["ERARK_CONFIG_DEFAULTS_ONLY"] = "1"
