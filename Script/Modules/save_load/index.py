"""
save_load 的存档索引
====================
存档都在游戏根目录的 save 下，一个存档一个目录：文件 "0" 是存档头（存档列表显示的信息），
"1" 是缓存，"2" 是内核状态。这里管存档目录、读写存档头，并列出现有的存档。
本模块不登记行动、事件或规则，也不在 LOAD_ORDER 里。
"""

import os
import pickle

SAVE_DIR = "save"
""" 存档根目录，相对游戏根目录 """
HEAD_FILE = "0"
""" 存档目录里存档头的文件名 """
CACHE_FILE = "1"
""" 存档目录里缓存的文件名 """


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


def head(save_id: str) -> dict:
    """
    读存档头
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    dict -- 存档头的数据：游戏版本、游戏时间、博士的名字、存档时间
    """
    with open(os.path.join(path(save_id), HEAD_FILE), "rb") as f:
        return pickle.load(f)


def write_head(save_id: str, head: dict) -> None:
    """
    写存档头，存档目录不在时先建出来
    Keyword arguments:
    save_id -- 存档id
    head -- 存档头的数据
    """
    os.makedirs(path(save_id), exist_ok=True)
    with open(os.path.join(path(save_id), HEAD_FILE), "wb") as f:
        pickle.dump(head, f)


def slots() -> list[str]:
    """
    现有的存档：存档头与缓存都在的存档目录
    Return arguments:
    list -- 存档id，按名字排序
    """
    os.makedirs(SAVE_DIR, exist_ok=True)
    return sorted(
        save_id
        for save_id in os.listdir(SAVE_DIR)
        if os.path.isfile(os.path.join(SAVE_DIR, save_id, HEAD_FILE))
        and os.path.isfile(os.path.join(SAVE_DIR, save_id, CACHE_FILE))
    )
