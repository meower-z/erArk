# -*- coding: UTF-8 -*-
"""
内核测试的玩具插件
==================
每个 Toy 是一个新的模块，它登记的钩子、行动、事件与规则都记在这个模块名下，只有 core.load 载入它时才生效。
KernelTestCase 每个测试换上空的事件表，游戏登记的事件不参与玩具世界的扫描。
"""

import itertools
import sys
from collections.abc import Callable, Mapping
from types import MappingProxyType, ModuleType
from typing import Any
from unittest import mock

from Script.Kernel import core
from tests.fast.base import FastTestCase

_serial = itertools.count()


class Toy:
    """一个玩具插件：新模块，以及把函数登记在它名下的装饰器"""

    def __init__(self) -> None:
        """登记一个新的模块"""
        self.module = ModuleType(f"tests.fast.kernel_toy_{next(_serial)}")
        sys.modules[self.module.__name__] = self.module

    def name(self, suffix: str) -> str:
        """
        这个插件名下的名字
        Keyword arguments:
        suffix -- 名字的后半
        Return arguments:
        str -- 带模块名前缀的名字
        """
        return f"{self.module.__name__}.{suffix}"

    def own[F: Callable[..., Any]](self, fn: F) -> F:
        """
        把函数记在这个插件名下
        Keyword arguments:
        fn -- 函数
        Return arguments:
        F -- 同一个函数
        """
        fn.__module__ = self.module.__name__
        return fn

    def input_hook(
        self, target: core.HookOnly[*tuple[Any, ...], Any]
    ) -> Callable[..., Any]:
        """
        这个插件在 target 上的输入钩子
        Keyword arguments:
        target -- 被钩的调用
        Return arguments:
        Callable -- 装饰器
        """
        return lambda fn: core.input_hook(target)(self.own(fn))

    def output_hook(
        self, target: core.HookOnly[*tuple[Any, ...], Any]
    ) -> Callable[..., Any]:
        """
        这个插件在 target 上的输出钩子
        Keyword arguments:
        target -- 被钩的调用
        Return arguments:
        Callable -- 装饰器
        """
        return lambda fn: core.output_hook(target)(self.own(fn))

    def action(self, suffix: str) -> Callable[..., core.Start]:
        """
        这个插件的行动
        Keyword arguments:
        suffix -- 行动名的后半
        Return arguments:
        Callable -- 装饰器
        """
        return lambda fn: core.action(self.name(suffix))(self.own(fn))

    def event(self, suffix: str, when: core.Trigger) -> Callable[..., Any]:
        """
        这个插件的事件
        Keyword arguments:
        suffix -- 事件名的后半
        when -- 事件的条件
        Return arguments:
        Callable -- 装饰器
        """
        return lambda fn: core.event(self.name(suffix), when)(self.own(fn))

    def rule(self, suffix: str) -> Callable[..., Any]:
        """
        这个插件拥有的键的规则
        Keyword arguments:
        suffix -- 键名的后半
        Return arguments:
        Callable -- 装饰器
        """
        return lambda fn: core.rule(self.name(suffix))(self.own(fn))


def game(
    clock: int,
    ends: Mapping[str, int],
    data: Mapping[str, Mapping[str, core.JSON]] | None = None,
) -> core.GameState:
    """
    玩具世界的 GameState：每个角色一个 Idle，在 ends 给出的分钟结束
    Keyword arguments:
    clock -- 时钟
    ends -- 角色键到他的 Idle 结束的分钟
    data -- 角色键到他的数据
    Return arguments:
    GameState -- 新的 GameState
    """
    data = data or {}
    characters = {
        who: core.Character(
            core.Action(who, core.idle.name, None, clock, end - clock),
            MappingProxyType(dict(data.get(who, {}))),
        )
        for who, end in ends.items()
    }
    return core.GameState(
        clock, MappingProxyType(characters), MappingProxyType({})
    )


class KernelTestCase(FastTestCase):
    """内核测试的基类：每个测试只扫描它自己登记的事件"""

    def setUp(self) -> None:
        """复原小世界，换上空的事件表"""
        super().setUp()
        self.enterContext(mock.patch.object(core, "_events", []))

    def start(self, state: core.GameState, *toys: Toy) -> None:
        """
        载入玩具插件并从 state 开始
        Keyword arguments:
        state -- 起始 GameState
        toys -- 由内到外的玩具插件
        """
        core.load(tuple(t.module for t in toys))
        core.reset_state(state)


def flag(name: str) -> core.Trigger:
    """
    角色数据里 name 为真时成立的条件
    Keyword arguments:
    name -- 数据键
    Return arguments:
    Trigger -- 条件
    """
    return lambda state, who: core.value(state, who, name) is True
