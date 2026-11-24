"""
干员在编生命周期服务（roster_lifecycle_service）
================================================
提供助理归零、角色离线与角色上线三项在编状态转换逻辑。
本模块不导入任何界面模块，可供后端服务直接调用。
Script/Settle/default.py 中的 ASSISTANT_RESET、CHARA_OFF_LINE 与 CHARA_ON_LINE 结算效果委托本模块执行。
"""

import datetime

from Script.Config import game_config
from Script.Core import constant
from Script.Design import attr_calculation
from Script.Modules.domains import activity, dirty, flags, h_state, needs
from Script.Modules.domains import relations, roster, status
from Script.Modules.gameplay_resolution import plan_queue


def clear_assistant(character_id: int) -> None:
    """
    将角色的助理服务数据清零；若该角色为玩家当前助理，则将玩家助理角色编号归零。
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    relations.assistant_services.set(
        character_id, attr_calculation.get_assistant_services_zero()
    )
    if relations.assistant_character_id(0) == character_id:
        relations.assistant_character_id.set(0, 0)


def chara_off_line(character_id: int) -> None:
    """
    使角色离线并归零离线相关状态：重置行动与事件数据，调用 clear_assistant 清零助理数据，
    调用 dirty.reset 与 h_state.reset 重置污浊和 H 状态，将配置类型为 0 的角色状态全部归零，
    清除 is_follow 跟随标记，若角色在当前在编名册中则移出，并将位置设为 ["0", "0"] 以离开地图。
    其余特殊状态标记（如 imprisonment、escaping）保持不变。
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    activity.set_behavior(character_id)
    activity.set_event(character_id)
    clear_assistant(character_id)
    dirty.reset(character_id)
    h_state.reset(character_id)
    for state_id in game_config.config_character_state:
        if game_config.config_character_state[state_id].type == 0:
            status.set(character_id, state_id, 0)
    flags.set(character_id, is_follow=0)
    if roster.has(character_id):
        roster.remove(character_id)
    activity.set_position(character_id, ["0", "0"])


def chara_on_line(character_id: int, now_time: datetime.datetime) -> None:
    """
    使角色上线并重置在编基础状态：将 hit、mana 设为各自上限，hunger、tired、urine、sleep 归零；
    重置全部特殊状态标记后始终恢复 in_diplomatic_visit，若重置前 imprisonment 为真则一并恢复。
    in_diplomatic_visit 需跨上线保留，否则外交官随罗德岛抵达驻在国回岛后会丢失驻在国信息。
    随后将交互目标设为自身，向当前行动合并空闲行为（SHARE_BLANKLY、自 now_time 起 0 分钟，
    与内核加入角色时赋予的空闲行为一致），保留移动目标等其余行动字段；
    状态设为 STATUS_ARDER，并经 plan_queue 排入打断，使已在内核中的角色打断当前行动；
    若角色尚未在当前在编名册中则加入。
    Keyword arguments:
    character_id -- 角色id
    now_time -- 当前游戏时间
    Return arguments:
    无
    """
    needs.set(character_id, hit=needs.of(character_id)["hit_max"])
    needs.set(character_id, mana=needs.of(character_id)["mana_max"])
    needs.set(character_id, hunger=0, tired=0, urine=0, sleep=0)
    old_imprisonment = flags.get(character_id, "imprisonment")
    old_in_diplomatic_visit = flags.get(character_id, "in_diplomatic_visit")
    flags.reset(character_id)
    flags.set(character_id, in_diplomatic_visit=old_in_diplomatic_visit)
    if old_imprisonment:
        flags.set(character_id, imprisonment=True)
    activity.set_target(character_id, character_id)
    activity.update_behavior(
        character_id,
        behavior_id=constant.Behavior.SHARE_BLANKLY,
        start_time=now_time,
        duration=0,
    )
    activity.set_state(character_id, constant.CharacterStatus.STATUS_ARDER)
    plan_queue.interrupt(character_id)
    if not roster.has(character_id):
        roster.add(character_id)
