# -*- coding: UTF-8 -*-
"""
buildata.py 生成的 ArkEditor 前提表与结算表不受常量文件开头的模块 docstring 影响
==============================================================================
把 constant_promise.py 与 constant_effect.py 各复制进临时目录两份：
一份原样，一份在开头加上模块 docstring 及 pyink 要求的两个空行；
在两份目录里分别运行 buildata 的 constand_promise_2_csv 与 constand_effect_2_csv，
比较写出的 Premise.csv 与 Effect.csv。
"""

import contextlib
import importlib
import io
import os
import tempfile
from unittest import mock

from Script.Config import game_config
from tests.fast.base import FastTestCase
from tests.world import ROOT

DOCSTRINGS = {
    "单行": '"""常量定义"""\n',
    "多行": '"""\n常量定义\n========\n每个常量后面一行是「分类 描述」。\n"""\n',
}
""" 加在常量文件开头的模块 docstring：写法名: docstring 文本 """
TABLES = (
    (
        "constand_promise_2_csv",
        "constant_promise.py",
        "Premise.csv",
    ),
    (
        "constand_effect_2_csv",
        "constant_effect.py",
        "Effect.csv",
    ),
)
""" (buildata 的函数名, Script/Core 下读的常量文件, tools/ArkEditor/csv 下写的表) """


def run_table(buildata, table: tuple, root: str, text: str) -> str:
  """
  在临时目录里摆出常量文件，在那里运行 buildata 的生成函数，读回写出的表
  Keyword arguments:
  buildata -- 已导入的 buildata 模块
  table -- TABLES 里的一项：(生成函数名, 常量文件名, 表的文件名)
  root -- 临时目录，作为运行时的当前目录
  text -- 常量文件的内容
  Return arguments:
  str -- 写出的表的全文
  """
  function_name, constant_name, output_name = table
  core_dir = os.path.join(root, "Script", "Core")
  csv_dir = os.path.join(root, "tools", "ArkEditor", "csv")
  os.makedirs(core_dir)
  os.makedirs(csv_dir)
  with open(
      os.path.join(core_dir, constant_name), "w", encoding="utf-8", newline=""
  ) as f:
    f.write(text)
  os.chdir(root)
  with contextlib.redirect_stdout(io.StringIO()):
    getattr(buildata, function_name)()
  with open(os.path.join(csv_dir, output_name), "r", encoding="utf-8") as f:
    return f.read()


class BuildataTablesIgnoreModuleDocstringTest(FastTestCase):
  """常量文件开头有没有模块 docstring，buildata 生成的前提表与结算表都相同"""

  def test_tables_equal_with_and_without_docstring(self) -> None:
    """两张表、两种 docstring 写法，加 docstring 前后生成的表全文相同"""
    # buildata 在模块顶层调 game_config.init()，导入时换成空函数
    with mock.patch.object(game_config, "init"):
      buildata = importlib.import_module("buildata")
    self.addCleanup(os.chdir, os.getcwd())
    for table in TABLES:
      with open(
          os.path.join(ROOT, "Script", "Core", table[1]),
          "r",
          encoding="utf-8",
          newline="",
      ) as f:
        plain_text = f.read()
      # 文件开头的 BOM 留在 docstring 之前
      bom = "\ufeff" if plain_text.startswith("\ufeff") else ""
      body = plain_text[len(bom) :]
      for style, docstring in DOCSTRINGS.items():
        with self.subTest(table=table[0], docstring=style):
          with tempfile.TemporaryDirectory() as tmp:
            plain_table = run_table(
                buildata, table, os.path.join(tmp, "plain"), plain_text
            )
            documented_table = run_table(
                buildata,
                table,
                os.path.join(tmp, "documented"),
                bom + docstring + "\n\n" + body,
            )
            os.chdir(ROOT)
          self.assertGreater(len(plain_table.splitlines()), 1)
          self.assertEqual(documented_table, plain_table)
