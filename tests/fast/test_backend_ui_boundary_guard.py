"""
后端目录界面边界守卫测试
========================
通过语法树检查 BACKEND_UI_FREE_DIRS 下的源码是否导入了 BANNED 中的界面或输入输出模块。
"""

import ast
from importlib.util import resolve_name
from pathlib import Path, PurePosixPath

from tests.fast.base import FastTestCase

ROOT = Path(__file__).resolve().parents[2]
""" 仓库根目录路径 """
BACKEND_UI_FREE_DIRS = (
    "Script/Config",
    "Script/Design/handle_premise",
    "Script/Kernel",
    "Script/Modules/domains",
    "Script/Modules/gameplay_resolution",
    "Script/Modules/save_load",
    "Script/Protocol",
    "Script/StateMachine",
)
""" 禁止导入界面与输入输出模块的后端目录 """
BANNED = (
    "Script.UI",
    "Script.Core.flow_handle",
    "Script.Core.image_cache",
    "Script.Core.io_init",
    "Script.Core.key_listion_event",
    "Script.Core.main_frame",
    "Script.Core.py_cmd",
    "Script.Frontend",
    "Script.Modules.tk_ui",
    "tkinter",
    "_tkinter",
    "PIL.ImageTk",
)
""" 禁止后端目录导入的界面、输入输出与 Tk（窗口、事件、图像、适配）模块（含子模块） """
ALLOWED = frozenset(
    {
        (
            "Script/Modules/save_load/kernel_state.py",
            "Script.Modules.tk_ui.orders",
        )
    }
)
""" 免于报出的 (仓库相对路径, 模块全名) 集合，对指定文件放行该模块及其成员 """


def _under(name: str, root: str) -> bool:
    return name == root or name.startswith(root + ".")


def _reported(name: str, path: str) -> bool:
    return any(_under(name, root) for root in BANNED) and not any(
        path == file and _under(name, module) for file, module in ALLOWED
    )


def banned_imports(source: str | bytes, path: str) -> list[tuple[int, str]]:
    """
    解析源码语法树，找出命中 BANNED 且未在 ALLOWED 中放行的导入语句。
    Keyword arguments:
    source -- 待检查的 Python 源码
    path -- 文件的仓库相对路径，用于解析相对导入与匹配 ALLOWED
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
        hits = [name for name in names if _reported(name, path)]
        if hits:
            found.append((node.lineno, hits[0]))
    return sorted(found)


def violations() -> list[str]:
    """
    扫描 BACKEND_UI_FREE_DIRS 下的 .py 文件，收集命中的违规导入。
    Return arguments:
    list -- 形如 "相对路径:行号: 模块全名" 的违规记录列表
    """
    found: list[str] = []
    for folder in BACKEND_UI_FREE_DIRS:
        for path in sorted((ROOT / folder).rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            found.extend(
                f"{relative}:{line}: {name}"
                for line, name in banned_imports(path.read_bytes(), relative)
            )
    return found


class BackendUiBoundaryGuardTest(FastTestCase):
    """验证后端目录不导入界面与输入输出模块"""

    def test_backend_dirs_import_no_ui(self) -> None:
        """断言 BACKEND_UI_FREE_DIRS 下不存在导入 BANNED 模块的语句"""
        self.assertEqual(violations(), [])

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
                "from Script.Core import main_frame",
                "from ...Core import main_frame",
                "import Script.Core.key_listion_event",
                "from ...Core import key_listion_event",
                "from Script.Core.image_cache import image_data",
                "from ...Core import image_cache",
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
                (20, "Script.Core.main_frame"),
                (21, "Script.Core.main_frame"),
                (22, "Script.Core.key_listion_event"),
                (23, "Script.Core.key_listion_event"),
                (24, "Script.Core.image_cache.image_data"),
                (25, "Script.Core.image_cache"),
            ],
        )

    def test_checker_resolves_relative_imports_in_package_init(self) -> None:
        """验证检查函数按所在包解析 __init__.py 中的相对导入，检出禁用导入并放行同包导入"""
        source = "from ..UI.Moudle import draw\nfrom . import core"
        self.assertEqual(
            banned_imports(source, "Script/Kernel/__init__.py"),
            [(1, "Script.UI.Moudle.draw")],
        )

    def test_allowed_import_is_narrow(self) -> None:
        """验证 ALLOWED 仅放行 kernel_state.py 导入 orders 及其成员，不放行其余模块或其他文件"""
        source = "\n".join(
            (
                "from Script.Modules.tk_ui import orders",
                "from ..tk_ui import orders",
                "from Script.Modules.tk_ui import callbacks",
                "import Script.Modules.tk_ui",
                "from Script.Modules.tk_ui.orders import settled",
                "from Script.Modules.tk_ui import orders_extra",
            )
        )
        self.assertEqual(
            banned_imports(source, "Script/Modules/save_load/kernel_state.py"),
            [
                (3, "Script.Modules.tk_ui.callbacks"),
                (4, "Script.Modules.tk_ui"),
                (6, "Script.Modules.tk_ui.orders_extra"),
            ],
        )
        self.assertEqual(
            banned_imports(source, "Script/Modules/save_load/reset.py"),
            [
                (1, "Script.Modules.tk_ui.orders"),
                (2, "Script.Modules.tk_ui.orders"),
                (3, "Script.Modules.tk_ui.callbacks"),
                (4, "Script.Modules.tk_ui"),
                (5, "Script.Modules.tk_ui.orders.settled"),
                (6, "Script.Modules.tk_ui.orders_extra"),
            ],
        )
