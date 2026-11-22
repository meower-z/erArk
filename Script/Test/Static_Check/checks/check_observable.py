# -*- coding: UTF-8 -*-
"""
静态检查系统 - 可观察矛盾检查

本模块实现 OBS 组的14条不变量检查（OBS-01 ~ OBS-09、OBS-12、OBS-13、OBS-16 ~ OBS-18），覆盖玩家可直接从指令面板、
角色标签、身体面板、位置面板与助理设置中观察到的状态矛盾。

全流水线实现总则：
1. 禁止调用 Script/Design/handle_premise 中的正式前提函数。这些函数可能升级旧档结构、补写指令过滤键，
   或通过 setdefault 修改存档。本模块直读 cache 的字段，经领域模块的读函数读 GameState 里的数据。
   地图路径与睡眠等级用已确认无副作用的派生函数算出。
2. 每回合执行，角色检查保持单层 O(N) 遍历；配置表和场景路径等共享查表放在循环外。
3. 每条检查的文档字符串都说明健康存档为何恒不命中；无法给出该理由的候选不进入本模块。
4. 消息的 ``[warning] `` 前缀表示已确认会命中当前版本真实缺陷的探测器，不是容许误报的出口。
5. 沿用全局守卫：``["0", "0"]`` 是真实场景；路径由 map_handle 助手拼接；离线只认来源标记；
   交互对象（activity.target）不作为 H 绑定断言；时停与 debug 按每条规格单独守卫。
6. 全部读取采用 getattr/dict.get 与形状判断；结构异常交给既有形状检查，不重复报告。
7. 一个检查先收集全部失配，再合并为一条 failure，避免检查级日志去重吞掉同次快照中的其余证据。
"""

from __future__ import annotations

from collections.abc import Iterator

from Script.Core import cache_control, constant, num
from Script.Design import attr_calculation, map_handle
from Script.Modules.domains import (
    abilities,
    activity,
    flags,
    h_state,
    history,
    modes,
)
from Script.Modules.domains import needs, player_ability, prison, roster, work
from ..check_registry import CheckFailure, make_failure, register_check

from typing import TYPE_CHECKING
from Script.Modules.domains import relations
from Script.Modules.domains import identity

if TYPE_CHECKING:
    from types import ModuleType
    from Script.Core import game_type

game_config: ModuleType | None
try:
    from Script.Config import game_config as _game_config_module

    game_config = _game_config_module
except Exception:  # pragma: no cover - 独立运行环境下配置包可能尚未载入
    game_config = None


# 场景路径必须使用游戏自身助手拼接，不能写死平台分隔符。
_P = map_handle.get_map_system_path_str_for_list
_ASSISTANT_SERVICE_KEYS = {2, 3, 4, 5, 6, 7, 8, 10}
_BATH_BEHAVIOR_TAGS = {
    constant.Behavior.SWIMMING: "Swimming_Pool",
    constant.Behavior.TAKE_SHOWER: "Bathroom",
    constant.Behavior.SOAK_FEET: "Foot_Bath",
    constant.Behavior.STEAM_SAUNA: "Sauna",
    constant.Behavior.HYDROTHERAPY_TREATMENT: "Spa_Room",
    constant.Behavior.ONSEN_BATH: "Onsen",
}


def _character_data(cache: game_type.Cache) -> identity.Table | None:
    """
    参数: cache 全局缓存对象
    返回值: identity.Table | None 角色身份表只读视图，cache 为 None 时返回 None
    功能: 统一读取角色身份表（identity.table()），在 cache 未初始化时返回 None。
    """
    return identity.table() if cache is not None else None


def _pl(cache: game_type.Cache) -> identity.Identity | None:
    """
    参数: cache 全局缓存对象
    返回值: 玩家角色对象；角色字典未初始化或缺少 cid=0 时返回 None
    功能: 统一取得玩家对象。
    """
    data = _character_data(cache)
    return data.get(0) if data is not None else None


