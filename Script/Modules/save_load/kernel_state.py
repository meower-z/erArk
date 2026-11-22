"""
save_load 的内核状态：存档时把 GameState 写成 JSON 放在缓存旁边，读档、新游戏时换掉内核的 GameState
===================================================================================================
存档目录里的文件 "2" 是 core.state() 的 JSON：版本、本次存档的标记、时钟、每个角色的行动与数据、全局数据。
Fraction 写成 {"$frac": str(分数)}，例如 Fraction(7, 72) 写成 "7/72"，Fraction(3, 1) 写成 "3"。
存档头（文件 "0"）里记着同一个标记。头里有标记的是版本 1 起的存档。头里没有标记的是旧存档（版本 0）。
头里有标记时，文件 "2" 缺失、损坏、标记不同或版本过高都拒绝读档。
每次 core.reset_state 都带 why（{"cause": ...}），save_load.reset 按它选要跑的步骤。
读档 load 换入文件 "2" 的 GameState，旧存档没有这个文件时换入存档头游戏时间的空 GameState。
读档的步骤装好存档的缓存、修补，没有角色时由缓存投影。new_game 换入开局时刻的空 GameState，步骤由建好的缓存投影。
new_round 以继承选择换入开局时刻，步骤建新周目。步骤运行时 game_time.now() 已是换入的时钟。
core.reset_state 在玩家选行动时调用会中止这次选择，所以 load 与 new_game 总是调用方最后做的事。
读档与新周目的步骤会改缓存。换入失败时，缓存与内核状态一起回到换入前。
"""

import datetime
import json
import os
import pickle
from collections.abc import Mapping
from fractions import Fraction
from types import MappingProxyType
from typing import Any

from Script.Config import normal_config
from Script.Core import cache_control
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.save_load import index, upgrade

SAVE_FILE = "2"
""" 存档目录里内核状态的文件名 """
TOKEN = "state_token"
""" 存档头与文件 "2" 里本次存档的标记的键 """
FRAC = "$frac"
""" 文件 "2" 里 Fraction 的标签 """


class SaveRefused(RuntimeError):
    """拒绝读档：存档头有标记，文件 "2" 却缺失、不是 JSON、没有整数版本、标记不同或版本过高"""


def _plain(value: core.JSON) -> object:
    """
    冻结的 JSON 值换成 json 能写的 dict 与 list，Fraction 换成 {"$frac": str(分数)}
    Keyword arguments:
    value -- 冻结的 JSON 值，只有一个键 "$frac" 且值是字符串的映射报 TypeError（它读回会变成 Fraction）
    Return arguments:
    object -- dict、list 或基本类型
    """
    if isinstance(value, Fraction):
        return {FRAC: str(value)}
    if isinstance(value, Mapping):
        if set(value) == {FRAC} and isinstance(value[FRAC], str):
            raise TypeError(f"{value!r} reads back as a Fraction")
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _frozen(value: object, tagged: bool) -> core.JSON:
    """
    json 读回的值冻结成内核的样子：dict 换成只读映射，list 换成 tuple。
    tagged 时，只有一个键 "$frac" 且值是字符串的 dict 换回 Fraction
    Keyword arguments:
    value -- json 读回的值
    tagged -- 文件版本 1 起为真
    Return arguments:
    JSON -- 冻结的值
    """
    if isinstance(value, dict):
        if tagged and set(value) == {FRAC} and isinstance(value[FRAC], str):
            return Fraction(value[FRAC])
        return MappingProxyType(
            {k: _frozen(v, tagged) for k, v in value.items()}
        )
    if isinstance(value, list):
        return tuple(_frozen(item, tagged) for item in value)
    if value is None or isinstance(value, bool | int | float | str):
        return value
    raise TypeError(f"{value!r} is not JSON")


def _frozen_data(value: object, tagged: bool) -> Mapping[str, core.JSON]:
    """
    json 读回的一张数据表冻结成只读映射，不是 dict 时报 TypeError
    Keyword arguments:
    value -- json 读回的 dict
    tagged -- 文件版本 1 起为真
    Return arguments:
    Mapping -- 只读映射
    """
    if not isinstance(value, dict):
        raise TypeError(f"{value!r} is not a JSON object")
    return MappingProxyType({k: _frozen(v, tagged) for k, v in value.items()})


