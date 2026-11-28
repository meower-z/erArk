"""
射精结算服务（ejaculation_service）
===================================
本模块提供忍耐判定、射精目标与部位决策、通用射精结算与射精总流程。
emit_endure_panel 按系统设置 11 分支，需要询问时经 modal_hooks 发出忍耐选项提示。
resolve_ejaculation 按当前对象、群交状态、场景无壳卵与系统设置 3 决定射精去向。
resolve_ejaculation 在需要询问时经 modal_hooks 发出对象或部位选项提示。
忍耐结果、射精文本与分隔线经 ui_hooks 输出。
射精前的按钮清理与部位选择后的面板切换同样经 ui_hooks 派发。
本模块不导入界面、Tk 或输入输出模块。
未在 modal_hooks 登记处理函数时，需要询问的分支由 modal_hooks.ask 抛出 RuntimeError。
"""

import random
from types import FunctionType

from Script.Config import game_config, normal_config
from Script.Core import constant, get_text, num
from Script.Design import clothing, handle_ability, handle_premise
from Script.Design import instuct_judege, map_handle
from Script.Modules.domains import abilities, achievement, action_info
from Script.Modules.domains import activity, dirty, flags, h_meters, h_state
from Script.Modules.domains import identity, modes, pregnancy, scene_state
from Script.Modules.domains import tallies, wardrobe
from Script.Modules.gameplay_resolution import achievement_service, modal_hooks
from Script.Modules.gameplay_resolution import semen_dirty_service, ui_hooks
from Script.Protocol.modal_prompts import ChoiceOption, ChoicePrompt

_: FunctionType = get_text._
""" 翻译api """

ENDURE_PROMPT_ID = "ejaculation_endure"
""" 忍耐射精提问使用的 ChoicePrompt 标识（"ejaculation_endure"）。 """


def emit_endure_panel() -> bool:
    """
    判定玩家本次是否忍住射精，并在忍住时写回状态与输出结果。
    函数先按玩家能力 30 等级与当前忍耐次数计算几率并调用 judge_endure_ejaculation 掷骰，
    再按系统设置 11（缺省为 2）分支。
    设为 2 或缺省时，函数经 modal_hooks.ask 询问「忍住」或「射出」。
    玩家选「射出」则判定未忍住，选「忍住」则采用掷骰结果。
    未在 modal_hooks 登记选择处理函数时，该分支的 modal_hooks.ask 抛出 RuntimeError。
    设为 1 时不提问并直接采用掷骰结果。
    设为 0 或其他非 1、2 值时不提问并判定未忍住。
    忍住时将 h_state 的 endure_not_shot_count 加 1 且将 h_meters 的 eja 清零，
    再经 ui_hooks 输出按文本宽度排版的忍耐提示与分隔线。
    Return arguments:
    bool -- 忍住射精返回 True，否则返回 False
    """
    now_lv = abilities.ability(0)[30]
    now_count = h_state.get(0, "endure_not_shot_count")
    if now_count <= now_lv:
        now_rate = 100
        endure_text = _("必定忍住")
    else:
        now_rate = max(0, 100 - (now_count - now_lv) * (50 - now_lv * 5))
        if now_rate >= 75:
            endure_text = _("高")
        elif now_rate >= 50:
            endure_text = _("中")
        elif now_rate >= 25:
            endure_text = _("低")
        else:
            endure_text = _("无")
    endured = judge_endure_ejaculation(now_rate)
    setting = normal_config.system_setting.base_setting.get(11, 2)
    if setting == 2:
        prompt = ChoicePrompt(
            ENDURE_PROMPT_ID,
            (
                ChoiceOption("endure", _("忍住")),
                ChoiceOption("release", _("射出")),
            ),
            _(
                "要射精了，是否要忍住射精，忍耐次数越多则射精量越多（当前已忍住{0}次，忍耐几率 {1}）\n"
            ).format(now_count, endure_text),
        )
        if modal_hooks.ask(prompt).selected_option_id == "release":
            endured = False
    elif setting != 1:
        endured = False
    if endured:
        h_state.set(0, endure_not_shot_count=now_count + 1)
        h_meters.set(0, eja=0)
        name = identity.of(0).name
        ui_hooks.emit_notice(
            _("\n{0}忍住了射精\n").format(name), use_text_width=True
        )
        ui_hooks.emit_divider()
    return endured


