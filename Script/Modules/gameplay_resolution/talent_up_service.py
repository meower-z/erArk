"""
素质升级资格查询服务（talent_up_service）
=========================================
提供角色陷落系素质的共通基础前提、陷落等级、爱情与隶属路线可见性及前提、
以及单条素质获取条件与动作模式的纯数据查询。
本模块不导入界面、窗口、计算或前提模块，仅依赖配置与领域数据接口。
"""

from dataclasses import dataclass
from typing import Literal

from Script.Config import game_config
from Script.Modules.domains import abilities, relations

COMMON_FAVORABILITY_MIN: int = 500
COMMON_TRUST_MIN: int = 50
HATE_MARK_ABILITY_ID: int = 18

PAIN_MARK_ABILITY_ID: int = 15
FEAR_MARK_ABILITY_ID: int = 17
INTIMACY_ABILITY_ID: int = 32
INTIMACY_MIN_LEVEL: int = 2

PLEASURE_MARK_ABILITY_ID: int = 13
SUBMISSION_MARK_ABILITY_ID: int = 14
OBEDIENCE_ABILITY_ID: int = 31
OBEDIENCE_MIN_LEVEL: int = 2

OBEY_FALL_TALENT_IDS: tuple[int, ...] = (211, 212, 213, 214)
FALL_STAGE_TALENTS: tuple[tuple[int, tuple[int, int]], ...] = (
    (1, (201, 211)),
    (2, (202, 212)),
    (3, (203, 213)),
    (4, (204, 214)),
)
ROUTE_CHOICE_TALENT_IDS: frozenset[int] = frozenset({201, 211})
RING_CONFESSION_TALENT_ID: int = 203
COLLAR_EQUIP_TALENT_ID: int = 213
MAX_FALL_LEVEL: int = 4

PrereqKind = Literal[
    "favorability",
    "trust",
    "hate_mark",
    "pain_mark",
    "fear_mark",
    "intimacy",
    "pleasure_mark",
    "submission_mark",
    "obedience",
]
RouteKind = Literal["love", "obey"]
TalentActionMode = Literal[
    "route_confirm",
    "route_blocked",
    "ring_confession",
    "collar_equip",
    "upgrade_confirm",
    "upgrade_blocked",
]


@dataclass(frozen=True)
class PrerequisiteCheck:
    """单条陷落路线前提条件的判定结果。"""

    kind: PrereqKind
    current: int | float
    required: int
    met: bool


@dataclass(frozen=True)
class TalentRequirementCheck:
    """单条素质获取需求的解析与判定结果。"""

    kind: str
    target_id: int
    current: int | float
    required: int
    met: bool


@dataclass(frozen=True)
class TalentGainEvaluation:
    """单个目标素质的获取条件明细与可执行动作模式。"""

    talent_id: int
    requirements: tuple[TalentRequirementCheck, ...]
    all_met: bool
    action_mode: TalentActionMode


@dataclass(frozen=True)
class FallRouteStatus:
    """单条陷落路线（爱情或隶属）的阶段、前提与下一级素质评估。"""

    route: RouteKind
    level: int
    prerequisites: tuple[PrerequisiteCheck, ...]
    route_ok: bool
    is_max_level: bool
    next_talent_id: int | None
    next_gain: TalentGainEvaluation | None


@dataclass(frozen=True)
class TalentUpgradeOverview:
    """角色陷落素质升级面板的完整纯数据查询视图。"""

    character_id: int
    common_prerequisites: tuple[PrerequisiteCheck, ...]
    common_ok: bool
    fall_level: int
    love_level: int
    obey_level: int
    love_route: FallRouteStatus | None
    obey_route: FallRouteStatus | None


def get_fall_level(character_id: int) -> int:
    """
    计算角色的带符号陷落等级：爱情系为正，隶属系为负，玩家或未陷落为 0。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    int -- 带符号陷落等级（-4 至 4）
    """
    if character_id == 0:
        return 0
    talent = abilities.talent(character_id)
    now_level = 0
    for level, pair in FALL_STAGE_TALENTS:
        if talent[pair[0]] or talent[pair[1]]:
            now_level = level
            break
    if any(talent[tid] for tid in OBEY_FALL_TALENT_IDS):
        return -now_level
    return now_level


