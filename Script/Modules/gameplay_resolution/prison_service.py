"""
监禁与调教助手服务（prison_service）
====================================
提供囚犯逃脱概率计算、逃脱判定、囚犯每日结算、逃脱结果处理、角色入狱处理、空闲牢房查询与调教助手行为筛选选择。
逃脱成功与逃脱失败提示经 ui_hooks.emit_notice 发出。
本模块不直接导入界面模块，供基地每日结算、监禁调教面板、行动结算、通用结算与外勤委托系统调用。
"""

import random
from types import FunctionType

from Script.Config import game_config
from Script.Core import constant, game_type, get_text
from Script.Design import attr_calculation, basement, game_time, handle_premise
from Script.Design import map_handle, virgin_break_gate
from Script.Modules.domains import abilities, activity, body_manage, chara_life
from Script.Modules.domains import facility, flags, identity, needs, prison
from Script.Modules.domains import work
from Script.Modules.gameplay_resolution import instruct_filter, ui_hooks

_: FunctionType = get_text._
""" 翻译api """


def calculate_escape_probability(character_id: int) -> float:
    """
    计算并更新指定囚犯的逃脱概率。
    以能力 42 与能力 45 之和乘以综合系数得到原始增量，综合系数由设置 4、能力 14、能力 18、陷落等级与设施 19 效率计算。
    增量不超过 (100 - 原概率) * 0.1，截断为整数后保底为 1。
    将原概率加增量并截断到 100 后写入 prison.set_escape_probability。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    float -- 更新后的逃脱概率
    """

    ability = abilities.ability(character_id)
    combat_skill = ability[42]
    knowledge_skill = ability[45]
    total_skill = combat_skill + knowledge_skill

    coefficient = (prison.setting(4) + 1) * 0.5
    coefficient -= ability[14] * 0.1
    coefficient += ability[18] * 0.2
    now_fall = attr_calculation.get_character_fall_level(character_id)
    coefficient -= now_fall * 0.2
    coefficient /= basement.calc_facility_efficiency(19)
    add_escape_probability = total_skill * coefficient

    old_prob = prison.escape_probability(character_id)
    max_probability = (100 - old_prob) * 0.1
    add_escape_probability = int(min(add_escape_probability, max_probability))
    add_escape_probability = max(add_escape_probability, 1)

    new_prob = min(old_prob + add_escape_probability, 100)
    prison.set_escape_probability(character_id, new_prob)
    return new_prob


def judge_can_escape(character_id: int) -> tuple[bool, float, float]:
    """
    只读判定指定角色当前能否逃脱成功。
    非囚犯直接返回 (False, 0, 0)。
    无监狱长时，逃脱概率大于 30 返回 (True, 0, 0)，否则返回 (False, 0, 0)。
    有监狱长时，逃脱概率低于 min(50 + 关押区当前等级效果, 99) 返回 (False, 0, 0)。
    达到阈值后，结合逃脱概率、设置 4、能力 42、hit 与 mana 计算囚犯逃脱值，并与监狱长对抗值比较。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    tuple[bool, float, float] -- (是否逃脱成功, 囚犯逃脱值, 监狱长对抗值)
    """
    if not prison.is_prisoner(character_id):
        return False, 0, 0
    prob = prison.escape_probability(character_id)
    warden_id = work.warden()
    if warden_id == 0:
        if prob > 30:
            return True, 0, 0
        return False, 0, 0
    now_level = facility.level(19)
    facility_cid = game_config.config_facility_effect_data[_("关押区")][
        int(now_level)
    ]
    facility_effect = game_config.config_facility_effect[facility_cid].effect
    need_escape_probability = 50 + facility_effect
    need_escape_probability = min(need_escape_probability, 99)
    if prob < need_escape_probability:
        return False, 0, 0

    escape_value = prob / 100
    escape_value *= (prison.setting(4) + 1) * 0.4
    escape_value *= abilities.ability(character_id)[42]
    escape_value *= needs.of(character_id)["hit"] / 100
    escape_value *= needs.of(character_id)["mana"] / 100

    warden_value: float = abilities.ability(warden_id)[42]
    warden_value *= needs.of(warden_id)["hit"] / 100
    warden_value *= needs.of(warden_id)["mana"] / 100

    if escape_value > warden_value:
        return True, escape_value, warden_value
    return False, escape_value, warden_value


def settle_prisoners() -> None:
    """
    遍历当前全部囚犯并执行每日结算。
    对每名囚犯依次调用 calculate_escape_probability 更新逃脱概率，再调用 judge_can_escape 判断能否逃脱。
    判定可逃脱时调用 escape_success，未逃脱且新逃脱概率大于 0 时调用 escape_fail。
    Return arguments:
    None -- 无返回值
    """
    for character_id in prison.prisoner_ids():
        escape_probability = calculate_escape_probability(character_id)
        can_escape, _escape_value, _warden_value = judge_can_escape(
            character_id
        )
        if can_escape:
            escape_success(character_id)
        elif escape_probability > 0:
            escape_fail(character_id)


