"""
角色的妊娠数据：角色的键 body.pregnancy
=======================================
值是 {"milk_max": 乳汁上限}。角色没有这一项时读默认值 DEFAULT（乳汁上限 200）。
这个键没有规则，写入整值替换它（working.put）。
"""

from collections.abc import Mapping
from typing import cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "body.pregnancy"
""" 妊娠数据在角色数据里的键 """
DEFAULT: Mapping[str, int] = {"milk_max": 200}
""" 角色没有 body.pregnancy 时读到的值 """

working.register(KEY, cast(core.JSON, DEFAULT))


def milk_max(cid: int, game: core.GameState | None = None) -> int:
    """
    角色的乳汁上限
    Keyword arguments:
    cid -- 角色id
    game -- 给出时只读这个状态，没有时读当前缓冲区，含还没套用的写入
    Return arguments:
    int -- 乳汁上限
    """
    stored = cast(Mapping[str, int], working.get(str(cid), KEY, game))
    return stored["milk_max"]


def set_milk_max(cid: int, value: int) -> None:
    """
    把角色的乳汁上限换成 value：整值替换 body.pregnancy，写进当前缓冲区
    Keyword arguments:
    cid -- 角色id
    value -- 乳汁上限
    """
    current = cast(Mapping[str, int], working.get(str(cid), KEY))
    working.put(str(cid), KEY, {**current, "milk_max": value})
