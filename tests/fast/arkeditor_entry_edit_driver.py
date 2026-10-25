"""
ArkEditor 的离屏驱动脚本，场景为新前提组、官方事件编辑之后的主窗口列表、新增与复制条目
================================================================================
test_arkeditor_file_load.py 在子进程里运行本脚本。
用法：python arkeditor_entry_edit_driver.py <编辑器目录> <数据目录> <场景> <场景参数>
数据目录里除了 arkeditor_file_load_driver.py 用到的文件，还要有事件文件 event_cve.json
与官方事件目录 official_event。脚本最后在标准输出打印一行 JSON，即 driver.result。
driver.result 记有各步之后的观察结果、弹出的菜单与窗口和槽函数抛出的异常。
场景：
  premise_group      参数为 add 或 restart。两种参数都记下启动时读入的前提组
                     与两个前提组文件的文字。参数为 add 时，脚本先打开 event1.json
                     并点选第一条事件，再按「将当前的所有前提设为新前提组」。
  official_selector  参数为 <effect|premise>:<copy|delete|double|drag>。
                     脚本开 event_cve.json 并点选它的事件，在官方事件编辑页按
                     综合结算或综合前提，建一个口上用flag的结算或前提。之后脚本对
                     主窗口的结算列表或前提列表的第二行右键复制、右键删除、双击
                     或拖到第一行。
  add_copy           参数为 <event|talk>:<add|copy>:<button|menu>。脚本开
                     event1.json 或 talk.csv 并点选第一条，用按钮或左侧条目列表的
                     右键菜单新增或复制条目，再按保存。
"""

import importlib
import json
import os
import sys
from typing import Any

from arkeditor_effect_menu_driver import EditorDriver, list_texts
from arkeditor_file_load_driver import (
    PREMISE_GROUP_FILES,
    FileLoadDriver,
    file_text_or_none,
)


class EntryEditDriver(FileLoadDriver):
  """
  FileLoadDriver 的子类。选目录的对话框返回 dir_path。左侧条目列表的右键菜单不弹出。给了 cv_choice
  时按它填综合型基础数值结算与前提窗口。它还能读取条目数据。
  """

  def __init__(self, editor_dir: str) -> None:
    """
    在编辑器目录里载入编辑器，不进入它的事件循环
    Keyword arguments:
    editor_dir -- str，编辑器目录（tools/ArkEditor 的副本）
    """
    super().__init__(editor_dir)
    self.dir_path = ""
    self.qt_widgets.QFileDialog.getExistingDirectory = staticmethod(
        lambda *args, **kwargs: self.dir_path
    )
    # ui.data_list 里的 QMenu 换成 pick_menu，因为在类上替换 QMenu.exec 对 PySide6 不起作用
    setattr(importlib.import_module("ui.data_list"), "QMenu", self.pick_menu)

  def pick_menu(self, *args: Any) -> Any:
    """
    建一个 QMenu，它的 exec 不弹出菜单。exec 记下菜单各项与是否可选。之后 exec 触发文字为 action_text 的可选项，
    与用户点选这一项相同。
    Keyword arguments:
    args -- Any，QMenu 的构造参数
    Return arguments:
    QMenu -- 换掉了 exec 的菜单
    """
    menu = self.qt_widgets.QMenu(*args)

    def fake_exec(*_: Any) -> Any:
      """
      代替菜单的 exec。它记下菜单各项与是否可选。有文字为 action_text 的可选项时，它触发这一项。
      Keyword arguments:
      _ -- Any，exec 的参数（弹出位置），不用
      Return arguments:
      QAction | None -- 触发的项，没有这一项时为 None
      """
      action = self.fake_menu_exec(menu)
      if action is not None:
        action.trigger()
      return action

    menu.exec = fake_exec
    return menu

  def fake_dialog_exec(self, dialog: Any) -> int:
    """
    代替窗口的弹出。给了 cv_choice 时调用 EditorDriver.fake_dialog_exec。
    EditorDriver.fake_dialog_exec 在综合型基础数值结算或前提窗口里按 cv_choice 选属性、填判定值，再点确定。没给
    cv_choice 时调用 FileLoadDriver.fake_dialog_exec。
    Keyword arguments:
    dialog -- QDialog，要弹出的窗口
    Return arguments:
    int -- 0，同关闭窗口
    """
    if self.cv_choice is not None:
      return EditorDriver.fake_dialog_exec(self, dialog)
    return super().fake_dialog_exec(dialog)

  def entries(self) -> dict[str, dict[str, Any]]:
    """
    取当前文件的各条目
    Keyword arguments:
    无
    Return arguments:
    dict[str, dict[str, Any]] -- 条目 id 到这一条的 text、comment、premise 与 effect。text
    是文本。comment 是注释，口上没有注释属性，所以为 None。premise 是前提 id 列表。effect 是结算 id 列表，
    条目没有结算属性时为空列表。
    """
    if self.cache_control.now_edit_type_flag == 1:
      data = self.cache_control.now_event_data
    else:
      data = self.cache_control.now_talk_data
    return {
        str(k): {
            "text": v.text,
            "comment": getattr(v, "comment", None),
            "premise": list(v.premise),
            "effect": list(getattr(v, "effect", {})),
        }
        for k, v in data.items()
    }

  def selected_entry_panels(self) -> dict[str, Any]:
    """
    按数据算出选中条目在面板上应有的文字
    Keyword arguments:
    无
    Return arguments:
    dict[str, Any] -- premise_list 是前提文字的列表。effect_list 是结算文字的列表。text 是文本框的文字。
    entries 里的 comment 不为 None 时，还有注释框的文字 comment。
    """
    entry = self.entries()[str(self.cache_control.now_select_id)]
    panels = {
        "premise_list": [
            self.cache_control.premise_data[p] for p in entry["premise"]
        ],
        "effect_list": [
            self.cache_control.effect_data[e] for e in entry["effect"]
        ],
        "text": entry["text"].replace("\\n", "\n"),
    }
    if entry["comment"] is not None:
      panels["comment"] = entry["comment"].replace("\\n", "\n")
    return panels