def _iter_npcs(cache: game_type.Cache) -> Iterator[tuple[int, object]]:
    """
    参数: cache 全局缓存对象
    返回值: Iterator[Tuple[int, object]]，依次产出已获得且存在的非玩家角色
    功能: 以 npc_id_got 为域做单层遍历，并保护角色字典中的悬空 id。
    """
    data = _character_data(cache)
    got = roster.active() if cache is not None else None
    if data is None or not got:
        return
    for cid in got:
        if cid != 0 and cid in data:
            yield cid, data[cid]


def _iter_live(cache: game_type.Cache) -> Iterator[tuple[int, object]]:
    """
    参数: cache 全局缓存对象
    返回值: Iterator[Tuple[int, object]]，依次产出玩家和已获得 NPC
    功能: 为检查域是 npc_id_got∪{0} 的条目提供统一遍历。
    """
    pl = _pl(cache)
    if pl is not None:
        yield 0, pl
    yield from _iter_npcs(cache)


def _name(chara: object) -> str:
    """
    参数: chara 角色对象
    返回值: str 角色名，缺失时返回问号
    功能: 防御式生成失败消息中的角色名。
    """
    return str(getattr(chara, "name", "?"))


def _hs(chara: object) -> game_type.BODY_H_STATE | None:
    """角色 h_state 视图，缺少有效 cid 时返回 None"""
    cid = getattr(chara, "cid", None)
    return h_state.view(cid) if isinstance(cid, int) else None


def _fully_out_of_h(chara: object) -> bool:
    """
    参数: chara 角色对象
    返回值: bool，角色完全脱离普通H、无意识H、隐奸与露出时为 True
    功能: 复用 HGROUP-31 的完全脱离 H 四字段口径。
    """
    cid = getattr(chara, "cid", None)
    return isinstance(cid, int) and not (
        flags.get(cid, "is_h")
        or flags.get(cid, "unconscious_h") != 0
        or flags.get(cid, "hidden_sex_mode") != 0
        or flags.get(cid, "exhibitionism_sex_mode") != 0
    )


def _scene(cache: game_type.Cache, position: object) -> game_type.Scene | None:
    """
    参数: cache 全局缓存对象；position 期望为字符串列表
    返回值: 对应场景对象；路径或场景结构异常时返回 None
    功能: 使用游戏路径助手防御式解析角色当前位置。
    """
    scene_data = (
        getattr(cache, "scene_data", None) if cache is not None else None
    )
    if (
        not isinstance(scene_data, dict)
        or not isinstance(position, list)
        or not position
        or not all(isinstance(x, str) for x in position)
    ):
        return None
    return scene_data.get(_P(position))


def _sleep_level(cid: int) -> int | None:
    """
    参数: cid 角色id
    返回值: Optional[int] 由熟睡值（needs.of(cid)["sleep"]）算出的睡眠等级，配置未载入或算不出等级时为 None
    功能: 用 attr_calculation.get_sleep_level 算等级。独立脚本里没有载入配置时返回 None，调用方跳过检查。
    """
    if game_config is None or not getattr(
        game_config, "config_sleep_level", None
    ):
        return None
    value = needs.of(cid)["sleep"]
    try:
        return attr_calculation.get_sleep_level(num.exact(value))[0]
    except Exception:
        return None


