# -*- coding: UTF-8 -*-
"""
静态检查系统 - 监禁调教/访客/招募名册/外勤委托相关检查
本模块实现 ROSTER 组的32条不变式（ROSTER-01..ROSTER-30、ROSTER-32、ROSTER-33），覆盖在编名册、场景成员关系、监禁与逃跑、
监狱长、访客、邀请、招募、外勤委托、载具、外交官、助理、装袋等子系统的状态自洽性。

设计基准: Linux(os.sep == "/")。全部涉及路径拼接的比较一律通过 os.sep.join 或场景标签集合完成，
不写死"\\"分隔符(详见各检查函数内注释)。全部离线判定一律用来源flag(field_commission/escaping/be_bagged)，
不使用 position == ["0","0"] 作为离线判据 —— 该坐标是真实场景"罗德岛出口"，在线角色途经该处合法。
全部访客排除一律写 vistor != 1，vistor == 2(前访客)是合法的招募/邀请目标，不得写成 vistor == 0。
"""

from __future__ import annotations

import collections
import datetime
import math
import os

from Script.Config import game_config
from Script.Core import cache_control
from Script.Modules.domains import abilities, activity, chara_life, commission
from Script.Modules.domains import diplomacy, facility, flags, location, modes
from Script.Modules.domains import playthrough, prison, recruit, relations
from Script.Modules.domains import roster, visitor, work, identity
from ..check_registry import CheckFailure, register_check, make_failure
from typing import TYPE_CHECKING
from Script.Design import game_time

if TYPE_CHECKING:
    from Script.Core import game_type

# ------------------------------- 共用小工具 -------------------------------


def _spath(pos: object) -> str:
    """
    参数: pos -- 形如["区域","房间"]的位置列表
    返回值: str -- 用os.sep拼接得到的场景路径字符串；pos形状不合法时返回空串
    功能: 等价于map_handle.get_map_system_path_str_for_list，避免任何地方写死分隔符
    """
    if isinstance(pos, (list, tuple)) and all(isinstance(x, str) for x in pos):
        return os.sep.join(pos)
    return ""


def _prison_dorms(cache: game_type.Cache) -> set[str]:
    """
    参数: cache -- 全局缓存
    返回值: Set[str] -- 全部带Prison标签的场景路径集合(关押/牢1..牢8)
    功能: 按场景标签动态推导合法牢房集合，避免子串匹配或写死路径
    """
    return {
        p
        for p, s in cache.scene_data.items()
        if "Prison" in getattr(s, "scene_tag", [])
    }


def _guest_rooms(cache: game_type.Cache) -> set[str]:
    """
    参数: cache -- 全局缓存
    返回值: Set[str] -- 全部带Guest_Room标签的场景路径集合(访客/客房N)
    功能: 按场景标签动态推导合法客房集合
    """
    return {
        p
        for p, s in cache.scene_data.items()
        if "Guest_Room" in getattr(s, "scene_tag", [])
    }


def _warden_dorm() -> str:
    """
    参数: 无
    返回值: str -- 监狱长专属宿舍"关押/休息室"的场景路径
    功能: 提供监狱长宿舍常量，统一走_spath避免分隔符问题
    """
    return _spath(["关押", "休息室"])


def _scene_membership(cache: game_type.Cache) -> dict[int, list[str]]:
    """
    参数: cache -- 全局缓存
    返回值: Dict[int, List[str]] -- 角色id到其出现的全部场景路径列表的反向索引(正常应恰好一条)
    功能: 遍历cache.scene_data建立场景成员关系反向索引，供在编/离线一致性类检查复用，避免重复遍历529个场景
    """
    membership: dict[int, list[str]] = {}
    for path, scene in cache.scene_data.items():
        for cid in getattr(scene, "character_list", []):
            if cid != 0:
                membership.setdefault(cid, []).append(path)
    return membership


def _invite_target() -> int:
    """
    返回值: int -- 邀请目标id，不是int时按0(无邀请)处理
    功能: 与ROSTER-18同样判断目标的类型，供ROSTER-19/21/27等读邀请目标的检查调用
    """
    target = visitor.invite()[0]
    return target if type(target) is int else 0


def _sev(cache: game_type.Cache, declared_warning: bool) -> str:
    """
    参数: cache -- 全局缓存; declared_warning -- 该检查项在不变式文档中声明的severity是否为warning
    返回值: str -- 需拼在失败信息最前面的前缀，declared_warning为True或cache.debug_mode为True时为"[warning] "，否则空串
    功能: 统一处理"[warning]"消息前缀规则，同时实现"debug模式下全部条目整体降级为提示"的全局约定，
    因为debug面板可以绕开配套流程直改facility_open/be_bagged/imprisonment等flag
    """
    return (
        "[warning] "
        if declared_warning or getattr(cache, "debug_mode", False)
        else ""
    )


# ------------------------------- ROSTER-01 ~ ROSTER-33 -------------------------------


@register_check("ROSTER-01", "在编名册id自洽")
def check_roster_id_self_consistency() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 校验cache.npc_id_got中每个id都存在角色对象，且角色自身cid与名册键一致，这是后续全部名册检查的地基
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    for cid in roster.active():
        if cid not in cd:
            failures.append(
                make_failure(
                    "ROSTER-01",
                    "在编名册id自洽",
                    f"{warn}npc_id_got中的角色id={cid}在character_data中不存在，len(npc_id_got)={roster.count()}",
                    [cid],
                )
            )
            continue
        c = cd[cid]
        if c.cid != cid:
            failures.append(
                make_failure(
                    "ROSTER-01",
                    "在编名册id自洽",
                    f"{warn}character_data[{cid}].cid={c.cid}与名册键{cid}不一致，name={c.name!r}，adv={c.adv}",
                    [cid],
                )
            )
    return failures


