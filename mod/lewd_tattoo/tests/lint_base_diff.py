# -*- coding: UTF-8 -*-
"""
本体 diff 门禁：相对 main 的本体改动只许是"钩子调用 + 白名单字段"

用法：
    python3 mod/lewd_tattoo/tests/lint_base_diff.py [--base main]
退出码 0 = 通过；1 = 有违规（逐条打印）；2 = git 错误

判定规则（三道闸，都过才算通过）：
A. 路径闸（merge-base 到工作区，含未提交改动与未跟踪文件）
   - 允许任意改动：mod/**、.agents/**、.scratch/**
   - 允许新增：Script/Core/mod_hook.py（唯一允许新增的本体文件）
   - 允许修改：Script/** 下已有的 .py
   - 其他一律违规：本体新增/删除/改名文件、data/**、config.ini、CI 文件……
B. 语义闸（对每个修改的 Script/**.py）：新文件 AST 归一化后与 main 版本 ast.dump 相等。归一化 =
   a. 删 import 里的 mod_hook
   b. `mod_hook.<钩子>(a0, ...)` 还原成 a0；<钩子> 必须在 mod_hook.py 的 `X = FoldHook(...)` 名单里；
      其余参数只许 Name / 纯属性链 / Constant，不许关键字参数与星号参数；mod_hook 的其他用法一律违规
   c. 删还原后的自赋值（`x = x`、`a, b = (a, b)`、`self.l = self.l`）
   d. stop_on_none 钩子的自赋值之后必须紧跟两种守卫之一：
      `if X is None: return` —— 删除；`if X is not None: <块>` —— 把块原样展开到原位置
   e. 删整句只有钩子调用的表达式语句（通知型钩子，如 desire_written）
   f. 只在 Script/Core/game_type.py 的 Character.__init__ 里：删 `self.mod_data` 声明及紧随的文档串
C. 文本闸：每条被删除的行，都必须在同一 hunk 内配对到一条新增行：要么含 "mod_hook"，要么是它缩进 4 格后的原文
   （被 `if X is not None:` 包住的行）。防止"AST 相同但顺手重排版"把 diff 弄大。
"""
import argparse
import ast
import difflib
import os
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
""" 仓库根目录 """
ALLOWED_ANY = ("mod/", ".agents/", ".scratch/")
""" 任意改动都允许的路径前缀 """
ALLOWED_NEW = ("Script/Core/mod_hook.py",)
""" 允许新增的本体文件 """
HOOK_MODULE_PATH = "Script/Core/mod_hook.py"
""" 钩子名单的唯一来源 """
WHITELIST_FIELD = ("Script/Core/game_type.py", "Character", "__init__", "mod_data")
""" (文件, 类, 方法, 字段) 白名单字段 """


# ========== git 访问 ==========


def _git(args: List[str]) -> str:
    """
    在仓库根目录执行 git 命令
    Keyword arguments:
    args -- git 参数
    Return arguments:
    str -- 标准输出
    """
    return subprocess.run(["git"] + args, cwd=REPO_ROOT, check=True, capture_output=True, text=True, encoding="utf-8").stdout


def changed_files(base_sha: str) -> List[Tuple[str, str]]:
    """
    列出相对 base_sha 的改动文件（含未提交改动与未跟踪文件）
    Keyword arguments:
    base_sha -- 基准提交
    Return arguments:
    List[Tuple[str, str]] -- (状态字母 A/M/D/R/..., 路径)；改名记为 (R, 旧路径) 与 (R, 新路径)
    """
    result: List[Tuple[str, str]] = []
    for line in _git(["diff", "--name-status", "-M", base_sha]).splitlines():
        parts = line.split("\t")
        status = parts[0][0]
        for path in parts[1:]:
            result.append((status, path))
    for path in _git(["ls-files", "--others", "--exclude-standard"]).splitlines():
        result.append(("A", path))
    return result


def read_worktree(path: str) -> str:
    """
    读工作区文件
    Keyword arguments:
    path -- 仓库相对路径
    Return arguments:
    str -- 文件内容
    """
    with open(os.path.join(REPO_ROOT, path), encoding="utf-8") as f:
        return f.read()


