"""
源石技艺面板菜单规则服务（originium_arts_panel_service）
========================================================
提供源石技艺主菜单条目可见性判定、能力系素质名称拼接、视觉系理智消耗计算
以及各能力系详情页行数据组装。
本模块不导入界面、翻译或结算模块，仅依赖配置、前提与素质检测及领域数据接口。
"""

from dataclasses import dataclass
from types import MappingProxyType

from Script.Config import game_config
from Script.Design import handle_premise, handle_talent
from Script.Modules.domains import abilities, modes


@dataclass(frozen=True, slots=True)
class ArtGroup:
    """单个源石技艺能力系的素质编号序列与每级每小时理智消耗配置。"""

    talent_ids: tuple[int, ...]
    sanity_per_level: int | None = None


ART_GROUPS: MappingProxyType[int, ArtGroup] = MappingProxyType(
    {
        2: ArtGroup((316, 317, 318)),
        5: ArtGroup((304, 305, 306)),
        6: ArtGroup((307, 308, 309), sanity_per_level=5),
    }
)
"""菜单编号到源石技艺能力系配置的只读映射（2 时间系、5 激素系、6 视觉系）。"""


@dataclass(frozen=True, slots=True)
class ArtMenuEntry:
    """源石技艺主菜单的单个可见按钮条目，包含菜单编号、已持有素质拼接名与每小时理智消耗。"""

    key: int
    talent_names: str = ""
    sanity_per_hour: int | None = None


@dataclass(frozen=True, slots=True)
class ArtTalentRow:
    """源石技艺能力系详情页中的单条素质展示数据，包含编号、名称、说明与解锁状态。"""

    talent_id: int
    name: str
    info: str
    unlocked: bool


def _group_entry(key: int) -> ArtMenuEntry:
    """
    按菜单编号组装对应能力系的主菜单条目，拼接玩家已持有素质名称并按需计算每小时理智消耗。
    Keyword arguments:
    key -- int，能力系对应的主菜单编号（须存在于 ART_GROUPS）
    Return arguments:
    ArtMenuEntry -- 组装后的主菜单条目
    """
    group = ART_GROUPS[key]
    talent = abilities.talent(0)
    owned = [tid for tid in group.talent_ids if talent[tid]]
    names = "".join(
        ("" if tid == group.talent_ids[0] else " + ")
        + game_config.config_talent[tid].name
        for tid in owned
    )
    sanity = None
    if group.sanity_per_level is not None:
        sanity = len(owned) * group.sanity_per_level
    return ArtMenuEntry(key, names, sanity)


def menu_entries() -> tuple[ArtMenuEntry, ...]:
    """
    按固定菜单顺序返回玩家当前可见的全部源石技艺主菜单条目。
    Return arguments:
    tuple[ArtMenuEntry, ...] -- 当前可见的主菜单条目元组
    """
    entries = [ArtMenuEntry(1)]
    if handle_premise.handle_primary_time_stop(0):
        entries.append(_group_entry(2))
    if handle_talent.have_hypnosis_talent():
        entries.append(ArtMenuEntry(3))
    if modes.debug():
        entries.append(ArtMenuEntry(4))
    if handle_talent.have_hormone_talent():
        entries.append(_group_entry(5))
    if handle_talent.have_visual_talent():
        entries.append(_group_entry(6))
    if handle_talent.have_tactile_talent():
        entries.append(ArtMenuEntry(7))
    entries.append(ArtMenuEntry(11))
    if modes.debug() or handle_premise.handle_time_over_a_year(0):
        entries.append(ArtMenuEntry(12))
    return tuple(entries)


def group_rows(key: int) -> tuple[ArtTalentRow, ...]:
    """
    按能力系配置的素质顺序返回该系详情页的全部展示行及玩家解锁状态。
    Keyword arguments:
    key -- int，能力系对应的主菜单编号（须存在于 ART_GROUPS）
    Return arguments:
    tuple[ArtTalentRow, ...] -- 该能力系各素质的展示行元组
    """
    talent = abilities.talent(0)
    rows = []
    for tid in ART_GROUPS[key].talent_ids:
        data = game_config.config_talent[tid]
        rows.append(ArtTalentRow(tid, data.name, data.info, bool(talent[tid])))
    return tuple(rows)
