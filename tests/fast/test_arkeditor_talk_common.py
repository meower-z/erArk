# -*- coding: UTF-8 -*-
"""
测试：ArkEditor 从口上菜单打开通用口上组件文件
==========================================
通用口上组件文件是 data/talk_common 下的 CSV。它的表头用 type_id 列代替口上文件的 behavior_id 列。
测试把 tools/ArkEditor 复制到临时目录。
临时数据目录里放口上文件 talk.csv，以及从仓库的 COMMON_FILE 复制来的 common.csv。
共 2 个子测试：一个先打开 talk.csv 并点选第一条，另一个不开文件。
每个子测试在子进程里运行 arkeditor_talk_common_driver.py。
驱动脚本从「口上 → 读取口上文件」打开 common.csv，再按保存按钮。
打开这一步不能抛异常，并要恰好弹出一个警告框。警告框的文字里要有 common.csv。
打开后的当前文件、左侧列表行数、各条目的前提与 observe() 记下的面板状态都要与打开前相同。
保存这一步不能抛异常。保存后两个文件的文字要与打开前相同。
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

DRIVER = os.path.join(ROOT, "tests", "fast", "arkeditor_talk_common_driver.py")
""" 驱动脚本 arkeditor_talk_common_driver.py 的路径 """
COMMON_FILE = os.path.join(
    "data", "talk_common", "action_A", "daily", "eat_A.csv"
)
""" 仓库里的一个通用口上组件文件，路径相对仓库根目录。测试把它复制成数据目录里的 common.csv """


class ArkEditorTalkCommonTest(FastTestCase):
    """从口上菜单打开通用口上组件文件时的警告框与编辑器状态，以及之后按保存时两个文件的文字"""

    def setUp(self) -> None:
        """
        PySide6.QtWidgets 无法导入时跳过。能导入时在临时目录里准备编辑器副本与空的数据目录
        Keyword arguments:
        无
        Return arguments:
        None -- 无
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
                "PySide6.QtWidgets 无法导入："
                + probe.stderr.strip().splitlines()[-1]
            )
        self.tmp = tempfile.mkdtemp(prefix="arkeditor_test_")
        self.addCleanup(shutil.rmtree, self.tmp)
        # 编辑器打开或保存口上文件时，把它备份到编辑器目录上两级的「备份」文件夹。
        # 副本放在临时目录下时，备份也落在临时目录里，不进仓库。
        self.editor_dir = os.path.join(self.tmp, "tools", "ArkEditor")
        shutil.copytree(
            os.path.join(ROOT, "tools", "ArkEditor"), self.editor_dir
        )
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(self.data_dir)

    def write_files(self) -> None:
        """
        在数据目录里写入 talk.csv，并把 COMMON_FILE 复制成 common.csv。
        每个子测试开始时调用，让各子测试从同样的两个文件开始
        Keyword arguments:
        无
        Return arguments:
        None -- 无
        """
        with open(
            os.path.join(self.data_dir, "talk.csv"), "w", encoding="utf-8"
        ) as talk_file:
            talk_file.write(file_load.TALK_CSV)
        shutil.copyfile(
            os.path.join(ROOT, COMMON_FILE),
            os.path.join(self.data_dir, "common.csv"),
        )

    def drive(self, prior: str) -> dict[str, Any]:
        """
        在子进程里运行驱动脚本，子进程退出码不为 0 时测试失败
        Keyword arguments:
        prior -- str，之前打开的文件，talk 或 none
        Return arguments:
        dict[str, Any] -- 驱动脚本最后一行输出的 JSON 解析成的字典
        """
        done = subprocess.run(
            [sys.executable, DRIVER, self.editor_dir, self.data_dir, prior],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        result: dict[str, Any] = json.loads(
            done.stdout.strip().splitlines()[-1]
        )
        return result

    def test_open_talk_common(self) -> None:
        """
        各子测试从口上菜单打开 common.csv 再按保存，检查警告框、编辑器状态与两个文件的文字
        Keyword arguments:
        无
        Return arguments:
        None -- 无
        """
        for prior in ("talk", "none"):
            with self.subTest(prior=prior):
                self.write_files()
                result = self.drive(prior)
                self.assertEqual(result["step_errors"]["open_common"], [])
                self.assertEqual(len(result["warnings"]), 1)
                self.assertIn("common.csv", result["warnings"][0][1])
                self.assertEqual(result["after"], result["before"])
                self.assertEqual(result["step_errors"]["save"], [])
                self.assertEqual(result["files_after"], result["files_before"])
