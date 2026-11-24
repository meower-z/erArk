"""
源石技艺与负面刻印服务（originium_arts_service）
================================================
提供默认催眠类型读写、源石技艺消耗计算与升级条件评估、习得升级结算、
内裤重复款式优先扣减以及负面刻印降低结算。
本模块不导入界面与窗口模块，仅依赖配置与领域数据接口。
"""

from collections.abc import Sequence
from dataclasses import dataclass
from types import MappingProxyType

from Script.Config import game_config
from Script.Core.num import Num
from Script.Modules.domains import abilities, dirty, hypnosis, modes
from Script.Modules.domains import player_ability, player_collection
from Script.Modules.domains import relations, roster, status, warehouse

ORIGINITE_PRIME_RESOURCE_ID: int = 3
""" 至纯源石在基地仓库中的资源编号。 """

NEGATIVE_MARK_ABILITY_IDS: tuple[int, ...] = (15, 17, 18)
""" 支持降低的负面刻印能力编号（苦痛、反发、恐怖刻印）。 """

NEGATIVE_MARK_STATUS_MAP: MappingProxyType[int, int] = MappingProxyType(
    {15: 17, 17: 18, 18: 20}
)
""" 负面刻印能力编号到对应主状态编号的映射。 """

NEGATIVE_MARK_PANTY_COST: int = 5
""" 每次降低负面刻印需消耗的内裤收藏条数。 """

FALL_TALENT_IDS: tuple[int, ...] = (201, 202, 203, 204, 211, 212, 213, 214)
""" 任意陷落路线对应的素质编号集合。 """

DEEP_FALL_TALENT_IDS: tuple[int, ...] = (204, 214)
""" 爱侣或奴隶深度陷落对应的素质编号。 """

INTERNAL_SEMEN_PART_IDS: tuple[int, ...] = (2, 6, 7, 8, 9, 15)
""" 计入体内射精总量的身体部位编号。 """


@dataclass(frozen=True)
class ArtConditionProgress:
    """单条源石技艺特殊解锁条件的进度与满足状态。"""

    kind: str
    required_primary: int
    current_primary: Num
    required_secondary: int | None = None
    current_secondary: int | None = None
    satisfied: bool = False


@dataclass(frozen=True)
class ArtUpgradeOption:
    """源石技艺升级面板展示用的单条可获得或可升级选项数据。"""

    cid: int
    talent_id: int
    level: int
    money_cost: int
    todo: bool
    can_buy_with_prime: bool
    condition: ArtConditionProgress | None


@dataclass(frozen=True)
class LearnArtResult:
    """学习或升级源石技艺的结算结果。"""

    success: bool
    cid: int
    talent_id: int
    money_cost: int
    paid_cost: int
    insufficient_prime: bool


@dataclass(frozen=True)
class NegativeMarkReductionResult:
    """降低角色负面刻印的结算结果。"""

    success: bool
    character_id: int
    ability_id: int
    consumed_panties: int
    remaining_panties: int
    new_level: int
    reset_status_id: int | None


def get_hypnosis_type(character_id: int = 0) -> int:
    """
    读取指定角色当前的默认催眠类型编号。
    Keyword arguments:
    character_id -- int，角色编号，默认 0（玩家）
    Return arguments:
    int -- 当前默认催眠类型编号
    """
    return player_ability.get(character_id, "hypnosis_type")


def set_hypnosis_type(hypnosis_type_cid: int, character_id: int = 0) -> None:
    """
    设置指定角色的默认催眠类型编号。
    Keyword arguments:
    hypnosis_type_cid -- int，目标催眠类型编号
    character_id -- int，角色编号，默认 0（玩家）
    """
    player_ability.set(character_id, hypnosis_type=hypnosis_type_cid)


def calculate_art_cost(level: int) -> int:
    """
    按能力等级计算习得或升级源石技艺所需的至纯源石数量。
    Keyword arguments:
    level -- int，能力等级
    Return arguments:
    int -- 所需至纯源石数量（10 ** (level - 1)）
    """
    return 10 ** (level - 1)


def originite_prime_amount() -> int:
    """
    读取基地仓库当前的至纯源石库存。
    Return arguments:
    int -- 当前至纯源石数量
    """
    return warehouse.amount(ORIGINITE_PRIME_RESOURCE_ID)


def _has_any_talent(character_id: int, talent_ids: Sequence[int]) -> bool:
    """判断角色是否持有给定素质编号中的任意一项。"""
    talent = abilities.talent(character_id)
    return any(talent[tid] for tid in talent_ids)


def _progress(
    kind: str,
    req1: int,
    cur1: Num,
    req2: int | None = None,
    cur2: int | None = None,
) -> ArtConditionProgress:
    """根据主副阈值与当前值构造解锁条件进度并计算 satisfied。"""
    ok = cur1 >= req1 and (req2 is None or (cur2 is not None and cur2 >= req2))
    return ArtConditionProgress(kind, req1, cur1, req2, cur2, ok)