@register_check("ROSTER-02", "玩家id不应长期留在NPC名册里")
def check_player_id_not_lingering_in_roster() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: npc_id_got语义上是NPC集合，但init_character_position/init_character_entertainment会对玩家本体add(0)，
    discard(0)只在基建/宿舍面板(玩家触发)里执行，回合主循环从不调用。新游戏/多周目开局第一回合必然命中，
    cache没有暴露"该discard调用是否已跑过"的持久标记，这里用game_round<=1作为"很可能是开局首回合、面板尚未打开过"
    的保守豁免，避免每局开头都刷一条假警报；游戏时间推进后(game_round>1)仍命中才报出
    """
    cache = cache_control.cache
    warn = _sev(cache, True)
    failures: list[CheckFailure] = []
    if not roster.has(0):
        return failures
    if playthrough.game_round() <= 1:
        return failures
    failures.append(
        make_failure(
            "ROSTER-02",
            "玩家id不应长期留在NPC名册里",
            f"{warn}玩家id=0仍留在npc_id_got中(len={roster.count()})，game_time={game_time.now()}，game_round={playthrough.game_round()}；"
            f"若非开局首回合，说明discard(0)调用点(基建/宿舍面板)未生效或该id被重新add",
            [0],
        )
    )
    return failures


@register_check("ROSTER-03", "在编干员与场景名册双向一致")
def check_roster_scene_bidirectional_consistency() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 校验在编NPC恰好出现在其position对应的那一个场景里，离线角色从所有场景消失，场景里不得有幽灵id。
    用os.sep拼路径，不加position != ["0","0"]的排除 —— 在线角色停在"罗德岛出口"(0/0)是合法状态
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    membership = _scene_membership(cache)
    for path, scene in cache.scene_data.items():
        for cid in getattr(scene, "character_list", []):
            if cid == 0:
                continue
            if cid not in cd:
                failures.append(
                    make_failure(
                        "ROSTER-03",
                        "在编干员与场景名册双向一致",
                        f"{warn}场景{path}的character_list中含幽灵角色id={cid}，character_data中不存在该id",
                        [cid],
                    )
                )
    for cid, c in cd.items():
        if cid == 0:
            continue
        paths = membership.get(cid, [])
        ctx = (
            f"field_commission={flags.get(cid, 'field_commission')}, "
            f"escaping={flags.get(cid, 'escaping')}, be_bagged={flags.get(cid, 'be_bagged')}, "
            f"in_diplomatic_visit={flags.get(cid, 'in_diplomatic_visit')}, vistor={flags.get(cid, 'vistor')}"
        )
        if roster.has(cid):
            pos = activity.position(c.cid)
            # 形状断言放宽为"非空list且元素全为str"：47%场景(248/530)是三段路径，["0","0"]是真实场景非哨兵，
            # map_handle无任何长度约束，故不再断言len==2。畸形position会被下面的路径存在性分支抓住，
            # 这里保留形状分支只为给出更精确的"形状异常"报错文案，不整段删除
            if not (
                isinstance(pos, list)
                and pos
                and all(isinstance(x, str) for x in pos)
            ):
                failures.append(
                    make_failure(
                        "ROSTER-03",
                        "在编干员与场景名册双向一致",
                        (
                            f"{warn}在编角色cid={cid} name={c.name!r} position={pos!r}形状异常(应为非空且元素全为str的l"
                            f"ist)；{ctx}"
                        ),
                        [cid],
                    )
                )
                continue
            expected = _spath(pos)
            if expected not in cache.scene_data:
                failures.append(
                    make_failure(
                        "ROSTER-03",
                        "在编干员与场景名册双向一致",
                        (
                            f"{warn}在编角色cid={cid} name={c.name!r} position={pos}对应路径{expected!r}不存在于scene_d"
                            f"ata中；{ctx}"
                        ),
                        [cid],
                    )
                )
                continue
            if paths != [expected]:
                failures.append(
                    make_failure(
                        "ROSTER-03",
                        "在编干员与场景名册双向一致",
                        (
                            f"{warn}在编角色cid={cid} name={c.name!r} position={pos}(期望仅出现在{expected!r})，"
                            f"实际出现在场景{paths}中；{ctx}"
                        ),
                        [cid],
                    )
                )
        else:
            if paths:
                failures.append(
                    make_failure(
                        "ROSTER-03",
                        "在编干员与场景名册双向一致",
                        f"{warn}离线角色cid={cid} name={c.name!r} 不在npc_id_got中，却残留在场景{paths}中；{ctx}",
                        [cid],
                    )
                )
    return failures


@register_check("ROSTER-04", "离线来源flag必须对应真正的离线态")
def check_offline_source_flag_matches_real_offline_state() -> (
    list[CheckFailure]
):
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 装袋/外勤/越狱三条路径都是"置来源flag→handle_chara_off_line"的原子写法。
    任一来源flag为真而角色仍在编、仍在某场景、或position未归零，即为半离线的幽灵。
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    membership = _scene_membership(cache)
    off = ("field_commission", "escaping", "be_bagged")
    for cid, c in cd.items():
        if cid == 0 or not any(flags.get(cid, k) for k in off):
            continue
        problems = []
        if roster.has(cid):
            problems.append("仍在npc_id_got在编名册中")
        hit = membership.get(cid, [])
        if hit:
            problems.append(f"仍残留在场景{hit}中")
        pos = activity.position(c.cid)
        if pos != ["0", "0"]:
            problems.append(f"position={pos!r}未归零")
        if problems:
            failures.append(
                make_failure(
                    "ROSTER-04",
                    "离线来源flag必须对应真正的离线态",
                    (
                        f"{warn}角色cid={cid} name={c.name!r} 三源flag("
                        f"field_commission={flags.get(cid, 'field_commission')}, "
                        f"escaping={flags.get(cid, 'escaping')}, be_bagged={flags.get(cid, 'be_bagged')})"
                        f"指示应离线，但{'; '.join(problems)}；state={activity.state(c.cid)}，"
                        f"behavior.behavior_id={activity.behavior(c.cid).behavior_id!r}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("ROSTER-05", "监禁flag的来源分区完整")
def check_imprisonment_flag_partition_completeness() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 带imprisonment的角色当且仅当是在册囚犯或逃跑中的前囚犯(escape_success故意保留imprisonment)；
    囚犯与逃犯两个集合互斥
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    imp = {cid for cid in cd if cid != 0 and flags.get(cid, "imprisonment")}
    esc = {cid for cid in cd if cid != 0 and flags.get(cid, "escaping")}
    prisoners_map = prison.prisoners()
    prisoners = set(prisoners_map)
    union = prisoners | esc
    for cid in imp - union:
        c = cd[cid]
        failures.append(
            make_failure(
                "ROSTER-05",
                "监禁flag的来源分区完整",
                (
                    f"{warn}角色cid={cid} name={c.name!r} sp_flag.imprisonment为True，"
                    f"但既不在base.prisoners也不escaping；"
                    f"position={activity.position(c.cid)}，dormitory={chara_life.dormitory(c.cid)!r}，permanent_dormitory={chara_life.permanent_dormitory(c.cid)!r}"
                ),
                [cid],
            )
        )
    for cid in union - imp:
        maybe_c = cd.get(cid)
        failures.append(
            make_failure(
                "ROSTER-05",
                "监禁flag的来源分区完整",
                (
                    f"{warn}角色cid={cid} name={getattr(maybe_c, 'name', '?')!r} 在base.prisoners或escaping中，"
                    f"但sp_flag.imprisonment为False；"
                    f"base.prisoners.get={prisoners_map.get(cid)}"
                ),
                [cid],
            )
        )
    for cid in prisoners & esc:
        c = cd[cid]
        failures.append(
            make_failure(
                "ROSTER-05",
                "监禁flag的来源分区完整",
                f"{warn}角色cid={cid} name={c.name!r} 同时在base.prisoners囚犯名册与escaping逃跑者集合中(应互斥)；"
                f"position={activity.position(c.cid)}，dormitory={chara_life.dormitory(c.cid)!r}",
                [cid],
            )
        )
    return failures


@register_check("ROSTER-06", "囚犯名册条目结构合法且本人在编")
def check_prisoner_record_shape_and_roster_membership() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 校验base.prisoners每条记录形状为[入狱时间, 逃脱概率]，概率夹在0..100之间且非bool污染，
    本人在编且sp_flag.imprisonment为True、escaping为False
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    for cid, rec in prison.prisoners().items():
        if cid == 0 or cid not in cd:
            failures.append(
                make_failure(
                    "ROSTER-06",
                    "囚犯名册条目结构合法且本人在编",
                    f"{warn}囚犯名册键cid={cid}非法(0号玩家或character_data中不存在)，record={rec!r}",
                    [cid],
                )
            )
            continue
        c = cd[cid]
        problems = []
        if not roster.has(cid):
            problems.append("不在npc_id_got在编名册中")
        if not (isinstance(rec, list) and len(rec) == 2):
            problems.append(f"record形状异常，期望长度2的list，实得{rec!r}")
        else:
            entry_time, prob = rec[0], rec[1]
            if not (
                isinstance(entry_time, datetime.datetime)
                and entry_time <= game_time.now()
            ):
                problems.append(
                    f"入狱时间rec[0]={entry_time!r}不是<=game_time({game_time.now()})的datetime"
                )
            if isinstance(prob, bool) or not isinstance(prob, (int, float)):
                problems.append(
                    f"逃脱概率rec[1]={prob!r}类型不是int/float或被bool污染"
                )
            elif not (math.isfinite(prob) and 0 <= prob <= 100):
                problems.append(
                    f"逃脱概率rec[1]={prob}超出[0,100]范围或非有限数"
                )
        if not flags.get(c.cid, "imprisonment"):
            problems.append("sp_flag.imprisonment为False")
        if flags.get(c.cid, "escaping"):
            problems.append("sp_flag.escaping为True(不应与在册囚犯并存)")
        if problems:
            failures.append(
                make_failure(
                    "ROSTER-06",
                    "囚犯名册条目结构合法且本人在编",
                    (
                        f"{warn}囚犯cid={cid} name={c.name!r} 存在问题: {'; '.join(problems)}；record={rec!r}，"
                        f"game_time={game_time.now()}，"
                        f"ability[42]={abilities.ability(c.cid).get(42)}，ability[45]={abilities.ability(c.cid).get(45)}，"
                        f"prison.setting(4)={prison.setting(4)}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("ROSTER-07", "囚犯宿舍是互不重复的合法牢房")
def check_prisoner_dormitory_uniqueness() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 每名囚犯的dormitory都必须在PRISON_DORMS(全部Prison标签场景，即牢1..牢8)集合内，且互不重复。
    唯一性是真实捕获点：指令前提SCENE_ONLY_ONE只看当前在场者，正在调教室的囚犯会让其牢房"看起来是空的"
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    prison_dorms = _prison_dorms(cache)
    dorm_to_cids: dict[str, list[int]] = {}
    prisoners = prison.prisoner_ids()
    for cid in prisoners:
        if cid not in cd:
            continue
        d = chara_life.dormitory(cid)
        dorm_to_cids.setdefault(d, []).append(cid)
    for d, cids in dorm_to_cids.items():
        if d not in prison_dorms:
            for cid in cids:
                c = cd[cid]
                failures.append(
                    make_failure(
                        "ROSTER-07",
                        "囚犯宿舍是互不重复的合法牢房",
                        f"{warn}囚犯cid={cid} name={c.name!r} 的宿舍dormitory={d!r}不在合法牢房集合PRISON_DORMS中；"
                        f"position={activity.position(c.cid)}，permanent_dormitory={chara_life.permanent_dormitory(c.cid)!r}，PRISON_DORMS={sorted(prison_dorms)}",
                        [cid],
                    )
                )
        if len(cids) > 1:
            names = [(cid, cd[cid].name) for cid in cids]
            failures.append(
                make_failure(
                    "ROSTER-07",
                    "囚犯宿舍是互不重复的合法牢房",
                    f"{warn}牢房{d!r}被多名囚犯共用: {names}，len(base.prisoners)={len(prisoners)}",
                    list(cids),
                )
            )
    return failures


@register_check("ROSTER-08", "囚犯留在关押区且不得同时被装袋")
def check_prisoner_stays_in_prison_area_and_not_bagged() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 囚犯cant_move，NPC AI会把不在牢房的囚犯瞬移回宿舍，合法的短暂离房只有"正在H(含调教室)"；
    用position[0] == "关押"比对目录首段，不拼分隔符。囚犯与被装袋互斥 —— 装袋前提含T_IMPRISONMENT_0，
    且chara_become_prisoner首行清be_bagged
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    for cid in prison.prisoner_ids():
        if cid not in cd:
            continue
        c = cd[cid]
        problems = []
        if flags.get(c.cid, "be_bagged"):
            problems.append("同时被装袋(be_bagged=True)")
        if not flags.get(c.cid, "is_h"):
            pos = activity.position(c.cid)
            if not (
                isinstance(pos, list) and len(pos) >= 1 and pos[0] == "关押"
            ):
                problems.append(f"既不在H中也不在关押区，position={pos!r}")
        if problems:
            failures.append(
                make_failure(
                    "ROSTER-08",
                    "囚犯留在关押区且不得同时被装袋",
                    (
                        f"{warn}囚犯cid={cid} name={c.name!r} {'; '.join(problems)}；"
                        f"position={activity.position(c.cid)}，dormitory={chara_life.dormitory(cid)!r}，"
                        f"is_h={flags.get(c.cid, "is_h")}，玩家position={activity.position(0)}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("ROSTER-09", "逃跑者处于完整离线态")
def check_escapee_full_offline_state() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: escape_success依次置escaping→pop囚犯名册→handle_chara_off_line→创建追捕委托，
    并保留imprisonment。任一环缺失即为半态。position == ["0","0"]在此是离线的结果而非判据
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    membership = _scene_membership(cache)
    for cid, c in cd.items():
        if cid == 0 or not flags.get(c.cid, "escaping"):
            continue
        problems = []
        if not flags.get(c.cid, "imprisonment"):
            problems.append("imprisonment应保留为True但为False")
        if prison.is_prisoner(cid):
            problems.append("仍残留在base.prisoners囚犯名册中")
        if roster.has(cid):
            problems.append("仍在npc_id_got在编名册中")
        hit = membership.get(cid, [])
        if hit:
            problems.append(f"仍残留在场景{hit}中")
        if activity.position(c.cid) != ["0", "0"]:
            problems.append(f"position={activity.position(c.cid)!r}未归零")
        if flags.get(c.cid, "field_commission"):
            problems.append(
                f"field_commission={flags.get(c.cid, "field_commission")}非零(逃犯不应挂外勤)"
            )
        if problems:
            failures.append(
                make_failure(
                    "ROSTER-09",
                    "逃跑者处于完整离线态",
                    f"{warn}逃跑者cid={cid} name={c.name!r} {'; '.join(problems)}",
                    [cid],
                )
            )
    return failures


@register_check("ROSTER-10", "逃跑者仍有一条可执行的追捕委托")
def check_escapee_has_executable_capture_commission() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 每个escaping角色都应存在一条reward=="追捕_{cid}_1"且未标记完成的委托配置；
    牢房全满时抓捕结算会静默跳过归案，委托却照样标完成并出表，逃犯从此永久滞留escaping。
    依赖game_config.config_commission，若该配置为空(独立环境/测试未加载配置)则无法判定，直接跳过本条
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, True)
    failures: list[CheckFailure] = []
    if not game_config.config_commission:
        return failures
    finished = commission.finished()
    for cid, c in cd.items():
        if cid == 0 or not flags.get(c.cid, "escaping"):
            continue
        target_reward = f"追捕_{cid}_1"
        candidates = [
            com_id
            for com_id, com in game_config.config_commission.items()
            if getattr(com, "reward", "") == target_reward
            and com_id not in finished
        ]
        if not candidates:
            failures.append(
                make_failure(
                    "ROSTER-10",
                    "逃跑者仍有一条可执行的追捕委托",
                    f"{warn}逃跑者cid={cid} name={c.name!r} 没有任何未完成的追捕委托(期望reward={target_reward!r})；"
                    f"已完成的委托={sorted(finished)}，"
                    f"进行中的委托id列表={list(commission.ongoing())}，当前囚犯数={len(prison.prisoner_ids())}",
                    [cid],
                )
            )
    return failures


@register_check("ROSTER-11", "监狱长缓存唯一且指向真实岗位")
def check_warden_cache_unique_and_valid() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 在编干员里最多只能有一名工作类型191的监狱长，监狱长(work.warden)非零时必须指向存在的角色，
    不能与那名在编191冲突。"wid非零而没有任何在编191"是可达残留，已拆到ROSTER-12作warning，不进本条
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    wid = work.warden()
    if type(wid) is not int:
        failures.append(
            make_failure(
                "ROSTER-11",
                "监狱长缓存唯一且指向真实岗位",
                f"{warn}监狱长(work.warden)类型异常: {wid!r}",
                [],
            )
        )
        return failures
    wardens = {
        cid
        for cid in roster.active()
        if cid != 0 and cid in cd and chara_life.work_type(cid) == 191
    }
    if len(wardens) > 1:
        details = [(c, cd[c].name, chara_life.dormitory(c)) for c in wardens]
        failures.append(
            make_failure(
                "ROSTER-11",
                "监狱长缓存唯一且指向真实岗位",
                (
                    f"{warn}存在{len(wardens)}名在编工作类型191(监狱长)的角色，超过唯一上限: {details}，"
                    f"work.warden()={wid}"
                ),
                list(wardens),
            )
        )
    if wid:
        if wid not in cd:
            failures.append(
                make_failure(
                    "ROSTER-11",
                    "监狱长缓存唯一且指向真实岗位",
                    f"{warn}work.warden()={wid}指向的角色不存在于character_data中",
                    [wid],
                )
            )
        elif wardens - {wid}:
            others = sorted(wardens - {wid})
            failures.append(
                make_failure(
                    "ROSTER-11",
                    "监狱长缓存唯一且指向真实岗位",
                    (
                        f"{warn}work.warden()={wid}与另外在编191岗位角色冲突: "
                        f"{[(cid, cd[cid].name) for cid in others]}"
                    ),
                    [wid] + others,
                )
            )
    return failures


@register_check("ROSTER-12", "监狱长身份软约束")
def check_warden_identity_soft_constraints() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 期望状态：监狱长(work.warden)非零时该人在编、宿舍是关押区休息室、不是囚犯/访客、不在外勤。
    三项都可被合法操作打破(装袋前提未排除监狱长，玩家可把监狱长本人装袋后投入监牢)，故只作提示
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, True)
    failures: list[CheckFailure] = []
    wid = work.warden()
    if not wid or wid not in cd:
        return failures
    w = cd[wid]
    warden_dorm = _warden_dorm()
    problems = []
    if not roster.has(wid):
        problems.append("不在npc_id_got在编名册中")
    if chara_life.work_type(wid) != 191:
        problems.append(f"work.work_type={chara_life.work_type(wid)}不是191")
    if chara_life.dormitory(wid) != warden_dorm:
        problems.append(
            f"dormitory={chara_life.dormitory(wid)!r}不是关押/休息室({warden_dorm!r})"
        )
    if prison.is_prisoner(wid):
        problems.append("是当前囚犯(在base.prisoners中)")
    if flags.get(w.cid, "vistor") == 1:
        problems.append("当前是在岛访客(vistor==1)")
    if flags.get(w.cid, "field_commission"):
        problems.append(
            f"field_commission={flags.get(w.cid, "field_commission")}非零(在外勤中)"
        )
    if flags.get(w.cid, "be_bagged"):
        problems.append("被装袋(be_bagged=True)")
    if problems:
        player = cd.get(0)
        failures.append(
            make_failure(
                "ROSTER-12",
                "监狱长身份软约束",
                (
                    f"{warn}监狱长wid={wid} name={w.name!r} 偏离期望状态: {'; '.join(problems)}；"
                    f"permanent_dormitory={chara_life.permanent_dormitory(wid)!r}，"
                    f"玩家bagging_chara_id={flags.get(0, 'bagging_chara_id') if player is not None else None}"
                ),
                [wid],
            )
        )
    return failures


@register_check("ROSTER-13", "监禁调教设置键齐全且取值在选项范围内")
def check_confinement_training_setting_keys_and_range() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 设置字典由配置表全量初始化为0，UI用option[cid][value]直接索引(越界IndexError)，
    结算路径对[4]/[13]直取(缺键KeyError)。type(v) is int而非isinstance，避免bool污染被当作合法整数放过。
    依赖game_config.config_confinement_training_setting，若为空(独立环境未加载配置)则循环自然不产生任何失败，等价于跳过本条
    """
    cache = cache_control.cache
    settings = prison.settings()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    for cid in game_config.config_confinement_training_setting:
        option = game_config.config_confinement_training_setting_option.get(
            cid, []
        )
        if cid not in settings:
            failures.append(
                make_failure(
                    "ROSTER-13",
                    "监禁调教设置键齐全且取值在选项范围内",
                    f"{warn}设置项cid={cid}缺失于base.prison_settings，option长度={len(option)}",
                    [],
                )
            )
            continue
        v = settings[cid]
        if type(v) is not int:
            failures.append(
                make_failure(
                    "ROSTER-13",
                    "监禁调教设置键齐全且取值在选项范围内",
                    f"{warn}设置项cid={cid}取值v={v!r}类型不是int(可能被bool污染)",
                    [],
                )
            )
            continue
        if not (0 <= v < len(option)):
            failures.append(
                make_failure(
                    "ROSTER-13",
                    "监禁调教设置键齐全且取值在选项范围内",
                    f"{warn}设置项cid={cid}取值v={v}越界，option长度={len(option)}，完整设置={dict(settings)}",
                    [],
                )
            )
    return failures


