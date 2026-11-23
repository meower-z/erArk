"""
势力外交结算服务（diplomacy_service）
=====================================
提供每周外交方针结算与各国源石病感染率周结算逻辑。
本模块不直接导入界面模块，供每日结算入口调用。
结算汇总提示通过 ui_hooks.emit_notice 发出。
"""

import random
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import handle_ability
from Script.Modules.domains import abilities, country, diplomacy, location
from Script.Modules.domains import medical
from Script.Modules.gameplay_resolution import ui_hooks

_: FunctionType = get_text._
""" 翻译api """


def judge_diplomatic_policy() -> None:
    """
    结算各已派遣外交官且已定方针国家的每周外交效果。
    函数跳过外交官编号或方针编号为 0 的国家，按方针难度为外交官结算经验 80 与 82。
    函数按外交官能力 40 算出正的能力修正与随机因子，能力低于 6 时随机因子可为负。
    方针 1 与 4 调整对应国家感染率（随机因子为正时降低，为负时升高）。
    方针 2、3 与 5 调整主势力及附属势力声望（随机因子为正时提高，为负时降低）。
    最后经 ui_hooks.emit_notice 按文本宽度发出一条等待确认的全势力声望总变化提示。
    Keyword arguments:
    无
    Return arguments:
    None -- 无返回值，更新外交官经验、国家感染率与势力声望
    """

    from Script.Settle import common_default

    all_reputation: float
    all_infection_rate: float
    all_reputation, all_infection_rate = 0, 0
    for country_id in diplomacy.table():
        diplomat_chara_id = diplomacy.of(country_id)["diplomat"]
        if diplomat_chara_id == 0:
            continue
        diplomatic_policy_id = diplomacy.of(country_id)["policy"]
        if diplomatic_policy_id == 0:
            continue
        diplomatic_policy_data = game_config.config_diplomatic_policy[
            diplomatic_policy_id
        ]

        for _i in range(diplomatic_policy_data.difficulty):
            common_default.base_chara_experience_common_settle(
                diplomat_chara_id, 80
            )
            common_default.base_chara_experience_common_settle(
                diplomat_chara_id, 82
            )

        ability_adjust = handle_ability.get_ability_adjust(
            abilities.ability(diplomat_chara_id)[40]
        )
        random_just = (
            random.uniform(
                -6 + abilities.ability(diplomat_chara_id)[40],
                6 + abilities.ability(diplomat_chara_id)[40],
            )
            / 10
        )

        if diplomatic_policy_id == 1:
            down_rate = 0.01 * ability_adjust * random_just
            country.add_infection_rate(country_id, -down_rate)
            all_infection_rate += down_rate
        elif diplomatic_policy_id == 2:
            up_reputation = 0.1 * ability_adjust * random_just
            nation_cid = country_id * 10 + 1
            country.add_reputation(nation_cid, up_reputation)
            all_reputation += up_reputation
            for (
                subordinate_id
            ) in game_config.config_nation_data_of_country_subordinate[
                nation_cid
            ]:
                country.add_reputation(subordinate_id, up_reputation * 0.5)
                all_reputation += up_reputation * 0.5
        elif diplomatic_policy_id == 3:
            up_reputation = 0.1 * ability_adjust * random_just
            nation_cid = country_id * 10 + 1
            country.add_reputation(nation_cid, up_reputation)
            all_reputation += up_reputation
            for (
                subordinate_id
            ) in game_config.config_nation_data_of_country_subordinate[
                nation_cid
            ]:
                country.add_reputation(subordinate_id, up_reputation * 3)
                all_reputation += up_reputation * 3
        elif diplomatic_policy_id == 4:
            down_rate = 0.05 * ability_adjust * random_just
            country.add_infection_rate(country_id, -down_rate)
            all_infection_rate += down_rate
        elif diplomatic_policy_id == 5:
            up_reputation = 0.3 * ability_adjust * random_just
            nation_cid = country_id * 10 + 1
            country.add_reputation(nation_cid, up_reputation)
            all_reputation += up_reputation
            for (
                subordinate_id
            ) in game_config.config_nation_data_of_country_subordinate[
                nation_cid
            ]:
                country.add_reputation(subordinate_id, up_reputation)
                all_reputation += up_reputation

    all_reputation = round(all_reputation, 2)
    all_infection_rate = round(all_infection_rate, 3)
    info_text = "\n"
    info_text += _("本周全势力声望变化：{0}\n").format(all_reputation)
    ui_hooks.emit_notice(info_text, wait=True, use_text_width=True)


def settle_all_country_infection_rate() -> None:
    """
    按每周治疗加权量结算大地图各国的源石病感染率与病人系数。
    函数跳过不在大地图中的出生地，并将国家 7 的病人系数设为 0.1 后跳过其感染率计算。
    函数更新其余大地图国家的感染率（夹在 0 至 99.99）与病人系数（夹在 0.1 至 3.0），并将每周治疗加权量清零。
    函数对比并更新上周感染率总和，再经 ui_hooks.emit_notice 按文本宽度发出等待确认的统计报告。
    Keyword arguments:
    无
    Return arguments:
    None -- 无返回值，更新国家感染率、病人系数、上周总和与每周治疗加权量
    """
    weekly_weighted_treatment = medical.state().weekly_weighted_treatment
    this_week_all_country_infection_rate = 0.0
    now_country = location.country()
    now_country_change = 0.0
    count = 0
    for country_id in game_config.config_birthplace:
        if game_config.config_birthplace[country_id].inmap == 0:
            continue
        if country_id == 7:
            country.set_patient_ratio(country_id, 0.1)
            continue
        count += 1
        old_rate = country.infection_rate(country_id)
        base_times = (old_rate // 10) + 1
        base_rate = 0.5 - weekly_weighted_treatment * 0.001
        change = base_times * base_rate
        if country_id == now_country:
            now_country_change = change
        new_rate = min(max(round(old_rate + change, 3), 0), 99.99)
        country.set_infection_rate(country_id, new_rate)
        this_week_all_country_infection_rate += new_rate
        country.set_patient_ratio(country_id, min(max(new_rate / 30, 0.1), 3.0))

    with medical.editing() as m:
        m.weekly_weighted_treatment = 0
    if country.last_week_rate() != -1.0:
        total_change = (
            this_week_all_country_infection_rate - country.last_week_rate()
        )
        total_change_rate = total_change / count
    else:
        total_change_rate = 0.0
    country.set_last_week_rate(this_week_all_country_infection_rate)
    info_text = "\n"
    info_text += _("○源石病感染率统计报告：")
    info_text += _("本周各国源石病感染率平均总变化：")
    if total_change_rate != 0.0:
        info_text += f"{round(total_change_rate, 2)}%\n"
    else:
        info_text += _("暂无数据\n")
    info_text += _("当前罗德岛所在国家为{0}，本周感染率变化：{1}%\n").format(
        game_config.config_birthplace[now_country].name,
        round(now_country_change, 2),
    )
    ui_hooks.emit_notice(info_text, wait=True, use_text_width=True)
