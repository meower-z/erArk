# -*- coding: UTF-8 -*-
"""
ArkEditor 的离屏测试：载入文件后的面板、没有选中条目时的前提列表、新建属性文件、前提组的保存、官方事件编辑之后的主窗口列表、新增与复制条目后的面板
==========================================================================
setUp 把 tools/ArkEditor 复制到临时目录。setUp 在数据目录里写三个事件文件和口上文件 talk.csv。属性文件
chara.csv 复制自 example 下的模板。官方事件目录 official_event 复制自 data/official_event。
各测试在子进程里运行 arkeditor_file_load_driver.py 或 arkeditor_entry_edit_driver.py，
由它们离屏驱动编辑器。各测试都检查驱动没有记下槽函数抛出的异常。PySide6.QtWidgets 无法导入时跳过。
打开 GAME_TABLE_TALK_FILES 所列口上文件的副本并逐行点选条目时不抛异常。
引用该常量所列角色扮演或能力 id 的前提，
在前提列表里显示的文字含有该 id 在 data/csv 下对应表里的名字。
"""

import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from tests.fast.base import FastTestCase
from tests.world import ROOT

DRIVER = os.path.join(ROOT, "tests", "fast", "arkeditor_file_load_driver.py")
""" 离屏驱动编辑器的脚本 """
ENTRY_DRIVER = os.path.join(
    ROOT, "tests", "fast", "arkeditor_entry_edit_driver.py"
)
""" 第二个驱动脚本，运行 premise_group、official_selector 与 add_copy 三个场景 """
CHARA_TEMPLATE = "0999_模板人物属性文件.csv"
""" 新建属性文件读入的模板文件名 """
EVENTS = {
    "event-1": {
        "uid": "event-1",
        "adv_id": "0",
        "behavior_id": "share_blankly",
        "start": 0,
        "type": 0,
        "text": "第一条事件",
        "comment": "第一条事件的注释",
        "premise": {"sys_0": 1, "sys_4": 1},
        "effect": {"0": 1},
    },
    "event-2": {
        "uid": "event-2",
        "adv_id": "0",
        "behavior_id": "share_blankly",
        "start": 0,
        "type": 0,
        "text": "第二条事件",
        "premise": {"sys_1": 1},
        "effect": {"9999": 1},
    },
}
""" 第一个事件文件：两条事件各带前提 """
OTHER_EVENTS = {
    "event-3": {
        "uid": "event-3",
        "adv_id": "0",
        "behavior_id": "share_blankly",
        "start": 0,
        "type": 0,
        "text": "另一个文件的事件",
        "premise": {},
        "effect": {"9999": 1},
    },
}
""" 第二个事件文件：一条事件 """
CVE_EVENTS = {
    "event-c": {
        "uid": "event-c",
        "adv_id": "0",
        "behavior_id": "share_blankly",
        "start": 0,
        "type": 0,
        "text": "带综合数值结算与前提的事件",
        "premise": {"sys_0": 1, "CVP_A1_Flag|0_G_5": 1},
        "effect": {"0": 1, "CVE_A1_Flag|0_G_5": 1},
    },
}
""" 第三个事件文件 event_cve.json：事件 event-c 的第二个前提与第二个结算是口上用flag的综合型基础数值前提与结算 """
PREMISE_GROUP_FILES = (
    "PremiseGroup.csv",
    os.path.join("csv", "PremiseGroup.csv"),
)
""" 编辑器目录下的两个前提组文件：根目录下的 PremiseGroup.csv 与编辑器启动时读入的 csv/PremiseGroup.csv """
TALK_CSV = (
    "cid,behavior_id,adv_id,premise,context\n"
    "口上id,触发口上的行为id,口上限定的剧情npcid,前提id,口上内容\n"
    "str,str,int,str,str\n"
    "0,0,0,0,1\n"
    "口上配置数据,,,,\n"
    "1,share_blankly,0,high_1&sys_0,第一条口上\n"
    "2,share_blankly,0,high_1&sys_1,第二条口上\n"
)
""" 口上文件：两条口上各带前提 """
GAME_TABLE_TALK_FILES = (
    (
        os.path.join("data", "talk", "arts", "roleplay.csv"),
        "Roleplay",
        "Roleplay",
        "角色扮演",
        ("25", "26", "27", "109", "110"),
    ),
    (
        os.path.join(
            "data", "talk", "sex", "sex_class", "sex_class_main_77.csv"
        ),
        "Ability",
        "A",
        "能力",
        ("77",),
    ),
)
""" 每组依次为仓库里的口上文件路径、data/csv 表名、前提 id 里的属性名、前提列表里名字前的文字、要核对的 id """


