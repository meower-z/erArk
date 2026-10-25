"""
ArkEditor 载入文件后各面板状态的离屏驱动脚本，由 test_arkeditor_file_load.py 在子进程里运行
=========================================================================================
用法：python arkeditor_file_load_driver.py <编辑器目录> <数据目录> <场景> <场景参数>
数据目录里有事件文件 event1.json、event2.json，口上文件 talk.csv，属性文件 chara.csv。
在编辑器目录里载入编辑器（不进入事件循环），按场景打开文件、点选与删除条目、操作前提列表与属性面板，
文件对话框返回给定路径，右键菜单与窗口不弹出：菜单只记下各项与是否可选并按场景选一项，窗口只记下类名。
最后在标准输出打印一行 JSON：各步之后的观察结果、弹出的菜单与窗口、以及槽函数抛出的异常。
场景：
  chara_after_event      先开事件文件并点选第一条事件，再开属性文件，按前提列表的各按钮
  new_entry_after_event  先开事件文件并点选第一条事件、打开文本预览，再开口上文件或另一个事件文件，新增条目并保存
  premise_list_actions   开事件文件或口上文件，未选条目时按前提列表的各按钮；
                         点选第一条后删除该条目，再右键、拖动、双击前提并按各按钮；最后点选剩下的一条右键删除前提
  new_chara              新建属性文件，改角色 id 与姓名后应用并保存
"""

import importlib
import json
import os
import sys
from typing import Any

from arkeditor_effect_menu_driver import EditorDriver, list_texts

PREMISE_BUTTONS = (
    "整体修改",
    "整体清零",
    "综合型基础数值前提",
    "将当前的所有前提设为新前提组",
    "玩家触发的该指令",
)
""" 前提列表上要按的按钮 """


