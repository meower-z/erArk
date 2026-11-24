"""
招募服务（recruit_service）
===========================
提供招募线读档修复、招募条件检查、待确认干员入职、可招募角色筛选、招募结算与招募线效率计算。
另提供招募线候选预览、可选策略列表、策略写入、专员表格单元格、副专员排序与主专员任命。
提示文本经 ui_hooks.emit_notice 发出，成就结算经 achievement_service.settle_and_notify 派发。
repair_recruit_lines 经 reset.repair 登记为读档修复函数。
本模块不直接导入界面模块，供招募面板、访客服务、访客邀请面板、指令系统、行为结算与外勤委托系统调用。
"""

import random
from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config, normal_config
from Script.Core import constant, get_text
from Script.Design import attr_calculation, basement, handle_ability
from Script.Design import handle_premise, handle_talent
from Script.Modules.domains import abilities, diplomacy, facility, flags
from Script.Modules.domains import identity, location, npc_template, recruit
from Script.Modules.domains import relations, roster, visitor, work
from Script.Modules.gameplay_resolution import achievement_service, ui_hooks
from Script.Modules.save_load import reset

_: FunctionType = get_text._
""" 翻译api """

_TRAITS: tuple[tuple[str, Callable[[int], int]], ...] = (
    ("config_nation", relations.nation),
    ("config_birthplace", relations.birthplace),
    ("config_profession", lambda cid: identity.of(cid).profession),
    ("config_race", lambda cid: identity.of(cid).race),
    ("config_talent", handle_talent.have_age_talent),
    ("config_talent", handle_talent.have_chest_talent),
    ("config_talent", handle_talent.have_hip_talent),
)
""" 按策略 2 至 8 顺序排列的七项特征配置表名与取值函数对（势力、出生地、职业、种族、年龄、胸部与臀部）。 """


@dataclass(frozen=True, slots=True)
class StrategyOption:
    """单条可选招募策略的只读数据项，包含策略编号 cid 与完整按钮文本 text。"""

    cid: int
    text: str


@reset.repair
def repair_recruit_lines() -> None:
    """
    读档时修复待确认干员集合与招募线进度。
    移除待确认集合中的编号 0 与不存在的角色，并将策略为 11 的招募线进度清零。
    Return arguments:
    None -- 无返回值
    """
    recruit.set_pending(
        cid for cid in recruit.pending() if cid and identity.exists(cid)
    )
    lines = recruit.lines()
    for line in lines.values():
        if line["strategy"] == 11:
            line["progress"] = 0
    recruit.put_lines(lines)


def can_recruit() -> bool:
    """
    检查当前是否可以接收待确认干员，不写入游戏状态。
    宿舍已满时经 ui_hooks.emit_notice 以等待确认、gold_enrod 样式与配置文本宽度发出宿舍不足提示。
    宿舍有空位时按待确认集合是否非空返回布尔值。
    Return arguments:
    bool -- 宿舍有空位且存在待确认干员时返回 True，否则返回 False
    """
    if roster.count() >= facility.people_max():
        ui_hooks.emit_notice(
            _("\n\n   ※ 空余宿舍不足，无法招募 ※\n\n"),
            wait=True,
            style="gold_enrod",
            use_text_width=True,
        )
        return False
    return bool(recruit.pending())


def recruit_new_chara() -> bool:
    """
    接收一名待确认干员加入罗德岛。
    宿舍已满时经 ui_hooks.emit_notice 以等待确认、gold_enrod 样式与配置文本宽度发出宿舍不足提示。
    有待确认干员时任意弹出一名建档入编，发出同类样式招募成功提示，再结算招募类型成就。
    Return arguments:
    bool -- 成功接收干员返回 True，宿舍已满或无待确认返回 False（无待确认时不发提示）
    """
    from Script.Design import character_handle

    notice_text = ""

    if roster.count() >= facility.people_max():
        notice_text += _("\n\n   ※ 空余宿舍不足，无法招募 ※\n\n")
        ui_hooks.emit_notice(
            notice_text, wait=True, style="gold_enrod", use_text_width=True
        )
        return False

    elif pending := recruit.pending():
        new_chara_id = pending.pop()
        recruit.set_pending(pending)
        character_handle.get_new_character(new_chara_id)
        character_data = identity.of(new_chara_id)
        notice_text += _("\n\n   ※ 成功招募了{0} ※\n\n").format(
            character_data.name
        )
        ui_hooks.emit_notice(
            notice_text, wait=True, style="gold_enrod", use_text_width=True
        )
        achievement_service.settle_and_notify(_("招募"))
        return True
    else:
        return False


