# -*- coding: UTF-8 -*-
"""
静态检查系统 - 载入存档时的保守自动修复
在载入存档完成后扫描已知的"逻辑不合法状态"，用保守策略修复（越界拉回、重复去重、悬空引用清除、
派生缓存按源数据重算），使刚读取的存档不再触发对应检查，防止祖传脏数据在修复前一直存在且永不自愈。

契约：
- 修复策略逐条挂在检查上（register_repair），只为语义清晰、有唯一保守答案的检查提供修复；
  语义模糊的检查宁可不修（检查级去重保证不修也只记一条日志）。
- 每条修复必须留痕：修了什么对象的什么字段、修复前值与修复后值，逐条写入static_check_error.log。
- 修复绝不让载入失败：每条修复规则独立try/except，修不动就跳过保留原样；入口函数永不向调用方抛异常。
- debug模式（mode.debug）开启时全部跳过（与相应检查的debug豁免一致，debug面板改出的值视为有意为之）。
"""

from __future__ import annotations

from collections.abc import Callable
from fractions import Fraction

from Script.Config import game_config
from Script.Modules.domains import flags, modes, needs, power, wardrobe, work

from . import check_log

from typing import TYPE_CHECKING
from Script.Modules.domains import chara_life, identity

if TYPE_CHECKING:
    from collections.abc import Iterator
    from Script.Core import game_type

_repair_registry: dict[
    str, tuple[str, Callable[[game_type.Cache], list[dict]]]
] = {}


def register_repair(check_id: str, repair_name: str) -> Callable[
    [Callable[[game_type.Cache], list[dict]]],
    Callable[[game_type.Cache], list[dict]],
]:
    """
    参数:
        check_id (str): 该修复对应的检查id（与check_registry中注册的检查一一对应）
        repair_name (str): 修复策略的简短中文名
    返回值:
        Callable: 装饰器
    功能:
        将一个接收cache参数的修复函数注册到修复注册表；
        同一函数（__module__ 与 __qualname__ 都相同）再次注册同一check_id时
        替换原条目，其他函数注册已有check_id时抛ValueError（导入期即暴露配置错误）
    """

    def decorator(
        func: Callable[[game_type.Cache], list[dict]],
    ) -> Callable[[game_type.Cache], list[dict]]:
        registered = _repair_registry.get(check_id)
        if registered is not None:
            old_func = registered[1]
            if (old_func.__module__, old_func.__qualname__) != (
                func.__module__,
                func.__qualname__,
            ):
                raise ValueError(f"重复注册修复: {check_id}")
        _repair_registry[check_id] = (repair_name, func)
        return func

    return decorator


def _record(
    check_id: str, target: str, field: str, old_value: object, new_value: object
) -> dict:
    """
    参数:
        check_id (str): 检查id
        target (str): 修复对象描述（如"角色69(塔佳娜)"）
        field (str): 被修复的字段路径
        old_value: 修复前的值
        new_value: 修复后的值
    返回值:
        dict: 标准修复记录
    功能:
        构造一条留痕用的修复记录，旧值新值都完整保留
    """
    return {
        "check_id": check_id,
        "target": target,
        "field": field,
        "old_value": old_value,
        "new_value": new_value,
    }


def _chara_label(cid: int | None, chara: object) -> str:
    """
    参数:
        cid: 角色id
        chara: 角色对象
    返回值:
        str: "角色id(名字)"形式的描述
    功能:
        构造修复记录中的角色描述文本
    """
    return f"角色{cid}({getattr(chara, 'name', '?')})"


@register_repair("NUM-27", "疲劳/饥饿/熟睡/醉酒越界拉回")
def repair_fatigue_family_range(cache: game_type.Cache) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 修复记录列表
    功能:
        与NUM-27同语义：body.needs的tired、hunger、sleep、drunk必须是[0,上界]内的int或Fraction。
        其他类型置0，越界钳制到边界，经needs.set写回。
    """
    bounds = {
        "needs.tired": 160,
        "needs.hunger": 240,
        "needs.sleep": 100,
        "needs.drunk": 100,
    }
    records = []
    for cid, chara in identity.table().items():
        values = {f"needs.{k}": v for k, v in needs.of(cid).items()}
        for field, upper in bounds.items():
            v = values[field]
            if isinstance(v, int | Fraction) and not isinstance(v, bool):
                if 0 <= v <= upper:
                    continue
                new_v = min(max(v, 0), upper)
            else:
                new_v = 0
            needs.set(cid, **{field.removeprefix("needs."): new_v})
            records.append(
                _record("NUM-27", _chara_label(cid, chara), field, v, new_v)
            )
    return records


@register_repair("SUPP-05", "愤怒值下界钳制")
def repair_angry_point_lower_bound(cache: game_type.Cache) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 修复记录列表
    功能:
        与SUPP-05同语义：body.needs的angry必须是>=0的int。非int置0，负值拉回0，经needs.set写回
    """
    records = []
    for cid, chara in identity.table().items():
        v = needs.of(cid)["angry"]
        if type(v) is int and v >= 0:
            continue
        new_v = max(v, 0) if type(v) is int else 0
        needs.set(cid, angry=new_v)
        records.append(
            _record(
                "SUPP-05", _chara_label(cid, chara), "angry_point", v, new_v
            )
        )
    return records


