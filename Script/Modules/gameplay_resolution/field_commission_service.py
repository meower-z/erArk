"""
外勤委托服务（field_commission_service）
========================================
提供外勤委托列表筛选、需求与运载速度计算、编队及派遣写入逻辑。
本模块不导入 Script.UI 与 Script.Settle。
"""

import contextlib
import datetime
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import game_time
from Script.Modules.domains import commission, facility, flags, identity
from Script.Modules.domains import location, modes, roster
from Script.Modules.gameplay_resolution import roster_lifecycle_service
from Script.System.Field_Commission_System.field_commission_function import (
    get_commission_demand_and_reward,
    process_commission_text,
)

_: FunctionType = get_text._
""" 翻译api """

HANGAR = 14
""" 机库设施编号（14），用于读取可接取委托等级上限。 """
NO_DEMAND = ("", "无", "-1")
""" 表示委托无额外需求的配置文本元组。 """
DAY_MINUTES = 1440
""" 游戏内单日换算的分钟数（1440）。 """


@dataclass(frozen=True)
class Readiness:
    """外勤委托派遣前的就绪检查结果。"""

    people: bool
    """ 派遣队伍人数是否满足委托最低人数要求。 """
    capacity: int
    """ 当前已选载具提供的总运载量。 """
    capacity_ok: bool
    """ 总运载量是否满足委托运载量需求。 """
    demand: bool
    """ 委托的各项额外需求是否全部满足。 """

    @property
    def all(self) -> bool:
        """人数、运载量与额外需求是否全部满足。"""
        return self.people and self.capacity_ok and self.demand


@dataclass(frozen=True)
class Dispatch:
    """外勤委托派遣写入完成后的返回结果。"""

    days: float
    """ 本次派遣预计耗时天数，供界面提示展示。 """
    returns_at: datetime.datetime
    """ 写入进行中委托记录的预计返回游戏时间。 """


def _level(commission_id: int) -> int:
    """返回指定委托在配置表中的等级。"""
    return game_config.config_commission[commission_id].level


def _recruited(adv: int) -> bool:
    """判断当前在编名册中是否存在指定 adv 编号的角色。"""
    return any(identity.of(cid).adv == adv for cid in roster.active())


def _listed(commission_id: int, special: bool) -> bool:
    """判断委托是否应显示在常规或特殊外勤列表中。"""
    data = game_config.config_commission[commission_id]
    if (data.special != 0) != special:
        return False
    if modes.debug():
        return True
    finished = commission.finished()
    if data.related_id != -1 and data.related_id not in finished:
        return False
    if data.special != 0 and commission_id in finished:
        return False
    if commission_id in commission.shut_down():
        return False
    if data.level > facility.level(HANGAR) + 1:
        return False
    if "c_" in data.demand and data.type == "角色":
        return _recruited(int(data.demand.split("_")[1]))
    return True


def visible_commissions(special: bool) -> list[int]:
    """
    返回当前可显示的常规或特殊外勤委托编号列表。
    Keyword arguments:
    special -- bool，True 为特殊外勤，False 为常规外勤
    Return arguments:
    list[int] -- 当地优先、各自按等级排序并过滤后的委托编号列表
    """
    by_country = game_config.config_commission_id_by_country
    country_id = location.country()
    local = by_country[country_id] if country_id in by_country else []
    common = by_country[-1]
    local.sort(key=_level)
    common.sort(key=_level)
    return [cid for cid in local + common if _listed(cid, special)]


def required_advs(commission_id: int) -> list[int]:
    """
    解析委托需求中以 c_ 指定的角色 adv 编号列表。
    Keyword arguments:
    commission_id -- int，委托编号
    Return arguments:
    list[int] -- 按出现顺序解析出的角色 adv 编号列表
    """
    advs: list[int] = []
    demand = game_config.config_commission[commission_id].demand
    with contextlib.suppress(ValueError):
        for part in demand.split("&"):
            fields = part.split("_")
            if fields[0] == "c" and len(fields) >= 2:
                advs.append(int(fields[1]))
    return advs


