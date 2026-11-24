"""
装备维护服务（equipment_service）
=================================
提供装备状态名称映射、外勤委托装备损坏结算以及铁匠的装备维修、保养与维护流程。
本模块不导入 Script.UI 下的模块，供装备维护面板、外勤委托结算与维护装备行为结算调用。
"""

import random
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import basement, handle_ability, handle_premise
from Script.Modules.domains import abilities, achievement, commission
from Script.Modules.domains import identity, maintenance, roster, wardrobe
from Script.Modules.gameplay_resolution import achievement_service, ui_hooks

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


def smith_maintain_equipment_once(
    smith_chara_id: int, draw_flag: bool = True
) -> bool:
    """
    为指定铁匠执行一次装备维护流程。
    铁匠在 maintenance.repairs() 中有记录目标时，目标装备状态小于 0 则执行维修，否则执行保养。
    随后按 maintenance.settings() 第 3 项确定优先项，默认 0 为优先维修。
    优先项尚未执行时自动执行该项，两项均未执行时再自动执行另一项。
    draw_flag 为真时，将非空的维修结果行与保养结果行依次拼接后经 ui_hooks.emit_notice 发出。
    draw_flag 为真且两者皆空时，经 ui_hooks.emit_notice 发出无可维护提示。
    Keyword arguments:
    smith_chara_id -- int，执行维护的铁匠角色编号
    draw_flag -- bool，为真时经 ui_hooks.emit_notice 发出结果提示，默认为 True
    Return arguments:
    bool -- 本次是否执行了维修或保养
    """
    repair_equipment_first = maintenance.settings().get(3, 0) == 0

    repair_flag, maintain_flag = False, False
    repair_text, maintain_text = "", ""
    target_id = 0
    repairing = maintenance.repairs()
    if smith_chara_id in repairing:
        target_id = repairing[smith_chara_id]
        npc_data = identity.of(target_id)
        if wardrobe.of(npc_data.cid).equipment_condition >= 0:
            maintain_flag, maintain_text = maintain_equipment(
                smith_chara_id, target_id
            )
        else:
            repair_flag, repair_text = repair_equipment(
                smith_chara_id, target_id
            )

    if repair_equipment_first:
        if not repair_flag:
            repair_flag, repair_text = repair_equipment(smith_chara_id)
        if not repair_flag and not maintain_flag:
            maintain_flag, maintain_text = maintain_equipment(smith_chara_id)
    else:
        if not maintain_flag:
            maintain_flag, maintain_text = maintain_equipment(smith_chara_id)
        if not maintain_flag and not repair_flag:
            repair_flag, repair_text = repair_equipment(smith_chara_id)

    if draw_flag:
        text = ""
        if repair_text:
            text += repair_text + "\n"
        if maintain_text:
            text += maintain_text + "\n"
        if not repair_text and not maintain_text:
            text = _("没有可维修或可保养的装备。")
        ui_hooks.emit_notice(text)
    return repair_flag or maintain_flag


def repair_equipment(
    smith_chara_id: int, target_chara_id: int = 0
) -> tuple[bool, str]:
    """
    为指定铁匠执行一次装备维修。
    维修量等于铁匠能力 48 修正值除以 2，再乘以 0.8 至 1.2 的随机系数与设施 2 效率。
    target_chara_id 为 0 时，从不含角色 0 的在队角色中筛选装备状态小于 0 者。
    筛选结果按 maintenance.settings() 第 0 项排序，默认 0 选最低，非 0 选最高。
    目标编号大于 0 时将装备状态加上维修量并封顶于 0，铁匠职业会写入维修记录。
    铁匠在维修记录中且新状态不小于 0 时，清除记录并将 equipment_repair_count 加 1。
    此时同时调用 achievement_service.settle_and_notify 结算维修成就。
    Keyword arguments:
    smith_chara_id -- int，执行维修的铁匠角色编号
    target_chara_id -- int，目标角色编号，为 0 时自动选择，默认为 0
    Return arguments:
    tuple[bool, str] -- 是否执行了维修与维修结果行，未执行时返回 (False, "")
    """
    smith_chara_data = identity.of(smith_chara_id)
    ability_lv = abilities.ability(smith_chara_id)[48]
    maintain_value = handle_ability.get_ability_adjust(ability_lv) / 2
    maintain_value *= random.uniform(0.8, 1.2)
    maintain_value *= basement.calc_facility_efficiency(2)
    maintain_priority = maintenance.settings().get(0, 0)

    repair_flag = False
    repair_text = ""

    if target_chara_id == 0:
        repair_list = []
        for npc_id in roster.active():
            if npc_id == 0:
                continue
            npc_data = identity.of(npc_id)
            cond = wardrobe.of(npc_data.cid).equipment_condition
            if cond < 0:
                repair_list.append((npc_id, cond))
        if repair_list:
            if maintain_priority == 0:
                repair_list.sort(key=lambda x: x[1], reverse=False)
            else:
                repair_list.sort(key=lambda x: x[1], reverse=True)
            target_chara_id, cond = repair_list[0]
    if target_chara_id > 0:
        npc_data = identity.of(target_chara_id)
        if handle_premise.handle_work_is_blacksmith(smith_chara_id):
            maintenance.set_repair(smith_chara_id, target_chara_id)
        condition = min(
            wardrobe.of(npc_data.cid).equipment_condition + maintain_value, 0
        )
        wardrobe.set(npc_data.cid, "equipment_condition", condition)
        repair_flag = True
        new_condition_text = get_equipment_condition_name(condition)
        repair_text = _("{0}维修了{1}的装备，当前情况：{2} ({3})\n").format(
            smith_chara_data.name,
            npc_data.name,
            new_condition_text,
            round(condition, 1),
        )
        if smith_chara_id in maintenance.repairs() and condition >= 0:
            maintenance.drop_repair(smith_chara_id)
            achievement.add("equipment_repair_count", 1)
            achievement_service.settle_and_notify(_("维修"))
    return repair_flag, repair_text


