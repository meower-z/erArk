# -*- coding: UTF-8 -*-
"""
测试：ArkEditor 打开读不了的文件后按保存
==========================================
测试把 tools/ArkEditor 复制到临时目录，在临时数据目录里写入可读的口上、事件与属性文件，
再各写一份读不了的：口上文件多一条 adv_id 为文字的口上，事件文件多一条没有 effect 的事件，
属性文件的 Sex 为文字。编辑器副本里的属性模板也换成这份读不了的属性文件。
另写一份截短的事件文件 cut_event.json，内容是可读事件文件的文字去掉末尾 20 个字符。
cut_event.json 不是合法的 JSON。
文件类型有 talk、event、cut_event、chara 与 template 五种。
talk、event、cut_event、chara 分别从菜单打开读不了的口上文件、事件文件、cut_event.json 与属性文件。
template 从菜单新建属性文件，读入模板。
每种分先打开一个可读文件（template 与 cut_event 时为事件文件）与不开文件两种，共 10 个子测试。
每个子测试在子进程里由 arkeditor_failed_open_driver.py 打开读不了的文件，再按保存按钮。
属性文件且先开过可读文件时再按应用并保存。
打开读不了的文件要抛异常。打开后的当前文件、左侧列表行数、条目前提、角色姓名与各面板状态
都要与打开前相同。保存与应用并保存不能抛异常。读不了的文件最后的文字要与打开前相同。
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

DRIVER = os.path.join(ROOT, "tests", "fast", "arkeditor_failed_open_driver.py")
""" 离屏驱动编辑器的脚本 """


class ArkEditorFailedOpenTest(FastTestCase):
  """编辑器打开读不了的文件后的状态与按保存后的文件"""

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
    # 编辑器打开口上与事件文件、按保存时，把备份写进自身目录上两级的「备份」文件夹，
    # 副本放在临时目录里，备份就不会写进仓库
    self.editor_dir = os.path.join(self.tmp, "tools", "ArkEditor")
    shutil.copytree(os.path.join(ROOT, "tools", "ArkEditor"), self.editor_dir)
    self.data_dir = os.path.join(self.tmp, "data")
    os.makedirs(self.data_dir)

  def write_files(self) -> None:
    """
    在数据目录里写入可读与读不了的口上、事件、属性文件各一份，再写入截短的事件文件 cut_event.json，
    并把编辑器目录下的模板写成读不了的属性文件。每个子测试开始时调用，各子测试从同样的文件开始
    Keyword arguments:
    无
    Return arguments:
    None -- 无
    """
    with open(
        os.path.join(ROOT, "example", file_load.CHARA_TEMPLATE),
        encoding="utf-8",
    ) as template_file:
      chara = template_file.read()
    bad_chara = chara.replace("Sex,int,1,", "Sex,int,女,", 1)
    bad_event = {"event-x": {"uid": "event-x", "premise": {}}}
    for path, text in (
        (os.path.join(self.data_dir, "talk.csv"), file_load.TALK_CSV),
        (
            os.path.join(self.data_dir, "bad_talk.csv"),
            file_load.TALK_CSV + "3,share_blankly,第三条,high_1,第三条口上\n",
        ),
        (
            os.path.join(self.data_dir, "event1.json"),
            json.dumps(file_load.EVENTS, ensure_ascii=False),
        ),
        (
            os.path.join(self.data_dir, "bad_event.json"),
            json.dumps(dict(file_load.EVENTS, **bad_event), ensure_ascii=False),
        ),
        (
            os.path.join(self.data_dir, "cut_event.json"),
            json.dumps(file_load.EVENTS, ensure_ascii=False)[:-20],
        ),
        (os.path.join(self.data_dir, "chara.csv"), chara),
        (os.path.join(self.data_dir, "bad_chara.csv"), bad_chara),
        (os.path.join(self.editor_dir, file_load.CHARA_TEMPLATE), bad_chara),
    ):
      with open(path, "w", encoding="utf-8") as data_file:
        data_file.write(text)

  def drive(self, variant: str) -> dict[str, Any]:
    """
    在子进程里运行驱动脚本，子进程退出码不为 0 时测试失败
    Keyword arguments:
    variant -- str，<文件类型>:<之前打开的文件>，如 talk:same 或 template:none
    Return arguments:
    dict[str, Any] -- 驱动脚本最后一行输出里的观察结果
    """
    done = subprocess.run(
        [sys.executable, DRIVER, self.editor_dir, self.data_dir, variant],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    self.assertEqual(done.returncode, 0, done.stderr)
    result: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return result

  def test_save_after_failed_open(self) -> None:
    """各子测试：打开读不了的文件时抛异常，编辑器状态不变，按保存后该文件不变"""
    for kind in ("talk", "event", "cut_event", "chara", "template"):
      for prior in ("same", "none"):
        with self.subTest(kind=kind, prior=prior):
          self.write_files()
          result = self.drive(f"{kind}:{prior}")
          self.assertNotEqual(result["step_errors"]["open_bad"], [])
          self.assertEqual(result["bad_after"], result["bad_before"])
          self.assertEqual(result["after"], result["before"])
          self.assertEqual(result["step_errors"]["save"], [])
          self.assertEqual(result["step_errors"].get("apply", []), [])