def demand_parts(commission_id: int, team: list[int]) -> list[tuple[str, bool]]:
    """
    拆分委托需求并返回逐项显示文本与满足状态。
    Keyword arguments:
    commission_id -- int，委托编号
    team -- list[int]，当前选中的派遣角色编号列表
    Return arguments:
    list[tuple[str, bool]] -- 各项的 (显示文本, 是否满足) 列表
    """
    demand = game_config.config_commission[commission_id].demand
    if demand in NO_DEMAND:
        return []
    parts = []
    for part in demand.split("&"):
        _kind, text, met = process_commission_text(
            part, False, False, team, "", "", True
        )
        parts.append((text.strip(), met))
    return parts


def capacity_need(commission_id: int) -> int:
    """
    计算委托所需运载量，即 (耗时天数 - 1) 乘以派遣人数。
    Keyword arguments:
    commission_id -- int，委托编号
    Return arguments:
    int -- 该委托所需的最低载具总运载量
    """
    data = game_config.config_commission[commission_id]
    return (data.time - 1) * data.people


def fleet_capacity(chosen: Mapping[int, int]) -> int:
    """
    计算已选载具映射提供的总运载量。
    Keyword arguments:
    chosen -- Mapping[int, int]，载具编号到选定数量的映射
    Return arguments:
    int -- 全部已选载具运载量乘以数量之和
    """
    return sum(
        game_config.config_vehicle[vid].capacity * count
        for vid, count in chosen.items()
    )


def _slowest(vehicle_ids: Collection[int], ceiling: int) -> int:
    """返回载具速度与上限值中的最小值。"""
    speeds = [game_config.config_vehicle[vid].speed for vid in vehicle_ids]
    return min([ceiling, *speeds])


def team_speed(vehicle_ids: Collection[int]) -> int:
    """
    计算派遣载具列表的队伍速度，无载具时为 1 且上限为 9。
    Keyword arguments:
    vehicle_ids -- Collection[int]，已选载具编号集合
    Return arguments:
    int -- 队伍最终移动速度
    """
    if not vehicle_ids:
        return 1
    return _slowest(vehicle_ids, 9)


def fleet_speed(chosen: Mapping[int, int]) -> int:
    """
    计算载具选择界面的队伍速度，无载具时返回 1。
    Keyword arguments:
    chosen -- Mapping[int, int]，载具编号到选定数量的映射
    Return arguments:
    int -- 已选载具的最低速度（上限 99，未选时为 1）
    """
    speed = _slowest(list(chosen), 99)
    return 1 if speed == 99 else speed


def fleet_effects(chosen: Mapping[int, int]) -> list[str]:
    """
    按选择顺序提取已选载具的非“无”特殊效果并去重。
    Keyword arguments:
    chosen -- Mapping[int, int]，载具编号到选定数量的映射
    Return arguments:
    list[str] -- 去重后的载具特殊效果文本列表
    """
    effects: list[str] = []
    for vid in chosen:
        special = game_config.config_vehicle[vid].special
        if special != _("无") and special not in effects:
            effects.append(special)
    return effects


def travel_minutes(days: int, speed: int) -> int | None:
    """
    按基础天数与队伍速度计算加速后的总耗时分钟数。
    Keyword arguments:
    days -- int，委托基础耗时天数
    speed -- int，队伍移动速度
    Return arguments:
    int | None -- 速度大于 1 返回分钟数，否则返回 None
    """
    if speed <= 1:
        return None
    return int(days * DAY_MINUTES * (0.9**speed))


def travel_days(days: int, speed: int) -> float:
    """
    按基础天数与队伍速度计算用于展示的预计耗时天数。
    Keyword arguments:
    days -- int，委托基础耗时天数
    speed -- int，队伍移动速度
    Return arguments:
    float -- 加速时保留一位小数的天数，否则返回原天数
    """
    minutes = travel_minutes(days, speed)
    return days if minutes is None else round(minutes / DAY_MINUTES, 1)


def readiness(
    commission_id: int, team: list[int], chosen: Mapping[int, int]
) -> Readiness:
    """
    汇总委托在当前队伍与载具配置下的各项就绪状态。
    Keyword arguments:
    commission_id -- int，委托编号
    team -- list[int]，当前派遣角色编号列表
    chosen -- Mapping[int, int]，载具编号到选定数量的映射
    Return arguments:
    Readiness -- 包含人数、运载量与需求满足标志的检查结果
    """
    demand = get_commission_demand_and_reward(commission_id, team)[0]
    capacity = fleet_capacity(chosen)
    return Readiness(
        people=len(team) >= game_config.config_commission[commission_id].people,
        capacity=capacity,
        capacity_ok=capacity >= capacity_need(commission_id),
        demand=demand,
    )


