# -*- coding: UTF-8 -*-
"""
快照里按角色对象的属性名记下 chara.flags、chara.action_info、player.ability 与 player.collection
==================================================================================================
供 tests/kernel_project.project_base_tallies 调用，使快照与迁入内核前录下的基准逐项比较。
"""


def project(state: dict[str, object]) -> None:
    """
    把 GameState 里全部角色的特殊标记、行动记录、玩家能力与收藏品按角色属性名写入快照
    Keyword arguments:
    state -- 快照字典，原地补上
    """
    from Script.Core import cache_control
    from Script.Modules.domains import (
        action_info,
        flags,
        player_ability,
        player_collection,
    )
    from tests.snapshot import flatten

    for cid in cache_control.cache.character_data:
        flatten(f"chara.{cid}.sp_flag", flags.snapshot(cid), state)
        flatten(f"chara.{cid}.action_info", action_info.snapshot(cid), state)
        flatten(f"chara.{cid}.pl_ability", player_ability.snapshot(cid), state)
        flatten(
            f"chara.{cid}.pl_collection",
            player_collection.snapshot(cid),
            state,
        )
