"""
后端界面边界守卫测试
====================
通过语法树检查 BACKEND_UI_FREE_DIRS 下的 .py 文件与 BACKEND_UI_FREE_FILES 中的文件
是否导入了 BANNED 中的界面、输入输出与 Tk 模块。
"""

import ast
from collections import Counter
from importlib.util import resolve_name
from pathlib import Path, PurePosixPath
from unittest import mock

from tests.fast.base import FastTestCase

ROOT = Path(__file__).resolve().parents[2]
""" 仓库根目录路径 """
BACKEND_UI_FREE_DIRS = (
    "Script/Config",
    "Script/Core/constant",
    "Script/Design",
    "Script/Kernel",
    "Script/Modules/domains",
    "Script/Modules/gameplay_resolution",
    "Script/Modules/npc_action_choice",
    "Script/Modules/save_load",
    "Script/Protocol",
    "Script/Settle",
    "Script/StateMachine",
    "Script/System",
    "Script/Test",
)
""" 禁止导入界面与输入输出模块的后端目录 """
BACKEND_UI_FREE_FILES = (
    "Script/Core/constant_effect.py",
    "Script/Core/constant_promise.py",
    "Script/Core/dijkstra.py",
    "Script/Core/game_path_config.py",
    "Script/Core/game_type.py",
    "Script/Core/get_text.py",
    "Script/Core/image_catalog.py",
    "Script/Core/image_path_index.py",
    "Script/Core/input_cache.py",
    "Script/Core/json_handle.py",
    "Script/Core/mod_manager.py",
    "Script/Core/num.py",
    "Script/Core/old_chara_to_new.py",
    "Script/Core/rich_text.py",
    "Script/Core/save_handle.py",
    "Script/Core/text_handle.py",
    "Script/Core/value_handle.py",
    "Script/Modules/__init__.py",
)
""" 禁止导入界面与输入输出模块的单个后端文件 """
BANNED = (
    "Script.UI",
    "Script.Core.flow_handle",
    "Script.Core.io_init",
    "Script.Core.py_cmd",
    "Script.Frontend",
    "Script.Modules.tk_ui",
    "tkinter",
    "_tkinter",
    "PIL.ImageTk",
)
""" 禁止后端目录导入的界面、输入输出与 Tk（窗口、事件、图像、适配）模块（含子模块） """


def _reported(name: str) -> bool:
    return any(name == root or name.startswith(root + ".") for root in BANNED)


def banned_imports(source: str | bytes, path: str) -> list[tuple[int, str]]:
    """
    解析源码语法树，找出命中 BANNED 的导入语句。
    Keyword arguments:
    source -- 待检查的 Python 源码
    path -- 文件的仓库相对路径，用于解析相对导入
    Return arguments:
    list -- 排序后的 (行号, 首个报出的解析后模块全名) 列表，每条语句至多一项
    """
    package = ".".join(PurePosixPath(path).parent.parts)
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package)
            names = [f"{base}.{alias.name}" for alias in node.names]
        else:
            continue
        hits = [name for name in names if _reported(name)]
        if hits:
            found.append((node.lineno, hits[0]))
    return sorted(found)


def guarded_files() -> list[str]:
    """
    收集 BACKEND_UI_FREE_DIRS 下的 .py 文件与 BACKEND_UI_FREE_FILES 所列文件的路径。
    Return arguments:
    list -- 仓库相对路径列表，先按目录顺序列出各目录内排序后的 .py 文件，再接单文件列表
    """
    found = [
        path.relative_to(ROOT).as_posix()
        for folder in BACKEND_UI_FREE_DIRS
        for path in sorted((ROOT / folder).rglob("*.py"))
    ]
    return found + list(BACKEND_UI_FREE_FILES)


def violations() -> list[str]:
    """
    读取 guarded_files() 返回的源码文件，收集命中 BANNED 的导入语句。
    Return arguments:
    list -- 形如 "相对路径:行号: 模块全名" 的违规记录列表
    """
    return [
        f"{relative}:{line}: {name}"
        for relative in guarded_files()
        for line, name in banned_imports(
            (ROOT / relative).read_bytes(), relative
        )
    ]


