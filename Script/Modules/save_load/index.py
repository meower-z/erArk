"""
save_load 的存档索引
====================
每个存档占 save/ 下的一个目录。当前版本的存档为单个文件 save.json。
旧存档含文件 "0"（存档头）与 "1"（缓存），版本 1 至 27 的旧存档另含文件 "2"。
本模块列出槽位、读取 save.json 与存档头，不登记行动、事件或规则，也不在 LOAD_ORDER 里。
"""

import datetime
import json
import os
from typing import Any

from Script.Modules.save_load import legacy_pickle

SAVE_DIR = "save"
""" 存档根目录，相对游戏根目录 """
SAVE_FILE = "save.json"
""" 当前版本存档的文件名 """
HEAD_FILE = "0"
""" 旧存档的存档头文件名 """
CACHE_FILE = "1"
""" 旧存档的缓存文件名 """


class SaveRefused(RuntimeError):
    """无法读取的存档异常：损坏的 save.json、过高的版本，或残缺的旧存档"""


def path(save_id: str) -> str:
    """
    存档目录的路径；存档根目录不在时先建出来
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    str -- 存档目录的路径
    """
    os.makedirs(SAVE_DIR, exist_ok=True)
    return os.path.join(SAVE_DIR, save_id)


def file(save_id: str, name: str) -> str:
    """
    返回存档目录内指定文件的路径
    Keyword arguments:
    save_id -- 存档id
    name -- 文件名
    Return arguments:
    str -- 文件路径
    """
    return os.path.join(path(save_id), name)


def is_json(save_id: str) -> bool:
    """
    存档槽位存在 save.json 时为 True
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    bool -- 是否为 save.json 槽位
    """
    return os.path.isfile(file(save_id, SAVE_FILE))


def document(save_id: str) -> dict[str, Any]:
    """
    读取 save.json；不是 UTF-8 JSON、不是 JSON 对象、缺少整型 version 或缺少 dict 类型 head 时抛 SaveRefused
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    dict -- 解析出的 JSON 对象
    """
    try:
        with open(file(save_id, SAVE_FILE), encoding="utf-8") as f:
            data = json.load(f)
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = None
    if (
        not isinstance(data, dict)
        or type(data.get("version")) is not int
        or not isinstance(data.get("head"), dict)
    ):
        raise SaveRefused(f"存档 {save_id} 的 {SAVE_FILE} 损坏")
    return data


def head(save_id: str) -> dict[str, Any]:
    """
    读存档头。槽位存在 save.json 时从中读取并解析 game_time 与 save_time（缺失或无效时抛 SaveRefused），
    否则经 legacy_pickle 读取旧存档文件 "0"
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    dict -- 存档头的数据：游戏版本、游戏时间、博士的名字、存档时间
    """
    if not is_json(save_id):
        return legacy_pickle.head(file(save_id, HEAD_FILE))
    from Script.Design import game_time

    saved = dict(document(save_id)["head"])
    try:
        saved["game_time"] = game_time.GameTime.fromisoformat(
            saved["game_time"]
        )
        saved["save_time"] = datetime.datetime.fromisoformat(saved["save_time"])
    except (KeyError, TypeError, ValueError):
        raise SaveRefused(f"存档 {save_id} 的存档头损坏") from None
    return saved


def slots() -> list[str]:
    """
    列出 save/ 下现有的存档：含 save.json 的目录，或同时含旧存档文件 "0" 与 "1" 的目录
    Return arguments:
    list -- 存档id，按名字排序
    """
    os.makedirs(SAVE_DIR, exist_ok=True)
    return sorted(
        save_id
        for save_id in os.listdir(SAVE_DIR)
        if os.path.isfile(os.path.join(SAVE_DIR, save_id, SAVE_FILE))
        or (
            os.path.isfile(os.path.join(SAVE_DIR, save_id, HEAD_FILE))
            and os.path.isfile(os.path.join(SAVE_DIR, save_id, CACHE_FILE))
        )
    )