def evaluate_art_unlock_condition(cid: int) -> ArtConditionProgress | None:
    """
    评估指定源石技艺配置条目的免费特殊解锁条件进度，无对应规则时返回 None。
    Keyword arguments:
    cid -- int，config_talent_of_arts 中的条目编号
    Return arguments:
    ArtConditionProgress | None -- 特殊解锁条件进度，无对应规则时为 None
    """
    data = game_config.config_talent_of_arts[cid]
    tid, req1, req2 = data.talent_id, data.lv_up_value1, data.lv_up_value2
    if tid == 304:
        max_fav, max_trust = 0, 0
        for chara_id in roster.active():
            fav = relations.favorability(chara_id)[0]
            if fav > max_fav:
                max_fav = int(fav)
            trust_val = relations.trust(chara_id)
            if trust_val > max_trust:
                max_trust = int(trust_val)
        return _progress(
            "max_favorability_trust", req1, max_fav, req2, max_trust
        )
    if tid == 305:
        total_fav, fall_count = 0, 0
        for chara_id in roster.active():
            fall_count += int(_has_any_talent(chara_id, FALL_TALENT_IDS))
            total_fav += int(relations.favorability(chara_id)[0])
        return _progress(
            "total_favorability_fall", req1, total_fav, req2, fall_count
        )
    if tid == 306:
        total_fav, deep_fall = 0, 0
        for chara_id in roster.active():
            total_fav += int(relations.favorability(chara_id)[0])
            deep_fall += int(_has_any_talent(chara_id, DEEP_FALL_TALENT_IDS))
        return _progress(
            "total_favorability_deep_fall", req1, total_fav, req2, deep_fall
        )
    if tid == 307:
        panty_total = sum(
            len(items)
            for items in player_collection.get("npc_panties").values()
        )
        return _progress("panty_collection_total", req1, panty_total)
    if tid == 308:
        semen_total: Num = 0
        orgasm_exp = 0
        for chara_id in roster.active():
            body_semen = dirty.view(chara_id).body_semen
            for part_id in INTERNAL_SEMEN_PART_IDS:
                semen_total += body_semen[part_id][3]
            orgasm_exp += abilities.experience(chara_id)[20]
        return _progress(
            "internal_semen_orgasm_exp", req1, semen_total, req2, orgasm_exp
        )
    if tid == 309:
        return _progress("child_count", req1, len(relations.child_id_list(0)))
    if tid == 316:
        orgasm_exp, sex_exp = 0, 0
        for chara_id in roster.active():
            npc_exp = abilities.experience(chara_id)
            orgasm_exp += npc_exp[78]
            sex_exp += npc_exp[79]
        return _progress(
            "unconscious_sex_orgasm_exp", req1, sex_exp, req2, orgasm_exp
        )
    if tid == 317:
        time_stop_sex = abilities.experience(0)[124]
        orgasm_exp = sum(
            abilities.experience(chara_id)[78] for chara_id in roster.active()
        )
        return _progress(
            "time_stop_sex_orgasm_exp", req1, time_stop_sex, req2, orgasm_exp
        )
    if tid == 331:
        return _progress("sleep_sex_exp", req1, abilities.experience(0)[120])
    if tid in game_config.config_hypnosis_talent_of_pl:
        up_data = game_config.config_hypnosis_talent_of_pl[tid]
        now_exp = abilities.experience(0)[122]
        now_degree_sum: float = 0
        for chara_id in roster.active():
            now_degree_sum += hypnosis.degree(chara_id)
        return _progress(
            "hypnosis_exp_degree",
            up_data.pl_experience,
            now_exp,
            up_data.npc_hypnosis_degree,
            int(now_degree_sum),
        )
    return None


def list_upgradeable_arts() -> list[ArtUpgradeOption]:
    """
    查询玩家当前可获得或可升级的全部源石技艺选项。
    自动跳过已持有及前置素质未获得的条目。
    Return arguments:
    list[ArtUpgradeOption] -- 按配置表顺序排列的可升级选项列表
    """
    player_talent = abilities.talent(0)
    prime_amount = originite_prime_amount()
    options: list[ArtUpgradeOption] = []
    for cid, data in game_config.config_talent_of_arts.items():
        if player_talent[data.talent_id]:
            continue
        if data.need_id and not player_talent[data.need_id]:
            continue
        money_cost = calculate_art_cost(data.level)
        todo = bool(data.todo)
        options.append(
            ArtUpgradeOption(
                cid=cid,
                talent_id=data.talent_id,
                level=data.level,
                money_cost=money_cost,
                todo=todo,
                can_buy_with_prime=(not todo and prime_amount >= money_cost),
                condition=evaluate_art_unlock_condition(cid),
            )
        )
    return options


