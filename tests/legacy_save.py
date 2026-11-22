# -*- coding: UTF-8 -*-
"""
读档测试用的旧存档构造辅助
==========================
old(name, **attrs) 构造按 Script.Core.game_type.<name>（Cache、Character 或 Rhodes_Island）序列化的替身对象；
write_cache 与 write_head 分别写出旧槽位的文件 "1" 与 "0"，write_state 写出旧槽位的文件 "2"，
to_legacy 把一个 save.json 槽位转换成指定版本的旧槽位。
"""

import contextlib
import json
import os
import pickle
from collections.abc import Iterator, Mapping
from typing import Any
from unittest import mock

from Script.Core import game_type
from Script.Modules.save_load import index, kernel_state

NAMES = ("Cache", "Character", "Rhodes_Island")
""" 旧存档替身类的类名列表 """


def _stand_in(name: str) -> type:
    return type(
        name, (), {"__module__": game_type.__name__, "__qualname__": name}
    )


STAND_INS = {name: _stand_in(name) for name in NAMES}
""" 类名到挂在 Script.Core.game_type 命名空间下的替身类映射 """


@contextlib.contextmanager
def old_classes() -> Iterator[None]:
    """上下文打开期间把替身类挂到 game_type 上，以便 pickle 按类名序列化"""
    with contextlib.ExitStack() as stack:
        for name, cls in STAND_INS.items():
            stack.enter_context(
                mock.patch.object(game_type, name, cls, create=True)
            )
        yield


def old(name: str, /, **attrs: Any) -> Any:
    """
    创建带 attrs 属性的替身对象
    Keyword arguments:
    name -- NAMES 中的类名
    attrs -- 写入对象的属性键值对
    Return arguments:
    Any -- 替身对象
    """
    obj = STAND_INS[name]()
    vars(obj).update(attrs)
    return obj


def dumps(value: object) -> bytes:
    """
    把 value 序列化为 pickle 字节串，替身类按 game_type 下的类名写出
    Keyword arguments:
    value -- 待序列化的值
    Return arguments:
    bytes -- pickle 字节串
    """
    with old_classes():
        return pickle.dumps(value)


def write_cache(save_id: str, cache: object) -> None:
    """
    写出旧存档槽位的文件 "1"
    Keyword arguments:
    save_id -- 存档id
    cache -- 缓存对象，通常由 old("Cache", ...) 构造
    """
    os.makedirs(index.path(save_id), exist_ok=True)
    with open(index.file(save_id, index.CACHE_FILE), "wb") as f:
        f.write(dumps(cache))


def write_head(save_id: str, head: Mapping[str, object]) -> None:
    """
    写出旧存档槽位的文件 "0"
    Keyword arguments:
    save_id -- 存档id
    head -- 存档头字段（版本 1 至 27 的旧槽位含 kernel_state.TOKEN）
    """
    os.makedirs(index.path(save_id), exist_ok=True)
    with open(index.file(save_id, index.HEAD_FILE), "wb") as f:
        f.write(dumps(dict(head)))


def write_state(save_id: str, data: Mapping[str, object]) -> None:
    """
    写出旧存档槽位的文件 "2"
    Keyword arguments:
    save_id -- 存档id
    data -- JSON 对象
    """
    os.makedirs(index.path(save_id), exist_ok=True)
    with open(
        index.file(save_id, kernel_state.LEGACY_FILE), "w", encoding="utf-8"
    ) as f:
        json.dump(data, f, ensure_ascii=False)


def to_legacy(save_id: str, cache: object, version: int = 27) -> None:
    """
    把槽位的 save.json 转换为指定版本（1 至 27）的旧槽位：删除 save.json，
    带校验标记的存档头写为文件 "0"，cache 写为文件 "1"，带同标记与目标版本的状态写为文件 "2"
    Keyword arguments:
    save_id -- 存档id
    cache -- 缓存对象，通常由 old("Cache", ...) 构造
    version -- 写入文件 "2" 的版本号
    """
    data = index.document(save_id)
    head = index.head(save_id)
    os.remove(index.file(save_id, index.SAVE_FILE))
    token = "legacy-token"
    state = {key: value for key, value in data.items() if key != "head"}
    state.update({"version": version, kernel_state.TOKEN: token})
    write_head(save_id, {**head, kernel_state.TOKEN: token})
    write_cache(save_id, cache)
    write_state(save_id, state)
