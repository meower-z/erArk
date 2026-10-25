# -*- coding: UTF-8 -*-
"""
静态检查注册表对重复检查项id的处理
==================================
同一个函数（__module__ 与 __qualname__ 都相同）再次注册同一id时替换原条目：重新执行带装饰器的 def 就会这样注册。
不同函数注册同一id抛 ValueError：这通常是复制检查后忘了改id。
"""

from typing import TYPE_CHECKING

from Script.Test.Static_Check import check_registry
from Script.Test.Static_Check.check_registry import get_all_checks, register_check
from tests.fast.base import FastTestCase

if TYPE_CHECKING:
  from collections.abc import Callable
  from typing import Any

  from Script.Test.Static_Check.check_registry import CheckFailure

CHECK_ID = "TEST-REREG-01"
""" 本测试注册的检查项id，不与真实检查项重复 """

SOURCE = """
@register_check(CHECK_ID, NAME)
def {func}():
    return []
"""
""" 一个带装饰器的检查函数定义，{func} 为函数名；每次 exec 都生成新的函数对象 """


def define(
    name: str, module: str = "tests.fast.fake_check_module", func: str = "check"
) -> "Callable[[], list[CheckFailure]]":
  """
  在名为 module 的模块命名空间里执行一次 SOURCE
  Keyword arguments:
  name -- 检查项中文名称
  module -- 函数的 __module__
  func -- 函数名，即模块级函数的 __qualname__
  Return arguments:
  function -- 本次执行生成的检查函数
  """
  namespace: "dict[str, Any]" = {
      "__name__": module,
      "register_check": register_check,
      "CHECK_ID": CHECK_ID,
      "NAME": name,
  }
  exec(SOURCE.format(func=func), namespace)
  return namespace[func]


class CheckReregisterTest(FastTestCase):
  """同一函数再次注册替换原条目，不同函数注册同一id抛 ValueError"""

  def tearDown(self) -> None:
    """
    从注册表移除本测试的检查项
    Keyword arguments:
    无
    Return arguments:
    无
    """
    check_registry._check_registry.pop(CHECK_ID, None)

  def test_same_function_replaces_entry(self) -> None:
    """同一模块、同一 __qualname__ 的函数再次注册不抛错，注册表里换成新的名称与函数"""
    define("第一次")
    second = define("第二次")
    self.assertEqual(get_all_checks()[CHECK_ID], ("第二次", second))

  def test_different_function_raises(self) -> None:
    """同一模块的另一个函数、另一个模块的同名函数注册同一id都抛 ValueError，注册表保留原条目"""
    for other in (
        {"func": "check_copy"},
        {"module": "tests.fast.other_check_module"},
    ):
      with self.subTest(**other):
        check_registry._check_registry.pop(CHECK_ID, None)
        first = define("第一次")
        with self.assertRaises(ValueError):
          define("第二次", **other)
        self.assertEqual(get_all_checks()[CHECK_ID], ("第一次", first))
