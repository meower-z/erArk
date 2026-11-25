"""
势力外交服务（nation_diplomacy_service）
======================================
提供势力列表与详情查询、在任外交官与候选干员查询、外交官任免、外交方针查询与设定。
update_nation_data 经 reset.repair 登记为读档时的国家矿石病感染率修补函数。
本模块不导入 Script.UI 与 Script.Settle。
"""

from dataclasses import dataclass

from Script.Config import game_config
from Script.Design import attr_calculation, game_time, handle_ability
from Script.Design import handle_premise, second_behavior, talk
from Script.Modules.domains import abilities, chara_life, country, diplomacy
from Script.Modules.domains import facility, flags, identity, location
from Script.Modules.domains import relations, roster
from Script.Modules.gameplay_resolution import roster_lifecycle_service
from Script.Modules.save_load import reset

SKILL = 40
"""外交官使用的能力编号（Ability.csv 编号 40，话术技能）。"""
DIPLOMAT_WORK = 131
"""外交官的工作类型编号。"""
VISITOR_AREA = 13
"""访客区的设施编号（Facility.csv 编号 13）。"""
RHODES = 0
"""罗德岛自身势力所属的国家编号。"""
NO_COUNTRY = -1
"""不属于任何国家的势力所使用的国家编号。"""
HIDDEN = 502
"""在势力列表中跳过的势力编号。"""


@dataclass(frozen=True, slots=True)
class NationRow:
    """势力列表中单行势力的展示数据。"""

    nation_id: int
    """势力编号。"""
    name: str
    """势力名称。"""
    reputation: float
    """保留两位小数的势力声望。"""
    reputation_level: str
    """势力声望对应的等级名称。"""
    infection_rate: float | None
    """所属国家保留三位小数的矿石病感染率，无所属国家时为 None。"""
    diplomat_name: str | None
    """所属国家在任外交官的名称，空缺时为 None。"""
    local: bool
    """国家页中所属国家是否为罗德岛当前所在国家，其他页恒为 False。"""


@dataclass(frozen=True, slots=True)
class Standing:
    """单个附属势力的名称与声望。"""

    name: str
    """附属势力名称。"""
    reputation: float
    """保留两位小数的附属势力声望。"""
    reputation_level: str
    """附属势力声望对应的等级名称。"""


@dataclass(frozen=True, slots=True)
class NationDetail:
    """势力详情中的势力基础信息、特产资源与附属势力。"""

    name: str
    """势力名称。"""
    reputation: float
    """保留两位小数的势力声望。"""
    infection_rate: float
    """所属国家保留三位小数的矿石病感染率，无记录时为 0。"""
    specialties: tuple[str, ...]
    """所属国家的特产资源名称元组。"""
    subordinates: tuple[Standing, ...]
    """附属势力及其声望的元组。"""


@dataclass(frozen=True, slots=True)
class Diplomat:
    """一名在任外交官或外交官候选干员的展示数据。"""

    character_id: int
    """角色编号。"""
    adv: int
    """角色身份记录中的剧情角色编号（Identity.adv）。"""
    name: str
    """角色名称。"""
    skill: int
    """话术技能（编号 40）等级。"""


@dataclass(frozen=True, slots=True)
class Posting:
    """一个国家在任外交官与外交方针的展示数据。"""

    diplomat: Diplomat
    """在任外交官。"""
    skill_name: str
    """话术技能（编号 40）的名称。"""
    effect: float
    """外交官能力对应的效果百分比（能力修正值的 5 倍）。"""
    policy_name: str
    """当前外交方针名称。"""


@dataclass(frozen=True, slots=True)
class Candidates:
    """指定势力所属国家的可选外交官列表。"""

    country_name: str
    """势力所属国家名称。"""
    current_id: int
    """在任外交官的角色编号，空缺时为 0。"""
    diplomats: tuple[Diplomat, ...]
    """在编干员及在任外交官中出身地或所属势力符合条件者。"""


@dataclass(frozen=True, slots=True)
class Policy:
    """一条可选外交方针的展示数据。"""

    policy_id: int
    """外交方针编号。"""
    name: str
    """外交方针名称。"""
    info: str
    """外交方针说明。"""
    selected: bool
    """是否为所属国家当前的外交方针。"""