@register_check("ROSTER-14", "访客名册与访客flag完全等价")
def check_visitor_registry_and_flag_equivalence() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: base.visitor的访客名册与sp_flag.vistor == 1的角色是同一批人，且当前访客都在在编名册(roster.active())里。
    不写成vistor != 0，因为前访客恒为2，是合法状态，不应被本条判为不一致
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    vis_flag = {cid for cid in cd if cid != 0 and flags.get(cid, "vistor") == 1}
    vis_reg = set(visitor.visitors())
    for cid in vis_reg - vis_flag:
        c = cd.get(cid)
        v = flags.get(c.cid, "vistor") if c is not None else None
        failures.append(
            make_failure(
                "ROSTER-14",
                "访客名册与访客flag完全等价",
                f"{warn}cid={cid}在访客名册中，但sp_flag.vistor={v}不为1",
                [cid],
            )
        )
    for cid in vis_flag - vis_reg:
        c = cd[cid]
        failures.append(
            make_failure(
                "ROSTER-14",
                "访客名册与访客flag完全等价",
                (
                    f"{warn}cid={cid} name={c.name!r} sp_flag.vistor==1，但不在访客名册中，"
                    f"dormitory={chara_life.dormitory(c.cid)!r}"
                ),
                [cid],
            )
        )
    for cid in vis_reg - roster.active():
        c = cd.get(cid)
        failures.append(
            make_failure(
                "ROSTER-14",
                "访客名册与访客flag完全等价",
                f"{warn}访客cid={cid} name={getattr(c, 'name', '?')!r} 不在cache.npc_id_got在编名册中",
                [cid],
            )
        )
    return failures


