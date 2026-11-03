"""
ArkEditor 打开读不了的文件后按保存的离屏驱动脚本，由 test_arkeditor_failed_open.py 运行
========================================
用法：python arkeditor_failed_open_driver.py <编辑器目录> <数据目录> <文件类型>:<之前打开的文件>
文件类型为 talk、event、chara 或 template，各类型用到的文件见 FAILED_OPEN_FILES。
之前打开的文件为 same 时，先从菜单打开 FAILED_OPEN_FILES 里该类型的可读文件，
除 chara 外再点选第一条；为 none 时不开文件。
在编辑器目录里载入编辑器（不进入事件循环），文件对话框返回给定路径。
脚本从菜单打开读不了的文件，template 时从菜单新建属性文件，读入编辑器目录下的模板。
然后按保存按钮；chara 且为 same 时再按应用并保存。
最后在标准输出打印一行 JSON：打开前后的状态、读不了的文件在打开前与保存后的文字、
以及各步里槽函数抛出的异常。
"""

import functools
import json
import os
import sys
from typing import Any

from arkeditor_file_load_driver import FileLoadDriver, file_text_or_none

FAILED_OPEN_FILES = {
    "talk": ("talk.csv", "bad_talk.csv"),
    "event": ("event1.json", "bad_event.json"),
    "chara": ("chara.csv", "bad_chara.csv"),
    "template": ("event1.json", None),
}
""" 文件类型到数据目录里的可读文件名与读不了的文件名，None 指编辑器目录下的模板 """


def save_after_failed_open(
    driver: FileLoadDriver, data_dir: str, variant: str
) -> None:
  """
  按 variant 先打开可读文件或不开文件，再打开读不了的文件，然后按保存按钮。
  chara 且为 same 时再按应用并保存。打开前后的状态与读不了的文件的文字记进 driver.result
  Keyword arguments:
  driver -- FileLoadDriver，编辑器驱动
  data_dir -- str，数据目录
  variant -- str，<文件类型>:<之前打开的文件>，如 talk:same 或 template:none
  Return arguments:
  None -- 无
  """
  kind, prior = variant.split(":")
  good_name, bad_name = FAILED_OPEN_FILES[kind]
  open_file = {
      "talk": driver.open_talk_file,
      "event": driver.open_event_file,
      "chara": driver.open_chara_file,
      "template": driver.open_event_file,
  }[kind]
  if prior == "same":
    open_file(os.path.join(data_dir, good_name))
    if kind != "chara":
      driver.select_row(0)
  if bad_name is None:
    bad_path = driver.cache_control.CHARA_TEMPLATE_PATH
    open_bad = driver.editor.menu_bar.new_chara_file_action.trigger
  else:
    bad_path = os.path.join(data_dir, bad_name)
    open_bad = functools.partial(open_file, bad_path)
  driver.result["bad_before"] = file_text_or_none(bad_path)

  def state() -> dict[str, Any]:
    """取当前文件路径、左侧列表行数、各条目的前提、角色姓名与 observe() 的结果"""
    chara_data = driver.cache_control.now_chara_data
    return {
        "file_path": driver.cache_control.now_file_path,
        "list_rows": driver.editor.data_list.list_widget.count(),
        "entries": driver.data_premises(),
        "chara_name": getattr(chara_data, "Name", None),
        **driver.observe(),
    }

  driver.result["before"] = state()
  driver.step("open_bad", open_bad)
  driver.result["after"] = state()
  driver.step("save", driver.editor.item_text_edit.save_button.click)
  if kind == "chara" and prior == "same":
    driver.step("apply", driver.editor.chara_list.apply_button.click)
  driver.result["bad_after"] = file_text_or_none(bad_path)


if __name__ == "__main__":
  DRIVER = FileLoadDriver(sys.argv[1])
  save_after_failed_open(DRIVER, sys.argv[2], sys.argv[3])
  print(json.dumps(DRIVER.result, ensure_ascii=False))
  sys.stdout.flush()
  # 编辑器在导入时建好 QApplication，用 os._exit 结束进程，不做解释器的退出清理
  os._exit(0)
