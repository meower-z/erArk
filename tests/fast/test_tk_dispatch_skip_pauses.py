"""Tk 前端事件分发测试：在独立子进程中验证 TkFrontend._dispatch 忽略 SkipPauses 事件而不干扰输入门控状态。"""

import os
import subprocess
import sys

from tests.fast.base import FastTestCase
from tests.world import ROOT

CHILD = """
from types import SimpleNamespace as NS
from Script.Frontend.Tk.app import TkFrontend
from Script.Frontend.Tk.gate import InputGate
from Script.Protocol import Pause, SkipPauses
frontend = TkFrontend.__new__(TkFrontend)
frontend.gate, frontend._arm_id = InputGate(1), None
root = NS(after_idle=lambda callback: "idle", after_cancel=lambda arm: None)
frontend.window = NS(root=root)
frontend.gate.right_click()
frontend._dispatch(SkipPauses("s", 1, False))
gate = frontend.gate
print(gate.request, gate.skip_requested, gate.offer(Pause("s", 2, 1, 1)))
"""
"""在无窗口环境下构造 TkFrontend 并向 `_dispatch` 分发 `SkipPauses` 事件后输出输入门控状态的子进程脚本。"""


class TkSkipPausesDispatchTest(FastTestCase):
    """验证 TkFrontend 分发 SkipPauses 事件时将其忽略并保持输入门控状态不变。"""

    def test_skip_pauses_event_keeps_queued_right_click_skip(self) -> None:
        """
        运行子进程脚本 `CHILD`，
        断言分发 `SkipPauses` 后无挂起请求、右键跳过预排保留且随后的可跳过暂停立即返回跳过应答。
        """
        result = subprocess.run(
            [sys.executable, "-c", CHILD],
            cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
            capture_output=True,
            encoding="utf-8",
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        skipped = "Continue(controller_epoch=1, request_id=1, skip_pauses=True)"
        last = result.stdout.splitlines()[-1]
        self.assertEqual(last, f"None True {skipped}")