@register_check("ROSTER-15", "访客住在互不重复的客房")
def check_visitor_room_uniqueness() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 访客由分配器挑一间没有别的访客占用的客房；用场景标签集合GUEST_ROOMS判定房间合法性，
    比"客房" in d的子串判定更强。注意：Linux上分配器room_full_path.split("\\")[-1]与配置房间名比对会失配，
    dormitory可能长期停在模板初值，本条在本机命中即为跨平台缺陷的真实证据，不应回头放宽检查
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    guest_rooms = _guest_rooms(cache)
    room_to_cids: dict[str, list[int]] = {}
    for cid in visitor.visitors():
        if cid not in cd:
            failures.append(
                make_failure(
                    "ROSTER-15",
                    "访客住在互不重复的客房",
                    f"{warn}访客cid={cid}不在character_data中",
                    [cid],
                )
            )
            continue
        c = cd[cid]
        d = chara_life.dormitory(c.cid)
        room_to_cids.setdefault(d, []).append(cid)
        if d not in guest_rooms:
            open_2000 = {
                k: v for k, v in facility.opens().items() if 2000 < k < 2100
            }
            failures.append(
                make_failure(
                    "ROSTER-15",
                    "访客住在互不重复的客房",
                    f"{warn}访客cid={cid} name={c.name!r} 的dormitory={d!r}不在合法客房集合GUEST_ROOMS中；"
                    f"position={activity.position(c.cid)}，访客上限={visitor.capacity()}，facility_open(2000-2099)={open_2000}",
                    [cid],
                )
            )
    for d, cids in room_to_cids.items():
        if len(cids) > 1:
            names = [(cid, cd[cid].name) for cid in cids]
            failures.append(
                make_failure(
                    "ROSTER-15",
                    "访客住在互不重复的客房",
                    f"{warn}客房{d!r}被多名访客共用: {names}",
                    list(cids),
                )
            )
    return failures


