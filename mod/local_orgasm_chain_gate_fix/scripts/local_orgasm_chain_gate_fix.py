# -*- coding: UTF-8 -*-
"""
本地绝顶链式门禁修复。

NPC 在一次玩家点击的结算中发生多重绝顶（>=2 个部位同时越过绝顶阈值）后，
仍可能在同一次点击内被立即重新调度、再次主动行动并再次绝顶，堆叠出大量口上。
本 mod 让已发生多重绝顶的 NPC 在本次点击剩余结算中不再生成新的自主行为，
但保留其群交参与关系并照常完成被动结算；下一次玩家点击开始时解除限制。

对应上游 PR #226（已被上游拒绝，改由本地 mod 承接）。使用与内联实现等价的行为，
但通过 wrapper 而非整函数复制实现，避免随上游函数体漂移。

标记读写一律走 getattr/直接赋值，不依赖 SPECIAL_FLAG 预声明该字段，
因此在剥离了内联代码的纯上游函数体上同样成立。
"""

HN_AI = "Script.Design.handle_npc_ai"
HN_AI_H = "Script.Design.handle_npc_ai_in_h"
SECOND_BEHAVIOR = "Script.Design.second_behavior"
UPDATE = "Script.Design.update"

# 角色临时结算标记名：本次玩家行动（一次点击）内已发生多重绝顶
FLAG_NAME = "multi_orgasm_this_player_action"


def _cache():
    """参数：无；返回：Cache对象；用途：获取当前游戏缓存。"""
    from Script.Core import cache_control

    return cache_control.cache


def _is_gated(character_data) -> bool:
    """参数：character_data(Character)为角色数据；返回：bool为本次点击是否已被门禁；用途：读取多重绝顶标记，缺省视为未门禁。"""
    return bool(getattr(character_data.sp_flag, FLAG_NAME, False))


def patched_find_character_target(character_id: int, now_time):
    """参数：character_id(int)为角色ID，now_time(datetime)为当前时间；返回：原函数返回值或None；用途：本次行动内已多重绝顶的NPC不再生成新自主行为，直接加入结束列表，由character_behavior()继续走被动结算尾部。"""
    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    if _is_gated(character_data):
        cache_obj.over_behavior_character.add(character_id)
        return
    return call_original(HN_AI, "find_character_target", character_id, now_time)


def patched_npc_ai_in_group_sex(character_id: int):
    """参数：character_id(int)为角色ID；返回：原函数返回值或None；用途：已多重绝顶的NPC不再写入自慰意图或群交模板占位，保留现有群交参与关系，随后同一角色仍会到普通入口完成被动结算尾部。"""
    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    if _is_gated(character_data):
        return
    return call_original(HN_AI_H, "npc_ai_in_group_sex", character_id)


def patched_character_get_second_behavior(character_id: int, second_behavior_id: str, reset: bool = False):
    """参数：character_id(int)为角色ID，second_behavior_id(str)为二段行为ID，reset(bool)为是否重置；返回：原函数返回值；用途：多重绝顶(plural_orgasm_*)释放后标记该NPC本次行动内已多重绝顶。"""
    result = call_original(SECOND_BEHAVIOR, "character_get_second_behavior", character_id, second_behavior_id, reset)
    # plural_orgasm_N 只在真实多重绝顶(part_count>=2)的释放路径触发（second_behavior.py orgasm_settle 内唯一调用点）；
    # 时停蓄积与成功寸止都在循环内提前 continue、part_count 保持 0，不会走到该调用，故不会误置位。
    # 玩家 character_id 为 0，被 `if character_id` 排除，不受该规则影响。
    if character_id and isinstance(second_behavior_id, str) and second_behavior_id.startswith("plural_orgasm_"):
        setattr(_cache().character_data[character_id].sp_flag, FLAG_NAME, True)
    return result


def patched_game_update_flow(add_time: int):
    """参数：add_time(int)为游戏步进时间；返回：None；用途：最外层玩家点击开始时重置全体NPC的多重绝顶标记；嵌套更新复用同一标记不重置。"""
    cache_obj = _cache()
    # 读取原函数进入前的深度：0 表示这是最外层点击。原函数随后自增深度并在 finally 恢复。
    if cache_obj.game_update_flow_running == 0:
        for npc_id in cache_obj.npc_id_got:
            npc_data = cache_obj.character_data.get(npc_id)
            if npc_data is not None:
                setattr(npc_data.sp_flag, FLAG_NAME, False)
    return call_original(UPDATE, "game_update_flow", add_time)
