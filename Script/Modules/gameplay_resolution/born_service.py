"""
生产与破壳结算服务（born_service）
====================================
本模块提供无界面的胎生生产与卵生破壳结算入口 resolve_born 与等待提示标识 WAIT_PROMPT_ID。
本模块不导入界面、Tk 或输入输出模块，正文提示与分隔线经 ui_hooks 输出。
resolve_born 在执行前检查选择与取名处理函数均已登记。
等待确认经 modal_hooks.ask 发起，取名经 pregnancy_hooks.ask_name 询问并做角色名校验。
second_behavior 仅在 resolve_born 内按需导入。
baby_growth_handle 仅在 _name_children 内按需导入。
延迟导入 baby_growth_handle 可避免模块加载时在游戏配置就绪前载入 education_constant。
"""

import random

from Script.Core import constant, get_text
from Script.Design import character_handle, game_time, handle_premise
from Script.Design import character, map_handle, talk
from Script.Modules.domains import abilities, activity, identity, pregnancy
from Script.Modules.domains import relations, roster
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import modal_hooks, pregnancy_hooks
from Script.Modules.gameplay_resolution import ui_hooks
from Script.Protocol.modal_prompts import ChoiceOption, ChoicePrompt

_ = get_text._
""" 文本翻译函数，指向 get_text._。 """
WAIT_PROMPT_ID = "born_wait"
""" 生产与破壳等待按钮使用的 ChoicePrompt 标识（"born_wait"）。 """


def _move_to_ward(mother_character_id: int) -> None:
    """
    将母亲与玩家（0 号角色）移至医疗部住院区（Inpatient_Department）。
    母亲已在含 Inpatient_Department 标签的场景时留在原地，否则随机选一间住院区场景移入。
    玩家不在该目标场景时一并移入。
    Keyword arguments:
    mother_character_id -- int，母亲的角色编号
    Return arguments:
    None -- 无返回值
    """
    mom_scene_str = map_handle.get_map_system_path_str_for_list(
        activity.position(mother_character_id)
    )
    if "Inpatient_Department" in constant.scene_data[mom_scene_str].scene_tag:
        target_scene_path = list(activity.position(mother_character_id))
    else:
        target_scene_path = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data["Inpatient_Department"])
        )
        map_handle.character_move_scene(
            activity.position(mother_character_id),
            target_scene_path,
            mother_character_id,
        )
    if activity.position(0) != target_scene_path:
        map_handle.character_move_scene(
            activity.position(0), target_scene_path, 0
        )


def _pick_doctor(mother_name: str) -> int:
    """
    从当前在册角色中选出接生或看护医生并返回其角色编号。
    母亲不是凯尔希且在册角色中存在名为 _("凯尔希") 的角色时直接选中该角色。
    否则从职业为 3（医疗）的在册角色中随机选取，无医疗角色时从全部在册角色中随机选取。
    Keyword arguments:
    mother_name -- str，母亲的角色名称
    Return arguments:
    int -- 选中的医生角色编号
    """
    doctor_id_list = []
    dr_k_id = 0
    doctor_id = 0
    for character_id in roster.active():
        character_data: identity.Identity = identity.of(character_id)
        if character_data.profession == 3:
            doctor_id_list.append(character_id)
        if character_data.name == _("凯尔希"):
            dr_k_id = character_id
    if mother_name == _("凯尔希") or dr_k_id == 0:
        if doctor_id_list:
            doctor_id = random.choice(doctor_id_list)
    else:
        doctor_id = dr_k_id
    if doctor_id == 0:
        doctor_id = random.choice(list(roster.active()))
    return doctor_id


def _show(text: str) -> None:
    """
    经 ui_hooks.emit_notice 按文本宽度输出等待确认的正文，随后追加一条换行提示。
    Keyword arguments:
    text -- str，要输出的正文文本
    Return arguments:
    None -- 无返回值
    """
    ui_hooks.emit_notice(text, wait=True, use_text_width=True)
    ui_hooks.emit_notice("\n")