def premise_group(driver: EntryEditDriver, data_dir: str, stage: str) -> None:
  """
  两个阶段都先记下编辑器启动时读入的前提组，最后记下两个前提组文件的文字。add 阶段在其间打开 event1.json 并点选第一条事件。然后 add
  阶段按「将当前的所有前提设为新前提组」，并记下按过之后的前提组。restart 阶段不做别的操作，测试用它核对重开编辑器后读入的前提组。
  Keyword arguments:
  driver -- EntryEditDriver，编辑器驱动
  data_dir -- str，数据目录
  stage -- str，add 或 restart
  Return arguments:
  无
  """
  groups = driver.cache_control.premise_group_data
  driver.result["groups_at_start"] = {k: list(v) for k, v in groups.items()}
  if stage == "add":
    driver.open_event_file(os.path.join(data_dir, "event1.json"))
    driver.select_row(0)
    driver.step(
        "add_group",
        lambda: driver.press_premise_button("将当前的所有前提设为新前提组"),
    )
    driver.result["groups_after_add"] = {k: list(v) for k, v in groups.items()}
  driver.result["premise_group_files"] = {
      name: file_text_or_none(name) for name in PREMISE_GROUP_FILES
  }


def official_selector(
    driver: EntryEditDriver, data_dir: str, variant: str
) -> None:
  """
  开 event_cve.json 并点选它的事件，再从菜单选官方事件目录 official_event，打开官方事件编辑页。在这一页按综合结算或综合前提，
  在弹出的窗口里选口上用flag并填判定值 5。之后对主窗口的结算列表或前提列表的第二行右键复制、右键删除、双击或拖到第一行。
  Keyword arguments:
  driver -- EntryEditDriver，编辑器驱动
  data_dir -- str，数据目录
  variant -- str，<effect|premise>:<copy|delete|double|drag>。前半选主窗口的列表：effect
  为结算列表，premise 为前提列表。后半选操作：copy 为右键复制，delete 为右键删除，double 为双击，drag 为拖到第一行。
  Return arguments:
  无
  """
  which, act = variant.split(":")
  driver.open_event_file(os.path.join(data_dir, "event_cve.json"))
  driver.select_row(0)
  driver.dir_path = os.path.join(data_dir, "official_event")
  driver.step(
      "open_official",
      driver.editor.menu_bar.select_official_event_dir_action.trigger,
  )
  edit_class = importlib.import_module(
      "ui.official_event_edit"
  ).OfficialEventEditWidget
  edit = driver.editor.main_window.findChildren(edit_class)[0]
  label = "综合结算" if which == "effect" else "综合前提"
  for button in edit.findChildren(driver.qt_widgets.QPushButton):
    if button.text() == label:
      driver.cv_choice = ("口上用flag", "5")
      driver.step("selector", button.click)
      driver.cv_choice = None
      break
  if which == "effect":
    item_list = driver.editor.item_effect_list.item_list
    texts = set(driver.cache_control.effect_data.values())
  else:
    item_list = driver.editor.item_premise_list.item_list
    texts = set(driver.cache_control.premise_data.values())
  driver.result["after_selector"] = list_texts(item_list)
  driver.result["after_selector_known"] = [
      text in texts for text in list_texts(item_list)
  ]
  if act == "double":
    driver.step(
        act, lambda: item_list.itemDoubleClicked.emit(item_list.item(1))
    )
  elif act == "drag":
    root = driver.qt_core.QModelIndex()
    driver.step(act, lambda: item_list.model().moveRow(root, 1, root, 0))
  else:
    driver.action_text = {"copy": "复制", "delete": "删除"}[act]
    rect = item_list.visualRect(item_list.model().index(1, 0))
    driver.step(
        act, lambda: item_list.customContextMenuRequested.emit(rect.center())
    )
  driver.result["after_action"] = list_texts(item_list)
  driver.result["entry"] = driver.entries()["event-c"]
  driver.result["copied"] = {
      "effect": driver.cache_control.now_copied_effect,
      "premise": driver.cache_control.now_copied_premise,
  }


