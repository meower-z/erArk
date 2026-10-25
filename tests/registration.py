# -*- coding: UTF-8 -*-
"""
测试登记检查的两层部分
======================
像 unittest discover 那样导入一层的测试模块，再按导入后实际存在的类与函数列出不合登记规则的测试。
tests/fast/test_registration.py 用它检查快速层；慢速层由同一文件在子进程里以 python -m tests.registration 检查，
因为 tests/slow/__init__.py 不许在载入了 tests.fast 的进程里导入。
本模块顶部只导入标准库与 tests.world；以 python -m 运行时再导入 tests.slow.base。
"""

import json
import os
import sys
from typing import TYPE_CHECKING, cast
import unittest

from tests.world import ROOT

if TYPE_CHECKING:
  from collections.abc import Mapping
  from types import ModuleType

FAST_LAYER = "tests/fast/"
""" 快速层的目录 """
SLOW_LAYER = "tests/slow/"
""" 慢速层的目录 """


class RecordingLoader(unittest.TestLoader):
  """unittest discover 用的加载器，另记下载入了哪些模块"""

  def __init__(self) -> None:
    """
    初始化
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().__init__()
    self.modules: list[ModuleType] = []

  def loadTestsFromModule(
      self, module: "ModuleType", *args: str | None, **kwargs: str | None
  ) -> unittest.TestSuite:
    """
    记下模块，再照常收集其中的测试
    Keyword arguments:
    module -- 测试模块
    args, kwargs -- 原样交给 unittest.TestLoader
    Return arguments:
    unittest.TestSuite -- 模块里的测试
    """
    self.modules.append(module)
    return super().loadTestsFromModule(module, *args, **kwargs)


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


def has_tests(cls: type, loader: unittest.TestLoader) -> bool:
  """
  类里有没有测试：TestCase 子类按 unittest 自己的收集（test 方法；一个也没有而有 runTest 时为 runTest），其他类看有没有 test 方法
  Keyword arguments:
  cls -- 类
  loader -- 用来收集测试的加载器
  Return arguments:
  bool -- 是否有测试
  """
  if issubclass(cls, unittest.TestCase):
    return loader.loadTestsFromTestCase(cls).countTestCases() > 0
  return bool(loader.getTestCaseNames(cls))


def module_classes(module: "ModuleType") -> list:
  """
  模块命名空间里的类
  Keyword arguments:
  module -- 模块
  Return arguments:
  list[type] -- 类，不重复
  """
  return list(
      dict.fromkeys(
          obj for obj in vars(module).values() if isinstance(obj, type)
      )
  )


def pytest_classes(module: "ModuleType") -> list:
  """
  pytest 收集的类：名字以 Test 开头（pytest 的默认设置）、__test__ 不为假的类，不是 TestCase 的还要 __init__ 与 __new__ 都沿用 object 的；
  先找模块里的，再找其中不是 TestCase 的类与它的基类里的，逐层往下；类与基类里同名的只看最先找到的那个（与 pytest 相同）
  Keyword arguments:
  module -- 测试模块
  Return arguments:
  list[type] -- 类，不重复
  """
  found: list[type] = []
  owners: list[ModuleType | type] = [module]
  while owners:
    owner = owners.pop()
    if isinstance(owner, type):
      namespaces: "list[Mapping[str, object]]" = [
          vars(klass) for klass in owner.__mro__
      ]
    else:
      namespaces = [vars(owner)]
    seen = set()
    for name, obj in (item for names in namespaces for item in names.items()):
      if name in seen:
        continue
      seen.add(name)
      if (
          not isinstance(obj, type)
          or not name.startswith("Test")
          or not getattr(obj, "__test__", True)
          or obj in found
      ):
        continue
      if issubclass(obj, unittest.TestCase):
        found.append(obj)
      elif obj.__init__ is object.__init__ and obj.__new__ is object.__new__:
        found.append(obj)
        owners.append(obj)
  return found


def collected_cases(module: "ModuleType", loader: unittest.TestLoader) -> list:
  """
  模块里会被收集的测试类：模块命名空间里有测试的 TestCase 子类
  Keyword arguments:
  module -- 测试模块
  loader -- 用来收集测试的加载器
  Return arguments:
  list[type] -- 测试类，不重复
  """
  return [
      cls
      for cls in module_classes(module)
      if issubclass(cls, unittest.TestCase) and has_tests(cls, loader)
  ]


def module_problems(
    module: "ModuleType",
    base: type,
    loader: unittest.TestLoader,
    layer_cases: list,
) -> list:
  """
  查一个已导入的测试模块，列出不合登记规则的测试
  Keyword arguments:
  module -- 测试模块
  base -- 该层的基类
  loader -- 用来收集测试的加载器
  layer_cases -- 这一层所有模块里会被收集的测试类
  Return arguments:
  list[str] -- 问题，每条写明文件、类或函数与改法
  功能描述:
      本模块会被收集的测试类要是 base 的子类。模块有 load_tests 时由它决定 unittest 收集什么，所以也报出。其他有测试的类（不是 TestCase 的类、类里嵌套的类）
      只有在是这一层某个会被收集的测试类的基类（如混入类）时，它的测试才会运行。类里嵌套的类：本模块里定义的类的属性所引用的、本模块定义的类（含别名，逐层往下）。
      pytest 还收集 pytest_classes 列出的类，不是 TestCase 的也单独运行，所以其中不继承 base 的类即使被测试类继承也报出。
  """
  assert module.__file__ is not None
  path = os.path.relpath(module.__file__, ROOT).replace(os.sep, "/")
  base_name = f"{base.__module__}.{base.__qualname__}"
  cases = collected_cases(module, loader)
  problems = [
      f"{path} 类 {cls.__qualname__}：不是 {base_name} 的子类，让它继承该基类"
      for cls in cases
      if not issubclass(cls, base)
  ]
  classes = module_classes(module)
  collected_by_pytest = pytest_classes(module)
  # 遍历中 classes 变长：嵌套再深的类、类属性引用的本模块的类也会查到
  for cls in classes:
    if cls.__module__ == module.__name__:
      inner_classes = dict.fromkeys(
          obj
          for obj in vars(cls).values()
          if isinstance(obj, type) and obj.__module__ == module.__name__
      )
      classes += [inner for inner in inner_classes if inner not in classes]
  classes += [cls for cls in collected_by_pytest if cls not in classes]
  for cls in classes:
    if (
        cls in collected_by_pytest
        and cls not in cases
        and has_tests(cls, loader)
        and not issubclass(cls, base)
    ):
      problems.append(
          f"{path} 类 {cls.__qualname__}：名字以 Test 开头，pytest 会不经 {base_name} 单独运行它；测试类继承该基类，混入类改用不以 Test 开头的名字"
      )
    elif (
        cls not in cases
        and has_tests(cls, loader)
        and not any(issubclass(case, cls) for case in layer_cases)
    ):
      problems.append(
          f"{path} 类 {cls.__qualname__}：它的测试不会运行，写成模块级的类并继承 {base_name}"
      )
  for name, obj in vars(module).items():
    if (
        name.startswith(loader.testMethodPrefix)
        and callable(obj)
        and not isinstance(obj, type)
    ):
      problems.append(
          f"{path} 函数 {name}：模块级的 test 函数 unittest 不收集，写成继承 {base_name} 的类里的方法"
      )
  if getattr(module, "load_tests", None) is not None:
    problems.append(
        f"{path} load_tests：它决定 unittest 收集哪些测试，本检查按模块里的类查，两层里不用它"
    )
  return problems


def layer_problems(layer: str, base: type) -> list:
  """
  像 unittest discover 那样导入一层的测试模块，列出不合登记规则的测试
  Keyword arguments:
  layer -- 层的目录，相对仓库根目录、以 / 结尾
  base -- 该层的基类
  Return arguments:
  list[str] -- 问题，每条写明文件、类或函数与改法
  功能描述:
      导入出错的模块、discover 没有载入的 test_*.py（如所在目录缺 __init__.py）也算问题：其中的测试查不到。
  """
  loader = RecordingLoader()
  saved_path = sys.path[:]
  try:
    loader.discover(
        os.path.join(ROOT, layer), pattern="test_*.py", top_level_dir=ROOT
    )
  finally:
    sys.path[:] = saved_path
  problems = []
  failed = set()
  for error in cast(list[str], loader.errors):
    lines = error.strip().splitlines()
    name = lines[0].rsplit(" ", 1)[-1]
    failed.add(name)
    problems.append(
        f"模块 {name} 导入出错（{lines[-1]}）：修好导入，其中的测试才查得到"
    )
  loaded = {
      os.path.realpath(module_file)
      for module in loader.modules
      if (module_file := getattr(module, "__file__", None))
  }
  for folder, dirs, files in os.walk(os.path.join(ROOT, layer)):
    dirs[:] = [name for name in dirs if name != "__pycache__"]
    for name in sorted(files):
      path = os.path.relpath(os.path.join(folder, name), ROOT).replace(
          os.sep, "/"
      )
      if (
          is_test_file(path)
          and os.path.realpath(os.path.join(ROOT, path)) not in loaded
          and path[:-3].replace("/", ".") not in failed
      ):
        problems.append(
            f"{path}：unittest discover 没有载入它，所在目录要有 __init__.py"
        )
  layer_cases = [
      cls
      for module in loader.modules
      for cls in collected_cases(module, loader)
  ]
  for module in loader.modules:
    problems += module_problems(module, base, loader, layer_cases)
  return problems


if __name__ == "__main__":
  # python -m tests.registration：检查慢速层，把问题列表以 JSON 写到标准输出的最后一行
  from tests.slow.base import SlowTestCase

  print(json.dumps(layer_problems(SLOW_LAYER, SlowTestCase)))
