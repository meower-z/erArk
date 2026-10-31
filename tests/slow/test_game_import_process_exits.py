# -*- coding: UTF-8 -*-
"""
导入游戏逻辑模块的进程自行退出
==============================
测试开始前，setUp 增量构建 data/ 下的生成物。子进程载入游戏配置时读取这些生成物。
子进程随后导入 Script.Design.update、Script.StateMachine.default 和 Script.Settle。
这些导入会连带导入指令处理模块 handle_instruct。子进程最后打印 handle_instruct 是否已导入。
子进程的脚本中没有 os._exit 调用。测试要求子进程在 CHILD_TIME_LIMIT（120）秒内以退出码 0 退出。
测试还要求子进程的输出含“导入完成 True”。
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
子进程执行的 Python 代码。代码新建游戏缓存后载入游戏配置。
代码随后导入 Script.Design.update、Script.StateMachine.default 和 Script.Settle。
最后一行打印“导入完成”和 handle_instruct 模块是否在 sys.modules 中。代码中没有 os._exit 调用。
"""
CHILD_TIME_LIMIT = 120
""" 等待子进程退出的时限，单位为秒。超过时限时子进程被杀掉，测试判为失败。 """


class GameImportProcessExitsTest(SlowTestCase):
  """检查导入游戏逻辑模块的子进程在脚本结束后于 CHILD_TIME_LIMIT 秒内以退出码 0 退出"""

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
