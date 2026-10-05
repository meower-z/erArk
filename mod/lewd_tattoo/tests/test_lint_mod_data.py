# -*- coding: UTF-8 -*-
"""
lint_mod_data 的夹具测试：在临时目录里摆出假仓库，合法访问必须放行、越界访问与坏形状必须报错；真仓库必须通过
用法：python3 mod/lewd_tattoo/tests/test_lint_mod_data.py
"""
import os
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import check, finish  # noqa: E402
import lint_mod_data as lint  # noqa: E402


def make_repo(files: dict) -> str:
    """
    在临时目录写出一个假仓库
    Keyword arguments:
    files -- {相对路径: 源码}
    Return arguments:
    str -- 临时仓库根目录
    """
    root = tempfile.mkdtemp(prefix="lint_mod_data_")
    for rel_path, source in files.items():
        path = os.path.join(root, rel_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(textwrap.dedent(source))
    return root


def errors_of(files: dict) -> list:
    """
    对一个假仓库跑 lint
    Keyword arguments:
    files -- {相对路径: 源码}
    Return arguments:
    list -- 违规描述
    """
    return lint.run(make_repo(files))


GOOD_STORE = """
    def write(c, keys):
        c.mod_data["x"] = {"v": 1, "effects": sorted(keys)}
        c.mod_data["x"]["n"] = [1, 2.0, "a", True, None]
        entry = {}
        c.mod_data["x"] = entry
        c.mod_data["x"] = make_entry(keys)
"""
""" 合法的 store.py """

print("[1] 访问者闸")
check("本体声明 + 每个 mod 的 store.py 放行", errors_of({
    "Script/Core/game_type.py": "class C:\n    def __init__(self):\n        self.mod_data = {}\n",
    "Script/Core/mod_hook.py": "def validate_mod_data(obj, path='mod_data'):\n    return []\n",
    "mod/a/store.py": GOOD_STORE,
    "mod/b/store.py": "def f(c):\n    return c.mod_data.get('b')\n",
}) == [])
errs = errors_of({"Script/Settle/x.py": "def f(c):\n    return c.mod_data\n"})
check("本体其他文件读 mod_data 报错", len(errs) == 1 and errs[0].startswith("Script/Settle/x.py:2"), errs)
errs = errors_of({"mod/a/hooks.py": "def f(c):\n    return getattr(c, 'mod_data')\n"})
check("mod 内非 store.py 用 getattr 字符串绕过也报错", len(errs) == 1 and "mod/a/hooks.py:2" in errs[0], errs)
errs = errors_of({"mod/a/sub/store.py": "def f(c):\n    return c.mod_data\n"})
check("嵌套目录里的 store.py 不算", len(errs) == 1, errs)
check("mod 的 tests/ 不扫", errors_of({"mod/a/tests/t.py": "x = c.mod_data\n"}) == [])
check("注释与文档字符串里提到 mod_data 不算", errors_of({"Script/x.py": '"""读写 character.mod_data 的说明"""\n# c.mod_data\n'}) == [])
check("只是包含 mod_data 的字符串不算", errors_of({"Script/x.py": "x = 'mod_data[1]'\n"}) == [])

print("[2] 形状闸")
check("合法字面量、变量、函数返回放行", lint.check_store_literals(textwrap.dedent(GOOD_STORE)) == [])
bad_cases = {
    "tuple": 'c.mod_data["x"] = {"v": (1, 2)}\n',
    "set": 'c.mod_data["x"] = {"v": {1, 2}}\n',
    "集合推导": 'c.mod_data["x"] = {"v": {k for k in ks}}\n',
    "生成器": 'c.mod_data["x"] = {"v": list(k for k in ks)}\n',
    "lambda": 'c.mod_data["x"] = {"v": lambda: 1}\n',
    "非内建调用": 'c.mod_data["x"] = {"v": frozenset(ks)}\n',
    "深层下标": 'c.mod_data["x"]["y"]["z"] = [(1, 2)]\n',
    "局部名 mod_data": 'mod_data["x"] = {"v": (1,)}\n',
}
for name, source in bad_cases.items():
    errs = lint.check_store_literals(source)
    check(f"{name} 报错", len(errs) >= 1 and errs[0].startswith("1:"), errs)
errs = errors_of({"mod/a/store.py": 'def f(c):\n    c.mod_data["a"] = {"v": (1,)}\n'})
check("run 带出 store.py 的形状错误", len(errs) == 1 and errs[0].startswith("mod/a/store.py:2:"), errs)
check("非 mod_data 的赋值不管", lint.check_store_literals('c.other["x"] = (1, 2)\n') == [])

print("[3] 真仓库")
real = lint.run()
check("真仓库通过 lint_mod_data", real == [], real)
check("main([]) 退出码 0", lint.main([]) == 0)

finish()