def evaluate_common_prerequisites(
    character_id: int,
) -> tuple[PrerequisiteCheck, ...]:
    """
    评估指定角色的陷落系素质共通基础前提（好感度、信任度与反发刻印）。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    tuple[PrerequisiteCheck, ...] -- 按固定展示顺序排列的三项判定结果
    """
    fav = relations.favorability(character_id)[0]
    trust_val = relations.trust(character_id)
    hate_mark = abilities.ability(character_id)[HATE_MARK_ABILITY_ID]
    return (
        PrerequisiteCheck(
            "favorability",
            fav,
            COMMON_FAVORABILITY_MIN,
            fav >= COMMON_FAVORABILITY_MIN,
        ),
        PrerequisiteCheck(
            "trust",
            trust_val,
            COMMON_TRUST_MIN,
            trust_val >= COMMON_TRUST_MIN,
        ),
        PrerequisiteCheck("hate_mark", hate_mark, 0, hate_mark == 0),
    )


def evaluate_route_prerequisites(
    character_id: int, route: str
) -> tuple[PrerequisiteCheck, ...]:
    """
    评估指定角色在给定陷落路线上的专属前提条件。
    Keyword arguments:
    character_id -- int，角色编号
    route -- str，路线标识（"love" 或 "obey"）
    Return arguments:
    tuple[PrerequisiteCheck, ...] -- 按固定展示顺序排列的三项判定结果
    """
    ability = abilities.ability(character_id)
    if route == "love":
        pain = ability[PAIN_MARK_ABILITY_ID]
        fear = ability[FEAR_MARK_ABILITY_ID]
        intimacy = ability[INTIMACY_ABILITY_ID]
        return (
            PrerequisiteCheck("pain_mark", pain, 0, pain == 0),
            PrerequisiteCheck("fear_mark", fear, 0, fear == 0),
            PrerequisiteCheck(
                "intimacy",
                intimacy,
                INTIMACY_MIN_LEVEL,
                intimacy >= INTIMACY_MIN_LEVEL,
            ),
        )
    if route == "obey":
        pleasure = ability[PLEASURE_MARK_ABILITY_ID]
        submission = ability[SUBMISSION_MARK_ABILITY_ID]
        obedience = ability[OBEDIENCE_ABILITY_ID]
        return (
            PrerequisiteCheck("pleasure_mark", pleasure, 1, pleasure >= 1),
            PrerequisiteCheck(
                "submission_mark", submission, 1, submission >= 1
            ),
            PrerequisiteCheck(
                "obedience",
                obedience,
                OBEDIENCE_MIN_LEVEL,
                obedience >= OBEDIENCE_MIN_LEVEL,
            ),
        )
    raise ValueError(f"unknown fall route: {route}")


def next_route_talent_id(route: str, level: int) -> int | None:
    """
    根据路线与当前阶段等级计算下一级陷落素质编号，满级时返回 None。
    Keyword arguments:
    route -- str，路线标识（"love" 或 "obey"）
    level -- int，当前路线阶段等级（0 至 4）
    Return arguments:
    int | None -- 下一级素质编号，已满级时为 None
    """
    if route not in ("love", "obey"):
        raise ValueError(f"unknown fall route: {route}")
    if level >= MAX_FALL_LEVEL:
        return None
    base = 200 if route == "love" else 210
    return base + 1 if level == 0 else base + level + 1


def resolve_action_mode(talent_id: int, all_met: bool) -> TalentActionMode:
    """
    根据目标素质编号与条件是否全部满足，确定面板应展示的动作模式。
    Keyword arguments:
    talent_id -- int，目标素质编号
    all_met -- bool，路线前提与素质自身需求是否全部满足
    Return arguments:
    TalentActionMode -- 动作模式标识
    """
    if talent_id in ROUTE_CHOICE_TALENT_IDS:
        return "route_confirm" if all_met else "route_blocked"
    if talent_id == RING_CONFESSION_TALENT_ID:
        return "ring_confession"
    if talent_id == COLLAR_EQUIP_TALENT_ID:
        return "collar_equip"
    return "upgrade_confirm" if all_met else "upgrade_blocked"