def encode(game: core.GameState, token: str) -> dict[str, Any]:
    """
    GameState 换成文件 "2" 的 JSON 对象
    Keyword arguments:
    game -- 状态
    token -- 本次存档的标记
    Return arguments:
    dict -- 带版本 upgrade.CURRENT 与标记的 JSON 对象
    """
    return {
        "version": upgrade.CURRENT,
        TOKEN: token,
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


def decode(data: dict[str, Any], tagged: bool) -> core.GameState:
    """
    文件 "2" 的 JSON 对象换回冻结的 GameState
    Keyword arguments:
    data -- JSON 对象
    tagged -- 文件版本 1 起为真，这时 Fraction 的标签换回 Fraction
    Return arguments:
    GameState -- 状态
    """
    characters = {
        who: core.Character(
            core.Action(
                who,
                c["action"]["action_id"],
                _frozen(c["action"]["action_data"], tagged),
                c["action"]["start"],
                c["action"]["duration"],
            ),
            _frozen_data(c["data"], tagged),
        )
        for who, c in data["characters"].items()
    }
    return core.GameState(
        data["clock"],
        MappingProxyType(characters),
        _frozen_data(data["data"], tagged),
    )


def write(save_id: str, token: str) -> None:
    """
    把 core.state() 写成存档目录里的文件 "2"：先写临时文件，再用 os.replace 换进去
    Keyword arguments:
    save_id -- 存档id
    token -- 本次存档的标记，与存档头里的相同
    """
    data = encode(core.state(), token)
    os.makedirs(index.path(save_id), exist_ok=True)
    file_path = os.path.join(index.path(save_id), SAVE_FILE)
    with open(file_path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(file_path + ".tmp", file_path)


def _json(save_id: str) -> object:
    """
    读文件 "2" 的 JSON。没有这个文件、不是 UTF-8 或不是 JSON 时为 None
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    object -- json 读回的值或 None
    """
    file_path = os.path.join(index.path(save_id), SAVE_FILE)
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def read(save_id: str) -> tuple[core.GameState | None, int]:
    """
    读回存档里的 GameState 与它的版本。存档头有标记时，文件 "2" 必须是 JSON、有整数版本且标记相同，
    版本也不能高于 upgrade.CURRENT，否则抛 SaveRefused。版本较低时依次跑 upgrade.STEPS 升到当前版本
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    tuple -- (GameState, 版本)。旧存档的版本为 0，没有可读的文件 "2" 时 GameState 为 None
    """
    token = index.head(save_id).get(TOKEN)
    data = _json(save_id)
    if token is None:
        if not isinstance(data, dict):
            return None, 0
        return decode(data, tagged=False), 0
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("version"), int)
        or data.get(TOKEN) != token
    ):
        raise SaveRefused(
            f"存档 {save_id} 的文件 {SAVE_FILE} 缺失、损坏或与存档头不符"
        )
    version = data["version"]
    if version > upgrade.CURRENT:
        raise SaveRefused(
            f"存档 {save_id} 的版本 {version} 高于 {upgrade.CURRENT}"
        )
    while version < upgrade.CURRENT:
        data = upgrade.STEPS[version](data)
        version += 1
    return decode(data, tagged=True), version


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
    core.reset_state(_empty(clock), {"cause": "boot"})


def _empty(clock: int) -> core.GameState:
    """
    没有角色的 GameState
    Keyword arguments:
    clock -- 时钟
    Return arguments:
    GameState -- 只有时钟的 GameState
    """
    return core.GameState(clock, MappingProxyType({}), MappingProxyType({}))


def _reset_keeping_cache(game: core.GameState, why: core.Data) -> None:
    """
    以 why 换入 game。Reset 抛出异常且内核状态未切换时，缓存换回换入前的副本，随后重新抛出异常。
    无论是否抛出异常，finally 都在内核状态未切换时丢弃读档暂存的 AI 设置，在状态已切换时提交并保存它。
    Keyword arguments:
    game -- 换入的状态
    why -- 换入的原因
    """
    from Script.Modules.gameplay_resolution import draft
    from Script.Modules.save_load import settings

    # 选择的草稿里换入时先换回原物，草稿之后关闭时什么也不做
    draft.abandon()
    cache = cache_control.cache
    # 换入前留一份缓存的 pickle（存档也这样 pickle 整个缓存），钩子出错时换回
    data = pickle.dumps(cache.__dict__, pickle.HIGHEST_PROTOCOL)
    before = core.state()
    try:
        core.reset_state(game, why)
    except BaseException:
        # 换入成功时（选行动中）也会抛出中止，那时内核的状态已换掉
        if core.state() is before:
            cache.__dict__.clear()
            cache.__dict__.update(pickle.loads(data))
        raise
    finally:
        # 内核状态已切换才提交暂存 AI 设置（含换态后中止选择），未切换则丢弃
        if core.state() is before:
            settings.drop_pending_ai()
        else:
            settings.commit_pending_ai()


def load(save_id: str) -> None:
    """
    读档：内核换成存档里的 GameState，旧存档换成存档头游戏时间的空 GameState，Reset 的步骤装好存档的缓存；
    玩家选行动时调用则中止这次选择，下一步在读回的 GameState 上从头开始
    Keyword arguments:
    save_id -- 存档id
    """
    game, version = read(save_id)
    if game is None:
        saved_at = game_time.to_game_time(index.head(save_id)["game_time"])
        game = _empty(game_time.minutes(saved_at))
    why: dict[str, core.JSON] = {
        "cause": "load",
        "save": save_id,
        "version": version,
    }
    _reset_keeping_cache(game, why)


def new_game(clock: int, effects: core.Effects = ()) -> None:
    """
    新游戏的最后一步（缓存已建好）：内核换成 clock 时刻的空 GameState 套上 effects，Reset 的步骤再由缓存投影出角色。
    空状态里没有角色，effects 写的角色数据先在 roster.offstage 里，Reset 的步骤把投影出的角色的数据移进各自的角色数据
    Keyword arguments:
    clock -- 开局的时钟
    effects -- 建角色时写进缓冲区的 GameState 数据换成的效果，默认没有
    """
    core.reset_state(
        core.preview(_empty(clock), effects), {"cause": "new_game"}
    )


def new_round(choices: Mapping[str, core.JSON]) -> None:
    """
    开始新周目：内核换成开局时刻、没有角色的 GameState，Reset 的步骤按继承选择建新周目并投影角色；
    玩家选行动时调用则中止这次选择
    Keyword arguments:
    choices -- 继承选择
    """
    why: Mapping[str, core.JSON] = {"cause": "new_round", "inherit": choices}
    _reset_keeping_cache(_empty(first_clock()), why)