def _iter_cloth_containers(
    cid: int,
) -> Iterator[tuple[str, dict[int, list[int]]]]:
    """
    参数:
        cid: 角色id
    返回值:
        Iterator[Tuple[str, dict]]: 角色服装（wardrobe.of）里四个服装容器的 (容器名, 槽位字典) 序列
    功能:
        逐个交出四个服装容器，结构非法的容器跳过（形状问题属BODY-01，不在修复范围）。
        遍历到底后把服装写回 body.cloth，调用方对槽位字典的修改因此生效
    """
    cloth = wardrobe.of(cid)
    for attr_name in (
        "cloth_wear",
        "cloth_off",
        "cloth_locker_in_shower",
        "cloth_locker_in_dormitory",
    ):
        d = getattr(cloth, attr_name, None)
        if isinstance(d, dict):
            yield attr_name, d
    wardrobe.put(cid, cloth)


@register_repair("BODY-02", "非法服装id清除与错位归正")
def repair_cloth_id_validity(cache: game_type.Cache) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 修复记录列表
    功能:
        与BODY-02同语义：四容器内配置中不存在的服装id（含非int与0占位）直接移除（悬空引用清除，
        旧版本遗留的已删除服装id属此类）；id有效但clothing_type与所在槽位不符的，移动到同容器的正确槽位
        （若正确槽位已含该id则仅从错误槽位移除）
    """
    tem = getattr(game_config, "config_clothing_tem", None)
    if not tem:
        return []
    records = []
    for cid, chara in identity.table().items():
        for attr_name, d in _iter_cloth_containers(cid):
            for t, lst in list(d.items()):
                if not isinstance(lst, list):
                    continue
                invalid = [
                    c
                    for c in lst
                    if type(c) is not int or c == 0 or c not in tem
                ]
                misplaced = [
                    c
                    for c in lst
                    if type(c) is int
                    and c in tem
                    and getattr(tem[c], "clothing_type", None) != t
                ]
                if not invalid and not misplaced:
                    continue
                old_list = list(lst)
                lst[:] = [
                    c for c in lst if c not in invalid and c not in misplaced
                ]
                for c in misplaced:
                    correct_t = getattr(tem[c], "clothing_type", None)
                    if (
                        correct_t in d
                        and isinstance(d[correct_t], list)
                        and c not in d[correct_t]
                    ):
                        d[correct_t].append(c)
                records.append(
                    _record(
                        "BODY-02",
                        _chara_label(cid, chara),
                        f"cloth.{attr_name}[{t}]",
                        old_list,
                        list(lst),
                    )
                )
    return records


@register_repair("BODY-03", "同槽位重复服装去重")
def repair_cloth_slot_duplicates(cache: game_type.Cache) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 修复记录列表
    功能:
        与BODY-03同语义：同一容器同一槽位列表内重复的服装id只保留首个，其余移除（保持原有顺序）
    """
    records = []
    for cid, chara in identity.table().items():
        for attr_name, d in _iter_cloth_containers(cid):
            for t, lst in d.items():
                if not isinstance(lst, list) or len(lst) == len(set(lst)):
                    continue
                old_list = list(lst)
                lst[:] = list(dict.fromkeys(lst))
                records.append(
                    _record(
                        "BODY-03",
                        _chara_label(cid, chara),
                        f"cloth.{attr_name}[{t}]",
                        old_list,
                        list(lst),
                    )
                )
    return records


