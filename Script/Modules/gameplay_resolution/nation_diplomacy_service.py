"""
势力外交服务（nation_diplomacy_service）
========================================
提供势力列表、势力详情、现任外交官与候选人查询、外交官任免、
可选外交方针查询与设定，以及读档时的国家感染率修补。
本模块顶层不导入任何界面或窗口模块，仅依赖配置、设计计算、领域数据、
在编生命周期服务与读档重置模块；干员上线与离线经由 roster_lifecycle_service
执行，仅在 assign_diplomat 内部按需导入 handle_premise、second_behavior 与 talk。
"""

from dataclasses import dataclass

from Script.Config import game_config
from Script.Design import attr_calculation, game_time, handle_ability
from Script.Modules.domains import abilities, chara_life, country, diplomacy
from Script.Modules.domains import facility, flags, identity, location
from Script.Modules.domains import relations, roster
from Script.Modules.gameplay_resolution import roster_lifecycle_service
from Script.Modules.save_load import reset

RHODES_ISLAND_COUNTRY_ID: int = 0
NO_COUNTRY_ID: int = -1
RAINBOW_SIX_NATION_ID: int = 502
DIPLOMACY_ABILITY_ID: int = 40
DIPLOMAT_EFFECT_FACTOR: int = 5
DIPLOMAT_WORK_TYPE: int = 131
VISITOR_AREA_FACILITY_ID: int = 13


@dataclass(frozen=True)
class NationRow:
    """势力列表的单行展示记录；其他势力标签页中 infection_rate 为 None，未任命外交官时 diplomat_name 为 None。"""

    nation_id: int
    name: str
    reputation: float
    reputation_level: str
    infection_rate: float | None
    diplomat_name: str | None
    is_local: bool


@dataclass(frozen=True)
class SubordinateReputation:
    """单个附属势力的名称、声望数值与声望等级名。"""

    name: str
    reputation: float
    reputation_level: str


@dataclass(frozen=True)
class NationDetail:
    """单个势力的详情记录，含国家编号、声望、感染率、特产列表与附属势力声望。"""

    country_id: int
    name: str
    reputation: float
    infection_rate: float
    specialties: tuple[str, ...]
    subordinates: tuple[SubordinateReputation, ...]


@dataclass(frozen=True)
class DiplomatSummary:
    """国家现任外交官的基本信息、话术能力加成与当前外交方针名称。"""

    adv: int
    name: str
    ability_name: str
    ability_level: int
    effect: float
    policy_name: str


@dataclass(frozen=True)
class DiplomatCandidate:
    """可任命为外交官的候选干员条目，is_current 标识其是否为现任外交官。"""

    character_id: int
    adv: int
    name: str
    ability_level: int
    is_current: bool


@dataclass(frozen=True)
class DiplomatSelectionView:
    """外交官选择视图，包含目标国家编号、国家名称与全部候选干员。"""

    country_id: int
    country_name: str
    candidates: tuple[DiplomatCandidate, ...]


@dataclass(frozen=True)
class PolicyOption:
    """单条可选外交方针记录，is_selected 标识其是否为国家当前方针。"""

    policy_id: int
    name: str
    info: str
    is_selected: bool


@dataclass(frozen=True)
class PolicySelectionView:
    """外交方针选择视图，包含目标国家编号与当前可选的全部方针。"""

    country_id: int
    options: tuple[PolicyOption, ...]


@dataclass(frozen=True)
class DiplomatAppointment:
    """新任外交官的任命结果，含外交官名、国家名与是否在罗德岛所在国任职的标记。"""

    diplomat_name: str
    country_name: str
    is_local: bool


@reset.repair
def update_nation_data() -> None:
    """读档修补：按默认值 0 读取声望与感染率，全部为 0（含国家表为空）时按配置重置各国感染率。"""
    if any(
        country.reputation(nid, 0) != 0 for nid in game_config.config_nation
    ):
        return
    if any(
        country.infection_rate(cid, 0) != 0
        for cid in game_config.config_birthplace
    ):
        return
    for cid, birthplace in game_config.config_birthplace.items():
        country.set_infection_rate(cid, birthplace.infect_rate)


def _reputation(nation_id: int) -> tuple[float, str]:
    """返回指定势力保留两位小数的声望值及其对应的声望等级名。"""
    value = round(country.reputation(nation_id), 2)
    return value, attr_calculation.get_reputation_level(value)[1]


def _diplomat_name(country_id: int) -> str | None:
    """返回指定国家现任外交官的名称，未任命外交官时返回 None。"""
    diplomat_id = diplomacy.of(country_id)["diplomat"]
    return identity.of(diplomat_id).name if diplomat_id != 0 else None


def list_nations(other: bool) -> tuple[NationRow, ...]:
    """
    列出势力列表行：other 为 False 时返回国家及附属势力页的主势力，
    为 True 时返回无所属国家的其他势力，跳过罗德岛与势力 502。
    """
    rows: list[NationRow] = []
    for nation_id, nation in game_config.config_nation.items():
        if nation.country == RHODES_ISLAND_COUNTRY_ID:
            continue
        if nation_id == RAINBOW_SIX_NATION_ID:
            continue
        if other != (nation.country == NO_COUNTRY_ID):
            continue
        if (
            not other
            and nation_id
            not in game_config.config_nation_data_of_country_subordinate
        ):
            continue
        reputation, level = _reputation(nation_id)
        rows.append(
            NationRow(
                nation_id=nation_id,
                name=nation.name,
                reputation=reputation,
                reputation_level=level,
                infection_rate=(
                    None
                    if other
                    else round(country.infection_rate(nation.country), 3)
                ),
                diplomat_name=_diplomat_name(nation.country),
                is_local=not other and nation.country == location.country(),
            )
        )
    return tuple(rows)


