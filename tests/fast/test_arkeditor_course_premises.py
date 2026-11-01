# -*- coding: UTF-8 -*-
"""
测试：ArkEditor 打开带课程类前提的口上文件
==========================================
课程类前提指属性为 Course、CourseType、CourseShowOff、Growth 的综合数值前提。
测试把 tools/ArkEditor 复制到临时目录，再把 COURSE_TALK_FILES 里的每个口上文件复制进临时数据目录。
每个文件在子进程里由 arkeditor_file_load_driver.py 从菜单打开，并逐行点选左侧条目。
打开时不能抛异常，载入的条目数与左侧列表行数都要等于文件里不同 cid 的个数。
Course 与 CourseShowOff 前提的显示文字要含中文名加 data/csv/Ability.csv 里的能力名。
CourseType 与 Growth 前提的显示文字要含中文名、竖线与编号。
文件里出现的课程类属性要与 COURSE_TALK_FILES 所列的相同。
PySide6.QtWidgets 无法导入时跳过。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from tests.fast import test_arkeditor_file_load as file_load
from tests.fast.base import FastTestCase
from tests.world import ROOT

COURSE_TALK_FILES = (
    (
        os.path.join("data", "talk", "work", "teach", "teach_music.csv"),
        ("Course", "CourseType"),
    ),
    (
        os.path.join(
            "data",
            "talk",
            "system",
            "second_show_off_study",
            "show_off_music.csv",
        ),
        ("CourseShowOff",),
    ),
    (
        os.path.join("data", "talk", "daily", "check_report_card.csv"),
        ("Growth",),
    ),
)
""" 每项依次为口上文件在仓库里的相对路径、该文件里应出现的课程类前提属性名 """
ATTRIBUTE_TEXTS = {
    "Course": ("当前课程科目", True),
    "CourseType": ("当前课型", False),
    "CourseShowOff": ("待炫耀的已升级科目", True),
    "Growth": ("养成数值", False),
}
""" 课程类前提属性名到前提列表里的中文名、编号是否为能力 id """
COURSE_PREMISE = re.compile(
    r"CVP_A\d_(Course|CourseType|CourseShowOff|Growth)\|(\d+)_"
)
""" 从课程类前提 id 的开头取出属性名与编号 """


class ArkEditorCoursePremiseTest(FastTestCase):
  """编辑器打开带课程类前提的口上文件后的载入结果与前提显示文字"""

  def setUp(self) -> None:
    """
    PySide6.QtWidgets 无法导入时跳过，否则在临时目录里准备编辑器副本与空的数据目录
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
    # 编辑器打开和保存文件时，把备份写进自身目录上两级的「备份」文件夹，
    # 副本放在临时目录里，备份就不会写进仓库
    self.editor_dir = os.path.join(self.tmp, "tools", "ArkEditor")
    shutil.copytree(os.path.join(ROOT, "tools", "ArkEditor"), self.editor_dir)
    self.data_dir = os.path.join(self.tmp, "data")
    os.makedirs(self.data_dir)

  def open_talk_file(self, name: str) -> dict[str, Any]:
    """
    在子进程里由驱动脚本从菜单打开数据目录里的口上文件并逐行点选条目，子进程退出码不为 0 时测试失败
    Keyword arguments:
    name -- str，数据目录里的口上文件名
    Return arguments:
    dict[str, Any] -- 驱动脚本最后一行输出里的观察结果
    """
    done = subprocess.run(
        [
            sys.executable,
            file_load.DRIVER,
            self.editor_dir,
            self.data_dir,
            "talk_premise_texts",
            name,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    self.assertEqual(done.returncode, 0, done.stderr)
    result: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return result

  def test_course_premise_texts(self) -> None:
    """逐个打开 COURSE_TALK_FILES 的口上文件：不抛异常，载入全部条目，课程类前提显示中文名加能力名或编号"""
    ability_names = file_load.game_table_names("Ability")
    for path, attributes in COURSE_TALK_FILES:
      with self.subTest(path=path):
        name = os.path.basename(path)
        shutil.copy(os.path.join(ROOT, path), os.path.join(self.data_dir, name))
        result = self.open_talk_file(name)
        self.assertEqual(result["errors"], [])
        cids = file_load.talk_file_cids(os.path.join(ROOT, path))
        self.assertEqual(result["entries"], len(cids))
        self.assertEqual(result["list_rows"], len(cids))
        seen = set()
        for premise, text in result["premise_texts"].items():
          match = COURSE_PREMISE.match(premise)
          if match is None:
            continue
          attribute, premise_id = match.groups()
          seen.add(attribute)
          label, is_ability = ATTRIBUTE_TEXTS[attribute]
          if is_ability:
            self.assertIn(label + ability_names[premise_id], text)
          else:
            self.assertIn(label + "|" + premise_id, text)
        self.assertEqual(seen, set(attributes))
