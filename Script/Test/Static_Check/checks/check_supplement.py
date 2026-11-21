# -*- coding: UTF-8 -*-
"""
静态检查系统 - 补充盲点检查
===========================
本模块实现 SUPP-01 与 SUPP-03 到 SUPP-08 七条检查。它们不属于任何单一领域的检查模块。
每条检查的文档字符串在「功能」一节以「来源:」注明来源编号。
失败消息以 "[warning] " 开头的是警示级，只作诊断参考。没有这个前缀的是错误级，命中即表示状态损坏。
"""

from __future__ import annotations

from Script.Core import cache_control
from Script.Config import game_config
from Script.Design import map_handle
from Script.Modules.domains import facility, flags, modes, needs, power, roster
from Script.Modules.domains import warehouse
from ..check_registry import CheckFailure, register_check, make_failure

from typing import TYPE_CHECKING
from Script.Modules.domains import chara_life

if TYPE_CHECKING:
    from Script.Core import game_type

# 场景路径列表 -> map_handle路径字符串；内部用os.sep拼接，禁止自己写分隔符
P = map_handle.get_map_system_path_str_for_list


def _all_current_effect_cids(ri: game_type.Rhodes_Island) -> list[int]:
    """
    参数:
        ri: cache.rhodes_island 罗德岛数据对象
    返回值:
        List[int]: 全部设施在其当前等级下对应的效果cid列表，单个设施数据缺失时静默跳过该设施
    功能:
        对应basement.get_base_updata()中"遍历全设施清单，按当前等级取效果cid"的只读复刻，
        供SUPP-03的开放覆盖判定复用，一次性计算避免对每个待开放项重复全表扫描
    """
    result = []
    facility_level = facility.levels()
    for facility_cid, facility_data in game_config.config_facility.items():
        try:
            level = facility_level.get(facility_cid)
            if type(level) is not int:
                continue
            facility_name = facility_data.name
            effect_data = game_config.config_facility_effect_data.get(
                facility_name
            )
            if effect_data is None or not (0 <= level < len(effect_data)):
                continue
            result.append(effect_data[level])
        except Exception:
            continue
    return result


@register_check("SUPP-01", "供电策略合法性")
def check_power_supply_strategy_validity() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        来源: IO-01。校验GameState全局键base.power_strategy（经power.strategies读）的键值域：
        键必须是当前配置中type==-1的大区块设施cid，值必须是game_config.config_supply_strategy的合法键。
        basement.calc_facility_efficiency先把子设施折算到父区块，再对策略配置做无保护索引，非法值会直接KeyError。
    """
    strategy = power.strategies()
    valid_zone_cids = {
        cid
        for cid, fac in game_config.config_facility.items()
        if getattr(fac, "type", None) == -1
    }
    valid_strategy_ids = set(game_config.config_supply_strategy)
    failures = []
    for zone_cid, strategy_id in strategy.items():
        if zone_cid not in valid_zone_cids:
            failures.append(
                make_failure(
                    "SUPP-01",
                    "供电策略合法性",
                    f"base.power_strategy中的键zone_cid={zone_cid}不是当前配置中type==-1的大区块设施cid"
                    f"（合法区块集合={sorted(valid_zone_cids)}），basement.calc_facility_efficiency按此键折算子设施供电策略时会取到脏数据",
                    [],
                )
            )
        if strategy_id not in valid_strategy_ids:
            failures.append(
                make_failure(
                    "SUPP-01",
                    "供电策略合法性",
                    f"base.power_strategy[{zone_cid}]={strategy_id}不在合法策略id集合{sorted(valid_strategy_ids)}中，"
                    f"basement.calc_facility_efficiency会对game_config.config_supply_strategy[{strategy_id}]做无保护索引，直接KeyError",
                    [],
                )
            )
    return failures


@register_check("SUPP-03", "设施开放派生单调覆盖")
def check_facility_open_monotonic_coverage() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        来源: IO-05。对当前config_facility_open中每个待开放项，只要其zone_cid已被全设施
        当前等级效果cid覆盖（相等，或同十位且个位数达标），对应facility_open[open_cid]就应为真。
        只迭代当前配置键，不查存档中的历史多余键；不检查反向"未覆盖就必须关闭"，因为开放只增不减，
        配置降级/mod可合法保留历史开放项。级别为warning：刷新同样只在打开面板时发生，跨版本读档到首次
        刷新前可合法不一致
    """
    cache = cache_control.cache
    ri = getattr(cache, "rhodes_island", None)
    if ri is None:
        return []
    effect_cids = _all_current_effect_cids(ri)
    if not effect_cids:
        return []
    facility_open = facility.opens()

    def _covered(zone_cid: int) -> bool:
        """
        参数:
            zone_cid (int): 待开放项要求的区块等级cid
        返回值:
            bool: 是否被全设施当前效果cid集合覆盖
        功能:
            basement.get_base_updata()中判定式的只读复刻：effect_cid==zone_cid，或同十位且effect_cid个位数>=zone_cid个位数
        """
        return any(
            effect_cid == zone_cid
            or (
                effect_cid // 10 == zone_cid // 10
                and effect_cid % 10 >= zone_cid % 10
            )
            for effect_cid in effect_cids
        )

    failures = []
    for open_cid, room in game_config.config_facility_open.items():
        zone_cid = getattr(room, "zone_cid", None)
        if type(zone_cid) is not int:
            continue
        if _covered(zone_cid) and not facility_open.get(open_cid, False):
            failures.append(
                make_failure(
                    "SUPP-03",
                    "设施开放派生单调覆盖",
                    (
                        f"[warning] 待开放项open_cid={open_cid}({getattr(room, 'name', '')})要求的zone_cid={zone_cid}已"
                        f"被当前设施等级效果覆盖，"
                        f"但facility_open.get({open_cid})={facility_open.get(open_cid, False)}，"
                        f"疑似开放派生表未刷新或get_base_updata()漏项"
                    ),
                    [],
                )
            )
    return failures


