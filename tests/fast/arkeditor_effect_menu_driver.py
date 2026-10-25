"""
ArkEditor 结算列表的离屏驱动脚本，由 test_arkeditor_effect_menu.py 在子进程里运行
==============================================================================
用法：python arkeditor_effect_menu_driver.py <编辑器目录> <事件文件> <口上文件> <场景>
在编辑器目录里载入编辑器（不进入事件循环），按场景依次打开事件文件与口上文件、点选条目、在结算列表上右键，
文件对话框返回给定路径，右键菜单与结算选择窗口不弹出：菜单只记下各项与是否可选并按场景选一项，窗口只记下类名；
综合指令状态结算窗口在场景要加结算时，在窗口的行为菜单里选一个行为（或不选）再按确定；
综合型基础数值结算、前提窗口在场景要加结算或前提时，在窗口的属性菜单里选一项（或留在待选择）、按需填判定值，再按确定。
最后在标准输出打印一行 JSON：各步之后的选中条目、前提与结算列表的文字、事件数据里的前提与结算、弹出的菜单与窗口、
存盘后文件里的结算，以及槽函数抛出的异常。
场景：
  event_then_talk  先开事件文件并点选第一条事件，再开口上文件，右键删除结算；新增口上后再右键删除，
                   再按结算列表的整体清零、整体修改、综合指令状态结算按钮
  talk_then_event  先开口上文件并点选第一条口上，再开事件文件并点选第一条事件，右键删除第一条结算
  cse_add_and_reopen  开事件文件并点选第一条事件，从综合指令状态结算窗口依次加入 CSE_BEHAVIORS 的结算，
                      保存事件文件后重新打开并点选第一条事件
  cse_empty_ok     开事件文件并点选第一条事件，在综合指令状态结算窗口里不选行为按确定，再选行为 chat 按确定
  cv_empty_ok      开事件文件并点选第一条事件，在综合型基础数值结算、前提窗口里属性留在待选择按确定，
                   再选属性好感按确定
  cve_add_and_reopen  开事件文件并点选第一条事件，从综合型基础数值结算窗口依次加入 CVE_CHOICES 的结算，
                      保存事件文件后重新打开并点选第一条事件
"""

import importlib
import json
import os
import sys
import traceback
from types import TracebackType
from typing import Any

CSE_BEHAVIORS = ("share_blankly", "chat")
""" cse_add_and_reopen 加入的结算所选的行为 id：带下划线与不带的各一个 """
CVE_CHOICES = (("好感", None), ("移动", "Dr_room"))
""" cve_add_and_reopen 加入的结算所选的属性与填的判定值（None 时不改）：判定值带下划线与不带的各一个 """


def list_texts(list_widget: Any) -> list[str]:
  """
  取列表控件里每一项的文字
  Keyword arguments:
  list_widget -- QListWidget
  Return arguments:
  list[str] -- 各项文字，按列表顺序
  """
  return [list_widget.item(i).text() for i in range(list_widget.count())]


