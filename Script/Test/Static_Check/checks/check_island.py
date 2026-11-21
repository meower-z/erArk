# -*- coding: UTF-8 -*-
"""
静态检查系统 - 基建/宿舍/岗位/资源/娱乐经营域检查
覆盖 ISLAND-01…ISLAND-33，校验 cache.rhodes_island（罗德岛基建总数据）与相关派生结构（岗位集合与列表、
设施等级与开放表、资源仓储、生产/农业/招募/交易线、宿舍管理员、图书借阅、派对排期、动力区、外勤委托、
监狱、访客与外交官映射等）的内部一致性。

全域前提（详见需求文档"约定与全域前提"一节，各检查函数按需复用）：
- 离线判定只能读 sp_flag.field_commission / escaping / be_bagged / in_diplomatic_visit 这几个来源标记，
  绝不能用"是否在 cache.npc_id_got 里"或"position == ['0','0']"判断角色是否离线在场——外勤、越狱、被绑架、
  外派外交官都会把角色移出名单但保留其岗位/槽位数据。
- 派生表（岗位集合/列表等）只由玩家打开对应面板时触发重算，没有任何每日/每回合结算刷新点，因此"派生表与
  实时名单逐人相等"类断言天然可能长期漂移，此类条目统一为 warning 级。
- 本文件所有检查函数都只读 cache，不做任何写入；对 cache.rhodes_island 及角色字段的访问一律用
  getattr/.get 加默认值，避免老存档缺字段时检查函数自身抛出未被期望的异常掩盖真实问题。
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from Script.Core import cache_control
from Script.Config import game_config
from Script.Modules.domains import (
    commission,
    diplomacy,
    dormitory,
    economy,
    facility,
    library,
    location,
    power,
    production,
    recruit,
    visitor,
    warehouse,
    work,
)
from Script.System.Dormitory_System import common as dorm_common
from ..check_registry import CheckFailure, register_check, make_failure

from typing import TYPE_CHECKING
from Script.Design import game_time

if TYPE_CHECKING:
    from Script.Core import game_type


def _eff(ri: game_type.Rhodes_Island, facility_cid: int) -> int | None:
    """
    参数:
        ri: cache.rhodes_island 罗德岛数据对象
        facility_cid (int): 设施配置cid（config_facility的键）
    返回值:
        int|None: 该设施在其当前等级下的效果数值(config_facility_effect.effect)，任何一环缺失/越界时返回None
    功能:
        对应需求文档中的 _eff(fid) 帮助函数：config_facility_effect[config_facility_effect_data[名字][等级]].effect，
        全程防御式访问，供多条检查复用，任一层级配置/存档字段缺失都安全地返回None而不抛异常
    """
    try:
        facility_data = game_config.config_facility.get(facility_cid)
        if facility_data is None:
            return None
        level = facility.levels().get(facility_cid)
        if type(level) is not int:
            return None
        effect_data = game_config.config_facility_effect_data.get(
            facility_data.name
        )
        if effect_data is None or not (0 <= level < len(effect_data)):
            return None
        effect_cid = effect_data[level]
        effect = game_config.config_facility_effect.get(effect_cid)
        if effect is None:
            return None
        return effect.effect
    except Exception:
        return None


def _chara_name(cd: dict[int, Any], cid: int) -> str:
    """
    参数:
        cd (Dict[int, Any]): cache.character_data 角色数据字典
        cid: 待查询的角色id
    返回值:
        str: 角色名字，角色不存在时返回"(不存在)"
    功能:
        安全获取角色名字，供各失败消息拼接使用
    """
    ch = cd.get(cid)
    return getattr(ch, "name", "?") if ch is not None else "(不存在)"


def _sp_flag_brief(ch: Any) -> str:
    """
    参数:
        ch: 角色对象
    返回值:
        str: 该角色离线相关标记的简要描述，形如 "field_commission=3,escaping=False,be_bagged=False,
        in_diplomatic_visit=0"
    功能:
        统一提取全域前提中约定的四个离线来源标记，供失败消息展示，用于判断"离线残留"还是"真实联动缺陷"
    """
    sp_flag = getattr(ch, "sp_flag", None)
    return (
        f"field_commission={getattr(sp_flag, 'field_commission', '?')},"
        f"escaping={getattr(sp_flag, 'escaping', '?')},"
        f"be_bagged={getattr(sp_flag, 'be_bagged', '?')},"
        f"in_diplomatic_visit={getattr(sp_flag, 'in_diplomatic_visit', '?')}"
    )


@register_check("ISLAND-01", "干员名单引用完整性")
def check_island_01_npc_id_got_ref() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验cache.npc_id_got中的每个id都存在于cache.character_data，且0号玩家角色存在。大量核心循环拿名单id
        直接无保护索引角色数据，缺一个即崩。应先于本域其余检查运行——ISLAND-07/09/19等都会用名单id索引角色，
        缺失时它们会抛检查器异常而不是给出清晰结论
    """
    cache = cache_control.cache
    cd = cache.character_data
    failures = []
    if 0 not in cd:
        failures.append(
            make_failure(
                "ISLAND-01",
                "干员名单引用完整性",
                "0号玩家角色在character_data中不存在",
                [],
            )
        )
    ghost_ids = [cid for cid in cache.npc_id_got if cid not in cd]
    if ghost_ids:
        failures.append(
            make_failure(
                "ISLAND-01",
                "干员名单引用完整性",
                f"npc_id_got中存在幽灵cid列表={ghost_ids}，len(npc_id_got)={len(cache.npc_id_got)}，"
                f"len(character_data)={len(cd)}，0 in character_data={0 in cd}",
                ghost_ids,
            )
        )
    return failures


@register_check("ISLAND-02", "设施等级键完整且落在配置区间")
def check_island_02_facility_level_range() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验当前配置的每个设施都在facility_level中有等级记录，且等级是int、落在该设施效果表的合法下标区间。
        缺键或越界会让config_facility_effect_data[name][level]直接下标失败。用<=而非==比较键集：读档只补当前
        配置缺键、从不删旧键，csv删设施后旧档会留多余键，多余键单独作迁移告警，不对多余键取config_facility[fid]
    """
    facility_level = facility.levels()
    failures = []
    missing = [
        fid for fid in game_config.config_facility if fid not in facility_level
    ]
    violations = []
    for fid, facility_data in game_config.config_facility.items():
        if fid not in facility_level:
            continue
        lv = facility_level[fid]
        effect_data = game_config.config_facility_effect_data.get(
            facility_data.name, []
        )
        if type(lv) is not int or not (1 <= lv < len(effect_data)):
            violations.append(
                (fid, facility_data.name, lv, len(effect_data) - 1)
            )
    extra_keys = sorted(set(facility_level) - set(game_config.config_facility))
    if missing or violations:
        failures.append(
            make_failure(
                "ISLAND-02",
                "设施等级键完整且落在配置区间",
                f"缺失的fac_cid列表={missing}，违规(fac_cid,设施名,lv,该设施最高级)={violations}，"
                f"历史多余键={extra_keys}",
                [],
            )
        )
    return failures


@register_check("ISLAND-03", "非控制中枢设施等级不超过中枢等级+1")
def check_island_03_facility_level_vs_core() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验除控制中枢(cid 0)自身外，任一设施等级不得高于控制中枢等级+1。唯一升级写点的门槛正是如此约束，
        豁免范围恰好只有控制中枢自身
    """
    facility_level = facility.levels()
    if 0 not in facility_level:
        return []
    core_lv = facility_level[0]
    violations = [
        (fid, game_config.config_facility[fid].name, facility_level[fid])
        for fid in game_config.config_facility
        if fid != 0
        and fid in facility_level
        and facility_level[fid] > core_lv + 1
    ]
    if violations:
        return [
            make_failure(
                "ISLAND-03",
                "非控制中枢设施等级不超过中枢等级+1",
                f"控制中枢等级facility_level[0]={core_lv}，违规(fac_cid,设施名,lv)={violations}",
                [],
            )
        ]
    return []


