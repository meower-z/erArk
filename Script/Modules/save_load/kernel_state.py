"""
save_load 的内核状态：存档时把 GameState 写在缓存旁边，读档时读回
==================================================================
GameState 写成只含 dict、tuple 与基本类型的数据（存档文件 "2"），读档后由它重建；
旧存档没有这个文件，下次跑内核时从缓存重建。跑内核前 GameState 总会按缓存对齐一次。
"""

import os
import pickle
from collections.abc import Mapping
from types import MappingProxyType

from Script.Kernel import core

_loaded: core.GameState | None = None
""" 读档读回、还没交给内核的 GameState """

SAVE_FILE = "2"
""" 存档目录里内核状态的文件名 """


def _plain(value: core.JSON) -> object:
    """
    冻结的 JSON 值换成 dict 与 tuple
    Keyword arguments:
    value -- 冻结的 JSON 值
    Return arguments:
    object -- 可 pickle 的值
    """
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_plain(item) for item in value)
    return value


def save_data() -> dict:
    """
    当前 GameState 写成存档数据
    Return arguments:
    dict -- 时钟、每个角色的行动与数据、全局数据
    """
    game = core.state()
    return {
        "clock": game.clock,
        "characters": {
            who: {
                "action": {
                    "action_id": c.action.action_id,
                    "action_data": _plain(c.action.action_data),
                    "start": c.action.start,
                    "duration": c.action.duration,
                },
                "data": _plain(c.data),
            }
            for who, c in game.characters.items()
        },
        "data": _plain(game.data),
    }


def load_data(data: dict | None) -> None:
    """
    读档：由存档数据重建 GameState，交给下一次 core.run；没有数据（旧存档）时下次从缓存重建
    Keyword arguments:
    data -- save_data 写下的数据，或 None
    """
    global _loaded
    if data is None:
        _loaded = core.GameState(0, MappingProxyType({}), MappingProxyType({}))
        return
    characters = {
        who: core.Character(
            core.Action(
                who,
                c["action"]["action_id"],
                c["action"]["action_data"],
                c["action"]["start"],
                c["action"]["duration"],
            ),
            MappingProxyType(c["data"]),
        )
        for who, c in data["characters"].items()
    }
    _loaded = core.GameState(
        data["clock"],
        MappingProxyType(characters),
        MappingProxyType(data["data"]),
    )


def take() -> core.GameState:
    """
    下一次 core.run 的起始 GameState：读档读回的，否则上一次跑完的
    Return arguments:
    GameState -- 起始 GameState（第一次跑时没有角色）
    """
    global _loaded
    game, _loaded = _loaded, None
    return core.state() if game is None else game


def forget() -> None:
    """内核出错后丢掉 GameState，下次从缓存重建"""
    load_data(None)


def write(save_id: str) -> None:
    """
    存档时把当前 GameState 写进存档目录的文件 "2"
    Keyword arguments:
    save_id -- 存档id
    """
    from Script.Core import save_handle

    save_handle.write_save_data(save_id, SAVE_FILE, save_data())


def read(save_id: str) -> None:
    """
    读档后读回存档里的 GameState（旧存档没有，下次跑内核时从缓存重建），并丢掉内核里本局之前的状态
    Keyword arguments:
    save_id -- 存档id
    """
    from Script.Core import save_handle
    from Script.Design import update

    path = os.path.join(save_handle.get_save_dir_path(save_id), SAVE_FILE)
    data = None
    if os.path.exists(path):
        with open(path, "rb") as f:
            data = pickle.load(f)
    update.reset_kernel(data)
