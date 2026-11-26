"""
`io_init` 与 `flow_handle` 协议端口集成测试：在子进程中验证嵌套选择、文本输入、逐项刷出、跳过暂停、999 退出、
跨线程取消与无轮询等待。
"""

import json
import subprocess
import sys

from tests.fast.base import FastTestCase
from tests.world import ROOT

SCENARIOS = """
import json
import os
import sys
import threading
import time
import types

sleeps = []
real_sleep = time.sleep


def counting_sleep(seconds):
    sleeps.append(seconds)
    real_sleep(seconds)


def forbidden_exit(code):
    raise AssertionError(f"os._exit({code})")


time.sleep = counting_sleep
os._exit = forbidden_exit
saved = []
sys.modules["Script.Core.save_handle"] = types.SimpleNamespace(
    establish_save=saved.append
)
from Script.Config import normal_config

normal_config.init_normal_config()
from Script.Core import flow_handle, input_cache, io_init
from Script.Protocol import (
    ButtonOp, Cancel, Choose, Continue, Exit, InputText, Pause, RenderChunk,
    ScriptedUiPort, SessionCancelled, SubmitChoice, TextOp, ThreadedUiPort,
    script,
)

report = {}


def requests(port):
    return [
        [type(event).__name__, event.request_id]
        for event in port.events
        if isinstance(event, (Pause, Choose))
    ]


def ops(port, kind):
    return [
        op
        for event in port.events
        if isinstance(event, RenderChunk)
        for op in event.ops
        if isinstance(op, kind)
    ]


port = ScriptedUiPort(script("1", "2"))
io_init.configure(port)
inner = []


def open_inner():
    flow_handle.print_cmd("inner", "2")
    inner.append(flow_handle.askfor_all(["2"]))


flow_handle.print_cmd("outer", "1", open_inner)
outer = flow_handle.askfor_all(["1"])
port.finish("normal")
report["nested"] = {
    "outer": outer,
    "inner": inner,
    "requests": requests(port),
    "valid_ids": [
        list(event.valid_ids) for event in port.events
        if isinstance(event, Choose)
    ],
    "buttons": [[op.label, op.command_id] for op in ops(port, ButtonOp)],
    "texts": [op.text for op in ops(port, TextOp)],
    "history": list(input_cache.input_cache),
}

port = ScriptedUiPort(
    script(
        lambda request: Continue(
            request.controller_epoch, request.request_id, skip_pauses=True
        ),
        "",
    )
)
io_init.configure(port)
flow_handle.askfor_wait()
flow_handle.askfor_wait()
io_init.set_skip_pauses(False)
flow_handle.askfor_wait()
io_init.set_skip_pauses(True)
flow_handle.askfor_wait()
report["pauses"] = requests(port)

port = ScriptedUiPort(script("name", ""))
io_init.configure(port)
typed = [flow_handle.askfor_str(), flow_handle.askfor_str(False)]
report["text"] = {
    "typed": typed,
    "requests": [
        [type(event).__name__, event.allow_empty] for event in port.events
        if isinstance(event, (Choose, InputText))
    ],
}

port = ScriptedUiPort(script())
io_init.configure(port)
chunks = []
for item in io_init.flushing(["a", "b"]):
    io_init.era_print(item)
    chunks.append(len(port.events))
chunks.append(len(port.events))
report["flushing"] = {
    "events_seen": chunks,
    "texts": [op.text for op in ops(port, TextOp)],
}

port = ScriptedUiPort(script("999"))
io_init.configure(port)
try:
    flow_handle.askfor_all(["999"])
    report["quit"] = "returned"
except SessionCancelled:
    report["quit"] = {
        "saved": saved,
        "exits": [e.reason for e in port.events if isinstance(e, Exit)],
    }

port = ThreadedUiPort("token", capacity=4)
io_init.configure(port)
epoch = port.attach("token").controller_epoch
results = []


def backend():
    try:
        flow_handle.print_cmd("go", "7")
        results.append(flow_handle.askfor_all(["7"]))
        flow_handle.askfor_wait()
        results.append("waited")
        flow_handle.askfor_all(["7"])
    except SessionCancelled:
        results.append("cancelled")


def next_request():
    while True:
        event = port.receive(epoch, timeout=10)
        if event is None or isinstance(event, (Pause, Choose)):
            return event


worker = threading.Thread(target=backend)
worker.start()
first = next_request()
port.submit(SubmitChoice(epoch, first.request_id, "7", "button"))
second = next_request()
port.submit(Continue(epoch, second.request_id))
third = next_request()
port.submit(Cancel(epoch, "window closed"))
closing = port.receive(epoch, timeout=10)
worker.join(10)
report["threaded"] = {
    "requests": [type(e).__name__ for e in (first, second, third)],
    "results": results,
    "closing": [type(closing).__name__, getattr(closing, "reason", None)],
    "alive": worker.is_alive(),
}
report["sleeps"] = sleeps
print(json.dumps(report, ensure_ascii=False))
"""
"""在子进程中依次执行六组端口交互场景并以末行 JSON 输出结果与 `time.sleep` 调用记录的脚本。"""


