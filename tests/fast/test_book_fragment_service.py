"""
书籍片段提示测试
================
- 片段输出：验证无摘录时静默且随机状态不变、单条与多条摘录经提示回调绘出默认样式 NormalDraw，以及无回调时静默。
- 口上调用：验证屏蔽读书面板时玩家读书发出摘录提示，非玩家读书与玩家其他行为不发出提示。
- 导入边界：验证口上模块不导入读书面板，以及屏蔽界面与 Tk 模块的子进程可独立运行摘录服务。
"""

import ast
import json
import random
import subprocess
import sys
from importlib.util import resolve_name
from typing import Any
from unittest import mock

from Script.Config import game_config
from Script.Core import constant, io_init
from Script.Design import talk
from Script.Kernel import core
from Script.Modules.domains import activity
from Script.Modules.gameplay_resolution import library_service, ui_hooks
from Script.Modules.gameplay_resolution import working
from Script.Modules.tk_ui import callbacks
from Script.UI import Panel
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

ONE = 9001
""" 仅含一条摘录的测试书籍编号（9001）。 """
MANY = 9002
""" 含四条摘录的测试书籍编号（9002）。 """
EMPTY = 9003
""" 摘录列表为空的测试书籍编号（9003）。 """
MISSING = 9004
""" 未在摘录表中登记的测试书籍编号（9004）。 """
EXCERPTS = {ONE: ["独段"], MANY: ["甲段", "乙段", "丙段", "丁段"], EMPTY: []}
""" 测试用书籍编号到摘录列表的映射表。 """
SEED = 7
""" 验证随机抽取与随机状态一致性的固定随机种子（7）。 """
PANEL = "Script.UI.Panel.read_book_panel"
""" 边界测试禁止口上模块导入的读书面板模块名。 """

type Drawn = tuple[str, float, str, str]
""" 单次绘制记录的元组类型，依次为绘制类名、宽度、样式名与文本。 """


def framed(fragment: str) -> str:
    """返回为摘录正文 fragment 添加首尾换行与省略号边框后的预期提示文本。"""
    return f"\n……{fragment}……\n"


