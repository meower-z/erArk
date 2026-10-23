# -*- coding: UTF-8 -*-
"""游戏根目录路径的确定（打包与源码运行两种环境），并将其加入模块搜索路径"""

import os
import sys

if getattr(sys, "frozen", False):
  # frozen
  dir_ = os.path.dirname(sys.executable)
  game_path = os.path.dirname(dir_)
else:
  # unfrozen
  dir_ = os.path.dirname(os.path.realpath(__file__))
  game_path = os.path.dirname(os.path.dirname(dir_))
sys.path.append(game_path)

platform = None
