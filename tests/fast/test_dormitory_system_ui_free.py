"""
宿舍系统模块无界面导入测试
==========================
本测试扫描 Script/System/Dormitory_System 目录，收集该目录下直接包含的 .py 模块名。
测试以 boot=True 调用 run_ui_free 启动无界面子进程。子进程安装默认导入拦截器并初始化后端，再依次导入这些模块。
用例断言 MODULES 包含 dormitory_manager_system。用例也断言子进程成功导入 MODULES 各模块，且未尝试导入或加载受拦截模块。
"""

from pathlib import Path

from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ROOT, ChildRun, run_ui_free

MODULES = tuple(
    sorted(
        path.stem
        for path in Path(ROOT, "Script/System/Dormitory_System").glob("*.py")
    )
)
""" Script/System/Dormitory_System 目录下直接包含的 .py 模块名的已排序元组。 """
LOAD_ALL = """
import importlib
for name in MODULES:
    try:
        importlib.import_module("Script.System.Dormitory_System." + name)
    except ImportError as error:
        payload[name] = repr(error)
    else:
        payload[name] = None
"""
""" 子进程导入 MODULES 各模块的代码片段，成功时在 payload 记 None，触发 ImportError 时记 repr(error)。 """


class DormitorySystemUiFreeTest(FastTestCase):
    """Script/System/Dormitory_System 模块的无界面子进程导入测试。"""

    child: ChildRun
    """ setUpClass 运行无界面子进程后保存的 ChildRun 结果。 """

    @classmethod
    def setUpClass(cls) -> None:
        """以 boot=True 调用 run_ui_free 导入 MODULES 各模块，并将结果存入 cls.child。"""
        cls.child = run_ui_free(f"MODULES = {MODULES!r}\n{LOAD_ALL}", boot=True)

    def test_modules_load_without_ui(self) -> None:
        """断言 MODULES 包含 dormitory_manager_system。断言子进程成功导入各模块，且未尝试导入或加载受拦截模块。"""
        self.assertIn("dormitory_manager_system", MODULES)
        self.assertEqual(self.child.payload, dict.fromkeys(MODULES))
        self.assertEqual(self.child.attempted, [])
        self.assertEqual(self.child.loaded, [])