@register_check("SUPP-04", "时停无意识值跨名单残留")
def check_time_stop_unconscious_survives_off_list() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        来源: MO-03。非时停时，character_data中任何角色都不应残留专属时停无意识值
        unconscious_h==3；不得以是否在npc_id_got中过滤（TIME_STOP_ON/OFF都只扫描当时的npc_id_got|{0}，
        角色可能在时停中因访客离开或debug操作被移出名单，关闭时停后便再也清不到）。级别为warning：
        新周目继承整张character_data也可能把历史残留带入
    """
    cache = cache_control.cache
    if cache is None or modes.time_stop():
        return []
    character_data = getattr(cache, "character_data", {}) or {}
    npc_id_got: set[int] = roster.active()
    failures = []
    for cid, c in character_data.items():
        if flags.get(cid, "unconscious_h") != 3:
            continue
        failures.append(
            make_failure(
                "SUPP-04",
                "时停无意识值跨名单残留",
                (
                    f"[warning] 角色id={cid} name={getattr(c, 'name', '')}的sp_flag.unconscious_h=3，"
                    f"但当前time_stop_mode=False；"
                    f"是否在npc_id_got中={cid in npc_id_got}，"
                    f"field_commission={flags.get(cid, 'field_commission')}，"
                    f"escaping={flags.get(cid, 'escaping')}，be_bagged={flags.get(cid, 'be_bagged')}，"
                    f"vistor={flags.get(cid, 'vistor')}，position={getattr(c, 'position', None)}，"
                    f"疑似TIME_STOP_OFF清理范围漏掉了时停中已离开名单的角色"
                ),
                [cid],
            )
        )
    return failures


@register_check("SUPP-05", "愤怒值下界")
def check_angry_point_lower_bound() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        来源: NO-01。校验每个角色的愤怒值（needs.of(cid)["angry"]）是int且不小于0。
        道歉等指令减愤怒值时以0为下限，本条防新的写入破坏这一点。级别为warning
    """
    cache = cache_control.cache
    character_data = getattr(cache, "character_data", {}) or {}
    failures = []
    for cid, c in character_data.items():
        angry_point = needs.of(cid)["angry"]
        if type(angry_point) is not int or angry_point < 0:
            failures.append(
                make_failure(
                    "SUPP-05",
                    "愤怒值下界",
                    f"[warning] 角色id={cid} name={getattr(c, 'name', '')}的angry_point={angry_point}，类型或值不满足"
                    f"type是int且>=0",
                    [cid],
                )
            )
    return failures


@register_check("SUPP-07", "仓储扩展模块使用数非负")
def check_used_extra_warehouse_capacity_module_non_negative() -> (
    list[CheckFailure]
):
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        来源: NO-05（只取独立于NUM-26的后半式）。校验base.warehouse_modules（warehouse.extra_modules()）
        类型为int且不小于0。warehouse.capacity()按 仓储区设施效果+模块数*200 算仓库容量，
        装配线结算每产出一个模块，模块数加1，容量随之多200。负数没有玩法语义，会把容量往下扣，
        可能在基础容量仍足够大时绕过NUM-26的warehouse.capacity()>=0检查。使用type(v) is int以拒绝bool
    """
    cache = cache_control.cache
    ri = getattr(cache, "rhodes_island", None)
    if ri is None:
        return []
    used = warehouse.extra_modules()
    if type(used) is not int or used < 0:
        return [
            make_failure(
                "SUPP-07",
                "仓储扩展模块使用数非负",
                (
                    f"base.warehouse_modules={used}，类型或值不满足type是int且>=0；"
                    f"facility_level[3]={facility.levels().get(3)}"
                ),
                [],
            )
        ]
    return []


@register_check("SUPP-08", "办公室场景引用合法")
def check_officeroom_reference_valid() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        来源: PO-02。校验character_data中每个角色的officeroom（列表字段）只允许是空列表或
        cache.scene_data的合法键。officeroom非空时会被角色信息面板交给get_scene_path_text，后者把坐标
        拼成路径后直接索引cache.scene_data；存档迁移只原样复制而不校验。级别为warning：当前主要后果是
        打开角色信息时渲染失败，且旧档兼容是主要来源
    """
    cache = cache_control.cache
    character_data = getattr(cache, "character_data", {}) or {}
    scene_data = getattr(cache, "scene_data", {}) or {}
    failures = []
    for cid, c in character_data.items():
        officeroom = chara_life.officeroom(cid)
        if not officeroom:
            continue
        if not (
            isinstance(officeroom, list)
            and all(isinstance(p, str) for p in officeroom)
            and P(officeroom) in scene_data
        ):
            failures.append(
                make_failure(
                    "SUPP-08",
                    "办公室场景引用合法",
                    (
                        f"[warning] 角色id={cid} name={getattr(c, 'name', '')}的officeroom={officeroom}非空但不是cache."
                        f"scene_data的合法键，"
                        f"打开该角色信息面板时get_scene_path_text会索引失败；position={getattr(c, 'position', None)}"
                    ),
                    [cid],
                )
            )
    return failures