def _positive_number(value: object) -> bool:
    """
    参数: value 任意字段值
    返回值: bool，value 是非 bool 数值且大于零时为 True
    功能: 为旧档字段做安全的正数判断，值域或类型异常时跳过而不让检查自身抛错。
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
    )


def _offline_context(chara: object) -> str:
    """
    参数: chara 角色对象
    返回值: str 离线来源标记摘要
    功能: 仅把装袋、外勤、外交访问、逃跑等来源标记写入消息上下文，不把坐标误当离线哨兵。
    """
    cid = getattr(chara, "cid", None)
    if not isinstance(cid, int):
        return (
            "be_bagged=None, field_commission=None, in_diplomatic_visit=None, "
            "escaping=None, vistor=None"
        )
    return (
        f"be_bagged={flags.get(cid, 'be_bagged')}, field_commission={flags.get(cid, 'field_commission')}, "
        f"in_diplomatic_visit={flags.get(cid, 'in_diplomatic_visit')}, escaping={flags.get(cid, 'escaping')}, "
        f"vistor={flags.get(cid, 'vistor')}"
    )


@register_check("OBS-01", "玩家不在H时同场不得有在H的NPC")
def check_observable_01() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，没有同场 H 残留时为空
    功能: 玩家完全退出普通H且不在隐奸/群交/时停时，同场 NPC 的 is_h 应已由结束链清零；
    健康存档的结束链对象一致，因此恒不命中。
    """
    cache = cache_control.cache
    pl = _pl(cache)
    if (
        pl is None
        or getattr(cache, "debug_mode", False)
        or modes.time_stop()
        or modes.group_sex()
    ):
        return []
    if flags.get(0, "is_h") or flags.get(0, "hidden_sex_mode") != 0:
        return []
    bad = []
    for cid, _chara in _iter_npcs(cache):
        if activity.position(cid) == activity.position(pl.cid) and flags.get(
            cid, "is_h"
        ):
            bad.append(cid)
    if not bad:
        return []
    details = [
        (
            f"cid={cid}({_name(identity.of(cid))}) "
            f"target={activity.target(cid)}"
        )
        for cid in bad
    ]
    return [
        make_failure(
            "OBS-01",
            "玩家不在H时同场不得有在H的NPC",
            (
                f"[warning] 已知缺陷机制：效果404按执行时target重置双方，错对象收尾会让真伙伴同场残留is_h；"
                f"玩家已不在H但同场NPC仍在H：{details}；玩家target={activity.target(pl.cid)} "
                f"position={activity.position(pl.cid)}"
            ),
            [0] + bad,
        )
    ]


@register_check("OBS-02", "玩家有性交体位时场内必须真有人被对应插入")
def check_observable_02() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，玩家体位与场内插入状态一致时为空
    功能: 校验玩家独占体位字段与场内 NPC 插入位置相互支撑；健康存档的体位切换与拔出链同步维护两侧字段，因此恒不命中。
    """
    cache = cache_control.cache
    pl = _pl(cache)
    if pl is None or getattr(cache, "debug_mode", False) or modes.time_stop():
        return []
    hs = _hs(pl)
    if hs is None:
        return []
    sex_position = getattr(hs, "current_sex_position", None)
    womb_position = getattr(hs, "current_womb_sex_position", None)
    insertions = []
    h_in_scene = []
    for cid, chara in _iter_npcs(cache):
        if activity.position(cid) != activity.position(pl.cid):
            continue
        pos = getattr(_hs(chara), "insert_position", None)
        if isinstance(pos, int) and not isinstance(pos, bool):
            insertions.append((cid, pos))
        if flags.get(cid, "is_h"):
            h_in_scene.append(cid)
    bad = []
    if (
        isinstance(sex_position, int)
        and not isinstance(sex_position, bool)
        and sex_position != -1
        and not any(pos in {6, 7, 8, 9} for _, pos in insertions)
    ):
        bad.append(
            f"current_sex_position={sex_position}但场内无人insert_position∈{{6,7,8,9}}"
        )
    if (
        isinstance(womb_position, int)
        and not isinstance(womb_position, bool)
        and womb_position != 0
        and not any(pos == 7 for _, pos in insertions)
    ):
        bad.append(
            f"current_womb_sex_position={womb_position}但场内无人insert_position=7"
        )
    if _fully_out_of_h(pl) and (
        (
            isinstance(sex_position, int)
            and not isinstance(sex_position, bool)
            and sex_position != -1
        )
        or (
            isinstance(womb_position, int)
            and not isinstance(womb_position, bool)
            and womb_position != 0
        )
    ):
        bad.append("玩家已完全脱离H但体位字段仍非空")
    if not bad:
        return []
    return [
        make_failure(
            "OBS-02",
            "玩家有性交体位时场内必须真有人被对应插入",
            f"{'; '.join(bad)}；场内插入={insertions}，场内is_h角色={h_in_scene}",
            [0],
        )
    ]


@register_check("OBS-03", "完全脱离H的角色不得残留口球")
def check_observable_03() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，没有非H口球残留时为空
    功能: 检查完全脱离 H 的角色 body_item[14] 未仍处于装备状态；健康存档应在 H 重置时移除 H 装备，所以恒不命中。
    """
    cache = cache_control.cache
    if cache is None or getattr(cache, "debug_mode", False):
        return []
    bad = []
    for cid, chara in _iter_live(cache):
        if not _fully_out_of_h(chara):
            continue
        items = getattr(_hs(chara), "body_item", None)
        item = items.get(14) if isinstance(items, dict) else None
        if isinstance(item, (list, tuple)) and len(item) == 3 and bool(item[1]):
            bad.append(cid)
    if not bad:
        return []
    return [
        make_failure(
            "OBS-03",
            "完全脱离H的角色不得残留口球",
            f"[warning] 已知配表缺陷机制：口球(14)被标为type=0，H重置会原样保留；以下角色出现非H口球残留：{bad}",
            bad,
        )
    ]