class IoFlowPortTest(FastTestCase):
    """运行端口交互场景子进程并逐项断言各场景输出符合协议语义。"""

    report: dict

    @classmethod
    def setUpClass(cls) -> None:
        """在仓库根目录运行 `SCENARIOS` 子进程并解析其输出的 JSON 报告供全部测试方法使用。"""
        result = subprocess.run(
            [sys.executable, "-c", SCENARIOS],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr[-3000:])
        cls.report = json.loads(result.stdout.splitlines()[-1])

    def test_nested_command_gets_its_own_choice(self) -> None:
        """断言嵌套命令回调会收到新的选择请求编号，并按顺序记录按钮、回显文本与输入历史。"""
        nested = self.report["nested"]
        self.assertEqual((nested["outer"], nested["inner"]), ("1", ["2"]))
        self.assertEqual(nested["requests"], [["Choose", 1], ["Choose", 2]])
        self.assertEqual(nested["buttons"], [["outer", "1"], ["inner", "2"]])
        self.assertEqual(nested["texts"], ["1\n", "2\n"])
        self.assertEqual(nested["history"], ["1", "2"])

    def test_choice_offers_only_the_prompts_options(self) -> None:
        """断言嵌套 `askfor_all` 发出的两次 `Choose` 请求的 `valid_ids` 分别只包含各自提示接受的选项。"""
        self.assertEqual(self.report["nested"]["valid_ids"], [["1"], ["2"]])

    def test_text_prompts_ask_for_text(self) -> None:
        """
        断言 `askfor_str()` 与 `askfor_str(False)` 分别发出 `allow_empty` 为 `False` 与 `True` 的 `InputText` 请求。
        """
        self.assertEqual(
            self.report["text"],
            {
                "typed": ["name", ""],
                "requests": [["InputText", False], ["InputText", True]],
            },
        )

    def test_flushing_publishes_after_each_item(self) -> None:
        """断言 `io_init.flushing` 在每项处理完后立即刷出缓冲文本，累计事件数依次为 0、1、2。"""
        self.assertEqual(
            self.report["flushing"],
            {"events_seen": [0, 1, 2], "texts": ["a", "b"]},
        )

    def test_skip_mode_answers_skippable_pauses(self) -> None:
        """断言开启跳过模式后可跳过暂停直接返回，仅在未跳过时向端口发出两次 `Pause` 请求。"""
        self.assertEqual(self.report["pauses"], [["Pause", 1], ["Pause", 2]])

    def test_quit_option_saves_and_ends_session(self) -> None:
        """断言输入 "999" 会保存 "auto" 存档、发出原因 "normal" 的 `Exit` 事件并抛出 `SessionCancelled`。"""
        self.assertEqual(
            self.report["quit"], {"saved": ["auto"], "exits": ["normal"]}
        )

    def test_threaded_port_round_trip_and_cancel(self) -> None:
        """断言跨线程端口完成选择与暂停往返后，提交 `Cancel` 会发出 "cancelled" 退出事件并正常结束工作线程。"""
        self.assertEqual(
            self.report["threaded"],
            {
                "requests": ["Choose", "Pause", "Choose"],
                "results": ["7", "waited", "cancelled"],
                "closing": ["Exit", "cancelled"],
                "alive": False,
            },
        )

    def test_waiting_for_input_does_not_sleep(self) -> None:
        """断言全部端口等待场景中从未调用 `time.sleep`。"""
        self.assertEqual(self.report["sleeps"], [])