TARGET_PROMPT_ID = "ejaculation_target"
""" 群交时选择射精对象使用的 ChoicePrompt 标识（"ejaculation_target"）。 """
PART_PROMPT_ID = "ejaculation_part"
""" 选择射精部位使用的 ChoicePrompt 标识（"ejaculation_part"）。 """
INSERTED_PARTS = {
    6: ("handle_penis_in_t_vagina", "handle_penis_in_t_womb"),
    7: ("handle_penis_in_t_womb",),
    8: ("handle_penis_in_t_anal",),
    9: ("handle_penis_in_t_nrethral",),
    15: ("handle_penis_in_t_deep_throat",),
}
""" 需要满足插入前提才可选的身体部位编号到 handle_premise 前提函数名元组的映射。 """


def resolve_ejaculation() -> None:
    """
    决定本次射精的目标与部位并执行射精流程，结束后经 ui_hooks.emit_divider 输出分隔线。
    对象为 0 时，有场景无壳卵则进入自身模式部位提问，否则直接射向部位 6。
    群交模式下依次提问射精对象与部位。
    场景有无壳卵或系统设置 3 为真时直接提问射精部位。
    其余情况按目标的 insert_position 自动决定部位，为 -1 时提问部位。
    Return arguments:
    None -- 无返回值
    """
    from Script.System.Pregnancy_System import soft_egg_handle

    target_id = activity.target(0)
    eggs = soft_egg_handle.get_soft_eggs_in_scene(activity.position(0))
    if target_id == 0:
        if eggs:
            _choose_part(self_mode=True)
        else:
            _shoot_here(6, 0)
    elif modes.group_sex():
        _choose_target()
        _choose_part()
    elif eggs or normal_config.system_setting.base_setting[3]:
        _choose_part()
    else:
        position = h_state.get(target_id, "insert_position")
        if position == -1:
            _choose_part()
        elif position < 20:
            _shoot_here(position, 0)
        else:
            _shoot_here(position - 20, 1)
    ui_hooks.emit_divider()


def _choose_target() -> None:
    """
    收集玩家所在场景内除自身外的角色，经 modal_hooks.ask 发起 TARGET_PROMPT_ID 提问。
    各选项以角色编号字符串为 option_id，以 "[{adv}]{name}" 为标签。
    将玩家选中角色的编号经 activity.set_target 设为玩家当前交互目标。
    Return arguments:
    None -- 无返回值
    """
    scene_path = map_handle.get_map_system_path_str_for_list(
        activity.position(0)
    )
    options = []
    for chara_id in scene_state.occupants(scene_path):
        if chara_id == 0:
            continue
        chara = identity.of(chara_id)
        options.append(
            ChoiceOption(str(chara_id), f"[{chara.adv}]{chara.name}")
        )
    prompt = ChoicePrompt(
        TARGET_PROMPT_ID, tuple(options), title=_("选择射精对象")
    )
    activity.set_target(0, int(modal_hooks.ask(prompt).selected_option_id))