@register_check("OBS-04", "透视或信息素开关开启时玩家必须持有对应素质")
def check_observable_04() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，技艺开关均有基础素质支撑时为空
    功能: 校验透视/信息素开关与其关闭指令所需基础素质一致；健康存档只能经持有素质的开启指令置位，所以恒不命中。
    """
    cache = cache_control.cache
    pl = _pl(cache)
    if pl is None or getattr(cache, "debug_mode", False):
        return []
    talent = abilities.talent(pl.cid)
    bad = []
    if player_ability.get(0, "visual") and not talent.get(307, 0):
        bad.append("透视开关visual=True但基础透视素质307缺失，关闭指令不可用")
    if player_ability.get(0, "hormone") and not talent.get(304, 0):
        bad.append(
            "信息素开关hormone=True但基础信息素素质304缺失，关闭指令不可用"
        )
    if not bad:
        return []
    return [
        make_failure(
            "OBS-04",
            "透视或信息素开关开启时玩家必须持有对应素质",
            f"[warning] 已知缺陷机制：旧档迁移或mod可让开关保留而素质消失；{'; '.join(bad)}",
            [0],
        )
    ]


@register_check("OBS-05", "玩家的交互对象必须在当前场景名册里")
def check_observable_05() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，非装袋交互对象在玩家场景名册中时为空
    功能: 校验指令面板轴心 target 与场景名册一致；
    交互对象是玩家自己或玩家正装袋搬运的角色时不报，debug 模式下也不报。
    """
    cache = cache_control.cache
    pl = _pl(cache)
    data = _character_data(cache)
    if pl is None or data is None or getattr(cache, "debug_mode", False):
        return []
    target_id = activity.target(pl.cid)
    if (
        not isinstance(target_id, int)
        or isinstance(target_id, bool)
        or target_id == 0
        or target_id not in data
        or target_id == flags.get(0, "bagging_chara_id")
    ):
        return []
    scene = _scene(cache, activity.position(pl.cid))
    roster = (
        getattr(scene, "character_list", None) if scene is not None else None
    )
    if not isinstance(roster, (list, set, tuple)) or target_id in roster:
        return []
    target = data[target_id]
    pre = history.recent()
    last_pre = pre[-1] if isinstance(pre, list) and pre else None
    return [
        make_failure(
            "OBS-05",
            "玩家的交互对象必须在当前场景名册里",
            (
                f"[warning] target cid={target_id}({_name(target)})不在玩"
                f"家当前场景名册，pl.position={activity.position(pl.cid)}，"
                f"target.position={activity.position(target.cid)}，离线来源={_offline_context(target)}，"
                f"上一玩家指令={last_pre}"
            ),
            [0, target_id],
        )
    ]


