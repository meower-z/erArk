"""
礼物面板纯规则服务（gift_service）
==================================
本模块提供礼物列表数据、送礼与药物可用性检查、送礼骚扰判定字符串以及可加速卵与婴儿候选查询。
本模块公开数据类 DrugToggle、GiftRow、PickOption 与 TargetPick。
本模块公开函数 gift_menu、gift_judge、gift_block_reason、drug_block_reason、egg_pick 与 baby_pick。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import game_time, handle_premise
from Script.Modules.domains import abilities, action_info, flags, identity
from Script.Modules.domains import inventory, pregnancy
from Script.System.Pregnancy_System import pregnancy_constant

_: FunctionType = get_text._
""" 翻译api """


@dataclass(frozen=True, slots=True)
class DrugToggle:
    """
    药物类礼物分组的展开与收起切换条目。
    属性 text 为展开态“▼药物类”或收起态“▶药物类”的本地化按钮文本。
    """

    text: str


@dataclass(frozen=True, slots=True)
class GiftRow:
    """
    礼物列表中的单条礼物展示数据。
    本类记录礼物编号 gift_id、完整显示文本 text 以及当前是否可点击选择标志 selectable。
    """

    gift_id: int
    text: str
    selectable: bool


@dataclass(frozen=True, slots=True)
class PickOption:
    """
    目标卵或婴儿选择列表中的单条按钮选项。
    本类记录选项标识 choice_id（卵编号或婴儿角色编号）以及按钮显示文本 text。
    """

    choice_id: int
    text: str


@dataclass(frozen=True, slots=True)
class TargetPick:
    """
    可加速卵或婴儿的候选查询结果。
    无候选时 chosen 为 None 且 options 为空元组，仅有一项候选时 chosen 为该编号且 options 为空元组，
    多项候选时 chosen 为 None 且 options 按候选顺序列出各 PickOption。
    """

    chosen: int | None
    options: tuple[PickOption, ...]


def gift_menu(show_drug: bool) -> tuple[DrugToggle | GiftRow, ...]:
    """
    按礼物配置顺序组装礼物面板的展示条目。
    在礼物编号 21 前插入药物分组切换项，并在未展开时跳过类型为 11 的药物礼物。
    未实装或玩家（角色 0）持有数量不大于 0 的礼物会追加对应后缀并标记为不可选。
    Keyword arguments:
    show_drug -- bool，是否展开药物类礼物分组
    Return arguments:
    tuple[DrugToggle | GiftRow, ...] -- 按配置顺序排列的切换项与礼物行元组
    """
    entries: list[DrugToggle | GiftRow] = []
    for gift_id, gift_data in game_config.config_gift_items.items():
        if gift_id == 21:
            entries.append(
                DrugToggle(_("▼药物类") if show_drug else _("▶药物类"))
            )
        if gift_data.type == 11 and not show_drug:
            continue
        item_id = gift_data.item_id
        item_data = game_config.config_item[item_id]
        gift_id_text = str(gift_id).rjust(2, "0")
        selectable = True
        if gift_data.todo == 1:
            text = f"[{gift_id_text}]{gift_data.info}" + _("(未实装)")
            selectable = False
        else:
            text = f"[{gift_id_text}]{item_data.name}：{item_data.info}"
        if inventory.items(0)[item_id] <= 0:
            text += _("(未拥有)")
            selectable = False
        entries.append(GiftRow(gift_id, text, selectable))
    return tuple(entries)


def gift_judge(gift_id: int) -> str:
    """
    根据礼物配置中的礼物类型返回送礼指令使用的骚扰判定文本。
    类型 11 返回“初级骚扰”，类型 13 返回“严重骚扰”，其余类型返回空字符串。
    Keyword arguments:
    gift_id -- int，礼物编号
    Return arguments:
    str -- 供送礼结算使用的本地化判定文本或空字符串
    """
    gift_type = game_config.config_gift_items[gift_id].type
    if gift_type == 11:
        return _("初级骚扰")
    if gift_type == 13:
        return _("严重骚扰")
    return ""


def gift_block_reason(gift_id: int, target: identity.Identity) -> str | None:
    """
    检查指定礼物当前是否被阻止赠送给目标角色。
    类型为 11 时委托 drug_block_reason，类型 3 检查当日是否已赠好感礼物，类型 2 检查反发刻印、生气状态与负面状态总值，
    类型 13 检查目标是否已持有玩家的阴茎倒模，其余类型直接放行。
    Keyword arguments:
    gift_id -- int，礼物编号
    target -- identity.Identity，目标角色身份视图
    Return arguments:
    str | None -- 阻止赠送时的本地化提示文本，允许赠送时返回 None
    """
    from Script.Design import second_behavior

    gift_type = game_config.config_gift_items[gift_id].type
    name = target.name
    if gift_type == 11:
        return drug_block_reason(gift_id, target)
    if gift_type == 3:
        days_diff = game_time.count_day_for_datetime(
            action_info.get(target.cid, "last_gift_time"), game_time.now()
        )
        if days_diff <= 0:
            return _("\n  {0}今天已经收过好感礼物了，不能重复赠送\n").format(
                name
            )
    elif gift_type == 2:
        hate_count, _hate_count_text = (
            second_behavior.get_now_state_all_value_and_text_from_mark_up_data(
                51, target.cid
            )
        )
        if abilities.ability(target.cid)[18] >= 2:
            return _(
                "\n  {0}的反发刻印大于等于2级，道歉礼物无效，需要先降低到1级\n"
            ).format(name)
        if abilities.ability(target.cid)[18] == 0 and not flags.get(
            target.cid, "angry_with_player"
        ):
            return _("\n  {0}没有生气，不需要赠送道歉礼物\n").format(name)
        if hate_count >= 10000:
            return _(
                "\n  {0}的反感、恐怖、苦痛等负面状态值过高，无法赠送道歉礼物，需要先降低负面状态值\n"
            ).format(name)
    elif gift_type == 13:
        if handle_premise.handle_have_penis_mold(target.cid):
            return _("\n  {0}已经拥有了你的阴茎倒模，不能重复赠送\n").format(
                name
            )
    return None


def drug_block_reason(drug_id: int, target: identity.Identity) -> str | None:
    """
    检查指定药物当前是否对目标角色不可用并返回阻止原因。
    覆盖体型药 21 至 28、泌乳与停乳药 33 与 34、妊娠与孵化加速药 35 与 36、假孕与终止药 37 与 38、
    成长加速药 39 以及成长停滞与继续药 40 与 41，未匹配的编号返回 None。
    Keyword arguments:
    drug_id -- int，药物礼物编号
    target -- identity.Identity，目标角色身份视图
    Return arguments:
    str | None -- 不可用时的本地化提示文本，可用或未匹配时返回 None
    """
    from Script.System.Pregnancy_System import egg_handle, pregnancy_handle

    cid = target.cid
    name = target.name
    talent = abilities.talent(cid)
    if drug_id == 21 and talent[125]:
        return _("\n  {0}已经是最大的【爆乳】了，无法使用丰胸药\n").format(name)
    if drug_id == 22 and talent[121]:
        return _("\n  {0}已经是最小的【绝壁】了，无法使用缩胸药\n").format(name)
    if drug_id == 23 and talent[128]:
        return _("\n  {0}已经是最大的【巨臀】了，无法使用丰臀药\n").format(name)
    if drug_id == 24 and talent[126]:
        return _("\n  {0}已经是最小的【小臀】了，无法使用缩臀药\n").format(name)
    if drug_id == 25 and talent[130]:
        return _("\n  {0}已经是【肉腿】了，无法使用丰腿药\n").format(name)
    if drug_id == 26 and talent[129]:
        return _("\n  {0}已经是【细腿】了，无法使用瘦腿药\n").format(name)
    if drug_id == 27 and talent[132]:
        return _("\n  {0}已经是【长足】了，无法使用丰足药\n").format(name)
    if drug_id == 28 and talent[131]:
        return _("\n  {0}已经是【小足】了，无法使用瘦足药\n").format(name)
    if drug_id == 33 and handle_premise.handle_lactation_1(cid):
        return _("\n  {0}已经在【泌乳】了，无法使用泌乳药\n").format(name)
    if drug_id == 34 and not handle_premise.handle_lactation_1(cid):
        return _("\n  {0}没有在【泌乳】，无法使用停乳药\n").format(name)
    if drug_id == 35:
        if not (
            handle_premise.handle_fertilization_1(cid)
            or handle_premise.handle_pregnancy_1(cid)
        ):
            return _(
                "\n  {0}没有处于受精或妊娠状态，无法使用妊娠加速药\n"
            ).format(name)
        if not egg_handle.is_viviparous(cid):
            return _("\n  {0}的种族不是胎生，无法使用妊娠加速药\n").format(name)
        if pregnancy_handle.get_pregnancy_acceleration_amount(cid) <= 0:
            return _(
                "\n  {0}的孕期已经加速到极限了，无法继续使用妊娠加速药\n"
            ).format(name)
    if drug_id == 36:
        if not handle_premise.handle_in_nursery(0):
            return _("\n  只能在育儿室使用孵化加速药\n")
        if not len(egg_handle.get_hatching_eggs(cid)):
            return _("\n  {0}没有正在孵化中的卵，无法使用孵化加速药\n").format(
                name
            )
        if not len(egg_handle.get_accelerable_hatching_eggs(cid)):
            return _(
                "\n  {0}的卵都已经加速到极限了，无法继续使用孵化加速药\n"
            ).format(name)
    if drug_id == 37:
        if not egg_handle.is_viviparous(cid):
            return _("\n  {0}的种族不是胎生，无法使用假孕药\n").format(name)
        if any(
            premise(cid)
            for premise in (
                handle_premise.handle_fertilization_1,
                handle_premise.handle_pregnancy_1,
                handle_premise.handle_parturient_1,
                handle_premise.handle_postpartum_1,
                handle_premise.handle_rearing_1,
                handle_premise.handle_fake_inflation_1,
                handle_premise.handle_inflation_1,
            )
        ):
            return _("\n  {0}正处于怀孕相关状态中，无法使用假孕药\n").format(
                name
            )
    if drug_id == 38 and not handle_premise.handle_fake_inflation_1(cid):
        return _("\n  {0}没有处于假孕状态，不需要使用假孕终止药\n").format(name)
    if drug_id == 39:
        if pregnancy_handle.is_growth_drug_self_target(cid):
            if pregnancy_handle.get_child_growth_acceleration_amount(cid) <= 0:
                return _(
                    "\n  {0}已经快要成长到下一阶段了，无法使用成长加速药\n"
                ).format(name)
            return None
        if not handle_premise.handle_in_nursery(0):
            return _("\n  只能在育儿室对母亲使用成长加速药\n")
        if not len(pregnancy_handle.get_baby_id_list(cid)):
            return _(
                "\n  {0}没有正在婴儿期的孩子，无法使用成长加速药\n"
            ).format(name)
        if not len(pregnancy_handle.get_accelerable_babies(cid)):
            return _(
                "\n  {0}的孩子都已经快要长成幼女了，无法使用成长加速药\n"
            ).format(name)
    if drug_id == 40:
        if not handle_premise.handle_self_is_player_daughter(cid):
            return _("\n  {0}不是博士的女儿，无法使用成长停滞药\n").format(name)
        if not (
            handle_premise.handle_self_is_child(cid)
            or handle_premise.handle_self_is_loli(cid)
        ):
            return _(
                "\n  {0}不处于幼女或学员阶段，无法使用成长停滞药\n"
            ).format(name)
        if handle_premise.handle_growth_stop_1(cid):
            return _(
                "\n  {0}已经处于【成长停滞】状态了，无法重复使用成长停滞药\n"
            ).format(name)
    if drug_id == 41:
        if not handle_premise.handle_self_is_player_daughter(cid):
            return _("\n  {0}不是博士的女儿，无法使用成长继续药\n").format(name)
        if not (
            handle_premise.handle_self_is_child(cid)
            or handle_premise.handle_self_is_loli(cid)
        ):
            return _(
                "\n  {0}不处于幼女或学员阶段，无法使用成长继续药\n"
            ).format(name)
        if not handle_premise.handle_growth_stop_1(cid):
            return _(
                "\n  {0}没有处于【成长停滞】状态，不需要使用成长继续药\n"
            ).format(name)
    return None


def egg_pick(target_id: int) -> TargetPick:
    """
    查询目标角色名下可加速的孵化中卵并组装候选结果。
    候选数为 0 或 1 时直接填入 chosen 且不构建按钮文本，
    候选数为 2 及以上时按卵序生成含孵化天数、已加速时长与预计破壳日期的选项元组。
    Keyword arguments:
    target_id -- int，目标角色编号
    Return arguments:
    TargetPick -- 卵候选查询结果
    """
    from Script.System.Pregnancy_System import egg_handle

    eggs = egg_handle.get_accelerable_hatching_eggs(target_id)
    if len(eggs) <= 1:
        return TargetPick(next(iter(eggs), None), ())
    options = []
    for egg_id, egg_data in eggs.items():
        hatch_day = egg_handle.get_hatch_day(egg_data)
        acc_day = int(egg_data.get("acceleration_days", 0))
        born_time = game_time.get_predict_date(
            pregnancy_constant.HATCH_TOTAL_DAY - acc_day, egg_data["lay_time"]
        )
        text = _("[{0}号卵] 孵化第{1}天（已加速{2}，预计{3}破壳）").format(
            egg_id,
            hatch_day,
            game_time.get_duration_text(acc_day),
            pregnancy_constant.format_season_date(born_time),
        )
        options.append(PickOption(egg_id, text))
    return TargetPick(None, tuple(options))


def baby_pick(target_id: int) -> TargetPick:
    """
    查询目标角色名下可加速成长的婴儿并组装候选结果。
    候选数为 0 或 1 时直接填入 chosen 且不构建按钮文本，
    候选数为 2 及以上时按候选顺序生成含姓名、出生天数、已加速时长与预计成长日期的选项元组。
    Keyword arguments:
    target_id -- int，母亲角色编号
    Return arguments:
    TargetPick -- 婴儿候选查询结果
    """
    from Script.System.Pregnancy_System import pregnancy_handle

    babies = pregnancy_handle.get_accelerable_babies(target_id)
    if len(babies) <= 1:
        return TargetPick(babies[0] if babies else None, ())
    options = []
    for child_id in babies:
        grow_day = pregnancy_handle.get_child_grow_day(child_id)
        child_preg = pregnancy.of(child_id)
        acc_day = int(child_preg.growth_acceleration_days)
        grow_time = game_time.get_predict_date(
            pregnancy_constant.REARING_COMPLETE_DAY - acc_day,
            child_preg.born_time,
        )
        text = _("[{0}] 出生第{1}天（已加速{2}，预计{3}成长为幼女）").format(
            identity.of(child_id).name,
            grow_day,
            game_time.get_duration_text(acc_day),
            pregnancy_constant.format_season_date(grow_time),
        )
        options.append(PickOption(child_id, text))
    return TargetPick(None, tuple(options))
