"""`TkFrontend` 快速测试辅助模块，在隔离子进程中以替身窗口、渲染器与端口驱动真实前端并收集状态快照。"""

import json
import os
import subprocess
import sys
from collections.abc import Sequence

from tests.world import ROOT

CHILD = """
import json
import sys
from collections import deque

from Script.Config import normal_config

normal_config.init_normal_config()
from Script.Frontend.Tk import app, warmup
from Script.Frontend.Tk.pager import Fit
from Script.Protocol import (
    AttachmentSnapshot, Choose, Clear, Continue, Exit, FrontendInitConfig, InputText, Pause, RenderChunk, SkipPauses,
    SubmitChoice, SyncPanel, TextOp,
)

ROW = 10
spec = json.loads(sys.stdin.read())
viewport = spec["viewport"]
EVENTS = {
    "text": lambda seq, text: RenderChunk("s", seq, (TextOp(text),)),
    "pause": lambda seq: Pause("s", seq, 1, seq),
    "choose": lambda seq: Choose("s", seq, 1, seq, ("1",)),
    "input": lambda seq: InputText("s", seq, 1, seq, 8, allow_empty=True),
    "sync": lambda seq: SyncPanel("s", seq, 1, "settle"),
    "exit": lambda seq: Exit("s", seq, "normal"),
    "skip": lambda seq, enabled: SkipPauses("s", seq, enabled),
    "clear": lambda seq: Clear("s", seq, "screen"),
}


class Root:
    def __init__(self):
        self.calls, self.handlers, self.destroyed, self.ids = {}, {}, False, 0

    def after(self, ms, fn): return self.after_idle(fn)

    def after_idle(self, fn):
        self.ids += 1
        self.calls[str(self.ids)] = fn
        return str(self.ids)

    def after_cancel(self, call_id): self.calls.pop(call_id, None)
    def bind(self, name, fn): self.handlers[name] = fn
    def mainloop(self): pass
    def destroy(self): self.destroyed = True

    def tick(self):
        calls, self.calls = self.calls, {}
        for fn in calls.values():
            if not self.destroyed:
                fn()


class Order:
    value = ""
    def get(self): return self.value
    def set(self, value): self.value = value


class Font:
    def measure(self, text): return 11


class Tooltip:
    def __init__(self, *args): pass
    def hide(self): pass


class Window:
    def __init__(self, normal):
        self.root, self.order, self.textbox, self.normal_font = Root(), Order(), None, Font()
        self.config = FrontendInitConfig(800, 600, 80, 16, "#000000")
        self.cue = False

    def on_close(self, handler): pass
    def focus_input(self): pass
    def set_hold_cue(self, active): self.cue = active


class Surface:
    def __init__(self, window, tooltip, press):
        self.press, self.rows, self.hidden = press, [], None
        self.anchor = self.unit = self.top = self.fits = 0
        self.views, self.unread_at_unit = [], []

    def end(self): return len(self.rows) if self.hidden is None else self.hidden

    def render(self, op):
        self.rows.extend(op.text.splitlines())

    def fit(self):
        self.fits += 1
        return Fit(ROW * (len(self.rows) - self.anchor), ROW * (self.unit - self.anchor), viewport)

    def clear_buttons(self, command_ids): pass

    def clear_screen(self):
        self.rows, self.hidden = [], None
        self.anchor = self.unit = self.top = 0

    def hits_button(self, x_root, y_root): return False
    def mark_unit(self):
        self.unread_at_unit.append(len(self.rows) - self.anchor)
        self.unit = len(self.rows)

    def ready(self): return viewport > 0
    def hide_unit(self): self.hidden = self.unit
    def reveal(self): self.hidden = None
    def sync_view(self, held):
        self.views.append("pin" if held else "end")
        if held:
            self.top = self.anchor
        else:
            self.scroll_end()

    def anchor_to_end(self): self.anchor = len(self.rows)
    def anchor_to_unit(self): self.anchor = self.unit
    def advance_page(self): self.anchor += viewport // ROW
    def scroll_end(self): self.top = max(0, self.end() - viewport // ROW)
    def screen(self): return self.rows[self.top : min(self.end(), self.top + viewport // ROW)]


class Port:
    def __init__(self): self.out, self.sent, self.seq, self.exit = deque(), [], 0, None

    def make(self, step):
        self.seq += 1
        return EVENTS[step[0]](self.seq, *step[1:])

    def attach(self, token):
        projection = tuple(self.make(step) for step in spec["projection"])
        return AttachmentSnapshot("s", 1, self.seq, projection, None, spec["skip"])

    def drain(self, epoch, max_events):
        return [self.out.popleft() for _ in range(min(max_events, len(self.out)))]

    def pending_exit(self, epoch): return self.exit

    def submit(self, response):
        match response:
            case SubmitChoice():
                value = f":{response.raw_value}"
            case Continue(skip_pauses=True):
                value = ":skip"
            case _:
                value = ""
        self.sent.append(type(response).__name__ + value)
        return spec["accept"]


class Click:
    x_root = y_root = 0


app.Window, app.Renderer, app.Tooltip = Window, Surface, Tooltip
warmup.warm_up = lambda *args: None
port = Port()
frontend = app.TkFrontend(port, "token")
frontend.run()
root, surface, gate = frontend.window.root, frontend.renderer, frontend.gate
keys = {"click": "<ButtonPress-1>", "rclick": "<ButtonPress-3>", "enter": "<Return>"}
looks = []
for step in spec["steps"]:
    match step:
        case ["step"]:
            root.tick()
        case ["map", height]:
            viewport = height
        case ["scrollup"]:
            surface.top = 0
        case ["tick", *count]:
            for _ in range(3 * (count[0] if count else 1)):
                root.tick()
        case ["press", command_id]:
            surface.press(command_id)
            root.handlers["<ButtonPress-1>"](Click())
        case ["look"]:
            looks.append({
                "hold": frontend.pager.hold,
                "screen": surface.screen(),
                "hidden": surface.rows[surface.end():],
                "request": type(gate.request).__name__ if gate.request else None,
                "armed": gate.armed,
                "sent": list(port.sent),
                "closed": root.destroyed,
                "order": frontend.window.order.get(),
                "skip": frontend.pager.skip,
                "queued": len(port.out),
                "fits": surface.fits,
                "views": surface.views,
                "unread_at_unit": surface.unread_at_unit,
                "cue": frontend.window.cue,
            })
            surface.views = []
        case [key] if key in keys:
            root.handlers[keys[key]](Click())
        case _:
            port.out.append(port.make(step))
            if isinstance(port.out[-1], Exit):
                port.exit = port.out[-1]
print(json.dumps(looks))
"""
"""在子进程中运行真实 `TkFrontend`、按步骤推进事件泵与键鼠输入并输出状态快照的脚本源码。"""


