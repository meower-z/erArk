# -*- coding: UTF-8 -*-
"""
面板注册无界面与选择草稿测试
============================
AddPanelUiFreeTest 在无界面子进程中验证 handle_panel.add_panel 无需界面模块即可注册与运行面板。
AddPanelDraftingTest 在本进程的玩家选择期间验证普通面板的选择草稿行为与 UNDRAFTED 面板的直接运行行为。
"""

from collections.abc import Mapping
from unittest import mock

from Script.Core import constant
from Script.Design import handle_panel
from Script.Kernel import core
from Script.Modules.domains import inventory
from Script.Modules.gameplay_resolution import edits, plan_queue, working
from Script.Modules.tk_ui import player_pick
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

PANEL = 9001
""" AddPanelDraftingTest 注册测试面板时使用的自定义面板 id，不与 constant.Panel 成员冲突。 """
ITEM = 99
""" AddPanelDraftingTest 读写角色 1 背包条目时使用的测试物品 id。 """
RUNS = """
payload["error"] = None
try:
    from Script.Core import constant
    from Script.Design import handle_panel

    calls = []

    @handle_panel.add_panel(9001)
    def panel(first, *, second):
        calls.append([first, second])
        return first + second

    @handle_panel.add_panel(9002)
    def broken():
        raise ValueError("broken")

    payload["result"] = panel(1, second=2)
    payload["calls"] = calls
    payload["registered"] = constant.panel_data[9001] is panel
    try:
        broken()
    except ValueError as error:
        payload["raised"] = repr(error)
except ImportError as error:
    payload["error"] = repr(error)
"""
""" 在无界面子进程中导入 constant 与 handle_panel，注册并调用测试面板，向 payload 记录结果、异常与导入错误。 """


class AddPanelUiFreeTest(FastTestCase):
    """无界面子进程中的 handle_panel.add_panel 注册、调用与模块隔离测试。"""

    child: ChildRun

    @classmethod
    def setUpClass(cls) -> None:
        """调用父类类级准备并经 run_ui_free 执行 RUNS，将结果保存到 cls.child。"""
        super().setUpClass()
        cls.child = run_ui_free(RUNS)

    def test_panel_runs_without_ui(self) -> None:
        """验证无界面子进程未记录导入错误，且完成面板注册、传参返回与异常传播。"""
        self.assertIsNone(self.child.payload["error"])
        self.assertEqual(self.child.payload["result"], 3)
        self.assertEqual(self.child.payload["calls"], [[1, 2]])
        self.assertIs(self.child.payload["registered"], True)
        self.assertEqual(self.child.payload["raised"], "ValueError('broken')")

    def test_panel_touches_no_ui_module(self) -> None:
        """验证无界面子进程未尝试导入也未加载任何受拦截模块。"""
        self.assertEqual(self.child.attempted, [])
        self.assertEqual(self.child.loaded, [])


class AddPanelDraftingTest(FastTestCase):
    """本进程玩家选择期间的 add_panel 选择草稿与 UNDRAFTED 面板行为测试。"""

    def setUp(self) -> None:
        """
        创建角色 0 与角色 1，隔离 constant.panel_data，并进入 player_pick.picking() 上下文。
        记录当前内核状态与计划队列打断标记，供断言核对状态未变动。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        self.enterContext(mock.patch.dict(constant.panel_data))
        self.enterContext(player_pick.picking())
        self.before = core.state()
        self.pending = plan_queue.mark()

    def assert_untouched(self) -> None:
        """断言内核状态对象未变、计划队列打断标记未变且选择缓冲区未打开。"""
        self.assertIs(core.state(), self.before)
        self.assertEqual(plan_queue.mark(), self.pending)
        self.assertFalse(working.picking())

    def test_drafted_panel_commits_edit(self) -> None:
        """验证带写入和打断的普通面板退出时抛出含来源与打断的 0 分钟 Edit，并保持原状态不变。"""
        seen = []

        @handle_panel.add_panel(PANEL)
        def panel(count: int, *, note: str) -> None:
            seen.append((count, note, working.picking()))
            inventory.set_item(1, ITEM, count)
            plan_queue.interrupt(1)

        self.assertIs(constant.panel_data[PANEL], panel)
        with self.assertRaises(player_pick.Chosen) as raised:
            panel(3, note="x")
        self.assertEqual(seen, [(3, "x", True)])
        act = raised.exception.action
        self.assertEqual((act.action_id, act.duration), (edits.EDIT, 0))
        data = act.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["origin"], f"panel {PANEL}")
        self.assertEqual(data["interrupts"], ("1",))
        self.assert_untouched()

    def test_drafted_panel_returns_value(self) -> None:
        """验证只读普通面板在选择缓冲区内执行并直接返回值，退出后不改动原状态。"""

        @handle_panel.add_panel(PANEL)
        def panel() -> tuple[bool, int | None]:
            return working.picking(), inventory.items(1).get(ITEM)

        self.assertEqual(panel(), (True, None))
        self.assert_untouched()

    def test_drafted_panel_error_drops_writes(self) -> None:
        """验证普通面板抛出 ZeroDivisionError 时向外传播异常，并丢弃本次写入与计划打断。"""

        @handle_panel.add_panel(PANEL)
        def panel() -> None:
            inventory.set_item(1, ITEM, 3)
            plan_queue.interrupt(1)
            raise ZeroDivisionError

        with self.assertRaises(ZeroDivisionError):
            panel()
        self.assert_untouched()
        self.assertIsNone(inventory.items(1).get(ITEM))

    def test_drafted_panel_back_drops_writes(self) -> None:
        """验证普通面板调用 player_pick.back() 时向外传播 Back，并丢弃本次写入。"""

        @handle_panel.add_panel(PANEL)
        def panel() -> None:
            inventory.set_item(1, ITEM, 3)
            player_pick.back()

        with self.assertRaises(player_pick.Back):
            panel()
        self.assert_untouched()

    def test_nested_panel_joins_outer(self) -> None:
        """验证嵌套面板将内层写入并入外层草稿，并由外层抛出以 PANEL 为来源的 Chosen。"""

        @handle_panel.add_panel(PANEL + 1)
        def inner() -> None:
            inventory.set_item(1, ITEM, 3)

        @handle_panel.add_panel(PANEL)
        def outer() -> None:
            inner()
            self.assertTrue(working.picking())

        with self.assertRaises(player_pick.Chosen) as raised:
            outer()
        data = raised.exception.action.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["origin"], f"panel {PANEL}")
        self.assert_untouched()

    def test_undrafted_panel_runs_plain(self) -> None:
        """验证 IN_SCENE 面板登记到 panel_data，且调用时不开选择缓冲区并直接返回值。"""
        seen = []

        @handle_panel.add_panel(constant.Panel.IN_SCENE)
        def panel(value: int) -> int:
            seen.append(working.picking())
            return value * 2

        self.assertEqual(panel(4), 8)
        self.assertEqual(seen, [False])
        self.assertIs(constant.panel_data[constant.Panel.IN_SCENE], panel)
