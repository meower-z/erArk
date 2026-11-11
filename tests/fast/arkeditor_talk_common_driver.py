"""
ArkEditor 从口上菜单打开通用口上组件文件再按保存的驱动脚本，由 test_arkeditor_talk_common.py 在子进程里运行
========================================
用法：python arkeditor_talk_common_driver.py <编辑器目录> <数据目录> <之前打开的文件>
数据目录里有口上文件 talk.csv 与通用口上组件文件 common.csv。
之前打开的文件为 talk 时，脚本先从「口上 → 读取口上文件」打开 talk.csv 并点选第一条。为 none 时不开文件。
脚本以 Qt 的 offscreen 平台在编辑器目录里载入编辑器，载入后不进入事件循环。
文件对话框不弹出，直接返回脚本给的路径。
脚本不弹出警告框，只记下它的标题与文字。
脚本接着从「口上 → 读取口上文件」打开 common.csv，再按保存按钮。
脚本最后在标准输出打印一行 JSON。JSON 里有打开 common.csv 前后的编辑器状态、两个文件在打开 common.csv 前与保存后的文字、
记下的警告框，以及槽函数抛出的异常。
"""

import json
import os
import sys
from typing import Any

from arkeditor_file_load_driver import FileLoadDriver, file_text_or_none


class TalkCommonDriver(FileLoadDriver):
    """在 FileLoadDriver 之上加入警告框的记录与编辑器状态的读取"""

    def __init__(self, editor_dir: str) -> None:
        """
        载入编辑器，不进入事件循环。QMessageBox.warning 换成 fake_warning
        Keyword arguments:
        editor_dir -- str，编辑器目录（tools/ArkEditor 的副本）
        Return arguments:
        None -- 无
        """
        super().__init__(editor_dir)
        self.result["warnings"] = []
        self.qt_widgets.QMessageBox.warning = staticmethod(self.fake_warning)

    def fake_warning(self, _parent: Any, title: str, text: str) -> Any:
        """
        代替警告框的弹出，把标题与文字记进 result["warnings"]
        Keyword arguments:
        _parent -- Any，警告框的父控件，不使用
        title -- str，标题
        text -- str，文字
        Return arguments:
        QMessageBox.StandardButton -- Ok，同按下 Ok 按钮
        """
        self.result["warnings"].append([title, text])
        return self.qt_widgets.QMessageBox.StandardButton.Ok

    def state(self) -> dict[str, Any]:
        """
        取当前文件路径、左侧列表的行数、当前文件各条目的前提与 observe() 的观察结果
        Keyword arguments:
        无
        Return arguments:
        dict[str, Any] -- 编辑器状态，键为 file_path、list_rows、entries 与 observe() 的各键
        """
        return {
            "file_path": self.cache_control.now_file_path,
            "list_rows": self.editor.data_list.list_widget.count(),
            "entries": self.data_premises(),
            **self.observe(),
        }


def open_common_then_save(
    driver: TalkCommonDriver, data_dir: str, prior: str
) -> None:
    """
    prior 为 talk 时，先从「口上 → 读取口上文件」打开 talk.csv 并点选第一条。
    然后从同一菜单项打开 common.csv，再按保存按钮。
    打开 common.csv 前后的编辑器状态记进 driver.result 的 before 与 after。
    两个文件在打开 common.csv 前与保存后的文字记进 files_before 与 files_after。
    打开与保存两步里抛出的异常记进 step_errors 的 open_common 与 save。
    Keyword arguments:
    driver -- TalkCommonDriver，编辑器驱动
    data_dir -- str，含 talk.csv 与 common.csv 的数据目录
    prior -- str，之前打开的文件，talk 或 none
    Return arguments:
    None -- 无
    """
    paths = {
        name: os.path.join(data_dir, name)
        for name in ("talk.csv", "common.csv")
    }
    if prior == "talk":
        driver.open_talk_file(paths["talk.csv"])
        driver.select_row(0)
    driver.result["files_before"] = {
        name: file_text_or_none(path) for name, path in paths.items()
    }
    driver.result["before"] = driver.state()
    driver.step(
        "open_common", lambda: driver.open_talk_file(paths["common.csv"])
    )
    driver.result["after"] = driver.state()
    driver.step("save", driver.editor.item_text_edit.save_button.click)
    driver.result["files_after"] = {
        name: file_text_or_none(path) for name, path in paths.items()
    }


if __name__ == "__main__":
    DRIVER = TalkCommonDriver(sys.argv[1])
    open_common_then_save(DRIVER, sys.argv[2], sys.argv[3])
    print(json.dumps(DRIVER.result, ensure_ascii=False))
    sys.stdout.flush()
    # 编辑器在导入时就建好了 QApplication。
    # 这里用 os._exit 结束进程，不做解释器的退出清理。
    os._exit(0)