def drive(
    steps: Sequence[Sequence[object]],
    viewport: int = 30,
    accept: bool = True,
    projection: tuple[list[str], ...] = (),
    skip: bool = False,
) -> list[dict]:
    """
    在子进程中驱动真实 `TkFrontend` 执行给定步骤序列并返回每次 `"look"` 采样得到的状态快照

    参数：
    steps (Sequence[Sequence[object]]) -- 按顺序执行的事件入队、泵推进、键鼠操作与采样步骤
    viewport (int) -- 替身渲染器可视区域像素高度，默认值为 30
    accept (bool) -- 替身端口 `submit` 返回的接受结果，默认值为 True
    projection (tuple[list[str], ...]) -- 附着快照中的初始回放事件步骤元组，默认为空元组
    skip (bool) -- 附着快照中的初始跳过暂停状态，默认值为 False

    返回值类型：list[dict] -- 与每个 `"look"` 步骤一一对应的前端状态快照字典列表
    """
    spec = {
        "steps": steps,
        "viewport": viewport,
        "accept": accept,
        "projection": list(projection),
        "skip": skip,
    }
    result = subprocess.run(
        [sys.executable, "-c", CHILD],
        cwd=ROOT,
        input=json.dumps(spec),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(result.stdout.splitlines()[-1])


def rows(*names: str) -> list[str]:
    """
    将若干行文本名称拼装为供 `drive` 使用的文本渲染块步骤

    参数：
    *names (str) -- 依次放入该输出块且每项后附带换行符的行内容

    返回值类型：list[str] -- 形如 `["text", "..."]` 的文本事件步骤列表
    """
    return ["text", "".join(f"{name}\n" for name in names)]