@register_check("ISLAND-04", "设施开放表键完整、值为0/1语义")
def check_island_04_facility_open_values() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验当前配置的每个可开放设施都在facility_open中有开放记录，值必须是True/False或语义等价的1/0。
        不能写type(v) is bool——debug面板"设施全满级、全开放"写的是整数1，一旦用过全表都变int
    """
    facility_open = facility.opens()
    missing = [
        oid
        for oid in game_config.config_facility_open
        if oid not in facility_open
    ]
    illegal = [
        (
            oid,
            game_config.config_facility_open[oid].name,
            repr(facility_open[oid]),
            type(facility_open[oid]).__name__,
        )
        for oid in game_config.config_facility_open
        if oid in facility_open
        and facility_open[oid] not in (True, False, 0, 1)
    ]
    if missing or illegal:
        return [
            make_failure(
                "ISLAND-04",
                "设施开放表键完整、值为0/1语义",
                f"缺失的open_cid列表={missing}，非法值的(open_cid,设施名,repr(value),type)={illegal}",
                [],
            )
        ]
    return []


@register_check("ISLAND-05", "资源表键完整且库存为非负整数")
def check_island_05_resource_stock() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验当前Resource.csv的每种资源都在base.stock中有库存记录，值必须是非负int。负库存意味着某处扣减漏了余额检查。
        同样用<=比较键集：读档只补缺的配置资源，不删已下线的资源id。已知合法误报源：debug面板可以把资源1、2、4
        的库存设成任意整数（含负数）。失败上下文附带cache.debug_mode供排查时参考，但不作硬豁免
    """
    cache = cache_control.cache
    materials = warehouse.stock()
    missing = [
        rid for rid in game_config.config_resouce if rid not in materials
    ]
    violations = [
        (
            rid,
            game_config.config_resouce[rid].name,
            materials[rid],
            type(materials[rid]).__name__,
        )
        for rid in game_config.config_resouce
        if rid in materials
        and not (type(materials[rid]) is int and materials[rid] >= 0)
    ]
    extra_keys = sorted(set(materials) - set(game_config.config_resouce))
    if missing or violations:
        return [
            make_failure(
                "ISLAND-05",
                "资源表键完整且库存为非负整数",
                f"缺失的rid列表={missing}，违规(rid,资源名,数量,type)={violations}，历史多余键={extra_keys}，"
                f"cache.debug_mode={getattr(cache, 'debug_mode', '?')}",
                [],
            )
        ]
    return []


@register_check("ISLAND-06", "仓库容量与干员上限是设施等级的派生值")
def check_island_06_warehouse_and_people_max() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验warehouse_capacity == 仓储区(cid 3)当前等级效果 + 已用仓储扩展模块数*200，
        people_max == 宿舍区(cid 4)当前等级效果。唯一合法漂移窗口是跨版本改配置效果值后、玩家首次打开
        相关面板之前，效果表本身缺失时退化为跳过
    """
    cache = cache_control.cache
    ri = cache.rhodes_island
    eff3 = _eff(ri, 3)
    eff4 = _eff(ri, 4)
    if eff3 is None or eff4 is None:
        return []
    failures = []
    warehouse_capacity = getattr(ri, "warehouse_capacity", None)
    used_extra = warehouse.extra_modules()
    expected_warehouse = eff3 + used_extra * 200
    if warehouse_capacity != expected_warehouse:
        failures.append(
            make_failure(
                "ISLAND-06",
                "仓库容量与干员上限是设施等级的派生值",
                f"ri.warehouse_capacity={warehouse_capacity}，期望值=_eff(3)({eff3})+"
                f"base.warehouse_modules({used_extra})*200={expected_warehouse}，"
                f"facility_level[3]={facility.levels().get(3)}，"
                f"本次读档后是否打开过基建/建造面板需人工排查",
                [],
            )
        )
    people_max = getattr(ri, "people_max", None)
    if people_max != eff4:
        failures.append(
            make_failure(
                "ISLAND-06",
                "仓库容量与干员上限是设施等级的派生值",
                f"ri.people_max={people_max}，期望值=_eff(4)={eff4}，"
                f"facility_level[4]={facility.levels().get(4)}，"
                f"本次读档后是否打开过基建/建造面板需人工排查",
                [],
            )
        )
    return failures


@register_check("ISLAND-07", "已招募干员的岗位id必须合法")
def check_island_07_work_type_valid() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验每个在编非玩家干员的work.work_type存在于WorkType.csv。非法值在下一次刷新时会进岗位名册；
        cid in cd的守卫交给ISLAND-01，这里再判一次只是防止本条自身抛异常
    """
    cache = cache_control.cache
    cd = cache.character_data
    valid_work_types = set(game_config.config_work_type)
    failures = []
    for cid in cache.npc_id_got:
        if cid == 0 or cid not in cd:
            continue
        work_type = cd[cid].work.work_type
        if work_type not in valid_work_types:
            failures.append(
                make_failure(
                    "ISLAND-07",
                    "已招募干员的岗位id必须合法",
                    f"角色cid={cid}({cd[cid].name})的work.work_type={work_type}不在合法岗位集合"
                    f"{sorted(valid_work_types)}中",
                    [cid],
                )
            )
    return failures


@register_check("ISLAND-08", "岗位名册的岗位合法、成员合法且与所在岗位自洽")
def check_island_08_work_rosters_self_consistent() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验岗位名册（work.rosters）的每个岗位id都在岗位配置里；名册里的每个id必须是存在的角色，且其work.work_type
        必须等于所在岗位。绝不能加cid in cache.npc_id_got——外勤/关押/外派会把人移出名单而名册保留他，
        是主线玩法下的必现误报
    """
    cache = cache_control.cache
    cd = cache.character_data
    rosters = work.rosters()
    key_diff_extra = sorted(set(rosters) - set(game_config.config_work_type))
    violations: list[tuple[Any, Any, str, int | None]] = []
    for wid, ids in rosters.items():
        for cid in ids:
            if cid not in cd:
                violations.append((wid, cid, "不存在", None))
            elif cd[cid].work.work_type != wid:
                violations.append(
                    (wid, cid, cd[cid].name, cd[cid].work.work_type)
                )
    if key_diff_extra or violations:
        return [
            make_failure(
                "ISLAND-08",
                "岗位名册的岗位合法、成员合法且与所在岗位自洽",
                f"多余的work_id={key_diff_extra}，"
                f"违规(work_id,cid,name,实际work_type)={violations}",
                [v[1] for v in violations],
            )
        ]
    return []


@register_check("ISLAND-09", "岗位集合与在编名单的逐人重算一致")
def check_island_09_work_set_recompute() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验按当前在编名单逐人重算的岗位集合应与岗位名册一致。只能是告警，有两个合法漂移源：外交任免直接改
        work.work_type却不调update_work_people()；离线角色留在名册里而重算式扫不到他。报告时按sp_flag把
        "离线残留"与"面板漏刷新"分类
    """
    cache = cache_control.cache
    cd = cache.character_data
    failures = []
    for wid in game_config.config_work_type:
        cached_set = set(work.roster(wid))
        recompute_set = {
            cid
            for cid in cache.npc_id_got
            if cid != 0 and cid in cd and cd[cid].work.work_type == wid
        }
        extra = cached_set - recompute_set
        missing = recompute_set - cached_set
        if not extra and not missing:
            continue
        detail = [
            (
                f"cid={cid},name={_chara_name(cd, cid)},"
                f"work_type={getattr(cd.get(cid), 'work', None) and cd[cid].work.work_type},"
                f"{_sp_flag_brief(cd.get(cid))}"
            )
            for cid in sorted(extra | missing)
        ]
        failures.append(
            make_failure(
                "ISLAND-09",
                "岗位集合与在编名单的逐人重算一致",
                f"[warning] 岗位work_id={wid}：多出的cid={sorted(extra)}，缺失的cid={sorted(missing)}，明细={detail}",
                sorted(extra | missing),
            )
        )
    return failures


