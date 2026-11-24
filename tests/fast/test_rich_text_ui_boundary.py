"""
富文本核心层与界面绘制层边界及行为测试
======================================
验证 Script/Core/rich_text.py 不导入界面或 Tk 模块且不含界面绘制构造函数，
在独立子进程中可无界面依赖地导入；同时验证纯解析/配色函数与
Script/UI/Moudle/rich_text_draw.py 绘制构造函数的行为契约。
"""

import importlib
import subprocess
import sys

from Script.Core import rich_text
from Script.UI.Moudle import draw, panel
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports

ISOLATED_IMPORT_SCRIPT = """
import importlib.abc
import sys

BLOCKED = ("Script.UI", "tkinter", "_tkinter")


class BlockUi(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        for root in BLOCKED:
            if fullname == root or fullname.startswith(root + "."):
                raise ImportError(f"blocked ui import: {fullname}")
        return None


sys.meta_path.insert(0, BlockUi())
import Script.Core.rich_text as rt

loaded = sorted(
    name
    for name in sys.modules
    if any(
        name == root or name.startswith(root + ".")
        for root in BLOCKED
    )
)
print(loaded)
print(rt.remove_rich_cache("<green>ok</green>"))
"""
"""独立子进程验证脚本，拦截 Script.UI 与 Tk 导入后加载 Script.Core.rich_text。"""


def _load_rich_text_draw():
    """按模块名加载 Script.UI.Moudle.rich_text_draw。"""
    return importlib.import_module("Script.UI.Moudle.rich_text_draw")


class RichTextImportBoundaryTest(FastTestCase):
    """验证 Script/Core/rich_text.py 与界面绘制层的静态及运行时隔离。"""

    def test_rich_text_source_imports_no_ui(self) -> None:
        """断言 Script/Core/rich_text.py 不导入 BANNED 模块且不暴露绘制构造函数。"""
        relative = "Script/Core/rich_text.py"
        source = (ROOT / relative).read_bytes()
        self.assertEqual(banned_imports(source, relative), [])
        self.assertFalse(hasattr(rich_text, "get_rich_text_draw_panel"))
        self.assertFalse(hasattr(rich_text, "get_rich_text_draw_list"))

    def test_rich_text_subprocess_import_is_ui_free(self) -> None:
        """断言独立子进程拦截 Script.UI 与 Tk 后仍可正常导入并使用 Script.Core.rich_text。"""
        result = subprocess.run(
            [sys.executable, "-c", ISOLATED_IMPORT_SCRIPT],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-2:], ["[]", "ok"])


class RichTextCoreBehaviorTest(FastTestCase):
    """验证 Script/Core/rich_text.py 保留的解析、清标签与配色函数行为。"""

    def test_get_rich_text_print_and_remove_rich_cache(self) -> None:
        """验证纯文本、嵌套颜色与修饰标签、未知标签、未闭合尖括号及转义换行解析一致。"""
        self.assertEqual(
            rich_text.get_rich_text_print("abc", "standard"),
            ["standard", "standard", "standard"],
        )
        tagged = "<green>hi</green><green><bold><italic>x</italic></bold></green><unknown>!</unknown>"
        self.assertEqual(
            rich_text.remove_rich_cache(tagged),
            "hix!",
        )
        self.assertEqual(
            rich_text.get_rich_text_print(tagged, "standard"),
            ["green", "green", "green_bold_italic", "standard"],
        )
        self.assertEqual(
            rich_text.get_rich_text_print("<bold>x</bold>", "unregistered"),
            [("unregistered", "bold")],
        )
        self.assertEqual(
            rich_text.get_rich_text_print("<green>a<b", "standard"),
            ["green", "green", "green"],
        )
        self.assertEqual(
            rich_text.remove_rich_cache("a\\nb"),
            "a\nb",
        )
        self.assertEqual(
            rich_text.get_rich_text_print("a\\nb", "standard"),
            ["standard", "standard", "standard"],
        )

    def test_character_state_and_unconscious_colors(self) -> None:
        """验证角色状态颜色与无意识状态颜色在各分支返回预期样式名。"""
        self.assertEqual(
            rich_text.get_chara_state_rich_color(0), "persian_pink"
        )
        for state_id in (12, 13):
            self.assertEqual(
                rich_text.get_chara_state_rich_color(state_id), "rose_pink"
            )
        for state_id in (14, 15, 16):
            self.assertEqual(
                rich_text.get_chara_state_rich_color(state_id), "deep_pink"
            )
        self.assertEqual(rich_text.get_chara_state_rich_color(17), "crimson")
        for state_id in (18, 19, 20):
            self.assertEqual(
                rich_text.get_chara_state_rich_color(state_id), "slate_blue"
            )
        self.assertEqual(
            rich_text.get_chara_state_rich_color(8), "pale_cerulean"
        )
        self.assertEqual(
            rich_text.get_chara_unconscious_rich_color(0), "standard"
        )
        self.assertEqual(
            rich_text.get_chara_unconscious_rich_color(1),
            "little_dark_slate_blue",
        )
        self.assertEqual(
            rich_text.get_chara_unconscious_rich_color(3), "light_sky_blue"
        )
        self.assertEqual(
            rich_text.get_chara_unconscious_rich_color(2), "standard"
        )


