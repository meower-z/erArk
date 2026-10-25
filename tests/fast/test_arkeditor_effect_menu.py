# -*- coding: UTF-8 -*-
"""
ArkEditor 在事件文件与口上文件之间切换后的前提、结算列表与结算列表的右键菜单，综合指令状态结算窗口，
以及综合型基础数值结算、前提窗口
====================================================================================================
把 tools/ArkEditor 复制到临时目录，写一份两条事件的事件文件与一条口上的口上文件，
在子进程里由 arkeditor_effect_menu_driver.py 离屏驱动编辑器：
先开事件文件再开口上文件时，前提与结算列表为空，右键、新增口上与结算列表的按钮都不抛异常、不改事件数据；
先开口上文件再开事件文件时，右键删除的是当前事件的结算；
从综合指令状态结算窗口加入的结算与保存后重新打开的结算，在结算列表里都显示所选行为的名字；
在这个窗口里不选行为按确定时不抛异常、不改事件的结算；
综合型基础数值结算、前提窗口里属性留在待选择按确定时不改事件的结算与前提；
从综合型基础数值结算窗口加入的结算与保存后重新打开的结算，在结算列表里的文字相同，判定值里的下划线留着。
PySide6 在本机无法导入时跳过。
"""

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from tests.fast.base import FastTestCase
from tests.world import ROOT

DRIVER = os.path.join(ROOT, "tests", "fast", "arkeditor_effect_menu_driver.py")
""" 离屏驱动编辑器的脚本 """
FIRST_EVENT = "event-1"
""" 事件文件里第一条事件的 uid """
SECOND_EVENT = "event-2"
""" 事件文件里第二条事件的 uid """
EVENTS = {
    FIRST_EVENT: {
        "uid": FIRST_EVENT,
        "adv_id": "0",
        "behavior_id": "share_blankly",
        "start": 0,
        "type": 0,
        "text": "第一条事件",
        "premise": {"sys_0": 1},
        "effect": {"0": 1, "1": 1},
    },
    SECOND_EVENT: {
        "uid": SECOND_EVENT,
        "adv_id": "0",
        "behavior_id": "share_blankly",
        "start": 0,
        "type": 0,
        "text": "第二条事件",
        "premise": {},
        "effect": {"9999": 1},
    },
}
""" 事件文件的内容：第一条事件带一个前提、两个结算 """
TALK_CSV = (
    "cid,behavior_id,adv_id,premise,context\n"
    "口上id,触发口上的行为id,口上限定的剧情npcid,前提id,口上内容\n"
    "str,str,int,str,str\n"
    "0,0,0,0,1\n"
    "口上配置数据,,,,\n"
    "1,share_blankly,0,high_1,一条口上\n"
)
""" 口上文件的内容：一条口上 """


def behavior_name(behavior_id: str) -> str:
  """
  从编辑器的行为表里取行为的名字
  Keyword arguments:
  behavior_id -- 行为 id（行为表的 en_name 列）
  Return arguments:
  str -- 行为的名字
  """
  path = os.path.join(ROOT, "tools", "ArkEditor", "csv", "Behavior_Data.csv")
  with open(path, encoding="utf-8") as behavior_file:
    for row in csv.DictReader(behavior_file):
      if row["en_name"] == behavior_id:
        return row["name"]
  raise LookupError(behavior_id)


