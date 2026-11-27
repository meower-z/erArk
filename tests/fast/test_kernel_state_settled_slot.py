"""
存档状态整理槽无界面隔离与暂存输入测试
======================================
- 拦截 tk_ui 与全部界面模块的无界面子进程中，kernel_state.write 默认原样写出 core.state()；
  经 kernel_state.on_settled 登记后按登记函数写出存档且不改变 core.state()，
  全程不加载 Script.Modules.tk_ui.orders 或其他受拦截模块。
- 导入 orders 后的玩具内核中，暂存输入随存档写出而不改 core.state() 与 _unsettled；
  读档（cause 为 "load"）清空 _unsettled，再次存档时暂存输入只出现一次。
- 新游戏（cause 为 "new_game"）换入后保留 _unsettled，core.state() 无输入而写出的存档包含该暂存输入。
存档写在临时目录中（index.SAVE_DIR 换为临时目录）。
"""

import json
import tempfile
from unittest import mock

from Script.Kernel import core
from Script.Modules.domains import history
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import index, kernel_state, upgrade
from Script.Modules.tk_ui import orders
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.kernel_toys import KernelTestCase, game
from tests.ui_free_subprocess import run_ui_free

SLOT = "settled_slot"
""" OrdersSettledSaveTest 使用的测试存档 id """
TK_UI_BLOCKED_SAVE = """
import sys
import tempfile
from types import MappingProxyType
from Script.Kernel import core
from Script.Modules.domains import history
from Script.Modules.save_load import index, kernel_state
data = MappingProxyType({"note": "kept"})
core.reset_state(core.GameState(120, MappingProxyType({}), data))
with tempfile.TemporaryDirectory() as folder:
    index.SAVE_DIR = folder
    kernel_state.write("plain", {})
    plain, version = kernel_state.read("plain")
    kernel_state.on_settled(lambda game: history.with_inputs(game, ["typed"]))
    kernel_state.write("settled", {})
    settled, _ = kernel_state.read("settled")
payload["plain_is_state"] = plain == core.state()
payload["version"] = version
payload["settled_inputs"] = history.inputs(settled)
payload["state_inputs"] = history.inputs(core.state())
payload["settled_note"] = core.value(settled, None, "note")
payload["orders_loaded"] = "Script.Modules.tk_ui.orders" in sys.modules
"""
"""
在无界面子进程中以默认槽与经 on_settled 登记的函数分别读写存档，
将结果、版本、输入、全局数据及 orders 加载状态写入 payload
"""


class KernelStateWithoutTkUiTest(FastTestCase):
    """验证拦截界面与 tk_ui 模块的无界面子进程中 kernel_state 的默认写出与 on_settled 替换行为"""

    def test_write_runs_with_tk_ui_blocked(self) -> None:
        """
        拦截全部界面与 tk_ui 模块运行子进程，验证默认存档等于 core.state()、
        登记 on_settled 后按登记函数写出且未加载 orders
        """
        child = run_ui_free(TK_UI_BLOCKED_SAVE, boot=True)
        self.assertEqual(child.attempted, [])
        self.assertEqual(child.loaded, [])
        self.assertEqual(
            child.payload,
            {
                "plain_is_state": True,
                "version": upgrade.CURRENT,
                "settled_inputs": ["typed"],
                "state_inputs": [],
                "settled_note": "kept",
                "orders_loaded": False,
            },
        )


class OrdersSettledSaveTest(KernelTestCase):
    """玩具内核测试：验证导入 orders 后 kernel_state.write 通过已登记的 settled 写出暂存输入"""

    def setUp(self) -> None:
        """清空 orders._unsettled，将 index.SAVE_DIR 换到临时目录，载入 orders 与 working 并重置为空闲角色状态"""
        super().setUp()
        self.enterContext(mock.patch.object(orders, "_unsettled", []))
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        core.load((orders, working))
        core.reset_state(game(0, {"1": 0}))

    def saved_inputs(self) -> list[str]:
        """
        将当前内核状态写入 SLOT 槽位，解码写出的 save.json 并返回其中的 log.inputs
        Return arguments:
        list[str] -- 存档中解码得到的 log.inputs 列表
        """
        kernel_state.write(SLOT, {})
        with open(index.file(SLOT, index.SAVE_FILE), encoding="utf-8") as f:
            saved = kernel_state.decode(json.load(f), tagged=True)
        return history.inputs(saved)

    def test_save_load_save_keeps_waiting_input_once(self) -> None:
        """存档包含暂存输入且不改 core.state() 与 _unsettled；读档清空 _unsettled，再次存档时暂存输入只出现一次"""
        kernel_data.put(history.add_inputs, ["1"])
        orders.accept("waiting")
        self.assertEqual(self.saved_inputs(), ["1", "waiting"])
        self.assertEqual(history.inputs(core.state()), ["1"])
        self.assertEqual(orders._unsettled, ["waiting"])
        saved, _ = kernel_state.read(SLOT)
        assert saved is not None
        core.reset_state(saved, {"cause": "load"})
        self.assertEqual(orders._unsettled, [])
        self.assertEqual(history.inputs(core.state()), ["1", "waiting"])
        self.assertEqual(self.saved_inputs(), ["1", "waiting"])

    def test_new_game_keeps_waiting_input_for_save(self) -> None:
        """新游戏换入（cause 为 "new_game"）后保留 _unsettled，core.state() 无输入而写出的存档包含该暂存输入"""
        orders.accept("title")
        core.reset_state(game(0, {"1": 0}), {"cause": "new_game"})
        self.assertEqual(orders._unsettled, ["title"])
        self.assertEqual(history.inputs(core.state()), [])
        self.assertEqual(self.saved_inputs(), ["title"])
