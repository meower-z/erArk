# -*- coding: UTF-8 -*-
"""
按编号清除命令的测试
====================
py_cmd.clr_cmd 收到命令编号时，只解除这些编号的绑定，
并向端口发出列出这些编号的 ClearButtonsOp 操作，其余编号的绑定保留。
"""

from unittest import mock

from Script.Core import flow_handle, io_init, py_cmd
from Script.Protocol import (
    ClearButtonsOp,
    RenderChunk,
    ScriptedUiPort,
    default_first_option,
)
from tests.fast.base import FastTestCase


class ClearCmdByNumberTest(FastTestCase):
    """clr_cmd 按编号清除：只动给出的编号"""

    def test_clear_one_of_two_commands(self) -> None:
        """绑定 "5" 与 "6" 后清除 "5"：只有 "5" 解除绑定，清除消息只列出 "5" """
        port = ScriptedUiPort(default_first_option())
        with mock.patch.dict(
            flow_handle.cmd_map, clear=True
        ), mock.patch.object(io_init, "_port", port):
            py_cmd.bind_cmd("5", flow_handle.null_func)
            py_cmd.bind_cmd("6", flow_handle.null_func)
            py_cmd.clr_cmd("5")
            self.assertNotIn("5", flow_handle.cmd_map)
            self.assertIn("6", flow_handle.cmd_map)
        port.finish("normal")
        cleared = [
            op.command_ids
            for event in port.events
            if isinstance(event, RenderChunk)
            for op in event.ops
            if isinstance(op, ClearButtonsOp)
        ]
        self.assertEqual(cleared, [("5",)])
