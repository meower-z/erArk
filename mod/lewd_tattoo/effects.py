# -*- coding: UTF-8 -*-
"""
淫纹效果定义（唯一来源）与纯函数数学

本模块不 import 任何 Script 模块，可以脱离游戏单测（tests/test_math.py）。
新增一种效果只改 EFFECTS 表和 compile_profile 里对应 kind 的一个分支；面板、存档、信息页都从 EFFECTS 读，不再另写名单。
"""
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, FrozenSet, Iterable, NamedTuple, Optional, Tuple

SLOT_CAP = 10
""" 槽位上限（spec：以后可能调整，只改这里） """

FEEL_PARTS: Dict[int, Tuple[str, str]] = {
    0: ("skin", "皮肤"),
    1: ("breast", "胸部"),
    2: ("clitoris", "阴蒂"),
    3: ("penis", "阴茎"),
    4: ("vagina", "阴道"),
    5: ("anus", "肛肠"),
    6: ("urethra", "尿道"),
    7: ("womb", "子宫"),
    21: ("mouth", "口喉"),
    22: ("beast", "兽部"),
    23: ("mind", "心理"),
}
""" 快感状态id -> (存档用英文键, 显示名)。与 CharacterState.csv 里 type==0 的 11 项一致（tests/test_smoke.py 核对） """

MIND = 23
""" 心理快感状态id """
DESIRE = 12
""" 欲情状态id """
PAIN = 17
""" 苦痛状态id """
NEGATIVE = (18, 19, 20)
""" 恐怖/抑郁/反感 """
DESIRE_FLOOR = 60
""" 媚药式的欲望值下限 """


@dataclass(frozen=True)
class EffectDef:
    """
    一种淫纹效果的定义
    Keyword arguments:
    key -- 存档键（只用英文，存档里只存这个字符串）
    name -- 面板显示名
    slots -- 占用槽位
    kind -- 效果种类，compile_profile 按它解释
    info -- 面板上的一句说明
    part -- kind=="boost_part" 时的快感状态id，其余为 None
    """

    key: str
    name: str
    slots: int
    kind: str
    info: str
    part: Optional[int] = None


def _build_effects() -> Tuple[EffectDef, ...]:
    """
    生成效果表：11 个单部位倍率 + 7 个其他效果，顺序即面板显示顺序
    Keyword arguments:
    无
    Return arguments:
    Tuple[EffectDef, ...] -- 全部效果定义
    """
    parts = tuple(EffectDef(f"boost:{en}", f"{zh}快感强化", 1, "boost_part", f"{zh}快感获得×1.5", sid) for sid, (en, zh) in FEEL_PARTS.items())
    others = (
        EffectDef("all_boost", "全部位快感强化", 4, "all_boost", "所有部位快感获得×1.5"),
        EffectDef("pain_to_mind", "苦痛快感化", 2, "pain_to_mind", "苦痛增加时改为获得心理快感"),
        EffectDef("negative_to_mind", "负面情感快感化", 3, "negative_to_mind", "恐怖、抑郁、反感增加时改为获得心理快感"),
        EffectDef("aphrodisiac", "媚药式", 2, "aphrodisiac", f"欲望值不低于{DESIRE_FLOOR}，每日欲望增长×2，欲情获得×1.5"),
        EffectDef("link1", "快感联结I", 4, "link1", "某部位获得快感时，其余部位各获得其0.1倍"),
        EffectDef("link2", "快感联结II", 6, "link2", "某部位获得快感时，本部位只得0.8倍，其余部位各获得其0.2倍"),
        EffectDef("edge_suppress", "寸止压制", 3, "edge_suppress", "寸止失败时有机会由淫纹强行压制住"),
    )
    return parts + others


EFFECTS: Tuple[EffectDef, ...] = _build_effects()
""" 全部效果定义，顺序即面板顺序 """
EFFECT_BY_KEY: Dict[str, EffectDef] = {effect.key: effect for effect in EFFECTS}
""" 存档键 -> 效果定义 """


@dataclass(frozen=True)
class Profile:
    """
    一组已选效果编译后的数值画像（不可变，按 frozenset 缓存，热路径只做属性读取）
    Keyword arguments:
    part_mult -- 快感状态id -> 增量倍率（单部位×全部位已相乘）
    own_scale -- 本部位最终保留比例（联结II 为 0.8，否则 1.0）
    spread -- 每个其他快感部位获得的裸增量比例（联结I 0.1 + 联结II 0.2，同带为 0.3）
    to_mind -- 需要转成心理快感的状态id集合（苦痛 17；负面 18/19/20）
    desire_mult -- 欲情(12)增量倍率
    desire_floor -- 欲望值下限（媚药式为 60，否则 0）
    daily_growth_mult -- 每日欲望增长倍率
    edge_suppress -- 是否有寸止压制
    slots_used -- 已用槽位
    """

    part_mult: Tuple[Tuple[int, float], ...]
    own_scale: float
    spread: float
    to_mind: FrozenSet[int]
    desire_mult: float
    desire_floor: int
    daily_growth_mult: int
    edge_suppress: bool
    slots_used: int

    def mult_of(self, state_id: int) -> float:
        """
        取某快感状态的增量倍率
        Keyword arguments:
        state_id -- 快感状态id
        Return arguments:
        float -- 倍率
        """
        for sid, mult in self.part_mult:
            if sid == state_id:
                return mult
        return 1.0


