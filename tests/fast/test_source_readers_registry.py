# -*- coding: UTF-8 -*-
"""
源码读取者清单的文件与符号校验
==============================
本模块校验 tests/source_readers.toml 里的每条 reader 与 allow 记录。每条记录的 file 字段必须指向仓库里实际存在的文件。
当 symbol 字段不是 <module> 时，对应文件的语法树里必须能按点分路径找到该符号的定义。
"""

import ast
from pathlib import Path
import tomllib

from tests.fast.base import FastTestCase
from tests.world import ROOT

REGISTRY = Path(ROOT) / "tests" / "source_readers.toml"
""" 源码读取者清单 tests/source_readers.toml 的文件路径 """


def defines(tree: ast.Module, symbol: str) -> bool:
    """
    判断模块语法树里是否定义指定符号
    Keyword arguments:
    tree -- 模块语法树
    symbol -- 符号名，模块顶层写作 <module>，其余为点分路径（逐层匹配函数、异步函数或类定义）
    Return arguments:
    bool -- symbol 为 <module> 或逐层找到匹配定义时返回 True，否则返回 False
    """
    if symbol == "<module>":
        return True
    body: list[ast.stmt] = tree.body
    for name in symbol.split("."):
        found = [
            node
            for node in body
            if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            )
            and node.name == name
        ]
        if not found:
            return False
        body = found[0].body
    return True


def unresolved() -> list[str]:
    """
    收集源码读取者清单里文件缺失或符号缺失的 reader 与 allow 记录
    Keyword arguments:
    无
    Return arguments:
    list -- 每条异常记录的报错字符串，末尾以 file missing 或 symbol missing 标明原因
    """
    with REGISTRY.open("rb") as f:
        registry = tomllib.load(f)
    problems = []
    for kind in ("reader", "allow"):
        for row in registry.get(kind, []):
            label = f"{kind} {row.get('id', '-')} {row['file']} {row['symbol']}"
            path = Path(ROOT) / row["file"]
            if not path.is_file():
                problems.append(f"{label}: file missing")
            elif not defines(
                ast.parse(path.read_text(encoding="utf-8")), row["symbol"]
            ):
                problems.append(f"{label}: symbol missing")
    return problems


class SourceReadersRegistryTest(FastTestCase):
    """源码读取者清单的文件与符号校验测试"""

    def test_rows_resolve(self) -> None:
        """
        断言清单里全部 reader 与 allow 记录都能通过文件与符号解析校验
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.assertEqual(unresolved(), [])