class FileLoadDriver(EditorDriver):
  """在 EditorDriver 之上加入属性文件、文本框、前提列表与属性面板的操作"""

  def __init__(self, editor_dir: str) -> None:
    """
    载入编辑器，不进入事件循环
    Keyword arguments:
    editor_dir -- 编辑器目录（tools/ArkEditor 的副本）
    """
    super().__init__(editor_dir)
    self.qt_core = importlib.import_module("PySide6.QtCore")

  def fake_dialog_exec(self, dialog: Any) -> int:
    """
    代替窗口的弹出：记下窗口类名；综合数值前提窗口按默认选项点确定
    Keyword arguments:
    dialog -- QDialog
    Return arguments:
    int -- 0，同关闭窗口
    """
    self.result["dialogs"].append(type(dialog).__name__)
    if type(dialog).__name__ == "CVPMenu":
      dialog.ok_button.click()
    return 0

  def observe(self) -> dict[str, Any]:
    """
    取当前的编辑类型、选中条目、前提与结算列表的文字、文本框与事件注释框的文字、保存按钮的文字与是否在预览
    Keyword arguments:
    无
    Return arguments:
    dict[str, Any] -- 观察结果
    """
    text_edit = self.editor.item_text_edit
    return {
        "edit_type": self.cache_control.now_edit_type_flag,
        "select_id": self.cache_control.now_select_id,
        "premise_list": list_texts(self.editor.item_premise_list.item_list),
        "effect_list": list_texts(self.editor.item_effect_list.item_list),
        "text": text_edit.label_text.toPlainText(),
        "comment": text_edit.comment_edit.toPlainText(),
        "save_button": text_edit.save_button.text(),
        "preview": text_edit.preview_button.isChecked(),
    }

  def data_premises(self) -> dict[str, list[str]]:
    """
    取当前文件各条目的前提
    Keyword arguments:
    无
    Return arguments:
    dict[str, list[str]] -- 条目 id 到前提 id 列表
    """
    if self.cache_control.now_edit_type_flag == 1:
      data = self.cache_control.now_event_data
    else:
      data = self.cache_control.now_talk_data
    return {str(k): list(v.premise) for k, v in data.items()}

  def step(self, name: str, action: Any) -> None:
    """
    执行一步操作，记下这一步里槽函数抛出的异常的最后一行
    Keyword arguments:
    name -- 这一步的名字
    action -- 无参数的操作
    Return arguments:
    无
    """
    before = len(self.result["errors"])
    action()
    self.result.setdefault("step_errors", {})[name] = [
        error.strip().splitlines()[-1]
        for error in self.result["errors"][before:]
    ]

  def select_row(self, row: int) -> None:
    """
    在左侧条目列表里点选一行，同时设为当前行
    Keyword arguments:
    row -- 行号
    Return arguments:
    无
    """
    self.editor.data_list.list_widget.setCurrentRow(row)
    self.click_row(row)

  def open_chara_file(self, path: str) -> None:
    """
    从菜单打开属性文件
    Keyword arguments:
    path -- 文件对话框返回的路径
    Return arguments:
    无
    """
    self.path = path
    self.editor.menu_bar.select_chara_file_action.trigger()

  def press_premise_button(self, text: str) -> None:
    """
    按下前提列表上文字为 text 的按钮
    Keyword arguments:
    text -- 按钮文字
    Return arguments:
    无
    """
    for button in self.editor.item_premise_list.findChildren(
        self.qt_widgets.QPushButton
    ):
      if button.text() == text:
        button.click()
        return
    raise LookupError(text)

  def premise_right_click(self, action_text: str) -> None:
    """
    在前提列表第一行的位置右键，并在菜单里选一项
    Keyword arguments:
    action_text -- 要选的菜单项文字
    Return arguments:
    无
    """
    self.action_text = action_text
    premise_list = self.editor.item_premise_list.item_list
    rect = premise_list.visualRect(premise_list.model().index(0, 0))
    premise_list.customContextMenuRequested.emit(rect.center())

  def premise_drag(self) -> None:
    """
    把前提列表第一行移到末尾，同拖动排序
    Keyword arguments:
    无
    Return arguments:
    无
    """
    premise_list = self.editor.item_premise_list.item_list
    root = self.qt_core.QModelIndex()
    premise_list.model().moveRow(root, 0, root, premise_list.count())

  def premise_double_click(self) -> None:
    """
    双击前提列表第一行
    Keyword arguments:
    无
    Return arguments:
    无
    """
    premise_list = self.editor.item_premise_list.item_list
    premise_list.itemDoubleClicked.emit(premise_list.item(0))

  def press_premise_buttons(self, prefix: str) -> None:
    """
    依次按下前提列表的各按钮
    Keyword arguments:
    prefix -- 步骤名的前缀
    Return arguments:
    无
    """
    for text in PREMISE_BUTTONS:
      self.step(prefix + text, lambda t=text: self.press_premise_button(t))


def read_text(path: str) -> str | None:
  """
  读文件的全部文字，文件不存在时为 None
  Keyword arguments:
  path -- 文件路径
  Return arguments:
  str | None -- 文件文字
  """
  if not os.path.exists(path):
    return None
  with open(path, encoding="utf-8") as now_file:
    return now_file.read()


def chara_after_event(driver: FileLoadDriver, data_dir: str, _: str) -> None:
  """
  先开事件文件并点选第一条事件，再开属性文件，按前提列表的各按钮
  Keyword arguments:
  driver -- 编辑器驱动
  data_dir -- 数据目录
  Return arguments:
  无
  """
  driver.open_event_file(os.path.join(data_dir, "event1.json"))
  driver.select_row(0)
  driver.result["event_selected"] = driver.observe()
  driver.step(
      "open_chara",
      lambda: driver.open_chara_file(os.path.join(data_dir, "chara.csv")),
  )
  driver.result["chara_opened"] = driver.observe()
  driver.result["chara_name"] = driver.cache_control.now_chara_data.Name
  driver.result["event_premises"] = driver.data_premises()
  driver.press_premise_buttons("chara:")
  driver.result["chara_after_buttons"] = driver.observe()
  driver.result["event_premises_after"] = driver.data_premises()
  driver.result["premise_group_file"] = read_text("PremiseGroup.csv")


