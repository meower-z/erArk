# -*- coding: UTF-8 -*-
"""
tools/lint_target_csv.py 与行尾无关
==================================
把仓库里的 target.csv 与 effect.csv 复制到临时目录，分别存成 LF 与 CRLF 两份，
在临时目录里以 --fast 运行检查脚本：两种行尾的输出与退出码相同；
再各埋一处重复 cid 与一处悬空的 effect target_id，两种行尾都要报出来。
"""

import os
import subprocess
import sys
import tempfile

from tests.fast.base import FastTestCase
from tests.world import ROOT

TARGET_DIR = os.path.join("data", "target", "default")
""" 两个 CSV 相对仓库根目录（也是相对检查脚本工作目录）的位置 """
SCRIPT = os.path.join(ROOT, "tools", "lint_target_csv.py")
""" 被测的检查脚本 """


def read_lf(name: str) -> str:
  """
  读入仓库里的一个目标 CSV，行尾统一成 LF
  Keyword arguments:
  name -- 文件名
  Return arguments:
  str -- 文件内容
  """
  with open(
      os.path.join(ROOT, TARGET_DIR, name), encoding="utf-8", newline=""
  ) as f:
    return f.read().replace("\r\n", "\n")


def plant_errors(target: str, effect: str) -> tuple[str, str]:
  """
  在 LF 文本里埋两处错误：target.csv 末尾重复一遍最后一个数据行（cid 重复），
  effect.csv 末尾加一行引用不存在的 target_id
  Keyword arguments:
  target -- target.csv 的内容
  effect -- effect.csv 的内容
  Return arguments:
  str -- 埋错后的 target.csv
  str -- 埋错后的 effect.csv
  """
  lines = [line for line in target.split("\n") if line.strip()]
  known = {
      int(line.split(",", 1)[0])
      for line in lines
      if line.split(",", 1)[0].isdigit()
  }
  target = target.rstrip("\n") + "\n" + lines[-1]
  effect = effect.rstrip("\n") + "\n0,%d,0" % (max(known) + 1)
  return target, effect


def run_lint(target: str, effect: str, line_end: str) -> tuple[int, str]:
  """
  把两个 CSV 以指定行尾写进临时目录，在那里以 --fast 运行检查脚本
  Keyword arguments:
  target -- target.csv 的 LF 内容
  effect -- effect.csv 的 LF 内容
  line_end -- 写入时使用的行尾
  Return arguments:
  int -- 退出码
  str -- 标准输出
  """
  with tempfile.TemporaryDirectory() as root:
    os.makedirs(os.path.join(root, TARGET_DIR))
    for name, text in (("target.csv", target), ("effect.csv", effect)):
      with open(
          os.path.join(root, TARGET_DIR, name),
          "w",
          encoding="utf-8",
          newline="",
      ) as f:
        f.write(text.replace("\n", line_end))
    result = subprocess.run(
        [sys.executable, SCRIPT, "--fast"],
        cwd=root,
        capture_output=True,
        check=False,
    )
  return result.returncode, result.stdout.decode("utf-8")


class LintTargetCsvLineEndsTest(FastTestCase):
  """lint_target_csv.py 对 LF 与 CRLF 的同一份数据给出相同结果，埋下的错误两种行尾都报"""

  def test_same_result_on_both_line_ends(self) -> None:
    """
    仓库数据存成 LF 与 CRLF，检查脚本的输出与退出码相同
    Keyword arguments:
    无
    Return arguments:
    无
    """
    target, effect = read_lf("target.csv"), read_lf("effect.csv")
    self.assertEqual(
        run_lint(target, effect, "\n"), run_lint(target, effect, "\r\n")
    )

  def test_planted_errors_found_on_both_line_ends(self) -> None:
    """
    埋下重复 cid 与悬空 target_id 后，两种行尾都以退出码 1 报出这两条规则，且输出相同
    Keyword arguments:
    无
    Return arguments:
    无
    """
    target, effect = plant_errors(read_lf("target.csv"), read_lf("effect.csv"))
    lf_result = run_lint(target, effect, "\n")
    crlf_result = run_lint(target, effect, "\r\n")
    for code, output in (lf_result, crlf_result):
      self.assertEqual(code, 1, output)
      self.assertIn("R1 cid重复", output)
      self.assertIn("R7 effect.csv引用了不存在的target", output)
    self.assertEqual(lf_result, crlf_result)
