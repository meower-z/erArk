"""
无界面子进程测试辅助模块测试
==========================
验证后端轻量启动、多终端编码下的中文结果与报错回传、预加载受限模块报告以及动态导入与放行规则拦截。
"""

import os
from unittest import mock

from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ROOT, run_ui_free

ENCODINGS = ("cp1252", "gbk", "utf-16")
"""编码测试覆盖的 PYTHONIOENCODING 取值元组。"""
BOOTED_RUN = """
from Script.Config import game_config
from Script.Kernel import core
payload["behaviors"] = len(game_config.config_behavior_must_settle_cid_list) > 0
payload["characters"] = len(core.state().characters)
"""
"""后端启动后检查必结行为配置非空且内核角色数为 0 的子进程代码片段。"""
CHINESE_RUN = """
import os
import sys
os.write(1, b"native write to fd 1\\n")
print("博士与干员")
payload["text"] = "博士与干员"
payload["encoding"] = sys.__stdout__.encoding
"""
"""向文件描述符 1 写入字节、打印中文并经 payload 回传中文与原始标准输出编码的子进程代码片段。"""
LAZY_IMPORT_RUN = """
import importlib
def load_later(name):
    importlib.import_module(name)
try:
    load_later({name!r})
except ImportError as error:
    payload["refused"] = error.name
"""
"""在函数内通过 importlib.import_module 延迟导入指定模块并记录被拒模块名的子进程代码片段模板。"""
TK_ORDERS_RUN = """
import sys
from Script.Modules.tk_ui import orders
payload["accept"] = callable(orders.accept)
try:
    from Script.Modules.tk_ui import callbacks
except ImportError as error:
    payload["refused"] = error.name
payload["orders_loaded"] = "Script.Modules.tk_ui.orders" in sys.modules
"""
"""验证放行 Script.Modules.tk_ui.orders 同时拦截同包 callbacks 模块的子进程代码片段。"""


def data_files() -> dict[str, tuple[int, int]]:
    """
    遍历仓库 data 目录，记录每个文件的字节大小与纳秒级修改时间。
    Keyword arguments:
    无
    Return arguments:
    dict[str, tuple[int, int]] -- 文件路径到 (字节大小, 纳秒级修改时间) 的映射
    """
    found = {}
    for folder, _, names in os.walk(os.path.join(ROOT, "data")):
        for name in names:
            path = os.path.join(folder, name)
            stat = os.stat(path)
            found[path] = (stat.st_size, stat.st_mtime_ns)
    return found


class UiFreeSubprocessTest(FastTestCase):
    """run_ui_free 辅助函数的子进程启动、编码隔离与导入拦截行为测试。"""

    def test_booted_backend_loads_no_ui_and_writes_no_data(self) -> None:
        """验证 boot=True 启动后端后配置可用、内核为空、无受限导入，且 data 目录文件保持不变。"""
        before = data_files()
        run = run_ui_free(BOOTED_RUN, boot=True)
        self.assertEqual((run.loaded, run.attempted), ([], []))
        self.assertEqual(run.payload, {"behaviors": True, "characters": 0})
        self.assertEqual(data_files(), before)

    def test_chinese_payload_survives_child_stdio_encodings(self) -> None:
        """验证在 cp1252、gbk 与 utf-16 编码下，中文结果不受文件描述符 1 输出干扰并准确回传。"""
        for encoding in ENCODINGS:
            with self.subTest(encoding):
                with mock.patch.dict(
                    os.environ, {"PYTHONIOENCODING": encoding}
                ):
                    run = run_ui_free(CHINESE_RUN)
                self.assertEqual(
                    run.payload, {"text": "博士与干员", "encoding": encoding}
                )

    def test_chinese_error_survives_child_stdio_encodings(self) -> None:
        """验证在 cp1252、gbk 与 utf-16 编码下，子进程中文异常文本完整传回父进程 RuntimeError。"""
        for encoding in ENCODINGS:
            with self.subTest(encoding):
                with (
                    mock.patch.dict(os.environ, {"PYTHONIOENCODING": encoding}),
                    self.assertRaises(RuntimeError) as caught,
                ):
                    run_ui_free('raise RuntimeError("干员诊断信息")')
                self.assertIn(
                    "RuntimeError: 干员诊断信息", str(caught.exception)
                )

    def test_already_loaded_blocked_module_is_reported(self) -> None:
        """验证拦截器安装前已载入的受限模块会被计入 loaded，且不记入 attempted。"""
        run = run_ui_free(
            'import io\npayload["name"] = io.__name__',
            blocked=frozenset({"io"}),
        )
        self.assertEqual(
            (run.payload, run.loaded, run.attempted),
            ({"name": "io"}, ["io"], []),
        )

    def test_lazy_ui_and_settle_imports_are_refused(self) -> None:
        """
        验证函数内延迟导入 Script.UI.Moudle.draw 与 Script.Settle 均触发根模块 ImportError。
        同时验证根模块记入 attempted 且 loaded 为空。
        """
        for name, root in (
            ("Script.UI.Moudle.draw", "Script.UI"),
            ("Script.Settle", "Script.Settle"),
        ):
            with self.subTest(name):
                run = run_ui_free(LAZY_IMPORT_RUN.format(name=name))
                self.assertEqual(run.payload["refused"], root)
                self.assertIn(root, run.attempted)
                self.assertEqual(run.loaded, [])

    def test_tk_ui_orders_imports_but_its_siblings_stay_blocked(self) -> None:
        """
        验证默认放行项 Script.Modules.tk_ui.orders 可正常导入且不记入 loaded。
        同时验证同包未放行的 Script.Modules.tk_ui.callbacks 被拦截并记入 attempted。
        """
        run = run_ui_free(TK_ORDERS_RUN)
        self.assertEqual(
            run.payload,
            {
                "accept": True,
                "refused": "Script.Modules.tk_ui.callbacks",
                "orders_loaded": True,
            },
        )
        self.assertEqual(run.attempted, ["Script.Modules.tk_ui.callbacks"])
        self.assertEqual(run.loaded, [])

    def test_uncaught_blocked_import_reports_child_stderr(self) -> None:
        """验证子进程中未捕获的受限导入会使父进程抛出 RuntimeError，且消息包含 ImportError 与模块名。"""
        with self.assertRaises(RuntimeError) as caught:
            run_ui_free("import Script.Settle")
        self.assertIn("ImportError", str(caught.exception))
        self.assertIn("Script.Settle", str(caught.exception))
