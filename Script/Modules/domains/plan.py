"""
排着的行动、玩家的寻路与睡觉存档：全局键 plan.queue、plan.route 与 plan.sleep_save
==============================================================================
plan.queue 是 {角色id的字符串: [[种类, 意图], ...]}，队首在前（gameplay_resolution.plan_queue 读写）。
plan.route 在玩家寻路途中为 [目标场景, 这一段的出发场景, 跟着走的干员id, 是否仍打开地图面板]，不在寻路时为 null。
plan.sleep_save 为 True 时玩家睡觉了，行动收尾时要自动存档。
没有某一项时队列为空，路线为 None，标记为 False。读交回可以改的新值（场景是列表）。写入整值替换一个键，值没变时不写。
"""

from collections.abc import Mapping, Sequence
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import pickled

QUEUE = "plan.queue"
""" 排着的行动的全局键 """
ROUTE = "plan.route"
""" 玩家寻路的全局键 """
SLEEP_SAVE = "plan.sleep_save"
""" 睡觉存档标记的全局键 """

working.register(QUEUE, {})
working.register(ROUTE, None)
working.register(SLEEP_SAVE, False)


def _thawed(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thawed(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_thawed(item) for item in value]
    return value


def _queues(game: core.GameState | None = None) -> Mapping[str, core.JSON]:
    return cast(Mapping[str, core.JSON], working.get(None, QUEUE, game))


def queue(who: int, game: core.GameState | None = None) -> list[Any]:
    """
    角色排着的行动，队首在前
    Keyword arguments:
    who -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    list -- [种类, 意图] 的新列表，没有时为空列表
    """
    return cast(list[Any], _thawed(_queues(game).get(str(who), [])))


def set_queue(who: int, items: Sequence[Any]) -> None:
    """
    换掉角色的队列，空队列时删掉这个角色，写进当前缓冲区
    Keyword arguments:
    who -- 角色id
    items -- [种类, 意图] 的序列，队首在前
    """
    old = cast(dict[str, Any], _thawed(_queues()))
    new = {**old, str(who): _thawed(items)}
    if not items:
        del new[str(who)]
    if old != new:
        working.put(None, QUEUE, new)


def queues() -> dict[int, list[Any]]:
    """全部角色的计划队列，角色id 为 int，队首在前"""
    return {
        int(who): cast(list[Any], _thawed(items))
        for who, items in _queues().items()
    }


def clear_queues() -> None:
    """清空全部角色的计划队列，写进当前缓冲区"""
    if _queues():
        working.put(None, QUEUE, {})


def route() -> list[Any] | None:
    """
    玩家寻路途中的路线，不在寻路时为 None
    Return arguments:
    list | None -- [目标场景, 这一段的出发场景, 跟着走的干员id, 是否仍打开地图面板] 的新列表
    """
    return cast(list[Any] | None, _thawed(working.get(None, ROUTE)))


def set_route(value: Sequence[Any] | None) -> None:
    """
    换掉玩家的路线，写进当前缓冲区
    Keyword arguments:
    value -- 路线，None 为不在寻路
    """
    new = _thawed(value)
    if route() != new:
        working.put(None, ROUTE, new)


def sleep_save() -> bool:
    """玩家睡觉了、行动收尾时要自动存档时为 True"""
    return cast(bool, working.get(None, SLEEP_SAVE))


def set_sleep_save(on: bool) -> None:
    """
    设下或清掉睡觉存档标记，写进当前缓冲区
    Keyword arguments:
    on -- 设下为 True
    """
    if sleep_save() != on:
        working.put(None, SLEEP_SAVE, on)


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从存档缓存里删掉计划队列、玩家路线与睡觉存档标记，写进当前缓冲区
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 补上或换掉的项数，计法同 save_handle.update_dict_with_default
    """
    default: dict[str, Any] = {
        "plan_queue": {},
        "player_route": None,
        "pl_sleep_save_flag": False,
    }
    found, count = pickled.take(loaded_dict, default, version)
    if not found:
        return 0
    clear_queues()
    for who, items in found["plan_queue"].items():
        set_queue(who, items)
    set_route(found["player_route"])
    set_sleep_save(found["pl_sleep_save_flag"])
    return count
