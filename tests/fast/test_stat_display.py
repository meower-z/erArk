# -*- coding: UTF-8 -*-
"""
连续数值显示前先取整
====================
体力、气力、理智等连续数值可以是有理数（num.Num），直接变成文字会显示成 7/2 这样的分数。
扫描 Script 下全部 .py：f-string 的字段、str() 的参数、字符串 % 的右边、.format() 的参数里
读到这些数值时，要包在 shown(...) 里。
读取先经过 int()、round()、加减等运算再变成文字也算；先交给别的函数（如求等级）或作为下标的不算。
"""

import ast
import pathlib

from tests.fast.base import FastTestCase
from tests.world import ROOT

PLAIN = frozenset(
    {
        "hit_point",
        "mana_point",
        "sanity_point",
        "eja_point",
        "semen_point",
        "sleep_point",
        "drunk_point",
        "absorbed_total_semen",
        "today_sanity_point_cost",
    }
)
""" 存 Num 的属性名（读到属性本身就是数值） """
PASS_THROUGH = frozenset({"int", "float", "round", "abs", "max", "min"})
""" 数值穿过它们仍然原样变成文字的函数 """


def is_num_read(node: ast.AST) -> bool:
    """
    是否读到一个 Num 数值
    Keyword arguments:
    node -- 表达式
    Return arguments:
    bool -- 是 PLAIN 里的属性、needs.of(...)[...]（生理需求）、status_data[...] 或 body_semen[...][1] 时为真
    """
    if isinstance(node, ast.Attribute):
        return node.attr in PLAIN
    if not isinstance(node, ast.Subscript):
        return False
    base = node.value
    if (
        isinstance(base, ast.Call)
        and isinstance(base.func, ast.Attribute)
        and base.func.attr == "of"
        and isinstance(base.func.value, ast.Name)
        and base.func.value.id == "needs"
    ):
        return True
    if isinstance(base, ast.Attribute) and base.attr == "status_data":
        return True
    return (
        isinstance(node.slice, ast.Constant)
        and node.slice.value == 1
        and isinstance(base, ast.Subscript)
        and isinstance(base.value, ast.Attribute)
        and base.value.attr == "body_semen"
    )


def call_name(node: ast.AST) -> str:
    """
    调用的函数名
    Keyword arguments:
    node -- 表达式
    Return arguments:
    str -- 函数名或方法名，不是调用时为空
    """
    if not isinstance(node, ast.Call):
        return ""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def text_roots(tree: ast.AST) -> list[ast.expr]:
    """
    会变成文字的表达式
    Keyword arguments:
    tree -- 语法树
    Return arguments:
    list -- f-string 字段、str() 参数、字符串 % 的右边、.format() 参数
    """
    roots: list[ast.expr] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FormattedValue):
            roots.append(node.value)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "str":
                roots += node.args
            elif (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "format"
            ):
                roots += node.args
                roots += [k.value for k in node.keywords]
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod):
            left = node.left
            if (
                (isinstance(left, ast.Constant) and isinstance(left.value, str))
                or isinstance(left, ast.JoinedStr)
                or call_name(left) == "_"
            ):
                roots.append(node.right)
    return roots


def raw_reads(root: ast.expr) -> list[ast.expr]:
    """
    一个会变成文字的表达式里，没包在 shown() 里的 Num 读取
    Keyword arguments:
    root -- 表达式
    Return arguments:
    list -- 读取的节点
    """
    found: list[ast.expr] = []
    stack: list[ast.AST] = [root]
    while stack:
        node = stack.pop()
        if call_name(node) == "shown":
            continue
        if isinstance(node, ast.expr) and is_num_read(node):
            found.append(node)
        elif isinstance(node, (ast.BinOp, ast.UnaryOp, ast.Tuple, ast.List)):
            stack += ast.iter_child_nodes(node)
        elif isinstance(node, ast.IfExp):
            stack += [node.body, node.orelse]
        elif isinstance(node, ast.Call) and call_name(node) in PASS_THROUGH:
            stack += node.args
    return found


def hits_in(source: str, rel: str) -> list[str]:
    """
    一份源码里的问题
    Keyword arguments:
    source -- 源码
    rel -- 显示用的文件名
    Return arguments:
    list -- 每处一行：文件、行号与读取的代码
    """
    found = {
        (node.lineno, ast.unparse(node))
        for root in text_roots(ast.parse(source))
        for node in raw_reads(root)
    }
    return [f"{rel}:{line} {code}" for line, code in sorted(found)]


def scanned() -> list[str]:
    """
    Script 下全部 .py 里的问题
    Return arguments:
    list -- 每处一行
    """
    out = []
    for path in sorted((pathlib.Path(ROOT) / "Script").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        out += hits_in(path.read_text(encoding="utf-8-sig"), rel)
    return out


class StatDisplayTest(FastTestCase):
    """连续数值变成文字前经过 shown()"""

    def test_no_raw_stat_text(self) -> None:
        """
        Script 下没有直接变成文字的 Num 读取
        Keyword arguments:
        无
        Return arguments:
        无
        """
        hits = scanned()
        self.assertEqual(
            hits, [], "这些数值要包在 num.shown(...) 里：\n" + "\n".join(hits)
        )

    def test_scan_finds_raw_reads(self) -> None:
        """
        扫描能认出四种文字形式与 int() 等中间运算，放过 shown() 与其他函数
        Keyword arguments:
        无
        Return arguments:
        无
        """
        source = "\n".join(
            [
                'a = f"{c.hit_point}"',
                "b = str(int(c.status_data[3]))",
                'd = "%d/%d" % (c.mana_point, c.mana_point_max)',
                'e = _("{0}").format(needs.of(c.cid)["milk"] + 1)',
                'f = f"{c.dirty.body_semen[2][1]}"',
                'g = f"{num.shown(c.hit_point)}"',
                'h = f"{get_level(needs.of(0)["tired"])}"',
                'i = f"{c.sp_flag.milk}{c.dirty.body_semen[2][2]}"',
                'j = f"{c.hit_point_max}"',
            ]
        )
        self.assertEqual(
            hits_in(source, "x.py"),
            [
                "x.py:1 c.hit_point",
                "x.py:2 c.status_data[3]",
                "x.py:3 c.mana_point",
                "x.py:4 needs.of(c.cid)['milk']",
                "x.py:5 c.dirty.body_semen[2][1]",
            ],
        )
