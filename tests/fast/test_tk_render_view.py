"""`Renderer` 视图滚动、翻页推进、高度测量与旧行裁剪快速测试，在隔离子进程中以替身文本框验证渲染器。"""

import json
import os
import subprocess
import sys

from tests.fast.base import FastTestCase
from tests.world import ROOT

CHILD = """
import json

from Script.Config import normal_config

normal_config.init_normal_config()
from Script.Frontend.Tk.render import ANCHOR, Renderer
from Script.Protocol import TextOp

LIMIT = normal_config.config_normal.text_hight


def line(index):
    return int(index.split(".")[0])


class Text:
    def __init__(self, heights, tail="", lines=1):
        self.heights, self.tail, self.lines, self.anchor = heights, tail, lines, ""
        self.calls, self.bottom, self.dline = [], "1.0", None

    def mark_set(self, name, index):
        if name == ANCHOR:
            self.anchor = self.index(index)

    def mark_gravity(self, name, side): pass
    def tag_configure(self, *args, **kwargs): pass
    def tag_add(self, *args): pass
    def tag_remove(self, *args): pass
    def insert(self, *args): pass
    def get(self, start, end): return self.tail
    def winfo_height(self): return 100
    def winfo_pixels(self, value): return 0
    def cget(self, option): return 0
    def count(self, start, end, *options): return self.heights.get((start, end))
    def dlineinfo(self, index): return self.dline
    def yview(self, *args): self.calls.append(["yview", *args])
    def yview_moveto(self, *args): self.calls.append(["moveto", *args])
    def yview_scroll(self, *args): self.calls.append(["scroll", *args])
    def delete(self, *args): self.calls.append(["delete", *args])

    def index(self, index):
        if index == "end-1c":
            return f"{self.lines}.0"
        if index == f"{ANCHOR} linestart":
            return self.anchor
        if index == f"{ANCHOR} +1 display lines":
            return "2.0"
        if index.startswith("@"):
            return self.bottom
        if index.endswith(" +1 display lines"):
            return f"{line(index) + 1}.0"
        return index

    def compare(self, left, op, right):
        left, right = (line(self.anchor if x == ANCHOR else x) for x in (left, right))
        return left > right if op == ">" else left < right


class Window:
    def __init__(self, textbox):
        self.textbox = textbox


class Tooltip:
    def drop_stale_tags(self): pass
    def hide(self): pass


def renderer(textbox):
    return Renderer(Window(textbox), Tooltip(), lambda command_id: None)


def view(height, clicks, held=False, tail="", blank=0):
    heights = {(ANCHOR, "2.0"): height, (ANCHOR, "end"): height, ("end-1c", "end"): blank}
    textbox = Text(heights, tail)
    shown = renderer(textbox)
    for _ in range(clicks):
        shown.advance_page()
    del textbox.calls[:]
    shown.sync_view(held)
    return textbox.calls


def advance(bottom_y):
    textbox = Text({(ANCHOR, "2.0"): 20, ("4.0", "5.0"): 20})
    shown = renderer(textbox)
    textbox.bottom, textbox.dline = "4.0", (0, bottom_y, 10, 100 - bottom_y, 15)
    shown.advance_page()
    return textbox.anchor


def used(tail, heights):
    textbox = Text({(ANCHOR, end): value for end, value in heights.items()}, tail)
    return renderer(textbox).fit().used


def trim(anchor):
    textbox = Text({}, lines=LIMIT * 10 + 1)
    shown = renderer(textbox)
    textbox.anchor = anchor
    shown.render(TextOp("x\\n"))
    return [call for call in textbox.calls if call[0] == "delete"]


def read_to_end():
    textbox = Text({}, lines=LIMIT * 10 + 1)
    shown = renderer(textbox)
    textbox.anchor = "7.0"
    shown.anchor_to_end()
    return [call for call in textbox.calls if call[0] == "delete"]


print(json.dumps({
    "fresh": view(0, 0),
    "fresh_newline": view(0, 0, tail="\\n", blank=20),
    "held": view(0, 0, held=True),
    "advance_full": advance(80),
    "advance_partial": advance(90),
    "tall_1_5": view(150, 1),
    "tall_2_5": view(250, 2),
    "tall_done": view(150, 2),
    "used_newline": used("\\n", {"end-1c": 40, "end": 60}),
    "used_open_line": used("x", {"end-1c": 40, "end": (60,)}),
    "trim_read": trim(f"{LIMIT * 8}.0"),
    "trim_unread": trim("7.0"),
    "trim_read_to_end": read_to_end(),
    "limit": LIMIT,
}))
"""
"""在隔离子进程中构造替身文本框与真实 `Renderer`、收集视图与裁剪调用并输出 JSON 报告的脚本源码。"""


