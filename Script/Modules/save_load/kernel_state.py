"""
save_load 的内核状态：存档写入 save.json，读档、新游戏与新周目换掉内核的 GameState
==================================================================================
当前存档 save.json 存 orders.settled(core.state()) 的 JSON（版本、时钟、各角色行动与数据、全局数据）
以及存档头 head。Fraction 写成 {"$frac": str(分数)}，例如 Fraction(7, 72) 写成 "7/72"，
Fraction(3, 1) 写成 "3"。
旧存档（版本 0 至 27）只读：版本 0 没有存档标记；版本 1 至 27 在文件 "0" 与文件 "2" 记着同一个标记，
文件 "2" 缺失、损坏、标记不同或版本过高都抛 SaveRefused。
save.json 损坏、版本低于 28 或高于当前版本同样抛 SaveRefused。
每次 core.reset_state 都带 why（{"cause": ...}），save_load.reset 按它选要跑的步骤。
读档 load 换入存档里的 GameState，版本 0 的旧存档没有文件 "2" 时换入存档头游戏时间的空 GameState。
读档步骤完成导入与修补，无角色时由领域数据投影。new_game 换入开局时刻空 GameState 并投影。
new_round 以继承选择换入开局时刻，步骤建新周目。步骤运行时 game_time.now() 已是换入的时钟。
core.reset_state 在玩家选行动时调用会中止这次选择，所以 load 与 new_game 总是调用方最后做的事。
换入失败时内核状态保持换入前的对象，待生效的 AI 设置随之丢弃。
"""

import datetime
import contextlib
import json
import os
from collections.abc import Mapping
from fractions import Fraction
from types import MappingProxyType
from typing import Any

from Script.Config import normal_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.save_load import index, upgrade
from Script.Modules.tk_ui import orders

LEGACY_FILE = "2"
""" 旧存档（版本 1 至 27）的内核状态文件名 """
TOKEN = "state_token"
""" 版本 1 至 27 的旧存档在存档头与文件 "2" 中存放校验标记的键名 """
FRAC = "$frac"
""" 存档里 Fraction 的标签 """
JSON_SINCE = 28
""" 以 save.json 写出的最低存档版本 """


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


def encode(game: core.GameState) -> dict[str, Any]:
    """
    把 GameState 编码为存档用的 JSON 对象（不含 head）
    Keyword arguments:
    game -- 状态
    Return arguments:
    dict -- 带版本 upgrade.CURRENT 的 JSON 对象
    """
    return {
        "version": upgrade.CURRENT,
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
    把存档的 JSON 对象换回冻结的 GameState
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


def write(save_id: str, head: Mapping[str, core.JSON]) -> None:
    """
    把 orders.settled(core.state()) 与 head 原子写入 save.json：先写临时文件并 flush、os.fsync，
    再经 os.replace 替换 save.json（出错时删掉临时文件，原 save.json 不变）；
    替换后删除该槽位残留的旧文件 "0"、"1" 与 "2"
    Keyword arguments:
    save_id -- 存档id
    head -- 存档头字段，值为 JSON 类型
    """
    data = {**encode(orders.settled(core.state())), "head": dict(head)}
    os.makedirs(index.path(save_id), exist_ok=True)
    file_path = index.file(save_id, index.SAVE_FILE)
    temporary = file_path + ".tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, file_path)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.remove(temporary)
        raise
    for name in (index.HEAD_FILE, index.CACHE_FILE, LEGACY_FILE):
        with contextlib.suppress(FileNotFoundError):
            os.remove(index.file(save_id, name))


def _legacy_json(save_id: str) -> object:
    """
    读取旧存档的文件 "2"；文件缺失、非 UTF-8 或不是合法 JSON 时返回 None
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    object -- json 读回的值或 None
    """
    try:
        with open(index.file(save_id, LEGACY_FILE), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _upgraded(
    save_id: str, data: dict[str, Any], lowest: int
) -> tuple[core.GameState, int]:
    """
    校验 lowest <= version <= upgrade.CURRENT（越界时抛 SaveRefused），
    沿 upgrade.STEPS 升到当前版本并解码为 GameState；解码失败时抛 SaveRefused
    Keyword arguments:
    save_id -- 存档id
    data -- 带整型 version 的 JSON 对象
    lowest -- 该存档格式允许的最低版本
    Return arguments:
    tuple -- (GameState, 版本)
    """
    version = data["version"]
    if version > upgrade.CURRENT:
        raise index.SaveRefused(
            f"存档 {save_id} 的版本 {version} 高于 {upgrade.CURRENT}"
        )
    if version < lowest:
        raise index.SaveRefused(f"存档 {save_id} 的版本 {version} 无效")
    while version < upgrade.CURRENT:
        data = upgrade.STEPS[version](data)
        version += 1
    try:
        return decode(data, tagged=True), version
    except (KeyError, TypeError, AttributeError):
        raise index.SaveRefused(f"存档 {save_id} 的状态损坏") from None


def read(save_id: str) -> tuple[core.GameState | None, int]:
    """
    读回存档里的 GameState 与版本。
    save.json 槽位只读 save.json；旧槽位存档头带标记时，文件 "2" 须为合法 JSON、含整型 version 且标记相符。
    版本高于 upgrade.CURRENT 或低于格式下限时抛 SaveRefused，较低版本沿 upgrade.STEPS 升级
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    tuple -- (GameState, 版本)。版本 0 的旧存档返回版本 0，没有可读的文件 "2" 时 GameState 为 None
    """
    if index.is_json(save_id):
        return _upgraded(save_id, index.document(save_id), JSON_SINCE)
    token = index.head(save_id).get(TOKEN)
    data = _legacy_json(save_id)
    if token is None:
        if not isinstance(data, dict):
            return None, 0
        return decode(data, tagged=False), 0
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("version"), int)
        or data.get(TOKEN) != token
    ):
        raise index.SaveRefused(
            f"存档 {save_id} 的文件 {LEGACY_FILE} 缺失、损坏或与存档头不符"
        )
    return _upgraded(save_id, data, 1)


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


def _reset(game: core.GameState, why: core.Data) -> None:
    """
    以 why 换入 game。
    finally 中按内核状态是否变化处理读档准备的 AI 设置：未换入时丢弃，
    换入后提交并写盘（包括选择中换态后中止选择的情况）
    Keyword arguments:
    game -- 换入的状态
    why -- 换入的原因
    """
    from Script.Modules.save_load import settings

    before = core.state()
    try:
        core.reset_state(game, why)
    finally:
        if core.state() is before:
            settings.drop_pending_ai()
        else:
            settings.commit_pending_ai()


def load(save_id: str) -> None:
    """
    读档：内核换成存档里的 GameState，版本 0 旧存档无文件 "2" 时换成存档头游戏时间的空 GameState，
    Reset 的步骤完成导入与修补；玩家选行动时调用则中止这次选择，下一步在读回的 GameState 上从头开始
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
    _reset(game, why)


def new_game(clock: int, effects: core.Effects = ()) -> None:
    """
    新游戏的最后一步：内核换成 clock 时刻的空 GameState 套上 effects，Reset 的步骤再由领域数据投影出角色。
    空状态里没有角色，effects 写的角色数据先在 roster.offstage 里，
    Reset 的步骤把投影出的角色的数据移进各自的角色数据
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
    _reset(_empty(first_clock()), why)