class BookCase(FastTestCase):
    """书籍片段测试基类，准备测试角色与摘录表，并接管提示回调与界面绘制调用。"""

    def setUp(self) -> None:
        """初始化玩家与测试干员、注入测试摘录表，接管提示回调并拦截各绘制类与 era_print。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "测试干员")
        self.enterContext(
            mock.patch.dict(game_config.config_book_excerpt_list, EXCERPTS)
        )
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.drawn: list[Drawn] = []
        self.direct: list[Drawn] = []
        self.inside = False
        self.enterContext(mock.patch.object(ui_hooks, "_notices", [self.relay]))
        for cls in vars(draw).values():
            if isinstance(cls, type) and hasattr(cls, "draw"):
                self.enterContext(
                    mock.patch.object(
                        cls, "draw", autospec=True, side_effect=self.keep
                    )
                )
        self.enterContext(
            mock.patch.object(io_init, "era_print", side_effect=self.printed)
        )

    def relay(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """记录收到的提示参数，置位回调标记并转发给 Tk 回调 callbacks.draw_notice。"""
        self.notices.append((text, wait, style, use_text_width))
        self.inside = True
        try:
            callbacks.draw_notice(
                text, wait=wait, style=style, use_text_width=use_text_width
            )
        finally:
            self.inside = False

    def keep(self, now: object) -> None:
        """按是否处于提示回调内，将绘制对象的类名、宽度、样式名与文本记入对应列表。"""
        drawn = (
            type(now).__name__,
            getattr(now, "width", 0),
            getattr(now, "style", ""),
            getattr(now, "text", ""),
        )
        (self.drawn if self.inside else self.direct).append(drawn)

    def printed(self, string: str, *args: Any, **kwargs: Any) -> None:
        """记录直接调用 io_init.era_print 输出的文本到直接绘制列表。"""
        self.direct.append(("era_print", 0, "", string))


class FragmentTest(BookCase):
    """library_service.draw_book_fragment 的摘录选取、提示绘制与静默场景测试。"""

    def test_no_excerpts_emits_nothing(self) -> None:
        """验证书籍缺失或摘录列表为空时不发提示、不触发绘制，且不改变随机状态。"""
        for book_id in (MISSING, EMPTY):
            with self.subTest(book_id=book_id):
                random.seed(SEED)
                before = random.getstate()
                library_service.draw_book_fragment(book_id)
                self.assertEqual(
                    (self.notices, self.drawn, self.direct), ([], [], [])
                )
                self.assertEqual(random.getstate(), before)

    def test_excerpt_drawn_as_notice(self) -> None:
        """
        验证单条与多条摘录场景均发出单条默认选项提示、回调绘出零宽 standard 样式 NormalDraw、
        无直接绘制且随机状态与独立生成器一致。
        """
        for book_id in (ONE, MANY):
            with self.subTest(book_id=book_id):
                self.notices.clear()
                self.drawn.clear()
                rng = random.Random(SEED)
                text = framed(rng.choice(EXCERPTS[book_id]))
                random.seed(SEED)
                library_service.draw_book_fragment(book_id)
                self.assertEqual(self.notices, [(text, False, None, False)])
                self.assertEqual(
                    self.drawn, [("NormalDraw", 0, "standard", text)]
                )
                self.assertEqual(self.direct, [])
                self.assertTrue(random.getstate() == rng.getstate())

    def test_no_listener_is_silent(self) -> None:
        """验证未登记提示回调时调用 draw_book_fragment 不产生提示也不触发绘制。"""
        with mock.patch.object(ui_hooks, "_notices", []):
            library_service.draw_book_fragment(ONE)
        self.assertEqual((self.notices, self.drawn, self.direct), ([], [], []))


class TalkCallerTest(BookCase):
    """口上输出函数 talk.handle_talk_draw 对书籍摘录服务的调用条件测试。"""

    def talk(self, character_id: int, behavior_id: str) -> None:
        """设置角色当前书籍为 ONE 并在屏蔽读书面板后调用真实 talk.handle_talk_draw。"""
        with working.based_on(core.state()):
            activity.update_behavior(character_id, book_id=ONE)
            with (
                mock.patch.dict(sys.modules, {PANEL: None}),
                mock.patch.object(Panel, "read_book_panel", None, create=True),
            ):
                talk.handle_talk_draw(
                    character_id, "口上", "", common_behavior_id=behavior_id
                )

    def test_player_reading_shows_excerpt(self) -> None:
        """验证玩家执行 READ_BOOK 行为时经口上流程发出单条带边框摘录提示。"""
        self.talk(0, constant.Behavior.READ_BOOK)
        self.assertEqual(self.notices, [(framed("独段"), False, None, False)])

    def test_other_cases_show_no_excerpt(self) -> None:
        """验证非玩家读书或玩家执行 SHARE_BLANKLY 行为时不发出摘录提示。"""
        for character_id, behavior_id in (
            (1, constant.Behavior.READ_BOOK),
            (0, constant.Behavior.SHARE_BLANKLY),
        ):
            with self.subTest(
                character_id=character_id, behavior_id=behavior_id
            ):
                self.talk(character_id, behavior_id)
                self.assertEqual(self.notices, [])


BLOCKED_RUN = """
import importlib.abc, json, sys

BLOCKED = ("Script.UI", "Script.Core.io_init", "Script.Modules.tk_ui", "tkinter", "_tkinter")

def blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)

class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            raise ImportError(fullname)
        return None

sys.meta_path.insert(0, Block())
from Script.Config import game_config
from Script.Modules.gameplay_resolution import library_service, ui_hooks

game_config.config_book_excerpt_list[9001] = ["独段"]
texts = []
ui_hooks._notices[:] = [lambda text, **_: texts.append(text)]
library_service.draw_book_fragment(9001)
print(json.dumps([texts, sorted(m for m in sys.modules if blocked(m))]))
"""
"""
子进程脚本：屏蔽界面、输入输出与 Tk 模块后导入图书馆服务，
运行 draw_book_fragment 并输出提示列表与误加载模块列表。
"""


class BoundaryTest(FastTestCase):
    """口上模块的读书面板导入边界与图书馆服务的无界面子进程运行测试。"""

    def test_talk_imports_no_read_book_panel(self) -> None:
        """验证 Script/Design/talk.py 的源码不以绝对、from 或相对形式导入读书面板模块及其子路径。"""
        path = "Script/Design/talk.py"
        package = "Script.Design"
        names: set[str] = set()
        for node in ast.walk(ast.parse((ROOT / path).read_bytes())):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = resolve_name(
                    "." * node.level + (node.module or ""), package
                )
                names.update(f"{base}.{alias.name}" for alias in node.names)
        self.assertEqual(
            sorted(
                name
                for name in names
                if name == PANEL or name.startswith(PANEL + ".")
            ),
            [],
        )

    def test_service_runs_with_ui_blocked(self) -> None:
        """验证在屏蔽界面与 Tk 模块的子进程中调用 draw_book_fragment 可正常输出单条摘录且零误加载。"""
        result = subprocess.run(
            [sys.executable, "-c", BLOCKED_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(
            json.loads(result.stdout.splitlines()[-1]),
            [[framed("独段")], []],
        )