# ========== 路径闸 ==========


def check_paths(changes: List[Tuple[str, str]]) -> List[str]:
    """
    路径闸
    Keyword arguments:
    changes -- 改动文件列表
    Return arguments:
    List[str] -- 违规描述
    """
    errors = []
    for status, path in changes:
        if path.startswith(ALLOWED_ANY):
            continue
        if status == "A" and path in ALLOWED_NEW:
            continue
        if status == "M" and path.startswith("Script/") and path.endswith(".py"):
            continue
        errors.append(f"路径闸: {path} ({status}) 不在允许范围")
    return errors


# ========== 语义闸 ==========


def load_hook_names(mod_hook_source: str) -> Dict[str, bool]:
    """
    从 mod_hook.py 源码的 AST 读钩子名单：模块级 `name = FoldHook("name", stop_on_none=...)`
    Keyword arguments:
    mod_hook_source -- mod_hook.py 源码
    Return arguments:
    Dict[str, bool] -- 钩子名 -> 是否 stop_on_none
    """
    hooks: Dict[str, bool] = {}
    for node in ast.parse(mod_hook_source).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
            continue
        call = node.value
        if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "FoldHook"):
            continue
        stop = False
        for keyword in call.keywords:
            if keyword.arg == "stop_on_none" and isinstance(keyword.value, ast.Constant):
                stop = bool(keyword.value.value)
        hooks[node.targets[0].id] = stop
    return hooks


def _dump(node: ast.AST) -> str:
    """
    去掉 Load/Store 上下文差异后的 ast.dump，用于判断自赋值
    Keyword arguments:
    node -- AST 节点
    Return arguments:
    str -- 归一化 dump
    """
    return ast.dump(node).replace("ctx=Store()", "ctx=Load()")


def _is_plain_ref(node: ast.AST) -> bool:
    """
    是否是"无副作用的引用"：Name、Constant，或以 Name 为根的纯属性链
    Keyword arguments:
    node -- AST 节点
    Return arguments:
    bool -- 是否合法
    """
    if isinstance(node, (ast.Name, ast.Constant)):
        return True
    if isinstance(node, ast.Attribute):
        return _is_plain_ref(node.value) and not isinstance(node.value, ast.Constant)
    return False


def _uses_name(node: ast.AST, name: str) -> bool:
    """
    节点内是否读取了某个变量名
    Keyword arguments:
    node -- AST 节点
    name -- 变量名
    Return arguments:
    bool -- 是否读取
    """
    return any(isinstance(sub, ast.Name) and sub.id == name and isinstance(sub.ctx, ast.Load) for sub in ast.walk(node))


