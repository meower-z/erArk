# -*- coding: UTF-8 -*-
"""
target.csv 校验脚本的全量检查
============================
在新进程里不带 --fast 运行 tools/lint_target_csv.py：R5/R6 要载入游戏配置并导入游戏模块。
脚本打印结果后须在时限内自行结束，仓库里的 target.csv 与 effect.csv 全部规则通过。
"""

import contextlib
import io
import os
import subprocess
import sys

from tests.slow.base import SlowTestCase
from tests.world import ROOT

TOOL = os.path.join(ROOT, "tools", "lint_target_csv.py")
""" 校验脚本的路径 """
TOOL_TIME_LIMIT = 120
""" 脚本从启动到退出的时限，秒 """


class LintTargetCsvFullCheckTest(SlowTestCase):
  """不带 --fast 运行校验脚本：在时限内退出，全部规则通过"""

  def setUp(self) -> None:
    """
    不启动游戏，只增量构建 data/ 下的生成物：脚本在自己的进程里读入它们
    Keyword arguments:
    无
    Return arguments:
    无
    """
    os.chdir(ROOT)
    with contextlib.redirect_stdout(io.StringIO()):
      import auto_build_config  # noqa: F401

  def test_full_check_exits_and_passes(self) -> None:
    """脚本在时限内以退出码 0 结束，输出全部规则通过"""
    result = subprocess.run(
        [sys.executable, "-u", TOOL],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        timeout=TOOL_TIME_LIMIT,
        check=False,
    )
    self.assertEqual(result.returncode, 0, result.stdout)
    self.assertIn("全部规则通过", result.stdout)