def find_recruitable_npc() -> list[int]:
    """
    按模板表顺序筛选当前可招募的角色编号列表。
    排除玩家、在编与待确认角色、女儿或 AdvNpc 大于 9000 的模板、不存在角色、现役访客与在任外交官。
    同时排除未通过 handle_normal_7 校验、列入禁用名单及 base_setting[7] 开启时被禁用的角色。
    Return arguments:
    list[int] -- 符合条件的可招募角色编号列表，按 npc_template.table() 遍历顺序排列
    """

    recruitable_npc_id_list = []

    diplomat_id_set = set()
    for post in diplomacy.table().values():
        if post["diplomat"]:
            diplomat_id_set.add(post["diplomat"])
    pending = recruit.pending()

    for adv_id, tem_data in npc_template.table().items():
        chara_id = adv_id
        if chara_id == 0:
            continue
        if roster.has(chara_id):
            continue
        if chara_id in pending:
            continue
        if tem_data.Mother_id != 0 or tem_data.AdvNpc > 9000:
            continue
        if not identity.exists(chara_id):
            continue
        if flags.get(chara_id, "vistor") == 1:
            continue
        if not handle_premise.handle_normal_7(chara_id):
            continue
        if chara_id in diplomat_id_set:
            continue
        if identity.of(chara_id).adv in constant.ban_NPC_adv_set:
            continue
        if normal_config.system_setting.base_setting[7]:
            if roster.is_forbidden(chara_id):
                continue
        recruitable_npc_id_list.append(chara_id)

    return recruitable_npc_id_list


def update_recruit() -> None:
    """
    结算进度满 100 的招募线，清零进度后按策略 0 至 8 筛选候选，提示经 ui_hooks.emit_notice 发出。
    有候选时随机抽一名加入待确认，命中受邀访客则清空邀请，发出等待确认、配置文本宽度的 gold_enrod 提示。
    无候选时发出等待确认、配置文本宽度的 warning 样式失败提示，并将该线策略设为 11。
    Return arguments:
    None -- 无返回值
    """

    for recruit_line_id, line in recruit.lines().items():

        if line["progress"] >= 100:
            recruit.set_line(recruit_line_id, progress=0)

            recruitment_strategy = line["strategy"]

            recruitable_npc_id_list = find_recruitable_npc()
            wait_id_list = []
            line_main_chara_id = line["main"]
            line_main_chara_data = identity.of(line_main_chara_id)
            for chara_id in recruitable_npc_id_list:
                if (
                    chara_id == 0
                    and recruitment_strategy != 0
                    and recruitment_strategy != 1
                ):
                    break

                if recruitment_strategy == 0:
                    character_data = identity.of(chara_id)
                    if (
                        relations.birthplace(character_data.cid)
                        != location.country()
                    ):
                        continue
                    wait_id_list.append(chara_id)
                elif recruitment_strategy == 1:
                    wait_id_list.append(chara_id)
                elif recruitment_strategy == 2:
                    character_data = identity.of(chara_id)
                    if relations.nation(character_data.cid) != relations.nation(
                        line_main_chara_id
                    ):
                        continue
                    wait_id_list.append(chara_id)
                elif recruitment_strategy == 3:
                    character_data = identity.of(chara_id)
                    if relations.birthplace(
                        character_data.cid
                    ) != relations.birthplace(line_main_chara_id):
                        continue
                    wait_id_list.append(chara_id)
                elif recruitment_strategy == 4:
                    character_data = identity.of(chara_id)
                    if (
                        character_data.profession
                        != line_main_chara_data.profession
                    ):
                        continue
                    wait_id_list.append(chara_id)
                elif recruitment_strategy == 5:
                    character_data = identity.of(chara_id)
                    if character_data.race != line_main_chara_data.race:
                        continue
                    wait_id_list.append(chara_id)
                elif recruitment_strategy == 6:
                    talent = abilities.talent(chara_id)
                    line_main_chara_age_talent = handle_talent.have_age_talent(
                        line_main_chara_id
                    )
                    if talent[line_main_chara_age_talent] != 1:
                        continue
                    wait_id_list.append(chara_id)
                elif recruitment_strategy == 7:
                    talent = abilities.talent(chara_id)
                    line_main_chara_bust_talent = (
                        handle_talent.have_chest_talent(line_main_chara_id)
                    )
                    if talent[line_main_chara_bust_talent] != 1:
                        continue
                    wait_id_list.append(chara_id)
                elif recruitment_strategy == 8:
                    talent = abilities.talent(chara_id)
                    line_main_chara_hip_talent = handle_talent.have_hip_talent(
                        line_main_chara_id
                    )
                    if talent[line_main_chara_hip_talent] != 1:
                        continue
                    wait_id_list.append(chara_id)
            if len(wait_id_list):
                choice_id = random.choice(wait_id_list)
                recruit.set_pending(recruit.pending() | {choice_id})

                notice_text = _(
                    "\n\n   ※ 招募到了新的干员，请前往博士办公室确认 ※\n\n"
                )
                if choice_id == visitor.invite()[0]:
                    notice_text += _(
                        "   ※ 招募到的新干员是正在邀请的访客，已自动停止邀请 ※\n\n"
                    )
                    visitor.set_invite(0)
                ui_hooks.emit_notice(
                    notice_text,
                    wait=True,
                    style="gold_enrod",
                    use_text_width=True,
                )
            else:
                notice_text = _(
                    "\n\n   ※ 当前招募策略无可招募npc，招募失败，已自动停止招募，请调整招募策略 ※\n\n"
                )
                ui_hooks.emit_notice(
                    notice_text, wait=True, style="warning", use_text_width=True
                )
                recruit.set_line(recruit_line_id, strategy=11)


