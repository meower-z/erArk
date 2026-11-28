"""
跨线程协议端口非阻塞退出查询与单退出事件契约的单元测试。
验证 finish 在队列满等待期间的 pending_exit 查询行为，以及重连与取消关闭时的单 Exit 不变式。
"""

import time
from collections.abc import Callable
from concurrent.futures import Future

from Script.Protocol import (
    Cancel,
    Exit,
    SessionCancelled,
    TextOp,
    ThreadedUiPort,
    default_first_option,
)
from tests.fast.base import FastTestCase
from tests.fast.test_protocol_ports import (
    TOKEN,
    _next,
    _ops,
    _serve,
    _start,
)

FINISHED = Exit("session", 3, "normal", "slot1")


def _full_queue_then_finish(
    port: ThreadedUiPort, texts: tuple[str, ...]
) -> Callable[[], None]:
    def body() -> None:
        port.clear("input")
        for text in texts:
            port.emit_op(TextOp(text))
        port.finish("normal", "slot1")

    return body


def _parked(port: ThreadedUiPort, epoch: int, worker: Future[object]) -> Exit:
    deadline = time.monotonic() + 5
    while (found := port.pending_exit(epoch)) is None:
        if worker.done() or time.monotonic() > deadline:
            raise AssertionError("finish did not reach its delivery wait")
        time.sleep(0.001)
    return found


def _finish_waiting(port: ThreadedUiPort) -> tuple[int, Future[object]]:
    epoch = port.attach(TOKEN).controller_epoch
    worker = _start(_full_queue_then_finish(port, ("last",)))
    if _parked(port, epoch, worker) != FINISHED:
        raise AssertionError("finish recorded an unexpected Exit")
    return epoch, worker


class PendingExitTest(FastTestCase):
    """验证 ThreadedUiPort 的 pending_exit 查询及 finish 等待投递期间的单退出事件行为。"""

    def test_pending_exit_reads_exit_while_finish_waits(self) -> None:
        """
        验证队列满导致 finish 阻塞时，pending_exit 对当前代次非阻塞返回 Exit 而不消费队列，
        且在非当前代次或断连后返回 None。
        """
        for texts in ((), ("a", "b")):
            with self.subTest(buffered=len(texts)):
                port = ThreadedUiPort(TOKEN, capacity=1)
                epoch = port.attach(TOKEN).controller_epoch
                self.assertIsNone(port.pending_exit(epoch))
                worker = _start(_full_queue_then_finish(port, texts))
                last = 3 if texts else 2
                finished = Exit("session", last, "normal", "slot1")
                self.assertEqual(_parked(port, epoch, worker), finished)
                self.assertIsNone(port.pending_exit(epoch + 1))
                self.assertFalse(worker.done())
                events = _serve(port, default_first_option())
                worker.result(5)
                seqs = [e.seq for e in events]
                self.assertEqual(seqs, list(range(1, last + 1)))
                self.assertEqual(events[-1], finished)
                self.assertEqual(_ops(events), [TextOp(t) for t in texts])
                epoch = port.attach(TOKEN).controller_epoch
                self.assertIsNone(port.pending_exit(epoch - 1))
                self.assertEqual(port.pending_exit(epoch), finished)
                port.detach(epoch)
                self.assertIsNone(port.pending_exit(epoch))

    def test_reattach_during_finish_wait_returns_before_exit_is_read(
        self,
    ) -> None:
        """
        验证 finish 在队满等待期间发生重连时，在队列中的 Exit 被读取前即正常返回。
        同时验证重连快照覆盖末尾渲染内容与退出水位，且新控制器仅读到一条 Exit。
        """
        port = ThreadedUiPort(TOKEN, capacity=1)
        _, worker = _finish_waiting(port)
        snapshot = port.attach(TOKEN)
        self.assertIsNone(worker.result(5))
        epoch = snapshot.controller_epoch
        self.assertEqual(snapshot.watermark_seq, FINISHED.seq)
        self.assertIn(TextOp("last"), _ops(snapshot.projection))
        self.assertEqual(_next(port, epoch), FINISHED)
        self.assertEqual(port.drain(epoch), [])

    def test_close_after_replayed_exit_queues_no_second_exit(self) -> None:
        """
        验证 finish 等待期间重连并读走重放 Exit 后，工作线程唤醒前调用 close 不追加第二条 Exit，且 finish 正常返回。
        同时验证关闭后空队列上的 receive 立即返回 None，pending_exit 与再次重连仍返回同一条 Exit。
        """
        port = ThreadedUiPort(TOKEN, capacity=1)
        _, worker = _finish_waiting(port)
        with port._cond:
            epoch = port.attach(TOKEN).controller_epoch
            self.assertEqual(port.drain(epoch), [FINISHED])
            port.close()
            self.assertEqual(port.drain(epoch), [])
        self.assertIsNone(worker.result(5))
        self.assertIsNone(_start(lambda: port.receive(epoch)).result(5))
        self.assertEqual(port.pending_exit(epoch), FINISHED)
        epoch = port.attach(TOKEN).controller_epoch
        self.assertEqual(port.drain(epoch), [FINISHED])

    def test_cancel_during_finish_wait_keeps_finish_exit(self) -> None:
        """
        验证 finish 在队满等待期间收到 Cancel 时抛出 SessionCancelled，且队列仅保留 finish 生成的 Exit。
        同时验证后续调用 close 不追加新 Exit，pending_exit 与再次重连均返回同一条 Exit。
        """
        port = ThreadedUiPort(TOKEN, capacity=1)
        epoch, worker = _finish_waiting(port)
        self.assertTrue(port.submit(Cancel(epoch, "quit")))
        self.assertIsInstance(worker.exception(5), SessionCancelled)
        self.assertEqual(port.drain(epoch), [FINISHED])
        port.close()
        self.assertEqual(port.drain(epoch), [])
        self.assertEqual(port.pending_exit(epoch), FINISHED)
        epoch = port.attach(TOKEN).controller_epoch
        self.assertEqual(port.drain(epoch), [FINISHED])
