"""
读常量文件里的常量说明
======================
read_constant_doc 用 ast 读 Script/Core 下常量文件里的常量与说明字符串，test_talk_data.py 用它校验静态数据。
本模块只用标准库，导入它不启动游戏。
"""

import ast
import os
from typing import Any


def read_constant_doc(file_name: str, class_name: str) -> dict[Any, tuple]:
    """
    用 ast 读 Script/Core 下的一个常量文件，取出指定类里后面紧跟着说明字符串的常量
    Keyword arguments:
    file_name -- 常量文件名
    class_name -- 类名
    Return arguments:
    dict -- 常量值 -> (常量名, 分类, 描述)。分类是说明里第一个空格之前的部分。描述是这个空格之后的部分，没有空格时为空
    """
    with open(
        os.path.join("Script", "Core", file_name), encoding="utf-8-sig"
    ) as constant_file:
        tree = ast.parse(constant_file.read())
    doc_dict: dict[Any, tuple] = {}
    for class_node in tree.body:
        if (
            not isinstance(class_node, ast.ClassDef)
            or class_node.name != class_name
        ):
            continue
        body = class_node.body
        for index in range(len(body) - 1):
            node, doc_node = body[index], body[index + 1]
            if not (
                isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(doc_node, ast.Expr)
                and isinstance(doc_node.value, ast.Constant)
                and isinstance(doc_node.value.value, str)
            ):
                continue
            doc_part = doc_node.value.value.strip().partition(" ")
            doc_dict[node.value.value] = (
                node.targets[0].id,
                doc_part[0],
                doc_part[2],
            )
    return doc_dict
