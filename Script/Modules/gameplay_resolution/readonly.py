"""
工作集解码视图缓存
==================
本模块按 (who, key, decode) 缓存 working.get 读出的原始值与解码后的只读视图。
再次读取同一槽位时，若当前原始值与缓存里的原始值是同一对象（is），view 直接复用已解码视图。
working 存下的原始值不可变。
缓存项一直持有原始值引用，避免该对象在条目存活期间被回收。
因此同一对象标识必然对应相同的值。
缓存按最近使用顺序维护，条目数超过 LIMIT 时淘汰最久未用的一项。
decode 必须返回不可原地修改的视图对象。
"""

from collections.abc import Callable
from typing import cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

LIMIT = 4096
""" 视图缓存最多保留的槽位条目数 """

type Slot = tuple[str | None, str, Callable[[core.JSON], object]]
""" 视图缓存的槽位键：(角色键或 None, 键名, 解码函数) """

_views: dict[Slot, tuple[core.JSON, object]] = {}


def view[V](
    who: str | None,
    key: str,
    decode: Callable[[core.JSON], V],
    game: core.GameState | None = None,
) -> V:
    """
    读取并解码一项工作集数据，原始值对象未变时复用缓存中的只读视图
    Keyword arguments:
    who -- 角色键，None 表示全局数据
    key -- 工作集键名
    decode -- 把原始 JSON 值解码为不可变视图的函数
    game -- 给出时只读该 GameState，为 None 时读当前缓冲区
    Return arguments:
    V -- 解码后的只读视图对象
    """
    raw = working.get(who, key, game)
    slot: Slot = (who, key, decode)
    hit = _views.pop(slot, None)
    if hit is None or hit[0] is not raw:
        hit = (raw, decode(raw))
    _views[slot] = hit
    if len(_views) > LIMIT:
        del _views[next(iter(_views))]
    return cast(V, hit[1])