def learn_or_upgrade_art(
    cid: int, *, no_cost_flag: bool = False
) -> LearnArtResult:
    """
    结算玩家学习或升级指定源石技艺。
    no_cost_flag 为 False 时检查并扣除至纯源石，库存不足时不授予素质并返回失败结果。
    Keyword arguments:
    cid -- int，config_talent_of_arts 中的条目编号
    no_cost_flag -- bool，为 True 时不消耗至纯源石直接习得
    Return arguments:
    LearnArtResult -- 本次学习或升级的结算结果
    """
    data = game_config.config_talent_of_arts[cid]
    talent_id = data.talent_id
    money_cost = calculate_art_cost(data.level)
    if no_cost_flag:
        paid_cost = 0
    else:
        if originite_prime_amount() < money_cost:
            return LearnArtResult(False, cid, talent_id, money_cost, 0, True)
        warehouse.add(ORIGINITE_PRIME_RESOURCE_ID, -money_cost)
        paid_cost = money_cost
    abilities.talent(0)[talent_id] = 1
    return LearnArtResult(True, cid, talent_id, money_cost, paid_cost, False)


def list_negative_mark_characters() -> list[int]:
    """
    查询当前在编干员中持有任意负面刻印（能力 15、17、18）的角色编号列表。
    Return arguments:
    list[int] -- 满足条件的在编角色编号列表
    """
    return [
        chara_id
        for chara_id in roster.active()
        if any(
            abilities.ability(chara_id)[aid]
            for aid in NEGATIVE_MARK_ABILITY_IDS
        )
    ]


def list_character_negative_marks(character_id: int) -> list[tuple[int, int]]:
    """
    查询指定角色当前非零的负面刻印及其等级。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    list[tuple[int, int]] -- (能力编号, 当前等级) 列表
    """
    ability = abilities.ability(character_id)
    return [
        (aid, ability[aid]) for aid in NEGATIVE_MARK_ABILITY_IDS if ability[aid]
    ]


def get_npc_panties_count(character_id: int) -> int:
    """
    读取藏品馆中已收藏的指定角色内裤数量。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    int -- 已收藏内裤条数
    """
    return len(player_collection.get("npc_panties").get(character_id, ()))


def consume_panties_duplicate_first(
    panties: Sequence[str], count: int = NEGATIVE_MARK_PANTY_COST
) -> list[str] | None:
    """
    从内裤列表中按重复款式优先规则移除指定条数，返回剩余的新列表。
    条数不足时返回 None，不修改传入序列。
    Keyword arguments:
    panties -- Sequence[str]，原内裤款式列表
    count -- int，需要消耗的条数，默认 5
    Return arguments:
    list[str] | None -- 扣除后的剩余列表，数量不足时为 None
    """
    if len(panties) < count:
        return None
    remaining = list(panties)
    pan_counts: dict[str, int] = {}
    for pan in remaining:
        pan_counts[pan] = pan_counts.get(pan, 0) + 1
    removed = 0
    for pan, freq in pan_counts.items():
        if freq > 1:
            remove_count = min(freq - 1, count - removed)
            for _step in range(remove_count):
                remaining.remove(pan)
            removed += remove_count
            if removed >= count:
                break
    while removed < count:
        remaining.pop(0)
        removed += 1
    return remaining


def reduce_negative_mark(
    character_id: int, ability_id: int
) -> NegativeMarkReductionResult:
    """
    结算指定角色负面刻印降低：非 debug 模式先消耗 5 条内裤，随后能力减 1 并清零对应主状态。
    Keyword arguments:
    character_id -- int，目标角色编号
    ability_id -- int，目标负面刻印能力编号
    Return arguments:
    NegativeMarkReductionResult -- 本次降低结算的结果
    """
    ability = abilities.ability(character_id)
    panties = list(player_collection.get("npc_panties").get(character_id, ()))
    if modes.debug():
        consumed, remaining_count = 0, len(panties)
    else:
        remaining = consume_panties_duplicate_first(
            panties, NEGATIVE_MARK_PANTY_COST
        )
        if remaining is None:
            return NegativeMarkReductionResult(
                False,
                character_id,
                ability_id,
                0,
                len(panties),
                ability.get(ability_id, 0),
                None,
            )
        player_collection.set_list_map_entry(
            "npc_panties", character_id, remaining
        )
        consumed, remaining_count = NEGATIVE_MARK_PANTY_COST, len(remaining)
    new_level = ability[ability_id] - 1
    ability[ability_id] = new_level
    reset_status_id = NEGATIVE_MARK_STATUS_MAP.get(ability_id)
    if reset_status_id is not None:
        status.set(character_id, reset_status_id, 0)
    return NegativeMarkReductionResult(
        True,
        character_id,
        ability_id,
        consumed,
        remaining_count,
        new_level,
        reset_status_id,
    )