class RendererViewTest(FastTestCase):
    """验证 `Renderer` 的 `sync_view`、`advance_page`、`fit` 与 `_trim` 行为的测试类。"""

    report: dict
    """`setUpClass` 从子进程收集并缓存的渲染器行为报告字典。"""

    @classmethod
    def setUpClass(cls) -> None:
        """
        在隔离子进程中运行 `CHILD` 脚本并将解析后的 JSON 报告缓存到 `report` 类属性

        参数：无

        返回值类型：None
        """
        result = subprocess.run(
            [sys.executable, "-c", CHILD],
            cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            check=False,
            capture_output=True,
            encoding="utf-8",
            timeout=300,
        )
        assert result.returncode == 0, result.stderr[-2000:]
        cls.report = json.loads(result.stdout.splitlines()[-1])

    def test_unheld_view_follows_the_end(self) -> None:
        """断言未停顿且无页内偏移时 sync_view 滚至文末并回退空行高度，停顿时对齐到 pager.anchor。"""
        for name, scroll in (("fresh", 0), ("fresh_newline", -20)):
            with self.subTest(name):
                self.assertEqual(
                    self.report[name],
                    [["moveto", 1.0], ["scroll", scroll, "pixels"]],
                )
        self.assertEqual(self.report["held"], [["yview", "pager.anchor"]])

    def test_page_advance_skips_only_a_whole_bottom_line(self) -> None:
        """断言底行完整落在视口内时 advance_page 将锚点移至其下一显示行，底行被截断时移至该底行。"""
        self.assertEqual(self.report["advance_full"], "5.0")
        self.assertEqual(self.report["advance_partial"], "4.0")

    def test_last_page_of_a_tall_line_stays_on_its_bottom(self) -> None:
        """断言超高单行末页停顿结束后 sync_view 对齐锚点加页内偏移，完全翻完后滚至文末。"""
        for name, offset in (("tall_1_5", 100), ("tall_2_5", 200)):
            with self.subTest(name):
                self.assertEqual(
                    self.report[name],
                    [["yview", "pager.anchor"], ["scroll", offset, "pixels"]],
                )
        self.assertEqual(
            self.report["tall_done"],
            [["moveto", 1.0], ["scroll", 0, "pixels"]],
        )

    def test_fit_skips_the_empty_line_after_a_newline(self) -> None:
        """断言 `fit` 在末尾含换行符时测至 `"end-1c"`，否则测至 `"end"`，并兼容 `count` 返回元组的情形。"""
        self.assertEqual(self.report["used_newline"], 40)
        self.assertEqual(self.report["used_open_line"], 60)

    def test_trim_keeps_the_unread_lines(self) -> None:
        """断言超行裁剪在锚点靠下时裁至上限五倍行，在锚点靠上时停在未读锚点所在行以保留未读内容。"""
        half = f"{self.report['limit'] * 5}.0"
        self.assertEqual(self.report["trim_read"], [["delete", "1.0", half]])
        self.assertEqual(self.report["trim_unread"], [["delete", "1.0", "7.0"]])

    def test_reading_to_the_end_trims_an_overlong_log(self) -> None:
        """断言超限时 `anchor_to_end` 将锚点移至文末并删除 `"1.0"` 至 `5 * text_hight` 行首的旧行。"""
        half = f"{self.report['limit'] * 5}.0"
        self.assertEqual(
            self.report["trim_read_to_end"], [["delete", "1.0", half]]
        )
