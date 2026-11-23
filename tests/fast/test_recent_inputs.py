# -*- coding: UTF-8 -*-
"""
玩家最近的输入（log.inputs）与界面输入历史（view.input_cache）
==============================================================
- 选行动阶段输入的非空指令在行动开始前写入当前写缓冲区，空输入被忽略，一步结束后留在 GameState 中。
- 选行动阶段连续输入超出 INPUTS_MAX 条时，GameState 中只保留最新的 INPUTS_MAX 条。
- 结算阶段接收的输入立即写入当前写缓冲区，同一步之后的读取马上可见，并在一步结束后留在 GameState 中。
- 一步之外暂存的输入在读档（cause 为 "load"）换入 GameState 时清空，新游戏换入时保留到下一个行动开始。
- kernel_state.write 写出的存档包含暂存输入，内核的 core.state() 本身不变。
- flow_handle.order_deal("str") 规范化纯数字返回值，同时把原始输入交给 orders.accept 暂存。
- 前一指令的前提读取 GameState 的 log.inputs，不受界面输入历史 view.input_cache 影响。
- log.inputs 随 kernel_state 编解码完整往返。
- 读档后 log.inputs 换成存档时的输入（含存档时的暂存输入），读档前的输入不保留，view.input_cache 不变。
存档写在临时目录里（index.SAVE_DIR 换成它）。
"""

import json
import tempfile
from unittest import mock

from Script.Core import constant, constant_promise, flow_handle, io_init
from Script.Core import save_handle
from Script.Design import handle_premise
from Script.Kernel import core
from Script.Modules.domains import country, history
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import index, kernel_state
from Script.Modules.tk_ui import orders
from Script.Protocol import ScriptedUiPort, script
from Script.UI.Moudle import draw, view
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.kernel_toys import KernelTestCase, Toy, flag, game

SLOT = "recent_inputs"
""" 测试用的存档id """


class Quiet:
    """不画的绘制对象，代替 NormalDraw 与 LeftDraw"""

    def __init__(self) -> None:
        """初始化为空文本、0 宽度与空样式"""
        self.text = ""
        self.width = 0
        self.style = ""

    def draw(self) -> None:
        """什么也不画"""


class OrdersKernelTest(KernelTestCase):
    """玩具内核测试：验证 orders 的暂存、落盘、读档清空与存档写入"""

    def setUp(self) -> None:
        """清空待写输入，将存档目录换到临时目录，并准备玩具插件与 Work 行动"""
        super().setUp()
        self.enterContext(mock.patch.object(orders, "_unsettled", []))
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.toy = Toy()
        self.started: list[list[str]] = []

        @self.toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            self.started.append(history.inputs())
            return ()

        self.work = work

    def run_world(self, state: core.GameState) -> None:
        """
        向内核载入玩具插件、orders 与 working，并以 state 初始化内核状态
        Keyword arguments:
        state -- 起始 GameState
        """
        core.load((self.toy.module, orders, working))
        core.reset_state(state)

    def pick_typing(self, *typed: str) -> None:
        """
        注册选行动钩子：角色选行动时依次将 typed 交给 orders.accept，然后返回 3 分钟的 Work 行动
        Keyword arguments:
        typed -- 选行动期间依次输入的字符串
        """
        work = self.work

        @self.toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            for order in typed:
                orders.accept(order)
            return core.Intercept(core.new_action(work, who, 3))

    def test_pick_inputs_reach_the_start(self) -> None:
        """选行动时输入非空与空字符串，空串不记，非空输入在行动开始时可读并在步末留在 GameState"""
        self.pick_typing("12", "", "34")
        self.run_world(game(0, {"1": 0}))
        core.step()
        self.assertEqual(self.started, [["12", "34"]])
        self.assertEqual(history.inputs(core.state()), ["12", "34"])

    def test_only_the_newest_inputs_stay(self) -> None:
        """选行动时连续输入 25 条，GameState 中只保留最新的 INPUTS_MAX 条"""
        typed = [str(i) for i in range(25)]
        self.pick_typing(*typed)
        self.run_world(game(0, {"1": 0}))
        core.step()
        self.assertEqual(
            history.inputs(core.state()), typed[-history.INPUTS_MAX :]
        )

    def test_settlement_input_is_read_at_once(self) -> None:
        """结算期间接收的输入立即写入当前缓冲区，同一步内后续读取可见且步末留在 GameState"""
        reads: list[list[str]] = []

        @self.toy.event("Ask", flag("ask"))
        def ask(who: str) -> core.Effects:
            orders.accept("7")
            reads.append(history.inputs())
            return (core.StateChange(who, "ask", True, False),)

        self.run_world(game(0, {"1": 9}, {"1": {"ask": True}}))
        core.step()
        self.assertEqual(reads, [["7"]])
        self.assertEqual(history.inputs(core.state()), ["7"])

    def test_load_drops_waiting_inputs(self) -> None:
        """读档换入 GameState 时清空暂存输入，新游戏换入时保留暂存输入到下次行动开始"""
        self.pick_typing()
        self.run_world(game(0, {"1": 0}))
        orders.accept("before load")
        core.reset_state(game(0, {"1": 0}), {"cause": "load"})
        orders.accept("title")
        core.reset_state(game(0, {"1": 0}), {"cause": "new_game"})
        core.step()
        self.assertEqual(self.started, [["title"]])

    def test_save_holds_waiting_inputs(self) -> None:
        """kernel_state.write 写出的存档包含暂存输入，内核的 core.state() 保持不变"""
        self.run_world(game(0, {"1": 0}))
        kernel_data.put(history.add_inputs, ["1"])
        orders.accept("save")
        kernel_state.write(SLOT, {})
        path = index.file(SLOT, index.SAVE_FILE)
        with open(path, encoding="utf-8") as f:
            saved = kernel_state.decode(json.load(f), tagged=True)
        self.assertEqual(history.inputs(saved), ["1", "save"])
        self.assertEqual(history.inputs(core.state()), ["1"])