# 三个岗位派生列表与对应的岗位id，ISLAND-11/ISLAND-12共用
_WORK_LIST_FIELDS = (
    ("production_worker_ids", 121),
    ("herb_garden_operator_ids", 161),
    ("green_house_operator_ids", 162),
)


def _work_list(field: str) -> list[int]:
    """ISLAND-11/12 的岗位人员列表，即 production.PICKLED_WORKERS[field] 这一类生产线的工人名单"""
    return production.workers(production.PICKLED_WORKERS[field])


@register_check("ISLAND-11", "岗位人员列表引用合法、无重复、不漏在岗者")
def check_island_11_work_lists_superset() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验三个岗位派生列表引用合法、无重复、不漏在岗者。列表成员必须是存在的角色，且岗位与列表对应。
        每个列表必须包含对应岗位名册的全部成员，漏人是真bug。三个列表都只断言超集，不报多出的成员。
        多出来的是离线残留，合法可达，交给ISLAND-12
    """
    cd = cache_control.cache.character_data
    failures = []
    for field, wid in _WORK_LIST_FIELDS:
        lst = _work_list(field)
        dup = [cid for cid, cnt in Counter(lst).items() if cnt > 1]
        mismatched = [
            (
                cid,
                _chara_name(cd, cid),
                cd[cid].work.work_type if cid in cd else None,
            )
            for cid in lst
            if cid not in cd or cd[cid].work.work_type != wid
        ]
        expected = set(work.roster(wid))
        missing = expected - set(lst)
        if dup or mismatched or missing:
            detail = [
                f"cid={cid},{_sp_flag_brief(cd.get(cid))}"
                for cid in sorted(set(dup) | missing)
            ]
            failures.append(
                make_failure(
                    "ISLAND-11",
                    "岗位人员列表引用合法、无重复、不漏在岗者",
                    f"列表{field}(work_id={wid})：重复cid={dup}，岗位不匹配(cid,name,work_type)={mismatched}，"
                    f"漏人(缺失的cid)={sorted(missing)}，明细={detail}",
                    sorted(set(dup) | missing),
                )
            )
    return failures


@register_check("ISLAND-12", "岗位人员列表的离线残留漂移")
def check_island_12_work_lists_stale_members() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        [warning] 校验三个增量维护的岗位列表应与对应岗位名册严格相等。出现多余成员说明列表在两次刷新之间
        滞后于成员实际状态。日结时update_work_people()会整体重置并按在编角色重建这些列表，本条覆盖的是
        两次重建之间可能出现的瞬态漂移
    """
    cd = cache_control.cache.character_data
    failures = []
    for field, wid in _WORK_LIST_FIELDS:
        lst = _work_list(field)
        expected = set(work.roster(wid))
        stale = set(lst) - expected
        if not stale:
            continue
        detail = [
            f"cid={cid},name={_chara_name(cd, cid)},{_sp_flag_brief(cd.get(cid))}"
            for cid in sorted(stale)
        ]
        failures.append(
            make_failure(
                "ISLAND-12",
                "岗位人员列表的离线残留漂移",
                f"[warning] 列表{field}(work_id={wid})存在离线残留cid={sorted(stale)}，明细={detail}",
                sorted(stale),
            )
        )
    return failures


@register_check("ISLAND-13", "流水线结构、数量与配方id合法")
def check_island_13_assembly_line() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验制造加工区(cid 12)等级N恰好开放0..N-1号流水线。流水线从 base.production 读。
        每条线的生产配方id在配方表里，上次结算的小时是 0..23 的 int
    """
    assembly_line = production.lines("assembly")
    facility_level = facility.levels()
    if 12 not in facility_level:
        return []
    failures = []
    expected_keys = set(range(facility_level[12]))
    actual_keys = set(assembly_line)
    if expected_keys != actual_keys:
        failures.append(
            make_failure(
                "ISLAND-13",
                "流水线结构、数量与配方id合法",
                f"facility_level[12]={facility_level[12]}，实际线号集合={sorted(actual_keys)}，"
                f"期望线号集合={sorted(expected_keys)}",
                [],
            )
        )
    violations = []
    for line_id, v in assembly_line.items():
        if v["product"] not in game_config.config_productformula:
            violations.append((line_id, dict(v)))
            continue
        if type(v["hour"]) is not int or not (0 <= v["hour"] <= 23):
            violations.append((line_id, dict(v)))
    if violations:
        failures.append(
            make_failure(
                "ISLAND-13",
                "流水线结构、数量与配方id合法",
                f"违规line_id与整条记录={violations}",
                [],
            )
        )
    return failures


@register_check("ISLAND-14", "农业线结构、种植类型合法")
def check_island_14_agriculture_line_structure() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验药田线与温室线（从 base.production 读）的种植类型是0(停种)或该线允许的资源，药田为11，温室为16。
        这两种资源取自种植面板 select_agriculture_line_produce 的候选
    """
    failures = []

    def _check_line(field: str, allowed_types: tuple[int, ...]) -> None:
        violations = [
            (line_id, dict(v))
            for line_id, v in production.lines(field).items()
            if v["product"] not in allowed_types
        ]
        if violations:
            failures.append(
                make_failure(
                    "ISLAND-14",
                    "农业线结构、种植类型合法",
                    f"线{field}：违规line_id与整条记录={violations}，允许的种植类型v[0]={allowed_types}",
                    [],
                )
            )

    _check_line("herb_garden", (0, 11))
    _check_line("green_house", (0, 16))
    return failures