@register_repair("BODY-35", "个人服装模板列表无效项清除")
def repair_clothing_tem_list(cache: game_type.Cache) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 修复记录列表
    功能:
        与BODY-35同语义：clothing_tem列表中配置已不存在的服装模板id（含非int项）移除
    """
    tem = getattr(game_config, "config_clothing_tem", None)
    if not tem:
        return []
    records = []
    for cid, chara in identity.table().items():
        cloth = wardrobe.of(cid)
        lst = cloth.clothing_tem
        bad = [x for x in lst if type(x) is not int or x not in tem]
        if not bad:
            continue
        old_list = list(lst)
        lst[:] = [x for x in lst if x not in bad]
        wardrobe.put(cid, cloth)
        records.append(
            _record(
                "BODY-35",
                _chara_label(cid, chara),
                "cloth.clothing_tem",
                old_list,
                list(lst),
            )
        )
    return records


@register_repair("ISLAND-09", "岗位集合按在编名单重算")
def repair_work_npc_set(cache: game_type.Cache) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 修复记录列表
    功能:
        与ISLAND-09同语义：岗位名册（work.rosters）可由角色work.work_type逐人重算，
        调用游戏自身的维护函数basement.update_work_people()整体重算（源数据即真相），留痕各岗位名册的前后差异
    """
    from Script.Design import basement

    old_sets = {wid: set(ids) for wid, ids in work.rosters().items()}
    # 唯一例外：游戏既有维护函数内部读取全局cache；此处只调用它重算岗位名册，不改造该函数本身
    basement.update_work_people()
    records = []
    new_sets = {wid: set(ids) for wid, ids in work.rosters().items()}
    for wid in set(old_sets) | set(new_sets):
        old_s = old_sets.get(wid, set())
        new_s = new_sets.get(wid, set())
        if old_s != new_s:
            records.append(
                _record(
                    "ISLAND-09",
                    "罗德岛岗位名册",
                    f"work.roster({wid})",
                    sorted(old_s),
                    sorted(new_s),
                )
            )
    return records


@register_repair("ISLAND-28", "主供能调控员非法槽位清空")
def repair_main_power_operator_slots(cache: game_type.Cache) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 修复记录列表
    功能:
        与ISLAND-28同语义。base.power 的 main_operators 里指向不存在角色或 work_type!=11 角色的槽位置 0（空槽）。
        同一 cid 占多槽时保留第一个，其余置 0。槽位有变化时整值写回 base.power
    """
    cd = identity.table()
    slots = list(power.plant()["main_operators"])
    if len(slots) != 4:
        return []
    old_slots = list(slots)
    seen = set()
    for i, m in enumerate(slots):
        if not m:
            continue
        if m in seen or not (m in cd and chara_life.work_type(m) == 11):
            slots[i] = 0
        else:
            seen.add(m)
    if slots == old_slots:
        return []
    power.set_plant(main_operators=tuple(slots))
    return [
        _record(
            "ISLAND-28",
            "罗德岛主供能设施",
            "base.power.main_operators",
            old_slots,
            list(slots),
        )
    ]


@register_repair("PLACE-28", "登记宿舍与当前宿舍相同时清空")
def repair_permanent_dormitory_equal_to_dormitory(
    cache: game_type.Cache,
) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 修复记录列表
    功能:
        与PLACE-28同语义：角色的「登记宿舍」（角色键 life.permanent_dormitory）非空且等于当前宿舍时，清空为""。
        这说明角色离开特殊房间时登记宿舍没有清空。
        只修这一种失败模式。登记宿舍不是开放的普通宿舍（PLACE-29）时本函数不修，因为推不出角色原来住的普通宿舍
    """
    records = []
    for cid, chara in identity.table().items():
        v = chara_life.permanent_dormitory(cid)
        if v != "" and v == chara_life.dormitory(cid):
            chara_life.permanent_dormitory.set(cid, "")
            records.append(
                _record(
                    "PLACE-28",
                    _chara_label(cid, chara),
                    "permanent_dormitory",
                    v,
                    "",
                )
            )
    return records


@register_repair("ISLAND-29", "监狱长悬空引用修正")
def repair_warden_reference(cache: game_type.Cache) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 修复记录列表
    功能:
        与ISLAND-29（引用子句，兼ROSTER-12）同语义：监狱长（work.warden）非0但指向的角色不存在或work_type!=191时，
        若恰有一名角色work_type==191则改指该角色，否则置0（无监狱长）。囚犯表子句语义不在本修复范围
    """
    cd = identity.table()
    warden_id = work.warden()
    if warden_id == 0 or (
        warden_id in cd and chara_life.work_type(warden_id) == 191
    ):
        return []
    actual_wardens = [cid for cid in cd if chara_life.work_type(cid) == 191]
    new_id = actual_wardens[0] if len(actual_wardens) == 1 else 0
    work.set_warden(new_id)
    return [
        _record("ISLAND-29", "罗德岛监狱", "work.warden", warden_id, new_id)
    ]


@register_repair("HGROUP-12", "「群交自慰」残留标记归零")
def repair_masturebate_stale_group_flag(cache: game_type.Cache) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 修复记录列表
    功能:
        与HGROUP-12同条件、保守口径：非H(sp_flag.is_h为假)且非群交模式(cache.group_sex_mode为假)但
        sp_flag.masturebate==3的角色，直接把该标记归0。条件即检查断言本身，只兜住已确认的存量残留形态
        （群交中有人从无意识恢复时先关group_sex_mode再清理其余角色，清理函数不清masturebate），不覆盖
        仍在H/群交中的角色——那些角色下次H/群交正常结束时会经效果407自然清零。
    """
    if modes.group_sex():
        return []
    records = []
    for cid, chara in identity.table().items():
        old_v = flags.get(cid, "masturebate")
        if old_v != 3 or flags.get(cid, "is_h"):
            continue
        flags.set(cid, masturebate=0)
        records.append(
            _record(
                "HGROUP-12",
                _chara_label(cid, chara),
                "sp_flag.masturebate",
                old_v,
                0,
            )
        )
    return records


