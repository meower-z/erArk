# -*- coding: UTF-8 -*-
"""
测试：ArkEditor 打开职业或种族一行类型为 str 的属性文件
======================================================
测试把 tools/ArkEditor 复制到临时目录，在临时数据目录里写入 example 下的模板属性文件。
各子测试再写一份副本，把模板里 Profession 或 Race 一行的类型从 int 改成 str。
每个文件由 arkeditor_chara_type_driver.py 在子进程里从菜单打开。
打开每个文件时，槽函数都不能抛出异常。
打开模板后，职业、种族、势力、出身地四个下拉框都要有文字。
打开副本后，这四个下拉框的文字要与打开模板后相同。
PySide6.QtWidgets 无法导入时跳过。
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from tests.fast import test_arkeditor_file_load as file_load
from tests.fast.base import FastTestCase
from tests.world import ROOT

DRIVER = os.path.join(ROOT, "tests", "fast", "arkeditor_chara_type_driver.py")
""" 在子进程里离屏驱动编辑器的脚本 """
STR_ROWS = ("Profession", "Race")
""" 各子测试把类型改成 str 的属性行 """


class ArkEditorCharaStrTypeTest(FastTestCase):
  """检查 ArkEditor 打开职业或种族类型为 str 的属性文件后的下拉框文字"""

  def setUp(self) -> None:
    """
    PySide6.QtWidgets 无法导入时跳过测试。
    能导入时，把编辑器复制到临时目录，并建一个空的数据目录。
    最后读入 example 下模板属性文件的文字。
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    probe = subprocess.run(
        [sys.executable, "-c", "import PySide6.QtWidgets"],
        capture_output=True,
        text=True,
        check=False,
    )
    if probe.returncode:
      self.skipTest(
          "PySide6.QtWidgets 无法导入：" + probe.stderr.strip().splitlines()[-1]
      )
    self.tmp = tempfile.mkdtemp(prefix="arkeditor_test_")
    self.addCleanup(shutil.rmtree, self.tmp)
    self.editor_dir = os.path.join(self.tmp, "tools", "ArkEditor")
    shutil.copytree(os.path.join(ROOT, "tools", "ArkEditor"), self.editor_dir)
    self.data_dir = os.path.join(self.tmp, "data")
    os.makedirs(self.data_dir)
    with open(
        os.path.join(ROOT, "example", file_load.CHARA_TEMPLATE),
        encoding="utf-8",
    ) as template_file:
      self.chara = template_file.read()

  def drive(self, name: str, text: str) -> dict[str, Any]:
    """
    把 text 写进数据目录里名为 name 的属性文件。
    在子进程里运行驱动脚本打开这个文件，子进程退出码不为 0 时测试失败。
    Keyword arguments:
    name -- str，属性文件名
    text -- str，属性文件的文字
    Return arguments:
    dict[str, Any] -- 驱动脚本最后一行输出解析出的 JSON
    """
    path = os.path.join(self.data_dir, name)
    with open(path, "w", encoding="utf-8") as chara_file:
      chara_file.write(text)
    done = subprocess.run(
        [sys.executable, DRIVER, self.editor_dir, path],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    self.assertEqual(done.returncode, 0, done.stderr)
    result: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return result

  def test_str_row_shows_same_page(self) -> None:
    """先打开模板，再在各子测试里打开一份副本，比较槽函数异常与下拉框的文字"""
    control = self.drive("int.csv", self.chara)
    self.assertEqual(control["step_errors"]["open_chara"], [])
    self.assertTrue(all(control["combo_texts"].values()), control)
    for key in STR_ROWS:
      with self.subTest(key=key):
        self.assertIn(f"\n{key},int,", self.chara)
        text = self.chara.replace(f"\n{key},int,", f"\n{key},str,", 1)
        result = self.drive(f"str_{key}.csv", text)
        self.assertEqual(result["step_errors"]["open_chara"], [])
        self.assertEqual(result["combo_texts"], control["combo_texts"])