def _wait_text(behavior_id: str, mom_name: str, egg_count: int) -> str:
    """
    按二段行为标识与孵化卵数拼装等待阶段提示文本。
    Keyword arguments:
    behavior_id -- str，二段行为标识（"born"、"egg_born" 或 "soft_egg_born"）
    mom_name -- str，母亲的角色名称
    egg_count -- int，本次孵化的卵数量（胎生时为 0）
    Return arguments:
    str -- 填入参数后的等待提示译文
    """
    if behavior_id == "soft_egg_born":
        if egg_count >= 2:
            return _(
                "\n 得知了{0}在育儿室悉心孵化的{1}颗受精卵粒即将孵化的消息后，"
                "你第一时间赶到了医疗部住院区，看着她小心翼翼地捧着那团凝胶里微微搏动的卵粒，"
                "静候新生命的到来\n"
            ).format(mom_name, egg_count)
        return _(
            "\n 得知了{0}在育儿室悉心孵化的受精卵粒即将孵化的消息后，你第一时间赶到了医疗部住院区，"
            "看着她小心翼翼地捧着那团凝胶里微微搏动的卵粒，静候新生命的到来\n"
        ).format(mom_name)
    if behavior_id == "egg_born":
        return _(
            "\n 得知了{0}在育儿室悉心孵化的卵即将破壳的消息后，你第一时间赶到了医疗部住院区，"
            "看着她小心翼翼地捧着微微颤动的卵，静候新生命的到来\n"
        ).format(mom_name)
    return _(
        "\n 得知了{0}即将生产的消息后，你第一时间来到了待产室，在短暂的陪伴后，目送着她被推入产房\n"
    ).format(mom_name)


def _arrival_text(
    behavior_id: str,
    doctor_name: str,
    mom_name: str,
    born_count: int,
    twins: bool,
) -> str:
    """
    按二段行为标识、接生或看护医生名、母亲名、出生人数与是否同卵双胞胎拼装诞生提示文本。
    Keyword arguments:
    behavior_id -- str，二段行为标识（"born"、"egg_born" 或 "soft_egg_born"）
    doctor_name -- str，接生或看护医生的角色名称
    mom_name -- str，母亲的角色名称
    born_count -- int，本次出生或孵化的孩子数量
    twins -- bool，是否为同卵双胞胎
    Return arguments:
    str -- 拼合后的诞生与起名引导提示译文
    """
    if behavior_id == "soft_egg_born" and born_count >= 2:
        head = _(
            " 在{0}的看护下，凝胶里的卵粒一颗颗地胀大、变得透亮，包裹着它们的胶质终于相继化开，"
            "{1}个小小的身影先后从凝胶中挣脱出来，此起彼伏地发出了响亮的啼哭\n"
        ).format(doctor_name, born_count)
        tail = _(
            " {0}把刚刚脱出凝胶的{1}个婴儿一一擦拭干净抱在怀里，对着你微微一笑，催促你逐个给孩子起名\n"
        ).format(mom_name, born_count)
    elif behavior_id == "soft_egg_born":
        head = _(
            " 在{0}的看护下，凝胶里那颗受精的卵粒一点点胀大、变得透亮，包裹着它的胶质终于化开，"
            "一个小小的身影从凝胶中挣脱出来，发出了响亮的啼哭\n"
        ).format(doctor_name)
        tail = _(
            " {0}把刚刚脱出凝胶的婴儿擦拭干净抱在怀里，对着你微微一笑，催促你给孩子起名\n"
        ).format(mom_name)
    elif behavior_id == "egg_born":
        head = _(
            " 在{0}的看护下，蛋壳上的裂纹越来越多，终于随着一声清脆的破裂声，"
            "一个小小的身影从蛋壳中探出头来，发出了响亮的啼哭\n"
        ).format(doctor_name)
        tail = _(
            " {0}轻轻抱起了刚刚破壳而出的婴儿，对着你微微一笑，催促你给孩子起名\n"
        ).format(mom_name)
    elif twins:
        head = _(
            " 经过了漫长的等待之后，随着响亮的哭声，{0}推开产房的门，告诉你{1}生了一对同卵双胞胎女儿，"
            "母女平安\n"
        ).format(doctor_name, mom_name)
        tail = _(
            " {0}躺在床上，怀里抱着两个一模一样的婴儿，对着你微微一笑，催促你分别给她们起名\n"
        ).format(mom_name)
    elif born_count >= 2:
        head = _(
            " 经过了漫长的等待之后，随着此起彼伏的哭声，{0}推开产房的门，告诉你{1}生了{2}个可爱的女儿，"
            "母女平安\n"
        ).format(doctor_name, mom_name, born_count)
        tail = _(
            " {0}躺在床上，怀里抱着{1}个婴儿，对着你微微一笑，催促你逐个给孩子起名\n"
        ).format(mom_name, born_count)
    else:
        head = _(
            " 经过了漫长的等待之后，随着响亮的哭声，{0}推开产房的门，告诉你{1}生了一个可爱的女儿，"
            "母女平安\n"
        ).format(doctor_name, mom_name)
        tail = _(
            " {0}躺在床上，怀里抱着婴儿，对着你微微一笑，催促你给孩子起名\n"
        ).format(mom_name)
    return head + tail