class BackendUiBoundaryGuardTest(FastTestCase):
    """验证后端目录不导入界面与输入输出模块"""

    def test_backend_sources_import_no_ui(self) -> None:
        """断言 guarded_files() 返回的源码中不存在导入 BANNED 模块的语句"""
        self.assertEqual(violations(), [])

    def test_scan_entries_are_distinct_and_nonempty(self) -> None:
        """断言守卫目录均含 .py 文件、单文件条目均为存在的 .py 文件，且 guarded_files() 无重复路径"""
        for folder in BACKEND_UI_FREE_DIRS:
            self.assertTrue(any((ROOT / folder).rglob("*.py")), folder)
        for file in BACKEND_UI_FREE_FILES:
            self.assertTrue(
                file.endswith(".py") and (ROOT / file).is_file(), file
            )
        counts = Counter(guarded_files())
        self.assertEqual([file for file, n in counts.items() if n > 1], [])

    def test_violations_scan_file_entries(self) -> None:
        """断言在内存中为 BACKEND_UI_FREE_FILES 注入禁用导入后，violations() 按序报出各条目"""

        def inject(path: Path) -> bytes:
            relative = path.relative_to(ROOT).as_posix()
            if relative in BACKEND_UI_FREE_FILES:
                return b"import tkinter\n"
            return b""

        with mock.patch.object(
            Path, "read_bytes", autospec=True, side_effect=inject
        ):
            found = violations()
        self.assertEqual(
            found, [f"{file}:1: tkinter" for file in BACKEND_UI_FREE_FILES]
        )

    def test_checker_resolves_absolute_and_relative_imports(self) -> None:
        """验证检查函数能检出绝对导入、相对导入与函数内导入，并放行仅前缀相近的模块"""
        source = "\n".join(
            (
                "from Script.UI.Moudle import draw",
                "from ...UI.Moudle import draw",
                "from ..save_load import reset",
                "from ... import UI",
                "import tkinter.font",
                "from _tkinter import TclError",
                "from PIL import Image, ImageTk",
                "from Script.Core import save_handle, flow_handle",
                "from ...Core import io_init",
                "import Script.Frontend.Tk",
                "from Script.UIX import widget",
                "def f():",
                "    from Script.UI.Panel import new_round",
                "from Script.Core import py_cmd",
                "from ...Core import py_cmd",
                "import Script.Modules.tk_ui",
                "from Script.Modules.tk_ui import callbacks",
                "from ..tk_ui import callbacks",
                "from Script.Modules.tk_ui import orders",
            )
        )
        self.assertEqual(
            banned_imports(source, "Script/Modules/domains/sample.py"),
            [
                (1, "Script.UI.Moudle.draw"),
                (2, "Script.UI.Moudle.draw"),
                (4, "Script.UI"),
                (5, "tkinter.font"),
                (6, "_tkinter.TclError"),
                (7, "PIL.ImageTk"),
                (8, "Script.Core.flow_handle"),
                (9, "Script.Core.io_init"),
                (10, "Script.Frontend.Tk"),
                (13, "Script.UI.Panel.new_round"),
                (14, "Script.Core.py_cmd"),
                (15, "Script.Core.py_cmd"),
                (16, "Script.Modules.tk_ui"),
                (17, "Script.Modules.tk_ui.callbacks"),
                (18, "Script.Modules.tk_ui.callbacks"),
                (19, "Script.Modules.tk_ui.orders"),
            ],
        )

    def test_checker_resolves_relative_imports_in_package_init(self) -> None:
        """验证检查函数按所在包解析 __init__.py 中的相对导入，检出禁用导入并放行同包导入"""
        source = "from ..UI.Moudle import draw\nfrom . import core"
        self.assertEqual(
            banned_imports(source, "Script/Kernel/__init__.py"),
            [(1, "Script.UI.Moudle.draw")],
        )