@register_check(
    "ISLAND-15", "各生产/招募/交易线主负责人有效、岗位匹配、同类不重复"
)
def check_island_15_line_main_operator() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验流水线(岗位121)、药田(161)、温室(162)、招募线(71)的主负责人与各资源类型主交易员(111)有效。
        四类线的主负责人必须是0或一名岗位与该线一致的存在角色，且在对应岗位人员列表中。同类线内一人不得主理两条。
        前三类的线与人员列表从 base.production 读。base.main_traders 里的主交易员必须是0或一名职位为111的存在角色。
        不要求主负责人在npc_id_got：主管、种植员与招聘专员都能被派外勤，岗位与槽位都保留
    """
    cache = cache_control.cache
    cd = cache.character_data
    failures = []
    main_list = {
        **{wid: production.workers(k) for k, wid in production.KINDS.items()},
        71: work.roster(work.HR_WORK),
    }
    slots = {
        kind: (wid, [(i, v["main"]) for i, v in production.lines(kind).items()])
        for kind, wid in production.KINDS.items()
    }
    recruit_mains = [(i, v["main"]) for i, v in recruit.lines().items()]
    slots["recruit_line"] = (71, recruit_mains)
    for line_name, (wid, pairs) in slots.items():
        mains = [(line_id, m) for line_id, m in pairs if m]
        occupant_count = Counter(m for _lid, m in mains)
        dup = {m for m, cnt in occupant_count.items() if cnt > 1}
        illegal = [
            (line_id, m)
            for line_id, m in mains
            if not (
                type(m) is int
                and m in cd
                and cd[m].work.work_type == wid
                and m in main_list.get(wid, [])
            )
        ]
        if dup or illegal:
            dup_lines = sorted(line_id for line_id, m in mains if m in dup)
            detail = [
                (
                    f"line_id={lid},m={m},{_chara_name(cd, m)},work_type={cd[m].work.work_type if m in cd else None},"
                    f"{_sp_flag_brief(cd.get(m))}"
                )
                for lid, m in illegal
            ]
            failures.append(
                make_failure(
                    "ISLAND-15",
                    "各生产/招募/交易线主负责人有效、岗位匹配、同类不重复",
                    f"线{line_name}：重复占用的line_id列表={dup_lines}，非法槽位明细(line_id,槽位值)={illegal}，"
                    f"详情={detail}，岗位列表={main_list.get(wid)}",
                    [m for _lid, m in illegal if type(m) is int],
                )
            )
    illegal_traders = [
        (rtype, m)
        for rtype, m in economy.main_traders().items()
        if m and not (m in cd and cd[m].work.work_type == economy.TRADER_WORK)
    ]
    if illegal_traders:
        detail = [
            f"type={t},m={m},{_chara_name(cd, m)},work_type={cd[m].work.work_type if m in cd else None}"
            for t, m in illegal_traders
        ]
        failures.append(
            make_failure(
                "ISLAND-15",
                "各生产/招募/交易线主负责人有效、岗位匹配、同类不重复",
                f"{economy.TRADERS}非法槽位={illegal_traders}，详情={detail}",
                [m for _t, m in illegal_traders],
            )
        )
    return failures


@register_check("ISLAND-16", "宿舍管理员表结构与引用合法")
def check_island_16_dormitory_managers_structure() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验dormitory.managers()的键只能是1..9层；值是0(未任命)或一名存在的角色；同一人不得同时管理两层。
        用<=而非==range(1,10)：旧档若存在残缺字典不会被修复；缺层
        不会崩溃，全部消费点都用.get(layer,0)。不要求管理员在npc_id_got（舍管可被派外勤）
    """
    cache = cache_control.cache
    cd = cache.character_data
    dormitory_managers = dormitory.managers()
    illegal_layers = [
        layer for layer in dormitory_managers if layer not in range(1, 10)
    ]
    illegal_values = [
        (layer, m)
        for layer, m in dormitory_managers.items()
        if not (type(m) is int and m >= 0)
    ]
    non_zero = [(layer, m) for layer, m in dormitory_managers.items() if m]
    manager_ids = [m for _layer, m in non_zero]
    dup_managers = [m for m, cnt in Counter(manager_ids).items() if cnt > 1]
    ghost_ids = [(layer, m) for layer, m in non_zero if m not in cd]
    if illegal_layers or illegal_values or dup_managers or ghost_ids:
        return [
            make_failure(
                "ISLAND-16",
                "宿舍管理员表结构与引用合法",
                (
                    f"dormitory_managers全量={dormitory_managers}，非法层键={illegal_layers}，"
                    f"非法值={illegal_values}，"
                    f"重复管理员及其层号={[(m, [n for n, mm in non_zero if mm == m]) for m in dup_managers]}，"
                    f"不存在的cid={ghost_ids}"
                ),
                [m for m in manager_ids if m in dup_managers]
                + [m for _l, m in ghost_ids],
            )
        ]
    return []


@register_check("ISLAND-17", "宿舍管理员岗位联动与层键覆盖")
def check_island_17_dormitory_manager_work_type_and_layers() -> (
    list[CheckFailure]
):
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        [warning] 校验每个被任命的管理员的work.work_type应为31，且1..9层键应齐全。前者失败指向一处真实的
        联动缺失（select_new_work把现任舍管改派成别的岗位时只改work.work_type，不碰各层管理员），
        后者指向旧档迁移残缺
    """
    cache = cache_control.cache
    cd = cache.character_data
    dormitory_managers = dormitory.managers()
    failures = []
    missing_layers = sorted(set(range(1, 10)) - set(dormitory_managers))
    if missing_layers:
        failures.append(
            make_failure(
                "ISLAND-17",
                "宿舍管理员岗位联动与层键覆盖",
                f"[warning] dormitory_managers缺失的层键={missing_layers}",
                [],
            )
        )
    mismatched = [
        (layer, m, _chara_name(cd, m), cd[m].work.work_type)
        for layer, m in dormitory_managers.items()
        if m and m in cd and cd[m].work.work_type != 31
    ]
    if mismatched:
        failures.append(
            make_failure(
                "ISLAND-17",
                "宿舍管理员岗位联动与层键覆盖",
                f"[warning] 管理员岗位不为31的(layer,manager_id,name,实际work_type)={mismatched}，"
                f"work.roster(31)={work.roster(31)}",
                [m for _layer, m, _n, _w in mismatched],
            )
        )
    return failures


@register_check("ISLAND-18", "已关闭楼层不得保留管理员")
def check_island_18_closed_layer_no_manager() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验层号高于当前宿舍区等级理论开放上限的层，其管理员必须为0。低优先级、近乎恒真的守卫；
        任命入口只对open_layers出按钮，实际只能抓存档编辑/mod
    """
    cache = cache_control.cache
    cd = cache.character_data
    dormitory_managers = dormitory.managers()
    try:
        max_open_layer = dorm_common.get_dormitory_max_open_layer()
    except Exception:
        return []
    violations = [
        (layer, mid, _chara_name(cd, mid))
        for layer, mid in dormitory_managers.items()
        if not (layer <= max_open_layer or mid == 0)
    ]
    if violations:
        return [
            make_failure(
                "ISLAND-18",
                "已关闭楼层不得保留管理员",
                f"facility_level[4]={facility.levels().get(4)}，"
                f"get_dormitory_max_open_layer()={max_open_layer}，违规(layer,manager_id,name)={violations}",
                [v[1] for v in violations],
            )
        ]
    return []


