"""
ArkEditor 综合型基础数值结算窗口（CVEMenu）与综合型基础数值前提窗口
（CVPMenu）的离屏驱动脚本。test_arkeditor_effect_menu.py 在子进程里
运行本脚本。本脚本不用口上文件参数。
用法：python arkeditor_cv_target_driver.py <编辑器目录> <事件文件> <口上文件> <场景>
场景结束后，本脚本在标准输出打印一行 JSON。这行 JSON 有 errors、menus、
dialogs 三个键。场景记下的每个快照也以快照名为键放在里面。保存过事件
文件的场景还有 saved_effects 键。errors 是到达 sys.excepthook 的异常。
menus 是被拦下的右键菜单的各项与是否可选。dialogs 是被拦下的窗口的
类名。saved_effects 是存盘后文件里各条事件的结算。
场景：
  cve_scene_tag_reopen  开事件文件并点选第一条事件，依次加入
                        SCENE_TAG_CHOICES 的移动结算，记下快照
                        cve_added。再保存并重新打开事件文件，点选
                        第一条事件，记下快照 cve_reopened。
  cve_change_target_reopen  步骤同 cve_scene_tag_reopen。加入的是
                            CHANGE_TARGET_IDS 里各 id 的指定角色id为
                            交互对象结算。
  cv_empty_box_ok  开事件文件并点选第一条事件。在 CVEMenu 与 CVPMenu 里
                   各选属性好感，把对象设为角色id为，id 框留空后按确定。
                   再在 CVPMenu 里选属性好感，清空判定值框后按确定。然后
                   记下快照 cv_empty_box_ok。最后在 CVPMenu 里选属性礼物，
                   清空隐藏的判定值框后按确定，记下快照 cv_hidden_box_ok。
"""

import json
import os
import sys
from collections.abc import Iterable
from typing import Any

from arkeditor_effect_menu_driver import EditorDriver

SCENE_TAG_CHOICES = (
    ("Auditorium", None),
    ("Teahouse", None),
    ("Lungmen_Eatery", None),
    ("Sauna", "358"),
)
""" cve_scene_tag_reopen 里各条移动结算的地点标签与角色 id（None 时不改对象） """
CHANGE_TARGET_IDS = ("107", "0", "358")
""" cve_change_target_reopen 依次加入的指定角色id为交互对象结算的角色 id """


class TargetIdDriver(EditorDriver):
  """在 CVEMenu、CVPMenu 里还能把对象设为角色id为并填入 target_id 的驱动"""

  def __init__(self, editor_dir: str) -> None:
    """
    载入编辑器，不进入事件循环
    Keyword arguments:
    editor_dir -- tools/ArkEditor 副本的目录路径（str）
    """
    super().__init__(editor_dir)
    # 非 None 时，fill_cv_menu 把对象设为角色id为并填入此 id。
    # None 时不动对象菜单与 id 框。
    self.target_id: str | None = None

  def fill_cv_menu(
      self,
      attribute_box: Any,
      value_box: Any,
      ok_button: Any,
      choice: tuple[str, str | None],
  ) -> None:
    """
    在 CVEMenu 或 CVPMenu 里先选 choice 里的属性。target_id 不为 None 时，
    再把对象设为角色id为并在 id 框里填入 target_id。choice 里的判定值不为
    None 时，再填判定值。最后按确定。
    Keyword arguments:
    attribute_box -- 窗口的属性菜单（QComboBox）
    value_box -- 窗口的判定值框（QTextEdit）
    ok_button -- 窗口的确定按钮（QPushButton）
    choice -- 要选的属性与要填的判定值（tuple[str, str | None]）。
    判定值为 None 时不填。
    Return arguments:
    无
    """
    attribute, value = choice
    # 先选属性，因为选属性时 change_b2 可能改动对象菜单与判定值框。
    attribute_box.setCurrentText(attribute)
    if self.target_id is not None:
      dialog = ok_button.window()
      prefix = type(dialog).__name__[:3].lower()
      getattr(dialog, prefix + "_a").setCurrentText("角色id为")
      getattr(dialog, prefix + "_a2").setPlainText(self.target_id)
    if value is not None:
      value_box.setPlainText(value)
    ok_button.click()