class RichTextDrawBuilderTest(FastTestCase):
    """验证 Script/UI/Moudle/rich_text_draw.py 构造绘制列表与绘制面板的行为。"""

    def test_draw_list_empty_and_single_newline(self) -> None:
        """验证空文本返回空列表，单换行符按 base_style 返回单条 NormalDraw。"""
        rich_text_draw = _load_rich_text_draw()
        self.assertEqual(rich_text_draw.get_rich_text_draw_list(""), [])
        single = rich_text_draw.get_rich_text_draw_list(
            "\n", base_style="green", wait_flag=True
        )
        self.assertEqual(len(single), 1)
        self.assertIs(type(single[0]), draw.NormalDraw)
        self.assertEqual((single[0].text, single[0].style), ("\n", "green"))

    def test_draw_list_merges_styles_and_respects_wait_flag(self) -> None:
        """验证连续同样式合并、换行单独拆分以及 wait_flag 切换换行绘制类。"""
        rich_text_draw = _load_rich_text_draw()
        plain = rich_text_draw.get_rich_text_draw_list(
            "hello", base_style="green"
        )
        self.assertEqual(
            [(type(item), item.text, item.style) for item in plain],
            [
                (draw.NormalDraw, "hello", "green"),
                (draw.NormalDraw, "\n", "green"),
            ],
        )
        sample = "<green>hi</green><bold>yo</bold>\n<semen>end</semen>"
        normal_items = rich_text_draw.get_rich_text_draw_list(
            sample, base_style="standard", wait_flag=False
        )
        self.assertEqual(
            [(type(item), item.text, item.style) for item in normal_items],
            [
                (draw.NormalDraw, "hi", "green"),
                (draw.NormalDraw, "yo", "standard_bold"),
                (draw.NormalDraw, "\n", "standard"),
                (draw.NormalDraw, "end", "semen"),
                (draw.NormalDraw, "\n", "standard"),
            ],
        )
        wait_items = rich_text_draw.get_rich_text_draw_list(
            sample, base_style="standard", wait_flag=True
        )
        self.assertEqual(
            [(type(item), item.text, item.style) for item in wait_items],
            [
                (draw.NormalDraw, "hi", "green"),
                (draw.NormalDraw, "yo", "standard_bold"),
                (draw.LineFeedWaitDraw, "\n", "standard"),
                (draw.NormalDraw, "end", "semen"),
                (draw.LineFeedWaitDraw, "\n", "standard"),
            ],
        )

    def test_draw_panel_empty_and_nonempty(self) -> None:
        """验证 get_rich_text_draw_panel 构造 LeftDrawTextListPanel 的列表内容与宽度累加。"""
        rich_text_draw = _load_rich_text_draw()
        empty_panel = rich_text_draw.get_rich_text_draw_panel("")
        self.assertIsInstance(empty_panel, panel.LeftDrawTextListPanel)
        self.assertEqual(empty_panel.draw_list, [])
        self.assertEqual(empty_panel.width, 0)

        filled_panel = rich_text_draw.get_rich_text_draw_panel(
            "<green>你好</green>ab"
        )
        self.assertIsInstance(filled_panel, panel.LeftDrawTextListPanel)
        self.assertEqual(len(filled_panel.draw_list), 1)
        row = filled_panel.draw_list[0]
        self.assertEqual(
            [(type(item), item.text, item.style) for item in row],
            [
                (draw.NormalDraw, "你好", "green"),
                (draw.NormalDraw, "ab", "standard"),
                (draw.NormalDraw, "\n", "standard"),
            ],
        )
        self.assertEqual(filled_panel.width, 5)
