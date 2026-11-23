"""
通信协议包 Script.Protocol 的单元测试。
通过公开接口验证独立导入、消息不可变性以及同线程与跨线程端口的行为契约。
"""

import contextlib
import dataclasses
import subprocess
import sys
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import Future, wait
from pathlib import Path
from typing import Any

import Script.Protocol
from Script.Protocol import (
    BackendEvent,
    BgColorOp,
    ButtonOp,
    Cancel,
    Choose,
    Clear,
    ClearButtonsOp,
    Continue,
    Exit,
    ImageButtonOp,
    ImageOp,
    InputText,
    Pause,
    RenderChunk,
    Responder,
    ScriptedUiPort,
    SessionCancelled,
    StyleDefOp,
    SubmitChoice,
    SubmitText,
    SyncPanel,
    TextOp,
    ThreadedUiPort,
    UiPort,
    UiRequest,
    UiResponse,
    default_first_option,
    reply,
    script,
)
from tests.fast.base import FastTestCase

ROOT = Path(__file__).resolve().parents[2]
TOKEN = "token"
STYLE = StyleDefOp("warn", "#f00", "#000", "mono", 12, True, False, False)
GO = ButtonOp("go", "cmd-go")
ICON = ImageButtonOp("icon", "cmd-icon")
ISOLATION = """
import sys
sys.path.insert(0, sys.argv[1])
sys.modules.update(tkinter=None, PIL=None)
import Script.Protocol
loaded = [n for n, module in sys.modules.items() if module is not None and n != "__main__"]
print(sorted(n for n in loaded if n.split(".")[0] not in sys.stdlib_module_names
             and n != "Script" and not n.startswith("Script.Protocol")))
"""


def _start(body: Callable[[], object]) -> Future[object]:
    future: Future[object] = Future()

    def run() -> None:
        try:
            future.set_result(body())
        except BaseException as error:
            future.set_exception(error)

    threading.Thread(target=run, daemon=True).start()
    return future


def _blocked(worker: Future[object]) -> bool:
    return not wait([worker], timeout=0.2).done


def _next(port: ThreadedUiPort, epoch: int = 1) -> BackendEvent:
    event = port.receive(epoch, timeout=5)
    if event is None:
        raise AssertionError("no backend event within 5 seconds")
    return event


def _serve(port: ThreadedUiPort, responder: Responder) -> list[BackendEvent]:
    events = [_next(port)]
    while not isinstance(events[-1], Exit):
        if isinstance(events[-1], Pause | Choose | InputText):
            port.submit(responder(events[-1]))
        events.append(_next(port))
    return events


def _story(port: UiPort) -> list[str]:
    port.emit_op(STYLE)
    port.emit_op(TextOp("hello"))
    port.clear("screen")
    port.sync_panel(7, "pick")
    port.set_skip_pauses(True)
    port.emit_op(TextOp("fast"))
    port.pause()
    port.pause(skippable=False)
    callbacks = {"save": lambda: port.choose(("yes", "no")).raw_value}
    first = port.choose(("save", "quit")).raw_value
    seen = [first, callbacks[first](), port.input_text(8).text]
    port.finish("normal", "slot1")
    return seen


def _skip(request: UiRequest) -> UiResponse:
    return Continue(request.controller_epoch, request.request_id, True)


def _ids(events: Iterable[BackendEvent]) -> list[int]:
    return [i for e in events if (i := getattr(e, "request_id", 0))]


def _ops(events: Iterable[BackendEvent]) -> list[object]:
    return [op for e in events if isinstance(e, RenderChunk) for op in e.ops]


