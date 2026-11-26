"""
道具系统模块无界面导入测试
==========================
本测试扫描 Script/System/Item_System 目录，收集直接位于该目录且除 __init__.py 外的模块名。
测试以 boot=True 调用 run_ui_free 启动无界面子进程。子进程安装默认导入拦截器并初始化后端，再依次导入对应模块。
用例断言 MODULES 包含 condom_handle。另一用例断言子进程成功导入 MODULES 各模块，且未尝试导入也未加载受拦截模块。
"""

from pathlib import Path

from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ROOT, ChildRun, run_ui_free

MODULES = tuple(
    sorted(
        path.stem
        for path in Path(ROOT, "Script/System/Item_System").glob("*.py")
        if path.stem != "__init__"
    )
)
""" 直接位于 Script/System/Item_System 目录下且除 __init__.py 外的已排序模块名元组。 """
LOAD_ALL = """
import importlib
for name in MODULES:
    try:
        importlib.import_module("Script.System.Item_System." + name)
    except ImportError as error:
        payload[name] = error.name
    else:
        payload[name] = None
"""
""" 子进程导入 MODULES 各模块的代码片段，成功时在 payload[name] 记 None，触发 ImportError 时记 error.name。 """


class ItemSystemUiFreeTest(FastTestCase):
    """Script/System/Item_System 模块的无界面子进程导入测试。"""

    child: ChildRun
    """ setUpClass 运行无界面子进程后保存的 ChildRun 结果。 """

    @classmethod
    def setUpClass(cls) -> None:
        """以 boot=True 调用 run_ui_free 导入 MODULES 各模块，并将结果存入 cls.child。"""
        cls.child = run_ui_free(f"MODULES = {MODULES!r}\n{LOAD_ALL}", boot=True)

    def test_scope_lists_item_modules(self) -> None:
        """断言 MODULES 包含模块名 condom_handle。"""
        self.assertIn("condom_handle", MODULES)

    def test_item_modules_load_without_ui(self) -> None:
        """断言子进程成功导入 MODULES 各模块，且未尝试导入也未加载受拦截模块。"""
        self.assertEqual(self.child.payload, dict.fromkeys(MODULES))
        self.assertEqual(self.child.attempted, [])
        self.assertEqual(self.child.loaded, [])