def escape_success(character_id: int) -> None:
    """
    处理指定囚犯的逃脱成功结果。
    经 ui_hooks.emit_notice 以等待确认、warning 样式与配置文本宽度发出逃脱成功提示。
    开启角色 escaping 标志，调用 prison.release 移出囚犯名册，使角色离线并生成追捕逃犯外勤委托。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    None -- 无返回值
    """
    from Script.Settle import default
    from Script.System.Field_Commission_System import field_commission_function

    character_data = identity.of(character_id)
    escape_text = _("\n囚犯{0}逃脱成功，请尽快派遣外勤干员进行追捕！\n").format(
        character_data.name
    )
    ui_hooks.emit_notice(
        escape_text, wait=True, style="warning", use_text_width=True
    )
    flags.set(character_id, escaping=True)
    prison.release(character_id)
    default.handle_chara_off_line(
        character_id,
        1,
        change_data=game_type.CharacterStatusChange(),
        now_time=game_time.now(),
    )
    field_commission_function.create_capture_fugitive_commission(character_id)


def escape_fail(character_id: int) -> None:
    """
    处理指定囚犯的逃脱失败结果。
    经 ui_hooks.emit_notice 以非等待确认、gold_enrod 样式与配置文本宽度发出逃脱失败提示，并将该囚犯的逃脱概率清零。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    None -- 无返回值
    """
    character_data = identity.of(character_id)
    escape_text = _("囚犯{0}逃脱失败，监狱长已经加强了对其的监视！\n").format(
        character_data.name
    )
    ui_hooks.emit_notice(
        escape_text, wait=False, style="gold_enrod", use_text_width=True
    )
    prison.set_escape_probability(character_id, 0)


def chara_become_prisoner(character_id: int) -> None:
    """
    将指定角色设为囚犯状态，不负责移动角色或使其上线。
    清除 be_bagged 与 escaping 标志，开启 imprisonment 标志，清零身体管理数据并登记入狱记录与囚犯服装。
    登记常住宿舍后将宿舍设为角色当前位置。
    按步骤提升能力 14 至 2，并按带符号陷落等级提升能力 17 至 1 及能力 18 至 1 到 3，同时触发对应二段行为。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    None -- 直接写入角色的囚犯状态与能力数据
    """
    from Script.Design import clothing, second_behavior

    ability = abilities.ability(character_id)

    flags.set(character_id, be_bagged=False)
    flags.set(character_id, imprisonment=True)
    flags.set(character_id, escaping=False)
    body_manage.replace(character_id, attr_calculation.get_body_manage_zero())
    prison.imprison(character_id, game_time.now(), 0)
    clothing.handle_prisoner_clothing(character_id)
    from Script.System.Dormitory_System import common as dormitory_common

    dormitory_common.register_permanent_dormitory(character_id)
    chara_life.dormitory.set(
        character_id,
        map_handle.get_map_system_path_str_for_list(
            activity.position(character_id)
        ),
    )
    target_fall = attr_calculation.get_character_fall_level(
        character_id, minus_flag=True
    )
    if ability[14] <= 0:
        ability[14] = 1
        second_behavior.character_get_second_behavior(
            character_id, "yield_mark_1"
        )
    if ability[14] <= 1:
        ability[14] = 2
        second_behavior.character_get_second_behavior(
            character_id, "yield_mark_2"
        )
    if ability[17] <= 0 and target_fall >= -2:
        ability[17] = 1
        second_behavior.character_get_second_behavior(
            character_id, "terror_mark_1"
        )
    if ability[18] <= 0 and target_fall >= -2:
        ability[18] = 1
        second_behavior.character_get_second_behavior(
            character_id, "hate_mark_1"
        )
    if ability[18] <= 1 and target_fall >= -1:
        ability[18] = 2
        second_behavior.character_get_second_behavior(
            character_id, "hate_mark_2"
        )
    if ability[18] <= 2 and target_fall >= 0:
        ability[18] = 3
        second_behavior.character_get_second_behavior(
            character_id, "hate_mark_3"
        )


def get_unused_prison_dormitory() -> str:
    """
    查找首个未被当前囚犯占用的牢房名称。
    按牢1至牢8的顺序检查，任意囚犯的宿舍字符串包含某牢房名即视为已占用。
    Return arguments:
    str -- 首个空闲牢房名称，八间均已占用时返回空字符串
    """
    all_dormitories = ["牢1", "牢2", "牢3", "牢4", "牢5", "牢6", "牢7", "牢8"]

    occupied_dorms = set()
    for prisoner_id in prison.prisoner_ids():
        dorm = chara_life.dormitory(prisoner_id)
        for d in all_dormitories:
            if d in dorm:
                occupied_dorms.add(d)

    for dorm in all_dormitories:
        if dorm not in occupied_dorms:
            return dorm
    return ""