@register_repair("ISLAND-20", "普通宿舍超员住户重新分配")
def repair_overcrowded_dormitory_room(cache: game_type.Cache) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 修复记录列表
    功能:
        与ISLAND-20同语义：普通宿舍房设计容量2人，把超员房里多出来的住户按游戏自身的入住规则改分到别的
        开放普通宿舍（只写dormitory一个字段，position与登记宿舍permanent_dormitory一概不动）。
        搬谁之前先判该住户是否本就该住普通宿舍：get_residence_type()返回非"dormitory"的人（访客/囚犯/
        同居助理/舍管/监狱长）住的是客房、牢房、博士房间或包住宿岗位房，他们的dormitory落在普通宿舍房里
        本身就是另一种不一致，把这种人改分到另一间普通宿舍只会同时踩坏PLACE-24与ROSTER囚犯牢房唯一性，
        所以本修复只跳过不动，留给对应检查报告；同房内确实该住普通宿舍的住户按cid升序保留前两名，其余
        逐个重新分配。落点由既有pick_dormitory_room()按实时占用表挑选：层序取第一间不足2人的房，全部住满
        时落到人数最少的一间——与游戏内新入住者、临时住宿恢复共用同一条分配规则，不另立标准。
        每搬一人都重取占用表，既让刚搬入的房间计入人数，也让被搬空到2人的原超员房不会被回选
    """
    # 函数级导入，与check_place.py的PLACE-29同惯例，避免包导入期的加载顺序问题；
    # 这些宿舍函数内部读取游戏全局cache，与repair_work_npc_set的情况相同，此处只调用不改造
    from Script.System.Dormitory_System import common as dormitory_common

    room_residents: dict[str, list[int]] = {}
    for cid in sorted(dormitory_common.get_dormitory_resident_id_set()):
        chara = identity.get(cid)
        if chara is None:
            continue
        room_residents.setdefault(chara_life.dormitory(cid), []).append(cid)
    records = []
    for room_path in sorted(room_residents):
        cids = room_residents[room_path]
        # 层号解析失败(返回0)的不是普通宿舍房，与ISLAND-20检查的取域保持一致
        if len(cids) <= 2 or not dormitory_common.get_layer_by_dormitory_path(
            room_path
        ):
            continue
        normal_cids = [
            cid
            for cid in cids
            if dormitory_common.get_residence_type(cid) == "dormitory"
        ]
        for cid in normal_cids[2:]:
            room_occupancy = (
                dormitory_common.get_open_dormitory_room_occupancy()
            )
            if not room_occupancy:
                break
            new_room = dormitory_common.pick_dormitory_room(room_occupancy)
            if new_room == room_path:
                continue
            chara = identity.of(cid)
            old_room = chara_life.dormitory(chara.cid)
            chara_life.dormitory.set(chara.cid, new_room)
            records.append(
                _record(
                    "ISLAND-20",
                    _chara_label(cid, chara),
                    "dormitory",
                    old_room,
                    new_room,
                )
            )
    return records


def apply_all_repairs(cache: game_type.Cache) -> list[dict]:
    """
    参数:
        cache: 当前游戏缓存对象
    返回值:
        List[dict]: 全部实际发生的修复记录（供门面返回；游戏侧无需使用返回值）
    功能:
        debug模式（mode.debug）开启时整体跳过修复，而静态检查仍照常运行。否则逐条执行注册表中的修复策略并写入留痕。
        每条修复独立隔离，单条失败只记录检查器自身异常，不影响其余修复。本函数的总兜底与就绪守卫由门面负责
    """
    all_records: list[dict] = []
    if modes.debug():
        return all_records
    for __, (__, repair_func) in _repair_registry.items():
        try:
            all_records.extend(repair_func(cache))
        except Exception as e:
            check_log.write_self_error_log(e)
    if all_records:
        check_log.write_repair_log(all_records, cache)
    return all_records