def new_entry_after_event(
    driver: FileLoadDriver, data_dir: str, second: str
) -> None:
  """
  先开事件文件并点选第一条事件、打开文本预览，再开口上文件或另一个事件文件，新增条目并保存
  Keyword arguments:
  driver -- 编辑器驱动
  data_dir -- 数据目录
  second -- 第二个文件：talk 或 event
  Return arguments:
  无
  """
  driver.open_event_file(os.path.join(data_dir, "event1.json"))
  driver.select_row(0)
  driver.editor.item_text_edit.preview_button.click()
  driver.result["event_selected"] = driver.observe()
  if second == "talk":
    second_path = os.path.join(data_dir, "talk.csv")
    driver.open_talk_file(second_path)
  else:
    second_path = os.path.join(data_dir, "event2.json")
    driver.open_event_file(second_path)
  driver.result["second_opened"] = driver.observe()
  driver.step("add_entry", driver.add_entry)
  driver.step("save", driver.editor.item_text_edit.save_button.click)
  driver.result["second_saved"] = read_text(second_path)


def premise_list_actions(
    driver: FileLoadDriver, data_dir: str, kind: str
) -> None:
  """
  开事件文件或口上文件，未选条目时按前提列表的各按钮；点选第一条后删除该条目，
  再右键、拖动、双击前提并按各按钮；最后点选剩下的一条右键删除前提
  Keyword arguments:
  driver -- 编辑器驱动
  data_dir -- 数据目录
  kind -- 文件类型：event 或 talk
  Return arguments:
  无
  """
  if kind == "event":
    driver.open_event_file(os.path.join(data_dir, "event1.json"))
  else:
    driver.open_talk_file(os.path.join(data_dir, "talk.csv"))
  driver.result["premises_opened"] = driver.data_premises()
  driver.press_premise_buttons("none:")
  driver.result["premises_none"] = driver.data_premises()
  driver.select_row(0)
  driver.result["selected"] = driver.observe()
  driver.editor.data_list.delete_text_button.click()
  driver.result["premises_deleted"] = driver.data_premises()
  for action_text in ("复制", "删除", "粘贴"):
    driver.step(
        "deleted:" + action_text,
        lambda a=action_text: driver.premise_right_click(a),
    )
  driver.step("deleted:drag", driver.premise_drag)
  driver.step("deleted:double_click", driver.premise_double_click)
  driver.press_premise_buttons("deleted:")
  driver.result["premises_after_deleted"] = driver.data_premises()
  driver.result["dialogs_after_deleted"] = list(driver.result["dialogs"])
  driver.result["premise_group_file"] = read_text("PremiseGroup.csv")
  driver.select_row(0)
  driver.result["remaining_selected"] = driver.observe()
  driver.step("remaining:删除", lambda: driver.premise_right_click("删除"))
  driver.result["remaining_after_delete"] = driver.observe()
  driver.result["premises_remaining_after_delete"] = driver.data_premises()


def new_chara(driver: FileLoadDriver, _: str, template: str) -> None:
  """
  新建属性文件，改角色 id 与姓名后应用并保存
  Keyword arguments:
  driver -- 编辑器驱动
  template -- 编辑器目录下的模板文件名
  Return arguments:
  无
  """
  driver.result["template_before"] = read_text(template)
  driver.step("new_chara", driver.editor.menu_bar.new_chara_file_action.trigger)
  if driver.result["step_errors"]["new_chara"]:
    return
  driver.result["chara_name"] = driver.cache_control.now_chara_data.Name
  chara_list = driver.editor.chara_list
  chara_list.chara_id_text_edit.setText("8002")
  chara_list.chara_name_text_edit.setText("测试新角色")
  driver.step("apply", chara_list.apply_button.click)
  driver.result["template_after"] = read_text(template)
  driver.result["new_file"] = read_text("8002_测试新角色.csv")


SCENARIOS = {
    "chara_after_event": chara_after_event,
    "new_entry_after_event": new_entry_after_event,
    "premise_list_actions": premise_list_actions,
    "new_chara": new_chara,
}
""" 场景名到场景函数 """


if __name__ == "__main__":
  DRIVER = FileLoadDriver(sys.argv[1])
  SCENARIOS[sys.argv[3]](DRIVER, sys.argv[2], sys.argv[4])
  print(json.dumps(DRIVER.result, ensure_ascii=False))
  sys.stdout.flush()
  # 编辑器在导入时建好 QApplication，直接结束进程
  os._exit(0)