@register_check("ROSTER-16", "访客人数不超过客房上限")
def check_visitor_count_within_capacity() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 访客数不超过visitor.capacity()按已开放客房数算出的访客上限。级别为warning
    """
    cache = cache_control.cache
    warn = _sev(cache, True)
    failures: list[CheckFailure] = []
    visitors = visitor.visitors()
    if len(visitors) > visitor.capacity():
        open_2000 = {
            k: v for k, v in facility.opens().items() if 2000 < k < 2100
        }
        failures.append(
            make_failure(
                "ROSTER-16",
                "访客人数不超过客房上限",
                f"{warn}当前访客数={len(visitors)}超过访客上限={visitor.capacity()}；"
                f"facility_open(2000-2099)={open_2000}，facility_level[13]={facility.levels().get(13)}",
                list(visitors),
            )
        )
    return failures


@register_check("ROSTER-17", "没有严重逾期未结算的访客")
def check_no_severely_overdue_visitors() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: base.visitor里没有离开时刻已过去一整天或更久的访客。访客到期由跨日结算处理一次，
    "D日到期、D+1日00:00才结算"是正常窗口，阈值因此放到一整天，否则会周期性误报
    """
    cache = cache_control.cache
    warn = _sev(cache, True)
    failures: list[CheckFailure] = []
    for cid, end in visitor.visitors().items():
        delta = game_time.now() - end
        if delta.days >= 1:
            failures.append(
                make_failure(
                    "ROSTER-17",
                    "没有严重逾期未结算的访客",
                    f"{warn}访客cid={cid}到期时间{end}已逾期{delta}，超过一整天未结算(可能日结算漏跑或该访客被卡住)；"
                    f"game_time={game_time.now()}，上次随机来访={visitor.last_arrival()}，"
                    f"罗德岛抵达过别处={visitor.moved()}",
                    [cid],
                )
            )
    return failures


@register_check("ROSTER-18", "邀请栏结构完整、空目标必归零")
def check_invite_visitor_shape_integrity() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: base.visitor的邀请是(目标id, 进度)，目标是int，进度是非负有限数，目标为0时进度为0。
    不加进度上界，因为客房满时settle_visitor_arrivals返回失败且不清零，进度停在>=100甚至继续增长是合法状态。
    本条的类型守卫由_invite_target复现，供ROSTER-19/21/27复用，各条各自调用_invite_target，不依赖调用顺序
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    raw = visitor.invite()
    problems = []
    if type(raw[0]) is not int:
        problems.append(f"目标={raw[0]!r}类型不是int")
    x = raw[1]
    if (
        isinstance(x, bool)
        or not isinstance(x, (int, float))
        or not math.isfinite(x)
        or x < 0
    ):
        problems.append(f"进度={x!r}不是非负有限数")
    elif type(raw[0]) is int and raw[0] == 0 and x != 0:
        problems.append(f"目标为0但进度={x!r}未归零")
    if problems:
        target = raw[0] if type(raw[0]) is int else None
        exists = target in cd if target else None
        failures.append(
            make_failure(
                "ROSTER-18",
                "邀请栏结构完整、空目标必归零",
                (
                    f"{warn}邀请(目标, 进度)={raw!r}存在问题: {'; '.join(problems)}；"
                    f"facility_level[13]={facility.levels().get(13)}，"
                    f"game_time={game_time.now()}，目标是否存在于character_data={exists}"
                ),
                [target] if target else [],
            )
        )
    return failures


@register_check("ROSTER-19", "邀请目标仍是合法的未入编候选")
def check_invite_target_still_valid_candidate() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 邀请目标只能来自find_recruitable_npc()。若目标在邀请期间被招募线或访客抽中，进度满100时
    会对一个已在编角色再跑一次get_new_character。用vistor != 1而非== 0 —— find_recruitable_npc只跳过vistor==1，
    前访客(vistor==2)是合法邀请目标。position == ["0","0"]在此是未入编角色的必要属性，不是离线判据
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    t = _invite_target()
    if not t:
        return failures
    if t not in cd:
        failures.append(
            make_failure(
                "ROSTER-19",
                "邀请目标仍是合法的未入编候选",
                f"{warn}邀请目标t={t}不存在于character_data中，邀请(目标, 进度)={visitor.invite()!r}",
                [t],
            )
        )
        return failures
    c = cd[t]
    problems = []
    if roster.has(t):
        problems.append("已在npc_id_got在编名册中")
    if visitor.is_visitor(t):
        problems.append("已在访客名册中")
    if t in recruit.pending():
        problems.append("已在recruit.pending()待确认招募名单中")
    if prison.is_prisoner(t):
        problems.append("已在base.prisoners囚犯名册中")
    if flags.get(c.cid, "vistor") == 1:
        problems.append("当前是在岛访客(vistor==1)")
    if flags.get(c.cid, "imprisonment"):
        problems.append("sp_flag.imprisonment为True")
    if flags.get(c.cid, "escaping"):
        problems.append("sp_flag.escaping为True")
    if flags.get(c.cid, "field_commission"):
        problems.append(
            f"sp_flag.field_commission={flags.get(c.cid, "field_commission")}非零"
        )
    if (where := activity.position(c.cid)) != ["0", "0"]:
        problems.append(f"position={where!r}未归零(未入编角色的必要属性)")
    if problems:
        failures.append(
            make_failure(
                "ROSTER-19",
                "邀请目标仍是合法的未入编候选",
                f"{warn}邀请目标t={t} name={c.name!r} adv={c.adv} 不再是合法候选: {'; '.join(problems)}；"
                f"访客数={len(visitor.visitors())}，访客上限={visitor.capacity()}",
                [t],
            )
        )
    return failures


@register_check("ROSTER-20", "待确认招募名单合法")
def check_recruited_id_pool_validity() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 待确认招募名单recruit.pending()是"已招募待玩家确认"的暂存池，
    里面不该有0、不存在的id，也不该有已在编或身份冲突的人。
    同样用vistor != 1(两个写入点都取自find_recruitable_npc，vistor == 2可合法入池)
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    for cid in recruit.pending():
        if cid == 0 or cid not in cd:
            failures.append(
                make_failure(
                    "ROSTER-20",
                    "待确认招募名单合法",
                    (
                        f"{warn}recruited_id中的cid={cid}非法(0号玩家或不存在于character_data)，"
                        f"全量recruited_id={sorted(recruit.pending())}"
                    ),
                    [cid],
                )
            )
            continue
        c = cd[cid]
        problems = []
        if roster.has(cid):
            problems.append("已在npc_id_got在编名册中")
        if visitor.is_visitor(cid):
            problems.append("已在访客名册中")
        if flags.get(c.cid, "vistor") == 1:
            problems.append("当前是在岛访客(vistor==1)")
        if flags.get(c.cid, "imprisonment"):
            problems.append("sp_flag.imprisonment为True")
        if flags.get(c.cid, "escaping"):
            problems.append("sp_flag.escaping为True")
        if flags.get(c.cid, "field_commission"):
            problems.append(
                f"sp_flag.field_commission={flags.get(c.cid, "field_commission")}非零"
            )
        if activity.position(c.cid) != ["0", "0"]:
            problems.append(f"position={activity.position(c.cid)!r}未归零")
        if problems:
            failures.append(
                make_failure(
                    "ROSTER-20",
                    "待确认招募名单合法",
                    f"{warn}待确认招募cid={cid} name={c.name!r} adv={c.adv} {'; '.join(problems)}；"
                    f"len(npc_id_got)={roster.count()}，people_max={facility.people_max()}",
                    [cid],
                )
            )
    return failures


@register_check("ROSTER-21", "当前访客与其它名册身份互斥")
def check_visitor_identity_mutual_exclusion() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 当前访客不能同时是待确认招募、邀请目标、囚犯、逃犯或外勤队员 —— 这些身份的在线规则互相冲突。
    C集合的构造自带形状守卫，不依赖ROSTER-25先跑通过
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    V = set(visitor.visitors())
    P = recruit.pending()
    t = _invite_target()
    invited = {t} if t else set()
    C: set[int] = set()
    for r in commission.ongoing().values():
        C |= set(r.team)
    R = set(prison.prisoner_ids())
    E = {cid for cid in cd if cid != 0 and flags.get(cid, "escaping")}
    named = {
        "待确认招募(recruited_id)": P,
        "邀请目标(invite_visitor)": invited,
        "外勤中(base.commission)": C,
        "囚犯(base.prisoners)": R,
        "逃跑者(escaping)": E,
    }
    for cid in V:
        c = cd.get(cid)
        hit_names = [label for label, s in named.items() if cid in s]
        if hit_names:
            failures.append(
                make_failure(
                    "ROSTER-21",
                    "当前访客与其它名册身份互斥",
                    f"{warn}访客cid={cid} name={getattr(c, 'name', '?')!r} 同时命中身份集合: {hit_names}；"
                    f"vistor={flags.get(cid, 'vistor') if c is not None else None}，recruited_id={sorted(P)}，"
                    f"邀请(目标, 进度)={visitor.invite()!r}，cid in npc_id_got={roster.has(cid)}",
                    [cid],
                )
            )
    return failures