def _evaluate_requirement(
    character_id: int, need_text: str
) -> TalentRequirementCheck:
    """解析并评估单条 config_talent_gain_data 需求表达式。"""
    head, raw_value = need_text.split("|", 1)
    need_type = head[0]
    need_type_id = int(head[1:] or 0)
    need_value = int(raw_value)
    if need_type == "A":
        current: int | float = abilities.ability(character_id)[need_type_id]
        return TalentRequirementCheck(
            "A", need_type_id, current, need_value, current >= need_value
        )
    if need_type == "T":
        current = abilities.talent(character_id)[need_value]
        return TalentRequirementCheck(
            "T", need_value, current, 1, bool(current)
        )
    if need_type == "J":
        current = abilities.juel(character_id)[need_type_id]
        return TalentRequirementCheck(
            "J", need_type_id, current, need_value, current >= need_value
        )
    if need_type == "E":
        current = abilities.experience(character_id)[need_type_id]
        return TalentRequirementCheck(
            "E", need_type_id, current, need_value, current >= need_value
        )
    if need_type == "F":
        current = relations.favorability(character_id)[0]
        return TalentRequirementCheck(
            "F", 0, current, need_value, current >= need_value
        )
    if need_type == "X":
        current = relations.trust(character_id)
        return TalentRequirementCheck(
            "X", 0, current, need_value, current >= need_value
        )
    return TalentRequirementCheck(need_type, need_type_id, 0, need_value, True)


def evaluate_talent_gain(
    character_id: int, talent_id: int, *, route_ok: bool = True
) -> TalentGainEvaluation:
    """
    评估指定角色获取目标素质的全部配置条件与可执行动作模式。
    Keyword arguments:
    character_id -- int，角色编号
    talent_id -- int，目标素质编号
    route_ok -- bool，外层共通与路线前提是否已满足
    Return arguments:
    TalentGainEvaluation -- 条件明细、总判定与动作模式
    """
    need_expr = game_config.config_talent_gain_data[talent_id].gain_need
    requirements = tuple(
        _evaluate_requirement(character_id, token)
        for token in need_expr.split("&")
    )
    all_met = route_ok and all(req.met for req in requirements)
    return TalentGainEvaluation(
        talent_id=talent_id,
        requirements=requirements,
        all_met=all_met,
        action_mode=resolve_action_mode(talent_id, all_met),
    )


def _build_route_status(
    character_id: int, route: RouteKind, level: int, common_ok: bool
) -> FallRouteStatus:
    """组装单条可见陷落路线的前提、满级标志与下一级素质评估。"""
    prereqs = evaluate_route_prerequisites(character_id, route)
    route_ok = common_ok and all(item.met for item in prereqs)
    is_max = level == MAX_FALL_LEVEL
    next_id = None if is_max else next_route_talent_id(route, level)
    next_gain = (
        None
        if next_id is None
        else evaluate_talent_gain(character_id, next_id, route_ok=route_ok)
    )
    return FallRouteStatus(
        route=route,
        level=level,
        prerequisites=prereqs,
        route_ok=route_ok,
        is_max_level=is_max,
        next_talent_id=next_id,
        next_gain=next_gain,
    )


def build_talent_upgrade_overview(character_id: int) -> TalentUpgradeOverview:
    """
    构建指定角色陷落素质升级面板所需的完整纯数据总览。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    TalentUpgradeOverview -- 包含共通前提、陷落等级及可见路线状态的总览对象
    """
    common_prereqs = evaluate_common_prerequisites(character_id)
    common_ok = all(item.met for item in common_prereqs)
    fall_level = get_fall_level(character_id)
    love_level = fall_level if fall_level > 0 else 0
    obey_level = -fall_level if fall_level < 0 else 0
    love_route = (
        _build_route_status(character_id, "love", love_level, common_ok)
        if love_level > 0 or obey_level == 0
        else None
    )
    obey_route = (
        _build_route_status(character_id, "obey", obey_level, common_ok)
        if obey_level > 0 or love_level == 0
        else None
    )
    return TalentUpgradeOverview(
        character_id=character_id,
        common_prerequisites=common_prereqs,
        common_ok=common_ok,
        fall_level=fall_level,
        love_level=love_level,
        obey_level=obey_level,
        love_route=love_route,
        obey_route=obey_route,
    )
