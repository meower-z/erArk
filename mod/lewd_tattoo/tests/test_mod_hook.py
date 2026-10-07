# -*- coding: UTF-8 -*-
"""
Script/Core/mod_hook.py 的单测：折叠、短路、异常传播、空表直通、validate_mod_data
用法：python3 mod/lewd_tattoo/tests/test_mod_hook.py
"""
import enum
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import check, finish  # noqa: E402
from Script.Core import mod_hook  # noqa: E402

print("==== FoldHook ====")
hook = mod_hook.FoldHook("t")
check("空表原样返回同一对象", hook(obj := [1]) is obj)
hook.register(lambda v, k: v + k, owner="a")
hook.register(lambda v, k: v * 10, owner="b")
check("按注册顺序折叠", hook(1, 2) == 30)
fn = lambda v, k: v  # noqa: E731
hook.register(fn, owner="c")
hook.register(fn, owner="c")
check("同一 (owner, fn) 重复注册只算一次", len(hook._fns) == 3)
hook.unregister("b")
check("unregister 只摘该 owner", hook(1, 2) == 3 and len(hook._fns) == 2)

stop = mod_hook.FoldHook("s", stop_on_none=True)
calls = []
stop.register(lambda v: None, owner="a")
stop.register(lambda v: calls.append(v) or v, owner="b")
check("stop_on_none 返回 None 短路", stop(5) is None and not calls)

boom = mod_hook.FoldHook("e")


def _raise(value):
    """
    抛异常的钩子函数
    Keyword arguments:
    value -- 任意
    Return arguments:
    无（总是抛异常）
    """
    raise ValueError("x")


boom.register(_raise, owner="a")
try:
    boom(1)
    check("钩子异常直接传播", False)
except ValueError:
    check("钩子异常直接传播", True)
check("异常后钩子仍挂着（不自动摘除）", boom.has_fns())

print("==== 模块级钩子初始为空 ====")
for name in ("state_gain", "edge_judged", "daily_desire_growth", "character_info_draw_list", "desire_written"):
    check(f"{name} 无 mod 时为空", not getattr(mod_hook, name).has_fns())

print("==== validate_mod_data ====")


class Color(enum.IntEnum):
    """测试用 Enum"""

    RED = 1


class MyStr(str):
    """测试用 str 子类"""


cyc = []
cyc.append(cyc)
check("合法树通过", mod_hook.validate_mod_data({"v": 1, "effects": ["a", "b"], "x": None, "f": 1.5, "b": True, "n": {"k": []}}) == [])
for label, bad in (
    ("tuple", {"a": (1,)}),
    ("set", {"a": {1}}),
    ("非 str 键", {1: 1}),
    ("Enum", {"a": Color.RED}),
    ("str 子类", {"a": MyStr("x")}),
    ("str 子类作键", {MyStr("k"): 1}),
    ("NaN", {"a": float("nan")}),
    ("inf", {"a": float("inf")}),
    ("自定义对象", {"a": object()}),
    ("循环引用", {"a": cyc}),
):
    check(f"拒绝 {label}", mod_hook.validate_mod_data(bad))
shared = [1]
check("同一列表出现两次（非循环）通过", mod_hook.validate_mod_data({"a": shared, "b": shared}) == [])

finish()
