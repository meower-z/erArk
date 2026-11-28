"""
真实 Tk 文本框上的分页停顿
==========================
用 Window._textbox 与 Window._input_bar 搭建三行真实文本框和底栏，接入真实 TkFrontend、Renderer 与 Pager。
后端由替身会话端口驱动，左键点击由输入框或停顿提示上的真实 Tk 事件触发。
各测试核对可见与截断行、停顿提示与布局高度、映射前等待、请求批次不移视图及旧行裁剪。
没有可用显示时跳过测试，不载入游戏也不开新游戏。
"""

import signal
import time
import tkinter
from tkinter import font, ttk
from typing import TYPE_CHECKING
from unittest import mock

from tests.slow import remove_parent_guard
from tests.slow.base import SlowTestCase

if TYPE_CHECKING:
    from Script.Protocol import (
        AttachmentSnapshot,
        BackendEvent,
        Exit,
        RenderChunk,
        RenderOp,
        TextOp,
        UiResponse,
    )

LINES = 3
""" 测试用文本框的高度，单位为行 """
TOKEN = "pager-test"
""" 替身端口附着时使用的鉴权令牌 """
type Chunks = tuple[RenderChunk, ...]
""" RenderChunk 输出块事件元组类型别名 """
type Events = tuple[BackendEvent, ...]
""" BackendEvent 后端事件元组类型别名 """


class Port:
    """替身会话端口，附着时提供回放事件，之后按入队顺序交付事件并接受全部应答"""

    def __init__(self, projection: "tuple[RenderChunk, ...]") -> None:
        """
        保存回放事件并初始化事件队列、应答记录与序号计数
        Keyword arguments:
        projection -- 附着快照包含的回放事件元组
        Return arguments:
        无
        """
        self.projection = projection
        self.out: list[BackendEvent] = []
        self.sent: list[str] = []
        self.seq = len(projection)

    def attach(self, auth_token: str) -> "AttachmentSnapshot":
        """
        构造并返回包含回放事件的附着快照
        Keyword arguments:
        auth_token -- 鉴权令牌，替身端口不做校验
        Return arguments:
        AttachmentSnapshot -- 含回放事件且无挂起请求的附着快照
        """
        from Script.Protocol import AttachmentSnapshot

        return AttachmentSnapshot("s", 1, self.seq, self.projection, None)

    def detach(self, controller_epoch: int) -> None:
        """空操作占位，满足 SessionPort.detach 接口"""

    def drain(
        self, controller_epoch: int, max_events: int = 64
    ) -> "list[BackendEvent]":
        """
        从队列头部取出最多 max_events 条待分发事件
        Keyword arguments:
        controller_epoch -- 控制器代次，替身端口不使用
        max_events -- 单次最多取出的事件条数
        Return arguments:
        list -- 取出的后端事件列表
        """
        events, self.out = self.out[:max_events], self.out[max_events:]
        return events

    def receive(
        self, controller_epoch: int, timeout: float | None = None
    ) -> "BackendEvent | None":
        """弹出并返回队首事件或 None，满足 SessionPort.receive 接口"""
        return self.out.pop(0) if self.out else None

    def pending_exit(self, controller_epoch: int) -> "Exit | None":
        """
        返回待处理退出事件，替身端口始终返回 None
        Keyword arguments:
        controller_epoch -- 控制器代次，替身端口不使用
        Return arguments:
        Exit | None -- 始终为 None
        """
        return None

    def submit(self, response: "UiResponse") -> bool:
        """
        记录应答类型名并返回 True 表示接受
        Keyword arguments:
        response -- 前端提交的协议应答
        Return arguments:
        bool -- 始终返回 True
        """
        self.sent.append(type(response).__name__)
        return True


def text_chunk(seq: int, *ops: "RenderOp") -> "RenderChunk":
    """
    将若干渲染操作封装为单个 RenderChunk 事件
    Keyword arguments:
    seq -- 事件序号
    ops -- 按顺序放入输出块的渲染操作
    Return arguments:
    RenderChunk -- 构造完成的输出块事件
    """
    from Script.Protocol import RenderChunk

    return RenderChunk("s", seq, tuple(ops))


def lines(*names: str) -> "TextOp":
    """
    将多行字符串拼接为每行以换行结尾的单个 TextOp
    Keyword arguments:
    names -- 按顺序写入的各行文本
    Return arguments:
    TextOp -- 包含对应多行文本的渲染操作
    """
    from Script.Protocol import TextOp

    return TextOp("".join(f"{name}\n" for name in names))


