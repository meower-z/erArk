# -*- coding: UTF-8 -*-
"""
测试：ArkEditor 打开文件后从菜单新建同类文件
==========================================
测试把 tools/ArkEditor 复制到临时目录，在临时数据目录里写入有两条口上的口上文件与有两条事件的事件文件。
test_new_talk_file 打开口上文件后新建口上文件，test_new_event_file 打开事件文件后新建事件文件。
每个测试在子进程里由 arkeditor_new_file_driver.py 从菜单打开文件并点选第一条，再从同一菜单新建文件。
新建后当前文件要是新文件，左侧列表要没有行，编辑器内存里要没有条目。
新建这一步不能抛异常，打开的文件的文字要不变。
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

DRIVER = os.path.join(ROOT, "tests", "fast", "arkeditor_new_file_driver.py")
""" 离屏驱动编辑器的脚本 """


class ArkEditorNewFileTest(FastTestCase):
    """编辑器打开文件后从菜单新建的同类文件"""

    def setUp(self) -> None:
        """
        PySide6.QtWidgets 无法导入时跳过，否则在临时目录里准备编辑器副本，
        并在数据目录里写入口上文件 talk.csv 与事件文件 event1.json
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
                "PySide6.QtWidgets 无法导入："
                + probe.stderr.strip().splitlines()[-1]
            )
        self.tmp = tempfile.mkdtemp(prefix="arkeditor_test_")
        self.addCleanup(shutil.rmtree, self.tmp)
        # 编辑器打开口上与事件文件时，把备份写进自身目录上两级的「备份」文件夹，
        # 副本放在临时目录里，备份就不会写进仓库
        self.editor_dir = os.path.join(self.tmp, "tools", "ArkEditor")
        shutil.copytree(
            os.path.join(ROOT, "tools", "ArkEditor"), self.editor_dir
        )
        self.data_dir = os.path.join(self.tmp, "data")
        os.makedirs(self.data_dir)
        for name, text in (
            ("talk.csv", file_load.TALK_CSV),
            ("event1.json", json.dumps(file_load.EVENTS, ensure_ascii=False)),
        ):
            with open(
                os.path.join(self.data_dir, name), "w", encoding="utf-8"
            ) as data_file:
                data_file.write(text)

    def drive(self, kind: str) -> dict[str, Any]:
        """
        在子进程里运行驱动脚本，子进程退出码不为 0 时测试失败
        Keyword arguments:
        kind -- str，talk 或 event
        Return arguments:
        dict[str, Any] -- 驱动脚本最后一行输出里的观察结果
        """
        done = subprocess.run(
            [sys.executable, DRIVER, self.editor_dir, self.data_dir, kind],
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

    def check_new_file(self, kind: str, new_name: str) -> None:
        """
        运行驱动脚本，检查新建后当前文件是新文件，列表与条目为空，新建这一步不抛异常，打开的文件不变
        Keyword arguments:
        kind -- str，talk 或 event
        new_name -- str，新建的文件名
        Return arguments:
        None -- 无
        """
        result = self.drive(kind)
        self.assertEqual(result["step_errors"]["new"], [])
        self.assertEqual(
            result["after"],
            {
                "file_path": os.path.join(self.data_dir, new_name),
                "list_rows": 0,
                "entries": {},
            },
        )
        self.assertEqual(result["open_after"], result["open_before"])

    def test_new_talk_file(self) -> None:
        """打开口上文件后新建口上文件，编辑器读入的新文件没有口上"""
        self.check_new_file("talk", "new_talk.csv")

    def test_new_event_file(self) -> None:
        """打开事件文件后新建事件文件，编辑器读入的新文件没有事件"""
        self.check_new_file("event", "new_event.json")