def game_table_names(table: str) -> dict[str, str]:
  """
  取 data/csv 下一张表第 6 行起各行的 cid 与 name。
  Keyword arguments:
  table -- str，data/csv 下的表文件名，不带 .csv
  Return arguments:
  dict[str, str] -- 各行的 cid 到 name
  """
  path = os.path.join(ROOT, "data", "csv", table + ".csv")
  with open(path, encoding="utf-8", newline="") as table_file:
    rows = list(csv.DictReader(table_file))[4:]
  return {row["cid"]: row["name"] for row in rows}


def talk_file_cids(path: str) -> set[str]:
  """
  取口上文件第 6 条记录起、至少一格不为空的各条记录首列的 cid。
  Keyword arguments:
  path -- str，口上文件路径
  Return arguments:
  set[str] -- cid 集合
  """
  with open(path, encoding="utf-8", newline="") as talk_file:
    records = list(csv.reader(talk_file))[5:]
  return {record[0] for record in records if any(record)}


class ArkEditorFileLoadTest(FastTestCase):
  """编辑器载入文件后的面板、前提列表与新建属性文件"""

  def setUp(self) -> None:
    """
    PySide6 无法导入时跳过；准备编辑器副本与数据文件
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
    self.data_dir = os.path.join(self.tmp, "data")
    os.makedirs(self.data_dir)
    for name, events in (
        ("event1.json", EVENTS),
        ("event2.json", OTHER_EVENTS),
        ("event_cve.json", CVE_EVENTS),
    ):
      with open(
          os.path.join(self.data_dir, name), "w", encoding="utf-8"
      ) as event_file:
        json.dump(events, event_file, ensure_ascii=False)
    with open(
        os.path.join(self.data_dir, "talk.csv"), "w", encoding="utf-8"
    ) as talk_file:
      talk_file.write(TALK_CSV)
    shutil.copy(
        os.path.join(ROOT, "example", CHARA_TEMPLATE),
        os.path.join(self.data_dir, "chara.csv"),
    )
    shutil.copytree(
        os.path.join(ROOT, "data", "official_event"),
        os.path.join(self.data_dir, "official_event"),
    )
    # 各前提组文件原有的文字，文件不存在时为 None
    self.premise_group_files: dict[str, str | None] = {}
    for name in PREMISE_GROUP_FILES:
      path = os.path.join(self.editor_dir, name)
      self.premise_group_files[name] = None
      if os.path.exists(path):
        with open(path, encoding="utf-8") as group_file:
          self.premise_group_files[name] = group_file.read()

  def drive(
      self, scenario: str, variant: str = "", driver: str = DRIVER
  ) -> dict[str, Any]:
    """
    在子进程里运行驱动脚本的一个场景。子进程的返回码不为 0 时测试失败。
    Keyword arguments:
    scenario -- str，场景名
    variant -- str，场景参数，默认为空字符串
    driver -- str，驱动脚本的路径，默认为 DRIVER
    Return arguments:
    dict[str, Any] -- 驱动脚本输出的最后一行 JSON
    """
    done = subprocess.run(
        [
            sys.executable,
            driver,
            self.editor_dir,
            self.data_dir,
            scenario,
            variant,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    self.assertEqual(done.returncode, 0, done.stderr)
    result: dict[str, Any] = json.loads(done.stdout.strip().splitlines()[-1])
    return result

  def write_failed_open_files(self) -> None:
    """
    占位说明：在数据目录里重写三种可读文件与三种读不了的文件
    Keyword arguments:
    无
    Return arguments:
    None -- 无
    """
    with open(
        os.path.join(ROOT, "example", CHARA_TEMPLATE), encoding="utf-8"
    ) as template_file:
      chara = template_file.read()
    for name, text in (
        ("talk.csv", TALK_CSV),
        (
            "bad_talk.csv",
            TALK_CSV + "3,share_blankly,第三条,high_1,第三条口上\n",
        ),
        ("event1.json", json.dumps(EVENTS, ensure_ascii=False)),
        (
            "bad_event.json",
            json.dumps(
                dict(EVENTS, **{"event-x": {"uid": "event-x", "premise": {}}}),
                ensure_ascii=False,
            ),
        ),
        ("chara.csv", chara),
        ("bad_chara.csv", chara.replace("Sex,int,1,", "Sex,int,女,", 1)),
    ):
      with open(
          os.path.join(self.data_dir, name), "w", encoding="utf-8"
      ) as data_file:
        data_file.write(text)

  def test_save_after_failed_open(self) -> None:
    """占位说明：打开读不了的文件后，编辑器仍停在之前的文件上，按保存不改读不了的文件"""
    for kind in ("talk", "event", "chara"):
      for prior in ("same", "none"):
        with self.subTest(kind=kind, prior=prior):
          self.write_failed_open_files()
          result = self.drive("save_after_failed_open", f"{kind}:{prior}")
          self.assertNotEqual(result["step_errors"]["open_bad"], [])
          self.assertEqual(result["bad_after"], result["bad_before"])
          self.assertEqual(result["after"], result["before"])
          self.assertEqual(result["step_errors"]["save"], [])
          self.assertEqual(result["step_errors"].get("apply", []), [])

  def test_chara_file_after_event_file(self) -> None:
    """先开事件文件、点选事件，再开属性文件：面板里没有事件的内容，前提列表的按钮不改事件、不写前提组文件"""
    result = self.drive("chara_after_event")
    self.assertEqual(result["errors"], [])
    selected = result["event_selected"]
    self.assertEqual(selected["select_id"], "event-1")
    self.assertEqual(len(selected["premise_list"]), 2)
    self.assertEqual(selected["text"], "第一条事件")
    self.assertEqual(result["chara_name"], "样板人物")
    opened = result["chara_opened"]
    self.assertEqual(opened["edit_type"], 2)
    for key in ("select_id", "text", "comment"):
      self.assertEqual(opened[key], "", key)
    self.assertEqual(opened["premise_list"], [])
    self.assertEqual(opened["effect_list"], [])
    self.assertEqual(opened["save_button"], "保存")
    # 整体修改与整体清零按钮本身就把保存按钮标为已修改，只比较面板内容
    after_buttons = dict(result["chara_after_buttons"], save_button="")
    self.assertEqual(after_buttons, dict(opened, save_button=""))
    self.assertEqual(result["event_premises_after"], result["event_premises"])
    self.assertEqual(result["dialogs"], [])
    self.assertEqual(result["premise_group_files"], self.premise_group_files)

  def test_new_entry_after_other_file(self) -> None:
    """开第二个文件后回到编辑模式。文本框与注释框为空。新增条目保存后是默认文本。"""
    for second in ("talk", "event"):
      with self.subTest(second=second):
        result = self.drive("new_entry_after_event", second)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["event_selected"]["text"], "第一条事件")
        self.assertTrue(result["event_selected"]["preview"])
        opened = result["second_opened"]
        self.assertEqual(opened["select_id"], "")
        self.assertEqual(opened["text"], "")
        self.assertEqual(opened["comment"], "")
        self.assertEqual(opened["save_button"], "保存")
        self.assertFalse(opened["preview"])
        saved = result["second_saved"]
        if second == "event":
          events = json.loads(saved)
          self.assertEqual(events["event-3"]["text"], "另一个文件的事件")
          new_events = [v for k, v in events.items() if k != "event-3"]
          self.assertEqual(len(new_events), 1)
          self.assertEqual(new_events[0]["text"], "空事件")
          self.assertEqual(new_events[0]["comment"], "")
        else:
          # 前五行是表头，之后每行一条口上，最后一列是口上内容
          rows = [row.split(",") for row in saved.splitlines()[5:]]
          self.assertEqual([row[0] for row in rows], ["1", "2", "3"])
          self.assertEqual(rows[1][-1], "第二条口上")
          self.assertEqual(rows[2][-1], "空口上")

  def test_premise_list_without_selected_entry(self) -> None:
    """未选条目、或删除了选中的条目时，前提列表的各操作不抛异常、不改数据、不开窗口；选中剩下的条目后右键删除照常删掉前提"""
    for kind, remaining_id, remaining_premises in (
        ("event", "event-2", ["sys_1"]),
        ("talk", "2", ["high_1", "sys_1"]),
    ):
      with self.subTest(kind=kind):
        result = self.drive("premise_list_actions", kind)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["premises_none"], result["premises_opened"])
        self.assertEqual(len(result["selected"]["premise_list"]), 2)
        deleted = result["premises_deleted"]
        self.assertEqual(deleted, {remaining_id: remaining_premises})
        self.assertEqual(result["premises_after_deleted"], deleted)
        self.assertEqual(result["dialogs_after_deleted"], [])
        self.assertEqual(
            result["premise_group_files"], self.premise_group_files
        )
        # 删除了选中的条目后，右键菜单的删除与粘贴不可选
        self.assertEqual(
            result["menus"][:3],
            [
                {
                    "删除": False,
                    "复制": True,
                    "粘贴": False,
                    "加入到快速插入列表": True,
                }
            ]
            * 3,
        )
        remaining = result["remaining_selected"]
        self.assertEqual(remaining["select_id"], remaining_id)
        after = result["remaining_after_delete"]
        self.assertEqual(after["premise_list"], remaining["premise_list"][1:])
        self.assertEqual(
            result["premises_remaining_after_delete"],
            {remaining_id: remaining_premises[1:]},
        )

  def test_new_chara_file(self) -> None:
    """新建属性文件：读入编辑器目录下的模板，改 id 与姓名后应用并保存，另存为新文件，模板不变"""
    for layout in ("source", "package"):
      with self.subTest(layout=layout):
        if layout == "package":
          # 打包后的编辑器目录里放的是 example 下的模板
          shutil.copy(
              os.path.join(ROOT, "example", CHARA_TEMPLATE), self.editor_dir
          )
        new_file = os.path.join(self.editor_dir, "8002_测试新角色.csv")
        if os.path.exists(new_file):
          os.remove(new_file)
        result = self.drive("new_chara", CHARA_TEMPLATE)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["chara_name"], "样板人物")
        self.assertIsNotNone(result["template_before"])
        self.assertEqual(result["template_after"], result["template_before"])
        self.assertIn("AdvNpc,int,8002,", result["new_file"])
        self.assertIn("Name,str,测试新角色,", result["new_file"])

  def test_talk_file_with_game_table_ids(self) -> None:
    """打开 GAME_TABLE_TALK_FILES 的口上文件并点选各条目不抛异常。引用所列 id 的前提文字含 data/csv 里的名字。"""
    for path, table, attribute, label, ids in GAME_TABLE_TALK_FILES:
      with self.subTest(path=path):
        name = os.path.basename(path)
        shutil.copy(os.path.join(ROOT, path), os.path.join(self.data_dir, name))
        result = self.drive("talk_premise_texts", name)
        self.assertEqual(result["errors"], [])
        cids = talk_file_cids(os.path.join(ROOT, path))
        self.assertEqual(result["entries"], len(cids))
        self.assertEqual(result["list_rows"], len(cids))
        names = game_table_names(table)
        for table_id in ids:
          pattern = re.compile(rf"CVP_A\d_{attribute}\|{table_id}_")
          texts = [
              text
              for premise, text in result["premise_texts"].items()
              if pattern.match(premise)
          ]
          self.assertNotEqual(texts, [], table_id)
          for text in texts:
            self.assertIn(label + names[table_id], text)

  def test_premise_group_saved_to_loaded_file(self) -> None:
    """新前提组追加到 csv/PremiseGroup.csv 末尾。根目录下的 PremiseGroup.csv 不变。重开编辑器后读得到新组。"""
    result = self.drive("premise_group", "add", ENTRY_DRIVER)
    self.assertEqual(result["errors"], [])
    start = result["groups_at_start"]
    added = {
        cid: premises
        for cid, premises in result["groups_after_add"].items()
        if cid not in start
    }
    self.assertEqual(list(added.values()), [["sys_0", "sys_4"]])
    cid = list(added)[0]
    loaded_file = PREMISE_GROUP_FILES[1]
    self.assertEqual(
        result["premise_group_files"],
        dict(
            self.premise_group_files,
            **{
                loaded_file: f"{self.premise_group_files[loaded_file]}"
                f"{cid},sys_0&sys_4\n"
            },
        ),
    )
    restart = self.drive("premise_group", "restart", ENTRY_DRIVER)
    self.assertEqual(restart["errors"], [])
    self.assertEqual(restart["groups_at_start"], result["groups_after_add"])

  def test_main_lists_after_official_selector(self) -> None:
    """官方事件编辑建过口上用flag的结算或前提后，主窗口列表每行的文字都在文字表里。右键复制记下这一项。右键删除、双击与拖动改动事件的数据。"""
    for which, other in (("effect", "0"), ("premise", "sys_0")):
      key = {"effect": "CVE_A1_Flag|0_G_5", "premise": "CVP_A1_Flag|0_G_5"}[
          which
      ]
      for act in ("copy", "delete", "double", "drag"):
        with self.subTest(which=which, act=act):
          result = self.drive(
              "official_selector", f"{which}:{act}", ENTRY_DRIVER
          )
          self.assertEqual(result["errors"], [])
          self.assertEqual(len(result["after_selector"]), 2)
          self.assertEqual(result["after_selector_known"], [True, True])
          ids = result["entry"][which]
          shown = result["after_selector"]
          if act == "copy":
            self.assertEqual(result["copied"][which], key)
            self.assertEqual(ids, [other, key])
          elif act == "drag":
            self.assertEqual(ids, [key, other])
            self.assertEqual(result["after_action"], [shown[1], shown[0]])
          else:
            self.assertEqual(ids, [other])
          if act == "delete" or (act == "double" and which == "effect"):
            # 双击前提行删掉前提后会打开前提窗口，由这个窗口重画列表。驱动不运行这个窗口，所以这里不查前提列表。
            self.assertEqual(result["after_action"], [shown[0]])

  def test_panels_after_add_or_copy(self) -> None:
    """新增或复制条目后，面板显示新条目。保存前后条目数据相同。保存的文件里新条目是自己的文本。"""
    for kind in ("event", "talk"):
      for act in ("add", "copy"):
        for entry_point in ("button", "menu"):
          with self.subTest(kind=kind, act=act, entry_point=entry_point):
            result = self.drive(
                "add_copy", f"{kind}:{act}:{entry_point}", ENTRY_DRIVER
            )
            self.assertEqual(result["errors"], [])
            after = result["after_act"]
            self.assertNotEqual(
                after["select_id"], result["selected"]["select_id"]
            )
            for name, value in result["expected_panels"].items():
              self.assertEqual(after[name], value, name)
            self.assertEqual(after["save_button"], "保存*")
            entries = result["entries_after_act"]
            self.assertEqual(result["entries_after_save"], entries)
            new_entry = entries[after["select_id"]]
            if kind == "event":
              saved = json.loads(result["saved"])[after["select_id"]]
              self.assertEqual(saved["text"], new_entry["text"])
              self.assertEqual(saved["comment"], new_entry["comment"])
            else:
              # 新口上在保存的 CSV 的最后一行。这一行的最后一列是口上内容。
              row = result["saved"].splitlines()[-1].split(",")
              self.assertEqual(row[0], after["select_id"])
              self.assertEqual(row[-1], new_entry["text"])