class RecentInputsTest(FastTestCase):
    """小世界测试：验证 order_deal 转发输入、前提读取 log.inputs、编解码与存读档"""

    def setUp(self) -> None:
        """复原小世界，清空待写输入，将存档目录换到临时目录并创建玩家角色"""
        super().setUp()
        self.enterContext(mock.patch.object(orders, "_unsettled", []))
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.world.chara(0, "博士")

    def test_order_deal_hands_inputs_to_orders(self) -> None:
        """order_deal("str") 规范化纯数字返回值，同时将原始输入交给 orders 暂存"""
        self.enterContext(mock.patch.object(io_init, "_port", io_init._port))
        self.enterContext(mock.patch.object(view, "input_cache", []))
        io_init.configure(ScriptedUiPort(script("05")))
        self.assertEqual(flow_handle.order_deal("str", print_order=False), "5")
        self.assertEqual(history.inputs(orders.settled(core.state())), ["05"])

    def test_premise_reads_game_state(self) -> None:
        """前一指令的前提读取 GameState 中的 log.inputs，不受 view.input_cache 影响"""
        kiss = str(constant.Instruct.KISS_H)
        caress = str(constant.Instruct.MAKING_OUT)
        kernel_data.put(history.add_inputs, [kiss, "0"])
        self.enterContext(mock.patch.object(view, "input_cache", [caress, "0"]))
        premise = constant_promise.Premise
        self.assertEqual(
            handle_premise.handle_premise(premise.LAST_CMD_KISS_H, 0), 1
        )
        self.assertEqual(
            handle_premise.handle_premise(premise.LAST_CMD_MAKING_OUT, 0), 0
        )

    def test_codec_round_trip(self) -> None:
        """log.inputs 随 kernel_state 编解码完整往返"""
        kernel_data.put(history.add_inputs, ["3", "确定"])
        decoded = kernel_state.decode(
            kernel_state.encode(core.state()), tagged=True
        )
        self.assertEqual(history.inputs(decoded), ["3", "确定"])

    def test_load_takes_the_saved_inputs(self) -> None:
        """读档后 log.inputs 恢复为存档时的输入（含暂存输入），读档前输入不保留且 view.input_cache 不变"""
        kernel_data.put(history.add_inputs, ["1"])
        orders.accept("save")
        save_handle.establish_save(SLOT)
        kernel_data.put(history.add_inputs, ["after save"])
        orders.accept("load")
        self.enterContext(mock.patch.object(view, "input_cache", ["ui"]))
        with (
            mock.patch.object(draw, "NormalDraw", Quiet),
            mock.patch.object(draw, "LeftDraw", Quiet),
            mock.patch.object(country, "fill", lambda: None),
        ):
            save_handle.input_load_save(SLOT)
        self.assertEqual(
            history.inputs(orders.settled(core.state())), ["1", "save"]
        )
        self.assertEqual(view.input_cache, ["ui"])