@dataclass(frozen=True, slots=True)
class Appointment:
    """一次新外交官任命的摘要信息。"""

    name: str
    """新外交官名称。"""
    country_name: str
    """任命国家名称。"""
    local: bool
    """任命国家是否为罗德岛当前所在国家。"""


@reset.repair
def update_nation_data() -> None:
    """
    在全部势力声望与全部国家矿石病感染率均为 0 时，将各国感染率重置为配置初始值。
    缺失记录按 0 处理，函数经 reset.repair 登记为读档重置 repairs 步骤修补函数。
    Keyword arguments:
    无
    Return arguments:
    None -- 无返回值
    """
    nations = game_config.config_nation
    if any(country.reputation(nid, 0) != 0 for nid in nations):
        return
    birthplaces = game_config.config_birthplace
    if any(country.infection_rate(cid, 0) != 0 for cid in birthplaces):
        return
    for cid, data in birthplaces.items():
        country.set_infection_rate(cid, data.infect_rate)


def _country_of(nation_id: int) -> int:
    """
    查询势力配置中对应的所属国家编号。
    Keyword arguments:
    nation_id -- int，势力编号
    Return arguments:
    int -- 该势力所属的国家编号
    """
    return game_config.config_nation[nation_id].country


def _reputation(nation_id: int) -> tuple[float, str]:
    """
    读取势力的当前声望与对应声望等级名称。
    Keyword arguments:
    nation_id -- int，势力编号
    Return arguments:
    tuple[float, str] -- 保留两位小数的声望值与对应的声望等级名称
    """
    value = round(country.reputation(nation_id), 2)
    return value, attr_calculation.get_reputation_level(value)[1]


def _diplomat(character_id: int) -> Diplomat:
    """
    读取单名角色用于外交展示的身份与话术技能等级。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    Diplomat -- 该角色的外交官展示数据
    """
    data = identity.of(character_id)
    skill = abilities.ability(character_id)[SKILL]
    return Diplomat(character_id, data.adv, data.name, skill)


def list_nations(countries: bool) -> tuple[NationRow, ...]:
    """
    按分页类型列出势力列表的一页数据。
    国家页仅列出各国家主势力，其他页仅列出国家编号为 -1 的势力，跳过国家 0 与势力 502。
    Keyword arguments:
    countries -- bool，为 True 时列出国家主势力页，为 False 时列出其他势力页
    Return arguments:
    tuple[NationRow, ...] -- 该页各势力的展示数据元组
    """
    subordinate = game_config.config_nation_data_of_country_subordinate
    rows = []
    for nid, data in game_config.config_nation.items():
        if data.country == RHODES or nid == HIDDEN:
            continue
        if countries != (data.country != NO_COUNTRY):
            continue
        if countries and nid not in subordinate:
            continue
        reputation, level = _reputation(nid)
        rate = None
        if data.country != NO_COUNTRY:
            rate = round(country.infection_rate(data.country), 3)
        diplomat_id = diplomacy.of(data.country)["diplomat"]
        rows.append(
            NationRow(
                nid,
                data.name,
                reputation,
                level,
                rate,
                identity.of(diplomat_id).name if diplomat_id else None,
                countries and data.country == location.country(),
            )
        )
    return tuple(rows)


def nation_detail(nation_id: int) -> NationDetail:
    """
    查询势力详情中的名称、声望、所属国家感染率、特产资源与附属势力。
    Keyword arguments:
    nation_id -- int，势力编号
    Return arguments:
    NationDetail -- 该势力的详情展示数据
    """
    data = game_config.config_nation[nation_id]
    specialties = game_config.config_resouce_data_of_nation.get(
        data.country, []
    )
    subordinates = game_config.config_nation_data_of_country_subordinate.get(
        nation_id, []
    )
    return NationDetail(
        data.name,
        round(country.reputation(nation_id), 2),
        round(country.infection_rate(data.country, 0), 3),
        tuple(game_config.config_resouce[rid].name for rid in specialties),
        tuple(
            Standing(game_config.config_nation[cid].name, *_reputation(cid))
            for cid in subordinates
        ),
    )


def posting(nation_id: int) -> Posting | None:
    """
    查询势力所属国家的在任外交官与当前外交方针。
    Keyword arguments:
    nation_id -- int，势力编号
    Return arguments:
    Posting | None -- 在任外交官与方针展示数据，外交官空缺时返回 None
    """
    post = diplomacy.of(_country_of(nation_id))
    if not post["diplomat"]:
        return None
    diplomat = _diplomat(post["diplomat"])
    return Posting(
        diplomat,
        game_config.config_ability[SKILL].name,
        5 * handle_ability.get_ability_adjust(diplomat.skill),
        game_config.config_diplomatic_policy[post["policy"]].name,
    )


