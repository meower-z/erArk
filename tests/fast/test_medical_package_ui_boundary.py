"""
医疗系统包界面面板导入边界测试
==============================
验证导入医疗系统包及后端子模块时不载入两个医疗界面面板，并核对通配导入结果与按名直接导入面板的行为。
同时通过语法树检查 Script/System/Medical_System 顶层非面板模块不导入面板模块或后端界面边界守卫禁止的模块。
"""

import subprocess
import sys

from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports
from tests.fast.test_discovery_service import panel_imports
from tests.fast.test_medical_log_draw_hooks import MEDICAL_DIR, PANELS

BLOCKED_RUN = """
import importlib.abc, sys
PANELS = ("Script.System.Medical_System.medical_department_panel",
    "Script.System.Medical_System.medical_player_diagnose_panel")
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
sys.meta_path.remove(block)
from Script.Config import normal_config
from Script.System.Medical_System import medical_department_panel
from Script.System.Medical_System import medical_player_diagnose_panel
panel = medical_department_panel.Medical_Department_Panel(
    normal_config.config_normal.text_width)
package = sys.modules["Script.System.Medical_System"]
print(type(panel).__name__, callable(medical_player_diagnose_panel.start_player_diagnose_flow),
    package.medical_department_panel is medical_department_panel)
"""
"""子进程测试脚本，先拦截两个医疗界面面板导入以验证包导入与通配导入，再解除拦截验证按名直接导入两面板。"""
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
    """验证在子进程中导入医疗系统包不载入两个医疗界面面板，且通配导入与按名直接导入均符合预期。"""

    result: subprocess.CompletedProcess[str]
    """setUpClass 运行 BLOCKED_RUN 子进程后保存的 CompletedProcess 执行结果。"""

    @classmethod
    def setUpClass(cls) -> None:
        """在仓库根目录运行一次 BLOCKED_RUN 子进程并将结果存至 cls.result。"""
        super().setUpClass()
        cls.result = subprocess.run(
            [sys.executable, "-c", BLOCKED_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )

    def line(self, index: int) -> str:
        """
        断言子进程退出码为 0，并返回标准输出末尾三行中的指定行。
        Keyword arguments:
        index -- int，在标准输出末尾三行中的索引
        Return arguments:
        str -- 对应索引位置的标准输出行文本
        """
        self.assertEqual(self.result.returncode, 0, self.result.stderr[-2000:])
        return self.result.stdout.splitlines()[-3:][index]

    def test_package_import_skips_panels(self) -> None:
        """验证导入医疗系统包及后端子模块后，sys.modules 中不含两个医疗界面面板模块。"""
        self.assertEqual(self.line(0), "[]")

    def test_star_import_binds_backend(self) -> None:
        """验证对医疗系统包执行通配导入后，绑定名称列表与 BACKEND 完全一致。"""
        self.assertEqual(self.line(1), repr(BACKEND))

    def test_panels_import_directly(self) -> None:
        """验证解除拦截后按名直接导入两个医疗界面面板可正常构造面板、获取可调用入口并挂载包属性。"""
        self.assertEqual(self.line(2), "Medical_Department_Panel True True")


class PackageSourceBoundaryTest(FastTestCase):
    """通过语法树验证医疗系统包顶层非面板模块不导入面板模块及后端界面边界守卫禁止的模块。"""

    def test_non_panel_modules_skip_panels(self) -> None:
        """验证医疗系统包顶层非面板模块（含 __init__.py）经 panel_imports 与 banned_imports 检查均返回空列表。"""
        sources = sorted((ROOT / MEDICAL_DIR).glob("*.py"))
        checked = [
            path.relative_to(ROOT).as_posix()
            for path in sources
            if path.name not in PANELS
        ]
        self.assertIn(f"{MEDICAL_DIR}/__init__.py", checked)
        for relative in checked:
            source = (ROOT / relative).read_bytes()
            with self.subTest(path=relative):
                self.assertEqual(
                    (
                        panel_imports(source, relative),
                        banned_imports(source, relative),
                    ),
                    ([], []),
                )