@register_check("ROSTER-22", "招募线记录形状与进度范围")
def check_recruit_line_shape_and_progress_range() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 每条招募线（recruit.lines()）的进度为非负有限数，策略与主专员为整数，
    进度上界<100由增量写入与结算相邻两行保证，不存在"已加未结"窗口。
    策略id子句依赖game_config.config_recruitment_strategy，若为空(独立环境未加载配置)则降级跳过该子句
    """
    cache = cache_control.cache
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    strategy_ids = set(game_config.config_recruitment_strategy)
    for lid, rec in recruit.lines().items():
        problems = []
        progress, strategy, main_hr = (
            rec["progress"],
            rec["strategy"],
            rec["main"],
        )
        if (
            isinstance(progress, bool)
            or not isinstance(progress, (int, float))
            or not math.isfinite(progress)
            or not (0 <= progress < 100)
        ):
            problems.append(
                f"进度progress={progress!r}不在[0,100)内、非有限数或被bool污染"
            )
        if type(strategy) is not int:
            problems.append(f"策略id strategy={strategy!r}类型不是int")
        elif strategy_ids and strategy not in strategy_ids:
            problems.append(
                f"策略id strategy={strategy}不在game_config.config_recruitment_strategy中"
            )
        if type(main_hr) is not int:
            problems.append(f"主专员id main={main_hr!r}类型不是int")
        if problems:
            failures.append(
                make_failure(
                    "ROSTER-22",
                    "招募线记录形状与进度范围",
                    (
                        f"{warn}招募线lid={lid} record={rec!r} {'; '.join(problems)}；"
                        f"facility_level[7]={facility.levels().get(7)}，"
                        f"game_time={game_time.now()}"
                    ),
                    [],
                )
            )
    return failures


@register_check("ROSTER-23", "招募线主专员真实可用且不重复")
def check_recruit_line_main_hr_validity_and_uniqueness() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 每条线的主招聘专员是0(空缺)或一名工作类型71且在招聘专员名单work.roster(71)内的角色；
    同一人不能同时主理两条线。不含cid in npc_id_got —— 派遣外勤不改work_type，把主专员派出去是常规操作，
    加在线子句必然长期误报
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    mains = [rec["main"] for rec in recruit.lines().values() if rec["main"]]
    dup = {cid for cid in mains if mains.count(cid) > 1}
    if dup:
        failures.append(
            make_failure(
                "ROSTER-23",
                "招募线主专员真实可用且不重复",
                (
                    f"{warn}以下角色同时是多条招募线的主专员(重复): {sorted(dup)}；"
                    f"完整recruit_line={recruit.lines()}"
                ),
                sorted(dup),
            )
        )
    for cid in set(mains):
        problems = []
        c = cd.get(cid)
        if c is None:
            problems.append("不存在于character_data")
        else:
            if cid not in work.roster(work.HR_WORK):
                problems.append("不在招聘专员名单work.roster(71)中")
            work_type = chara_life.work_type(c.cid)
            if work_type != 71:
                problems.append(f"work.work_type={work_type}不是71")
        if problems:
            failures.append(
                make_failure(
                    "ROSTER-23",
                    "招募线主专员真实可用且不重复",
                    f"{warn}主专员cid={cid} name={getattr(c, 'name', '?')!r} {'; '.join(problems)}；"
                    f"field_commission={flags.get(cid, 'field_commission') if c is not None else None}，"
                    f"cid in npc_id_got={roster.has(cid)}，work.roster(71)={work.roster(work.HR_WORK)}",
                    [cid],
                )
            )
    return failures


@register_check("ROSTER-24", "招聘专员列表无重复、成员岗位正确、在编71全部在内")
def check_hr_operator_list_integrity() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 招聘专员名单work.roster(71)是招募效率计算用的名单。可断言的是：无重复、成员都是存在的非玩家角色且
    工作类型仍为71、所有在编的71号岗位都已收录。不做集合相等 —— 名册只在刷新时按npc_id_got重建，下线（移出npc_id_got）的
    成员留在名册里直到下一次刷新，只保留"在编71 ⊆ 列表"这一个方向
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    hr = work.roster(work.HR_WORK)
    dup = {cid for cid in hr if hr.count(cid) > 1}
    if dup:
        failures.append(
            make_failure(
                "ROSTER-24",
                "招聘专员列表无重复、成员岗位正确、在编71全部在内",
                f"{warn}work.roster(71)中存在重复id: {sorted(dup)}，完整列表={hr}",
                sorted(dup),
            )
        )
    for cid in set(hr):
        problems = []
        c = cd.get(cid)
        if cid == 0 or c is None:
            problems.append("为0号玩家或不存在于character_data")
        elif (work_type := chara_life.work_type(c.cid)) != 71:
            problems.append(f"work.work_type={work_type}不是71")
        if problems:
            failures.append(
                make_failure(
                    "ROSTER-24",
                    "招聘专员列表无重复、成员岗位正确、在编71全部在内",
                    f"{warn}work.roster(71)成员cid={cid} {'; '.join(problems)}；name={getattr(c, 'name', '?')!r}",
                    [cid],
                )
            )
    work71 = {
        cid
        for cid in roster.active()
        if cid != 0 and cid in cd and chara_life.work_type(cid) == 71
    }
    for cid in work71 - set(hr):
        c = cd[cid]
        failures.append(
            make_failure(
                "ROSTER-24",
                "招聘专员列表无重复、成员岗位正确、在编71全部在内",
                f"{warn}在编71号岗位角色cid={cid} name={c.name!r} 未被收录进work.roster(71)；"
                f"field_commission={flags.get(c.cid, 'field_commission')}，"
                f"in_diplomatic_visit={flags.get(c.cid, 'in_diplomatic_visit')}",
                [cid],
            )
        )
    return failures


@register_check("ROSTER-25", "进行中委托记录结构合法、人员全局唯一")
def check_ongoing_commission_shape_and_member_uniqueness() -> (
    list[CheckFailure]
):
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: base.commission里进行中委托的id不为0，同一人不在一个委托的队伍里重复出现，也不同时在两个委托的队伍里
    """
    cache = cache_control.cache
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    seen: dict[int, int] = {}
    for mid, r in commission.ongoing().items():
        problems = []
        if mid == 0:
            problems.append(f"委托id={mid!r}非法(应为非零int)")
        members = list(r.team)
        if len(members) != len(set(members)):
            problems.append(f"队伍内部有重复干员id: {members}")
        dup_across = set(members) & set(seen)
        if dup_across:
            problems.append(
                f"以下干员同时出现在别的委托中: {[(cid, seen[cid]) for cid in dup_across]}"
            )
        for cid in members:
            seen.setdefault(cid, mid)
        if problems:
            failures.append(
                make_failure(
                    "ROSTER-25",
                    "进行中委托记录结构合法、人员全局唯一",
                    f"{warn}委托mid={mid} {'; '.join(problems)}；完整record={r!r}，game_time={game_time.now()}",
                    members,
                )
            )
    return failures


