"""
流水线生产结算服务（assembly_service）
======================================
提供制造加工流水线的效率计算与生产结算逻辑。
结算流程经 ui_hooks 发出提示，并经 achievement_service 触发生产成就结算。
本模块不直接导入界面模块，供流水线管理面板与 basement 调用。
"""

from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import basement, game_time, handle_ability
from Script.Modules.domains import abilities, achievement, identity
from Script.Modules.domains import maintenance, medical, production, warehouse
from Script.Modules.gameplay_resolution import achievement_service, ui_hooks

_: FunctionType = get_text._
""" 翻译api """


def calculate_assembly_line_efficiency(line_id: int) -> tuple[str, float]:
    """
    计算某条生产线当前总效率(百分比值)
    输入参数:
    line_id -- 流水线id
    输出参数:
    流水线效率(百分比值, 例如 123.5)
    """
    lines = production.lines("assembly")
    if line_id not in lines:
        return _("无此生产线"), 0.0
    facility_effect_ratio = basement.calc_facility_efficiency(12)
    facility_effect_str = _("* 设施效率调整{0}%").format(
        round((facility_effect_ratio) * 100, 1)
    )
    base = facility_effect_ratio * 100
    line_main_id = lines[line_id]["main"]
    ability = abilities.ability(line_main_id)
    main_ids = {line["main"] for line in lines.values()}
    total = base
    sub_bonus = 0.0
    worker_str = "["
    if identity.exists(line_main_id) and line_main_id != 0:
        char_data: identity.Identity = identity.of(line_main_id)
        main_bonus = 10 * handle_ability.get_ability_adjust(ability[48])
        total += main_bonus
        worker_str = _("主:{0}(制造lv{1}:{2}%)").format(
            char_data.name, ability[48], round(main_bonus, 1)
        )
    else:
        worker_str += _("主:空缺")
    for cid in production.workers("assembly"):
        if cid == 0 or not identity.exists(cid):
            continue
        if cid in main_ids:
            continue
        base_effect = 2 * handle_ability.get_ability_adjust(
            abilities.ability(cid).get(48, 0)
        )
        sub_bonus += base_effect
    total += sub_bonus
    worker_str += _("，副:{0}%]").format(round(sub_bonus, 1))
    detail_str = _("当前效率加成：{0} {1} = {2}%").format(
        worker_str, facility_effect_str, round(total, 1)
    )
    return detail_str, round(total, 2)


def settle_assembly_line(
    newdayflag: bool = False, draw_flag: bool = True
) -> tuple[bool, str]:
    """
    结算流水线的生产\n
    Keyword arguments:\n
    newdayflag -- 是否是新的一天\n
    draw_flag -- 是否绘制结算信息\n
    Return arguments:\n
    un_normal -- 是否有异常\n
    return_text -- 结算信息\n
    """

    un_normal = False
    return_text = "\n"

    if newdayflag and draw_flag:
        return_text += _("○制造加工部结算：\n")

    damage_down = 0
    for facility_str, count in maintenance.damage().items():
        if "制造加工" in facility_str:
            damage_down = count * 2

    hospital_bed_modules = 0
    extra_warehouse_modules = 0

    for assembly_line_id, line in production.lines("assembly").items():
        now_formula_id = line["product"]
        if now_formula_id != 0:
            formula_data_now = game_config.config_productformula_data[
                now_formula_id
            ]
            formula_now = game_config.config_productformula[now_formula_id]
            product_id = formula_now.product_id
            if newdayflag:
                max_time = 24 + game_time.now().hour - line["hour"]
            else:
                max_time = game_time.now().hour - line["hour"]
            _detail_str, produce_effect = calculate_assembly_line_efficiency(
                assembly_line_id
            )
            produce_effect = produce_effect / 100
            produce_num_max = int(max_time * produce_effect)
            produce_num = produce_num_max

            for need_type in formula_data_now:
                now_type_max_produce_num = (
                    warehouse.amount(need_type) // formula_data_now[need_type]
                )
                produce_num = min(produce_num, now_type_max_produce_num)

            if produce_num > 0:
                for need_type in formula_data_now:
                    warehouse.add(
                        need_type, -(produce_num * formula_data_now[need_type])
                    )
                warehouse.add(product_id, produce_num)
                achievement.add("production_count", produce_num)
                if product_id == 54:
                    hospital_bed_modules += produce_num
                elif product_id == 55:
                    extra_warehouse_modules += produce_num

                now_text = _("\n 流水线{0}:").format(assembly_line_id)
                now_text += _("上次结算是{0}时，到现在已过{1}小时，").format(
                    line["hour"],
                    max_time,
                )
                if damage_down > 0:
                    now_text += _("由于设备故障，生产效率下降{0}%，").format(
                        damage_down
                    )
                if produce_num < produce_num_max:
                    now_text += _(
                        "由于原料不足，最大可以生产{0}个，实际"
                    ).format(produce_num)
                    un_normal = True
                now_text += _("共生产了{0}个{1}").format(
                    produce_num, game_config.config_resouce[product_id].name
                )
                if warehouse.amount(product_id) > warehouse.capacity():
                    warehouse.set(product_id, warehouse.capacity())
                    now_text += _(
                        "，由于仓库容量不足，{0}已达上限数量{1}"
                    ).format(
                        game_config.config_resouce[product_id].name,
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
            "assembly", assembly_line_id, hour=game_time.now().hour
        )
    achievement_service.settle_and_notify(_("生产"))
    if hospital_bed_modules > 0:
        from Script.System.Medical_System import medical_core

        with medical.editing() as m:
            m.bed_modules += hospital_bed_modules
            m.bed_limit = medical_core._calculate_medical_bed_limit()
        hospital_bed_modules_text = _(
            "○由于生产了{0}个住院病房扩展模块，罗德岛住院部床位数量提升了{1}个！\n"
        ).format(hospital_bed_modules, hospital_bed_modules * 3)
        return_text += hospital_bed_modules_text
        if draw_flag:
            ui_hooks.emit_notice(
                hospital_bed_modules_text, wait=True, use_text_width=True
            )

    if extra_warehouse_modules > 0:
        warehouse.set_extra_modules(
            warehouse.extra_modules() + extra_warehouse_modules
        )
        extra_warehouse_modules_text = _(
            "○由于生产了{0}个仓储空间扩展模块，罗德岛仓库容量提升了{1}！\n"
        ).format(extra_warehouse_modules, extra_warehouse_modules * 200)
        return_text += extra_warehouse_modules_text
        if draw_flag:
            ui_hooks.emit_notice(
                extra_warehouse_modules_text, wait=True, use_text_width=True
            )

    return un_normal, return_text
