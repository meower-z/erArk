"""
前端导入边界守卫测试：用 `ast` 扫描 `Script/` 下除 `Script/Frontend/Tk/` 外的全部 Python 文件，禁止导入 Tk、Tk
图片接口及 Tk 前端模块。
"""

import ast
from pathlib import Path

from tests.fast.base import FastTestCase
from tests.world import ROOT

FRONTEND = Path("Script/Frontend/Tk")
"""允许导入 Tk 依赖的前端包相对路径。"""
BANNED_PREFIXES = ("tkinter", "_tkinter", "PIL.ImageTk", "Script.Frontend.Tk")
"""游戏后端代码中禁止导入的模块前缀元组。"""


def absolute_module(node: ast.ImportFrom, package: str) -> str:
    """
    结合当前文件所属包名解析 `ast.ImportFrom` 节点，将相对导入还原为绝对模块路径

    参数：
    node (ast.ImportFrom) -- 导入语法树节点
    package (str) -- 当前源码文件所在包名，顶层文件为空字符串

    返回值类型：str -- 解析后的模块全名
    """
    if node.level == 0:
        return node.module or ""
    parts = package.split(".") if package else []
    base = parts[: max(len(parts) - node.level + 1, 0)]
    return ".".join([*base, *([node.module] if node.module else [])])


def imported_names(tree: ast.AST, package: str = "") -> list[str]:
    """
    遍历抽象语法树中的导入节点，结合所属包名解析相对导入并返回模块及成员名称列表

    参数：
    tree (ast.AST) -- 待检查的 Python 抽象语法树
    package (str) -- 当前源码文件所在包名，默认为空字符串

    返回值类型：list[str] -- 提取出的导入名称列表
    """
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = absolute_module(node, package)
            names.append(module)
            names.extend(f"{module}.{alias.name}" for alias in node.names)
    return names


def banned(name: str) -> bool:
    """
    判断单条导入名称是否命中禁止前缀

    参数：
    name (str) -- 待检查的导入名称

    返回值类型：bool -- 命中禁用规则时返回 True，否则返回 False
    """
    return any(
        name == prefix or name.startswith(prefix + ".")
        for prefix in BANNED_PREFIXES
    )


def violations() -> list[str]:
    """
    扫描 `Script/` 下前端包之外的全部 `.py` 文件，收集所有违规导入记录

    参数：无

    返回值类型：list[str] -- 形如 "相对路径: 模块名" 的违规列表
    """
    found = []
    root = Path(ROOT)
    for path in sorted((root / "Script").rglob("*.py")):
        relative = path.relative_to(root)
        if relative.is_relative_to(FRONTEND):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), str(relative))
        package = ".".join(relative.parent.parts)
        found.extend(
            f"{relative.as_posix()}: {name}"
            for name in imported_names(tree, package)
            if banned(name)
        )
    return found


class FrontendBoundaryGuardTest(FastTestCase):
    """验证游戏后端代码不导入任何 Tk 相关模块，且守卫匹配规则能检出每类禁用导入。"""

    def test_backend_imports_no_tk_module(self) -> None:
        """断言 `Script/` 除 Tk 前端包外的全部源码文件不存在违规导入。"""
        self.assertEqual(violations(), [])

    def test_guard_flags_each_banned_import(self) -> None:
        """用固定源码样本断言 `imported_names` 与 `banned` 准确检出每类禁用导入并放行允许导入。"""
        source = "\n".join(
            (
                "import tkinter.font",
                "from _tkinter import TclError",
                "from PIL import ImageTk",
                "from Script.Frontend.Tk import app",
                "from ..Frontend.Tk import app",
                "from .. import Frontend",
                "from PIL import Image",
                "from Script.Core import io_init",
                "from . import flow_handle",
            )
        )
        flagged = [
            name
            for name in imported_names(ast.parse(source), "Script.Core")
            if banned(name)
        ]
        self.assertEqual(
            flagged,
            [
                "tkinter.font",
                "_tkinter",
                "_tkinter.TclError",
                "PIL.ImageTk",
                "Script.Frontend.Tk",
                "Script.Frontend.Tk.app",
                "Script.Frontend.Tk",
                "Script.Frontend.Tk.app",
            ],
        )