class EditorDriver:
  """在编辑器目录里载入编辑器，替换文件对话框、右键菜单与窗口的弹出，提供各步操作并记下观察结果"""

  def __init__(self, editor_dir: str) -> None:
    """
    载入编辑器，不进入事件循环
    Keyword arguments:
    editor_dir -- 编辑器目录（tools/ArkEditor 的副本）
    """
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.chdir(editor_dir)
    sys.path.insert(0, editor_dir)
    self.result: dict[str, Any] = {"errors": [], "menus": [], "dialogs": []}
    self.path = ""
    self.action_text = ""
    # 综合指令状态结算窗口里要选的行为 id，为空字符串时不选；None 时窗口只记下类名
    self.cse_behavior_id: str | None = None
    # 综合型基础数值结算、前提窗口里要选的属性与要填的判定值（None 时不改）；整体为 None 时窗口只记下类名
    self.cv_choice: tuple[str, str | None] | None = None
    sys.excepthook = self.record_error
    self.qt_widgets = importlib.import_module("PySide6.QtWidgets")
    self.qt_widgets.QApplication.exec = lambda app: 0
    self.qt_widgets.QFileDialog.getOpenFileName = staticmethod(
        lambda *args, **kwargs: (self.path, "")
    )
    # 普通函数挂到类上才会收到菜单与窗口本身
    self.qt_widgets.QMenu.exec_ = lambda menu, *args: self.fake_menu_exec(menu)
    self.qt_widgets.QDialog.exec = lambda dialog, *args: self.fake_dialog_exec(
        dialog
    )
    self.editor = importlib.import_module("main")
    self.cache_control = importlib.import_module("cache_control")

  def record_error(
      self,
      exc_type: type[BaseException],
      exc: BaseException,
      tb: TracebackType | None,
  ) -> None:
    """
    记下槽函数里抛出的异常
    Keyword arguments:
    exc_type -- 异常类型
    exc -- 异常
    tb -- 回溯
    Return arguments:
    无
    """
    self.result["errors"].append(
        "".join(traceback.format_exception(exc_type, exc, tb))
    )

  def fake_menu_exec(self, menu: Any) -> Any:
    """
    代替右键菜单的弹出：记下菜单各项与是否可选，返回场景要选的那一项
    Keyword arguments:
    menu -- QMenu
    Return arguments:
    QAction | None -- 选中的项
    """
    actions = menu.actions()
    self.result["menus"].append({a.text(): a.isEnabled() for a in actions})
    for action in actions:
      if action.text() == self.action_text and action.isEnabled():
        return action
    return None

  def fake_dialog_exec(self, dialog: Any) -> int:
    """
    代替结算选择窗口的弹出：记下窗口类名；要加综合指令状态结算时，在窗口里选行为再按确定
    Keyword arguments:
    dialog -- QDialog
    Return arguments:
    int -- 0，同关闭窗口
    """
    self.result["dialogs"].append(type(dialog).__name__)
    if type(dialog).__name__ == "CSEMenu" and self.cse_behavior_id is not None:
      self.fill_cse_menu(dialog, self.cse_behavior_id)
    if type(dialog).__name__ == "CVEMenu" and self.cv_choice is not None:
      self.fill_cv_menu(
          dialog.cve_b1, dialog.cve_d, dialog.ok_button, self.cv_choice
      )
    if type(dialog).__name__ == "CVPMenu" and self.cv_choice is not None:
      self.fill_cv_menu(
          dialog.cvp_b1, dialog.cvp_d, dialog.ok_button, self.cv_choice
      )
    return 0

  def fill_cse_menu(self, dialog: Any, behavior_id: str) -> None:
    """
    在综合指令状态结算窗口的行为菜单里选 behavior_id 对应的行为（为空字符串时不选），再按确定
    Keyword arguments:
    dialog -- CSEMenu
    behavior_id -- 行为 id
    Return arguments:
    无
    """
    # 选中行为后窗口会重建行为菜单，所以先找到动作再触发
    picked = None
    for sub_action in dialog.status_menu.actions():
      sub_menu = sub_action.menu()
      if sub_menu is None:
        continue
      for action in sub_menu.actions():
        if action.data() == behavior_id:
          picked = action
    if picked is not None:
      picked.trigger()
    dialog.ok_button.click()

  def fill_cv_menu(
      self,
      attribute_box: Any,
      value_box: Any,
      ok_button: Any,
      choice: tuple[str, str | None],
  ) -> None:
    """
    在综合型基础数值结算或前提窗口里选属性、填判定值，再按确定
    Keyword arguments:
    attribute_box -- 窗口的属性菜单（QComboBox）
    value_box -- 窗口的判定值输入框（QTextEdit）
    ok_button -- 窗口的确定按钮
    choice -- 要选的属性与要填的判定值（None 时不改）
    Return arguments:
    无
    """
    attribute, value = choice
    # 选属性时窗口会重置判定值，所以先选属性再填判定值
    attribute_box.setCurrentText(attribute)
    if value is not None:
      value_box.setPlainText(value)
    ok_button.click()

  def snapshot(self, name: str) -> None:
    """
    记下当前的选中条目、前提与结算列表的文字、事件数据里的结算
    Keyword arguments:
    name -- 这一步的名字
    Return arguments:
    无
    """
    self.result[name] = {
        "select_id": self.cache_control.now_select_id,
        "premise_list": list_texts(self.editor.item_premise_list.item_list),
        "effect_list": list_texts(self.editor.item_effect_list.item_list),
        "event_effects": {
            uid: dict(event.effect)
            for uid, event in self.cache_control.now_event_data.items()
        },
        "event_premises": {
            uid: dict(event.premise)
            for uid, event in self.cache_control.now_event_data.items()
        },
    }

  def open_event_file(self, path: str) -> None:
    """
    从菜单打开事件文件
    Keyword arguments:
    path -- 文件对话框返回的路径
    Return arguments:
    无
    """
    self.path = path
    self.editor.menu_bar.select_event_file_action.trigger()

  def open_talk_file(self, path: str) -> None:
    """
    从菜单打开口上文件
    Keyword arguments:
    path -- 文件对话框返回的路径
    Return arguments:
    无
    """
    self.path = path
    self.editor.menu_bar.select_talk_file_action.trigger()

  def click_row(self, row: int) -> None:
    """
    在左侧条目列表里点选一行
    Keyword arguments:
    row -- 行号
    Return arguments:
    无
    """
    data_list = self.editor.data_list.list_widget
    data_list.clicked.emit(data_list.model().index(row, 0))

  def right_click(self, action_text: str) -> None:
    """
    在结算列表第一行的位置右键，并在菜单里选一项
    Keyword arguments:
    action_text -- 要选的菜单项文字
    Return arguments:
    无
    """
    self.action_text = action_text
    effect_list = self.editor.item_effect_list.item_list
    rect = effect_list.visualRect(effect_list.model().index(0, 0))
    effect_list.customContextMenuRequested.emit(rect.center())

  def press(self, text: str) -> None:
    """
    按下结算列表上文字为 text 的按钮
    Keyword arguments:
    text -- 按钮文字
    Return arguments:
    无
    """
    buttons = self.editor.item_effect_list.findChildren(
        self.qt_widgets.QPushButton
    )
    for button in buttons:
      if button.text() == text:
        button.click()
        return
    raise LookupError(text)

  def add_cse(self, behavior_id: str) -> None:
    """
    按结算列表的综合指令状态结算按钮，在窗口里选行为后按确定
    Keyword arguments:
    behavior_id -- 要选的行为 id，为空字符串时不选
    Return arguments:
    无
    """
    self.cse_behavior_id = behavior_id
    self.press("综合指令状态结算")
    self.cse_behavior_id = None

  def add_cv(self, button_text: str, attribute: str, value: str | None) -> None:
    """
    按结算列表或前提列表上文字为 button_text 的按钮，在打开的窗口里选属性、填判定值后按确定
    Keyword arguments:
    button_text -- 按钮文字
    attribute -- 要选的属性
    value -- 要填的判定值，为 None 时不改
    Return arguments:
    无
    """
    self.cv_choice = (attribute, value)
    for panel in (self.editor.item_effect_list, self.editor.item_premise_list):
      for button in panel.findChildren(self.qt_widgets.QPushButton):
        if button.text() == button_text:
          button.click()
          self.cv_choice = None
          return
    raise LookupError(button_text)

  def save_event_file(self) -> None:
    """
    从菜单保存事件文件，记下文件里各条事件的结算
    Keyword arguments:
    无
    Return arguments:
    无
    """
    self.editor.menu_bar.save_event_action.trigger()
    with open(self.path, encoding="utf-8") as event_file:
      self.result["saved_effects"] = {
          uid: event["effect"] for uid, event in json.load(event_file).items()
      }

  def add_entry(self) -> None:
    """
    按左侧条目列表的新增条目按钮
    Keyword arguments:
    无
    Return arguments:
    无
    """
    self.editor.data_list.new_text_button.click()


