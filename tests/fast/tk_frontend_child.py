"""
`TkFrontend` 快速集成测试共享子进程辅助模块，
提供以假窗口与假渲染器驱动前端并采集状态快照的脚本与工具函数。
"""

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
    AttachmentSnapshot, Choose, Clear, Exit, FrontendInitConfig, InputText, Pause, RenderChunk, SkipPauses,
    SubmitChoice, SyncPanel, TextOp,
)

ROW = 10
spec = json.loads(sys.stdin.read())
viewport = spec["viewport"]
rows_per_screen = max(viewport, 0) // ROW
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
        self.surface, self.deferred, self.pending = None, False, False

    def on_close(self, handler): pass
    def focus_input(self): pass
    def defer_see_end(self): self.deferred = True

    def flush_see_end(self):
        self.deferred = False
        if self.pending:
            self.pending = False
            self.see_end()

    def see_end(self):
        if self.deferred:
            self.pending = True
        else:
            self.surface.scroll_end()


class Surface:
    def __init__(self, window, tooltip, press):
        self.window, window.surface, self.press = window, self, press
        self.rows, self.hidden = [], None
        self.anchor = self.unit = self.top = 0

    def end(self): return len(self.rows) if self.hidden is None else self.hidden

    def render(self, op):
        self.rows.extend(op.text.splitlines())
        self.window.see_end()

    def fit(self):
        return Fit(ROW * (len(self.rows) - self.anchor), ROW * (self.unit - self.anchor), viewport)

    def clear_buttons(self, command_ids): pass

    def clear_screen(self):
        self.rows, self.hidden = [], None
        self.anchor = self.unit = self.top = 0

    def hits_button(self, x_root, y_root): return False
    def mark_unit(self): self.unit = len(self.rows)
    def hide_unit(self): self.hidden = self.unit
    def reveal(self): self.hidden = None
    def pin(self): self.top = self.anchor
    def anchor_to_end(self): self.anchor = len(self.rows)
    def anchor_to_unit(self): self.anchor = self.unit
    def advance_page(self): self.anchor += rows_per_screen
    def scroll_end(self): self.top = max(0, self.end() - rows_per_screen)
    def screen(self): return self.rows[self.top : min(self.end(), self.top + rows_per_screen)]


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
        value = f":{response.raw_value}" if isinstance(response, SubmitChoice) else ""
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
                "backlog": len(frontend._backlog),
                "limit": app.DRAIN_BATCH,
            })
        case [key] if key in keys:
            root.handlers[keys[key]](Click())
        case _:
            port.out.append(port.make(step))
            if isinstance(port.out[-1], Exit):
                port.exit = port.out[-1]
print(json.dumps(looks))
"""
"""
在子进程中以假窗口、假渲染器与假端口驱动真实 `TkFrontend`
事件循环与键鼠回调并输出状态快照的测试脚本。
"""


def drive(
    steps: Sequence[Sequence[object]],
    viewport: int = 30,
    accept: bool = True,
    projection: tuple[list[str], ...] = (),
    skip: bool = False,
) -> list[dict]:
    """
    在独立子进程中按步骤驱动 `TkFrontend`，
    返回每次观察点采集到的状态快照列表

    参数：
    steps (Sequence[Sequence[object]]) -- 依次执行的步骤列表
    viewport (int) -- 假文本框的视口像素高度，默认为 30
    accept (bool) -- 假端口是否接受前端提交的应答，默认为 True
    projection (tuple[list[str], ...]) -- 附着回放的投影步骤元组
    skip (bool) -- 附着快照中的跳过开关初值，默认为 False

    返回值类型：list[dict] -- 与每个 "look" 对应的状态字典列表
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
    将若干行名拼接为逐行换行的文本输出步骤

    参数：
    *names (str) -- 按顺序写入同一文本块的各行内容

    返回值类型：list[str] -- 供 `drive` 使用的 ["text", 文本内容] 步骤列表
    """
    return ["text", "".join(f"{name}\n" for name in names)]
