# -*- coding: UTF-8 -*-
"""
mod_data 门禁（静态部分）：谁能碰 character.mod_data、store.py 写进去的字面量是不是内建类型

用法：
    python3 mod/lewd_tattoo/tests/lint_mod_data.py
退出码 0 = 通过；1 = 有违规（逐条打印）

规则：
1. 访问者闸：对 Script/**/*.py 与 mod/**/*.py（不含各 mod 的 tests/ 目录）做 AST 扫描，
   出现属性名 mod_data（ast.Attribute.attr）或值恰为 "mod_data" 的字符串常量（防 getattr/setattr 绕过）的文件只能是：
     - Script/Core/game_type.py（字段声明）
     - Script/Core/mod_hook.py（文档与校验器）
     - mod/<mod 目录>/store.py（每个 mod 的唯一数据模块）
2. 形状闸（只查 store.py）：对 mod_data 下标赋值（`<...>.mod_data[...] = 右值` 及更深的下标）的右值，
   若是字面量/推导式，只许含 dict/list/str/int/float/bool/None；不许 tuple/set 字面量、集合推导、生成器、lambda、
   调用非内建构造的 Call。右值是变量或函数返回值时静态判断不了，放行，交给运行时闸。
运行时闸不在这里：store.write 写入前调用 Script/Core/mod_hook.validate_mod_data；test_save_roundtrip.py 每阶段存档后再查一遍。
"""
import ast
import os
import sys
from typing import List

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
""" 仓库根目录 """
ALLOWED_BASE_FILES = ("Script/Core/game_type.py", "Script/Core/mod_hook.py")
""" 本体中允许出现 mod_data 的文件 """
ALLOWED_CALLS = ("dict", "list", "str", "int", "float", "bool", "sorted")
""" 形状闸里允许出现在字面量右值中的调用 """
FIELD = "mod_data"
""" 字段名 """


def is_allowed(rel_path: str) -> bool:
    """
    判断一个文件是否允许访问 mod_data
    Keyword arguments:
    rel_path -- 相对仓库根目录、用 / 分隔的路径
    Return arguments:
    bool -- 是否允许
    """
    if rel_path in ALLOWED_BASE_FILES:
        return True
    parts = rel_path.split("/")
    return len(parts) == 3 and parts[0] == "mod" and parts[2] == "store.py"


def find_accesses(source: str) -> List[int]:
    """
    规则 1：找出源码里所有访问 mod_data 的行号
    Keyword arguments:
    source -- 源码
    Return arguments:
    List[int] -- 行号（升序去重）
    """
    lines = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr == FIELD:
            lines.add(node.lineno)
        elif isinstance(node, ast.Constant) and node.value == FIELD:
            lines.add(node.lineno)
    return sorted(lines)


def _touches_mod_data(node: ast.AST) -> bool:
    """
    判断一个赋值目标是否是 mod_data 的下标（任意深度）
    Keyword arguments:
    node -- 赋值目标
    Return arguments:
    bool -- 是否是 mod_data 的下标
    """
    while isinstance(node, ast.Subscript):
        node = node.value
        if isinstance(node, ast.Attribute) and node.attr == FIELD:
            return True
        if isinstance(node, ast.Name) and node.id == FIELD:
            return True
    return False


def _bad_literal_nodes(value: ast.AST) -> List[str]:
    """
    规则 2：列出右值里不许出现的节点
    Keyword arguments:
    value -- 赋值右值
    Return arguments:
    List[str] -- 违规描述
    """
    problems = []
    for node in ast.walk(value):
        if isinstance(node, ast.Tuple):
            problems.append("tuple 字面量")
        elif isinstance(node, (ast.Set, ast.SetComp)):
            problems.append("set 字面量或集合推导")
        elif isinstance(node, ast.GeneratorExp):
            problems.append("生成器")
        elif isinstance(node, ast.Lambda):
            problems.append("lambda")
        elif isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in ALLOWED_CALLS):
            problems.append("非内建构造的调用")
    return problems


def check_store_literals(source: str) -> List[str]:
    """
    规则 2：检查 store.py 中写入 mod_data 子树的字面量右值
    Keyword arguments:
    source -- store.py 源码
    Return arguments:
    List[str] -- 违规描述（"行号: 描述"）
    """
    errors = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AugAssign):
            targets, value = [node.target], node.value
        else:
            continue
        if not any(_touches_mod_data(target) for target in targets):
            continue
        # 变量、属性、下标、函数返回：静态判断不了，交给运行时闸
        if isinstance(value, (ast.Name, ast.Attribute, ast.Subscript)):
            continue
        if isinstance(value, ast.Call) and not (isinstance(value.func, ast.Name) and value.func.id in ALLOWED_CALLS):
            continue
        for problem in _bad_literal_nodes(value):
            errors.append(f"{node.lineno}: mod_data 子树里出现{problem}")
    return errors


def _iter_py_files(repo_root: str):
    """
    列出要扫描的 .py 文件（Script/** 与 mod/**，跳过各 mod 的 tests/ 与 __pycache__）
    Keyword arguments:
    repo_root -- 仓库根目录
    Return arguments:
    generator -- 相对路径（/ 分隔）
    """
    for top in ("Script", "mod"):
        for dir_path, dir_names, file_names in os.walk(os.path.join(repo_root, top)):
            rel_dir = os.path.relpath(dir_path, repo_root).replace(os.sep, "/")
            dir_names[:] = [d for d in dir_names if d != "__pycache__" and not (top == "mod" and rel_dir.count("/") == 1 and d == "tests")]
            for file_name in file_names:
                if file_name.endswith(".py"):
                    yield f"{rel_dir}/{file_name}"


def run(repo_root: str = REPO_ROOT) -> List[str]:
    """
    跑两道闸
    Keyword arguments:
    repo_root -- 仓库根目录
    Return arguments:
    List[str] -- 违规描述
    """
    errors = []
    for rel_path in _iter_py_files(repo_root):
        with open(os.path.join(repo_root, rel_path), encoding="utf-8") as f:
            source = f.read()
        if FIELD not in source:
            continue
        lines = find_accesses(source)
        if lines and not is_allowed(rel_path):
            errors += [f"{rel_path}:{line} 访问了 mod_data（只允许 store.py 与本体两处声明）" for line in lines]
        if rel_path.startswith("mod/") and rel_path.endswith("/store.py"):
            errors += [f"{rel_path}:{e}" for e in check_store_literals(source)]
    return errors


def main(argv: List[str]) -> int:
    """
    命令行入口
    Keyword arguments:
    argv -- 命令行参数（未使用）
    Return arguments:
    int -- 退出码
    """
    errors = run()
    for error in errors:
        print(f"[lint_mod_data] FAIL {error}")
    if not errors:
        print("[lint_mod_data] PASS")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