class Rig:
    """运行在真实三行 Tk 文本框上的 TkFrontend 测试夹具，支持推送事件、点击与检查可见行"""

    def __init__(self, projection: Chunks = (), startup: Events = ()) -> None:
        """
        创建三行真实文本框与底栏并回放 projection，窗口映射前运行一次事件泵并记录 early，再推进至稳定
        Keyword arguments:
        projection -- 附着快照包含的回放事件元组
        startup -- 启动前已在端口排队的后端事件元组
        Return arguments:
        无
        """
        from Script.Frontend.Tk import app, warmup
        from Script.Frontend.Tk.window import Window
        from Script.Protocol import FrontendInitConfig

        def window(normal):
            shown = Window.__new__(Window)
            shown.root = tkinter.Tk()
            shown.root.geometry("+0+0")
            frame = ttk.Frame(shown.root)
            frame.pack()
            shown.textbox = shown._textbox(frame, normal)
            shown.textbox.configure(height=LINES, width=40)
            shown.order = tkinter.StringVar()
            keys = ("background", "foreground", "selectbackground")
            style: dict = dict.fromkeys(keys, "#000000")
            style.update(font=normal.font, font_size=12)
            shown.inputbox, shown.cue = shown._input_bar(frame, normal, style)
            shown.normal_font = font.Font()
            shown.config = FrontendInitConfig(800, 600, 40, 12, "#000000")
            return shown

        self.port = Port(projection)
        self.port.out.extend(startup)
        with mock.patch.object(app, "Window", window):
            self.front = app.TkFrontend(self.port, TOKEN)
        self.text = self.front.window.textbox
        with (
            mock.patch.object(warmup, "warm_up"),
            mock.patch.object(self.front.window.root, "mainloop"),
        ):
            self.front.run()
        self.front._pump()
        self.early = len(self.port.out), self.text.winfo_height()
        self.settle()

    def close(self) -> None:
        """
        标记前端关闭并销毁 Tk 根窗口
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.front._closed = True
        self.front.window.root.destroy()

    def settle(self) -> None:
        """
        连续运行 15 轮 Tk 窗口更新以驱动事件泵和重绘
        Keyword arguments:
        无
        Return arguments:
        无
        """
        for _ in range(15):
            self.front.window.root.update()
            time.sleep(0.01)

    def seq(self) -> int:
        """
        递增并返回替身端口的下一个事件序号
        Keyword arguments:
        无
        Return arguments:
        int -- 递增后的事件序号
        """
        self.port.seq += 1
        return self.port.seq

    def show(self, *ops) -> None:
        """
        依次推送一个输出块和一个 Choose 请求，并推进 Tk 事件循环至稳定
        Keyword arguments:
        ops -- 放入输出块的渲染操作
        Return arguments:
        无
        """
        from Script.Protocol import Choose

        self.port.out.append(text_chunk(self.seq(), *ops))
        seq = self.seq()
        self.port.out.append(Choose("s", seq, 1, seq, ("1",)))
        self.settle()

    def click(self) -> None:
        """
        在输入框上发送一次真实左键按下事件并推进 Tk 事件循环至稳定
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.front.window.inputbox.event_generate("<ButtonPress-1>", x=2, y=2)
        self.settle()

    def viewport(self) -> int:
        """
        计算文本框扣除边框、高亮边与上下内边距后的可视区域像素高度
        Keyword arguments:
        无
        Return arguments:
        int -- 文本框可视区域的像素高度
        """
        text = self.text
        inset = sum(
            text.winfo_pixels(text.cget(option))
            for option in ("borderwidth", "highlightthickness", "pady")
        )
        return text.winfo_height() - 2 * inset

    def look(self) -> tuple[list[str], list[str]]:
        """
        分别收集当前完整可见与部分可见的文本行，空行或纯图片行记为 <行号>
        Keyword arguments:
        无
        Return arguments:
        tuple[list[str], list[str]] -- 完整可见行列表与部分可见行列表
        """
        text = self.text
        inset = (text.winfo_height() - self.viewport()) // 2
        top, bottom = inset, text.winfo_height() - inset
        full, part = [], []
        last = int(text.index("end-1c").split(".")[0])
        for number in range(1, last + 1):
            index = f"{number}.0"
            info = text.dlineinfo(index)
            if info is None or info[3] == 0:
                continue
            following = f"{index} +1 display lines"
            height = text.count(index, following, "update", "ypixels")
            height = height[0] if isinstance(height, tuple) else height
            y = info[1]
            name = text.get(index, f"{index} lineend") or f"<{number}>"
            if y >= top and y + max(height or 0, info[3]) <= bottom:
                full.append(name)
            elif y + info[3] > top and y < bottom:
                part.append(name)
        return full, part

    def page_through(self, limit: int = 8) -> list[tuple[list[str], list[str]]]:
        """
        在停顿期间反复点击直至停顿解除或达到上限，记录初始与每次点击后的可见行
        Keyword arguments:
        limit -- 允许点击的最大次数
        Return arguments:
        list[tuple[list[str], list[str]]] -- 初始及每次点击后的可见行记录列表
        """
        looks = [self.look()]
        while self.front.pager.hold != "none" and len(looks) <= limit:
            self.click()
            looks.append(self.look())
        return looks


