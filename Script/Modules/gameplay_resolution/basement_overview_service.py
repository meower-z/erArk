"""
基建总览服务（basement_overview_service）
=========================================
提供管理罗德岛界面的仓库、部门概况、部门详情与子系统入口提示查询。
本模块不导入 Script.UI 与 Script.Settle。
"""

import datetime
from collections.abc import Iterable
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import basement, game_time, handle_premise
from Script.Modules.domains import commission, economy, facility, identity
from Script.Modules.domains import maintenance, prison, recruit, roster
from Script.Modules.domains import warehouse, work

_: FunctionType = get_text._
""" 翻译api """


def capacity() -> int:
    """
    返回仓库的单项资源存放上限。
    Return arguments:
    int -- 当前仓库的单项资源容量上限
    """
    return warehouse.capacity()


def stock_rows(kind: str) -> list[tuple[str, int]]:
    """
    按资源分类筛选并返回当前库存列表。
    Keyword arguments:
    kind -- str，资源配置中的分类名称
    Return arguments:
    list[tuple[str, int]] -- (资源名称, 库存数量) 列表
    """
    return [
        (game_config.config_resouce[rid].name, warehouse.amount(rid))
        for rid in warehouse.stock()
        if game_config.config_resouce[rid].type == kind
    ]


def departments() -> list[str]:
    """
    按设施配置顺序返回所有部门的名称列表。
    Return arguments:
    list[str] -- 设施配置中 type 为 -1 的部门名称列表
    """
    return [
        data.name
        for data in game_config.config_facility.values()
        if data.type == -1
    ]


def staffing() -> tuple[int, int]:
    """
    返回当前工作中干员数与在编干员总数。
    Return arguments:
    tuple[int, int] -- (当前工作人数, 在编干员总数)
    """
    return work.people_now(), roster.count()


def income() -> int:
    """
    返回今日各部门的龙门币总收入。
    Return arguments:
    int -- 今日累计龙门币收入
    """
    return economy.income()


def _works(department: str) -> list[tuple[int, str]]:
    """按工作配置顺序返回指定部门下各岗位的 (岗位编号, 名称) 列表。"""
    return [
        (cid, data.name)
        for cid, data in game_config.config_work_type.items()
        if data.department == department
    ]


def staff_text(department: str) -> str:
    """
    组装单个部门在总览行中显示的人数统计文本。
    Keyword arguments:
    department -- str，部门名称
    Return arguments:
    str -- 各岗位人数文本（机库追加外勤干员数，关押区追加囚犯数）
    """
    text = "".join(
        f"  {name} — {len(work.roster(cid))}"
        for cid, name in _works(department)
    )
    if department == _("机库"):
        team = sum(len(one.team) for one in commission.ongoing().values())
        text += _("  外勤干员 — {0}").format(team)
    elif department == _("关押区"):
        text += _("  囚犯 — {0}").format(len(prison.prisoner_ids()))
    return text


def _names(chara_ids: Iterable[int]) -> list[str]:
    """按给定角色编号顺序返回对应的角色名称列表。"""
    return [identity.of(cid).name for cid in chara_ids]


def _grid(cells: list[str]) -> str:
    """将文本条目按每行三项排成多行缩进文本，列表为空时返回无。"""
    text = "".join(
        ("\n" if index % 3 == 0 else "") + f"    {cell}"
        for index, cell in enumerate(cells)
    )
    return text or _("\n    无")


def _engineering() -> str:
    """组装工程部的故障地点损坏数与检修人员负责地点文本。"""
    damage = [
        f"{scene}-{count}" for scene, count in maintenance.damage().items()
    ]
    places = [
        f"{identity.of(cid).name}-{place}"
        for cid, place in maintenance.places().items()
        if len(place)
    ]
    return (
        _("\n  当前故障地点与设施损坏数：")
        + _grid(damage)
        + _("\n  当前检修人员与其负责地点：")
        + _grid(places)
    )


