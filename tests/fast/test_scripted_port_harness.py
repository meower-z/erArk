"""
脚本化端口测试夹具验证
======================
检验 default_first_option、ScriptedUiPort 即时监听与回调关闭顺序，以及 tests.world 延迟导入游戏模块。
同时检验 MinimalWorld.reset 与 PlayerInput 经 ScriptedUiPort 驱动真实输入输出流程的行为。
"""

import subprocess
import sys
from unittest import mock

from Script.Core import flow_handle, io_init
from Script.Modules.tk_ui import orders
from Script.Protocol import (
    BackendEvent,
    Continue,
    Exit,
    RenderChunk,
    ScriptedUiPort,
    SessionCancelled,
    TextOp,
    default_first_option,
)
from Script.Protocol._core import MAX_CHUNK_BYTES
from Script.UI.Moudle import view
from tests import world
from tests.fast.base import FastTestCase


def _hooks() -> dict[str, object]:
    """
    收集 io_init 与 flow_handle 上 8 个关键输入输出函数的当前对象引用。
    Keyword arguments:
    无
    Return arguments:
    dict[str, object] -- 以函数名为键的当前函数对象字典
    """
    return {
        "era_print": io_init.era_print,
        "io_print_cmd": io_init.io_print_cmd,
        "io_print_image_cmd": io_init.io_print_image_cmd,
        "io_clear_cmd": io_init.io_clear_cmd,
        "clear_screen": io_init.clear_screen,
        "askfor_all": flow_handle.askfor_all,
        "askfor_wait": flow_handle.askfor_wait,
        "order_deal": flow_handle.order_deal,
    }


def _closing_port(
    trigger: type[Exit | RenderChunk],
) -> tuple[ScriptedUiPort, list[BackendEvent]]:
    """
    构造带记录型监听器的 ScriptedUiPort，监听器在收到 trigger 类型事件时调用 port.close()。
    Keyword arguments:
    trigger -- 触发关闭端口的事件类型（Exit 或 RenderChunk）
    Return arguments:
    tuple[ScriptedUiPort, list[BackendEvent]] -- 创建的端口实例与已收事件列表
    """
    seen: list[BackendEvent] = []

    def on_event(event: BackendEvent) -> None:
        """记录收到的后端事件，并在收到 trigger 类型的事件时调用 port.close()。"""
        seen.append(event)
        if isinstance(event, trigger):
            port.close()

    port = ScriptedUiPort(default_first_option(), listener=on_event)
    return port, seen


class DefaultFirstOptionTest(FastTestCase):
    """检验 default_first_option、ScriptedUiPort 即时监听及回调内关闭端口的行为。"""

    def test_answers_each_request_kind(self) -> None:
        """校验 default_first_option 应答非空选单、暂停与允许空串的文本请求，并对空选单抛 ValueError。"""
        port = ScriptedUiPort(default_first_option())
        self.assertEqual(port.choose(("甲", "乙")).raw_value, "甲")
        self.assertRaises(ValueError, port.choose, ())
        self.assertIsInstance(port.pause(), Continue)
        self.assertEqual(port.input_text(10, allow_empty=True).text, "")

    def test_listener_sees_each_op_at_once(self) -> None:
        """校验配置 listener 后 emit_op 立即刷出单条 RenderChunk 给回调，且 port.events 保持为空。"""
        seen: list[object] = []
        port = ScriptedUiPort(default_first_option(), listener=seen.append)
        port.emit_op(TextOp("一"))
        self.assertEqual(seen, [RenderChunk("scripted", 1, (TextOp("一"),))])
        self.assertEqual(port.events, [])

    def test_listener_may_close_on_exit(self) -> None:
        """
        校验 listener 收到取消 Exit 时调用 port.close() 幂等返回且仅记录一次 Exit。
        同时校验关闭后的端口调用 flush 抛出 SessionCancelled。
        """
        port, seen = _closing_port(Exit)
        port.close()
        self.assertEqual(seen, [Exit("scripted", 1, "cancelled")])
        self.assertRaises(SessionCancelled, port.flush)

    def test_listener_may_close_on_finish(self) -> None:
        """
        校验 finish 交付 normal 或 error 结束事件时，listener 调用 port.close() 仅保留该次 Exit。
        同时校验结束后的端口调用 flush 抛出 SessionCancelled。
        """
        for reason in ("normal", "error"):
            with self.subTest(reason=reason):
                port, seen = _closing_port(Exit)
                port.finish(reason)
                self.assertEqual(seen, [Exit("scripted", 1, reason)])
                self.assertRaises(SessionCancelled, port.flush)

    def test_listener_may_close_on_large_chunk(self) -> None:
        """
        校验单条达到分块字节上限的渲染操作触发刷出时，listener 调用 port.close() 后 emit_op 正常返回。
        同时校验 listener 按序收到该 RenderChunk 与取消 Exit。
        """
        port, seen = _closing_port(RenderChunk)
        op = TextOp("x" * MAX_CHUNK_BYTES)
        port.emit_op(op)
        self.assertEqual(
            seen,
            [
                RenderChunk("scripted", 1, (op,)),
                Exit("scripted", 2, "cancelled"),
            ],
        )