class ArkEditorEffectMenuTest(FastTestCase):
  """编辑器切换文件后，前提、结算列表与结算列表的右键菜单只作用于当前文件；综合指令状态结算、综合型基础数值结算与前提窗口加入的结算与前提"""

  def setUp(self) -> None:
    """
    PySide6 无法导入时跳过；准备编辑器副本与两个数据文件
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
    # 编辑器把备份写到自己目录的上两级，放在临时目录里
    self.editor_dir = os.path.join(self.tmp, "tools", "ArkEditor")
    shutil.copytree(os.path.join(ROOT, "tools", "ArkEditor"), self.editor_dir)
    self.event_path = os.path.join(self.tmp, "event.json")
    with open(self.event_path, "w", encoding="utf-8") as event_file:
      json.dump(EVENTS, event_file, ensure_ascii=False)
    self.talk_path = os.path.join(self.tmp, "talk.csv")
    with open(self.talk_path, "w", encoding="utf-8") as talk_file:
      talk_file.write(TALK_CSV)

  def drive(self, scenario: str) -> dict[str, Any]:
    """
    在子进程里运行驱动脚本的一个场景
    Keyword arguments:
    scenario -- 场景名
    Return arguments:
    dict[str, Any] -- 驱动脚本打印的观察结果
    """
    done = subprocess.run(
        [
            sys.executable,
            DRIVER,
            self.editor_dir,
            self.event_path,
            self.talk_path,
            scenario,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    self.assertEqual(done.returncode, 0, done.stderr)
    result: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return result

  def test_talk_file_after_event_file(self) -> None:
    """先开事件文件、点选事件，再开口上文件：没有选中条目，前提与结算列表为空，结算列表上的操作不改事件数据"""
    result = self.drive("event_then_talk")
    self.assertEqual(result["errors"], [])
    selected = result["event_selected"]
    self.assertEqual(selected["select_id"], FIRST_EVENT)
    self.assertEqual(len(selected["premise_list"]), 1)
    self.assertEqual(len(selected["effect_list"]), 2)
    event_effects = selected["event_effects"]
    opened = result["talk_opened"]
    self.assertEqual(opened["select_id"], "")
    self.assertEqual(opened["premise_list"], [])
    self.assertEqual(opened["effect_list"], [])
    # 口上没有结算：新增口上后结算列表仍为空，右键不弹菜单，结算按钮不打开结算窗口
    self.assertEqual(result["talk_added"]["select_id"], "2")
    for step in ("talk_deleted", "talk_added_deleted", "talk_buttons"):
      self.assertEqual(result[step]["effect_list"], [], step)
      self.assertEqual(result[step]["event_effects"], event_effects, step)
    self.assertEqual(result["menus"], [])
    self.assertEqual(result["dialogs"], [])

  def test_event_file_after_talk_file(self) -> None:
    """先开口上文件、点选口上，再开事件文件：点选事件后右键删除的是这条事件的结算"""
    result = self.drive("talk_then_event")
    self.assertEqual(result["errors"], [])
    opened = result["event_opened"]
    self.assertEqual(opened["select_id"], "")
    self.assertEqual(opened["premise_list"], [])
    self.assertEqual(opened["effect_list"], [])
    selected = result["event_selected"]
    self.assertEqual(selected["select_id"], FIRST_EVENT)
    first_text = selected["effect_list"][0]
    deleted = result["event_deleted"]
    self.assertEqual(
        result["menus"], [{"删除": True, "复制": True, "粘贴": True}]
    )
    self.assertEqual(deleted["effect_list"], selected["effect_list"][1:])
    self.assertEqual(
        deleted["event_effects"],
        {FIRST_EVENT: {"1": 1}, SECOND_EVENT: {"9999": 1}},
    )
    self.assertNotIn(first_text, deleted["effect_list"])

  def test_cse_added_and_reopened_text(self) -> None:
    """从综合指令状态结算窗口加入的结算与保存后重新打开的结算，在结算列表里都显示所选行为的名字"""
    result = self.drive("cse_add_and_reopen")
    self.assertEqual(result["errors"], [])
    # 驱动脚本依次加入的两个行为 id：带下划线与不带的各一个
    behavior_ids = ("share_blankly", "chat")
    self.assertEqual(
        result["saved_effects"],
        {
            FIRST_EVENT: {"0": 1, "1": 1}
            | {f"CSE_A1_{behavior_id}": 1 for behavior_id in behavior_ids},
            SECOND_EVENT: {"9999": 1},
        },
    )
    texts = [
        f"综合指令状态结算 玩家对自己 进行 {behavior_name(behavior_id)}"
        for behavior_id in behavior_ids
    ]
    for step in ("cse_reopened", "cse_added"):
      self.assertEqual(result[step]["effect_list"][2:], texts, step)

  def test_cse_ok_without_behavior(self) -> None:
    """综合指令状态结算窗口里不选行为按确定时不抛异常、不改结算；之后选了行为再按确定照常加入"""
    result = self.drive("cse_empty_ok")
    self.assertEqual(result["errors"], [])
    self.assertEqual(
        result["cse_empty_ok"]["event_effects"][FIRST_EVENT], {"0": 1, "1": 1}
    )
    self.assertEqual(
        result["cse_picked_ok"]["event_effects"][FIRST_EVENT],
        {"0": 1, "1": 1, "CSE_A1_chat": 1},
    )

  def test_cv_ok_without_attribute(self) -> None:
    """综合型基础数值结算、前提窗口里属性留在待选择按确定时不改结算与前提；之后选了属性再按确定照常加入"""
    result = self.drive("cv_empty_ok")
    self.assertEqual(result["errors"], [])
    empty = result["cv_empty_ok"]
    self.assertEqual(empty["event_effects"][FIRST_EVENT], {"0": 1, "1": 1})
    self.assertEqual(empty["event_premises"][FIRST_EVENT], {"sys_0": 1})
    picked = result["cv_picked_ok"]
    self.assertEqual(
        picked["event_effects"][FIRST_EVENT],
        {"0": 1, "1": 1, "CVE_A1_F_G_0": 1},
    )
    self.assertEqual(
        picked["event_premises"][FIRST_EVENT],
        {"sys_0": 1, "CVP_A1_F_G_0": 1},
    )

  def test_cve_added_and_reopened_text(self) -> None:
    """从综合型基础数值结算窗口加入的结算与保存后重新打开的结算，在结算列表里的文字相同，判定值里的下划线留着"""
    result = self.drive("cve_add_and_reopen")
    self.assertEqual(result["errors"], [])
    self.assertEqual(
        result["saved_effects"][FIRST_EVENT],
        {"0": 1, "1": 1, "CVE_A1_F_G_0": 1, "CVE_A1_Move|0_寻路_Dr_room": 1},
    )
    texts = ["综合数值结算  自己好感增加0", "综合数值结算  自己移动寻路Dr_room"]
    for step in ("cve_added", "cve_reopened"):
      self.assertEqual(result[step]["effect_list"][2:], texts, step)