def add_copy(driver: EntryEditDriver, data_dir: str, variant: str) -> None:
  """
  开 event1.json 或 talk.csv 并点选第一条。再用按钮或左侧条目列表的右键菜单新增或复制条目，并记下面板与条目数据。最后按保存，
  记下保存后的条目数据与文件的文字。
  Keyword arguments:
  driver -- EntryEditDriver，编辑器驱动
  data_dir -- str，数据目录
  variant -- str，<event|talk>:<add|copy>:<button|menu>。三段依次选文件类型、新增或复制、按钮或右键菜单。
  Return arguments:
  无
  """
  kind, act, entry_point = variant.split(":")
  if kind == "event":
    path = os.path.join(data_dir, "event1.json")
    driver.open_event_file(path)
  else:
    path = os.path.join(data_dir, "talk.csv")
    driver.open_talk_file(path)
  driver.select_row(0)
  driver.result["selected"] = driver.observe()
  data_list = driver.editor.data_list
  if entry_point == "button":
    button = data_list.new_text_button
    if act == "copy":
      button = data_list.copy_text_button
    driver.step("act", button.click)
  else:
    name = {"event": "事件", "talk": "口上"}[kind]
    driver.action_text = {"add": "新增", "copy": "复制"}[act] + name
    list_widget = data_list.list_widget
    position = list_widget.visualItemRect(list_widget.item(0)).center()
    driver.step("act", lambda: data_list.right_button_menu(position))
  driver.result["after_act"] = driver.observe()
  driver.result["expected_panels"] = driver.selected_entry_panels()
  driver.result["entries_after_act"] = driver.entries()
  driver.step("save", driver.editor.item_text_edit.save_button.click)
  driver.result["entries_after_save"] = driver.entries()
  driver.result["saved"] = file_text_or_none(path)


SCENARIOS = {
    "premise_group": premise_group,
    "official_selector": official_selector,
    "add_copy": add_copy,
}
""" 场景名到场景函数 """


if __name__ == "__main__":
  DRIVER = EntryEditDriver(sys.argv[1])
  SCENARIOS[sys.argv[3]](DRIVER, sys.argv[2], sys.argv[4])
  print(json.dumps(DRIVER.result, ensure_ascii=False))
  sys.stdout.flush()
  # 编辑器在导入时就建好了 QApplication，因此用 os._exit 直接结束进程
  os._exit(0)
