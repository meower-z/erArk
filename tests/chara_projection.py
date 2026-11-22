# -*- coding: UTF-8 -*-
"""
角色内核状态快照投影
====================
供 tests/kernel_project.project_base_tallies 调用，把每个角色在 GameState 里的
chara.flags、chara.action_info、player.ability、player.collection、h.meters、
h.state、body.dirty、mind.hypnosis、history.first_record 与
history.first_record_history 按旧 Character 属性名展开进快照，使快照与迁入内核前录下的基准逐项比较。
"""

from __future__ import annotations

from collections.abc import Mapping


def project(state: dict[str, object]) -> None:
    """
    把 GameState 里全部角色的标记、行动记录、玩家能力/收藏品与 H/污浊/催眠/初次记录按角色属性名写入快照
    Keyword arguments:
    state -- 快照字典，原地补上
    """
    from Script.Core import cache_control
    from Script.Modules.domains import action_info, dirty, first_record, flags
    from Script.Modules.domains import h_meters, h_state, hypnosis
    from Script.Modules.domains import player_ability, player_collection
    from tests.snapshot import flatten

    for cid in sorted(cache_control.cache.character_data):
        prefix = f"chara.{cid}"
        flatten(f"{prefix}.sp_flag", flags.snapshot(cid), state)
        flatten(f"{prefix}.action_info", action_info.snapshot(cid), state)
        flatten(f"{prefix}.pl_ability", player_ability.snapshot(cid), state)
        flatten(
            f"{prefix}.pl_collection",
            player_collection.snapshot(cid),
            state,
        )
        meters: Mapping[str, object] = h_meters.of(cid)
        for old_name, stat in h_meters.OLD_CHARA_FIELDS.items():
            flatten(f"{prefix}.{old_name}", meters[stat], state)
        flatten(f"{prefix}.h_state", h_state.view(cid), state)
        flatten(f"{prefix}.dirty", dirty.view(cid), state)
        flatten(f"{prefix}.hypnosis", hypnosis.view(cid), state)
        flatten(f"{prefix}.first_record", first_record.view(cid), state)
        flatten(
            f"{prefix}.first_record_history",
            first_record.history(cid),
            state,
        )
