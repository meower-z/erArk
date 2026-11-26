"""
结算子模块无界面导入测试
========================
本测试在单个独立子进程中放行 Script.Settle，并保留 Script.UI、tkinter 与 PIL.ImageTk 等
其余默认拦截项。子进程依次导入七个结算子模块。子进程失败时，setUpClass 抛出异常。
用例断言七个模块均已载入，且子进程未加载也未尝试导入任何受拦截模块。
"""

from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import BLOCKED, ChildRun, run_ui_free

UI_FREE_SUBMODULES = (
    "Script.Settle.Second_effect",
    "Script.Settle.common_default",
    "Script.Settle.default_cloth",
    "Script.Settle.item_effect",
    "Script.Settle.orgasm_settle",
    "Script.Settle.power_settle",
    "Script.Settle.realtime_settle",
)
"""无界面子进程中验证导入的七个 Script.Settle 子模块全名元组。"""
IMPORT_RUN = """
import importlib
import sys
for name in NAMES:
    importlib.import_module(name)
payload["imported"] = sorted(name for name in NAMES if name in sys.modules)
"""
"""在子进程中依次导入 NAMES 所列模块并将已载入模块名写入 payload 的代码片段。"""


class SettleSubmodulesUiFreeTest(FastTestCase):
    """七个 Script.Settle 子模块的无界面子进程导入测试。"""

    child: ChildRun

    @classmethod
    def setUpClass(cls) -> None:
        """放行 Script.Settle 并在子进程导入七个子模块，子进程失败时抛出 RuntimeError。"""
        names = f"NAMES = {UI_FREE_SUBMODULES!r}\n"
        cls.child = run_ui_free(
            names + IMPORT_RUN,
            boot=True,
            blocked=BLOCKED - {"Script.Settle"},
        )

    def test_submodules_load_no_ui(self) -> None:
        """断言七个结算子模块均已导入，且受拦截模块未被加载也未被尝试导入。"""
        self.assertEqual(
            self.child.payload["imported"], sorted(UI_FREE_SUBMODULES)
        )
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))
