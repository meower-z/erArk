"""
医疗系统包界面面板导入边界测试
==============================
验证导入医疗系统包及后端子模块时不载入两个医疗界面面板，并核对通配导入绑定的后端子模块名。
同时通过语法树检查 Script/System/Medical_System 顶层各 .py 文件。
检查断言这些文件不导入名称段以 _panel 结尾的模块或成员。
"""

import os
import subprocess
import sys

from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT
from tests.fast.test_discovery_service import panel_imports
from tests.fast.test_medical_log_draw_hooks import MEDICAL_DIR

BLOCKED_RUN = """
import importlib.abc, sys
PANELS = ("Script.UI.Panel.medical_department_panel",
    "Script.UI.Panel.medical_player_diagnose_panel")
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname in PANELS:
            raise ImportError(fullname)
block = Block()
sys.meta_path.insert(0, block)
import tests.fast
import Script.System.Medical_System
from Script.System.Medical_System import medical_constant, medical_service
print(sorted(name for name in PANELS if name in sys.modules))
names = {}
exec("from Script.System.Medical_System import *", names)
print(sorted(name for name in names if name != "__builtins__"))
"""
"""子进程测试脚本，先拦截两个医疗界面面板的导入，再执行包导入与通配导入并输出两行检查结果。"""
BACKEND = [
    "clinic_doctor_service",
    "clinic_patient_management",
    "hospital_doctor_service",
    "hospital_patient_management",
    "log_system",
    "medical_constant",
    "medical_core",
    "medical_player_diagnose_function",
    "medical_service",
]
"""对医疗系统包执行通配导入时预期绑定的九个后端子模块名称列表（按字典序排列）。"""


class PackageImportTest(FastTestCase):
    """验证在子进程中导入医疗系统包不载入两个医疗界面面板，且通配导入绑定名称与 BACKEND 一致。"""

    result: subprocess.CompletedProcess[str]
    """setUpClass 运行 BLOCKED_RUN 子进程后保存的 CompletedProcess 执行结果。"""

    @classmethod
    def setUpClass(cls) -> None:
        """在仓库根目录运行一次 BLOCKED_RUN 子进程并将结果存至 cls.result。"""
        super().setUpClass()
        cls.result = subprocess.run(
            [sys.executable, "-c", BLOCKED_RUN],
            cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
            capture_output=True,
            encoding="utf-8",
            timeout=300,
        )

    def line(self, index: int) -> str:
        """
        断言子进程退出码为 0，并返回标准输出末尾两行中的指定行。
        Keyword arguments:
        index -- int，在标准输出末尾两行中的索引
        Return arguments:
        str -- 对应索引位置的标准输出行文本
        """
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-2000:])
        return self.result.stdout.splitlines()[-2:][index]

    def test_package_import_skips_panels(self) -> None:
        """验证导入医疗系统包及后端子模块后，sys.modules 中不含两个医疗界面面板模块。"""
        self.assertEqual(self.line(0), "[]")

    def test_star_import_binds_backend(self) -> None:
        """验证对医疗系统包执行通配导入后，绑定名称列表与 BACKEND 完全一致。"""
        self.assertEqual(self.line(1), repr(BACKEND))


class PackageSourceBoundaryTest(FastTestCase):
    """通过语法树验证医疗系统包顶层 .py 文件不导入名称段以 _panel 结尾的模块或成员。"""

    def test_non_panel_modules_skip_panels(self) -> None:
        """验证医疗系统包顶层 .py 文件（含 __init__.py）的 panel_imports 返回空列表。"""
        checked = [
            path.relative_to(ROOT).as_posix()
            for path in sorted((ROOT / MEDICAL_DIR).glob("*.py"))
        ]
        self.assertIn(f"{MEDICAL_DIR}/__init__.py", checked)
        for relative in checked:
            source = (ROOT / relative).read_bytes()
            with self.subTest(path=relative):
                self.assertEqual(panel_imports(source, relative), [])
