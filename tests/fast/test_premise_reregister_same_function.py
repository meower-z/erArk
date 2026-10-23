# -*- coding: UTF-8 -*-
"""
前提注册表对重复前提id的处理
============================
handle_premise 包的各模块都用 add_premise 把前提处理函数按前提id登记进 constant.handle_premise_data。
同一个函数（__module__ 与 __qualname__ 都相同）再次登记时替换原条目：重新执行带装饰器的 def 就会这样登记。
不同函数登记同一前提id抛 ValueError：这通常是两个前提常量写成了同一个id字符串。
"""

from Script.Core import constant
from Script.Design import handle_premise
from Script.Design.handle_premise import premise_profiler_patch
from tests.fast.base import FastTestCase

PREMISE_ID = "test_rereg_premise"
""" 本测试登记的前提id，不与真实前提重复 """

SOURCE = """
@add_premise(PREMISE_ID)
def {func}(character_id):
    return 1
"""
""" 一个带装饰器的前提处理函数定义，{func} 为函数名；每次 exec 都生成新的函数对象 """


def define(module="tests.fast.fake_premise_module", func="handle_test"):
  """
  在名为 module 的模块命名空间里执行一次 SOURCE
  Keyword arguments:
  module -- 函数的 __module__
  func -- 函数名，即模块级函数的 __qualname__
  Return arguments:
  function -- 本次执行生成的前提处理函数
  """
  namespace = {
      "__name__": module,
      "add_premise": handle_premise.add_premise,
      "PREMISE_ID": PREMISE_ID,
  }
  exec(SOURCE.format(func=func), namespace)
  return namespace[func]


class PremiseReregisterTest(FastTestCase):
  """同一函数再次登记替换原条目，不同函数登记同一前提id抛 ValueError"""

  def tearDown(self):
    """
    从前提表移除本测试的前提
    Keyword arguments:
    无
    Return arguments:
    无
    """
    constant.handle_premise_data.pop(PREMISE_ID, None)

  def test_same_function_replaces_entry(self):
    """同一模块、同一 __qualname__ 的函数再次登记不抛错，前提表里换成新的函数对象"""
    define()
    second = define()
    self.assertIs(constant.handle_premise_data[PREMISE_ID], second)

  def test_same_function_replaces_entry_under_profiler(self):
    """统计补丁把前提表换成包裹函数的代理字典后，同一函数再次登记也不抛错，登记的前提照常可调用"""
    original = constant.handle_premise_data
    try:
      premise_profiler_patch.activate_profiler()
      define()
      define()
      self.assertEqual(constant.handle_premise_data[PREMISE_ID](0), 1)
    finally:
      constant.handle_premise_data = original
      premise_profiler_patch.premise_profile_stats.pop(PREMISE_ID, None)

  def test_different_function_raises(self):
    """同一模块的另一个函数、另一个模块的同名函数登记同一前提id都抛 ValueError，前提表保留原条目"""
    for other in (
        {"func": "handle_test_copy"},
        {"module": "tests.fast.other_premise_module"},
    ):
      with self.subTest(**other):
        constant.handle_premise_data.pop(PREMISE_ID, None)
        first = define()
        with self.assertRaises(ValueError):
          define(**other)
        self.assertIs(constant.handle_premise_data[PREMISE_ID], first)
