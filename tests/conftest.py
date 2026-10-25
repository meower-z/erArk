# -*- coding: UTF-8 -*-
"""
pytest 的公共设置：固定字符串哈希的随机化
==========================================
PYTHONHASHSEED 只能在解释器启动前设定，它决定字符串集合的遍历顺序。
没有设成 tests.world.SEED 时，这里用同样的命令行重新执行一次 pytest，让每次运行的哈希顺序相同。
"""

import os
import subprocess
import sys
from typing import TYPE_CHECKING

from tests.world import SEED

if TYPE_CHECKING:
  import pytest


def pytest_configure(config: "pytest.Config") -> None:
  """
  PYTHONHASHSEED 不是固定值时，带上它重新执行同一条命令，并以子进程的退出码结束
  Keyword arguments:
  config -- pytest 配置对象
  Return arguments:
  无
  功能描述:
      先暂停 pytest 的输出捕获，新进程才写到真正的终端；Windows 没有真正的 exec，就起子进程并等它结束。
  """
  if os.environ.get("PYTHONHASHSEED") == str(SEED):
    return
  capture = config.pluginmanager.getplugin("capturemanager")
  if capture is not None:
    capture.suspend_global_capture(in_=True)
  sys.stdout.flush()
  sys.stderr.flush()
  env = dict(os.environ, PYTHONHASHSEED=str(SEED))
  argv = [sys.executable, *sys.orig_argv[1:]]
  if os.name == "nt":
    os._exit(subprocess.call(argv, env=env))
  os.execve(sys.executable, argv, env)
