"""
基地的岗位名册：全局键 base.work 与 base.warden
==============================================
base.work 是 {岗位id的字符串: [角色id, ...]}，只有有人的岗位，岗位id按数值排序。
每个名单按刷新（basement.update_work_people）遍历在编干员（npc_id_got）时遇到的顺序排列。
base.warden 是监狱长的角色id，0 为没有。两个键都整值替换，新值与旧值相同时不写。
在岗人数与招聘专员名单由名册算出，不存。
"""

from collections.abc import Collection, Mapping
from typing import cast

from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "base.work"
""" 岗位名册在全局数据里的键 """
WARDEN = "base.warden"
""" 监狱长在全局数据里的键 """
HR_WORK = 71
""" 招聘专员的岗位id """

working.register(KEY, {})
working.register(WARDEN, 0)


def rosters(game: core.GameState | None = None) -> dict[int, tuple[int, ...]]:
    """
    全部有人的岗位名册
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 岗位id到按刷新顺序排列的角色id
    """
    stored = cast(Mapping[str, tuple[int, ...]], working.get(None, KEY, game))
    return {int(work_id): tuple(ids) for work_id, ids in stored.items()}


def roster(work_id: int, game: core.GameState | None = None) -> tuple[int, ...]:
    """
    一个岗位的名册
    Keyword arguments:
    work_id -- 岗位id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    tuple -- 按刷新顺序排列的角色id，没有人时为空
    """
    stored = cast(Mapping[str, tuple[int, ...]], working.get(None, KEY, game))
    return tuple(stored.get(str(work_id), ()))


def people_now(game: core.GameState | None = None) -> int:
    """
    在岗人数，即岗位 0（无岗位）以外各名册的人数之和
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 人数
    """
    return sum(len(ids) for work_id, ids in rosters(game).items() if work_id)


def set_rosters(new: Mapping[int, Collection[int]]) -> None:
    """
    整值替换岗位名册，写进当前缓冲区。没有人的岗位不记，新值与旧值相同时不写
    Keyword arguments:
    new -- 岗位id到角色id，名单保持给出的顺序
    """
    table = {
        str(work_id): tuple(new[work_id])
        for work_id in sorted(new)
        if new[work_id]
    }
    if working.get(None, KEY) != table:
        working.put(None, KEY, table)


def warden(game: core.GameState | None = None) -> int:
    """
    监狱长
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 角色id，0 为没有
    """
    return cast(int, working.get(None, WARDEN, game))


def set_warden(cid: int) -> None:
    """
    把监狱长设为 cid，写进当前缓冲区。与现在的相同时不写
    Keyword arguments:
    cid -- 角色id，0 为没有
    """
    if warden() != cid:
        working.put(None, WARDEN, cid)


def remap(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把名册与监狱长里的旧id换成新id。名单顺序不变，两个旧id换成同一个新id时只留前一个
    Keyword arguments:
    old_to_new -- 旧id到新id，表里没有的id不变
    """
    set_rosters(
        {
            work_id: dict.fromkeys(old_to_new.get(cid, cid) for cid in ids)
            for work_id, ids in rosters().items()
        }
    )
    if warden():
        set_warden(old_to_new.get(warden(), warden()))


def drop(cids: Collection[int]) -> int:
    """
    把 cids 里的角色从各岗位名册里去掉
    Keyword arguments:
    cids -- 角色id
    Return arguments:
    int -- 去掉的人次
    """
    current = rosters()
    kept = {
        work_id: [cid for cid in ids if cid not in cids]
        for work_id, ids in current.items()
    }
    set_rosters(kept)
    return sum(len(current[w]) - len(kept[w]) for w in current)
