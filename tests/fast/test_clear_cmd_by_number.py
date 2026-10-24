# -*- coding: UTF-8 -*-
"""
按编号清除命令的测试（Tk 模式）
==============================
py_cmd.clr_cmd 收到命令编号时，只解除这些编号的绑定，
并向 Tk 前端的输出队列发出列出这些编号的 clearcmd_cmd 消息；其他编号的绑定保留。
"""

import json
from unittest import mock

from Script.Core import flow_handle, io_init, py_cmd
from tests.fast.base import FastTestCase


class ClearCmdByNumberTest(FastTestCase):
  """clr_cmd 按编号清除：只动给出的编号"""

  def test_clear_one_of_two_commands(self):
    """绑定 "5" 与 "6" 后清除 "5"：只有 "5" 解除绑定，清除消息只列出 "5" """
    messages = []
    with mock.patch.dict(flow_handle.cmd_map, clear=True), mock.patch.object(
        io_init, "put_queue", messages.append
    ):
      py_cmd.bind_cmd("5", flow_handle.null_func)
      py_cmd.bind_cmd("6", flow_handle.null_func)
      py_cmd.clr_cmd("5")
      self.assertNotIn("5", flow_handle.cmd_map)
      self.assertIn("6", flow_handle.cmd_map)
    clear_messages = [
        json.loads(message)["clearcmd_cmd"]
        for message in messages
        if "clearcmd_cmd" in json.loads(message)
    ]
    self.assertEqual(clear_messages, [["5"]])
