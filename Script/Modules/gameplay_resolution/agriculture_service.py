"""
农业生产结算服务（agriculture_service）
=======================================
提供药田与温室生产线的效率计算与生产结算逻辑。
结算流程经 ui_hooks 发出提示，并经 achievement_service 触发种植成就结算。
本模块不直接导入界面模块，供农业生产面板与 basement 调用。
"""

from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import basement, game_time, handle_ability
from Script.Modules.domains import abilities, achievement, identity
from Script.Modules.domains import maintenance, production, warehouse
from Script.Modules.gameplay_resolution import achievement_service, ui_hooks

_: FunctionType = get_text._
""" 翻译api """


def calculate_agriculture_line_efficiency(
    line_id: int, agriculture_type: int
) -> tuple[str, float]:
    """
    计算某条农业生产线的效率加成，并返回描述字符串和效率倍率\n
    输入:\n
        line_id: 生产线id\n
        agriculture_type: 农业类型，0药田，1温室\n
    返回:\n
        detail_str: str 描述字符串\n
        total_bonus: float 效率倍率，例如 1.25 表示125%\n
    说明:\n
        主种植员提供100%个人加成，副种植员提供20%个人加成，总加成乘以设施效率\n
    """
    facility_effect = basement.calc_facility_efficiency(16)
    if agriculture_type == 0:
        facility_effect += basement.calc_facility_efficiency(41) - 1
    facility_effect_str = _("* 设施效率调整{0}%").format(
        round(facility_effect * 100, 1)
    )

    kind = ("herb_garden", "green_house")[agriculture_type]
    lines = production.lines(kind)
    main_id = lines.get(line_id, production.IDLE)["main"]
    operator_ids = production.workers(kind)
    main_ids = {line["main"] for line in lines.values()}

    total_bonus = 0.0
    sub_bonus = 0.0
    parts_str = "["
    if identity.exists(main_id) and main_id != 0:
        c = identity.of(main_id)
        base_effect = 10 * handle_ability.get_ability_adjust(
            abilities.ability(main_id).get(47, 0)
        )
        total_bonus += base_effect
        parts_str += _("主:{0}(农业lv{1}:{2}%)").format(
            c.name, abilities.ability(main_id).get(47, 0), round(base_effect, 1)
        )
    else:
        parts_str += _("主:空缺")

    for cid in operator_ids:
        if cid == 0 or not identity.exists(cid):
            continue
        if cid == main_id:
            continue
        if cid in main_ids:
            continue
        base = 10 * handle_ability.get_ability_adjust(
            abilities.ability(cid).get(47, 0)
        )
        sub_bonus += base / 5
    total_bonus += sub_bonus
    parts_str += _("，副:{0}%]").format(round(sub_bonus, 1))

    ratio = (100.0 + total_bonus) / 100.0
    ratio *= facility_effect

    detail_str = _("当前效率加成：{0} {1} = {2}%").format(
        parts_str, facility_effect_str, round(ratio * 100, 1)
    )
    return detail_str, ratio


def settle_agriculture_line(draw_flag: bool = True) -> tuple[bool, str]:
    """
    结算农业的生产
    Keyword arguments:
    draw_flag -- 是否绘制结算信息
    Return arguments:
    un_normal -- bool 是否有异常
    return_text -- str 结算信息
    """
    un_normal = False
    return_text = "\n"
    if draw_flag:
        return_text += _("○疗养庭院结算：\n")
    damage_down = 0
    for facility_str, count in maintenance.damage().items():
        if "疗养庭院" in facility_str:
            damage_down = count * 2

    for agriculture_line_id, line in production.lines("herb_garden").items():
        resouce_id = line["product"]
        if resouce_id != 0:
            resouce_data = game_config.config_resouce[resouce_id]

            max_time = 10
            _detail_str, produce_effect = calculate_agriculture_line_efficiency(
                agriculture_line_id, 0
            )
            produce_num_max = int(max_time * produce_effect)
            produce_num = produce_num_max

            if produce_num > 0:
                warehouse.add(resouce_id, produce_num)
                achievement.add("harvest_count", produce_num)

                now_text = _("\n今日药田共生产了{0}个{1}").format(
                    produce_num, resouce_data.name
                )
                if damage_down > 0:
                    now_text += _("，由于设备故障，生产效率下降{0}%").format(
                        damage_down
                    )
                if warehouse.amount(resouce_id) > warehouse.capacity():
                    warehouse.set(resouce_id, warehouse.capacity())
                    now_text += _(
                        "，由于仓库容量不足，{0}已达上限数量{1}"
                    ).format(
                        resouce_data.name,
                        warehouse.capacity(),
                    )
                    un_normal = True
                now_text += "\n"
                return_text += now_text
                if draw_flag:
                    ui_hooks.emit_notice(
                        now_text, wait=True, use_text_width=True
                    )

        production.set_line(
            "herb_garden", agriculture_line_id, hour=game_time.now().hour
        )

    for agriculture_line_id, line in production.lines("green_house").items():
        resouce_id = line["product"]
        if resouce_id != 0:
            resouce_data = game_config.config_resouce[resouce_id]

            max_time = 10
            _detail_str, produce_effect = calculate_agriculture_line_efficiency(
                agriculture_line_id, 1
            )
            produce_num_max = int(max_time * produce_effect)
            produce_num = produce_num_max

            if produce_num > 0:
                warehouse.add(resouce_id, produce_num)
                achievement.add("harvest_count", produce_num)

                now_text = _("\n今日温室共生产了{0}个{1}").format(
                    produce_num, resouce_data.name
                )
                if damage_down > 0:
                    now_text += _("，由于设备故障，生产效率下降{0}%").format(
                        damage_down
                    )
                if warehouse.amount(resouce_id) > warehouse.capacity():
                    warehouse.set(resouce_id, warehouse.capacity())
                    now_text += _(
                        "，由于仓库容量不足，{0}已达上限数量{1}"
                    ).format(
                        resouce_data.name,
                        warehouse.capacity(),
                    )
                    un_normal = True
                now_text += "\n"
                return_text += now_text
                if draw_flag:
                    ui_hooks.emit_notice(
                        now_text, wait=True, use_text_width=True
                    )

        production.set_line(
            "green_house", agriculture_line_id, hour=game_time.now().hour
        )

    achievement_service.settle_and_notify(_("种植"))

    return un_normal, return_text