@register_check("OBS-06", "同一角色不得同时处于隐奸模式与露出模式")
def check_observable_06() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，隐奸与露出模式互斥时为空
    功能: 检查同一角色的两种 H 分流模式不会同时大于零；健康存档的入口与结束链应保持模式互斥，因此恒不命中。
    """
    cache = cache_control.cache
    if cache is None or getattr(cache, "debug_mode", False):
        return []
    bad = []
    details = []
    for cid, chara in _iter_live(cache):
        hidden = flags.get(cid, "hidden_sex_mode")
        exhibitionism = flags.get(cid, "exhibitionism_sex_mode")
        if (
            isinstance(hidden, (int, float))
            and isinstance(exhibitionism, (int, float))
            and hidden > 0
            and exhibitionism > 0
        ):
            bad.append(cid)
            details.append(
                f"cid={cid}({_name(chara)}) hidden={hidden} "
                f"exhibitionism={exhibitionism}({'玩家侧已知可达' if cid == 0 else 'NPC侧模式泄漏'})"
            )
    if not bad:
        return []
    return [
        make_failure(
            "OBS-06",
            "同一角色不得同时处于隐奸模式与露出模式",
            f"[warning] 已知缺陷机制：隐奸1/2清玩家is_h后可经NOT_H入口叠加露出模式；{details}",
            bad,
        )
    ]


@register_check("OBS-07", "性爱助手结算必须满足监狱长约束")
def check_observable_07() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，性爱助手设置、监狱长与角色标记一致时为空
    功能: 校验群交调教现场有非零监狱长，且 sex_assist 只落在该监狱长身上；
    健康存档的助手结算应只写当前监狱长，因此恒不命中。
    """
    cache = cache_control.cache
    if (
        cache is None
        or getattr(cache, "debug_mode", False)
        or modes.time_stop()
    ):
        return []
    settings = prison.settings()
    warden = work.warden()
    bad_ids = []
    bad = []
    if (
        _positive_number(settings.get(12, 0))
        and warden == 0
        and modes.group_sex()
    ):
        bad.append(
            "群交现场已开启调教助手设置但没有监狱长(work.warden()=0)，结算会把玩家当助手"
        )
        bad_ids.append(0)
    data = _character_data(cache)
    for cid, chara in data.items() if data is not None else ():
        if getattr(_hs(chara), "sex_assist", False) is True and (
            warden == 0 or cid != warden
        ):
            bad.append(
                f"{'玩家' if cid == 0 else '角色'}cid={cid}({_name(chara)}) sex_assist=True但当前监狱长={warden}"
            )
            bad_ids.append(cid)
    if not bad:
        return []
    return [
        make_failure(
            "OBS-07",
            "性爱助手结算必须满足监狱长约束",
            f"[warning] 已知缺陷机制：助手结算直接把warden行为覆盖为助手行为，空监狱长会落到cid=0；{'; '.join(bad)}",
            sorted(set(bad_ids)),
        )
    ]