@register_check("ROSTER-26", "外勤名单与角色外勤flag双向一致")
def check_field_commission_membership_flag_consistency() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 派遣时逐人写sp_flag.field_commission = 委托id，结算时逐人清0再上线。两侧必须互指同一委托，
    任一单向残留都要报出来。真实可达捕获点：本地外交官被派出外勤后基地返回该国时会对他调handle_chara_on_line，
    整体重建sp_flag把field_commission抹成0并塞回名册，而委托记录里还挂着他
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    membership_scene = _scene_membership(cache)
    membership: dict[int, int] = {}
    for mid, r in commission.ongoing().items():
        for cid in r.team:
            if cid == 0 or cid not in cd:
                failures.append(
                    make_failure(
                        "ROSTER-26",
                        "外勤名单与角色外勤flag双向一致",
                        f"{warn}委托mid={mid}人员列表含非法cid={cid}",
                        [cid] if isinstance(cid, int) else [],
                    )
                )
                continue
            c = cd[cid]
            if flags.get(c.cid, "field_commission") != mid:
                failures.append(
                    make_failure(
                        "ROSTER-26",
                        "外勤名单与角色外勤flag双向一致",
                        (
                            f"{warn}委托mid={mid}人员cid={cid} name={c.name!r} "
                            f"的sp_flag.field_commission={flags.get(c.cid, 'field_commission')}"
                            f"与所属委托不一致；cid in npc_id_got={roster.has(cid)}，"
                            f"position={activity.position(c.cid)}，"
                            f"命中场景={membership_scene.get(cid, [])}"
                        ),
                        [cid],
                    )
                )
            membership[cid] = mid
    flagged = {
        cid for cid in cd if cid != 0 and flags.get(cid, "field_commission")
    }
    for cid in flagged - set(membership):
        c = cd[cid]
        failures.append(
            make_failure(
                "ROSTER-26",
                "外勤名单与角色外勤flag双向一致",
                (
                    f"{warn}角色cid={cid} name={c.name!r} "
                    f"sp_flag.field_commission={flags.get(c.cid, 'field_commission')}非零，"
                    f"但未出现在任何委托记录的人员列表中；cid in npc_id_got={roster.has(cid)}，"
                    f"position={activity.position(c.cid)}，"
                    f"命中场景={membership_scene.get(cid, [])}"
                ),
                [cid],
            )
        )
    return failures


@register_check("ROSTER-27", "外勤人员不得兼任访客/囚犯/助理/监狱长/招募目标")
def check_field_commission_member_identity_exclusion() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 派遣候选表显式排除访客、助理、监狱长以及2类(临盆/产后/监禁)、7类(离线)异常；待确认招募与
    邀请目标本就不在在编名册内。这些身份同时成立意味着有别的流程绕过了派遣面板
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    C: set[int] = set()
    commission_of: dict[int, int] = {}
    for mid, r in commission.ongoing().items():
        for cid in r.team:
            C.add(cid)
            commission_of.setdefault(cid, mid)
    t = _invite_target()
    player = cd.get(0)
    assistant = relations.assistant_character_id(0) if player is not None else 0
    forbidden = {
        "访客(base.visitor)": set(visitor.visitors()),
        "待确认招募(recruited_id)": recruit.pending(),
        "囚犯(base.prisoners)": set(prison.prisoner_ids()),
        "邀请目标(invite_visitor)": {t} if t else set(),
        "监狱长(work.warden)": {work.warden()} if work.warden() else set(),
        "逃跑者(escaping)": {
            cid for cid in cd if cid != 0 and flags.get(cid, "escaping")
        },
        "助理(assistant_character_id)": {assistant} if assistant else set(),
    }
    for cid in C:
        c = cd.get(cid)
        hit = [label for label, s in forbidden.items() if cid in s]
        if hit:
            failures.append(
                make_failure(
                    "ROSTER-27",
                    "外勤人员不得兼任访客/囚犯/助理/监狱长/招募目标",
                    (
                        f"{warn}外勤中cid={cid} name={getattr(c, 'name', '?')!r}(委托mid={commission_of.get(cid)}) "
                        f"同时命中身份集合: {hit}；"
                        f"work.work_type={chara_life.work_type(cid) if c is not None else None}，"
                        f"work.warden()={work.warden()}，"
                        f"assistant_character_id={assistant}，dormitory={chara_life.dormitory(cid) if c else None}"
                    ),
                    [cid],
                )
            )
        if c is not None:
            if flags.get(c.cid, "vistor") == 1:
                failures.append(
                    make_failure(
                        "ROSTER-27",
                        "外勤人员不得兼任访客/囚犯/助理/监狱长/招募目标",
                        (
                            f"{warn}外勤中cid={cid} name={c.name!r}(委托mid={commission_of.get(cid)}) "
                            f"sp_flag.vistor==1(当前在岛访客)"
                        ),
                        [cid],
                    )
                )
            if flags.get(c.cid, "imprisonment"):
                failures.append(
                    make_failure(
                        "ROSTER-27",
                        "外勤人员不得兼任访客/囚犯/助理/监狱长/招募目标",
                        (
                            f"{warn}外勤中cid={cid} name={c.name!r}(委托mid={commission_of.get(cid)}) "
                            f"sp_flag.imprisonment为True"
                        ),
                        [cid],
                    )
                )
    return failures


@register_check("ROSTER-28", "载具外勤中数与委托明细守恒")
def check_vehicle_busy_count_conservation() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: base.vehicles[vid] = (拥有数, 外勤中数)，外勤中数等于所有进行中委托里这种载具的出现次数且在0与拥有数之间，
    委托里出现的载具都在载具表里。完成结算先调settle_vehicle再删委托，计数错误会直接表现为"有车却派不出去"或负库存
    """
    cache = cache_control.cache
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    used: collections.Counter[int] = collections.Counter()
    ongoing = commission.ongoing()
    for r in ongoing.values():
        used.update(r.vehicles)
    vehicles = commission.vehicles()
    for vid in set(used) - set(vehicles):
        failures.append(
            make_failure(
                "ROSTER-28",
                "载具外勤中数与委托明细守恒",
                f"{warn}委托明细中出现的载具vid={vid}未在载具表中登记，使用次数={used[vid]}",
                [],
            )
        )
    for vid, v in vehicles.items():
        if not all(type(x) is int for x in v):
            failures.append(
                make_failure(
                    "ROSTER-28",
                    "载具外勤中数与委托明细守恒",
                    f"{warn}载具表[{vid}]类型异常，期望(拥有数,外勤中数)两个int，实得{v!r}",
                    [],
                )
            )
            continue
        own, busy = v[0], v[1]
        u = used.get(vid, 0)
        if not (0 <= busy <= own):
            failures.append(
                make_failure(
                    "ROSTER-28",
                    "载具外勤中数与委托明细守恒",
                    f"{warn}载具vid={vid} 外勤中数busy={busy}不在[0,拥有数own={own}]范围内",
                    [],
                )
            )
        if busy != u:
            detail = {mid: r.vehicles for mid, r in ongoing.items()}
            failures.append(
                make_failure(
                    "ROSTER-28",
                    "载具外勤中数与委托明细守恒",
                    f"{warn}载具vid={vid} 缓存外勤中数busy={busy}与委托明细实际出现次数{u}不一致，vehicles[{vid}]={v}，"
                    f"委托载具明细={detail}",
                    [],
                )
            )
    return failures


@register_check("ROSTER-29", "进行中委托id有效且未逾期")
def check_ongoing_commission_id_valid_and_not_overdue() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 委托完成判定在每个非时停玩家回合的行为树里先于NPC结算跑一次，回合结束时留下的委托必须严格
    满足end_time > game_time(> 而非 >=，恰好到点的委托按完成条件本应已结算)；逾期判定排除debug_mode与time_stop_mode。
    id有效性依赖game_config.config_commission，若为空(独立环境未加载配置)则降级跳过该子句，仅保留结构与逾期判定
    """
    cache = cache_control.cache
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    config_loaded = bool(game_config.config_commission)
    for mid, r in commission.ongoing().items():
        if config_loaded and mid not in game_config.config_commission:
            failures.append(
                make_failure(
                    "ROSTER-29",
                    "进行中委托id有效且未逾期",
                    f"{warn}进行中委托mid={mid}在game_config.config_commission中查不到配置",
                    [],
                )
            )
        end_time = r.end
        if not cache.debug_mode and not modes.time_stop():
            if not (end_time > game_time.now()):
                overdue = game_time.now() - end_time
                members = list(r.team)
                failures.append(
                    make_failure(
                        "ROSTER-29",
                        "进行中委托id有效且未逾期",
                        f"{warn}委托mid={mid}已到期或逾期，end_time={end_time}，game_time={game_time.now()}，逾期时长={overdue}；"
                        f"人员={members}，已完成的委托={sorted(commission.finished())}",
                        members,
                    )
                )
    return failures