def event_then_talk(
    driver: EditorDriver, event_path: str, talk_path: str
) -> None:
  """
  先开事件文件并点选第一条事件，再开口上文件，在结算列表上右键删除、新增口上、按结算按钮
  Keyword arguments:
  driver -- 编辑器驱动
  event_path -- 事件文件路径
  talk_path -- 口上文件路径
  Return arguments:
  无
  """
  driver.open_event_file(event_path)
  driver.click_row(0)
  driver.snapshot("event_selected")
  driver.open_talk_file(talk_path)
  driver.snapshot("talk_opened")
  driver.right_click("删除")
  driver.snapshot("talk_deleted")
  driver.add_entry()
  driver.snapshot("talk_added")
  driver.right_click("删除")
  driver.snapshot("talk_added_deleted")
  for text in ("整体清零", "整体修改", "综合指令状态结算"):
    driver.press(text)
  driver.snapshot("talk_buttons")


def talk_then_event(
    driver: EditorDriver, event_path: str, talk_path: str
) -> None:
  """
  先开口上文件并点选第一条口上，再开事件文件并点选第一条事件，右键删除第一条结算
  Keyword arguments:
  driver -- 编辑器驱动
  event_path -- 事件文件路径
  talk_path -- 口上文件路径
  Return arguments:
  无
  """
  driver.open_talk_file(talk_path)
  driver.click_row(0)
  driver.snapshot("talk_selected")
  driver.open_event_file(event_path)
  driver.snapshot("event_opened")
  driver.click_row(0)
  driver.snapshot("event_selected")
  driver.right_click("删除")
  driver.snapshot("event_deleted")


