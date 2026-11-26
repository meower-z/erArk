"""
履历展示服务（first_record_service）
====================================
提供体液数据文本、周目视图、分组列表与会话折叠状态管理。
本模块不导入 Script.UI 与 Script.Settle。
"""

from dataclasses import dataclass, field
from types import FunctionType
from typing import NamedTuple
from Script.Core import game_type, get_text, num
from Script.Config import game_config
from Script.Modules.gameplay_resolution import first_record_text
from Script.Modules.domains import dirty, first_record as first_record_domain
from Script.Modules.domains import playthrough

_: FunctionType = get_text._
""" 文本翻译函数。 """

FLUID_GROUP_NAME = _("体液数据")
""" 体液数据分组的显示名称。 """

FLUID_GROUP = -1
""" 体液数据分组使用的分组编号（-1）。 """


def fluid_text(character_id: int) -> str:
    """
    构建角色当前体液数据的展示文本，无可展示数据时返回空串。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    str -- 体液数据文本，无数据时为空串
    """
    now_text = ""
    dirty_view = dirty.view(character_id)
    semen_count = 0
    for body_part in game_config.config_body_part:
        semen_count += dirty_view.body_semen[body_part][3]
    if semen_count:
        now_text += _("  全身总共被射上过{0}ml精液\n").format(semen_count)
        now_text += _(" 【各部位累计被射精液量】\n")
        for part_cid in game_config.config_body_part:
            part_semen = dirty_view.body_semen[part_cid][3]
            part_name = game_config.config_body_part[part_cid].name
            if part_cid == 2:
                if part_semen:
                    now_text += _("  {0}：总共喝过{1}ml精液\n").format(
                        part_name, part_semen
                    )
                continue
            if part_cid == 15:
                absorbed_semen = dirty_view.absorbed_total_semen
                if part_semen or absorbed_semen:
                    stomach_text_list = []
                    if part_semen:
                        stomach_text_list.append(
                            _("有{0}ml精液在食道直接射进了胃里").format(
                                part_semen
                            )
                        )
                    if absorbed_semen:
                        stomach_text_list.append(
                            _("肠胃一共吸收了{0}ml精液").format(
                                num.shown(absorbed_semen)
                            )
                        )
                    now_text += _("  {0}：{1}\n").format(
                        part_name, _("，").join(stomach_text_list)
                    )
                continue
            if part_semen:
                if part_cid in (6, 7, 8, 9):
                    now_text += _("  {0}：总共被射入过{1}ml精液\n").format(
                        part_name, part_semen
                    )
                else:
                    now_text += _("  {0}：总共被淋上过{1}ml精液\n").format(
                        part_name, part_semen
                    )
    from Script.Modules.domains import player_collection

    milk_total = player_collection.get("milk_total").get(character_id, 0)
    if milk_total > 0:
        now_text += _("  总共收集了{0}ml乳汁\n").format(milk_total)
    urine_total = player_collection.get("urine_total").get(character_id, 0)
    if urine_total > 0:
        now_text += _("  总共收集了{0}ml圣水\n").format(urine_total)
    return now_text


@dataclass(frozen=True)
class RoundView:
    """单次履历查询的周目视图数据。"""

    rounds: tuple[int, ...]
    """ 可查看的周目编号元组，历史周目升序排列后接当前周目。 """
    current: int
    """ 当前进行的周目编号。 """
    shown: int
    """ 当前实际展示的周目编号。 """
    record: game_type.FIRST_RECORD
    """ 当前展示周目对应的 FIRST_RECORD 数据。 """

    @property
    def is_current(self) -> bool:
        """判断当前展示的是否为当前周目。"""
        return self.shown == self.current


def round_view(character_id: int, selected_round: int) -> RoundView:
    """
    按角色与所选周目构建周目视图，无效周目回退到当前周目。
    Keyword arguments:
    character_id -- int，角色编号
    selected_round -- int，期望查看的周目编号
    Return arguments:
    RoundView -- 含可选周目、当前与展示周目及履历数据的视图
    """
    history = first_record_domain.history(character_id)
    current = playthrough.game_round()
    rounds = (*sorted(history), current)
    shown = selected_round if selected_round in rounds else current
    if shown == current:
        record = first_record_domain.view(character_id)
    else:
        record = history[shown]
    return RoundView(rounds, current, shown, record)


class GroupEntry(NamedTuple):
    """履历面板中单个分组条目的展示元数据。"""

    name: str
    """ 分组显示名称。 """
    group: int
    """ 分组编号，0 至 5 为履历分组，-1 为体液数据。 """
    fold_key: str
    """ 折叠状态键，格式为周目编号与位置序号拼接。 """
    default_expand: bool
    """ 是否默认展开，仅 0 号分组为 True。 """


def group_entries(view: RoundView) -> list[GroupEntry]:
    """
    生成指定周目视图下的分组列表，当前周目在索引 2 插入体液数据。
    Keyword arguments:
    view -- RoundView，当前周目视图
    Return arguments:
    list[GroupEntry] -- 按展示顺序排列的分组条目列表
    """
    groups = list(enumerate(first_record_text.GROUP_NAMES))
    if view.is_current:
        groups.insert(2, (FLUID_GROUP, FLUID_GROUP_NAME))
    return [
        GroupEntry(name, group, f"{view.shown}_{slot}", group == 0)
        for slot, (group, name) in enumerate(groups)
    ]


def group_text(character_id: int, view: RoundView, group: int) -> str:
    """
    获取指定分组的展示文本，无内容时返回无记录提示行。
    Keyword arguments:
    character_id -- int，角色编号
    view -- RoundView，当前周目视图
    group -- int，分组编号（0 至 5 或 -1）
    Return arguments:
    str -- 分组正文或带换行的无记录提示
    """
    if group == FLUID_GROUP:
        text = fluid_text(character_id)
    else:
        text = first_record_text.build_group_text(view.record, group)
    return text or _("  无记录\n")


@dataclass
class PanelState:
    """仅在当前会话内保存的周目选择与分组折叠状态。"""

    selected_round: int = -1
    """ 当前选中的周目编号，-1 表示跟随当前周目。 """
    folds: dict[str, bool] = field(default_factory=dict)
    """ 各分组折叠键到展开状态的映射。 """

    def select_round(self, round_num: int) -> None:
        """
        记录用户选择的周目编号。
        Keyword arguments:
        round_num -- int，目标周目编号
        """
        self.selected_round = round_num

    def toggle_fold(self, fold_key: str, default_expand: bool) -> None:
        """
        翻转指定折叠键的展开状态，未记录时以默认状态为起点。
        Keyword arguments:
        fold_key -- str，分组折叠键
        default_expand -- bool，未记录时的默认展开状态
        """
        self.folds[fold_key] = not self.folds.get(fold_key, default_expand)

    def expanded(self, entry: GroupEntry) -> bool:
        """
        查询分组条目当前是否展开，未记录时返回其默认状态。
        Keyword arguments:
        entry -- GroupEntry，目标分组条目
        Return arguments:
        bool -- 当前是否处于展开状态
        """
        return self.folds.get(entry.fold_key, entry.default_expand)
