# -*- coding: UTF-8 -*-
"""
绝顶链式门禁

NPC 在一次玩家点击的结算中发生多重绝顶（>=2 个部位同时越过绝顶阈值）后，
仍可能在同一次点击内被立即重新调度、再次主动行动并再次绝顶，堆叠出大量口上。
本 mod 让已发生多重绝顶的 NPC 在本次点击剩余结算中不再生成新的自主行为，
但保留其群交参与关系并照常完成被动结算；下一次玩家点击开始时解除限制。

全部是 call_original 薄包装，不复制本体函数体：
- character_get_second_behavior：NPC 得到 plural_orgasm_* 时记入门禁名单
- game_update_flow：最外层玩家点击开始时清空门禁名单
- find_character_target / npc_ai_in_group_sex：门禁中的 NPC 不再生成新行为
门禁名单只放在本模块里，不写进角色数据，因此不会进存档。
对应上游已拒绝的 PR #226。
"""
from typing import Set

from Script.Core import cache_control

HN_AI = "Script.Design.handle_npc_ai"
HN_AI_H = "Script.Design.handle_npc_ai_in_h"
SECOND_BEHAVIOR = "Script.Design.second_behavior"
UPDATE = "Script.Design.update"

_gated_ids: Set[int] = set()
""" 本次玩家点击内已发生多重绝顶的 NPC id """


def patched_find_character_target(character_id: int, now_time):
    """
    门禁中的 NPC 不再生成新自主行为，直接加入结束列表，由 character_behavior() 继续走被动结算尾部
    Keyword arguments:
    character_id -- 角色id
    now_time -- 当前时间
    Return arguments:
    本体函数的返回值；门禁时为 None
    """
    if character_id in _gated_ids:
        cache_control.cache.over_behavior_character.add(character_id)
        return None
    return call_original(HN_AI, "find_character_target", character_id, now_time)


def patched_npc_ai_in_group_sex(character_id: int):
    """
    门禁中的 NPC 不再写入自慰意图或群交模板占位，保留现有群交参与关系；随后同一角色仍会到普通入口完成被动结算尾部
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    本体函数的返回值；门禁时为 None
    """
    if character_id in _gated_ids:
        return None
    return call_original(HN_AI_H, "npc_ai_in_group_sex", character_id)


def patched_character_get_second_behavior(character_id: int, second_behavior_id: str, reset: bool = False):
    """
    NPC 得到多重绝顶(plural_orgasm_*)二段行为时记入门禁名单
    plural_orgasm_N 只在真实多重绝顶(part_count>=2)的释放路径触发；时停蓄积与成功寸止都会提前跳过，不会误记。玩家(0)不记。
    Keyword arguments:
    character_id -- 角色id
    second_behavior_id -- 二段行为id
    reset -- 是否重置
    Return arguments:
    本体函数的返回值
    """
    result = call_original(SECOND_BEHAVIOR, "character_get_second_behavior", character_id, second_behavior_id, reset)
    if character_id and second_behavior_id.startswith("plural_orgasm_"):
        _gated_ids.add(character_id)
    return result


def patched_game_update_flow(add_time: int):
    """
    最外层玩家点击开始时清空门禁名单；嵌套更新沿用同一名单
    Keyword arguments:
    add_time -- 游戏步进时间
    Return arguments:
    本体函数的返回值
    """
    # 进入本体前读深度：0 表示最外层点击（本体随后自增深度并在 finally 恢复）
    if cache_control.cache.game_update_flow_running == 0:
        _gated_ids.clear()
    return call_original(UPDATE, "game_update_flow", add_time)