def get_nation_detail(nation_id: int) -> NationDetail:
    """返回指定势力的声望、感染率、特产名称与各附属势力声望详情。"""
    nation = game_config.config_nation[nation_id]
    reputation, _level = _reputation(nation_id)
    subordinates = []
    for sub_id in game_config.config_nation_data_of_country_subordinate.get(
        nation_id, []
    ):
        sub_reputation, sub_level = _reputation(sub_id)
        subordinates.append(
            SubordinateReputation(
                game_config.config_nation[sub_id].name,
                sub_reputation,
                sub_level,
            )
        )
    return NationDetail(
        country_id=nation.country,
        name=nation.name,
        reputation=reputation,
        infection_rate=round(country.infection_rate(nation.country, 0), 3),
        specialties=tuple(
            game_config.config_resouce[rid].name
            for rid in game_config.config_resouce_data_of_nation.get(
                nation.country, []
            )
        ),
        subordinates=tuple(subordinates),
    )


def get_diplomat_summary(country_id: int) -> DiplomatSummary | None:
    """返回指定国家现任外交官的话术加成与当前外交方针摘要，未任命外交官时返回 None。"""
    post = diplomacy.of(country_id)
    diplomat_id = post["diplomat"]
    if diplomat_id == 0:
        return None
    diplomat = identity.of(diplomat_id)
    level = abilities.ability(diplomat_id)[DIPLOMACY_ABILITY_ID]
    return DiplomatSummary(
        adv=diplomat.adv,
        name=diplomat.name,
        ability_name=game_config.config_ability[DIPLOMACY_ABILITY_ID].name,
        ability_level=level,
        effect=DIPLOMAT_EFFECT_FACTOR
        * handle_ability.get_ability_adjust(level),
        policy_name=game_config.config_diplomatic_policy[post["policy"]].name,
    )


def list_diplomat_candidates(nation_id: int) -> DiplomatSelectionView:
    """
    生成外交官选择视图：候选池包含在编干员与现任外交官（即使未在编），
    所有候选人均须满足出身地属于该国或所属势力为该势力的筛选条件。
    """
    country_id = game_config.config_nation[nation_id].country
    current_id = diplomacy.of(country_id)["diplomat"]
    chara_ids = roster.active()
    if current_id != 0:
        chara_ids.add(current_id)
    candidates = []
    for cid in chara_ids:
        if (
            relations.birthplace(cid) != country_id
            and relations.nation(cid) != nation_id
        ):
            continue
        chara = identity.of(cid)
        candidates.append(
            DiplomatCandidate(
                character_id=cid,
                adv=chara.adv,
                name=chara.name,
                ability_level=abilities.ability(cid)[DIPLOMACY_ABILITY_ID],
                is_current=cid == current_id,
            )
        )
    return DiplomatSelectionView(
        country_id=country_id,
        country_name=game_config.config_birthplace[country_id].name,
        candidates=tuple(candidates),
    )


def assign_diplomat(
    character_id: int, country_id: int
) -> DiplomatAppointment | None:
    """
    先解除该国现任外交官再任命 character_id 并返回任命结果；
    character_id 为 0 或与现任相同时仅解除并返回 None。
    外交官上线与离舰外派均通过 roster_lifecycle_service 执行。
    """
    from Script.Design import handle_premise, second_behavior, talk

    old_id = diplomacy.of(country_id)["diplomat"]
    if old_id != 0:
        chara_life.work_type.set(old_id, 0)
        flags.set(old_id, in_diplomatic_visit=0)
        diplomacy.set_post(country_id, diplomat=0)
        if not handle_premise.handle_normal_7(old_id):
            roster_lifecycle_service.chara_on_line(old_id, game_time.now())
        second_behavior.character_get_second_behavior(
            old_id,
            (
                "relieved_of_diplomat_local"
                if location.country() == country_id
                else "relieved_of_diplomat_out"
            ),
        )
        talk.must_show_talk_check(old_id)
    if character_id == 0 or character_id == old_id:
        return None
    name = identity.of(character_id).name
    chara_life.work_type.set(character_id, DIPLOMAT_WORK_TYPE)
    diplomacy.set_post(country_id, diplomat=character_id)
    flags.set(character_id, in_diplomatic_visit=country_id)
    is_local = location.country() == country_id
    second_behavior.character_get_second_behavior(
        character_id,
        (
            "appoinnted_as_diplomat_local"
            if is_local
            else "appoinnted_as_diplomat_out"
        ),
    )
    talk.must_show_talk_check(character_id)
    if not is_local:
        roster_lifecycle_service.chara_off_line(character_id)
    return DiplomatAppointment(
        diplomat_name=name,
        country_name=game_config.config_birthplace[country_id].name,
        is_local=is_local,
    )


def list_available_policies(nation_id: int) -> PolicySelectionView:
    """列出难度均不超过访客区等级与现任外交官话术等级的外交方针，并标记当前已选方针。"""
    country_id = game_config.config_nation[nation_id].country
    post = diplomacy.of(country_id)
    level = facility.level(VISITOR_AREA_FACILITY_ID)
    ability = abilities.ability(post["diplomat"])[DIPLOMACY_ABILITY_ID]
    return PolicySelectionView(
        country_id=country_id,
        options=tuple(
            PolicyOption(pid, policy.name, policy.info, pid == post["policy"])
            for pid, policy in game_config.config_diplomatic_policy.items()
            if policy.difficulty <= level and policy.difficulty <= ability
        ),
    )


def set_diplomatic_policy(country_id: int, policy_id: int) -> None:
    """将指定国家的外交方针设为 policy_id。"""
    diplomacy.set_post(country_id, policy=policy_id)