@register_check("ISLAND-19", "已招募干员的宿舍路径必须是合法场景")
def check_island_19_dormitory_path_valid() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验每个在编非玩家干员的dormitory必须非空且是cache.scene_data的合法键，不得残留""或模板值"无"。
        面板是模态阻塞的，回合快照看不到面板中途状态，不因"可能在编辑面板内"而抑制本条
    """
    cache = cache_control.cache
    cd = cache.character_data
    failures = []
    for cid in cache.npc_id_got:
        if cid == 0 or cid not in cd:
            continue
        ch = cd[cid]
        dormitory = getattr(ch, "dormitory", None)
        if dormitory and dormitory in cache.scene_data:
            continue
        failures.append(
            make_failure(
                "ISLAND-19",
                "已招募干员的宿舍路径必须是合法场景",
                f"角色cid={cid}({ch.name})的dormitory={dormitory!r}非法（务必区分''/'无'/其他非法路径），"
                f"permanent_dormitory={getattr(ch, 'permanent_dormitory', None)!r}，work.work_type={ch.work.work_type}",
                [cid],
            )
        )
    return failures


@register_check("ISLAND-20", "普通宿舍房间不超过2人")
def check_island_20_dormitory_room_capacity() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        [warning] 校验普通宿舍房设计容量2人；超员说明分配逻辑或特殊搬迁把人塞进了满房。永不判失败——代码自身
        容忍超员（max(2,实际人数)撑容量），超员可以合法持续到玩家升级宿舍；本函数仅在确有超员时给出经营告警
    """
    cache = cache_control.cache
    cd = cache.character_data
    try:
        resident_ids = dorm_common.get_dormitory_resident_id_set()
    except Exception:
        return []
    occ: dict[str, list[int]] = {}
    for cid in resident_ids:
        ch = cd.get(cid)
        if ch is None:
            continue
        occ.setdefault(ch.dormitory, []).append(cid)
    failures = []
    for path, cids in occ.items():
        try:
            layer = dorm_common.get_layer_by_dormitory_path(path)
        except Exception:
            layer = 0
        if not layer or len(cids) <= 2:
            continue
        residents = [
            (cid, cd[cid].name, cd[cid].work.work_type) for cid in cids
        ]
        scene_name = (
            getattr(cache.scene_data.get(path), "name", path)
            if path in getattr(cache, "scene_data", {})
            else path
        )
        failures.append(
            make_failure(
                "ISLAND-20",
                "普通宿舍房间不超过2人",
                f"[warning] 房间路径={path}(场景名={scene_name})，层号={layer}，人数={len(cids)}，住户={residents}，"
                f"materials_resouce仅供参考不代表空床数",
                cids,
            )
        )
    return failures


@register_check("ISLAND-21", "借书记录双向一致且不超借阅上限")
def check_island_21_book_borrow_consistency() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验library.holders()[book]=借阅者id(-1未借出，0为玩家)与角色的entertainment.borrow_book_id_set必须
        互为反向索引；书籍id必须合法；单人持书不超过3本。两处状态必须成对更新，是典型易漏点；书籍id合法性
        不是冗余——自动借书直接索引config_book[book_id]，失效键会崩
    """
    cache = cache_control.cache
    cd = cache.character_data
    book_borrow_dict = library.holders()
    failures = []
    for book, holder in book_borrow_dict.items():
        if book not in game_config.config_book:
            failures.append(
                make_failure(
                    "ISLAND-21",
                    "借书记录双向一致且不超借阅上限",
                    f"book_id={book}不在config_book中，holder={holder}",
                    [],
                )
            )
            continue
        book_name = game_config.config_book[book].name
        if holder == -1:
            continue
        if (
            holder not in cd
            or book not in cd[holder].entertainment.borrow_book_id_set
        ):
            failures.append(
                make_failure(
                    "ISLAND-21",
                    "借书记录双向一致且不超借阅上限",
                    (
                        f"book_id={book}({book_name})记录holder={holder}({_chara_name(cd, holder)})，"
                        f"但其borrow_book_id_set="
                        f"{cd[holder].entertainment.borrow_book_id_set if holder in cd else '(角色不存在)'}中不含该书"
                    ),
                    [holder] if holder in cd else [],
                )
            )
    for cid, ch in cd.items():
        borrow_set = ch.entertainment.borrow_book_id_set
        if len(borrow_set) > 3:
            failures.append(
                make_failure(
                    "ISLAND-21",
                    "借书记录双向一致且不超借阅上限",
                    f"角色cid={cid}({ch.name})持书数={len(borrow_set)}超过上限3，borrow_book_id_set={borrow_set}",
                    [cid],
                )
            )
        mismatched = [b for b in borrow_set if book_borrow_dict.get(b) != cid]
        if mismatched:
            failures.append(
                make_failure(
                    "ISLAND-21",
                    "借书记录双向一致且不超借阅上限",
                    f"角色cid={cid}({ch.name})的borrow_book_id_set中book_id={mismatched}在book_borrow_dict里未指回该角色，"
                    f"反向不一致明细={[(b, book_borrow_dict.get(b)) for b in mismatched]}",
                    [cid],
                )
            )
    return failures


@register_check("ISLAND-22", "一周派对排期键值合法且同一娱乐不占两天")
def check_island_22_party_day_of_week() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验party_day_of_week必须是dict、键恰为0..6，值为合法娱乐id(0表示无活动)，且同一非零娱乐id不得同时
        占据两天。isinstance(dict)守卫不可省——debug面板允许把整个party_day_of_week直接替换成一个整数，
        否则检查器会抛异常而不是给出清晰结论
    """
    cache = cache_control.cache
    ri = cache.rhodes_island
    party_day_of_week = getattr(ri, "party_day_of_week", None)
    if not isinstance(party_day_of_week, dict):
        return [
            make_failure(
                "ISLAND-22",
                "一周派对排期键值合法且同一娱乐不占两天",
                f"ri.party_day_of_week不是dict，实际类型={type(party_day_of_week).__name__}，"
                f"cache.debug_mode={getattr(cache, 'debug_mode', '?')}",
                [],
            )
        ]
    failures = []
    key_set = set(party_day_of_week)
    if key_set != set(range(7)):
        failures.append(
            make_failure(
                "ISLAND-22",
                "一周派对排期键值合法且同一娱乐不占两天",
                f"party_day_of_week全量={party_day_of_week}，缺失键={sorted(set(range(7)) - key_set)}，"
                f"多余键={sorted(key_set - set(range(7)))}",
                [],
            )
        )
    illegal_values = [
        (day, v)
        for day, v in party_day_of_week.items()
        if not (type(v) is int and v in game_config.config_entertainment)
    ]
    if illegal_values:
        failures.append(
            make_failure(
                "ISLAND-22",
                "一周派对排期键值合法且同一娱乐不占两天",
                f"非法娱乐id的(day,v)={illegal_values}",
                [],
            )
        )
    non_zero_vals = [
        v for v in party_day_of_week.values() if type(v) is int and v
    ]
    dup_vals = {v for v, cnt in Counter(non_zero_vals).items() if cnt > 1}
    if dup_vals:
        dup_days = {
            v: [d for d, vv in party_day_of_week.items() if vv == v]
            for v in dup_vals
        }
        failures.append(
            make_failure(
                "ISLAND-22",
                "一周派对排期键值合法且同一娱乐不占两天",
                (
                    f"重复出现的娱乐id与对应天={dup_days}，"
                    f"当前weekday={getattr(game_time.now(), 'weekday', lambda: '?')()}"
                ),
                [],
            )
        )
    return failures


