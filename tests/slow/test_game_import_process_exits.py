# -*- coding: UTF-8 -*-
"""
导入游戏逻辑模块的进程自行退出
==============================
Python 进程退出前要等所有非守护线程结束。一个模块若在导入时启动不会结束的非守护线程，就会让进程在代码跑完后无法自行退出。
本测试在子进程里导入游戏逻辑模块，导入链中含指令处理模块 handle_instruct。子进程的代码里没有 os._exit 调用。
测试要求子进程在 CHILD_TIME_LIMIT 秒内以退出码 0 退出。测试还要求输出含“导入完成 True”，这表明 handle_instruct 确实被导入了。
setUp 先增量构建 data/ 下的生成物。子进程载入游戏配置时读取这些生成物。
"""

import contextlib
import importlib
import io
import os
import subprocess
import sys

from tests.slow.base import SlowTestCase
from tests.world import ROOT

CHILD_CODE = """
import sys
from Script.Core import game_type, cache_control
from Script.Config import normal_config

cache_control.cache = game_type.Cache()
normal_config.init_normal_config()
from Script.Config import game_config

game_config.init()
import Script.Design.update
import Script.StateMachine.default
import Script.Settle

print("导入完成", "Script.System.Instruct_System.handle_instruct" in sys.modules)
"""
"""
子进程执行的代码。代码新建游戏缓存，载入游戏配置，再导入 Script.Design.update、Script.StateMachine.default 和 Script.Settle。
最后一行打印“导入完成”和 handle_instruct 是否在 sys.modules 中。代码里没有 os._exit 调用。代码跑完后，进程靠解释器的正常退出流程结束。
"""
CHILD_TIME_LIMIT = 120
""" 等待子进程退出的时限，单位为秒。子进程超时后被杀掉，测试判为失败。 """


class GameImportProcessExitsTest(SlowTestCase):
  """导入游戏逻辑模块的子进程在代码跑完后，须于 CHILD_TIME_LIMIT 秒内以退出码 0 自行退出"""

  def setUp(self) -> None:
    """
    导入 auto_build_config，增量构建 data/ 下的生成物。子进程载入游戏配置时读取这些生成物。本方法不启动游戏。
    Keyword arguments:
    无
    Return arguments:
    无
    """
    os.chdir(ROOT)
    with contextlib.redirect_stdout(io.StringIO()):
      importlib.import_module("auto_build_config")

  def test_process_exits_after_script_ends(self) -> None:
    """
    用子进程运行 CHILD_CODE。子进程须在 CHILD_TIME_LIMIT 秒内以退出码 0 退出。子进程的输出须含“导入完成 True”。
    """
    try:
      result = subprocess.run(
          [sys.executable, "-u", "-c", CHILD_CODE],
          cwd=ROOT,
          stdout=subprocess.PIPE,
          stderr=subprocess.STDOUT,
          encoding="utf-8",
          errors="replace",
          timeout=CHILD_TIME_LIMIT,
          check=False,
      )
    except subprocess.TimeoutExpired as error:
      output = error.output
      if isinstance(output, bytes):
        output = output.decode("utf-8", "replace")
      self.fail(f"脚本结束后进程 {CHILD_TIME_LIMIT} 秒内未退出，输出：{output}")
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertIn("导入完成 True", result.stdout)
