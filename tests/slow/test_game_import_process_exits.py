# -*- coding: UTF-8 -*-
"""
导入游戏逻辑模块的进程自行退出
==============================
在新进程里载入游戏配置，导入游戏主循环、状态机与结算模块（导入链含指令处理模块），
脚本随后正常结束，不调用 os._exit：进程须在时限内以退出码 0 自行退出。
"""

import contextlib
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
""" 子进程执行的代码：载入配置、导入模块后正常结束 """
CHILD_TIME_LIMIT = 120
""" 子进程从启动到退出的时限，秒 """


class GameImportProcessExitsTest(SlowTestCase):
  """导入游戏逻辑模块的脚本正常结束后，进程在时限内以退出码 0 退出"""

  def setUp(self) -> None:
    """
    不启动游戏，只增量构建 data/ 下的生成物：子进程载入配置时读入它们
    Keyword arguments:
    无
    Return arguments:
    无
    """
    os.chdir(ROOT)
    with contextlib.redirect_stdout(io.StringIO()):
      import auto_build_config  # noqa: F401

  def test_process_exits_after_script_ends(self) -> None:
    """子进程导入了指令处理模块，脚本结束后在时限内以退出码 0 退出"""
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
