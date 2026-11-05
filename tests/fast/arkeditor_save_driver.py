"""
ArkEditor 保存操作的离屏驱动脚本，由 test_arkeditor_save.py 在子进程里运行
====================================================================
用法：python arkeditor_save_driver.py <编辑器目录> <数据目录> <文件类型>
文件类型为 talk 或 event，各类型打开的文件名见 OPEN_FILES。
脚本在编辑器目录里载入编辑器，不进入事件循环。
脚本从菜单打开数据目录里的文件，点选第一条，在文本框末尾加上 MARK。
然后脚本依次按保存按钮、点菜单里的保存项、按 Ctrl+S。
最后脚本在标准输出打印一行 JSON。
saves 记着每个保存操作写入打开的文件的次数，以及操作后文件与备份的文字。
step_errors 记着各步里槽函数抛出的异常。
"""

import builtins
import glob
import importlib
import json
import os
import sys
from typing import Any
from collections.abc import Callable

from arkeditor_file_load_driver import FileLoadDriver, file_text_or_none

OPEN_FILES = {"talk": "talk.csv", "event": "event1.json"}
""" 文件类型到打开的文件名，文件在数据目录里 """
MARK = "XYZ"
""" 加在第一条文本末尾的文字 """


class WriteCounter:
  """代替内置 open：以写入方式打开 path 时计数，再照常打开文件"""

  def __init__(self, path: str) -> None:
    """
    记下要数的文件与内置 open，计数从 0 开始
    Keyword arguments:
    path -- str，要数写入次数的文件路径
    """
    self.path = path
    self.count = 0
    self.real_open = builtins.open

  def __call__(self, file: Any, *args: Any, **kwargs: Any) -> Any:
    """
    打开的是 path 且模式含 w、a、x 或 + 时计数一次，再用内置 open 打开文件
    Keyword arguments:
    file -- 文件路径或描述符
    args -- 内置 open 的其余位置参数，其中第一个是模式
    kwargs -- 内置 open 的关键字参数
    Return arguments:
    Any -- 内置 open 返回的文件对象
    """
    mode = args[0] if args else kwargs.get("mode", "r")
    if file == self.path and set(mode) & set("wax+"):
      self.count += 1
    return self.real_open(file, *args, **kwargs)


def open_and_edit(
    driver: FileLoadDriver, path: str, kind: str
) -> dict[str, Callable[[], Any]]:
  """
  从菜单打开 kind 类型的文件 path，点选第一条，在文本框末尾加上 MARK
  Keyword arguments:
  driver -- FileLoadDriver，编辑器驱动
  path -- str，要打开的文件
  kind -- str，talk 或 event
  Return arguments:
  dict[str, Callable[[], Any]] -- 保存操作名到无参数的操作。
  button 点保存按钮，menu 触发菜单里的保存项，
  ctrl_s 发出 Ctrl+S 快捷键的 activated 信号
  """
  menu_bar = driver.editor.menu_bar
  if kind == "talk":
    driver.open_talk_file(path)
    menu_save = menu_bar.save_talk_action
  else:
    driver.open_event_file(path)
    menu_save = menu_bar.save_event_action
  driver.select_row(0)
  text_box = driver.editor.item_text_edit.label_text
  text_box.setPlainText(text_box.toPlainText() + MARK)
  shortcuts = [
      shortcut
      for shortcut in driver.editor.main_window.findChildren(
          importlib.import_module("PySide6.QtGui").QShortcut
      )
      if shortcut.key().toString() == "Ctrl+S"
  ]
  return {
      "button": driver.editor.item_text_edit.save_button.click,
      "menu": menu_save.trigger,
      "ctrl_s": shortcuts[0].activated.emit,
  }


def save_actions(driver: FileLoadDriver, data_dir: str, kind: str) -> None:
  """
  打开 kind 类型的文件并改第一条的文本，再依次做三个保存操作。
  每个操作的写入次数、操作后文件的文字与备份文件夹里文件名排在最后的备份的文字
  记进 driver.result["saves"]
  Keyword arguments:
  driver -- FileLoadDriver，编辑器驱动
  data_dir -- str，数据目录
  kind -- str，talk 或 event
  Return arguments:
  None -- 无
  """
  path = os.path.join(data_dir, OPEN_FILES[kind])
  backup_glob = os.path.join(os.path.dirname(data_dir), "备份", "*")
  actions = open_and_edit(driver, path, kind)
  counter = WriteCounter(path)
  builtins.open = counter
  driver.result["saves"] = {}
  for name, action in actions.items():
    counter.count = 0
    driver.step(name, action)
    backups = sorted(glob.glob(backup_glob))
    driver.result["saves"][name] = {
        "writes": counter.count,
        "file": file_text_or_none(path),
        "backup": file_text_or_none(backups[-1]) if backups else None,
    }
  builtins.open = counter.real_open


if __name__ == "__main__":
  DRIVER = FileLoadDriver(sys.argv[1])
  save_actions(DRIVER, sys.argv[2], sys.argv[3])
  print(json.dumps(DRIVER.result, ensure_ascii=False))
  sys.stdout.flush()
  # 编辑器在导入时建好 QApplication，用 os._exit 结束进程，跳过解释器的退出清理
  os._exit(0)
