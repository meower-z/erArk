"""
save_load 的内核状态：存档时把 GameState 写成 JSON 放在缓存旁边，读档、新游戏时换掉内核的 GameState
====================================================================================================
存档目录里的文件 "2" 是 core.state() 的 JSON：时钟、每个角色的行动与数据、全局数据。
读档时 restore 读回它，经 core.reset_state 交给内核；旧存档没有这个文件，由缓存投影出 GameState。
新游戏与新周目经 new_game 由缓存在开局时刻投影。
core.reset_state 在玩家选行动时调用会中止这次选择，所以 restore 与 new_game 总是调用方最后做的事。
"""

import datetime
import json
import os
from collections.abc import Mapping
from types import MappingProxyType

from Script.Config import normal_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions
from Script.Modules.save_load import index

SAVE_FILE = "2"
""" 存档目录里内核状态的文件名 """


def _plain(value: core.JSON) -> object:
    """
    冻结的 JSON 值换成 json 能写的 dict 与 list
    Keyword arguments:
    value -- 冻结的 JSON 值
    Return arguments:
    object -- dict、list 或基本类型
    """
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _frozen(value: object) -> core.JSON:
    """
    json 读回的值冻结成内核的样子：dict 换成只读映射，list 换成 tuple
    Keyword arguments:
    value -- json 读回的值
    Return arguments:
    JSON -- 冻结的值
    """
    if isinstance(value, dict):
        return MappingProxyType({k: _frozen(v) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_frozen(item) for item in value)
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise TypeError(f"{value!r} is not JSON")


def _frozen_data(value: object) -> Mapping[str, core.JSON]:
    """
    json 读回的一张数据表冻结成只读映射
    Keyword arguments:
    value -- json 读回的 dict
    Return arguments:
    Mapping -- 只读映射
    """
    if not isinstance(value, dict):
        raise TypeError(f"{value!r} is not a JSON object")
    return MappingProxyType({k: _frozen(v) for k, v in value.items()})


def write(save_id: str) -> None:
    """
    把 core.state()（总是一步的边界）写成 JSON，放进存档目录的文件 "2"
    Keyword arguments:
    save_id -- 存档id
    """
    game = core.state()
    data = {
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
    os.makedirs(index.path(save_id), exist_ok=True)
    with open(
        os.path.join(index.path(save_id), SAVE_FILE), "w", encoding="utf-8"
    ) as f:
        json.dump(data, f, ensure_ascii=False)


def read(save_id: str) -> core.GameState | None:
    """
    读回存档里的 GameState
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    GameState | None -- 存档里的 GameState，已冻结；没有文件 "2"、或它不是 JSON（旧存档）时为 None
    """
    file_path = os.path.join(index.path(save_id), SAVE_FILE)
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    characters = {
        who: core.Character(
            core.Action(
                who,
                c["action"]["action_id"],
                _frozen(c["action"]["action_data"]),
                c["action"]["start"],
                c["action"]["duration"],
            ),
            _frozen_data(c["data"]),
        )
        for who, c in data["characters"].items()
    }
    return core.GameState(
        data["clock"], MappingProxyType(characters), _frozen_data(data["data"])
    )


def first_clock() -> int:
    """
    开局时刻：config.ini 里的开局日期规整到游戏日历上
    Return arguments:
    int -- 内核时钟的分钟数
    """
    config = normal_config.config_normal
    start = datetime.datetime(
        config.year, config.month, config.day, config.hour, config.minute
    )
    return game_time.minutes(game_time.to_game_time(start))


def reset_clock(clock: int) -> None:
    """
    内核换成只有时钟、没有角色的 GameState（启动时、新游戏建角色前），读游戏时间的代码读到 clock
    Keyword arguments:
    clock -- 时钟
    """
    core.reset_state(_empty(clock))


def _empty(clock: int) -> core.GameState:
    """
    没有角色的 GameState
    Keyword arguments:
    clock -- 时钟
    Return arguments:
    GameState -- 只有时钟的 GameState
    """
    return core.GameState(clock, MappingProxyType({}), MappingProxyType({}))


def from_cache(clock: int) -> core.GameState:
    """
    由缓存在 clock 这一分钟投影出的 GameState（新游戏、新周目、没有文件 "2" 的旧存档）
    Keyword arguments:
    clock -- 投影的时钟
    Return arguments:
    GameState -- 投影出的 GameState
    """
    return actions.state_from_cache(clock)


def restore(save_id: str) -> None:
    """
    读档的最后一步（缓存已换成存档里的）：内核换成存档里的 GameState，旧存档由缓存在存档头的游戏时间投影；
    玩家选行动时调用则中止这次选择，下一步在读回的 GameState 上从头开始
    Keyword arguments:
    save_id -- 存档id
    """
    game = read(save_id)
    if game is None:
        saved_at = game_time.to_game_time(index.head(save_id)["game_time"])
        game = from_cache(game_time.minutes(saved_at))
    core.reset_state(game)


def new_game(clock: int) -> None:
    """
    新游戏、新周目的最后一步（缓存已建好）：内核换成由缓存在 clock 投影出的 GameState
    Keyword arguments:
    clock -- 开局的时钟
    """
    core.reset_state(from_cache(clock))