def add_cve_and_reopen(
    driver: TargetIdDriver,
    event_path: str,
    choices: Iterable[tuple[str, str | None, str | None]],
) -> None:
  """
  打开事件文件并点选第一条事件。按 choices 依次加入综合型基础数值结算，
  再记下快照 cve_added。然后保存事件文件，保存时记下 saved_effects。之后
  重新打开事件文件并点选第一条事件，再记下快照 cve_reopened。
  Keyword arguments:
  driver -- 编辑器驱动（TargetIdDriver）
  event_path -- 事件文件路径（str）
  choices -- 各条结算的属性、判定值与角色 id
  （Iterable[tuple[str, str | None, str | None]]）。判定值为 None 时不填。
  角色 id 为 None 时不改对象。
  Return arguments:
  无
  """
  driver.open_event_file(event_path)
  driver.click_row(0)
  for attribute, value, target_id in choices:
    driver.target_id = target_id
    driver.add_cv("综合型基础数值结算", attribute, value)
  driver.snapshot("cve_added")
  driver.save_event_file()
  driver.open_event_file(event_path)
  driver.click_row(0)
  driver.snapshot("cve_reopened")


def cve_scene_tag_reopen(driver: TargetIdDriver, event_path: str) -> None:
  """
  以 SCENE_TAG_CHOICES 里的各条移动结算运行 add_cve_and_reopen
  Keyword arguments:
  driver -- 编辑器驱动（TargetIdDriver）
  event_path -- 事件文件路径（str）
  Return arguments:
  无
  """
  choices = [("移动", tag, target) for tag, target in SCENE_TAG_CHOICES]
  add_cve_and_reopen(driver, event_path, choices)


def cve_change_target_reopen(driver: TargetIdDriver, event_path: str) -> None:
  """
  以 CHANGE_TARGET_IDS 里各 id 的指定角色id为交互对象结算运行
  add_cve_and_reopen
  Keyword arguments:
  driver -- 编辑器驱动（TargetIdDriver）
  event_path -- 事件文件路径（str）
  Return arguments:
  无
  """
  attribute = "指定角色id为交互对象"
  choices = [(attribute, None, target) for target in CHANGE_TARGET_IDS]
  add_cve_and_reopen(driver, event_path, choices)


def cv_empty_box_ok(driver: TargetIdDriver, event_path: str) -> None:
  """
  打开事件文件并点选第一条事件。在 CVEMenu 与 CVPMenu 里各选属性好感，
  把对象设为角色id为，id 框留空后按确定。再在 CVPMenu 里选属性好感，清空
  判定值框后按确定。然后记下快照 cv_empty_box_ok。最后在 CVPMenu 里选
  属性礼物，清空隐藏的判定值框后按确定，再记下快照 cv_hidden_box_ok。
  Keyword arguments:
  driver -- 编辑器驱动（TargetIdDriver）
  event_path -- 事件文件路径（str）
  Return arguments:
  无
  """
  driver.open_event_file(event_path)
  driver.click_row(0)
  driver.target_id = ""
  for button_text in ("综合型基础数值结算", "综合型基础数值前提"):
    driver.add_cv(button_text, "好感", None)
  driver.target_id = None
  driver.add_cv("综合型基础数值前提", "好感", "")
  driver.snapshot("cv_empty_box_ok")
  driver.add_cv("综合型基础数值前提", "礼物", "")
  driver.snapshot("cv_hidden_box_ok")


SCENARIOS = {
    "cve_scene_tag_reopen": cve_scene_tag_reopen,
    "cve_change_target_reopen": cve_change_target_reopen,
    "cv_empty_box_ok": cv_empty_box_ok,
}
""" 命令行里的场景名到场景函数 """


if __name__ == "__main__":
  DRIVER = TargetIdDriver(sys.argv[1])
  SCENARIOS[sys.argv[4]](DRIVER, sys.argv[2])
  print(json.dumps(DRIVER.result, ensure_ascii=False))
  sys.stdout.flush()
  # 编辑器在导入时建好 QApplication。
  # os._exit 结束进程，不做解释器的退出清理。
  os._exit(0)