def _ask_text(born_index: int, born_count: int, twins: bool) -> str:
    """
    按当前序号、总出生人数与是否同卵双胞胎返回取名输入框的询问文本。
    Keyword arguments:
    born_index -- int，当前孩子从 0 开始的序号
    born_count -- int，本次出生或孵化的孩子总数
    twins -- bool，是否为同卵双胞胎
    Return arguments:
    str -- 传给取名回调的询问译文
    """
    if twins:
        if born_index == 0:
            return _(" 你决定给双胞胎中的姐姐取名为——")
        return _(" 你决定给双胞胎中的妹妹取名为——")
    if born_count >= 2:
        return _(" 你决定给第{0}个女儿取名为——").format(born_index + 1)
    return _(" 你决定给女儿取名为——")


def _summary_text(
    behavior_id: str, mom_name: str, names: list[str], twins: bool
) -> str:
    """
    按二段行为标识与新生儿名单返回多名孩子的汇总文本，非同卵双胞胎且不足两人时返回空串。
    Keyword arguments:
    behavior_id -- str，二段行为标识（"born"、"egg_born" 或 "soft_egg_born"）
    mom_name -- str，母亲的角色名称
    names -- list[str]，本次各新生儿的角色名称列表
    twins -- bool，是否为同卵双胞胎
    Return arguments:
    str -- 汇总提示译文，无需汇总时为空串
    """
    if twins:
        return _("\n{0}生下了一对同卵双胞胎：{1}与{2}\n").format(
            mom_name, names[0], names[1]
        )
    if behavior_id == "soft_egg_born" and len(names) >= 2:
        return _("\n{0}的{1}颗受精卵粒一同孵化了：{2}\n").format(
            mom_name, len(names), "、".join(names)
        )
    if len(names) >= 2:
        return _("\n{0}一次生下了{1}个孩子：{2}\n").format(
            mom_name, len(names), "、".join(names)
        )
    return ""


def _ask_valid_name(ask_text: str) -> str:
    """
    经 pregnancy_hooks.ask_name 询问角色名并用 character.validate_character_name 校验。
    校验未通过时经 ui_hooks.emit_notice 输出提示并重新询问，直到名称通过校验。
    取名处理函数重复返回已被拒绝的名称时抛出 ValueError。
    Keyword arguments:
    ask_text -- str，传给取名回调的询问文本
    Return arguments:
    str -- 通过角色名校验的新生儿名称
    """
    rejected: set[str] = set()
    new_name = pregnancy_hooks.ask_name(ask_text)
    while (error := character.validate_character_name(new_name)) is not None:
        if new_name in rejected:
            raise ValueError(f"name handler repeated rejected {new_name!r}")
        rejected.add(new_name)
        ui_hooks.emit_notice(error)
        new_name = pregnancy_hooks.ask_name(ask_text)
    return new_name