class ProtocolPortsTest(FastTestCase):
    """验证协议包独立导入、消息不可变性以及同线程与跨线程端口的行为契约。"""

    def test_imports_without_tk_pil_or_game_packages(self) -> None:
        """验证在屏蔽 tkinter 与 PIL 的独立子进程中导入协议包时仅加载标准库与自身模块。"""
        command = [sys.executable, "-I", "-S", "-c", ISOLATION, str(ROOT)]
        result = subprocess.run(command, capture_output=True, check=False)
        output = (result.returncode, result.stdout.strip())
        self.assertEqual(output, (0, b"[]"), result.stderr)

    def test_messages_are_frozen_and_slotted(self) -> None:
        """验证协议包公开导出的全部消息数据类均不可修改属性且不带实例字典。"""
        exported = map(vars(Script.Protocol).get, Script.Protocol.__all__)
        kinds: list[Any] = [k for k in exported if dataclasses.is_dataclass(k)]
        self.assertGreaterEqual(len(kinds), 21)
        for kind in kinds:
            message = kind(*[None] * len(dataclasses.fields(kind)))
            with self.subTest(kind.__name__):
                with self.assertRaises(dataclasses.FrozenInstanceError):
                    setattr(message, dataclasses.fields(kind)[0].name, None)
                self.assertFalse(hasattr(message, "__dict__"))

    def test_chunk_flushes_at_256_ops_or_32_kib(self) -> None:
        """验证渲染指令缓冲在达到 256 条或 32 KiB 估算字节数时立即刷出为一个 RenderChunk。"""
        small = [TextOp(str(i)) for i in range(256)]
        for ops in (small, [TextOp("x" * 10_000)] * 4):
            port = ScriptedUiPort(default_first_option())
            for op in ops[:-1]:
                port.emit_op(op)
            self.assertEqual(port.events, [])
            port.emit_op(ops[-1])
            expected = [RenderChunk("scripted", 1, tuple(ops))]
            self.assertEqual(port.events, expected)

    def test_buffered_ops_flush_before_every_barrier(self) -> None:
        """验证清屏、面板同步、暂停、选择、文本输入与结束调用前会先刷出已缓冲的渲染指令。"""
        barriers: list[tuple[Callable[[ScriptedUiPort], object], type]] = [
            (lambda port: port.clear("buttons"), Clear),
            (lambda port: port.sync_panel(1, "pick"), SyncPanel),
            (lambda port: port.pause(), Pause),
            (lambda port: port.choose(("a",)), Choose),
            (lambda port: port.input_text(4, allow_empty=True), InputText),
            (lambda port: port.finish("normal"), Exit),
        ]
        for act, kind in barriers:
            with self.subTest(kind.__name__):
                port = ScriptedUiPort(default_first_option())
                port.emit_op(TextOp("a"))
                act(port)
                chunk = RenderChunk("scripted", 1, (TextOp("a"),))
                self.assertEqual(port.events[0], chunk)
                self.assertIsInstance(port.events[1], kind)
                self.assertEqual(port.events[1].seq, 2)

    def test_flush_publishes_buffered_ops_without_a_barrier(self) -> None:
        """
        断言 `ScriptedUiPort` 与 `ThreadedUiPort` 的 `flush()` 无缓冲时不发事件、有缓冲时发布 `RenderChunk`，关闭后抛出
        `SessionCancelled`。
        """
        port = ScriptedUiPort(default_first_option())
        port.flush()
        self.assertEqual(port.events, [])
        port.emit_op(TextOp("a"))
        port.emit_op(TextOp("b"))
        port.flush()
        chunk = RenderChunk("scripted", 1, (TextOp("a"), TextOp("b")))
        self.assertEqual(port.events, [chunk])
        threaded = ThreadedUiPort(TOKEN)
        threaded.attach(TOKEN)
        threaded.emit_op(TextOp("c"))
        threaded.flush()
        self.assertEqual(_ops([_next(threaded)]), [TextOp("c")])
        threaded.close("done")
        with self.assertRaises(SessionCancelled):
            threaded.flush()

    def test_skip_pauses_until_choose_input_or_sync(self) -> None:
        """验证可跳过暂停受跳过开关与 Continue 跳过标记控制，并在选择、文本输入或面板同步后关闭跳过。"""
        port = ScriptedUiPort(script("", "a", _skip, "t", "", ""))
        port.set_skip_pauses(True)
        self.assertEqual(port.pause(), Continue(1, 0, skip_pauses=True))
        self.assertEqual(port.pause(skippable=False), Continue(1, 1))
        port.choose(("a",))
        self.assertEqual(port.pause(), Continue(1, 3, skip_pauses=True))
        self.assertEqual(port.pause(), Continue(1, 0, skip_pauses=True))
        port.input_text(4)
        self.assertEqual(port.pause(), Continue(1, 5))
        port.set_skip_pauses(True)
        port.sync_panel(1, "pick")
        self.assertEqual(port.pause(), Continue(1, 6))

    def test_default_first_option_answers_every_request(self) -> None:
        """验证 default_first_option 能按规则应答暂停、有或无候选项的选择以及文本输入请求。"""
        port = ScriptedUiPort(default_first_option(lambda r: "n" * r.max_len))
        self.assertEqual(port.pause(), Continue(1, 1))
        self.assertEqual(port.choose(("x", "y")).raw_value, "x")
        self.assertRaises(ValueError, port.choose, ())
        self.assertEqual(port.input_text(3).text, "nnn")

    def test_cancel_and_close_raise_session_cancelled(self) -> None:
        """验证取消响应与关闭端口会丢弃未刷出指令、发出取消退出事件并抛出不被 Exception 捕获的 SessionCancelled。"""
        port = ScriptedUiPort(lambda r: Cancel(r.controller_epoch, "quit"))
        swallow = contextlib.suppress(Exception)
        with self.assertRaises(SessionCancelled), swallow:
            port.choose(("a",))
        self.assertRaises(SessionCancelled, port.emit_op, TextOp("late"))
        self.assertEqual(port.events[-1], Exit("scripted", 2, "cancelled"))
        port = ScriptedUiPort(default_first_option())
        port.emit_op(TextOp("unflushed"))
        port.close()
        port.close()
        self.assertEqual(port.events, [Exit("scripted", 1, "cancelled")])

        def closing(request: UiRequest) -> UiResponse:
            port.close("gone")
            return reply(request)

        port = ScriptedUiPort(closing)
        self.assertRaises(SessionCancelled, port.pause)

    def test_rejected_scripted_response_raises(self) -> None:
        """验证脚本应答器返回编号、类型、代次不符或文本超长的响应时抛出 ValueError。"""
        responders: list[Responder] = [
            lambda r: SubmitChoice(r.controller_epoch, r.request_id + 1, "a"),
            lambda r: Continue(r.controller_epoch, r.request_id),
            lambda r: SubmitChoice(r.controller_epoch + 1, r.request_id, "a"),
        ]
        for responder in responders:
            choose = ScriptedUiPort(responder).choose
            self.assertRaises(ValueError, choose, ("a",))
        port = ScriptedUiPort(script("x" * 4))
        self.assertRaises(ValueError, port.input_text, 3)

    def test_event_stream_matches_scripted_port(self) -> None:
        """验证同一段游戏逻辑在跨线程端口与脚本端口上产生完全一致的后端事件序列与返回值。"""
        steps = ("", "save", "yes", "name")
        scripted = ScriptedUiPort(script(*steps), session_id="s")
        self.assertEqual(_story(scripted), ["save", "yes", "name"])
        self.assertEqual(_ids(scripted.events), [1, 2, 3, 4])
        port = ThreadedUiPort(TOKEN, session_id="s")
        port.attach(TOKEN)
        worker = _start(lambda: _story(port))
        self.assertEqual(_serve(port, script(*steps)), scripted.events)
        self.assertEqual(worker.result(5), ["save", "yes", "name"])

    def test_backpressure_waits_for_capacity_without_drops(self) -> None:
        """验证跨线程端口在事件队列满时阻塞工作线程并在消费后继续发送，不丢失事件。"""
        port = ThreadedUiPort(TOKEN, capacity=2)
        port.attach(TOKEN)

        def body() -> None:
            for _ in range(5):
                port.clear("input")
            port.finish("normal")

        worker = _start(body)
        self.assertTrue(_blocked(worker))
        events = port.drain(1)
        self.assertEqual(len(events), 2)
        events += _serve(port, default_first_option())
        worker.result(5)
        self.assertEqual([e.seq for e in events], [1, 2, 3, 4, 5, 6])

    def test_finish_drains_while_close_and_cancel_drop(self) -> None:
        """验证正常结束保留队列事件供消费，而开放态关闭或取消会清空未送达事件并唤醒阻塞工作线程。"""
        port = ThreadedUiPort(TOKEN)
        port.attach(TOKEN)
        port.emit_op(TextOp("a"))
        port.finish("normal", "slot1")
        port.close()
        chunk = RenderChunk("session", 1, (TextOp("a"),))
        finished = Exit("session", 2, "normal", "slot1")
        self.assertEqual(port.drain(1), [chunk, finished])
        self.assertRaises(SessionCancelled, port.emit_op, TextOp("late"))
        port = ThreadedUiPort(TOKEN)
        epoch = port.attach(TOKEN).controller_epoch
        worker = _start(lambda: port.choose(("a",)))
        self.assertIsInstance(_next(port), Choose)
        self.assertTrue(port.submit(Cancel(epoch, "quit")))
        self.assertIsInstance(worker.exception(5), SessionCancelled)
        self.assertEqual(port.drain(1), [Exit("session", 2, "cancelled")])
        port = ThreadedUiPort(TOKEN, capacity=1)
        port.attach(TOKEN)
        worker = _start(lambda: [port.clear("input") for _ in range(3)])
        self.assertTrue(_blocked(worker))
        port.close("quit")
        self.assertIsInstance(worker.exception(5), SessionCancelled)
        self.assertEqual(port.drain(1), [Exit("session", 3, "cancelled")])

    def test_stale_responses_are_rejected_across_reattach(self) -> None:
        """验证接入令牌校验，以及重连后旧代次读取返回空、旧取消与各类无效响应均被拒绝。"""
        port = ThreadedUiPort(TOKEN)
        self.assertRaises(PermissionError, port.attach, "wrong")
        self.assertEqual(port.attach(TOKEN).controller_epoch, 1)

        def body() -> str:
            port.choose(("a", "b"))
            port.choose(("c",))
            return port.input_text(3).text

        worker = _start(body)
        self.assertEqual(_next(port), Choose("session", 1, 1, 1, ("a", "b")))
        stale = _start(lambda: port.receive(1, timeout=30))
        self.assertTrue(_blocked(stale))
        snapshot = port.attach(TOKEN)
        self.assertIsNone(stale.result(2))
        retagged = Choose("session", 1, 2, 1, ("a", "b"))
        self.assertEqual(snapshot.pending_request, retagged)
        port.clear("buttons")
        self.assertEqual(port.drain(1), [])
        self.assertIsNone(port.receive(1, timeout=0))
        self.assertEqual(port.drain(2), [Clear("session", 2, "buttons")])
        self.assertFalse(port.submit(Cancel(1, "stale")))
        self.assertFalse(port.submit(SubmitChoice(1, 1, "a")))
        self.assertFalse(port.submit(SubmitChoice(2, 9, "a")))
        self.assertFalse(port.submit(Continue(2, 1)))
        self.assertTrue(port.submit(SubmitChoice(2, 1, "a")))
        self.assertFalse(port.submit(SubmitChoice(2, 1, "a")))
        self.assertEqual(_ids([_next(port, 2)]), [2])
        self.assertTrue(port.submit(SubmitChoice(2, 2, "c")))
        self.assertIsInstance(_next(port, 2), InputText)
        self.assertFalse(port.submit(SubmitText(2, 3, "long")))
        self.assertFalse(port.submit(SubmitText(2, 3, "")))
        self.assertTrue(port.submit(SubmitText(2, 3, "ok")))
        self.assertEqual(worker.result(5), "ok")

    def test_reconnect_snapshot_keeps_controls_on_long_screen(self) -> None:
        """验证长屏重连快照分别限制文本与控件数量、清理已清除按钮，且后续实时事件序号高于水位线。"""
        port = ThreadedUiPort(TOKEN, session_id="s")
        for op in (STYLE, BgColorOp("#111"), TextOp("old")):
            port.emit_op(op)
        port.clear("screen")
        port.sync_panel(3, "settle")
        port.emit_op(BgColorOp("#222"))
        port.emit_op(GO)
        for i in range(5000):
            port.emit_op(TextOp(f"line {i}"))
        port.emit_op(ICON)
        port.clear("input")
        snap = port.attach(TOKEN)
        ops = _ops(snap.projection)
        for kept in (STYLE, BgColorOp("#222"), GO, ICON, TextOp("line 4999")):
            self.assertTrue(kept in ops, kept)
        self.assertFalse({BgColorOp("#111"), TextOp("old")} & set(ops))
        self.assertLess(sum(isinstance(op, TextOp) for op in ops), 5000)
        self.assertIn(SyncPanel("s", 3, 3, "settle"), snap.projection)
        watermark = snap.watermark_seq
        self.assertEqual(watermark, snap.projection[-1].seq + 1)
        port.emit_op(TextOp("live"))
        port.clear("input")
        live = port.drain(1)
        self.assertEqual([e.seq for e in live], [watermark + 1, watermark + 2])
        self.assertEqual(_ops(live), [TextOp("live")])
        port.detach(1)
        for i in range(3000):
            port.emit_op(ImageOp(f"img {i}"))
            port.emit_op(ButtonOp("pick", f"cmd-{i}"))
            port.emit_op(ClearButtonsOp((f"cmd-{i - 1}",)))
        port.clear("input")
        ops = _ops(port.attach(TOKEN).projection)
        self.assertLessEqual(len(ops), 2 * 2000 + 2 * 1000 + 2)
        self.assertTrue(ImageOp("img 2999") in ops)
        buttons = [op for op in ops if isinstance(op, ButtonOp | ImageButtonOp)]
        self.assertEqual(buttons, [ButtonOp("pick", "cmd-2999")])
        port.detach(2)
        port.clear("buttons")
        ops = _ops(port.attach(TOKEN).projection)
        self.assertFalse(ButtonOp("pick", "cmd-2999") in ops)

    def test_detached_worker_keeps_computing_until_its_prompt(self) -> None:
        """验证控制器断连会解除队列满阻塞并让工作线程继续运行到下一个输入请求，重连后可恢复应答。"""
        port = ThreadedUiPort(TOKEN, capacity=1)
        epoch = port.attach(TOKEN).controller_epoch
        unblocked, computed = threading.Event(), threading.Event()

        def body() -> str:
            port.clear("input")
            port.clear("input")
            unblocked.set()
            computed.wait(5)
            port.emit_op(TextOp("while away"))
            return port.choose(("ok",)).raw_value

        worker = _start(body)
        self.assertTrue(_blocked(worker))
        self.assertFalse(unblocked.is_set())
        port.detach(epoch)
        self.assertTrue(unblocked.wait(5))
        computed.set()
        self.assertTrue(_blocked(worker))
        snapshot = port.attach(TOKEN)
        self.assertIn(TextOp("while away"), _ops(snapshot.projection))
        pending = Choose("session", 4, 2, 1, ("ok",))
        self.assertEqual(snapshot.pending_request, pending)
        self.assertTrue(port.submit(SubmitChoice(2, 1, "ok")))
        self.assertEqual(worker.result(5), "ok")
