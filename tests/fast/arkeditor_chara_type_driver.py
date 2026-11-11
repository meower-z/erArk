"""
ArkEditor 打开属性文件的离屏驱动脚本，由 test_arkeditor_chara_str_type.py 在子进程里运行
============================================================
用法：python arkeditor_chara_type_driver.py <编辑器目录> <属性文件>
在编辑器目录里离屏载入编辑器，不进入事件循环。
文件对话框返回给定的属性文件，脚本从菜单打开它。
最后在标准输出打印一行 JSON，其中有打开时槽函数抛出的异常，以及职业、种族、势力、出身地下拉框显示的文字。
"""

import json
import os
import sys

from arkeditor_file_load_driver import FileLoadDriver

COMBO_BOXES = (
    "profession_combo_box",
    "race_combo_box",
    "nation_combo_box",
    "birthplace_combo_box",
)
""" CharaList 上要记下显示文字的四个下拉框的属性名 """


if __name__ == "__main__":
    DRIVER = FileLoadDriver(sys.argv[1])
    DRIVER.step("open_chara", lambda: DRIVER.open_chara_file(sys.argv[2]))
    chara_list = DRIVER.editor.chara_list
    DRIVER.result["combo_texts"] = {
        name: getattr(chara_list, name).currentText() for name in COMBO_BOXES
    }
    print(json.dumps(DRIVER.result, ensure_ascii=False))
    sys.stdout.flush()
    # 编辑器在导入时建好 QApplication，所以这里直接结束进程
    os._exit(0)