def cse_add_and_reopen(
    driver: EditorDriver, event_path: str, talk_path: str
) -> None:
  """
  开事件文件并点选第一条事件，加入 CSE_BEHAVIORS 的综合指令状态结算，保存后重新打开
  Keyword arguments:
  driver -- 编辑器驱动
  event_path -- 事件文件路径
  talk_path -- 口上文件路径（不用）
  Return arguments:
  无
  """
  driver.open_event_file(event_path)
  driver.click_row(0)
  for behavior_id in CSE_BEHAVIORS:
    driver.add_cse(behavior_id)
  driver.snapshot("cse_added")
  driver.save_event_file()
  driver.open_event_file(event_path)
  driver.click_row(0)
  driver.snapshot("cse_reopened")


def cse_empty_ok(driver: EditorDriver, event_path: str, talk_path: str) -> None:
  """
  开事件文件并点选第一条事件，在综合指令状态结算窗口里不选行为按确定，再选行为 chat 按确定
  Keyword arguments:
  driver -- 编辑器驱动
  event_path -- 事件文件路径
  talk_path -- 口上文件路径（不用）
  Return arguments:
  无
  """
  driver.open_event_file(event_path)
  driver.click_row(0)
  driver.add_cse("")
  driver.snapshot("cse_empty_ok")
  driver.add_cse("chat")
  driver.snapshot("cse_picked_ok")


def cv_empty_ok(driver: EditorDriver, event_path: str, talk_path: str) -> None:
  """
  开事件文件并点选第一条事件，在综合型基础数值结算、前提窗口里属性留在待选择按确定，再选属性好感按确定
  Keyword arguments:
  driver -- 编辑器驱动
  event_path -- 事件文件路径
  talk_path -- 口上文件路径（不用）
  Return arguments:
  无
  """
  driver.open_event_file(event_path)
  driver.click_row(0)
  for button_text in ("综合型基础数值结算", "综合型基础数值前提"):
    driver.add_cv(button_text, "待选择", None)
  driver.snapshot("cv_empty_ok")
  for button_text in ("综合型基础数值结算", "综合型基础数值前提"):
    driver.add_cv(button_text, "好感", None)
  driver.snapshot("cv_picked_ok")


def cve_add_and_reopen(
    driver: EditorDriver, event_path: str, talk_path: str
) -> None:
  """
  开事件文件并点选第一条事件，加入 CVE_CHOICES 的综合型基础数值结算，保存后重新打开
  Keyword arguments:
  driver -- 编辑器驱动
  event_path -- 事件文件路径
  talk_path -- 口上文件路径（不用）
  Return arguments:
  无
  """
  driver.open_event_file(event_path)
  driver.click_row(0)
  for attribute, value in CVE_CHOICES:
    driver.add_cv("综合型基础数值结算", attribute, value)
  driver.snapshot("cve_added")
  driver.save_event_file()
  driver.open_event_file(event_path)
  driver.click_row(0)
  driver.snapshot("cve_reopened")


SCENARIOS = {
    "event_then_talk": event_then_talk,
    "talk_then_event": talk_then_event,
    "cse_add_and_reopen": cse_add_and_reopen,
    "cse_empty_ok": cse_empty_ok,
    "cv_empty_ok": cv_empty_ok,
    "cve_add_and_reopen": cve_add_and_reopen,
}
""" 场景名到场景函数 """


if __name__ == "__main__":
  DRIVER = EditorDriver(sys.argv[1])
  SCENARIOS[sys.argv[4]](DRIVER, sys.argv[2], sys.argv[3])
  print(json.dumps(DRIVER.result, ensure_ascii=False))
  sys.stdout.flush()
  # 编辑器在导入时建好 QApplication，直接结束进程
  os._exit(0)