class Normalizer:
    """
    归一化器：执行规则 B 的 a~f；违规写进 self.errors 而不是抛异常，一次报全
    Keyword arguments:
    path -- 文件相对路径
    hooks -- 钩子名单
    """

    def __init__(self, path: str, hooks: Dict[str, bool]):
        """
        初始化
        Keyword arguments:
        path -- 文件相对路径
        hooks -- 钩子名单
        Return arguments:
        None
        """
        self.path = path
        """ 文件相对路径 """
        self.hooks = hooks
        """ 钩子名 -> 是否 stop_on_none """
        self.errors: List[str] = []
        """ 违规描述 """

    # ---------- 表达式层 ----------

    def hook_name(self, node: ast.AST) -> Optional[str]:
        """
        若节点是 `mod_hook.<名>(...)` 调用，返回钩子名，否则 None
        Keyword arguments:
        node -- AST 节点
        Return arguments:
        Optional[str] -- 钩子名
        """
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name) and node.func.value.id == "mod_hook":
            return node.func.attr
        return None

    def restore_call(self, node: ast.Call, name: str) -> ast.AST:
        """
        规则 b：校验钩子调用并还原成第一个参数
        Keyword arguments:
        node -- 钩子调用节点
        name -- 钩子名
        Return arguments:
        ast.AST -- 第一个参数（已递归归一化）
        """
        if name not in self.hooks:
            self.errors.append(f"语义闸: {self.path}:{node.lineno} 未知钩子 mod_hook.{name}")
        if node.keywords or not node.args or any(isinstance(arg, ast.Starred) for arg in node.args):
            self.errors.append(f"语义闸: {self.path}:{node.lineno} 钩子调用只许位置参数且至少一个")
            return node
        for arg in node.args[1:]:
            if not _is_plain_ref(arg):
                self.errors.append(f"语义闸: {self.path}:{node.lineno} 钩子 {name} 的上下文参数只许 Name/属性链/常量，实为 {type(arg).__name__}")
        return self.expr(node.args[0])

    def expr(self, node: ast.AST) -> ast.AST:
        """
        递归归一化一个非语句节点：还原其中的钩子调用，拦截 mod_hook 的其他用法
        Keyword arguments:
        node -- AST 节点
        Return arguments:
        ast.AST -- 新节点
        """
        name = self.hook_name(node)
        if name is not None:
            return self.restore_call(node, name)
        if isinstance(node, ast.Name) and node.id == "mod_hook":
            self.errors.append(f"语义闸: {self.path}:{node.lineno} mod_hook 只许以 mod_hook.<钩子>(...) 形式调用")
            return node
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                new_items = []
                for item in value:
                    if isinstance(item, ast.stmt):
                        new_items.append(item)
                    elif isinstance(item, ast.AST):
                        new_items.append(self.expr(item))
                    else:
                        new_items.append(item)
                setattr(node, field, new_items)
            elif isinstance(value, ast.AST) and not isinstance(value, ast.stmt):
                setattr(node, field, self.expr(value))
        return node

    # ---------- 语句层 ----------

    def strip_import(self, node: ast.stmt) -> Optional[ast.stmt]:
        """
        规则 a：删 import 里的 mod_hook
        Keyword arguments:
        node -- Import / ImportFrom 节点
        Return arguments:
        Optional[ast.stmt] -- 新节点；None 表示整句删除
        """
        if isinstance(node, ast.ImportFrom):
            names = [alias for alias in node.names if not (alias.name == "mod_hook" and alias.asname is None)]
            if len(names) != len(node.names) and node.module != "Script.Core":
                self.errors.append(f"语义闸: {self.path}:{node.lineno} mod_hook 只许从 Script.Core 导入")
        else:
            names = [alias for alias in node.names if not (alias.name == "Script.Core.mod_hook" and alias.asname is None)]
        if not names:
            return None
        node.names = names
        return node

    def is_none_guard(self, node: ast.stmt, target: str, op: type) -> bool:
        """
        判断是否为 `if <target> is None:`（op=Is）或 `if <target> is not None:`（op=IsNot），且无 else
        Keyword arguments:
        node -- 语句节点
        target -- 变量名
        op -- ast.Is 或 ast.IsNot
        Return arguments:
        bool -- 是否匹配
        """
        if not (isinstance(node, ast.If) and not node.orelse and isinstance(node.test, ast.Compare)):
            return False
        test = node.test
        return (
            isinstance(test.left, ast.Name)
            and test.left.id == target
            and len(test.ops) == 1
            and isinstance(test.ops[0], op)
            and isinstance(test.comparators[0], ast.Constant)
            and test.comparators[0].value is None
        )

    def body(self, stmts: List[ast.stmt], scope: Tuple[str, ...]) -> List[ast.stmt]:
        """
        归一化一个语句列表（规则 a、c、d、e、f 在这一层处理）
        Keyword arguments:
        stmts -- 语句列表
        scope -- 当前所在的 (类/函数名, ...) 链
        Return arguments:
        List[ast.stmt] -- 新语句列表
        """
        result: List[ast.stmt] = []
        index = 0
        in_whitelist_scope = self.path == WHITELIST_FIELD[0] and scope[-2:] == WHITELIST_FIELD[1:3]
        while index < len(stmts):
            node = stmts[index]
            index += 1
            # 规则 a
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                new_node = self.strip_import(node)
                if new_node is not None:
                    result.append(new_node)
                continue
            # 规则 e：整句钩子调用
            if isinstance(node, ast.Expr) and self.hook_name(node.value) is not None:
                self.restore_call(node.value, self.hook_name(node.value))
                continue
            # 规则 f：白名单字段
            if in_whitelist_scope and isinstance(node, ast.AnnAssign) and _dump(node.target) == _dump(ast.parse(f"self.{WHITELIST_FIELD[3]}", mode="eval").body):
                if index < len(stmts) and isinstance(stmts[index], ast.Expr) and isinstance(stmts[index].value, ast.Constant) and isinstance(stmts[index].value.value, str):
                    index += 1
                continue
            # 规则 c、d：钩子赋值
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and self.hook_name(node.value) is not None:
                name = self.hook_name(node.value)
                restored = self.restore_call(node.value, name)
                target = node.targets[0]
                if _dump(target) != _dump(restored):
                    self.errors.append(f"语义闸: {self.path}:{node.lineno} 钩子 {name} 的结果必须赋回第一个参数本身")
                    node.value = restored
                    result.append(self.stmt(node, scope))
                    continue
                if self.hooks.get(name):
                    guard = stmts[index] if index < len(stmts) else None
                    var = target.id if isinstance(target, ast.Name) else None
                    if var is not None and guard is not None and self.is_none_guard(guard, var, ast.Is) and len(guard.body) == 1 and isinstance(guard.body[0], ast.Return) and guard.body[0].value is None:
                        index += 1
                    elif var is not None and guard is not None and self.is_none_guard(guard, var, ast.IsNot):
                        index += 1
                        # 包裹块首尾两句都必须用到被钩的变量：防止把原本在块外的语句（愤怒、好感等）一并包进去
                        if not (_uses_name(guard.body[0], var) and _uses_name(guard.body[-1], var)):
                            self.errors.append(f"语义闸: {self.path}:{guard.lineno} `if {var} is not None:` 块的首尾语句必须用到 {var}（只许包住原写入与记录）")
                        result.extend(self.body(guard.body, scope))
                    else:
                        self.errors.append(f"语义闸: {self.path}:{node.lineno} stop_on_none 钩子 {name} 赋值后必须紧跟 `if X is None: return` 或 `if X is not None:`")
                continue
            result.append(self.stmt(node, scope))
        return result

    def stmt(self, node: ast.stmt, scope: Tuple[str, ...]) -> ast.stmt:
        """
        归一化单条语句：子语句列表走 body()，其余字段走 expr()
        Keyword arguments:
        node -- 语句节点
        scope -- 当前所在的 (类/函数名, ...) 链
        Return arguments:
        ast.stmt -- 新节点
        """
        inner_scope = scope
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            inner_scope = scope + (node.name,)
        for field, value in ast.iter_fields(node):
            if isinstance(value, list) and value and all(isinstance(item, ast.stmt) for item in value):
                setattr(node, field, self.body(value, inner_scope))
            elif isinstance(value, list):
                new_items = []
                for item in value:
                    if isinstance(item, ast.excepthandler):
                        item.body = self.body(item.body, inner_scope)
                        if item.type is not None:
                            item.type = self.expr(item.type)
                        new_items.append(item)
                    elif isinstance(item, ast.match_case):
                        item.body = self.body(item.body, inner_scope)
                        new_items.append(item)
                    elif isinstance(item, ast.AST):
                        new_items.append(self.expr(item))
                    else:
                        new_items.append(item)
                setattr(node, field, new_items)
            elif isinstance(value, ast.AST):
                setattr(node, field, self.expr(value))
        return node