@register_check("ISLAND-23", "干员娱乐安排固定三项且id合法")
def check_island_23_entertainment_type() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验每个角色的entertainment.entertainment_type必须是长度恰为3的list，每项都是Entertainment.csv中的
        合法cid(0=无)。会真实崩溃的非法态——无保护索引config_entertainment[…]。检查范围取全部角色而非在编
        名单：该字段是角色自带属性，离线角色归队后同样会被AI读取。已知合法误报源：debug面板允许输入任意三元组
    """
    cache = cache_control.cache
    cd = cache.character_data
    failures = []
    for cid, ch in cd.items():
        et = ch.entertainment.entertainment_type
        if (
            isinstance(et, list)
            and len(et) == 3
            and all(
                type(e) is int and e in game_config.config_entertainment
                for e in et
            )
        ):
            continue
        illegal_items = (
            [
                e
                for e in et
                if not (
                    isinstance(et, list)
                    and type(e) is int
                    and e in game_config.config_entertainment
                )
            ]
            if isinstance(et, list)
            else et
        )
        failures.append(
            make_failure(
                "ISLAND-23",
                "干员娱乐安排固定三项且id合法",
                f"角色cid={cid}({ch.name})的entertainment_type={et!r}不合法，非法项={illegal_items}，"
                f"cache.debug_mode={getattr(cache, 'debug_mode', '?')}",
                [cid],
            )
        )
    return failures


@register_check("ISLAND-24", "自动交易设置键与阈值合法")
def check_island_24_auto_trade_setting() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验base.auto_trade里的自动交易设置键与阈值合法。每个资源id必须存在于资源配置。
        设置字典必须含六个标准键。库存阈值在0..仓库容量，价格百分比在0..300，开关是0/1或True/False。
        开关不能写type(...) is bool：economy.auto_trade把设置过的资源缺的键读成整数0，面板改设置时连这个0一起存回
    """
    ri = cache_control.cache.rhodes_island
    keys_required = set(economy.AUTO_TRADE_KEYS)
    warehouse_capacity = getattr(ri, "warehouse_capacity", 0)
    failures = []
    for rid, s in economy.auto_trade_table().items():
        if (
            rid not in game_config.config_resouce
            or not isinstance(s, dict)
            or not (keys_required <= set(s))
        ):
            failures.append(
                make_failure(
                    "ISLAND-24",
                    "自动交易设置键与阈值合法",
                    (
                        f"resource_id={rid}("
                        f"{game_config.config_resouce[rid].name if rid in game_config.config_resouce else '不存在'})，"
                        f"完整setting字典={s}，"
                        f"缺失的键={sorted(keys_required - set(s)) if isinstance(s, dict) else '(非dict)'}"
                    ),
                    [],
                )
            )
            continue
        out_of_range = []
        if s["buy_on"] not in (True, False, 0, 1):
            out_of_range.append(("buy_on", s["buy_on"]))
        if s["sell_on"] not in (True, False, 0, 1):
            out_of_range.append(("sell_on", s["sell_on"]))
        if not (0 <= s["buy_stock"] <= warehouse_capacity):
            out_of_range.append(("buy_stock", s["buy_stock"]))
        if not (0 <= s["sell_stock"] <= warehouse_capacity):
            out_of_range.append(("sell_stock", s["sell_stock"]))
        if not (0 <= s["buy_price_percent"] <= 300):
            out_of_range.append(("buy_price_percent", s["buy_price_percent"]))
        if not (0 <= s["sell_price_percent"] <= 300):
            out_of_range.append(("sell_price_percent", s["sell_price_percent"]))
        if out_of_range:
            failures.append(
                make_failure(
                    "ISLAND-24",
                    "自动交易设置键与阈值合法",
                    f"resource_id={rid}({game_config.config_resouce[rid].name})，完整setting字典={s}，"
                    f"ri.warehouse_capacity={warehouse_capacity}，越界字段={out_of_range}",
                    [],
                )
            )
    return failures


@register_check("ISLAND-25", "载具在外数量与进行中委托占用一致")
def check_island_25_vehicle_usage_consistency() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验base.vehicles里每种载具的记录是两个int(拥有数,外勤中数)，满足0<=外勤中数<=拥有数，
        外勤中数等于所有进行中委托派出该型载具的台数之和，委托派出的载具型号必须同时存在于配置与载具表。
        先扫委托再扫载具表，因为只遍历载具表会漏掉"委托引用了不在载具表里的型号"这一类
    """
    vehicles = commission.vehicles()
    failures = []
    used: Counter[int] = Counter()
    used_by: dict[int, list[int]] = {}
    for com_id, c in commission.ongoing().items():
        for vid in c.vehicles:
            if vid not in game_config.config_vehicle or vid not in vehicles:
                failures.append(
                    make_failure(
                        "ISLAND-25",
                        "载具在外数量与进行中委托占用一致",
                        f"委托com_id={com_id}引用的载具vid={vid}不在config_vehicle或vehicles中",
                        [],
                    )
                )
                continue
            used[vid] += 1
            used_by.setdefault(vid, []).append(com_id)
    for vid, v in vehicles.items():
        vehicle_name = (
            game_config.config_vehicle[vid].name
            if vid in game_config.config_vehicle
            else "?"
        )
        if not all(type(x) is int for x in v):
            failures.append(
                make_failure(
                    "ISLAND-25",
                    "载具在外数量与进行中委托占用一致",
                    f"vid={vid}({vehicle_name})的记录类型非法：{v!r}",
                    [],
                )
            )
            continue
        total, out = v
        used_count = used.get(vid, 0)
        if not (0 <= out <= total) or out != used_count:
            failures.append(
                make_failure(
                    "ISLAND-25",
                    "载具在外数量与进行中委托占用一致",
                    f"vid={vid}({vehicle_name})，total={total}，out={out}，实际委托占用used={used_count}，"
                    f"占用该载具的委托id列表={used_by.get(vid, [])}",
                    [],
                )
            )
    return failures


@register_check("ISLAND-26", "外勤派遣名单与干员外勤标记一致")
def check_island_26_field_commission_flag_consistency() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验每个进行中委托的id必须合法；成员必须是存在的角色、不被两个委托同时派遣、其sp_flag.field_commission
        等于该委托id；反过来，任何field_commission!=0的角色都必须恰好出现在对应委托的名单里。反向检查必须
        遍历character_data而不是npc_id_got——外勤成员必然不在npc_id_got里，用名单遍历会必现漏检
    """
    cache = cache_control.cache
    cd = cache.character_data
    failures = []
    seen = set()
    for com_id, c in commission.ongoing().items():
        if com_id not in game_config.config_commission:
            failures.append(
                make_failure(
                    "ISLAND-26",
                    "外勤派遣名单与干员外勤标记一致",
                    f"委托com_id={com_id}不在config_commission中",
                    [],
                )
            )
            continue
        commission_name = game_config.config_commission[com_id].name
        for cid in c.team:
            if cid not in cd:
                failures.append(
                    make_failure(
                        "ISLAND-26",
                        "外勤派遣名单与干员外勤标记一致",
                        f"委托com_id={com_id}({commission_name})名单中的cid={cid}在character_data中不存在",
                        [],
                    )
                )
                continue
            if cid in seen:
                failures.append(
                    make_failure(
                        "ISLAND-26",
                        "外勤派遣名单与干员外勤标记一致",
                        f"重复派遣的cid={cid}({cd[cid].name})同时出现在多个委托名单中",
                        [cid],
                    )
                )
                continue
            seen.add(cid)
            ch = cd[cid]
            if ch.sp_flag.field_commission != com_id:
                failures.append(
                    make_failure(
                        "ISLAND-26",
                        "外勤派遣名单与干员外勤标记一致",
                        f"委托com_id={com_id}({commission_name})名单含cid={cid}({ch.name})，但其"
                        f"sp_flag.field_commission={ch.sp_flag.field_commission}，与委托id不符，"
                        f"cid in cache.npc_id_got={cid in cache.npc_id_got}",
                        [cid],
                    )
                )
    for cid, ch in cd.items():
        if cid == 0:
            continue
        if ch.sp_flag.field_commission != 0 and cid not in seen:
            failures.append(
                make_failure(
                    "ISLAND-26",
                    "外勤派遣名单与干员外勤标记一致",
                    f"角色cid={cid}({ch.name})的sp_flag.field_commission={ch.sp_flag.field_commission}(悬空标记)，"
                    f"但未出现在任何进行中委托名单里",
                    [cid],
                )
            )
    return failures


