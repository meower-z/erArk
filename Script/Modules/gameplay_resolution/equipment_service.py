"""
装备维护服务（equipment_service）
=================================
提供装备状态数值到名称的区间映射，以及外勤委托结束时的装备损坏结算。
不直接导入界面模块，供装备维护面板与外勤委托结算调用。
"""

import random
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import commission, identity, wardrobe

_: FunctionType = get_text._
""" 翻译api """


def get_equipment_condition_name(value: float) -> str:
    """
    按装备状态数值查找对应的状态名称。
    将 config_equipment_condition 各条目按 value 升序排列，返回最后一个 value 不大于输入值的条目名称。
    输入值低于最低条目时，返回最低条目的名称。
    Keyword arguments:
    value -- float，装备状态数值
    Return arguments:
    str -- 匹配到的装备状态名称
    """
    condition_list = list(game_config.config_equipment_condition.values())
    condition_list.sort(key=lambda x: x.value)
    result_name = condition_list[0].name
    for cond in condition_list:
        if value >= cond.value:
            result_name = cond.name
        else:
            break
    return result_name


def settle_equipment_damage_in_commission(commision_id: int) -> str:
    """
    结算指定外勤委托中派遣队伍的装备损坏情况。
    按委托等级读取 config_equipment_damage_rate 的 rate_0 至 rate_4 五档概率，为每名成员抽取随机数。
    取累计概率首次超过随机数的档位作为损坏等级，未超过时为 0。
    损坏等级大于 0 时，将该成员的 equipment_condition 设为损坏等级的相反数并追加提示行。
    Keyword arguments:
    commision_id -- int，外勤委托编号
    Return arguments:
    str -- 拼接后的装备损坏提示文本，无人损坏时返回空字符串
    """
    equipment_damage_text = ""
    send_npc_list = commission.ongoing()[commision_id].team
    commision_lv = game_config.config_commission[commision_id].level
    damage_rate_data = game_config.config_equipment_damage_rate[commision_lv]
    damage_rate_list = [
        damage_rate_data.rate_0,
        damage_rate_data.rate_1,
        damage_rate_data.rate_2,
        damage_rate_data.rate_3,
        damage_rate_data.rate_4,
    ]
    for send_npc_id in send_npc_list:
        send_npc_data = identity.of(send_npc_id)
        random_damage_rate = random.random()
        damage_lv = 0
        count_damage_rate: float = 0
        for i, rate in enumerate(damage_rate_list):
            count_damage_rate += rate
            if random_damage_rate < count_damage_rate:
                damage_lv = i
                break
        if damage_lv > 0:
            wardrobe.set(send_npc_id, "equipment_condition", damage_lv * -1)
            equipment_condition = get_equipment_condition_name(
                wardrobe.of(send_npc_id).equipment_condition
            )
            equipment_damage_text += _(
                "{0}的装备损坏了，损坏情况为{1}，需要进行维修。\n"
            ).format(send_npc_data.name, equipment_condition)

    return equipment_damage_text
