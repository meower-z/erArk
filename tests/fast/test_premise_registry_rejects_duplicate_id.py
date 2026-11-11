# -*- coding: UTF-8 -*-
"""
add_premise 拒绝重复的前提id
============================
add_premise 返回的装饰器把前提处理函数存入 constant.handle_premise_data。
测试先注册 handle_first，再对同一个前提id注册 handle_second，然后再次注册 handle_first。
后两次注册都须抛 ValueError。
每次抛错后，这个前提id仍须对应 handle_first。
"""

from Script.Core import constant
from Script.Design.handle_premise.premise_registry import add_premise
from tests.fast.base import FastTestCase

PREMISE_ID = "test_duplicate_premise_id"
""" 本测试注册的前提id，游戏不使用这个id """


def handle_first(character_id: int) -> int:
    """
    先注册到 PREMISE_ID 的前提处理函数
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重，固定为1
    """
    return 1


def handle_second(character_id: int) -> int:
    """
    后注册到 PREMISE_ID 的前提处理函数
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 权重，固定为0
    """
    return 0


class PremiseRegistryDuplicateIdTest(FastTestCase):
    """add_premise 拒绝重复注册前提id的测试"""

    def tearDown(self) -> None:
        """
        从 constant.handle_premise_data 移除 PREMISE_ID
        Keyword arguments:
        无
        Return arguments:
        无
        """
        constant.handle_premise_data.pop(PREMISE_ID, None)

    def test_second_registration_raises(self) -> None:
        """
        对已注册的 PREMISE_ID 再注册 handle_second 和 handle_first，每次都须抛 ValueError。
        每次抛错后，PREMISE_ID 仍须对应 handle_first。
        Keyword arguments:
        无
        Return arguments:
        无
        """
        add_premise(PREMISE_ID)(handle_first)
        for func in (handle_second, handle_first):
            with self.subTest(func=func.__name__):
                with self.assertRaises(ValueError):
                    add_premise(PREMISE_ID)(func)
                self.assertIs(
                    constant.handle_premise_data[PREMISE_ID], handle_first
                )
