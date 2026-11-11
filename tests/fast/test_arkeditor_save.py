# -*- coding: UTF-8 -*-
"""
测试：ArkEditor 的保存按钮、菜单保存项与 Ctrl+S 各写一次文件
==========================================
测试把 tools/ArkEditor 复制到临时目录，
在临时数据目录里写入有两条口上的口上文件与有两条事件的事件文件。
每个测试在子进程里运行 arkeditor_save_driver.py。
驱动脚本从菜单打开文件，在第一条的文本末尾加上 MARK，再依次做三个保存操作。
每个保存操作要只写一次文件，不能抛异常。
操作后文件与当天备份的文字都要等于改过第一条后的文字。
PySide6.QtWidgets 无法导入时跳过。
"""

import copy
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

DRIVER = os.path.join(ROOT, "tests", "fast", "arkeditor_save_driver.py")
""" 在子进程里离屏驱动编辑器的脚本 """
MARK = "XYZ"
""" 驱动脚本加在第一条文本末尾的文字，要与 arkeditor_save_driver.MARK 相同 """
SAVES = ("button", "menu", "ctrl_s")
"""
驱动脚本结果里的保存操作名：button 是保存按钮，menu 是菜单保存项，
ctrl_s 是 Ctrl+S
"""


class ArkEditorSaveTest(FastTestCase):
    """编辑器三个保存操作的写入次数与写出的文件、备份"""

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
        # 编辑器把备份写进自身目录上两级的「备份」文件夹，
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
        dict[str, Any] -- 驱动脚本最后一行输出解析出的观察结果
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

    def check_saves(self, kind: str, saved_text: str) -> None:
        """
        运行驱动脚本，对 SAVES 里的每个操作检查槽函数不抛异常、只写一次文件，
        并检查操作后文件与备份的文字都是 saved_text
        Keyword arguments:
        kind -- str，talk 或 event
        saved_text -- str，改过第一条后应写出的文字
        Return arguments:
        None -- 无
        """
        result = self.drive(kind)
        for name in SAVES:
            with self.subTest(save=name):
                self.assertEqual(result["step_errors"][name], [])
                self.assertEqual(
                    result["saves"][name],
                    {"writes": 1, "file": saved_text, "backup": saved_text},
                )

    def test_talk_saves(self) -> None:
        """口上文件的三个保存操作各写一次，文件与备份是第一条加上 MARK 后的口上"""
        self.check_saves(
            "talk",
            file_load.TALK_CSV.replace("第一条口上", "第一条口上" + MARK),
        )

    def test_event_saves(self) -> None:
        """事件文件的三个保存操作各写一次，文件与备份是第一条加上 MARK 后的事件"""
        events = copy.deepcopy(file_load.EVENTS)
        events["event-1"]["text"] = "第一条事件" + MARK
        self.check_saves("event", json.dumps(events, ensure_ascii=False))
