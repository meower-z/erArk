# -*- coding: UTF-8 -*-
"""
玩家选择期间的写入缓冲与打断记录（player_pick.drafting）
========================================================
- 选择块写入 GameState 数据或计划打断且未定下行动时，交回一个 0 分钟的 Edit。
- 块内定下行为时，写入与打断附到该行为上；其他行动抛 TypeError。
- Back 与异常不留下写入或打断，内核状态保持不变。
- 选择块内开启新周目会丢弃块内写入，退出块时不定下行动。
- 指令判定失败换成失败行为时，开始门丢弃选择期间的写入与打断。
"""

import sys
from collections.abc import Mapping
from types import SimpleNamespace
from unittest import mock

from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import inventory
from Script.Modules.gameplay_resolution import (
    actions,
    edits,
    intent,
    plan_queue,
    working,
)
from Script.Modules.save_load import kernel_state
from Script.Modules.tk_ui import player_pick
from Script.UI.Moudle import view
from tests.fast.base import FastTestCase

ITEM = 99
""" 测试写入干员背包的道具 id """


class PickCase(FastTestCase):
    """处于玩家选择上下文中、含玩家与一名干员的测试基类"""

    def setUp(self) -> None:
        """建出玩家与 1 号干员，进入 player_pick.picking 上下文并记下基线"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        self.enterContext(player_pick.picking())
        self.before = core.state()
        self.pending = plan_queue.mark()

    def write(self) -> None:
        """执行一次 GameState 写入并计划一次打断"""
        inventory.set_item(1, ITEM, 3)
        plan_queue.interrupt(1)

    def assert_untouched(self) -> None:
        """断言内核状态、待提交打断数与选择缓冲区都与进入选择块前相同"""
        self.assertIs(core.state(), self.before)
        self.assertEqual(plan_queue.mark(), self.pending)
        self.assertFalse(working.picking())


class DraftingTest(PickCase):
    """玩家选择中 player_pick.drafting 的行为测试"""

    def test_changed_state_commits_one_edit(self) -> None:
        """有写入与打断而未定下行动时，生成一个同时携带两者的 0 分钟 Edit"""
        with self.assertRaises(player_pick.Chosen) as raised:
            with player_pick.drafting("test"):
                self.write()
                self.assertEqual(inventory.items(1).get(ITEM), 3)
        act = raised.exception.action
        self.assertEqual(
            (act.action_id, act.who, act.duration), (edits.EDIT, "0", 0)
        )
        data = act.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["interrupts"], ("1",))
        effects = data["effects"]
        assert isinstance(effects, tuple)
        self.assertEqual(len(effects), 1)
        self.assertNotIn("draft", data)
        self.assert_untouched()

    def test_look_only_commits_nothing(self) -> None:
        """仅读取数据与修改界面状态时，不生成 Edit"""
        with player_pick.drafting("test"):
            inventory.items(1)
            view.now_panel_id = 5
        self.assertEqual(view.now_panel_id, 5)
        self.assert_untouched()

    def test_back_leaves_nothing(self) -> None:
        """写入并计划打断后调用 Back，两者都被丢弃且状态不变"""
        with self.assertRaises(player_pick.Back):
            with player_pick.drafting("test"):
                self.write()
                player_pick.back()
        self.assert_untouched()
        self.assertIsNone(inventory.items(1).get(ITEM))

    def test_error_leaves_nothing(self) -> None:
        """写入并计划打断后抛出异常，异常向外传播且两者都被丢弃"""
        with self.assertRaises(ZeroDivisionError):
            with player_pick.drafting("test"):
                self.write()
                _ = 1 / 0
        self.assert_untouched()

    def test_chosen_behavior_carries_writes(self) -> None:
        """写入并计划打断后定下行为，行为意图同时携带写入与打断"""
        with self.assertRaises(player_pick.Chosen) as raised:
            with player_pick.drafting("test"):
                self.write()
                player_pick.choose("wait", 5)
        data = raised.exception.action.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["interrupts"], ("1",))
        effects = data["effects"]
        assert isinstance(effects, tuple)
        self.assertEqual(len(effects), 1)
        self.assertNotIn("draft", data)
        self.assert_untouched()

    def test_nested_part_joins_outer(self) -> None:
        """嵌套选择块并入外层，仅在外层退出时生成一个 Edit"""
        with self.assertRaises(player_pick.Chosen) as raised:
            with player_pick.drafting("outer"):
                with player_pick.drafting("inner"):
                    self.write()
                self.assertTrue(working.picking())
        data = raised.exception.action.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["origin"], "outer")
        self.assert_untouched()

    def test_other_action_with_writes_raises(self) -> None:
        """有写入时定下既非 Edit 又无 behavior_id 的行动，抛 TypeError"""
        other = core.Action("0", core.idle.name, None, 0, 1)
        with self.assertRaises(TypeError):
            with player_pick.drafting("test"):
                self.write()
                raise player_pick.Chosen(other)
        self.assert_untouched()

    def test_outside_pick_runs_plain(self) -> None:
        """不在玩家选择上下文中时，drafting 直接运行块且不打开选择缓冲区"""
        player_pick._in_pick = False
        with player_pick.drafting("test"):
            self.assertFalse(working.picking())


class ResetInPickTest(PickCase):
    """玩家选择块内启动新周目的测试"""

    def setUp(self) -> None:
        """用计数且可配置失败的替身替换 new_round 面板，并加载内核模块"""
        super().setUp()
        self.broken = False
        self.setups = 0

        def setup(inherit: object) -> None:
            self.setups += 1
            if self.broken:
                raise RuntimeError("setup")

        panel = SimpleNamespace(setup=setup)
        self.enterContext(
            mock.patch.dict(sys.modules, {"Script.UI.Panel.new_round": panel})
        )
        core.load(load_order.LOAD_ORDER)
        self.before = core.state()

    def test_failed_reset_keeps_state(self) -> None:
        """选择块内启动新周目失败时，异常传播且内核状态与写入、打断不变"""
        self.broken = True
        with self.assertRaises(RuntimeError):
            with player_pick.drafting("test"):
                self.write()
                kernel_state.new_round({})
        self.assertEqual(self.setups, 1)
        self.assert_untouched()

    def test_reset_drops_pick_writes(self) -> None:
        """选择块内成功启动新周目后，此前的写入与打断被丢弃且不生成 Edit"""
        with mock.patch.object(actions, "project", lambda new: new):
            with player_pick.drafting("test"):
                self.write()
                kernel_state.new_round({})
                self.assertFalse(working.picking())
        self.assertEqual(self.setups, 1)
        self.assertIsNot(core.state(), self.before)
        self.assertEqual(plan_queue.mark(), 0)
        self.assertIsNone(inventory.items(1).get(ITEM))


class IntentWritesTest(FastTestCase):
    """指令判定失败时开始门丢弃选择写入的测试"""

    def test_failed_judge_drops_writes(self) -> None:
        """_judged 换上失败行为时，不带入原意图的 effects 与 interrupts"""
        from Script.Modules.gameplay_resolution import start_gate
        from Script.System.Instruct_System import handle_instruct

        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        chosen = intent.Intent(behavior_id="kiss", minutes=5, target=1)
        chosen["judge"] = "亲吻"
        chosen["effects"] = [{"who": "1", "key": "k", "old": 1, "new": 2}]
        chosen["interrupts"] = ["1"]
        act = intent.behavior_action(0, chosen)
        with mock.patch.object(
            handle_instruct, "_judged_behavior_id", lambda *a: "kiss_fail"
        ), mock.patch.object(
            handle_instruct, "_instruct_duration", lambda b, d: 1
        ):
            data = act.action_data
            assert isinstance(data, Mapping)
            judged = start_gate._judged(act, 0, data)
        judged_data = judged.action_data
        assert isinstance(judged_data, Mapping)
        self.assertNotIn("effects", judged_data)
        self.assertNotIn("interrupts", judged_data)