@register_check("OBS-08", "醉酒型无意识H不得在醉酒值耗尽后残留")
def check_observable_08() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，醉酒型无意识 H（unconscious_h=2）的角色的醉酒值都大于 0 时为空
    功能: 报出 unconscious_h=2 而醉酒值（needs.of(cid)["drunk"]）<=0 的角色。debug 模式与时停中不检查。
    """
    cache = cache_control.cache
    if (
        cache is None
        or getattr(cache, "debug_mode", False)
        or modes.time_stop()
    ):
        return []
    bad = []
    details = []
    for cid, chara in _iter_live(cache):
        drunk_point = needs.of(cid)["drunk"]
        if flags.get(cid, "unconscious_h") == 2 and drunk_point <= 0:
            bad.append(cid)
            details.append(
                f"cid={cid}({_name(chara)}) drunk_point={drunk_point}"
            )
    if not bad:
        return []
    return [
        make_failure(
            "OBS-08",
            "醉酒型无意识H不得在醉酒值耗尽后残留",
            f"[warning] 已知缺陷机制：当前代码没有以酒醒为触发的unconscious_h清零路径；{details}",
            bad,
        )
    ]


@register_check("OBS-09", "非群交下至多一名NPC处于阴茎插入中")
def check_observable_09() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，非群交快照中至多一名 NPC 有插入位置时为空
    功能: 校验玩家单一阴茎不会在普通 H 中同时记录插入多名 NPC；健康存档换位与拔出链会清旧对象，所以恒不命中。
    """
    cache = cache_control.cache
    if (
        cache is None
        or getattr(cache, "debug_mode", False)
        or modes.time_stop()
        or modes.group_sex()
    ):
        return []
    bad = []
    for cid, chara in _iter_npcs(cache):
        pos = getattr(_hs(chara), "insert_position", -1)
        if isinstance(pos, int) and not isinstance(pos, bool) and pos != -1:
            bad.append(cid)
    if len(bad) < 2:
        return []
    details = [
        (
            f"cid={cid}({_name(identity.of(cid))}) "
            f"insert_position={getattr(_hs(identity.of(cid)), 'insert_position', None)}"
        )
        for cid in bad
    ]
    return [
        make_failure(
            "OBS-09",
            "非群交下至多一名NPC处于阴茎插入中",
            f"[warning] 已知低频残留机制：普通H换位仅有少数复位点，旧对象可能保留insert_position；{details}",
            bad,
        )
    ]


# OBS-11（已删除，2026-08-28）：曾断言"异地智能跟随者必须正在赶路或门外等待"（is_follow==1 且异地却处于
# SHARE_BLANKLY 即报）。该单帧断言结构性不成立：(1) 行为结束重置
# （character_behavior.py:327-350，time_judge==2）在采样点（指令面板绘制后）必然产生临时 SHARE_BLANKLY；
# (2) 合法"门外等待"WAIT 结束同样重置为同一形态；(3) is_follow==1 本就由 AI 目标表驱动而非每回合直接派发
# （is_follow==2 才是），断言"恒驱动 MOVE/WAIT"对 1 结构性错。真正的滞留（跟随目标丢失、寻路卡死）几乎必然
# 表现为角色卡死不动或 is_follow 被自动归 0，以"持续 SHARE_BLANKLY 且 is_follow 仍为 1"的形态存在的真故障
# 类别近乎为空；要做成能立住的持久化版本需要跨帧状态与经验阈值，违反本模块单帧只读设计前提。


