"""
协议层无界面导入测试
====================
验证 Script.Protocol 包及其全部子模块可在无界面子进程中导入。
导入结束后断言未尝试导入且未加载任何默认受限模块。
"""

from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

IMPORT_ALL = """
import importlib
import pkgutil
import Script.Protocol
for module in pkgutil.walk_packages(Script.Protocol.__path__, "Script.Protocol."):
    importlib.import_module(module.name)
"""
"""导入 Script.Protocol 并遍历导入其全部子模块的子进程代码片段。"""


class ProtocolUiFreeTest(FastTestCase):
    """Script.Protocol 全部模块的无界面子进程导入测试。"""

    def test_every_protocol_module_imports_without_ui(self) -> None:
        """
        验证经 run_ui_free 导入 Script.Protocol 全部模块正常完成。
        同时断言返回的 attempted 与 loaded 均为空列表。
        """
        run = run_ui_free(IMPORT_ALL)
        self.assertEqual((run.attempted, run.loaded), ([], []))
