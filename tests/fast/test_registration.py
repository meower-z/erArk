# -*- coding: UTF-8 -*-
"""
测试的登记检查
==============
测试靠位置与基类登记，没有总清单：
- tests/fast/ 下的 test_*.py 是快速层测试，其中的测试类继承 tests.fast.base.FastTestCase；
- tests/slow/ 下的 test_*.py 是慢速层测试，其中的测试类继承 tests.slow.base.SlowTestCase；
- 仓库里别处不能有 test_*.py，NOT_IN_LAYERS 列出的例外除外。
继承可以经过同一层里的其他模块（如 tests/slow/health_check.py 的 HealthCheckTestCase）。
两层的模块只解析、不导入（慢速层的模块不能在快速层的进程里导入）；两层之外的文件取自 git：已跟踪的，加上没有被忽略的新文件。
"""
import ast
import os
import shutil
import subprocess
import unittest

from tests.fast.base import FastTestCase
from tests.world import ROOT

LAYERS = {"tests/fast/": ("tests.fast.base", "FastTestCase"), "tests/slow/": ("tests.slow.base", "SlowTestCase")}
""" 层的目录: (基类所在模块, 基类名) """
NOT_IN_LAYERS = {
    "tools/tests/education/": "育儿系统的旧测试，各自单独运行，迁移前保留",
    "tools/MCP/prts_character_downloader/test_downloader.py": "PRTS 立绘下载器的手动脚本，从网上下载图片，不是游戏的测试",
}
""" 可以不在两层里的 test_*.py：路径（以 / 结尾的是目录）: 原因 """


def is_test_file(path: str) -> bool:
    """
    是不是测试文件：文件名为 test_*.py
    Keyword arguments:
    path -- 用 / 分隔的路径
    Return arguments:
    bool -- 是否为测试文件
    """
    name = path.rsplit("/", 1)[-1]
    return name.startswith("test_") and name.endswith(".py")


def repository_test_files() -> list:
    """
    列出仓库里现有的 test_*.py：git 跟踪的，加上没有被忽略的新文件
    Keyword arguments:
    无
    Return arguments:
    list[str] -- 相对仓库根目录、用 / 分隔的路径
    """
    output = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    paths = output.decode("utf-8").split("\0")
    return [path for path in paths if is_test_file(path) and os.path.isfile(os.path.join(ROOT, path))]


def misplaced(paths: list) -> list:
    """
    找出不在两层里、也不在 NOT_IN_LAYERS 里的测试文件
    Keyword arguments:
    paths -- 测试文件，用 / 分隔的路径
    Return arguments:
    list[str] -- 放错位置的测试文件
    """
    allowed = tuple(LAYERS) + tuple(NOT_IN_LAYERS)
    return [path for path in paths if not path.startswith(allowed)]


def layer_modules(layer: str) -> dict:
    """
    解析一层目录下的全部模块
    Keyword arguments:
    layer -- 层的目录，如 "tests/fast/"
    Return arguments:
    dict -- 用 / 分隔的路径: 模块的语法树
    """
    modules = {}
    for dir_path, dir_names, file_names in os.walk(os.path.join(ROOT, layer)):
        dir_names[:] = [name for name in dir_names if name != "__pycache__"]
        for file_name in file_names:
            if file_name.endswith(".py"):
                path = os.path.relpath(os.path.join(dir_path, file_name), ROOT).replace(os.sep, "/")
                with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                    modules[path] = ast.parse(f.read(), path)
    return modules


def module_name(path: str) -> str:
    """
    由路径得出模块名
    Keyword arguments:
    path -- 用 / 分隔的 .py 路径
    Return arguments:
    str -- 模块名，如 tests.slow.health_check
    """
    return path[: -len(".py")].replace("/", ".").removesuffix(".__init__")


def visible_registered(tree: ast.Module, module: str, registered: set) -> set:
    """
    一个模块里可以当作已登记基类使用的名字：从别的模块导入的已登记类，加上本模块里已登记的类
    Keyword arguments:
    tree -- 模块的语法树
    module -- 模块名
    registered -- 已登记的类：(模块名, 类名)
    Return arguments:
    set[str] -- 名字
    """
    names = {name for owner, name in registered if owner == module}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names if (node.module, alias.name) in registered)
    return names


def registered_classes(modules: dict, module: str, base: str) -> set:
    """
    找出一层里继承基类的全部类，继承可以经过同层的其他模块
    Keyword arguments:
    modules -- 用 / 分隔的路径: 模块的语法树
    module -- 基类所在模块
    base -- 基类名
    Return arguments:
    set -- (模块名, 类名)
    """
    registered = {(module, base)}
    while True:
        found = set(registered)
        for path, tree in modules.items():
            name = module_name(path)
            names = visible_registered(tree, name, found)
            for node in tree.body:
                if isinstance(node, ast.ClassDef) and any(isinstance(item, ast.Name) and item.id in names for item in node.bases):
                    found.add((name, node.name))
                    names.add(node.name)
        if found == registered:
            return registered
        registered = found


def base_class_problems(tree: ast.Module, module: str, registered: set, base: str) -> list:
    """
    检查一个测试文件的测试都写在已登记的类里
    Keyword arguments:
    tree -- 测试文件的语法树
    module -- 测试文件的模块名
    registered -- 本层已登记的类：(模块名, 类名)
    base -- 本层的基类名，写进问题说明
    Return arguments:
    list[str] -- 问题，没有问题时为空
    功能描述:
        定义 test 开头方法的类都要已登记；模块级的 test 开头函数不算登记；文件里至少要有一个带测试方法的已登记类。
    """
    names = visible_registered(tree, module, registered)
    problems = []
    test_classes = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            problems.append(f"模块级函数 {node.name}：测试要写在继承 {base} 的类里")
        elif isinstance(node, ast.ClassDef) and any(isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith("test") for item in node.body):
            if node.name in names:
                test_classes += 1
            else:
                problems.append(f"类 {node.name} 没有继承 {base}")
    if not test_classes and not problems:
        problems.append(f"没有继承 {base} 的测试类")
    return problems


class RegistrationTest(FastTestCase):
    """每个测试文件放在一层里，测试类继承该层的基类；别处的 test_*.py 只有 NOT_IN_LAYERS 列出的"""

    maxDiff = None

    def test_layer_tests_use_layer_base(self):
        """两层里每个 test_*.py 的测试类都继承该层的基类"""
        problems = {}
        for layer, (module, base) in LAYERS.items():
            modules = layer_modules(layer)
            registered = registered_classes(modules, module, base)
            for path, tree in modules.items():
                if is_test_file(path):
                    found = base_class_problems(tree, module_name(path), registered, base)
                    if found:
                        problems[path] = found
        self.assertEqual(problems, {})

    def test_no_test_outside_layers(self):
        """test_*.py 只在 tests/fast/、tests/slow/ 与 NOT_IN_LAYERS 里；NOT_IN_LAYERS 的每一项都还有 test_*.py"""
        if shutil.which("git") is None or not os.path.exists(os.path.join(ROOT, ".git")):
            raise unittest.SkipTest("两层之外的文件从 git 取，这里没有 git 或不是 git 检出")
        paths = repository_test_files()
        self.assertEqual(misplaced(paths), [])
        stale = [entry for entry in NOT_IN_LAYERS if not any(path == entry or entry.endswith("/") and path.startswith(entry) for path in paths)]
        self.assertEqual(stale, [], "迁移或删除后要从 NOT_IN_LAYERS 去掉")