def available_vehicles() -> list[tuple[int, int]]:
    """
    返回当前有空闲数量的载具编号与可用数量列表。
    Return arguments:
    list[tuple[int, int]] -- (载具编号, 空闲数量) 列表
    """
    return [
        (vid, owned - out)
        for vid, (owned, out) in commission.vehicles().items()
        if owned - out > 0
    ]


def add_vehicle(chosen: dict[int, int], vehicle_id: int) -> None:
    """
    将指定载具选定数量加一并钳制到当前空闲上限。
    Keyword arguments:
    chosen -- dict[int, int]，原地更新的载具选择字典
    vehicle_id -- int，载具编号
    """
    chosen[vehicle_id] = chosen.get(vehicle_id, 0) + 1
    owned, out = commission.vehicles()[vehicle_id]
    chosen[vehicle_id] = min(chosen[vehicle_id], owned - out)


def remove_vehicle(chosen: dict[int, int], vehicle_id: int) -> None:
    """
    将指定载具选定数量减一，不大于 0 时移除该项。
    Keyword arguments:
    chosen -- dict[int, int]，原地更新的载具选择字典
    vehicle_id -- int，载具编号
    """
    if vehicle_id in chosen:
        chosen[vehicle_id] -= 1
        if chosen[vehicle_id] <= 0:
            chosen.pop(vehicle_id)


def toggle_member(
    team: list[int], lead: int, character_id: int, commission_id: int
) -> int:
    """
    切换角色在派遣队伍中的选中状态并维护队长编号。
    Keyword arguments:
    team -- list[int]，原地更新的派遣角色编号列表
    lead -- int，当前队长角色编号，无队长时为 0
    character_id -- int，要切换选中状态的角色编号
    commission_id -- int，委托编号，用于校验人数上限
    Return arguments:
    int -- 更新后的队长角色编号，移除队长后队伍为空时为 0
    """
    if character_id in team:
        team.remove(character_id)
        if character_id == lead:
            return team[0] if team else 0
        return lead
    if len(team) >= game_config.config_commission[commission_id].people:
        return lead
    team.append(character_id)
    return character_id if len(team) == 1 else lead


def default_lead(lead: int, team: list[int]) -> int:
    """
    在尚未指定队长且队伍非空时返回首位队员作为队长。
    Keyword arguments:
    lead -- int，当前队长角色编号
    team -- list[int]，派遣角色编号列表
    Return arguments:
    int -- 确定后的队长角色编号
    """
    if lead == 0 and team:
        return team[0]
    return lead


def lead_first(team: list[int], lead: int) -> None:
    """
    原地将队长角色移至派遣队伍列表的首位。
    Keyword arguments:
    team -- list[int]，原地调整顺序的派遣角色列表
    lead -- int，队长角色编号
    """
    team.remove(lead)
    team.insert(0, lead)


def dispatch(
    commission_id: int, team: list[int], chosen: Mapping[int, int]
) -> Dispatch:
    """
    执行派遣写入：扣需求、离队、占载具并登记进行中委托。
    Keyword arguments:
    commission_id -- int，委托编号
    team -- list[int]，派遣角色编号列表
    chosen -- Mapping[int, int]，载具编号到选定数量的映射
    Return arguments:
    Dispatch -- 包含预计耗时天数与返回时刻的派遣结果
    """
    days = game_config.config_commission[commission_id].time
    plain_return = game_time.get_sub_date(day=days)
    get_commission_demand_and_reward(commission_id, team, False, True)
    for cid in team:
        flags.set(cid, field_commission=commission_id)
        roster_lifecycle_service.chara_off_line(cid)
    vehicle_ids: list[int] = []
    for vid, count in chosen.items():
        commission.add_vehicle(vid, out=count)
        vehicle_ids.extend([vid] * count)
    minutes = travel_minutes(days, team_speed(vehicle_ids))
    if minutes is None:
        spent: float = days
        returns_at = plain_return
    else:
        spent = round(minutes / DAY_MINUTES, 1)
        returns_at = game_time.get_sub_date(minute=minutes)
    commission.start(commission_id, team, returns_at, vehicle_ids)
    return Dispatch(spent, returns_at)