def _part_can_choose(body_part_cid: int) -> bool:
    """
    判断身体部位编号是否可选。
    对 INSERTED_PARTS 中的部位，
    函数在调用时按名在 handle_premise 查找前提函数并传入 0 执行。
    上述前提全部返回假值时返回 False。
    编号为 2 时以 not_draw_flag=True 对目标调用口交指令判定。
    该判定各路径均返回三元素列表。部位 2 是否可选由随后的暴露检查决定。
    最后检查该编号是否位于忽略内裤后目标的暴露身体部位中。
    Keyword arguments:
    body_part_cid -- int，待检查的身体部位编号
    Return arguments:
    bool -- 可选返回 True，否则返回 False
    """
    premises = INSERTED_PARTS.get(body_part_cid)
    if premises is not None and not any(
        getattr(handle_premise, name)(0) for name in premises
    ):
        return False
    if body_part_cid == 2 and not instuct_judege.calculation_instuct_judege(
        0, activity.target(0), _("口交"), not_draw_flag=True
    ):
        return False
    return body_part_cid in clothing.get_exposed_body_parts(
        activity.target(0), ignore_panties=True
    )


def _choose_part(self_mode: bool = False) -> None:
    """
    构造 PART_PROMPT_ID 选项并经 modal_hooks.ask 提问，按结果执行射精并切回 IN_SCENE。
    非自身模式按配置顺序加入身体与服装选项，不可选者标为 blocked。
    随后附加场景无壳卵选项。自身模式追加 normal 选项。
    选中卵块选项时，在调用 ejaculation_flow 前经 ui_hooks.clear_buttons 清理按钮。
    Keyword arguments:
    self_mode -- bool，为真时仅列出无壳卵与照常射出选项，默认为 False
    Return arguments:
    None -- 无返回值
    """
    from Script.System.Pregnancy_System import soft_egg_handle

    options = []
    if not self_mode:
        for cid, part in game_config.config_body_part.items():
            options.append(
                ChoiceOption(
                    f"body_{cid}",
                    f"[{cid}]{part.name}",
                    "open" if _part_can_choose(cid) else "blocked",
                )
            )
        worn = wardrobe.of(activity.target(0)).cloth_wear
        for kind, cloth in game_config.config_clothing_type.items():
            options.append(
                ChoiceOption(
                    f"cloth_{kind}",
                    f"[{kind}]{cloth.name}",
                    "open" if worn[kind] else "blocked",
                )
            )
    eggs = soft_egg_handle.get_soft_eggs_in_scene(activity.position(0))
    for egg_id, egg in eggs.items():
        label = _("[卵块{0}]{1}（{2}ml）").format(
            egg_id,
            soft_egg_handle.get_soft_egg_name(egg_id),
            int(egg["semen_count"]),
        )
        options.append(ChoiceOption(f"egg_{egg_id}", label))
    if self_mode:
        options.append(ChoiceOption("normal", _("[照常射出]")))
    prompt = ChoicePrompt(
        PART_PROMPT_ID, tuple(options), title=_("选择射精部位")
    )
    kind, _sep, key = modal_hooks.ask(prompt).selected_option_id.partition("_")
    if kind == "egg":
        ui_hooks.clear_buttons()
        ejaculation_flow(-1, 0, soft_egg_id=int(key))
    elif kind == "normal":
        _shoot_here(6, 0)
    else:
        _shoot_here(int(key), 0 if kind == "body" else 1)
    ui_hooks.switch_panel(constant.Panel.IN_SCENE)


def _shoot_here(part_cid: int, part_type: int) -> None:
    """
    将玩家与当前目标的 insert_position 写为所选位置，
    再经 ui_hooks.clear_buttons 清理按钮并立即调用 ejaculation_flow。
    服装类型写入 part_cid + 20。身体类型且上一指令为深喉时，传入部位 15 执行射精。
    Keyword arguments:
    part_cid -- int，身体部位编号或服装类型编号
    part_type -- int，部位类型，0 表示身体，1 表示服装
    Return arguments:
    None -- 无返回值
    """
    target_id = activity.target(0)
    position = part_cid if part_type == 0 else part_cid + 20
    h_state.set(0, insert_position=position)
    h_state.set(target_id, insert_position=position)
    if part_type == 0 and handle_premise.handle_last_cmd_deep_throat(0):
        part_cid = 15
    ui_hooks.clear_buttons()
    ejaculation_flow(part_cid, part_type)


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
