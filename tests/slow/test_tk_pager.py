"""
真实 Tk 窗口视口分页集成测试
==============================
载入游戏并创建 ThreadedUiPort 与 TkFrontend，
经 io_init 输出文本与图片并驱动事件泵与窗口刷新。
验证超屏块隐藏与左键显现、超屏单块逐屏翻页、折行与图片高度计数、
满屏末行不暂停、超屏高图逐屏到底、提示词后追加高图从顶展示
以及裁剪保留未显示行。仅在没有可用显示时跳过测试。
"""

import signal
import time
import tkinter
from unittest import mock

from tests.slow import remove_parent_guard
from tests.slow.base import SlowTestCase
from tests.world import FullWorld

TOKEN = "pager-test"
"""测试内 `ThreadedUiPort` 与 `TkFrontend` 附着校验使用的固定鉴权令牌。"""
LIMIT = 2000
"""测试循环中输出块数与翻页次数的安全上限。"""


class TkPagerTest(SlowTestCase):
    """
    在真实 Tk 文本框中验证按块暂停、逐屏翻页、折行与图片测量、
    满屏边界、高图翻页、提示词后高图置顶与裁剪保底行为的集成测试类。
    """

    def setUp(self) -> None:
        """
        设好时限并载入游戏，先探测能否创建 Tk 根窗口（仅缺显示时跳过），
        再创建端口与真实 Tk 前端，等待文本框完成布局后泵送一次事件
        Keyword arguments:
        无
        Return arguments:
        无
        """
        signal.signal(signal.SIGALRM, self._time_up)
        signal.alarm(self.time_limit)
        remove_parent_guard()
        self.world = FullWorld.load()
        from Script.Core import io_init
        from Script.Frontend.Tk.app import TkFrontend
        from Script.Protocol import ThreadedUiPort

        try:
            tkinter.Tk().destroy()
        except tkinter.TclError as error:
            self.skipTest(f"没有可用的显示，无法创建 Tk 窗口：{error}")
        port = ThreadedUiPort(TOKEN)
        frontend = TkFrontend(port, TOKEN)
        self.addCleanup(frontend.window.root.destroy)
        io_init.configure(port)
        io_init.init_style()
        self.io = io_init
        self.frontend = frontend
        self.textbox = frontend.window.textbox
        root = frontend.window.root
        with mock.patch.object(root, "mainloop"):
            frontend.run()
        deadline = time.monotonic() + 10
        while self.textbox.winfo_height() < 200 and time.monotonic() < deadline:
            root.update()
            time.sleep(0.05)
        self.pump()

    def pump(self) -> None:
        """
        执行一次前端事件泵并刷新 Tk 窗口布局与界面
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.frontend._pump()
        self.frontend.window.root.update()

    def chunk(self, *lines: str) -> None:
        """
        把多行文本合并为同一输出块刷入端口并泵送到 Tk 窗口
        Keyword arguments:
        *lines -- 按顺序写入本块的各行文本
        Return arguments:
        无
        """
        for line in lines:
            self.io.era_print(f"{line}\n")
        self.io.flush()
        self.pump()

    def click(self) -> None:
        """
        向文本框发送一次左键按下事件并泵送刷新
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.textbox.event_generate("<ButtonPress-1>", x=5, y=5)
        self.pump()

    def grow(self, before: int) -> int:
        """
        计算当前未读像素高度相对指定基线的增量
        Keyword arguments:
        before -- 输出前的未读像素高度基线
        Return arguments:
        int -- 当前 `fit().used` 减去 `before` 得到的像素增量
        """
        return self.frontend.renderer.fit().used - before

    def test_overflowing_chunk_is_hidden_and_click_reveals_it(self) -> None:
        """断言逐块输出超屏后停在 "unit" 状态并仅隐藏末尾溢出块，左键点击后解除暂停并将锚点移至该块起点使其可见。"""
        pager = self.frontend.pager
        count = 0
        while pager.hold == "none" and count < LIMIT:
            count += 1
            self.chunk(f"line {count}")
        self.assertEqual(pager.hold, "unit")
        textbox = self.textbox
        self.assertIsNotNone(textbox.bbox("pager.anchor"))
        self.assertIsNotNone(textbox.bbox("pager.unit - 1c"))
        first, last = textbox.tag_ranges("pager.hidden")
        self.assertEqual(str(first), textbox.index("pager.unit"))
        hidden = textbox.get(first, last)
        self.assertTrue(hidden.startswith(f"line {count}\n"), hidden)
        self.assertNotIn(f"line {count - 1}\n", hidden)
        self.assertIsNone(textbox.bbox(f"{first} + 1c"))
        self.click()
        self.assertEqual(pager.hold, "none")
        self.assertEqual(textbox.tag_ranges("pager.hidden"), ())
        self.assertIsNotNone(textbox.bbox("pager.anchor"))
        self.assertIsNotNone(textbox.bbox(f"{first} + 1c"))
        self.assertEqual(textbox.index("pager.anchor"), str(first))

    def test_oversize_chunk_shows_one_screen_per_click(self) -> None:
        """断言约三屏高的单块输出至少停在 "page" 状态两次且每次锚点位于视口顶部，全部点完后回到 "none" 且末行可见。"""
        renderer = self.frontend.renderer
        pager = self.frontend.pager
        textbox = self.textbox
        viewport = renderer.fit().viewport
        line = renderer.fit().used
        lines = [f"row {index}" for index in range(3 * viewport // line)]
        self.chunk(*lines)
        pages = 0
        while pager.hold == "page" and pages < LIMIT:
            pages += 1
            self.assertEqual(
                textbox.index("@0,0"), textbox.index("pager.anchor")
            )
            self.click()
        self.assertGreaterEqual(pages, 2)
        self.assertEqual(pager.hold, "none")
        self.assertIsNotNone(textbox.bbox("pager.anchor"))
        self.assertIsNotNone(textbox.bbox("end - 2c"))

    def test_wrapped_line_counts_every_display_row(self) -> None:
        """断言 5000 字符的长折行带来的未读高度增量大于 3 倍单短行高度。"""
        renderer = self.frontend.renderer
        renderer.anchor_to_end()
        self.chunk("x")
        row = renderer.fit().used
        self.assertGreater(row, 0)
        renderer.anchor_to_end()
        before = renderer.fit().used
        self.chunk("x" * 5000)
        self.assertGreater(self.grow(before), 3 * row)

    def test_image_counts_its_pixel_height(self) -> None:
        """断言内联图片输出后从锚点到文本末尾的未读高度不小于该图片自身的像素高度。"""
        from Script.Core import image_catalog
        from Script.Frontend.Tk import image_cache

        name = next(iter(image_catalog.image_path_data))
        height = image_cache.image_data[name].height()
        renderer = self.frontend.renderer
        renderer.anchor_to_end()
        self.io.image_print(name)
        self.io.flush()
        self.pump()
        self.assertGreaterEqual(renderer.fit().used, height)

    def test_last_whole_line_of_a_screen_does_not_hold(self) -> None:
        """
        断言刚好填满视口整行数的逐块输出不触发暂停且首末行均在屏内，
        再多输出一行才进入 "unit" 暂停。
        """
        renderer = self.frontend.renderer
        pager = self.frontend.pager
        textbox = self.textbox
        renderer.anchor_to_end()
        self.chunk("row 0")
        row = renderer.fit().used
        viewport = renderer.fit().viewport
        for index in range(1, viewport // row):
            self.chunk(f"row {index}")
        self.assertEqual(renderer.fit().used, viewport // row * row)
        self.assertEqual(pager.hold, "none")
        top = textbox.dlineinfo("pager.anchor")
        assert top is not None
        self.assertGreaterEqual(top[1], 0)
        self.assertIsNotNone(textbox.bbox("end - 2c"))
        self.chunk("row last")
        self.assertEqual(pager.hold, "unit")

    def test_image_taller_than_the_screen_pages_to_its_end(self) -> None:
        """
        断言末尾无换行的三倍视口高图片进入 "page" 暂停并至少分三屏递增下滚，
        点完后回到 "none" 状态。
        """
        from Script.Frontend.Tk import image_cache

        renderer = self.frontend.renderer
        pager = self.frontend.pager
        viewport = renderer.fit().viewport
        image = tkinter.PhotoImage(
            master=self.frontend.window.root, width=8, height=3 * viewport
        )
        dict.__setitem__(image_cache.image_data, "pager-tall", image)
        self.addCleanup(dict.pop, image_cache.image_data, "pager-tall", None)
        renderer.anchor_to_end()
        self.io.image_print("pager-tall")
        self.io.flush()
        self.pump()
        tops: list[float] = []
        while pager.hold == "page" and len(tops) < LIMIT:
            tops.append(self.textbox.yview()[0])
            self.click()
        self.assertEqual(pager.hold, "none")
        self.assertGreaterEqual(len(tops), 3)
        self.assertEqual(tops, sorted(set(tops)))

    def test_tall_image_after_a_prompt_starts_at_its_top(self) -> None:
        """
        断言无换行提示词后锚点移至末尾再追加三倍视口高图片时进入 "page" 暂停，
        且锚点所在行顶端不超出视口上沿。
        """
        from Script.Frontend.Tk import image_cache

        renderer = self.frontend.renderer
        viewport = renderer.fit().viewport
        image = tkinter.PhotoImage(
            master=self.frontend.window.root, width=8, height=3 * viewport
        )
        dict.__setitem__(image_cache.image_data, "pager-prompt", image)
        self.addCleanup(dict.pop, image_cache.image_data, "pager-prompt", None)
        self.io.era_print("prompt")
        self.io.flush()
        self.pump()
        renderer.anchor_to_end()
        self.io.image_print("pager-prompt")
        self.io.flush()
        self.pump()
        self.assertEqual(self.frontend.pager.hold, "page")
        top = self.textbox.dlineinfo("pager.anchor")
        assert top is not None
        self.assertGreaterEqual(top[1], 0)

    def test_trim_keeps_lines_not_yet_shown(self) -> None:
        """断言触发超限旧行裁剪时不会删到 `ANCHOR` 所在行，未显示的首行仍保留为 "row 0"。"""
        from Script.Config import normal_config

        limit = normal_config.config_normal.text_hight
        self.chunk(*(f"row {index}" for index in range(limit * 12)))
        self.assertEqual(self.frontend.pager.hold, "page")
        anchor = self.textbox.index("pager.anchor")
        self.assertEqual(self.textbox.get(anchor, f"{anchor} lineend"), "row 0")
