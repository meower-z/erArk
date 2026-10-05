# -*- coding: UTF-8 -*-
"""
淫纹 mod 测试的最小断言工具（不 import 游戏）：check / finish，输出格式同 tools/tests/education
"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
""" 仓库根目录 """
MOD_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
""" mod 目录 """
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

PASS = 0
""" 已通过的断言数 """
FAIL = []
""" 失败的断言名 """


def check(name: str, cond, extra="") -> bool:
    """
    记录一条断言结果
    Keyword arguments:
    name -- 断言名
    cond -- 断言条件
    extra -- 失败时附带打印的实际值
    Return arguments:
    bool -- 是否通过
    """
    global PASS
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
        return True
    FAIL.append(name)
    print(f"  [FAIL] {name} {extra}")
    return False


def finish() -> None:
    """
    打印汇总并强制退出进程（游戏导入链里的非守护线程会让进程不自行结束）
    Keyword arguments:
    无
    Return arguments:
    None
    """
    print("=" * 50)
    print(f"PASS={PASS} FAIL={len(FAIL)}")
    for name in FAIL:
        print("  -", name)
    sys.stdout.flush()
    os._exit(0 if not FAIL else 1)


def load_mod_package():
    """
    以测试身份按 entry.py 同样的方式加载私有包 _erark_mod_lewd_tattoo（不调用 install）
    Keyword arguments:
    无
    Return arguments:
    module -- 包模块
    """
    import importlib.util

    name = "_erark_mod_lewd_tattoo"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(MOD_DIR, "__init__.py"), submodule_search_locations=[MOD_DIR])
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