def _name_children(mother_id: int, born_count: int, twins: bool) -> list[str]:
    """
    经 _ask_valid_name 逐个取名并创建新生儿，写入出生时刻并输出命名提示。
    按需导入 baby_growth_handle，逐个转写胎教值并输出非空说明，全部创建后清零母亲侧。
    Keyword arguments:
    mother_id -- int，母亲的角色编号
    born_count -- int，本次出生或孵化的孩子总数
    twins -- bool，是否为同卵双胞胎
    Return arguments:
    list[str] -- 按创建顺序排列的新生儿名称列表
    """
    from Script.System.Education_System import baby_growth_handle

    pl_name = identity.of(0).name
    mom_name = identity.of(mother_id).name
    names = []
    for born_index in range(born_count):
        new_name = _ask_valid_name(_ask_text(born_index, born_count, twins))
        new_child_id = character_handle.born_new_character(mother_id, new_name)
        child_name = identity.of(new_child_id).name
        pregnancy.update(new_child_id, born_time=game_time.now())
        names.append(child_name)
        _show(
            _(
                "\n孩子的名字叫做{0}，她是{1}的第{2}个孩子，也是{3}的第{4}个孩子，请慢慢养育她长大成人吧\n"
            ).format(
                child_name,
                pl_name,
                len(relations.child_id_list(0)),
                mom_name,
                len(relations.child_id_list(mother_id)),
            )
        )
        prenatal_text = baby_growth_handle.settle_prenatal_to_child(
            mother_id, new_child_id
        )
        if prenatal_text:
            _show(prenatal_text)
    baby_growth_handle.clear_prenatal_point(mother_id)
    return names


def _settle_hatch(
    mother_id: int, egg_ids: tuple[int, ...], names: list[str]
) -> str:
    """
    执行卵生破壳结算，移除已孵化的卵、授予育儿与泌乳素质、按罩杯设乳汁上限并加妊娠经验。
    Keyword arguments:
    mother_id -- int，母亲的角色编号
    egg_ids -- tuple[int, ...]，本次孵化的卵编号元组
    names -- list[str]，本次各新生儿的角色名称列表
    Return arguments:
    str -- 破壳结算结果提示文本
    """
    mom_name = identity.of(mother_id).name
    talent = abilities.talent(mother_id)
    draw_text = "\n※※※※※※※※※\n"
    with pregnancy.editing(mother_id) as mom_preg:
        for egg_id in egg_ids:
            mom_preg.eggs.pop(egg_id, None)
    talent[24] = 1
    draw_text += _("\n{0}获得了[育儿]\n").format(mom_name)
    talent[27] = 1
    draw_text += _("\n{0}获得了[泌乳]\n").format(mom_name)
    for talent_id in [121, 122, 123, 124, 125]:
        if talent[talent_id]:
            pregnancy.set_milk_max(mother_id, 150 + (talent_id - 121) * 40)
            break
    abilities.experience(mother_id)[86] += 1
    draw_text += _("\n{0}的妊娠经验+1\n").format(mom_name)
    draw_text += _("\n{0}接下来的行动重心会以照顾{1}为主\n").format(
        mom_name, "、".join(names)
    )
    return draw_text + "\n※※※※※※※※※\n"


def _settle_birth(mother_id: int) -> str:
    """
    执行胎生生产状态结算并返回结果提示文本。
    将临盆（22）与孕肚（26）置 0、产后（23）置 1，并重置妊娠加速天数、胎数与同卵标记。
    同时累加扩张与妊娠经验，并将低于 5 级的扩张能力（9、12）提至 5 级。
    Keyword arguments:
    mother_id -- int，母亲的角色编号
    Return arguments:
    str -- 生产结算结果提示文本
    """
    mom_name = identity.of(mother_id).name
    talent = abilities.talent(mother_id)
    experience = abilities.experience(mother_id)
    ability = abilities.ability(mother_id)
    draw_text = "\n※※※※※※※※※\n"
    draw_text += _("\n{0}的生产结束了，但她仍需要在住院部休息几天\n").format(
        mom_name
    )
    talent[22] = 0
    talent[23] = 1
    draw_text += _("\n{0}从[临盆]转变为[产后]\n").format(mom_name)
    talent[26] = 0
    draw_text += _("\n{0}失去了[孕肚]\n").format(mom_name)
    pregnancy.update(
        mother_id, acceleration_days=0.0, fetus_count=0, identical_twins=False
    )
    experience[65] += 10
    experience[68] += 10
    experience[86] += 1
    draw_text += _("\n{0}的Ｖ扩张经验+10，Ｗ扩张经验+10，妊娠经验+1\n").format(
        mom_name
    )
    if ability[9] < 5:
        ability[9] = 5
        draw_text += _("\n{0}的Ｖ扩张上升至5级\n").format(mom_name)
    if ability[12] < 5:
        ability[12] = 5
        draw_text += _("\n{0}的Ｗ扩张上升至5级\n").format(mom_name)
    return draw_text + "\n※※※※※※※※※\n"


