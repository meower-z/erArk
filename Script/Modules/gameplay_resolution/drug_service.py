"""
药物使用效果服务（drug_service）
================================
本模块提供药物礼物使用效果的处理入口 handle_drug_use_effect。
本模块不导入 Script.UI 界面模块或 pregnancy_panel。
处理结果的提示文本通过 ui_hooks.emit_notice 发出。
"""

from types import FunctionType

from Script.Core import get_text
from Script.Design import game_time
from Script.Modules.domains import abilities, activity, identity, pregnancy
from Script.Modules.gameplay_resolution import ui_hooks
from Script.System.Pregnancy_System import pregnancy_constant

_: FunctionType = get_text._
""" 翻译api """


def handle_drug_use_effect(character_id: int, drug_id: int) -> None:
    """
    按药物编号对目标角色结算药物使用效果。
    结算结果以 gold_enrod 样式经 ui_hooks.emit_notice 发出并等待确认。
    Keyword arguments:
    character_id -- int，目标角色编号
    drug_id -- int，药物编号
    Return arguments:
    None -- 无返回值
    """
    from Script.Design import handle_talent

    character_data: identity.Identity = identity.of(character_id)
    text = "\n  "
    if drug_id == 21:
        text += handle_talent.body_part_talent_update(
            character_id, [121, 122, 123, 124, 125], True, _("胸部")
        )
    elif drug_id == 22:
        text += handle_talent.body_part_talent_update(
            character_id, [121, 122, 123, 124, 125], False, _("胸部")
        )
    elif drug_id == 23:
        text += handle_talent.body_part_talent_update(
            character_id, [126, 127, 128], True, _("臀部")
        )
    elif drug_id == 24:
        text += handle_talent.body_part_talent_update(
            character_id, [126, 127, 128], False, _("臀部")
        )
    elif drug_id == 25:
        text += handle_talent.body_part_talent_update(
            character_id, [129, 130], True, _("腿部")
        )
    elif drug_id == 26:
        text += handle_talent.body_part_talent_update(
            character_id, [129, 130], False, _("腿部")
        )
    elif drug_id == 27:
        text += handle_talent.body_part_talent_update(
            character_id, [131, 132], True, _("足部")
        )
    elif drug_id == 28:
        text += handle_talent.body_part_talent_update(
            character_id, [131, 132], False, _("足部")
        )
    elif drug_id == 33:
        abilities.talent(character_id)[27] = 1
        text += _("{0}获得了【泌乳】\n").format(character_data.name)
    elif drug_id == 34:
        abilities.talent(character_id)[27] = 0
        text += _("{0}失去了【泌乳】\n").format(character_data.name)
    elif drug_id == 35:
        from Script.System.Pregnancy_System import pregnancy_handle

        add_day = pregnancy_handle.get_pregnancy_acceleration_amount(
            character_id
        )
        if add_day > 0:
            with pregnancy.editing(character_id) as preg:
                preg.acceleration_days += add_day
                now_acc = int(preg.acceleration_days)
                fert_time = preg.fertilization_time
            predict_time = game_time.get_predict_date(
                pregnancy_constant.PARTURIENT_DAY - now_acc,
                fert_time,
            )
            text += _(
                "本次加速{0}，累计加速{1}，{2}的预计临盆日期提前到了{3}\n"
            ).format(
                game_time.get_duration_text(add_day),
                game_time.get_duration_text(now_acc),
                character_data.name,
                pregnancy_constant.format_season_date(predict_time),
            )
        else:
            text += _("{0}的孕期已经加速到极限，药物没有产生效果\n").format(
                character_data.name
            )
    elif drug_id == 36:
        from Script.System.Pregnancy_System import egg_handle

        egg_id = activity.behavior(0).gift_egg_id
        activity.update_behavior(0, gift_egg_id=-1)
        with pregnancy.editing(character_id) as preg:
            egg_data = preg.eggs.get(egg_id)
            if egg_data is None or not (
                egg_data["identified"] and egg_data["fertilized"]
            ):
                text += _("选中的卵已经不存在，药物没有产生效果\n")
            else:
                add_day = egg_handle.get_egg_acceleration_amount(egg_data)
                if add_day > 0:
                    egg_data["acceleration_days"] = (
                        egg_data.get("acceleration_days", 0) + add_day
                    )
                    now_acc = int(egg_data["acceleration_days"])
                    predict_time = game_time.get_predict_date(
                        pregnancy_constant.HATCH_TOTAL_DAY - now_acc,
                        egg_data["lay_time"],
                    )
                    text += _(
                        "本次加速{0}，累计加速{1}，这枚卵的预计破壳日期提前到了{2}\n"
                    ).format(
                        game_time.get_duration_text(add_day),
                        game_time.get_duration_text(now_acc),
                        pregnancy_constant.format_season_date(predict_time),
                    )
                else:
                    text += _("这枚卵已经加速到极限，药物没有产生效果\n")
    elif drug_id == 37:
        abilities.talent(character_id)[25] = 1
        text += _(
            "{0}获得了【假孕孕肚】，肚子像真正的孕妇一样隆起来了\n"
        ).format(character_data.name)
    elif drug_id == 38:
        abilities.talent(character_id)[25] = 0
        text += _("{0}失去了【假孕孕肚】，隆起的肚子恢复了原状\n").format(
            character_data.name
        )
    elif drug_id == 39:
        from Script.System.Pregnancy_System import pregnancy_handle

        if pregnancy_handle.is_growth_drug_self_target(character_id):
            child_id = character_id
        else:
            child_id = activity.behavior(0).gift_child_id
            activity.update_behavior(0, gift_child_id=-1)
            if child_id not in pregnancy_handle.get_baby_id_list(character_id):
                child_id = -1
                text += _("选中的婴儿已经不在婴儿期，药物没有产生效果\n")
        if child_id != -1:
            child_character_data: identity.Identity = identity.of(child_id)
            add_day = pregnancy_handle.get_child_growth_acceleration_amount(
                child_id
            )
            next_stage_name = pregnancy_handle.get_child_next_stage_name(
                child_id
            )
            if add_day > 0:
                with pregnancy.editing(child_id) as child_preg:
                    child_preg.growth_acceleration_days += add_day
                    now_acc = int(child_preg.growth_acceleration_days)
                    born_time = child_preg.born_time
                total_day = pregnancy_handle.get_child_growth_stage_total_day(
                    child_id
                )
                predict_time = game_time.get_predict_date(
                    total_day - now_acc,
                    born_time,
                )
                text += _(
                    "本次加速{0}，累计加速{1}，{2}预计将在{3}成长为{4}\n"
                ).format(
                    game_time.get_duration_text(add_day),
                    game_time.get_duration_text(now_acc),
                    child_character_data.name,
                    pregnancy_constant.format_season_date(predict_time),
                    next_stage_name,
                )
            else:
                text += _("{0}已经快要成长为{1}了，药物没有产生效果\n").format(
                    child_character_data.name, next_stage_name
                )
    elif drug_id == 40:
        abilities.talent(character_id)[28] = 1
        text += _(
            "{0}获得了【成长停滞】，在使用成长继续药之前她会一直保持在当前的阶段\n"
        ).format(character_data.name)
    elif drug_id == 41:
        abilities.talent(character_id)[28] = 0
        text += _("{0}失去了【成长停滞】，她会继续正常成长\n").format(
            character_data.name
        )
    ui_hooks.emit_notice(text, wait=True, style="gold_enrod")