def calculate_recruit_line_efficiency(line_id: int) -> tuple[str, float]:
    """
    计算指定招募线的效率加成数值与明细文本，不写入游戏状态。
    招募线不存在、策略未知或策略为 11 时返回对应说明文本与 0.0。
    其余情况汇总主专员加成（空缺取 1.0）与非主专员人事岗位五分之一加成，乘以策略系数与设施 7 效率。
    Keyword arguments:
    line_id -- int，招募线编号
    Return arguments:
    tuple[str, float] -- (效率说明或明细文本, 效率加成数值)
    """
    lines = recruit.lines()
    if line_id not in lines:
        return _("无此招募线"), 0.0

    recruitment_strategy_id = lines[line_id]["strategy"]
    recruitment_strategy_data = game_config.config_recruitment_strategy.get(
        recruitment_strategy_id
    )
    if not recruitment_strategy_data:
        return _("未知策略"), 0.0
    if recruitment_strategy_id == 11:
        return _("已停止招募"), 0.0

    facility_effect = basement.calc_facility_efficiency(7)

    line_main_id = lines[line_id]["main"]
    main_name = (
        identity.of(line_main_id).name
        if identity.exists(line_main_id)
        else _("空缺")
    )
    main_ids = {line["main"] for line in lines.values()}
    total_bonus = 0.0
    sub_bonus = 0.0
    hr_parts_str = "["
    for chara_id in work.roster(work.HR_WORK):
        if not identity.exists(chara_id):
            continue
        if chara_id == 0:
            continue
        base_effect = 2 * handle_ability.get_ability_adjust(
            abilities.ability(chara_id).get(40, 0)
        )
        if chara_id == line_main_id:
            total_bonus += base_effect
            hr_parts_str += _("主:{0}(话术lv{1}:{2}%)").format(
                main_name,
                abilities.ability(chara_id).get(40, 0),
                round(base_effect, 1),
            )
        elif chara_id not in main_ids:
            sub_bonus += base_effect / 5
    if hr_parts_str == "[":
        hr_parts_str += _("主:空缺(基础1.0%)")
        total_bonus = 1.0
    total_bonus += sub_bonus
    hr_parts_str += _("，副:{0}%]").format(round(sub_bonus, 1))

    total_bonus *= recruitment_strategy_data.adjust
    strategy_str = _(" * 策略调整系数{0}%").format(
        int(recruitment_strategy_data.adjust * 100)
    )

    total_bonus *= facility_effect
    facility_effect_str = _("* 设施效率调整{0}%").format(
        round(facility_effect * 100, 1)
    )

    if recruitment_strategy_id == 11:
        total_bonus = 0.0
        hr_parts_str += _("，已停止招募")

    detail_str = _("当前效率加成：{0} {1} {2} = {3}%").format(
        hr_parts_str, strategy_str, facility_effect_str, round(total_bonus, 1)
    )
    return detail_str, total_bonus


