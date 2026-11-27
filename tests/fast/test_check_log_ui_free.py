"""
静态检查日志无界面与开关测试
============================
本测试模块在独立子进程中验证静态检查日志的无界面运行与自检开关的按需导入。
CheckLogUiFreeTest 在启用默认导入拦截的子进程中运行 check_log，验证其未触碰受拦截模块并写出含末尾 10 条
输入的日志。StaticCheckSwitchTest 在仅拦截 Script.Test 的子进程中运行 save_handle.repair_installed，
验证系统设置第 14 项（游戏状态自检开关）关闭时不加载 Script.Test、开启时尝试导入该包。
"""

from typing import Any, cast

from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

CHILD_LOG = """
import os
import tempfile

home = os.getcwd()
with tempfile.TemporaryDirectory() as folder:
    os.chdir(folder)
    try:
        from Script.Core import input_cache
        from Script.Test.Static_Check import check_log
        from Script.Test.Static_Check.check_registry import CheckFailure
        from tests import kernel_data
        from tests.world import start_time

        kernel_data.reset_clock(start_time(), {})
        input_cache.input_cache[:] = [str(i) for i in range(12)]
        payload["recent"] = check_log._build_recent_input_text()
        failure = CheckFailure("UIFREE-01", "ui-free", "failed", [])
        payload["written"] = check_log.write_error_log([failure])
        with open(check_log.LOG_PATH, encoding="utf-8") as log:
            payload["log"] = log.read().splitlines()
    finally:
        os.chdir(home)
"""
"""在无界面子进程切入临时目录后再导入模块、写 12 条输入并调用 check_log.write_error_log 回传结果的片段。"""
CHILD_SWITCH = """
import sys
from Script.Config import normal_config
from Script.Core import flow_handle, save_handle

settings = normal_config.system_setting.base_setting
settings[14] = 0
save_handle.repair_installed()
payload["off"] = sorted(name for name in sys.modules if name.startswith("Script.Test"))
settings[14] = 1
try:
    save_handle.repair_installed()
except ImportError as error:
    payload["on"] = error.name
"""
"""在拦截 Script.Test 的子进程中分别关闭与开启系统设置第 14 项，并调用 save_handle.repair_installed 的代码片段。"""


class CheckLogUiFreeTest(FastTestCase):
    """check_log 的无界面子进程运行测试。"""

    @classmethod
    def setUpClass(cls) -> None:
        """在默认拦截规则的无界面子进程中执行 CHILD_LOG 并缓存结果。子进程失败时抛出 RuntimeError。"""
        super().setUpClass()
        cls.child = run_ui_free(CHILD_LOG, boot=True)
        cls.payload = cast(dict[str, Any], cls.child.payload)

    def test_no_blocked_module_loaded(self) -> None:
        """断言子进程未加载也未尝试导入任何受拦截模块。"""
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_log_entry_carries_last_ten_inputs(self) -> None:
        """断言最近输入文本取末尾 10 条，write_error_log 返回 True，且日志包含该输入行与 UIFREE-01 失败行。"""
        recent = str([str(i) for i in range(2, 12)])
        self.assertEqual(self.payload["recent"], recent)
        self.assertTrue(self.payload["written"])
        log = self.payload["log"]
        self.assertIn(f"最近输入(input_cache 末尾10条): {recent}", log)
        self.assertTrue(
            any("[UIFREE-01] ui-free: failed" in line for line in log)
        )


class StaticCheckSwitchTest(FastTestCase):
    """系统设置第 14 项（游戏状态自检开关）控制 Script.Test 按需导入的子进程测试。"""

    @classmethod
    def setUpClass(cls) -> None:
        """在仅拦截 Script.Test 的子进程中执行 CHILD_SWITCH 并缓存结果。子进程失败时抛出 RuntimeError。"""
        super().setUpClass()
        cls.child = run_ui_free(
            CHILD_SWITCH,
            boot=True,
            blocked=frozenset({"Script.Test"}),
        )
        cls.payload = cast(dict[str, Any], cls.child.payload)

    def test_switch_off_leaves_package_unloaded(self) -> None:
        """断言游戏状态自检开关关闭时未加载任何 Script.Test 模块，且子进程结束时受拦截加载列表为空。"""
        self.assertEqual(self.payload["off"], [])
        self.assertEqual(self.child.loaded, [])

    def test_switch_on_imports_package(self) -> None:
        """断言游戏状态自检开关开启时触发对 Script.Test 的导入尝试，且唯一被拦截的模块为 Script.Test。"""
        self.assertEqual(self.payload["on"], "Script.Test")
        self.assertEqual(self.child.attempted, ["Script.Test"])