def _first_mismatch(old_body: List[ast.stmt], new_body: List[ast.stmt], prefix: str) -> str:
    """
    下钻找第一个不一致的 def/class，返回限定名，便于定位
    Keyword arguments:
    old_body -- main 版本语句列表
    new_body -- 归一化后的语句列表
    prefix -- 限定名前缀
    Return arguments:
    str -- 限定名（找不到更细的位置时返回 prefix）
    """
    for old, new in zip(old_body, new_body):
        if ast.dump(old) == ast.dump(new):
            continue
        if isinstance(old, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and type(old) is type(new) and old.name == new.name:
            return _first_mismatch(old.body, new.body, f"{prefix}::{old.name}" if prefix else old.name)
        return f"{prefix}（main 第 {getattr(old, 'lineno', '?')} 行附近）"
    return f"{prefix}（语句数不同：main {len(old_body)}，归一化后 {len(new_body)}）"


def check_semantic(path: str, old_source: str, new_source: str, hooks: Dict[str, bool]) -> List[str]:
    """
    语义闸：归一化新文件后与 main 版本比对
    Keyword arguments:
    path -- 文件相对路径
    old_source -- main 版本源码
    new_source -- 当前版本源码
    hooks -- 钩子名单
    Return arguments:
    List[str] -- 违规描述
    """
    normalizer = Normalizer(path, hooks)
    new_tree = ast.parse(new_source)
    new_tree.body = normalizer.body(new_tree.body, ())
    old_tree = ast.parse(old_source)
    errors = list(normalizer.errors)
    if ast.dump(old_tree) != ast.dump(new_tree):
        errors.append(f"语义闸: {path} 剥除钩子后与 main 不一致，位置 {_first_mismatch(old_tree.body, new_tree.body, '') or '<模块>'}")
    return errors


# ========== 文本闸 ==========


def check_text(path: str, old_source: str, new_source: str) -> List[str]:
    """
    文本闸：每条被删除的行必须在同一 hunk 内配对到一条新增行（含 mod_hook，或是它缩进 4 格后的原文），一对一消耗
    Keyword arguments:
    path -- 文件相对路径
    old_source -- main 版本源码
    new_source -- 当前版本源码
    Return arguments:
    List[str] -- 违规描述
    """
    errors = []
    old_lines = old_source.splitlines()
    new_lines = new_source.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag not in ("replace", "delete"):
            continue
        added = list(new_lines[j1:j2])
        for line_no in range(i1, i2):
            removed = old_lines[line_no]
            partner = None
            for k, candidate in enumerate(added):
                if candidate == "    " + removed:
                    partner = k
                    break
            if partner is None:
                for k, candidate in enumerate(added):
                    if "mod_hook" in candidate:
                        partner = k
                        break
            if partner is None:
                errors.append(f"文本闸: {path} 删除了 main 第 {line_no + 1} 行且无对应钩子行: {removed.strip()[:80]}")
            else:
                added.pop(partner)
    return errors


# ========== 入口 ==========


def run(base_ref: str) -> List[str]:
    """
    对工作区跑全部三道闸
    Keyword arguments:
    base_ref -- 基准分支名
    Return arguments:
    List[str] -- 违规描述
    """
    base_sha = _git(["merge-base", "HEAD", base_ref]).strip()
    changes = changed_files(base_sha)
    errors = check_paths(changes)
    hooks = load_hook_names(read_worktree(HOOK_MODULE_PATH))
    for status, path in changes:
        if status == "M" and path.startswith("Script/") and path.endswith(".py"):
            old_source = _git(["show", f"{base_sha}:{path}"])
            new_source = read_worktree(path)
            errors += check_semantic(path, old_source, new_source, hooks)
            errors += check_text(path, old_source, new_source)
    return errors


def main(argv: List[str]) -> int:
    """
    命令行入口
    Keyword arguments:
    argv -- 命令行参数
    Return arguments:
    int -- 退出码
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="main")
    args = parser.parse_args(argv)
    try:
        errors = run(args.base)
    except subprocess.CalledProcessError as e:
        print(f"[lint_base_diff] git 错误: {e.stderr}")
        return 2
    for error in errors:
        print(f"[lint_base_diff] FAIL {error}")
    if errors:
        print(f"[lint_base_diff] {len(errors)} 处违规")
        return 1
    print("[lint_base_diff] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