def line_candidates(
    strategy_id: int, main_id: int, recruitable: list[int]
) -> list[int]:
    """
    按策略 strategy_id 与主专员 main_id 从 recruitable 依次只读筛选候选编号，返回 list[int]。
    策略 0 匹配所在国出生地，1 返回副本，2 至 8 需非零主专员并匹配同属性或素质值为 1，其余情况返回空列表。
    """
    if strategy_id == 0:
        country = location.country()
        return [c for c in recruitable if relations.birthplace(c) == country]
    if strategy_id == 1:
        return list(recruitable)
    if not 2 <= strategy_id <= 8 or not main_id:
        return []
    key = _TRAITS[strategy_id - 2][1]
    if strategy_id <= 5:
        return [c for c in recruitable if key(c) == key(main_id)]
    return [
        c for c in recruitable if abilities.talent(c).get(key(main_id)) == 1
    ]


def strategy_options(line_id: int) -> list[StrategyOption]:
    """
    只读返回招募线 line_id 在当前设施 7 等级下可选的 list[StrategyOption]，按策略配置顺序排列。
    文案含两位编号、名称、调整系数与说明，策略 0 追加所在国出生地名，策略 2 至 8 在有主专员时追加其对应特征名。
    """
    main_id = recruit.lines()[line_id]["main"]
    level = facility.level(7)
    options = []
    for cid, data in game_config.config_recruitment_strategy.items():
        if level < data.lv:
            continue
        text = f"[{str(cid).rjust(2, '0')}]"
        text += attr_calculation.pad_display_width(data.name, 24)
        text += _("(调整系数{0})").format(data.adjust) + "：" + data.introduce
        if cid == 0:
            birthplace = game_config.config_birthplace[location.country()]
            text += _("（{0}）").format(birthplace.name)
        elif 2 <= cid <= 8 and main_id != 0:
            table, key = _TRAITS[cid - 2]
            trait = getattr(game_config, table)[key(main_id)]
            text += _("（{0}）").format(trait.name)
        options.append(StrategyOption(cid, text))
    return options


def set_line_strategy(line_id: int, strategy_id: int) -> None:
    """将招募线 line_id 的策略设为 strategy_id，策略为 11 时同步将进度清零，无返回值。"""
    recruit.set_line(line_id, strategy=strategy_id)
    if strategy_id == 11:
        recruit.set_line(line_id, progress=0)


def hr_cells(chara_id: int, is_main: bool) -> tuple[str, ...]:
    """
    只读生成角色 chara_id 在专员表中职位列后的 10 个单元格元组，chara_id 为 0 时返回空缺与九个 -。
    其余依次为名字、按 is_main 计算的加成（副专员取五分之一）、话术评级与等级及七项特征名，缺配置项填 -。
    """
    if chara_id == 0:
        return (_("空缺"),) + ("-",) * 9
    name = identity.of(chara_id).name
    level = abilities.ability(chara_id).get(40, 0)
    base_effect = 2 * handle_ability.get_ability_adjust(level)
    bonus = base_effect if is_main else base_effect / 5
    traits = []
    for table, key in _TRAITS:
        config, trait_id = getattr(game_config, table), key(chara_id)
        traits.append(config[trait_id].name if trait_id in config else "-")
    grade = f"{attr_calculation.judge_grade(level)} {level}"
    return (name, f"{round(bonus, 1)}%", grade, *traits)


def sub_hr_ids() -> list[int]:
    """只读返回人事名册中排除 0 与各线主专员后的副专员列表，按话术等级降序且同级保原序。"""
    main_ids = {line["main"] for line in recruit.lines().values()}
    hr_ids = [c for c in work.roster(work.HR_WORK) if c and c not in main_ids]
    return sorted(
        hr_ids, key=lambda c: abilities.ability(c).get(40, 0), reverse=True
    )


def appoint_main_hr(line_id: int, chara_id: int) -> None:
    """当 chara_id 在人事名册内时通过 recruit.appoint 任命或撤销 line_id 的主专员，否则忽略。"""
    if chara_id in work.roster(work.HR_WORK):
        recruit.appoint(line_id, chara_id)