@lru_cache(maxsize=256)
def compile_profile(keys: FrozenSet[str]) -> Profile:
    """
    把一组效果键编译成 Profile（调用方保证 keys 全是已知键；未知键的角色根本不激活，见 store.active_keys）
    Keyword arguments:
    keys -- 效果键集合
    Return arguments:
    Profile -- 数值画像
    """
    defs = [EFFECT_BY_KEY[key] for key in keys if key in EFFECT_BY_KEY]
    kinds = {effect.kind for effect in defs}
    boosted_parts = {effect.part for effect in defs if effect.kind == "boost_part"}
    all_mult = 1.5 if "all_boost" in kinds else 1.0
    part_mult = tuple((sid, all_mult * (1.5 if sid in boosted_parts else 1.0)) for sid in FEEL_PARTS)
    to_mind = set()
    if "pain_to_mind" in kinds:
        to_mind.add(PAIN)
    if "negative_to_mind" in kinds:
        to_mind.update(NEGATIVE)
    aphrodisiac = "aphrodisiac" in kinds
    return Profile(
        part_mult=part_mult,
        own_scale=0.8 if "link2" in kinds else 1.0,
        spread=(0.1 if "link1" in kinds else 0.0) + (0.2 if "link2" in kinds else 0.0),
        to_mind=frozenset(to_mind),
        desire_mult=1.5 if aphrodisiac else 1.0,
        desire_floor=DESIRE_FLOOR if aphrodisiac else 0,
        daily_growth_mult=2 if aphrodisiac else 1,
        edge_suppress="edge_suppress" in kinds,
        slots_used=sum(effect.slots for effect in defs),
    )


def slots_of(keys: Iterable[str]) -> int:
    """
    计算一组效果键占用的槽位（面板实时显示与"能否确认"判断用）
    Keyword arguments:
    keys -- 效果键
    Return arguments:
    int -- 槽位数
    """
    return sum(EFFECT_BY_KEY[key].slots for key in set(keys) if key in EFFECT_BY_KEY)


def can_confirm(current: FrozenSet[str], selected: FrozenSet[str]) -> bool:
    """
    面板能否确认：只有选择改变、且不超槽位上限时才能确认
    Keyword arguments:
    current -- 当前已刻效果（还没有淫纹时为空集合）
    selected -- 面板上的新选择
    Return arguments:
    bool -- 能否确认
    """
    return selected != current and slots_of(selected) <= SLOT_CAP


class GainPlan(NamedTuple):
    """
    一次状态增量在淫纹作用下的去向
    Keyword arguments:
    main -- 写回本状态的增量；to_mind 为 True 时无意义
    to_mind -- 是否改为以原增量递归结算心理快感（同本体心控苦痛快感化）
    side -- 联结给其他快感部位的裸增量 ((状态id, 增量), ...)，还没扣除"角色缺少的部位"
    """

    main: int
    to_mind: bool
    side: Tuple[Tuple[int, int], ...]


def plan_gain(profile: Profile, state_id: int, value: int) -> GainPlan:
    """
    计算一次正增量的去向（纯函数）

    计算顺序（value = 本体 int() 之后、写入之前的增量，调用方保证 value > 0）：
    1. state_id 在 to_mind 里：不写本状态，由调用方以 value 递归结算 23
    2. state_id == 12：main = int(value * desire_mult)
    3. state_id 是快感部位 s：
       X = value * part_mult[s]            # 单部位 1.5 与全部位 1.5 相乘，各自独立乘区
       main = int(X * own_scale)           # 联结II 本部位 ×0.8，作用在 X 之后
       其他每个快感部位 t≠s：side += int(X * spread)，为 0 则不列
    4. 其他状态：原样
    Keyword arguments:
    profile -- 数值画像
    state_id -- 状态id
    value -- 本体算好的正增量
    Return arguments:
    GainPlan -- 去向
    """
    if state_id in profile.to_mind:
        return GainPlan(0, True, ())
    if state_id == DESIRE:
        return GainPlan(int(value * profile.desire_mult), False, ())
    if state_id not in FEEL_PARTS:
        return GainPlan(value, False, ())
    boosted = value * profile.mult_of(state_id)
    main = int(boosted * profile.own_scale)
    side_gain = int(boosted * profile.spread)
    side = tuple((sid, side_gain) for sid in FEEL_PARTS if sid != state_id) if side_gain > 0 else ()
    return GainPlan(main, False, side)


def edge_rescue_chance(over_count: int) -> float:
    """
    寸止失败后淫纹追加成功的概率：k = -over_count，p = 0.85 ** max(k - 2, 0)
    Keyword arguments:
    over_count -- 本体算出的 技巧*3 - Σ寸止次数²（失败时必为负）
    Return arguments:
    float -- 追加成功概率，k<=2 时为 1.0
    """
    return 0.85 ** max(-over_count - 2, 0)


def daily_growth(profile: Profile, desire_point: int, growth: int) -> int:
    """
    媚药式下的每日欲望增长量：先把欲望值抬到下限，再加 倍率×原增长
    返回值是"增量"，本体执行 desire_point += 返回值；结果 = max(dp, floor) + mult * growth
    Keyword arguments:
    profile -- 数值画像
    desire_point -- 当前欲望值
    growth -- 本体算出的原增长量
    Return arguments:
    int -- 新增长量
    """
    return max(desire_point, profile.desire_floor) - desire_point + profile.daily_growth_mult * growth


EDGE_RESCUE_TEXTS: Tuple[str, str] = (
    "{NPCName}的寸止险些失败，依靠淫纹才压制住奔涌的快感",
    "{NPCName}的大量快感被淫纹抑制，浑身剧烈颤抖却无法高潮",
)
""" 寸止压制成功时二选一（各 50%）的提示，替换本体"尝试寸止…但失败了"那一行 """