def resolve_born(mother_id: int, egg_ids: tuple[int, ...] = ()) -> None:
    """
    结算一次胎生生产或卵生破壳流程，按需导入 second_behavior。
    开始前检查选择与取名处理函数均已登记，缺任一时在移动或输出前抛出 RuntimeError。
    egg_ids 为空元组时按胎生处理，非空时孵化指定卵编号（含任一无壳卵则走无壳卵分支）。
    依次移入住院区、选定医生、输出分隔线、触发二段行为与对话、展示等待文本并发起等待提示。
    确认后展示诞生文本，经 _name_children 逐个取名建角、转写并清零胎教值，再按需展示汇总。
    破壳分支执行 _settle_hatch，胎生分支先触发产后二段行为与对话再执行 _settle_birth。
    最后输出结果提示与两次等待换行，并结算生育成就（玩家女儿追加 707）。
    Keyword arguments:
    mother_id -- int，母亲的角色编号
    egg_ids -- tuple[int, ...]，本次孵化的卵编号元组，空元组表示胎生生产
    Return arguments:
    None -- 无返回值
    """
    from Script.Design import second_behavior

    if not (modal_hooks.has_handler() and pregnancy_hooks.has_handler()):
        raise RuntimeError("born flow needs choice and name input handlers")
    mom_eggs = pregnancy.of(mother_id).eggs
    if any(mom_eggs.get(egg_id, {}).get("soft", False) for egg_id in egg_ids):
        behavior_id = "soft_egg_born"
    elif egg_ids:
        behavior_id = "egg_born"
    else:
        behavior_id = "born"
    mom_name = identity.of(mother_id).name
    _move_to_ward(mother_id)
    doctor_name = identity.of(_pick_doctor(mom_name)).name
    ui_hooks.emit_divider()
    second_behavior.character_get_second_behavior(mother_id, behavior_id)
    talk.must_show_talk_check(mother_id)
    _show(_wait_text(behavior_id, mom_name, len(egg_ids)))
    modal_hooks.ask(
        ChoicePrompt(WAIT_PROMPT_ID, (ChoiceOption("wait", _("[焦急等待]")),))
    )
    if egg_ids:
        born_count = len(egg_ids)
        twins = False
    else:
        mom_preg = pregnancy.of(mother_id)
        born_count = max(1, mom_preg.fetus_count)
        twins = bool(mom_preg.identical_twins) and born_count == 2
    _show(_arrival_text(behavior_id, doctor_name, mom_name, born_count, twins))
    names = _name_children(mother_id, born_count, twins)
    summary = _summary_text(behavior_id, mom_name, names, twins)
    if summary:
        _show(summary)
    if egg_ids:
        draw_text = _settle_hatch(mother_id, egg_ids, names)
    else:
        second_behavior.character_get_second_behavior(mother_id, "postpartum")
        talk.must_show_talk_check(mother_id)
        draw_text = _settle_birth(mother_id)
    ui_hooks.emit_notice(draw_text, wait=True, use_text_width=True)
    ui_hooks.emit_notice("\n", wait=True)
    ui_hooks.emit_notice("\n", wait=True)
    achievement_service.settle_and_notify(_("生育"))
    if handle_premise.handle_self_is_player_daughter(mother_id):
        achievement_service.settle_and_notify(_("生育"), 707)
