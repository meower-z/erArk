# -*- coding: UTF-8 -*-
"""
ArkEditor 前提列表显示每个前提自己的说明
========================================
load_csv.load_config 读入 tools/ArkEditor/csv/Premise.csv。
cache_control.premise_data 为每个前提id保存一条说明。
cache_control.premise_type_data 按分类保存前提id。
前提选择对话框按分类列出前提id，并显示这个id保存的说明。
测试逐行核对 Premise.csv。
每一行的前提id在 premise_data 中的说明须等于该行的说明。
每一行的前提id须只列在该行的分类下。
"""

import contextlib
import csv
import importlib
import os
import sys
from unittest import mock

from tests.fast.base import FastTestCase
from tests.world import ROOT

EDITOR_DIR = os.path.join(ROOT, "tools", "ArkEditor")
""" ArkEditor 目录的路径 """
EDITOR_MODULES = ("load_csv", "cache_control", "game_type")
""" 测试导入编辑器时进入 sys.modules 的顶层模块名，测试结束时移除 """


class ArkEditorPremiseLabelTest(FastTestCase):
    """编辑器载入 Premise.csv 后的前提说明和前提分类的测试"""

    def test_each_row_shows_own_label(self) -> None:
        """
        逐行核对编辑器保存的前提说明和前提分类是否与 Premise.csv 一致
        Keyword arguments:
        无
        Return arguments:
        无
        """
        for name in EDITOR_MODULES:
            self.addCleanup(sys.modules.pop, name, None)
        with mock.patch.object(sys, "path", [EDITOR_DIR, *sys.path]):
            load_csv = importlib.import_module("load_csv")
            cache_control = importlib.import_module("cache_control")
        with contextlib.chdir(EDITOR_DIR):
            load_csv.load_config()
            with open(load_csv.premise_path, encoding="utf-8") as premise_file:
                rows = [
                    row for row in csv.DictReader(premise_file) if row["cid"]
                ]
        for row in rows:
            cid = row["cid"]
            with self.subTest(cid=cid, premise_name=row["premise_name"]):
                self.assertEqual(
                    cache_control.premise_data[cid], row["premise"]
                )
                types = {
                    premise_type
                    for premise_type, cids in cache_control.premise_type_data.items()
                    if cid in cids
                }
                self.assertEqual(types, {row["premise_type"]})
