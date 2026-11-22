"""
角色的身体管理：角色键 body.manage
==================================
值是 {身体管理要求id的字符串: 值}，值为 0 时不要求。角色没有这一项时读空表。
新角色由 character.init_attr 写下 Body_Manage_Requirement.csv 里的每一项，值为 0。
写入整值替换这个键。键、顺序、值与值的类型都没变时不写。
"""

from collections.abc import Collection, Mapping
from typing import Any, cast

from Script.Kernel import core
from Script.Modules.domains import counts
from Script.Modules.gameplay_resolution import working

KEY = "body.manage"
""" 身体管理在角色数据里的键 """
PICKLED = "body_manage"
""" 版本 19 之前的存档里，角色对象上身体管理的属性名 """

working.register(KEY, {})


def of(cid: int, game: core.GameState | None = None) -> counts.Table[int]:
    """
    角色的身体管理
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    counts.Table -- 要求id到值的只读表
    """
    return counts.Table(
        cast(Mapping[str, int], working.get(str(cid), KEY, game))
    )


def replace(cid: int, table: Mapping[int, int]) -> None:
    """
    把角色的身体管理整个换成 table，写进当前缓冲区。键、顺序、值与值的类型都没变时不写
    Keyword arguments:
    cid -- 角色id
    table -- 要求id到值
    """
    new = counts.stored(table)
    old = cast(Mapping[str, int], working.get(str(cid), KEY))
    if not working.same(old, new):
        working.put(str(cid), KEY, cast(core.JSON, new))


def set(cid: int, manage_id: int, value: int) -> None:
    """
    把一项身体管理换成 value，写进当前缓冲区。没有这一项时加在最后
    Keyword arguments:
    cid -- 角色id
    manage_id -- 要求id
    value -- 新值
    """
    table = dict(of(cid))
    table[manage_id] = value
    replace(cid, table)


def clear(cid: int, ids: Collection[int]) -> None:
    """
    把 ids 里值不为 0 的各项换成 0，写进当前缓冲区。别的项不变，表里没有的 id 不加
    Keyword arguments:
    cid -- 角色id
    ids -- 要求id
    """
    table = {k: 0 if k in ids and v else v for k, v in of(cid).items()}
    replace(cid, table)


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时调用。存档里的角色对象带着 PICKLED 属性时（版本 19 之前的存档），从对象上删掉它。不空的表写进当前缓冲区
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    for cid, table in counts.taken(loaded_dict, PICKLED):
        if table:
            replace(cid, table)