def scrollback() -> tuple:
    """
    构造包含十行旧输出的回放事件元组
    Keyword arguments:
    无
    Return arguments:
    tuple -- 含单个十行 RenderChunk 的元组
    """
    return (text_chunk(1, lines(*[f"old{index}" for index in range(1, 11)])),)


class TkPagerTest(SlowTestCase):
    """在真实 Tk 窗口上验证分页停顿、停顿提示、映射前等待、请求批次不移视图、翻页边界与旧行裁剪"""

    def setUp(self) -> None:
        """
        设置超时闹钟、移除父进程守卫并初始化基础配置，再以临时窗口确认存在可用显示
        Keyword arguments:
        无
        Return arguments:
        无
        """
        signal.signal(signal.SIGALRM, self._time_up)
        signal.alarm(self.time_limit)
        remove_parent_guard()
        from Script.Config import normal_config

        normal_config.init_normal_config()
        try:
            tkinter.Tk().destroy()
        except tkinter.TclError as error:
            self.skipTest(f"没有可用的显示，无法创建 Tk 窗口：{error}")

    def test_block_that_exactly_fills_the_view_shows_every_line(self) -> None:
        """正好占满三行视口的新输出块在视图处于末尾或顶部时都不停顿且完整显示全部三行"""
        for scrolled_up in (False, True):
            rig = Rig(scrollback())
            if scrolled_up:
                rig.text.yview_moveto(0.0)
                rig.settle()
            rig.show(lines("new1", "new2", "new3"))
            self.assertEqual(rig.front.pager.hold, "none")
            self.assertEqual(rig.look(), (["new1", "new2", "new3"], []))
            rig.close()

    def test_one_click_reaches_the_rest_of_a_six_line_block(self) -> None:
        """三行视口内的六行输出块先停在前三行，点击一次后显示后三行并解除停顿"""
        rig = Rig(scrollback())
        rig.show(lines(*[f"l{index}" for index in range(1, 7)]))
        looks = rig.page_through()
        self.assertEqual(
            looks, [(["l1", "l2", "l3"], []), (["l4", "l5", "l6"], [])]
        )

    def test_partly_clipped_bottom_line_opens_the_next_page(self) -> None:
        """底行因半高图片被视口截断时，下一页以该行作为首行完整显示"""
        from Script.Frontend.Tk import image_cache
        from Script.Protocol import ImageOp, TextOp

        rig = Rig(scrollback())
        image_cache.image_data["half"] = tkinter.PhotoImage(
            master=rig.text, width=20, height=rig.viewport() // 2
        )
        rig.show(
            lines("p1", "p2"),
            TextOp("p3"),
            ImageOp("half"),
            lines("", "p4", "p5"),
        )
        first, second, *_ = rig.page_through()
        self.assertEqual(first, (["p1", "p2"], ["p3"]))
        self.assertEqual(second[0][0], "p3")

    def test_tall_image_moves_the_view_on_every_click(self) -> None:
        """高于视口 1.5 倍与 2.5 倍的图片分别经两次与三次点击逐屏下移，末页显示其后的文本行"""
        from Script.Frontend.Tk import image_cache
        from Script.Protocol import ImageOp, TextOp

        for factor, clicks in ((1.5, 2), (2.5, 3)):
            rig = Rig(scrollback())
            image_cache.image_data["tall"] = tkinter.PhotoImage(
                master=rig.text, width=20, height=int(rig.viewport() * factor)
            )
            rig.show(TextOp("top\n"), ImageOp("tall"), TextOp("\nbelow\n"))
            views = [rig.text.yview()[0]]
            while rig.front.pager.hold != "none" and len(views) <= 6:
                rig.click()
                views.append(rig.text.yview()[0])
            self.assertEqual(len(views) - 1, clicks)
            self.assertEqual(views, sorted(set(views)))
            self.assertIn("below", rig.look()[0])
            rig.close()

    def test_hidden_block_reveals_then_pages_then_releases(self) -> None:
        """溢出块隐藏并显示停顿提示，点击提示逐页翻完后提示清空，期间文本框与底栏高度不变且不提交应答"""
        from Script.Frontend.Tk.window import HOLD_CUE

        rig = Rig(scrollback())
        cue = rig.front.window.cue
        before = rig.text.winfo_height(), cue.master.winfo_height()
        rig.port.out.append(text_chunk(rig.seq(), lines("a1", "a2")))
        rig.show(lines(*[f"b{index}" for index in range(1, 6)]))
        looks, sizes = [], set()
        while len(looks) < 6:
            looks.append((*rig.look(), cue.cget("text")))
            sizes.add((rig.text.winfo_height(), cue.master.winfo_height()))
            if rig.front.pager.hold == "none":
                break
            cue.event_generate("<ButtonPress-1>", x=1, y=1)
            rig.settle()
        self.assertEqual(
            looks,
            [
                (["old10", "a1", "a2"], [], HOLD_CUE),
                (["b1", "b2", "b3"], [], HOLD_CUE),
                (["b3", "b4", "b5"], [], ""),
            ],
        )
        self.assertEqual(sizes, {before})
        self.assertEqual(rig.port.sent, [])

    def test_old_lines_are_trimmed_but_unread_lines_stay(self) -> None:
        """单个超限回放块会裁剪旧行并保留末行，未读输出触发超限时仅裁掉锚点之前的旧行"""
        from Script.Config import normal_config
        from Script.Frontend.Tk.render import ANCHOR

        cap = normal_config.config_normal.text_hight * 10
        replay = lines(*[f"r{index}" for index in range(1, cap + 40)])
        rig = Rig((text_chunk(1, replay),))
        self.assertLess(int(rig.text.index("end-1c").split(".")[0]), cap)
        self.assertIn(f"r{cap + 39}", rig.text.get("end-2l", "end"))
        rig.close()
        rig = Rig((text_chunk(1, lines(*[f"o{i}" for i in range(1, 101)])),))
        unread = [f"u{index}" for index in range(1, cap - 50)]
        rig.show(lines(*unread))
        self.assertEqual(rig.front.pager.hold, "page")
        self.assertEqual(rig.text.get("1.0", "1.0 lineend"), "u1")
        self.assertEqual(rig.text.get(ANCHOR, "end-1c").splitlines(), unread)

    def test_startup_output_waits_for_the_mapped_view(self) -> None:
        """窗口映射前的事件泵不拉取端口内的启动事件，映射后对启动输出分页停顿且不分发后续请求"""
        from Script.Protocol import Choose

        rows = lines(*[f"s{index}" for index in range(1, 7)])
        rig = Rig(startup=(text_chunk(1, rows), Choose("s", 2, 1, 2, ("1",))))
        self.assertEqual(rig.early, (2, 1))
        self.assertEqual(rig.front.pager.hold, "page")
        self.assertEqual(rig.look(), (["s1", "s2", "s3"], []))
        self.assertIsNone(rig.front.gate.request)
        rig.close()

    def test_batches_without_output_keep_the_scrollback_view(self) -> None:
        """上翻回看旧输出时，仅含跳过开关、面板同步或输入请求的批次不移动视图"""
        from Script.Protocol import Choose, InputText, Pause, SkipPauses
        from Script.Protocol import SyncPanel

        for event in (
            SkipPauses("s", 2, True),
            Choose("s", 2, 1, 2, ("1",)),
            InputText("s", 2, 1, 2, 8, allow_empty=True),
            Pause("s", 2, 1, 2),
            SyncPanel("s", 2, 1, "settle"),
        ):
            rig = Rig(scrollback())
            rig.text.yview_moveto(0.0)
            rig.port.out.append(event)
            rig.settle()
            self.assertEqual(
                rig.text.yview()[0],
                0.0,
                f"仅含 {type(event).__name__} 的批次移动了视图",
            )
            rig.close()

    def test_skipped_oversized_chunk_is_trimmed(self) -> None:
        """跳过开关开启时，单个超出行数上限的输出块直接计为已读、裁剪旧行并保留末行"""
        from Script.Config import normal_config
        from Script.Protocol import SkipPauses

        cap = normal_config.config_normal.text_hight * 10
        rig = Rig()
        rig.port.out.append(SkipPauses("s", rig.seq(), True))
        rig.show(lines(*[f"x{index}" for index in range(1, cap + 101)]))
        self.assertLess(int(rig.text.index("end-1c").split(".")[0]), cap)
        self.assertIn(f"x{cap + 100}", rig.text.get("end-2l", "end"))
        rig.close()
