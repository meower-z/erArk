"""
H 服装面板绘制时判定的内衣可见性
================================
场景面板在写缓冲区之外绘制，H 服装面板绘制时不写 GameState，只用 remember
暂存交互对象与本次判定的内衣可见性。keep 在当前写缓冲区里把暂存值写入该角色的
cloth_see 并清空记录；交互对象已换或双方都不在 H 中时，只清空记录。
选择草稿开启时（player_pick.drafting）先调 keep，使草稿后续写入（行动开始时重放）
建立在它之上；点服装按钮在草稿末尾重绘后再调一次 keep。
之后第一个行动开始或结束时，kernel.StartAction 输入钩子在开始函数前调用 keep，
kernel.EndAction 输入钩子在结束结算前调用 keep。
kernel.Reset 换入整个 GameState 时丢弃记录。
"""

from collections.abc import Mapping

from Script.Core import cache_control, game_type
from Script.Kernel import core
from Script.Modules.domains import activity, flags, wardrobe

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

_drawn: tuple[int, dict[int, bool]] | None = None
""" 上次绘制记下的 (交互对象 id, {部位: 是否可见})，无记录时为 None """


def remember(cid: int, seen: Mapping[int, bool]) -> None:
    """
    暂存本次绘制判定的内衣可见性，覆盖上一次记录
    Keyword arguments:
    cid -- 交互对象的角色 id
    seen -- 各部位是否可见的映射 {部位: 是否可见}
    """
    global _drawn
    _drawn = (cid, dict(seen))


def keep() -> None:
    """
    在当前写缓冲区内把暂存的可见性写入该角色的 cloth_see，并清空记录。
    无记录时直接返回；交互对象已换或双方都不在 H 中时，只清空不写入
    """
    global _drawn
    if _drawn is None:
        return
    cid, seen = _drawn
    _drawn = None
    if cid != activity.target(0):
        return
    if not (flags.get(0, "is_h") or flags.get(cid, "is_h")):
        return
    see = wardrobe.of(cid).cloth_see
    see.update(seen)
    wardrobe.set(cid, "cloth_see", see)


@core.input_hook(core.start_action)
def keep_on_start(act: core.Action) -> tuple[core.Action]:
    """
    kernel.StartAction 输入钩子：行动开始函数运行前将暂存的可见性写入 cloth_see
    Keyword arguments:
    act -- 即将开始的行动
    Return arguments:
    tuple -- 原样交给内层的行动元组 (act,)
    """
    keep()
    return (act,)


@core.input_hook(core.end_action)
def keep_on_end(act: core.Action) -> tuple[core.Action]:
    """
    kernel.EndAction 输入钩子：行动结束结算前将暂存的可见性写入 cloth_see
    Keyword arguments:
    act -- 即将结束的行动
    Return arguments:
    tuple -- 原样交给内层的行动元组 (act,)
    """
    keep()
    return (act,)


@core.output_hook(core.reset)
def forget_on_reset(game: core.GameState) -> core.GameState:
    """
    kernel.Reset 输出钩子：读档、新游戏或新周目换入新 GameState 后清空记录
    Keyword arguments:
    game -- 换入的新 GameState
    Return arguments:
    GameState -- 原样返回的 GameState
    """
    global _drawn
    _drawn = None
    return game