def candidates(nation_id: int) -> Candidates:
    """
    从在编干员与该国在任外交官中筛选出身地或所属势力符合条件的候选外交官。
    Keyword arguments:
    nation_id -- int，势力编号
    Return arguments:
    Candidates -- 国家名称、在任外交官编号与符合条件的候选干员列表
    """
    country_id = _country_of(nation_id)
    current_id = diplomacy.of(country_id)["diplomat"]
    chara_ids = roster.active()
    if current_id:
        chara_ids.add(current_id)
    diplomats = []
    for cid in chara_ids:
        tem = identity.of(cid).cid
        if (
            relations.birthplace(tem) != country_id
            and relations.nation(tem) != nation_id
        ):
            continue
        diplomats.append(_diplomat(cid))
    return Candidates(
        game_config.config_birthplace[country_id].name,
        current_id,
        tuple(diplomats),
    )


def assign_diplomat(character_id: int, nation_id: int) -> Appointment | None:
    """
    任免势力所属国家的外交官。
    存在在任外交官时，先解除其职位与驻在国标记，按需召回在编，再写入解除二段行为并执行对话检查。
    传入 0 或原在任外交官编号时仅解除并返回 None。
    否则写入新任命、二段行为并执行对话检查，目标国非罗德岛所在国时将其置为离线。
    Keyword arguments:
    character_id -- int，待任命的角色编号，为 0 或等于原在任外交官编号时仅解除原任
    nation_id -- int，势力编号
    Return arguments:
    Appointment | None -- 新任命的摘要信息，仅解除原任时返回 None
    """
    country_id = _country_of(nation_id)
    local = location.country() == country_id
    old_id = diplomacy.of(country_id)["diplomat"]
    if old_id:
        chara_life.work_type.set(old_id, 0)
        flags.set(old_id, in_diplomatic_visit=0)
        diplomacy.set_post(country_id, diplomat=0)
        if not handle_premise.handle_normal_7(old_id):
            roster_lifecycle_service.chara_on_line(old_id, game_time.now())
        second_behavior.character_get_second_behavior(
            old_id,
            (
                "relieved_of_diplomat_local"
                if local
                else "relieved_of_diplomat_out"
            ),
        )
        talk.must_show_talk_check(old_id)
    if not character_id or character_id == old_id:
        return None
    chara_life.work_type.set(character_id, DIPLOMAT_WORK)
    diplomacy.set_post(country_id, diplomat=character_id)
    flags.set(character_id, in_diplomatic_visit=country_id)
    second_behavior.character_get_second_behavior(
        character_id,
        (
            "appoinnted_as_diplomat_local"
            if local
            else "appoinnted_as_diplomat_out"
        ),
    )
    talk.must_show_talk_check(character_id)
    if not local:
        roster_lifecycle_service.chara_off_line(character_id)
    return Appointment(
        identity.of(character_id).name,
        game_config.config_birthplace[country_id].name,
        local,
    )


def policies(nation_id: int) -> tuple[Policy, ...]:
    """
    列出难度不超过访客区（设施编号 13）等级且不超过在任外交官话术技能（编号 40）等级的外交方针，并标出当前方针。
    Keyword arguments:
    nation_id -- int，势力编号
    Return arguments:
    tuple[Policy, ...] -- 可选外交方针的展示数据元组
    """
    post = diplomacy.of(_country_of(nation_id))
    level = facility.level(VISITOR_AREA)
    skill = abilities.ability(post["diplomat"])[SKILL]
    return tuple(
        Policy(pid, data.name, data.info, pid == post["policy"])
        for pid, data in game_config.config_diplomatic_policy.items()
        if data.difficulty <= level and data.difficulty <= skill
    )


def set_policy(nation_id: int, policy_id: int) -> None:
    """
    将势力所属国家当前的外交方针设为指定编号。
    Keyword arguments:
    nation_id -- int，势力编号
    policy_id -- int，外交方针编号
    Return arguments:
    None -- 无返回值
    """
    diplomacy.set_post(_country_of(nation_id), policy=policy_id)
