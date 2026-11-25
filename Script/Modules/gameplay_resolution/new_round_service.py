"""
多周目结算规则与查询服务（new_round_service）
=============================================
本模块提供周目点数汇总、继承消耗计算、继承选项快照与预览查询。
本模块公开常量 KEYS、ARTS_COST、GROWTH、DEBUG_BONUS、
PLAYER_HIDDEN_TYPES、HIDDEN_ABILITY 与 HIDDEN_EXPERIENCE。
本模块公开数据类 Fallen 与 Points。
本模块公开函数 points、rate、step、maxima、cost、growth_preview、
choices、ability_groups 与 experience_texts。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

from collections.abc import Sequence
from dataclasses import dataclass

from Script.Config import game_config
from Script.Core.num import Num
from Script.Design import handle_talent
from Script.Kernel import core
from Script.Modules.domains import abilities, first_record, h_meters
from Script.Modules.domains import hypnosis, identity, modes, needs
from Script.Modules.domains import player_collection, playthrough
from Script.Modules.domains import relations, roster

KEYS = (
    "pl_originium_arts_count",
    "pl_abi_and_exp_count",
    "pl_extra_growth_count",
    "pl_collection_count",
    "chara_fon_and_trust_count",
    "chara_abi_and_exp_count",
    "chara_hypnosis_count",
)
""" 按继承类型编号 0 至 6 排列的继承等级键名元组。 """
ARTS_COST = (
    ((304, 307, 310, 316, 331), 10),
    ((305, 308, 311, 317, 332), 30),
    ((306, 309, 312, 318, 333), 60),
    ((334,), 120),
)
""" 源石技艺天赋编号分组与对应周目点数单价表。 """
GROWTH = {
    "hit_max": (1000, 50),
    "mana_max": (1000, 50),
    "sanity_max": (100, 1),
    "semen_max": (100, 1),
}
""" 玩家四项属性上限的基础值与每点消耗折算系数映射。 """
DEBUG_BONUS = 9999
""" 调试模式下额外计入的周目点数加成值。 """
PLAYER_HIDDEN_TYPES = frozenset({0, 1, 2, 6})
""" 博士能力预览中跳过的能力类型编号集合。 """
HIDDEN_ABILITY = {0: frozenset({73, 74, 75}), 1: frozenset({3})}
""" 按角色性别隐藏的能力编号映射表。 """
HIDDEN_EXPERIENCE = {
    0: frozenset(
        {2, 4, 7, 12, 14, 17, 20, 22, 26, 51, 54, 55, 58, 72, 74, 77, 86}
        | set(range(100, 107))
    ),
    1: frozenset({3, 13, 21, 73}),
}
""" 按角色性别隐藏的经验编号映射表。 """


@dataclass(frozen=True, slots=True)
class Fallen:
    """单个陷落干员的结算条目，含角色编号、陷落天赋编号与点数。"""

    chara_id: int
    talent_id: int
    point: int


@dataclass(frozen=True, slots=True)
class Points:
    """周目点数结算汇总数据，含周目数、陷落干员、收藏品数与调试标志。"""

    game_round: int
    fallen: tuple[Fallen, ...]
    panties: int
    socks: int
    debug: bool

    @property
    def round_point(self) -> int:
        """按当前周目数乘以 20 计算基础周目点数。"""
        return self.game_round * 20

    @property
    def fallen_point(self) -> int:
        """汇总全部陷落干员条目提供的周目点数。"""
        return sum(row.point for row in self.fallen)

    @property
    def collection_point(self) -> int:
        """汇总内裤与袜子收藏品提供的周目点数。"""
        return self.panties + self.socks

    @property
    def total(self) -> int:
        """汇总周目、陷落、收藏品点数并在调试模式下计入加成。"""
        bonus = DEBUG_BONUS if self.debug else 0
        return (
            self.round_point + self.fallen_point + self.collection_point + bonus
        )


def _count(name: str) -> int:
    """统计玩家收藏品表中指定类别的全部条目总数。"""
    return sum(len(items) for items in player_collection.get(name).values())


def points() -> Points:
    """
    读取当前在编名册、周目数、收藏品与调试标志并生成点数汇总。
    Return arguments:
    Points -- 包含各项点数明细与总点数的结算对象
    """
    fallen = []
    for chara_id in roster.active():
        talent_id = handle_talent.have_fall_talent(chara_id)
        if talent_id:
            fallen.append(Fallen(chara_id, talent_id, talent_id % 10 * 2))
    return Points(
        playthrough.game_round(),
        tuple(fallen),
        _count("npc_panties"),
        _count("npc_socks"),
        modes.debug(),
    )


def rate(type_id: int, level: int) -> int:
    """
    查询指定继承类型与等级对应的继承百分比。
    Keyword arguments:
    type_id -- int，继承类型编号
    level -- int，继承等级
    Return arguments:
    int -- 配置表中的继承比例百分比
    """
    cid = game_config.config_new_round_inherit_type_data[type_id][level]
    return game_config.config_new_round_inherit[cid].inherit_rate


def step(type_id: int, level: int, delta: int) -> int:
    """
    按增量调整继承等级并限制在配置允许的等级范围内。
    Keyword arguments:
    type_id -- int，继承类型编号
    level -- int，当前继承等级
    delta -- int，等级增减步长
    Return arguments:
    int -- 夹紧至 0 与最高等级之间的新等级
    """
    top = len(game_config.config_new_round_inherit_type_data[type_id]) - 1
    return max(0, min(level + delta, top))


def maxima() -> dict[str, Num]:
    """
    读取博士当前的体力、气力、理智与精液四项属性上限。
    Return arguments:
    dict[str, Num] -- 四项属性上限键值映射
    """
    pl_needs = needs.of(0)
    return {
        "hit_max": pl_needs["hit_max"],
        "mana_max": pl_needs["mana_max"],
        "sanity_max": pl_needs["sanity_max"],
        "semen_max": h_meters.of(0)["semen_max"],
    }


def _growth_cost(now_rate: int) -> int:
    """按当前继承比例计算博士四项属性上限成长的周目点数消耗。"""
    now = maxima()
    return sum(
        int((now[key] - base) * now_rate / 100 / per)
        for key, (base, per) in GROWTH.items()
    )


def cost(type_id: int, level: int) -> int:
    """
    计算指定继承类型在目标等级下所需的周目点数。
    Keyword arguments:
    type_id -- int，继承类型编号
    level -- int，目标继承等级
    Return arguments:
    int -- 该继承项在目标等级的点数消耗
    """
    if type_id == 0:
        talent = abilities.talent(0)
        arts = (price for ids, price in ARTS_COST for i in ids if talent[i])
        return sum(arts) if level else 0
    if type_id == 2:
        return _growth_cost(rate(2, level)) if level else 0
    cid = game_config.config_new_round_inherit_type_data[type_id][level]
    return game_config.config_new_round_inherit[cid].point_cost


def growth_preview(now_rate: int) -> list[Num]:
    """
    按继承比例生成博士四项属性上限的当前值与继承值序列。
    Keyword arguments:
    now_rate -- int，属性上限继承比例百分比
    Return arguments:
    list[Num] -- 按四项顺序交替排列的当前值与继承值列表
    """
    row: list[Num] = []
    for key, value in maxima().items():
        base = GROWTH[key][0]
        row += [value, base + int((value - base) * now_rate / 100)]
    return row


def choices(
    levels: Sequence[int],
    fallen_ids: Sequence[int],
    world_setting: dict[int, int],
) -> dict[str, core.JSON]:
    """
    从当前内核状态收集多周目重置所需的全部继承选择快照。
    Keyword arguments:
    levels -- Sequence[int]，按类型顺序排列的七项继承等级
    fallen_ids -- Sequence[int]，陷落干员角色编号序列
    world_setting -- dict[int, int]，新周目世界设定映射
    Return arguments:
    dict[str, core.JSON] -- 供重置流程读取的继承数据字典
    """
    st = core.state()
    return {
        **dict(zip(KEYS, levels, strict=True)),
        "all_fall_chara_list": tuple(fallen_ids),
        "world_setting": {
            str(cid): value for cid, value in world_setting.items()
        },
        "player_maxima": maxima(),
        "npc_hypnosis": {
            str(c): d for c in fallen_ids if (d := hypnosis.degree(c))
        },
        "first_records": first_record.carry_for_new_round(identity.table(), st),
        "fallen_social": {
            str(cid): (relations.trust(cid), relations.favorability(cid)[0])
            for cid in fallen_ids
        },
        "carried": playthrough.carry_for_new_round(st),
        "abilities": abilities.carry([0, *fallen_ids], st),
        "carried_collection": player_collection.carry_for_new_round(st),
    }


def ability_groups(cid: int) -> dict[int, tuple[int, list[int]]]:
    """
    按配置顺序过滤角色能力编号并返回各类型的总数与展示列表。
    Keyword arguments:
    cid -- int，角色编号
    Return arguments:
    dict[int, tuple[int, list[int]]] -- 类型到总数与可见编号的映射
    """
    hidden = HIDDEN_ABILITY.get(identity.of(cid).sex, frozenset())
    groups = {}
    for ability_type, ids in game_config.config_ability_type_data.items():
        if cid == 0 and ability_type in PLAYER_HIDDEN_TYPES:
            continue
        groups[ability_type] = (len(ids), [i for i in ids if i not in hidden])
    return groups


def experience_texts(cid: int, now_rate: int) -> list[str]:
    """
    按性别过滤角色非零经验并生成含继承预览值的文本列表。
    Keyword arguments:
    cid -- int，角色编号
    now_rate -- int，能力与经验继承比例百分比
    Return arguments:
    list[str] -- 格式化后的经验展示文本列表
    """
    hidden = HIDDEN_EXPERIENCE.get(identity.of(cid).sex, frozenset())
    experience = abilities.experience(cid)
    texts = []
    for experience_id, data in game_config.config_experience.items():
        if experience_id in hidden or experience_id not in experience:
            continue
        value = experience[experience_id]
        if value > 0:
            inherited = int(value * now_rate / 100)
            texts.append(f" {data.name}:{value}(→{inherited})")
    return texts
