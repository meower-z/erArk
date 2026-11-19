# -*- coding: UTF-8 -*-
"""
草稿的编码、比较与应用走遍存档 99 的缓存
========================================
读用户存档 99（不入库，装在 save/99 时才跑，没装时报跳过）。
打开一个草稿（draft.Session），把缓存的每个顶层属性（界面状态与全局设置之外）都取一遍副本，
在每个顶层属性里找到的每种叶子类型（int、bool、float、str、Fraction、datetime、UUID、None）各改一个值，
再各改一个列表、一个集合、一个字典的键：关上草稿得到改动（draft.diff），
经 json 往返后应用到原来的缓存上（draft.apply）。
之后每个顶层属性的编码（draft.encode）与改过的副本相同。编码不了的类型在关草稿时就报 TypeError 并给出路径。
"""

import datetime
import importlib
import json
import os
import uuid
from collections.abc import Iterator
from fractions import Fraction
from typing import Any

from tests.slow.base import SlowTestCase

USER_SAVE_ID = "99"
""" 用户存档的存档id（不入库，装在 save/99） """


def mutated(value: object) -> object:
    """
    叶子值改过之后的值，类型不变；不是叶子时返回 value 本身
    Keyword arguments:
    value -- 原来的值
    Return arguments:
    object -- 改过的值
    """
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 0.5
    if isinstance(value, Fraction):
        return value + Fraction(1, 3)
    if isinstance(value, str):
        return value + "改"
    if isinstance(value, datetime.datetime):
        return value + datetime.timedelta(minutes=1)
    if isinstance(value, uuid.UUID):
        return uuid.UUID(int=value.int ^ 1)
    if value is None:
        return 0
    return value


def kind(value: object) -> str:
    """叶子与容器按类型分组的名字"""
    if isinstance(value, datetime.datetime):
        return "datetime"
    return type(value).__name__


def slots(node: object) -> Iterator[tuple[object, Any, object]]:
    """
    一个节点下可以改的位置
    Keyword arguments:
    node -- 字典、列表或带 __dict__ 的对象
    Return arguments:
    Iterator -- (容器, 键或下标或属性名, 值)
    """
    if isinstance(node, dict):
        for key, value in list(node.items()):
            yield node, key, value
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield node, index, value
    elif hasattr(node, "__dict__") and not isinstance(node, type):
        for name, value in list(vars(node).items()):
            yield node, ("attr", name), value


def put(parent: Any, key: Any, value: object) -> None:
    """在容器的这个位置写入 value"""
    if isinstance(key, tuple) and key[:1] == ("attr",):
        setattr(parent, key[1], value)
    else:
        parent[key] = value


class DraftCodecSweepTest(SlowTestCase):
    """草稿走遍存档 99 的缓存"""

    time_limit = 900

    def test_every_leaf_type_round_trips(self) -> None:
        """每个顶层属性里的每种叶子类型各改一个，再改列表、集合与字典键：应用之后与改过的副本编码相同"""
        constant = importlib.import_module("Script.Core.constant")
        save_handle = importlib.import_module("Script.Core.save_handle")
        draft = importlib.import_module(
            "Script.Modules.gameplay_resolution.draft"
        )
        player_pick = importlib.import_module(
            "Script.Modules.tk_ui.player_pick"
        )
        if not os.path.isdir(os.path.join("save", USER_SAVE_ID)):
            self.skipTest("用户存档 99 没装在 save/99")
        save_handle.input_load_save(USER_SAVE_ID)
        self.cache.now_panel_id = constant.Panel.IN_SCENE
        keep = player_pick.UI_STATE | player_pick.META_STATE
        session = draft.Session(keep)
        copies: dict[str, object] = {}
        changed: dict[str, list[str]] = {}
        try:
            for name in sorted(session.orig):
                if name in session.keep:
                    continue
                copy = getattr(self.cache, name)
                copies[name] = copy
                changed[name] = self.mutate_one_of_each(copy)
            changes, _interrupts = session.close()
        except BaseException:
            if draft.active():
                session.drop()
            raise
        changes = json.loads(json.dumps(changes))
        draft.apply(changes)
        unequal = [
            name
            for name, copy in copies.items()
            if draft.encode(dict(copy) if isinstance(copy, dict) else copy)
            != draft.encode(getattr(self.cache, name))
        ]
        kinds = sorted({k for found in changed.values() for k in found})
        self.assertGreater(len(changes), 0)
        self.assertEqual(unequal, [], f"改过的类型：{kinds}")

    def mutate_one_of_each(self, root: object) -> list[str]:
        """
        在 root 下每种叶子类型各改一个值，再改一个列表（追加）、一个集合（去掉一个元素）、一个字典（去掉一个键）
        Keyword arguments:
        root -- 顶层属性的副本
        Return arguments:
        list -- 改过的类型名
        """
        done: set[str] = set()
        stack: list[object] = [root]
        seen: set[int] = set()
        while stack:
            node = stack.pop()
            if id(node) in seen:
                continue
            seen.add(id(node))
            if isinstance(node, dict) and node and "dict" not in done:
                del node[next(iter(node))]
                done.add("dict")
                continue
            for parent, key, value in slots(node):
                group = kind(value)
                new = mutated(value)
                if new is not value and new != value:
                    if group not in done:
                        put(parent, key, new)
                        done.add(group)
                    continue
                if isinstance(value, list) and "list" not in done:
                    value.append(value[0] if value else 0)
                    done.add("list")
                elif isinstance(value, set) and value and "set" not in done:
                    value.discard(next(iter(value)))
                    done.add("set")
                stack.append(value)
        return sorted(done)