def get_all_can_use_behavior_id_for_sex_assistant(
    select_part: str = "", not_selet_part: str = ""
) -> list[str]:
    """
    筛选调教助手当前可用的行为编号列表。
    汇总配置中口、手、道具三组行为编号并经集合去重，保留存在对应指令、通过指令筛选且触发方不为 pl 的条目。
    指定 select_part 或 not_selet_part 时按标签过滤，并排除调教助手禁止列表中的编号。
    玩家存在交互对象时，同时排除 virgin_break_gate.takes_kept_virginity 拦截的编号。
    Keyword arguments:
    select_part -- str，要求包含的部位标签，空字符串表示不限
    not_selet_part -- str，要求排除的部位标签，空字符串表示不限
    Return arguments:
    list[str] -- 符合条件的行为编号列表，顺序由集合去重决定
    """
    behavior_id_list = []
    behavior_id_list.extend(
        game_config.config_behavior_id_list_of_group_sex_body_part["口"]
    )
    behavior_id_list.extend(
        game_config.config_behavior_id_list_of_group_sex_body_part["手"]
    )
    behavior_id_list.extend(
        game_config.config_behavior_id_list_of_group_sex_body_part["道具"]
    )
    behavior_id_list = list(set(behavior_id_list))
    now_premise_data: dict[str, float] = {}
    new_behavior_id_list = []
    for behavior_id in behavior_id_list:
        if behavior_id in constant.behavior_id_to_instruct_id:
            instruct_id = constant.behavior_id_to_instruct_id[behavior_id]
            filter_judge, now_premise_data = (
                instruct_filter.judge_single_instruct_filter(
                    instruct_id,
                    now_premise_data,
                    constant.InstructType.SEX,
                    use_type_filter_flag=False,
                    skip_h_judge=True,
                )
            )
            if filter_judge:
                behavior_data = game_config.config_behavior[behavior_id]
                behavior_tag_list: str | list[str] = behavior_data.tag
                behavior_tag_list = behavior_data.tag.split("|")
                if behavior_data.trigger == "pl":
                    continue
                if select_part != "" and select_part not in behavior_tag_list:
                    continue
                if not_selet_part != "" and not_selet_part in behavior_tag_list:
                    continue
                if select_part != "" or not_selet_part != "":
                    if behavior_id in prison.assistant_ban_behaviors():
                        continue
                if activity.target(0) != 0:
                    target_character_data = identity.of(activity.target(0))
                    if virgin_break_gate.takes_kept_virginity(
                        behavior_tag_list,
                        abilities.talent(target_character_data.cid),
                    ):
                        continue

                new_behavior_id_list.append(behavior_id)
    return new_behavior_id_list


def get_behavior_id_of_sex_assistant() -> str:
    """
    为调教助手选择本次执行的行为编号。
    助手关闭、设置 13 为 0 且交互对象非囚犯，或监狱长未处于正常状态 6 或被束缚时返回 "0"。
    设置 12 为 3 且指定行为列表非空时从中随机抽取。
    否则读取玩家当前行为标签中按 U、W、V、A、C、B、N 顺序首个命中的部位，按设置 12 的模式 1 或 2 筛选候选。
    随机抽取前先对候选列表排序，使同一随机状态不受集合去重顺序影响而选出同一编号。
    Return arguments:
    str -- 选中的行为编号，不满足条件或无候选时返回 "0"
    """
    if handle_premise.handle_sex_assistant_off(0):
        return "0"
    if prison.setting(13) == 0 and handle_premise.handle_t_imprisonment_0(0):
        return "0"
    warden_id = work.warden()
    if not handle_premise.handle_normal_6(
        warden_id
    ) or handle_premise.handle_self_now_bondage(warden_id):
        return "0"
    behaviors = prison.assistant_behaviors()
    if handle_premise.handle_sex_assistant_3(0) and behaviors:
        return random.choice(behaviors)
    behavior_id = activity.behavior(0).behavior_id
    if behavior_id in game_config.config_behavior:
        state_data = game_config.config_behavior[behavior_id]
        part_str_list = ["U", "W", "V", "A", "C", "B", "N"]
        now_part = ""
        for part_str in part_str_list:
            if part_str in state_data.tag:
                now_part = part_str
                break
        if now_part == "":
            return "0"
        if handle_premise.handle_sex_assistant_1(0):
            new_behavior_id_list = (
                get_all_can_use_behavior_id_for_sex_assistant(
                    select_part=now_part
                )
            )
            if len(new_behavior_id_list) > 0:
                behavior_id = random.choice(sorted(new_behavior_id_list))
                return behavior_id
        elif handle_premise.handle_sex_assistant_2(0):
            new_behavior_id_list = (
                get_all_can_use_behavior_id_for_sex_assistant(
                    not_selet_part=now_part
                )
            )
            if len(new_behavior_id_list) > 0:
                behavior_id = random.choice(sorted(new_behavior_id_list))
                return behavior_id
    return "0"
