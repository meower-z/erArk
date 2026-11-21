"""
宿舍管理员的全局键 base.dormitory_managers
==========================================
值是 {层号的字符串: 管理员的角色id}，0 为未任命。没有这个键时读 DEFAULT：1~9 层都未任命。
写入整值替换这个键。新值与旧值相同时不写。
"""

from collections.abc import Mapping
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "base.dormitory_managers"
""" 各层宿舍管理员在全局数据里的键 """
DEFAULT: Mapping[str, int] = {str(layer): 0 for layer in range(1, 10)}
""" 没有 base.dormitory_managers 时读到的值 """

working.register(KEY, cast(core.JSON, DEFAULT))


def managers(game: core.GameState | None = None) -> dict[int, int]:
    """
    各层的管理员。返回新建的 dict
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 层号到角色id（0 为未任命），按存下的顺序
    """
    stored = cast(Mapping[str, int], working.get(None, KEY, game))
    return {int(layer): cid for layer, cid in stored.items()}


def set_manager(layer: int, chara_id: int) -> None:
    """
    换一层的管理员。表里没有这一层时加在最后
    Keyword arguments:
    layer -- 层号
    chara_id -- 角色id，0 为撤下
    """
    current = managers()
    current[layer] = chara_id
    stored = {str(k): v for k, v in current.items()}
    if stored != working.get(None, KEY):
        working.put(None, KEY, stored)


PICKLED = "dormitory_managers"
""" 版本 11 之前的存档里，罗德岛对象上 {层号: 角色id} 的属性名 """


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED，是 dict 时整表写进当前缓冲区
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 版本 11 之前的存档里缺了或类型不符时为 1，否则为 0，计法同 save_handle.update_dict_with_default
    """
    raw = vars(loaded_dict["rhodes_island"]).pop(PICKLED, None)
    if type(raw) is not dict:
        return 1 if version < 11 else 0
    stored = {str(layer): cid for layer, cid in raw.items()}
    if stored != working.get(None, KEY):
        working.put(None, KEY, stored)
    return 0
