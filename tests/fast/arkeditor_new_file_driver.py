"""
ArkEditor 打开文件后从菜单新建同类文件的离屏驱动脚本，由 test_arkeditor_new_file.py 在子进程里运行
========================================
用法：python arkeditor_new_file_driver.py <编辑器目录> <数据目录> <文件类型>
文件类型为 talk 或 event，各类型先打开的文件与新建的文件名见 NEW_FILES。
脚本在编辑器目录里载入编辑器，不进入事件循环。
脚本从菜单打开数据目录里的文件并点选第一条，再从同一菜单在数据目录里新建文件。
打开时文件对话框返回要打开的文件，新建时各个文件对话框都返回新文件。
最后在标准输出打印一行 JSON，其中有新建后的当前文件、左侧列表行数与各条目的前提，
有打开的文件在新建前后的文字，还有新建这一步里槽函数抛出的异常。
"""

import json
import os
import sys

from arkeditor_file_load_driver import FileLoadDriver, file_text_or_none

NEW_FILES = {
    "talk": ("talk.csv", "new_talk.csv"),
    "event": ("event1.json", "new_event.json"),
}
""" 文件类型到先打开的文件名与新建的文件名，两个文件都在数据目录里 """


def new_file_after_open(
    driver: FileLoadDriver, data_dir: str, kind: str
) -> None:
  """
  从菜单打开 kind 类型的文件并点选第一条，再从同一菜单新建文件。新建后的状态与打开的文件前后的文字记进 driver.result
  Keyword arguments:
  driver -- FileLoadDriver，编辑器驱动
  data_dir -- str，数据目录
  kind -- str，talk 或 event
  Return arguments:
  None -- 无
  """
  open_name, new_name = NEW_FILES[kind]
  open_path = os.path.join(data_dir, open_name)
  qt_dialog = driver.qt_widgets.QFileDialog
  qt_dialog.getSaveFileName = staticmethod(
      lambda *args, **kwargs: (driver.path, "")
  )
  qt_dialog.exec = lambda dialog, *args: 1
  qt_dialog.selectedFiles = lambda dialog: [driver.path]
  if kind == "talk":
    driver.open_talk_file(open_path)
    new_action = driver.editor.menu_bar.new_talk_file_action
  else:
    driver.open_event_file(open_path)
    new_action = driver.editor.menu_bar.new_event_file_action
  driver.select_row(0)
  driver.result["open_before"] = file_text_or_none(open_path)
  driver.path = os.path.join(data_dir, new_name)
  driver.step("new", new_action.trigger)
  driver.result["after"] = {
      "file_path": driver.cache_control.now_file_path,
      "list_rows": driver.editor.data_list.list_widget.count(),
      "entries": driver.data_premises(),
  }
  driver.result["open_after"] = file_text_or_none(open_path)


if __name__ == "__main__":
  DRIVER = FileLoadDriver(sys.argv[1])
  new_file_after_open(DRIVER, sys.argv[2], sys.argv[3])
  print(json.dumps(DRIVER.result, ensure_ascii=False))
  sys.stdout.flush()
  # 编辑器在导入时建好 QApplication，用 os._exit 结束进程，不做解释器的退出清理
  os._exit(0)
