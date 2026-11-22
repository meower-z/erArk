"""
群交部位模板（h.state 里的 group_sex_body_template_dict）辅助操作
================================================================
在角色替换重映射、移出成员与检查成员是否在模板中时读写 h.state 的群交模板字段。
"""

from collections.abc import Callable, Collection, Mapping
from contextlib import AbstractContextManager
from typing import Any, cast

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working


def _valid_tpl(tpl: Any) -> bool:
    return (
        isinstance(tpl, (list, tuple))
        and len(tpl) >= 2
        and isinstance(tpl[0], Mapping)
    )


def _valid_serve(tpl: Any) -> bool:
    return (
        isinstance(tpl[1], (list, tuple))
        and len(tpl[1]) >= 2
        and isinstance(tpl[1][0], (list, tuple))
    )


def remap_group_sex_ids(
    key: str,
    editing_fn: Callable[[int], AbstractContextManager[game_type.BODY_H_STATE]],
    cid: int,
    id_map: Mapping[int, int],
) -> None:
    """重映射角色群交部位模板里引用的角色id"""
    if "group_sex_body_template_dict" not in cast(
        Mapping[str, Any], working.get(str(cid), key)
    ):
        return
    with editing_fn(cid) as hs:
        for tpl in hs.group_sex_body_template_dict.values():
            if not _valid_tpl(tpl):
                continue
            for pk, pv in tpl[0].items():
                if isinstance(pv, list) and pv and pv[0] != -1:
                    tpl[0][pk] = [id_map.get(pv[0], pv[0]), *pv[1:]]
            if _valid_serve(tpl):
                tpl[1][0] = [
                    id_map.get(o, o) if o != -1 else o for o in tpl[1][0]
                ]


def remove_from_group_sex_template(
    key: str,
    editing_fn: Callable[[int], AbstractContextManager[game_type.BODY_H_STATE]],
    cid: int,
    drop_ids: Collection[int],
) -> int:
    """从角色群交部位模板中移除指定角色id集合，返回改动的项数"""
    if not drop_ids or "group_sex_body_template_dict" not in cast(
        Mapping[str, Any], working.get(str(cid), key)
    ):
        return 0
    drop_set, count = set(drop_ids), 0
    with editing_fn(cid) as hs:
        for tpl in hs.group_sex_body_template_dict.values():
            if not _valid_tpl(tpl):
                continue
            for pk, pv in tpl[0].items():
                if isinstance(pv, list) and pv and pv[0] in drop_set:
                    tpl[0][pk] = [-1, -1]
                    count += 1
            if _valid_serve(tpl):
                kept = [x for x in tpl[1][0] if x not in drop_set]
                if len(kept) != len(tpl[1][0]):
                    tpl[1] = [kept, tpl[1][1]] if kept else [[-1], -1]
                    count += 1
    return count


def group_sex_template_has(
    key: str,
    cid: int,
    id_set: Collection[int],
    game: core.GameState | None = None,
) -> bool:
    """检查角色群交部位模板里是否包含 id_set 中任一角色id"""
    tpl_dict = cast(Mapping[str, Any], working.get(str(cid), key, game)).get(
        "group_sex_body_template_dict"
    )
    if not isinstance(tpl_dict, Mapping) or not id_set:
        return False
    ids = set(id_set)
    for tpl in tpl_dict.values():
        if not _valid_tpl(tpl):
            continue
        if any(
            isinstance(pv, (list, tuple)) and pv and pv[0] in ids
            for pv in tpl[0].values()
        ):
            return True
        if _valid_serve(tpl) and any(x in ids for x in tpl[1][0]):
            return True
    return False