def _clerical() -> str:
    """组装文职部的待确认招募干员人数与 1 至 4 号招募位进度文本。"""
    if recruit.pending():
        text = _(
            "\n  当前已招募未确认干员人数为：{0}人，请前往博士办公室确认"
        ).format(len(recruit.pending()))
    else:
        text = _("\n  当前没有已招募干员，请等待招募完成")
    lines = recruit.lines()
    for line_id in sorted(lines.keys() & {0, 1, 2, 3}):
        text += _("\n  {0}号招募位进度：{1}%/100%").format(
            line_id + 1, round(lines[line_id]["progress"], 1)
        )
    return text


def _library() -> str:
    """组装图书馆当前读者人数的统计文本。"""
    return _("\n  当前读者人数：{0} 人").format(basement.library_reader_count())


def _dormitory() -> str:
    """组装宿舍区的干员总数、宿舍容量与入住名单文本。"""
    from Script.System.Dormitory_System import common as dormitory_common

    text = _("\n  干员总数/宿舍容量：{0}/{1}").format(
        str(roster.count()), facility.people_max()
    )
    return text + dormitory_common.get_dormitory_occupants_text() + "\n"


def _days_left(end: datetime.datetime) -> str:
    """计算当前时刻到截止时间的剩余天数，不超过零天时返回不足一天。"""
    days = game_time.count_day_for_datetime(game_time.now(), end)
    return _("不足一天") if days <= 0 else _("{0}天").format(days)


def _hangar() -> str:
    """组装机库进行中的外勤委托与可用或出动中载具的概况文本。"""
    text = _("\n  当前外勤委托情况：")
    ongoing = commission.ongoing()
    for commission_id, one in ongoing.items():
        text += _("\n  [{0}]：{1}，剩余{2}").format(
            game_config.config_commission[commission_id].name,
            "、".join(_names(one.team)),
            _days_left(one.end),
        )
    if not len(ongoing):
        text += _("\n  无")
    text += _("\n  当前载具情况：")
    for vehicle_id, (owned, out) in commission.vehicles().items():
        if owned == 0 and out == 0:
            continue
        text += _("\n  [{0}]：可用{1}辆，出动中{2}辆").format(
            game_config.config_vehicle[vehicle_id].name, owned, out
        )
    return text


def department_text(department: str) -> str:
    """
    组装单个部门详情页的在岗人员与部门专项概况文本。
    Keyword arguments:
    department -- str，部门名称
    Return arguments:
    str -- 部门情况文本，含各岗位名单及工程部等五个部门的专项信息
    """
    text = _("\n当前{0}部门情况：").format(department)
    for cid, name in _works(department):
        text += _("\n  当前正在工作的{0}：").format(name)
        members = _names(work.roster(cid))
        text += "".join(f" {member}" for member in members) or _(" 暂无")
    extra = {
        _("工程部"): _engineering,
        _("文职部"): _clerical,
        _("图书馆"): _library,
        _("宿舍区"): _dormitory,
        _("机库"): _hangar,
    }.get(department)
    return text + (extra() if extra else "")


def entry_notice(label: str) -> str | None:
    """
    检查部门子系统入口的准入条件并返回提示文本。
    Keyword arguments:
    label -- str，子系统按钮标签文本
    Return arguments:
    str | None -- 不可直接进入时返回提示文案，可进入时返回 None
    """
    if label == _("[装备维护系统]"):
        if not handle_premise.handle_blacksmith_shop_open(0):
            return _("\n○铁匠铺未开放，无法进入装备维护系统\n")
    elif label == _("[烹饪系统]"):
        return _("\n○需要在生活娱乐区-厨房中进行烹饪\n")
    elif label == _("[监禁调教系统]"):
        if not handle_premise.handle_have_warden(0):
            return _("\n○未任命监狱长，无法进入监禁调教系统\n")
    return None