@register_check("ISLAND-27", "储能与供能设施结构、绝对范围合法")
def check_island_27_power_structure_and_range() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验 base.power_storage 在[0, 最大储能]内、clean 与 batteries 各有 3 项、副反应炉与各设施数量都是非负整数。
        不加"设施数<=基础位+当前模块库存"等上界断言。交易卖出不看已建设施，可把模块库存卖到低于已建设施的需求。
        这类上界只适合做经营告警
    """
    plant = power.plant()
    stored, top = power.storage(), power.storage_max()
    problems = []
    if not 0 <= stored <= top:
        problems.append(
            f"base.power_storage={stored}，最大储能={top}，超出[0, max]范围"
        )
    for name in ("clean", "batteries"):
        if len(plant[name]) != 3:
            problems.append(
                f"base.power.{name}结构非法：{plant[name]!r}，期望长度3"
            )
    counts = [plant["aux_reactors"], *plant["clean"], *plant["batteries"]]
    bad = [n for n in counts if type(n) is not int or n < 0]
    if bad:
        problems.append(
            f"供能设施中存在非法数量={bad}，base.power={dict(plant)}"
        )
    return [
        make_failure("ISLAND-27", "储能与供能设施结构、绝对范围合法", text, [])
        for text in problems
    ]


@register_check("ISLAND-28", "主供能调控员槽位有效且不重复")
def check_island_28_main_power_operator_slots() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验 base.power 的 main_operators 是火/水/风/光 4 槽、每个非0值是 work.work_type==11 的现有角色、4 槽互不重复。
        不要求角色在 npc_id_got 里，派外勤的调控员保留岗位与槽位
    """
    cache = cache_control.cache
    cd = cache.character_data
    slots = power.plant()["main_operators"]
    if len(slots) != 4:
        return [
            make_failure(
                "ISLAND-28",
                "主供能调控员槽位有效且不重复",
                f"base.power.main_operators结构非法：{slots!r}，期望长度4",
                [],
            )
        ]
    non_zero = [m for m in slots if m]
    dup = {m for m, cnt in Counter(non_zero).items() if cnt > 1}
    illegal = [
        m for m in non_zero if not (m in cd and cd[m].work.work_type == 11)
    ]
    if dup or illegal:
        detail = [
            (
                f"cid={m},{_chara_name(cd, m)},work_type={cd[m].work.work_type if m in cd else None},"
                f"{_sp_flag_brief(cd.get(m))}"
            )
            for m in sorted(set(dup) | set(illegal))
        ]
        return [
            make_failure(
                "ISLAND-28",
                "主供能调控员槽位有效且不重复",
                f"四槽全量={slots}，重复占用cid={sorted(dup)}，非法槽位cid={illegal}，明细={detail}，"
                f"work.roster(11)={work.roster(11)}",
                sorted(set(dup) | set(illegal)),
            )
        ]
    return []


@register_check("ISLAND-29", "监狱长引用与囚犯数据自洽")
def check_island_29_warden_and_prisoners() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验监狱长（work.warden）为0或指向一名存在的、work.work_type==191的角色；每个囚犯id必须存在，逃脱概率
        落在0..100。去掉了"在npc_id_got"子句——监狱长可能被关押或逃脱而离线，此时work_type仍是191，引用合法
    """
    cache = cache_control.cache
    ri = cache.rhodes_island
    cd = cache.character_data
    failures = []
    warden_id = work.warden()
    if warden_id != 0 and not (
        warden_id in cd and cd[warden_id].work.work_type == 191
    ):
        actual_wardens = [
            cid for cid, ch in cd.items() if ch.work.work_type == 191
        ]
        ch = cd.get(warden_id)
        ch_work = getattr(ch, "work", None)
        failures.append(
            make_failure(
                "ISLAND-29",
                "监狱长引用与囚犯数据自洽",
                f"work.warden()={warden_id}({_chara_name(cd, warden_id)})不是合法监狱长引用，"
                f"实际work_type={ch_work and ch_work.work_type}，{_sp_flag_brief(ch)}，"
                f"实际work_type==191的角色列表={actual_wardens}",
                [warden_id],
            )
        )
    current_prisoners = getattr(ri, "current_prisoners", None)
    if isinstance(current_prisoners, dict):
        illegal = [
            (p, v)
            for p, v in current_prisoners.items()
            if not (
                p in cd
                and isinstance(v, list)
                and len(v) >= 2
                and 0 <= v[1] <= 100
            )
        ]
        if illegal:
            failures.append(
                make_failure(
                    "ISLAND-29",
                    "监狱长引用与囚犯数据自洽",
                    f"current_prisoners中的违规(囚犯id,记录)={illegal}",
                    [p for p, _v in illegal if p in cd],
                )
            )
    return failures


@register_check("ISLAND-30", "设施损坏数据与检修分派自洽")
def check_island_30_facility_damage_and_maintenance() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验facility_damage_data的键必须是合法场景路径、值为正整数(<=0时代码会pop)；maintenance_place的键
        必须是存在的、work.work_type==21的角色，值必须是合法场景路径。不要求检修工程师在npc_id_got（外勤中
        的工程师不会被清maintenance_place）；不要求检修目标当前仍有损坏记录（无损坏时会随机选目标）
    """
    cache = cache_control.cache
    ri = cache.rhodes_island
    cd = cache.character_data
    failures = []
    facility_damage_data = getattr(ri, "facility_damage_data", None)
    if isinstance(facility_damage_data, dict):
        illegal_damage = [
            (p, v)
            for p, v in facility_damage_data.items()
            if not (p in cache.scene_data and type(v) is int and v >= 1)
        ]
        if illegal_damage:
            failures.append(
                make_failure(
                    "ISLAND-30",
                    "设施损坏数据与检修分派自洽",
                    f"facility_damage_data非法键/值明细={illegal_damage}",
                    [],
                )
            )
    maintenance_place = getattr(ri, "maintenance_place", None)
    if isinstance(maintenance_place, dict):
        illegal_maintenance = [
            (cid, place)
            for cid, place in maintenance_place.items()
            if not (
                cid in cd
                and cd[cid].work.work_type == 21
                and place in cache.scene_data
            )
        ]
        if illegal_maintenance:
            detail = [
                f"cid={cid},{_chara_name(cd, cid)},work_type={cd[cid].work.work_type if cid in cd else None},"
                f"{_sp_flag_brief(cd.get(cid))},place_in_scene_data={place in cache.scene_data}"
                for cid, place in illegal_maintenance
            ]
            failures.append(
                make_failure(
                    "ISLAND-30",
                    "设施损坏数据与检修分派自洽",
                    f"maintenance_place非法明细={illegal_maintenance}，涉及角色详情={detail}",
                    [cid for cid, _place in illegal_maintenance if cid in cd],
                )
            )
    return failures


