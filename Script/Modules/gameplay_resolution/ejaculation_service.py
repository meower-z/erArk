"""
射精结算服务（ejaculation_service）
===================================
本模块提供忍耐射精判定、通用射精结算、射精总流程，以及忍耐询问与射精面板回调的登记与触发入口。
射精文本经 ui_hooks 的提示与分隔线接口输出。
本模块不直接导入界面、Tk 或输入输出模块。
未登记回调时，emit_ejaculation_panel 不执行操作。
未登记回调时，emit_endure_panel 返回 False。
"""

import random
from collections.abc import Callable
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text, num
from Script.Design import handle_ability, handle_premise
from Script.Modules.domains import abilities, achievement, action_info
from Script.Modules.domains import activity, dirty, flags, h_meters, h_state
from Script.Modules.domains import identity, pregnancy, tallies
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import semen_dirty_service, ui_hooks

_: FunctionType = get_text._
""" 翻译api """

type EndurePanel = Callable[[], bool]
""" 忍耐射精询问回调函数类型，返回 True 表示忍住射精。 """
_endure_panel: EndurePanel | None = None
""" 当前登记的忍耐射精询问回调，未登记时为 None。 """


def on_endure_panel(fn: EndurePanel) -> EndurePanel:
    """
    登记忍耐射精询问回调，可作为装饰器使用，后登记的回调覆盖先前的回调。
    Keyword arguments:
    fn -- EndurePanel，询问是否忍住射精并返回结果的回调函数
    Return arguments:
    EndurePanel -- 原样返回传入的 fn
    """
    global _endure_panel
    _endure_panel = fn
    return fn


def emit_endure_panel() -> bool:
    """
    调用当前登记的忍耐射精询问回调。
    Return arguments:
    bool -- 已登记时返回回调的布尔结果，未登记时返回 False
    """
    if _endure_panel is None:
        return False
    return bool(_endure_panel())


type EjaculationPanel = Callable[[], None]
""" 射精面板回调函数类型，不接收参数。 """
_ejaculation_panel: EjaculationPanel | None = None
""" 当前登记的射精面板回调，未登记时为 None。 """


def on_ejaculation_panel(fn: EjaculationPanel) -> EjaculationPanel:
    """
    登记射精面板回调，可作为装饰器使用，后登记的回调覆盖先前的回调。
    Keyword arguments:
    fn -- EjaculationPanel，绘制射精面板的回调函数
    Return arguments:
    EjaculationPanel -- 原样返回传入的 fn
    """
    global _ejaculation_panel
    _ejaculation_panel = fn
    return fn


def emit_ejaculation_panel() -> None:
    """
    调用当前登记的射精面板回调，未登记时不执行操作。
    Return arguments:
    None -- 无返回值
    """
    if _ejaculation_panel is not None:
        _ejaculation_panel()


def judge_endure_ejaculation(endure_rate: int) -> bool:
    """
    计算是否忍住射精
    Keyword arguments:
    endure_rate -- 忍住射精的几率
    """
    if random.randint(1, 100) <= endure_rate:
        return True
    else:
        return False


def common_ejaculation() -> tuple[str, int]:
    """
    通用射精结算，进行一次射精，并返回射精文本和射精量
    return
    semen_text 射精文本
    semen_count 射精量
    """

    random_weight = random.uniform(0.8, 1.2)

    extra_text = ""

    if handle_premise.handle_pl_semen_le_2(0):
        return _("只流出了些许前列腺液，已经射不出精液了"), 0
    else:
        endure_cnt = h_state.get(0, "endure_not_shot_count")
        if activity.second_behavior(0, "p_orgasm_strong") == 1:
            semen_count: float = int(
                game_config.config_semen_shoot_amount[2].base_semen_amount
                * random_weight
            ) * (endure_cnt + 1)
            semen_text = _("超大量射精，射出了")
        elif activity.second_behavior(0, "p_orgasm_normal") == 1:
            semen_count = int(
                game_config.config_semen_shoot_amount[1].base_semen_amount
                * random_weight
            ) * (endure_cnt + 1)
            semen_text = _("大量射精，射出了")
        else:
            semen_count = int(
                game_config.config_semen_shoot_amount[0].base_semen_amount
                * random_weight
            )
            semen_text = _("射精，射出了")

        if activity.target(0) > 0:
            target_data: identity.Identity = identity.of(activity.target(0))
            squeeze_adjust = handle_ability.get_ability_adjust(
                abilities.ability(target_data.cid)[77]
            )
            semen_count *= squeeze_adjust
            if squeeze_adjust > 1:
                extra_text += _("（{0}榨精+）").format(target_data.name)

        if action_info.get(0, "day_first_shoot_semen"):
            semen_count *= 2
            action_info.set(0, "day_first_shoot_semen", False)
            extra_text += _("（醒来第一发+）")

        if handle_premise.handle_self_semen_energy_agent(0):
            semen_count *= 2
            h_state.set(0, used_semen_energy_agent=False)
            extra_text += _("（精力剂+）")

        if handle_premise.handle_aromatherapy_flag_7(0):
            semen_count *= 2
            extra_text += (
                f"（{game_config.config_aromatherapy_recipes[7].name}+）"
            )

        if handle_premise.handle_pl_semen_tmp_ge_max(0):
            semen_count *= 2
            extra_text += _("（积攒精液+）")

        if handle_premise.handle_self_semen_thick_1(0):
            semen_count *= 2
            extra_text += _("（浓厚精液+）")

        meters = h_meters.of(0)
        semen_ml = min(
            int(semen_count),
            num.whole(meters["semen"] + meters["extra_semen"]),
        )
        semen_text += str(semen_ml) + _("ml精液") + extra_text

        with h_state.editing(0) as hs:
            hs.orgasm_level[3] += 1
            hs.just_shoot = 1
            hs.endure_not_shot_count = 0
        with dirty.editing(0) as d:
            d.penis_dirty_dict["semen"] = True
        tallies.add(tallies.SEMEN, semen_ml)

        extra = meters["extra_semen"]
        if extra > semen_ml:
            h_meters.set(
                0,
                extra_semen=extra - semen_ml,
                semen=max(0, meters["semen"]),
            )
        else:
            h_meters.set(
                0,
                semen=max(0, meters["semen"] - (semen_ml - extra)),
                extra_semen=0,
            )

        return semen_text, semen_ml