@register_check("OBS-12", "助理跟随服务开启时恢复正常的空闲助理必须在跟随")
def check_observable_12() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，已恢复正常的空闲助理与跟随服务设置一致时为空
    功能: 检查服务2开启后，非疲劳、非困倦、无生理意图、非H的空闲在线助理不会丢失跟随；
    健康存档的服务承诺应维持 is_follow=1，因此恒不命中。
    """
    cache = cache_control.cache
    pl = _pl(cache)
    data = _character_data(cache)
    if (
        pl is None
        or data is None
        or getattr(cache, "debug_mode", False)
        or modes.time_stop()
    ):
        return []
    assistant_id = relations.assistant_character_id(0)
    got = roster.active()
    if (
        not isinstance(assistant_id, int)
        or isinstance(assistant_id, bool)
        or assistant_id not in data
        or assistant_id not in got
        or assistant_id == 0
    ):
        return []
    assistant = data[assistant_id]
    services = relations.assistant_services(assistant_id)
    if not services.get(2, 0):
        return []
    follow = flags.get(assistant_id, "is_follow")
    if (
        follow in {2, 3, 4}
        or follow != 0
        or activity.behavior(assistant_id).behavior_id
        != constant.Behavior.SHARE_BLANKLY
    ):
        return []
    sleep_level = _sleep_level(assistant_id)
    if (
        sleep_level is None
        or flags.get(assistant_id, "tired")
        or sleep_level >= 2
    ):
        return []
    physiological = (
        flags.get(assistant_id, "rest")
        or flags.get(assistant_id, "sleep")
        or flags.get(assistant_id, "pee")
        or _positive_number(flags.get(assistant_id, "eat_food"))
        or _positive_number(flags.get(assistant_id, "help_buy_food"))
        or _positive_number(flags.get(assistant_id, "help_make_food"))
        or _positive_number(flags.get(assistant_id, "shower"))
        or flags.get(assistant_id, "milk")
        or _positive_number(flags.get(assistant_id, "masturebate"))
        or flags.get(assistant_id, "npc_masturebate_for_player")
    )
    if (
        physiological
        or flags.get(assistant_id, "is_h")
        or flags.get(assistant_id, "unconscious_h") != 0
    ):
        return []
    if (
        flags.get(assistant_id, "be_bagged")
        or flags.get(assistant_id, "field_commission")
        or flags.get(assistant_id, "escaping")
        or flags.get(assistant_id, "in_diplomatic_visit")
    ):
        return []
    return [
        make_failure(
            "OBS-12",
            "助理跟随服务开启时恢复正常的空闲助理必须在跟随",
            (
                f"[warning] 已知缺陷机制：疲劳/困倦会清is_follow，而白天恢复后没有重挂路径，只有跨日睡眠恢复；"
                f"助理cid={assistant_id}({_name(assistant)}) services[2]={services.get(2)!r} is_follow={follow} "
                f"sleep_level={sleep_level}"
            ),
            [0, assistant_id],
        )
    ]


@register_check("OBS-13", "非当前助理的角色助理服务位必须全为0")
def check_observable_13() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，只有当前助理持有已实装服务位时为空
    功能: 全量检查非玩家、非当前助理角色的已实装服务位均归零；健康存档在替换或取消助理时会清旧服务，因此恒不命中。
    """
    cache = cache_control.cache
    pl = _pl(cache)
    data = _character_data(cache)
    if pl is None or data is None:
        return []
    assistant_id = relations.assistant_character_id(0)
    if not isinstance(assistant_id, int) or isinstance(assistant_id, bool):
        return []
    bad = []
    details = []
    for cid, chara in data.items():
        if cid == 0 or cid == assistant_id:
            continue
        services = relations.assistant_services(cid)
        active = {
            key: services.get(key)
            for key in _ASSISTANT_SERVICE_KEYS
            if services.get(key)
        }
        if active:
            bad.append(cid)
            details.append(
                f"cid={cid}({_name(chara)}) active_services={active}"
            )
    if not bad:
        return []
    return [
        make_failure(
            "OBS-13",
            "非当前助理的角色助理服务位必须全为0",
            f"当前助理cid={assistant_id}，但以下非助理角色仍持有会被AI消费的服务位：{details}",
            bad,
        )
    ]