@register_check("ISLAND-31", "访客集合与待确认招募集合合法")
def check_island_31_visitor_and_recruited_id() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验base.visitor里的访客都是存在的角色，访客数不超过按已开放客房数算出的访客上限(visitor.capacity())，
        待确认招募名单recruit.pending()不含0、成员均存在、与已招募名单不相交。
        不断言"访客必须在npc_id_got"（可能被绑架而离线）。
        不断言"干员数<=people_max"（访客计入名单但只受客房数约束，属设计内流程，不在本条硬检查范围）
    """
    cache = cache_control.cache
    cd = cache.character_data
    failures = []
    visitors = visitor.visitors()
    ghost_visitors = [v for v in visitors if v not in cd]
    if ghost_visitors or len(visitors) > visitor.capacity():
        failures.append(
            make_failure(
                "ISLAND-31",
                "访客集合与待确认招募集合合法",
                f"访客数={len(visitors)}，访客上限={visitor.capacity()}，幽灵访客id={ghost_visitors}",
                ghost_visitors,
            )
        )
    recruited_id = recruit.pending()
    conflict = recruited_id & cache.npc_id_got
    ghost_recruited = [r for r in recruited_id if r not in cd]
    if 0 in recruited_id or ghost_recruited or conflict:
        conflict_detail = [(r, _chara_name(cd, r)) for r in conflict]
        failures.append(
            make_failure(
                "ISLAND-31",
                "访客集合与待确认招募集合合法",
                f"recruited_id含0={0 in recruited_id}，幽灵成员={ghost_recruited}，"
                f"recruited_id与npc_id_got交集={conflict_detail}",
                list(conflict) + ghost_recruited,
            )
        )
    return failures


@register_check("ISLAND-32", "贸易子设施列表与开放表一致、不超上限、无重复")
def check_island_32_shop_open_list() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        校验已开放商店名(base.shops_open)无重名、长度不超过贸易区(cid 11)当前等级效果值，且其中每个名称都
        对应一个贸易区可建设施且该设施已开放。反向不成立、禁止加：贸易区5级会经zone_cid规则自动开放全部151-168号
        子设施而不调economy.open_shop，"facility_open为真⇒名字在base.shops_open里"是必现误报
    """
    cache = cache_control.cache
    ri = cache.rhodes_island
    shop_open_list = economy.shops_open()
    eff11 = _eff(ri, 11)
    trade_open = {
        o.name: oid
        for oid, o in game_config.config_facility_open.items()
        if 111 <= o.zone_cid <= 115
    }
    facility_open = facility.opens()
    failures = []
    dup_names = [n for n, cnt in Counter(shop_open_list).items() if cnt > 1]
    if dup_names:
        failures.append(
            make_failure(
                "ISLAND-32",
                "贸易子设施列表与开放表一致、不超上限、无重复",
                f"shop_open_list重复名={dup_names}，全量={shop_open_list}",
                [],
            )
        )
    if eff11 is not None and len(shop_open_list) > eff11:
        failures.append(
            make_failure(
                "ISLAND-32",
                "贸易子设施列表与开放表一致、不超上限、无重复",
                f"len(shop_open_list)={len(shop_open_list)}超过_eff(11)={eff11}，"
                f"facility_level[11]={facility.levels().get(11)}",
                [],
            )
        )
    unmatched = [
        (name, trade_open.get(name))
        for name in shop_open_list
        if name not in trade_open
        or not facility_open.get(trade_open[name], False)
    ]
    if unmatched:
        failures.append(
            make_failure(
                "ISLAND-32",
                "贸易子设施列表与开放表一致、不超上限、无重复",
                f"在列表中但facility_open为假(或未匹配到设施)的设施名与open_cid={unmatched}",
                [],
            )
        )
    return failures


@register_check("ISLAND-33", "外交官映射、岗位与外派标记三方一致")
def check_island_33_diplomat_mapping_consistency() -> list[CheckFailure]:
    """
    参数:
        无
    返回值:
        List[CheckFailure]: 失败记录列表
    功能:
        [warning] 校验diplomacy.table()[国家]["diplomat"]的非零角色必须存在、sp_flag.in_diplomatic_visit等于该国家、
        work.work_type==131，且一人不得同时负责两国；反过来任何in_diplomatic_visit!=0的角色都必须正是该国
        映射所指的人。定为告警是因为有UI可达的破坏路径（改派现任外交官为别的岗位、任命候选表不排除已负责
        他国的角色），都是设计缺陷而非数据损坏
    """
    cache = cache_control.cache
    cd = cache.character_data
    failures = []
    seen: dict[int, int] = {}
    for country, post in diplomacy.table().items():
        did = post["diplomat"]
        if not did:
            continue
        if did not in cd:
            failures.append(
                make_failure(
                    "ISLAND-33",
                    "外交官映射、岗位与外派标记三方一致",
                    f"[warning] country_id={country}指向的diplomat_id={did}在character_data中不存在",
                    [],
                )
            )
            continue
        if did in seen:
            failures.append(
                make_failure(
                    "ISLAND-33",
                    "外交官映射、岗位与外派标记三方一致",
                    f"[warning] diplomat_id={did}({cd[did].name})同时被country_id={seen[did]}与country_id={country}"
                    f"两国映射引用，一人负责的全部国家列表={[seen[did], country]}",
                    [did],
                )
            )
            continue
        seen[did] = country
        ch = cd[did]
        if (
            ch.sp_flag.in_diplomatic_visit != country
            or ch.work.work_type != 131
        ):
            location_head = location.country()
            failures.append(
                make_failure(
                    "ISLAND-33",
                    "外交官映射、岗位与外派标记三方一致",
                    f"[warning] country_id={country}，diplomat_id={did}({ch.name})，"
                    f"实际work.work_type={ch.work.work_type}(期望131)，"
                    f"实际sp_flag.in_diplomatic_visit={ch.sp_flag.in_diplomatic_visit}(期望{country})，"
                    f"所在国家={location_head}",
                    [did],
                )
            )
    for cid, ch in cd.items():
        if cid and ch.sp_flag.in_diplomatic_visit:
            if seen.get(cid) != ch.sp_flag.in_diplomatic_visit:
                failures.append(
                    make_failure(
                        "ISLAND-33",
                        "外交官映射、岗位与外派标记三方一致",
                        (
                            f"[warning] 角色cid={cid}({ch.name})的sp_flag.in_diplomatic_visit="
                            f"{ch.sp_flag.in_diplomatic_visit}，"
                            f"但diplomacy.table()[{ch.sp_flag.in_diplomatic_visit}]未指回该角色"
                            f"(实际映射到seen.get(cid)={seen.get(cid)})"
                        ),
                        [cid],
                    )
                )
    return failures