@register_check("ROSTER-30", "外交官表与角色外派flag双向一致")
def check_diplomat_registry_and_flag_consistency() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 任命写diplomacy的[国家]["diplomat"] = id与sp_flag.in_diplomatic_visit = 国家，解任同时清两者。
    外派到非当前所在国的外交官处于离线态，罗德岛抵达该国时会让他上线。本条大概率会报出真实缺陷：
    handle_chara_on_line整体重建sp_flag会把in_diplomatic_visit抹成0
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    current_country = location.country()
    posts = diplomacy.table()
    for country, post in posts.items():
        did = post["diplomat"]
        if not did:
            continue
        if did not in cd:
            failures.append(
                make_failure(
                    "ROSTER-30",
                    "外交官表与角色外派flag双向一致",
                    f"{warn}国家{country}的外交官did={did}不存在于character_data中",
                    [did],
                )
            )
            continue
        c = cd[did]
        problems = []
        if flags.get(c.cid, "in_diplomatic_visit") != country:
            problems.append(
                f"sp_flag.in_diplomatic_visit={flags.get(c.cid, "in_diplomatic_visit")}与所属国家{country}不一致"
            )
        if current_country is not None:
            if country != current_country:
                if roster.has(did):
                    problems.append(
                        f"外派到非当前所在国({country}!={current_country})但仍在npc_id_got在编名册中"
                    )
            else:
                if not roster.has(did):
                    problems.append(
                        f"外派国家与当前所在国一致({country})但不在npc_id_got在编名册中"
                    )
        if problems:
            failures.append(
                make_failure(
                    "ROSTER-30",
                    "外交官表与角色外派flag双向一致",
                    f"{warn}国家{country}外交官did={did} name={c.name!r} {'; '.join(problems)}；"
                    f"work.work_type={chara_life.work_type(c.cid)}，所在国家={current_country}，position={activity.position(c.cid)}",
                    [did],
                )
            )
    for cid, c in cd.items():
        visit = flags.get(c.cid, "in_diplomatic_visit")
        if cid == 0 or not visit:
            continue
        slot = posts.get(visit, diplomacy.VACANT)
        if slot["diplomat"] != cid:
            failures.append(
                make_failure(
                    "ROSTER-30",
                    "外交官表与角色外派flag双向一致",
                    f"{warn}角色cid={cid} name={c.name!r} sp_flag.in_diplomatic_visit={visit}，"
                    f"但diplomacy[{visit}]={slot!r}的外交官不指回该角色",
                    [cid],
                )
            )
    return failures


@register_check("ROSTER-32", "助理身份互斥")
def check_assistant_identity_exclusion() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 助理候选排除访客、监狱长以及2/7类异常。各写入点都做了过滤，且统一离线流程会调
    handle_assistant_reset把离线角色从助理位清掉 —— 命中即为某个任命流程漏清身份的真实问题
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    player = cd.get(0)
    if player is None:
        return failures
    a = relations.assistant_character_id(0)
    if type(a) is not int:
        failures.append(
            make_failure(
                "ROSTER-32",
                "助理身份互斥",
                f"{warn}cd[0].assistant_character_id类型异常: {a!r}",
                [],
            )
        )
        return failures
    if not a:
        return failures
    if a not in cd:
        failures.append(
            make_failure(
                "ROSTER-32",
                "助理身份互斥",
                f"{warn}助理a={a}不存在于character_data中",
                [a],
            )
        )
        return failures
    ca = cd[a]
    problems = []
    if not roster.has(a):
        problems.append("不在npc_id_got在编名册中")
    if visitor.is_visitor(a) or flags.get(ca.cid, "vistor") == 1:
        problems.append(
            f"当前是访客(在访客名册={visitor.is_visitor(a)}, vistor={flags.get(ca.cid, "vistor")})"
        )
    if a == work.warden():
        problems.append("同时是监狱长(work.warden)")
    if prison.is_prisoner(a) or flags.get(ca.cid, "imprisonment"):
        problems.append("同时是囚犯(在base.prisoners中或imprisonment为True)")
    if flags.get(ca.cid, "field_commission"):
        problems.append(
            f"field_commission={flags.get(ca.cid, "field_commission")}非零(外勤中)"
        )
    if flags.get(ca.cid, "escaping"):
        problems.append("sp_flag.escaping为True")
    if flags.get(ca.cid, "be_bagged"):
        problems.append("sp_flag.be_bagged为True")
    if problems:
        failures.append(
            make_failure(
                "ROSTER-32",
                "助理身份互斥",
                f"{warn}助理a={a} name={ca.name!r} {'; '.join(problems)}",
                [a],
            )
        )
    return failures


@register_check("ROSTER-33", "装袋双方记录双向一致")
def check_bagging_pair_consistency() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能: 玩家的sp_flag.bagging_chara_id与被搬运者的sp_flag.be_bagged必须互指；被装袋者必须离线，
    且不能同时是囚犯、访客、外勤或逃跑者。这对flag分居玩家与目标两个对象，是本域内最容易单边脱钩的一对
    """
    cache = cache_control.cache
    cd = identity.table()
    warn = _sev(cache, False)
    failures: list[CheckFailure] = []
    player = cd.get(0)
    if player is None:
        return failures
    b = flags.get(player.cid, "bagging_chara_id")
    if type(b) is not int:
        failures.append(
            make_failure(
                "ROSTER-33",
                "装袋双方记录双向一致",
                f"{warn}cd[0].sp_flag.bagging_chara_id类型异常: {b!r}",
                [],
            )
        )
        return failures
    bagged = {cid for cid in cd if cid != 0 and flags.get(cid, "be_bagged")}
    expected = {b} if b else set()
    for cid in bagged - expected:
        c = cd[cid]
        failures.append(
            make_failure(
                "ROSTER-33",
                "装袋双方记录双向一致",
                f"{warn}角色cid={cid} name={c.name!r} sp_flag.be_bagged=True，但玩家bagging_chara_id={b}未指向它",
                [cid],
            )
        )
    for cid in expected - bagged:
        maybe_c = cd.get(cid)
        failures.append(
            make_failure(
                "ROSTER-33",
                "装袋双方记录双向一致",
                (
                    f"{warn}玩家bagging_chara_id={b}指向cid={cid}，但该角色sp_flag.be_bagged不为True；"
                    f"name={getattr(maybe_c, 'name', '?')!r}"
                ),
                [cid],
            )
        )
    if b and b in cd:
        membership = _scene_membership(cache)
        c = cd[b]
        problems = []
        if roster.has(b):
            problems.append("仍在npc_id_got在编名册中")
        hit = membership.get(b, [])
        if hit:
            problems.append(f"仍残留在场景{hit}中")
        if activity.position(c.cid) != ["0", "0"]:
            problems.append(f"position={activity.position(c.cid)!r}未归零")
        if prison.is_prisoner(b) or flags.get(c.cid, "imprisonment"):
            problems.append("同时是囚犯(base.prisoners或imprisonment)")
        if visitor.is_visitor(b) or flags.get(c.cid, "vistor") == 1:
            problems.append("同时是访客(访客名册或vistor==1)")
        if flags.get(c.cid, "field_commission"):
            problems.append(
                f"field_commission={flags.get(c.cid, "field_commission")}非零"
            )
        if flags.get(c.cid, "escaping"):
            problems.append("sp_flag.escaping为True")
        if problems:
            failures.append(
                make_failure(
                    "ROSTER-33",
                    "装袋双方记录双向一致",
                    f"{warn}被装袋者b={b} name={c.name!r} {'; '.join(problems)}；玩家position={activity.position(0)}",
                    [b],
                )
            )
    return failures