class WorldImportTest(FastTestCase):
    """检验导入 tests.world 时不预载 Script 下的游戏模块。"""

    def test_world_loads_no_game_module(self) -> None:
        """校验在独立子进程中导入 tests.world 后，sys.modules 中不含顶层包为 Script 的模块。"""
        code = (
            "import sys, tests.world; "
            "print(sorted(m for m in sys.modules if m.split('.')[0] == 'Script'))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=world.ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "[]")


class MinimalWorldPortTest(FastTestCase):
    """检验 MinimalWorld.reset 安装丢弃事件的脚本端口、隔离会话状态及空选项快速失败的行为。"""

    def setUp(self) -> None:
        """复原小世界并隔离 orders._unsettled 与 view.input_cache。"""
        super().setUp()
        self.enterContext(mock.patch.object(orders, "_unsettled", []))
        self.enterContext(mock.patch.object(view, "input_cache", []))

    def test_reset_answers_through_real_flow(self) -> None:
        """
        校验 reset 保持关键输入输出函数不变并安装 ScriptedUiPort。
        同时校验 askfor_all 与 askfor_wait 经端口应答返回预期结果且 port.events 保持为空。
        """
        before = _hooks()
        self.world.reset()
        self.assertEqual(_hooks(), before)
        port = io_init._port
        self.assertIsInstance(port, ScriptedUiPort)
        self.assertEqual(flow_handle.askfor_all(["甲", "乙"]), "甲")
        self.assertIsNone(flow_handle.askfor_wait())
        self.assertEqual(port.events, [])

    def test_reset_drops_session_state(self) -> None:
        """校验 reset 安装全新端口、清空 cmd_map，且新端口关闭跳过暂停并处于开放状态。"""
        old = io_init._port
        io_init.set_skip_pauses(True)
        flow_handle.bind_cmd("leak", lambda: None)
        old.close()
        self.world.reset()
        self.assertIsNot(io_init._port, old)
        self.assertNotIn("leak", flow_handle.cmd_map)
        self.assertEqual(io_init._port.pause(), Continue(1, 1))

    def test_empty_choice_fails_fast(self) -> None:
        """校验向 askfor_all 传入空选项列表时立即抛出 ValueError。"""
        self.assertRaises(ValueError, flow_handle.askfor_all, [])


class PlayerInputTest(FastTestCase):
    """检验 PlayerInput 通过 ScriptedUiPort 监听输出、应答输入与按关键词捕获文本的行为。"""

    def setUp(self) -> None:
        """隔离端口、输入暂存、输入历史与命令映射，记录初始函数引用并安装新的 PlayerInput 实例。"""
        super().setUp()
        self.enterContext(mock.patch.object(io_init, "_port", io_init._port))
        self.enterContext(mock.patch.object(orders, "_unsettled", []))
        self.enterContext(mock.patch.object(view, "input_cache", []))
        self.enterContext(mock.patch.dict(flow_handle.cmd_map, clear=True))
        self.before = _hooks()
        self.player = world.PlayerInput()
        self.player.install()

    def test_install_keeps_real_functions(self) -> None:
        """校验 PlayerInput.install 保持 io_init 与 flow_handle 函数不变，并安装 ScriptedUiPort。"""
        self.assertEqual(_hooks(), self.before)
        self.assertIsInstance(io_init._port, ScriptedUiPort)

    def test_tracks_text_and_buttons(self) -> None:
        """校验 PlayerInput 即时记录非空文本与按钮，并在清除单个命令或清屏时同步移除按钮。"""
        io_init.era_print("开场白")
        io_init.era_print("   ")
        flow_handle.print_cmd("[确定]", "ok")
        flow_handle.print_cmd("[返回]", "back")
        self.assertEqual(self.player.screen, ["开场白"])
        self.assertEqual(
            self.player.buttons, [("[确定]", "ok"), ("[返回]", "back")]
        )
        flow_handle.cmd_clear("ok")
        self.assertEqual(self.player.buttons, [("[返回]", "back")])
        io_init.clear_screen()
        self.assertEqual(self.player.buttons, [])

    def test_press_runs_bound_command(self) -> None:
        """校验安排 press 后 askfor_all 返回匹配按钮编号、执行其绑定命令，并清空当前按钮与计划。"""
        ran: list[str] = []
        flow_handle.print_cmd("[确定]", "ok", lambda: ran.append("ok"))
        flow_handle.print_cmd("[返回]", "back")
        self.player.press("确定")
        self.assertEqual(flow_handle.askfor_all(["ok", "back"]), "ok")
        self.assertEqual(ran, ["ok"])
        self.assertEqual(self.player.buttons, [])
        self.player.check_done()

    def test_typed_text_answers_text_request(self) -> None:
        """校验 askfor_wait 不消费已安排的 type 输入，由随后的 askfor_str 消费并返回该文本。"""
        self.player.type("多克特")
        flow_handle.askfor_wait()
        self.assertEqual(self.player.planned, [("type", "多克特")])
        self.assertEqual(flow_handle.askfor_str(), "多克特")
        self.player.check_done()

    def test_unplanned_choice_raises(self) -> None:
        """校验未安排输入时调用 askfor_all 抛出 UnplannedInput。"""
        flow_handle.print_cmd("[返回]", "back")
        with self.assertRaises(world.UnplannedInput):
            flow_handle.askfor_all(["back"])

    def test_capture_keeps_keyword_text(self) -> None:
        """校验 capture 按关键词或全量收集文本且不受 screen 上限截断，同时保持输入输出函数不变。"""
        woken = self.player.capture("吵醒")
        everything = self.player.capture()
        io_init.era_print("她被吵醒了")
        for line in range(self.player.SCREEN_LIMIT):
            io_init.era_print(f"第{line}行")
        self.assertEqual(woken, ["她被吵醒了"])
        self.assertEqual(len(everything), self.player.SCREEN_LIMIT + 1)
        self.assertNotIn("她被吵醒了", self.player.screen)
        self.assertEqual(_hooks(), self.before)
