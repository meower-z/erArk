"""
save_load 的存档升级
====================
文件 "2" 的版本：CURRENT 是本游戏写的版本，STEPS[n] 把版本 n 的 JSON 对象升到 n + 1。
版本 0 是旧存档，它的生理需求与供电策略还在文件 "1" 的缓存对象上，所以 0 升 1 不是 JSON 步骤。
这一升级是读档的 install_save 里的三步：解开缓存后 fill_v0_defaults，角色替换时 copy_v0_needs，重建角色后 adopt_v0。
读旧存档不改写存档的文件。读完再存，写的是当前版本。本模块不登记行动、事件或规则，也不在 LOAD_ORDER 里。
"""

from collections.abc import Callable
from typing import Any

from Script.Core import num
from Script.Modules.domains import needs, power
from Script.Modules.gameplay_resolution import working

CURRENT = 1
""" 本游戏写的文件 "2" 的版本 """
STEPS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}
""" 版本 n 到 n + 1 的升级步骤，现在没有 """

V0_NEEDS = {
    "tired_point": "tired",
    "hunger_point": "hunger",
    "urinate_point": "urine",
}
""" 旧存档角色对象上的生理需求属性名到 body.needs 的项 """
V0_MILK = "milk"
""" 旧存档里乳汁在角色妊娠数据（pregnancy）上的属性名 """
V0_STRATEGY = "power_supply_strategy"
""" 旧存档里供电策略在罗德岛对象上的属性名 """


def fill_v0_defaults(loaded_dict: dict[str, Any]) -> None:
    """
    旧存档解开后补齐属性：缺生理需求属性的角色补上旧构造函数给的 0，缺供电策略的罗德岛补上空表
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    for character in loaded_dict.get("character_data", {}).values():
        for name in V0_NEEDS:
            if not hasattr(character, name):
                setattr(character, name, 0)
        pregnancy = getattr(character, "pregnancy", None)
        if pregnancy is not None and not hasattr(pregnancy, V0_MILK):
            setattr(pregnancy, V0_MILK, 0)
    island = loaded_dict.get("rhodes_island")
    if island is not None and not hasattr(island, V0_STRATEGY):
        setattr(island, V0_STRATEGY, {})


def copy_v0_needs(old: object, new: object) -> bool:
    """
    角色替换时，把旧存档角色对象上的疲劳、饥饿、尿意属性抄到新角色对象上
    Keyword arguments:
    old -- 旧角色
    new -- 新角色
    Return arguments:
    bool -- 旧角色带着这些属性（旧存档）时为 True，否则什么也不抄，为 False
    """
    if not hasattr(old, "tired_point"):
        return False
    for name in V0_NEEDS:
        setattr(new, name, getattr(old, name))
    return True


def adopt_v0(loaded_dict: dict[str, Any]) -> None:
    """
    旧存档重建角色之后，把角色对象上的四项生理需求（换成精确值）与罗德岛的供电策略表（区块id换成字符串）
    写进当前缓冲区，再删掉对象上的这些属性。重建后的妊娠数据没有乳汁属性时，乳汁读 0
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    for cid, character in loaded_dict["character_data"].items():
        if not hasattr(character, "tired_point"):
            continue
        values = {
            stat: num.exact(getattr(character, name))
            for name, stat in V0_NEEDS.items()
        }
        values["milk"] = num.exact(getattr(character.pregnancy, V0_MILK, 0))
        needs.set(cid, **values)
        for name in V0_NEEDS:
            delattr(character, name)
        if hasattr(character.pregnancy, V0_MILK):
            delattr(character.pregnancy, V0_MILK)
    island = loaded_dict["rhodes_island"]
    strategy = getattr(island, V0_STRATEGY)
    table = {str(zone): value for zone, value in strategy.items()}
    working.put(None, power.KEY, table)
    delattr(island, V0_STRATEGY)