@register_check("OBS-16", "洗浴和游泳类行为必须发生在对应设施")
def check_observable_16() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，六类行为均位于对应设施时为空
    功能: 校验 NPC 当前洗浴/游泳行为与场景标签匹配；
    健康存档只会在带目标设施前提的状态机中启动行为，移动又会替换行为，因此恒不命中。
    """
    cache = cache_control.cache
    if (
        cache is None
        or getattr(cache, "debug_mode", False)
        or modes.time_stop()
    ):
        return []
    bad = []
    details = []
    for cid, chara in _iter_npcs(cache):
        behavior_id = activity.behavior(cid).behavior_id
        expected = (
            _BATH_BEHAVIOR_TAGS.get(behavior_id)
            if behavior_id is not None
            else None
        )
        if expected is None:
            continue
        scene = _scene(cache, activity.position(cid))
        tags = getattr(scene, "scene_tag", None) if scene is not None else None
        if not isinstance(tags, (list, set, tuple)):
            continue
        if expected not in tags:
            bad.append(cid)
            details.append(
                f"cid={cid}({_name(chara)}) behavior={behavior_id} position={activity.position(cid)} "
                f"scene_tags={tags} 期望={expected}"
            )
    if not bad:
        return []
    return [
        make_failure(
            "OBS-16",
            "洗浴和游泳类行为必须发生在对应设施",
            f"行为与设施标签矛盾：{details}",
            bad,
        )
    ]


@register_check("OBS-17", "移动行为中的NPC必须带非空最终目的地")
def check_observable_17() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，所有移动中的 NPC 都带非空 move_final_target 时为空
    功能: 检查位置面板可见的移动行为拥有最终目的地；
    健康存档的寻路提交会同步填写该字段，抵达或取消时会退出移动行为，因此恒不命中。
    """
    cache = cache_control.cache
    if (
        cache is None
        or getattr(cache, "debug_mode", False)
        or modes.time_stop()
    ):
        return []
    bad = []
    details = []
    for cid, chara in _iter_npcs(cache):
        behavior = activity.behavior(cid)
        if (
            getattr(behavior, "behavior_id", None) == constant.Behavior.MOVE
            and getattr(behavior, "move_final_target", None) == []
        ):
            bad.append(cid)
            details.append(
                f"cid={cid}({_name(chara)}) position={activity.position(cid)} "
                f"move_src={getattr(behavior, 'move_src', None)} "
                f"move_target={getattr(behavior, 'move_target', None)} duration={getattr(behavior, 'duration', None)} "
                f"start_time={getattr(behavior, 'start_time', None)} "
                f"is_follow={flags.get(cid, 'is_follow')} is_h={flags.get(cid, 'is_h')}"
            )
    if not bad:
        return []
    return [
        make_failure(
            "OBS-17",
            "移动行为中的NPC必须带非空最终目的地",
            f"[warning] 已知缺陷机制：抵达清空或cancel_movement_plan可留下原作者标注BUG的移动空目的地尾态；{details}",
            bad,
        )
    ]


@register_check("OBS-18", "绳缚值必须是合法配置键")
def check_observable_18() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]，所有非零 bondage 都能索引配置表时为空
    功能: 防止 realtime_settle 以非法绳缚键直接索引 config_bondage 崩溃；
    健康存档只由绳缚面板写配置表中的合法键，因此恒不命中。
    """
    cache = cache_control.cache
    data = _character_data(cache)
    bondage_config = (
        getattr(game_config, "config_bondage", None)
        if game_config is not None
        else None
    )
    if data is None or not bondage_config:
        return []
    bad = []
    details = []
    for cid, chara in data.items():
        bondage = getattr(_hs(chara), "bondage", 0)
        if bondage == 0:
            continue
        try:
            invalid = bondage not in bondage_config
        except TypeError:
            # 不可哈希的非零bondage本身就是结算侧config_bondage[bondage]会抛TypeError崩溃的情形，必须记为非法。
            invalid = True
        if invalid:
            bad.append(cid)
            details.append(f"cid={cid}({_name(chara)}) bondage={bondage!r}")
    if not bad:
        return []
    return [
        make_failure(
            "OBS-18",
            "绳缚值必须是合法配置键",
            f"非法绳缚值会在realtime_settle直接索引config_bondage并崩溃：{details}",
            bad,
        )
    ]
