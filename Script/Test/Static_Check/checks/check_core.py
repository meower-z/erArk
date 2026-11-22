# -*- coding: UTF-8 -*-
"""
静态检查系统 - 核心示例检查
提供两个最基础的角色索引一致性检查，用于验证静态检查框架自身管线可用，后续领域检查模块可参照本文件的写法接入。
"""

from Script.Modules.domains import roster
from ..check_registry import CheckFailure, register_check, make_failure
from Script.Modules.domains import activity
from Script.Modules.domains import identity


@register_check("CORE-01", "角色索引一致性")
def check_npc_id_got_consistency() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表，在编名单（roster.active()）中所有id均存在于身份表时返回空列表
    功能:
        校验在编名单（roster.active()）中的每个id都在角色身份表（identity.characters）中存在，
        避免出现"在编但无角色身份"的野指针状态
    """
    failures = []
    for character_id in roster.active():
        if not identity.exists(character_id):
            failures.append(
                make_failure(
                    "CORE-01",
                    "角色索引一致性",
                    f"npc_id_got中的角色id={character_id}在character_data中不存在",
                    [character_id],
                )
            )
    return failures


@register_check("CORE-02", "交互对象有效性")
def check_target_character_id_validity() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表，全部角色的交互对象均存在于身份表时返回空列表
    功能:
        校验角色身份表（identity.characters）中每个角色的交互对象id（activity.target）都存在于身份表中。
        自指（activity.target(cid) == cid）是"无交互对象"的约定值，角色初始化与上线重置都指向自身。
        activity.target(cid) == 0 对NPC而言表示交互对象是0号玩家，settle_behavior据此互换双方结算数据。
        本条统一按是否在身份表中判定，自指与指向玩家都自然通过，不对0值做特殊豁免
    """
    failures = []
    for character_id, character_data in identity.table().items():
        target_id = activity.target(character_data.cid)
        if not identity.exists(target_id):
            failures.append(
                make_failure(
                    "CORE-02",
                    "交互对象有效性",
                    f"角色id={character_id}的target_character_id={target_id}在character_data中不存在",
                    [character_id],
                )
            )
    return failures
