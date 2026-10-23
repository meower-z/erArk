# -*- coding: UTF-8 -*-
"""
生长养成系统脚本的整份跳过
==========================
脚本调 skip() 打印原因并以 SKIP_EXIT 结束进程；
tests/slow/test_education_suite.py 见到这个退出码时报告跳过。
本模块只用标准库，导入它不启动游戏。
"""

import os
from typing import NoReturn

SKIP_EXIT = 77
""" 整份脚本跳过时的退出码 """


def skip(reason: str) -> NoReturn:
  """
  打印跳过的原因，以 SKIP_EXIT 结束进程
  Keyword arguments:
  reason -- 跳过的原因
  Return arguments:
  无（进程在这里结束）
  """
  print(f"SKIPPED: {reason}", flush=True)
  os._exit(SKIP_EXIT)