def ejaculation_flow(
    part_cid: int,
    part_type: int,
    target_character_id: int = 0,
    draw_flag: bool = True,
    soft_egg_id: int = -1,
) -> None:
    """
    执行射精结算总流程，完成精液去向、状态更新、提示输出与成就结算。
    Keyword arguments:
    part_cid -- int，部位编号（cid）
    part_type -- int，部位类型，0 为身体，1 为穿着服装，2 为浴场衣柜，3 为宿舍衣柜
    target_character_id -- int，目标角色编号，默认为 0（为 0 时取当前交互对象）
    draw_flag -- bool，为真时经 ui_hooks 的提示与分隔线接口输出换行、分隔线、换行、
    按文本宽度排版的 semen 样式等待射精文本与两次换行，默认为 True
    soft_egg_id -- int，射在体外无壳卵上时的卵编号，默认为 -1（不射在卵上），
    未戴避孕套且非负时精液全部加到该卵并跳过部位污浊、精液流动、受精概率与射精部位记录
    Return arguments:
    None -- 无返回值
    """
    character_data: identity.Identity = identity.of(0)
    if target_character_id == 0:
        target_character_id = activity.target(0)
    target_data: identity.Identity = identity.of(target_character_id)

    semen_text, semen_count = common_ejaculation()

    if semen_count > 0:
        h_state.set(
            0,
            shoot_semen_amount=h_state.get(0, "shoot_semen_amount")
            + semen_count,
        )
        if handle_premise.handle_group_sex_mode_on(0):
            achievement.append_entry("group_sex_record", 1, target_character_id)
        elif handle_premise.handle_hidden_sex_mode_ge_1(0):
            achievement.add_entry("hidden_sex_record", 3)
        elif handle_premise.handle_exhibitionism_sex_mode_ge_1(0):
            achievement.add_entry("exhibitionism_sex_record", 3)
        elif handle_premise.handle_t_unconscious_flag_1(0):
            achievement.add_entry("sleep_sex_record", 2)
        if not h_state.body_item_on(0, 13):
            if soft_egg_id >= 0:
                from Script.System.Pregnancy_System import soft_egg_handle

                soft_egg_handle.add_semen_to_soft_egg(soft_egg_id, semen_count)
                now_text = _("在{0}上{1}").format(
                    soft_egg_handle.get_soft_egg_name(soft_egg_id), semen_text
                )
            elif target_character_id > 0:
                h_meters.set_shoot_position(part_cid)
                semen_dirty_service.update_semen_dirty(
                    target_character_id, part_cid, part_type, semen_count
                )
                if part_type in [0, 1]:
                    semen_dirty_service.calculate_semen_flow(
                        target_character_id, part_cid, part_type, semen_count
                    )
                from Script.System.Pregnancy_System import pregnancy_handle

                pregnancy_handle.get_fertilization_rate(target_character_id)
                if part_type == 0:
                    part_name = game_config.config_body_part[part_cid].name
                    now_text = _("在{0}的{1}{2}").format(
                        target_data.name, part_name, semen_text
                    )
                    if (
                        part_cid in [6, 7]
                        and flags.get(target_character_id, "unconscious_h") == 0
                    ):
                        pregnancy.update(
                            target_data.cid, unconscious_fertilization=False
                        )
                else:
                    cloth_text = game_config.config_clothing_type[part_cid].name
                    now_text = _("在{0}的{1}{2}").format(
                        target_data.name, cloth_text, semen_text
                    )
            else:
                now_text = character_data.name + semen_text
        else:
            h_meters.set_shoot_position(0)
            condom_cnt = h_state.get(0, "condom_count")
            h_state.set(
                0, condom_count=[condom_cnt[0] + 1, condom_cnt[1] + semen_count]
            )
            from Script.System.Item_System import condom_handle

            condom_handle.add_used_condom(semen_count)
            h_state.set_body_item(0, 13, False)
            now_text = _("在避孕套里") + semen_text

    else:
        now_text = character_data.name + semen_text

    if draw_flag:
        ui_hooks.emit_notice("\n")
        ui_hooks.emit_divider()
        ui_hooks.emit_notice("\n")
        ui_hooks.emit_notice(
            now_text, wait=True, style="semen", use_text_width=True
        )
        ui_hooks.emit_notice("\n")
        ui_hooks.emit_notice("\n")

    achievement_service.get_achievement_judge_by_value(1201, 1)
    achievement_service.settle_and_notify(_("射精"))