def maintain_equipment(
    smith_chara_id: int, target_chara_id: int = 0
) -> tuple[bool, str]:
    """
    为指定铁匠执行一次装备保养。
    保养量等于能力 48 修正值除以 4，乘以 0.8 至 1.2 随机系数与设施 2 效率。
    maintenance.settings() 第 1 项为保养上限（默认 0），第 2 项选候选范围。
    第 2 项为 0 取在队角色，非 0 取 maintenance.operators()，均排除铁匠本人。
    target_chara_id 为 0 时从候选中取状态低于上限的最低者。
    目标大于 0 时加上保养量并封顶于上限，铁匠职业写入维修记录。
    在记录中且达上限时清除记录，equipment_maintenance_count 加 1。
    此时调用 achievement_service.settle_and_notify 结算保养成就。
    Keyword arguments:
    smith_chara_id -- int，铁匠角色编号
    target_chara_id -- int，目标编号，0 为自动选择，默认 0
    Return arguments:
    tuple[bool, str] -- 是否保养与结果行，未执行返回 (False, "")
    """
    smith_chara_data = identity.of(smith_chara_id)
    ability_lv = abilities.ability(smith_chara_id)[48]
    maintain_value = handle_ability.get_ability_adjust(ability_lv) / 4
    maintain_value *= random.uniform(0.8, 1.2)
    maintain_value *= basement.calc_facility_efficiency(2)
    maintain_enable = maintenance.settings().get(1, 0)
    maintain_target = maintenance.settings().get(2, 0)
    maintain_operator_ids = maintenance.operators()

    maintain_flag = False
    maintain_text = ""

    if target_chara_id == 0:
        if maintain_target == 0:
            candidate_ids = [i for i in roster.active() if i != smith_chara_id]
        else:
            candidate_ids = [
                i for i in maintain_operator_ids if i != smith_chara_id
            ]
        maintain_list = []
        for npc_id in candidate_ids:
            npc_data = identity.of(npc_id)
            cond = wardrobe.of(npc_data.cid).equipment_condition
            if cond < maintain_enable:
                maintain_list.append((npc_id, cond))
        if maintain_list:
            maintain_list.sort(key=lambda x: x[1])
            target_chara_id, cond = maintain_list[0]
    if target_chara_id > 0:
        npc_data = identity.of(target_chara_id)
        if handle_premise.handle_work_is_blacksmith(smith_chara_id):
            maintenance.set_repair(smith_chara_id, target_chara_id)
        condition = min(
            wardrobe.of(npc_data.cid).equipment_condition + maintain_value,
            maintain_enable,
        )
        wardrobe.set(npc_data.cid, "equipment_condition", condition)
        maintain_flag = True
        new_condition_text = get_equipment_condition_name(condition)
        maintain_text = _("{0}保养了{1}的装备，当前情况：{2} ({3})\n").format(
            smith_chara_data.name,
            npc_data.name,
            new_condition_text,
            round(condition, 1),
        )
        if (
            smith_chara_id in maintenance.repairs()
            and condition >= maintain_enable
        ):
            maintenance.drop_repair(smith_chara_id)
            achievement.add("equipment_maintenance_count", 1)
            achievement_service.settle_and_notify(_("保养"))
    return maintain_flag, maintain_text
