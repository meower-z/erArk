# -*- coding: UTF-8 -*-
"""
静态检查系统 - 意识域（时停/催眠/无意识/睡眠）领域检查
本模块实现 MIND 组的28条不变量检查（MIND-01 ~ MIND-25、MIND-28 ~ MIND-30），覆盖时间停止、催眠深度/类型/子项、
角色扮演列表、睡眠/装睡、熟睡值等意识状态相关字段的一致性约束。
来源: final_invariants_mind.md（M-xx + MS-xx 不变式清单）。

约定与踩坑说明（写在此处，避免散落在各检查函数注释里重复）：
1. `mode.debug` 开启时debug面板可越过前提直接改素质、催眠深度/子项、角色扮演列表、熟睡值等，
   凡这些字段参与、且检查内容为"值来自合法结算路径"的不变式，都在检查体前加debug豁免；
   纯粹的存档结构/schema式检查（如MIND-22/28/29）不受debug模式影响，不加豁免。
2. `roster.active()` 不保证是 `identity.table()` 的子集，一律用 `_iter_npcs()` 做存在性保护。
3. 场景key统一用 `map_handle.get_map_system_path_str_for_list`（`os.sep.join`），不是 "|".join。
4. `game_config.config_roleplay` 在独立脚本环境下可能未加载，相关检查（MIND-16）遇缺表时降级为跳过。
5. 全部字段访问一律使用 getattr/dict.get 加默认值防御，绝不能因为老存档缺字段或类型不符而让检查器自身抛异常。
"""

from __future__ import annotations

from fractions import Fraction
from typing import TypeGuard

from Script.Core import constant, num
from Script.Design import map_handle
from Script.Modules.domains import abilities, achievement, action_info, activity
from Script.Modules.domains import flags, h_state as h_state_domain
from Script.Modules.domains import hypnosis as hypnosis_domain, modes, needs
from Script.Modules.domains import player_ability, roster, scene_state
from ..check_registry import CheckFailure, register_check, make_failure

from typing import TYPE_CHECKING
from Script.Modules.domains import identity

if TYPE_CHECKING:
    from collections.abc import Iterator


def _name(chara: object) -> str:
    """
    参数: chara 角色对象
    返回值: str 角色名，取不到时返回"?"
    功能: 防御式获取角色名用于拼接失败信息
    """
    return str(getattr(chara, "name", "?"))


def _pl() -> identity.Identity | None:
    """
    参数: 无
    返回值: 玩家角色对象，cache未初始化或0号角色不存在时返回None
    功能: 统一获取玩家角色对象
    """
    return identity.get(0)


def _iter_npcs() -> Iterator[tuple[int, identity.Identity]]:
    """
    参数: 无
    返回值: 迭代器，依次产出(角色id, identity.Identity)
    功能: 遍历在编名单（roster.active()）中存在于身份表（identity.characters）的非玩家角色，
        防止在编名单含悬空id时报错
    """
    for cid in roster.active():
        if cid and identity.exists(cid):
            yield cid, identity.of(cid)


def _iter_all() -> Iterator[tuple[int, identity.Identity]]:
    """
    参数: 无
    返回值: 迭代器，依次产出(角色id, identity.Identity)
    功能: 遍历身份表（identity.table()）中的全部角色（含未在编角色）
    """
    yield from identity.table().items()


def _iter_pl_and_npcs() -> Iterator[tuple[int, identity.Identity]]:
    """
    参数: 无
    返回值: 迭代器，依次产出(角色id, 角色对象)，玩家(若存在)排在最前
    功能: 供"玩家 + 已登场干员"这一常见迭代范围复用
    """
    pl = _pl()
    if pl is not None:
        yield 0, pl
    yield from _iter_npcs()


def _talent_get(chara: identity.Identity, talent_id: int) -> int:
    """
    参数:
        chara: 角色对象
        talent_id (int): 素质id
    返回值:
        int: 素质取值，结构异常或缺键时返回0
    功能:
        防御式读取素质值，避免素质表缺键或结构异常让检查器自身抛异常
    """
    value = abilities.talent(chara.cid).get(talent_id, 0)
    return (
        value if isinstance(value, int) and not isinstance(value, bool) else 0
    )


def _u(chara: object) -> int:
    """
    参数: chara 角色对象
    返回值: int sp_flag.unconscious_h取值，结构缺失时返回-1（不落在任何合法值域内，交由调用方处理）
    功能: 防御式读取无意识H状态
    """
    cid = getattr(chara, "cid", None)
    return flags.get(cid, "unconscious_h") if isinstance(cid, int) else -1


def _behavior_id(chara: identity.Identity) -> str:
    """
    参数: chara 角色对象
    返回值: str 当前行为id，结构缺失时返回"?"
    功能: 防御式读取behavior.behavior_id
    """
    return getattr(activity.behavior(chara.cid), "behavior_id", "?")


def _scene_key(position: object) -> str | None:
    """
    参数: position 角色/玩家的position字段
    返回值: Optional[str] 场景key字符串；position不是"全字符串的list"形状时返回None
    功能: 用map_handle.get_map_system_path_str_for_list(os.sep.join)统一生成场景key，
        供 MIND-19/MIND-20 按场景查 constant.scene_data，坏形状交由调用方判失败而不是让本函数抛异常
    """
    if (
        not isinstance(position, list)
        or not position
        or not all(isinstance(x, str) for x in position)
    ):
        return None
    return map_handle.get_map_system_path_str_for_list(position)


def _num(x: object) -> TypeGuard[int | float | Fraction]:
    """
    参数: x 任意值
    返回值: bool x为非bool的int/float/Fraction时返回True
    功能: 判断x是否为可安全参与大小比较的数值，排除bool（bool是int子类，会静默通过数值比较）
    """
    return isinstance(x, (int, float, Fraction)) and not isinstance(x, bool)


# ============================== 一、时停 ==============================


@register_check("MIND-01", "时停开启时玩家处于时停无意识")
def check_time_stop_player_unconscious() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验TIME_STOP_ON把npc_id_got|{0}全部置为3之后，玩家侧没有任何"上线重置"之类的合法例外路径；
        时停开着而玩家unconscious_h不是3，意味着有非指令路径改写了玩家意识状态。
        玩家半没有NPC半(MIND-02)已知的"时停中上线"例外，两者严重级别不同，故分列为error
    """
    if not modes.time_stop():
        return []
    pl = _pl()
    if pl is None:
        return []
    u = _u(pl)
    if u == 3:
        return []
    return [
        make_failure(
            "MIND-01",
            "时停开启时玩家处于时停无意识",
            (
                f"时停开启(time_stop_mode=True)但玩家sp_flag.unconscious_h={u}(应为3)，"
                f"behavior_id={_behavior_id(pl)}，"
                f"累计时停时长={achievement.get('time_stop_duration')}"
            ),
            [0],
        )
    ]


@register_check("MIND-02", "时停开启时已登场干员处于时停无意识")
def check_time_stop_npc_unconscious() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验时停开启时全体已登场干员的unconscious_h均为3；漏掉的干员会被AI与指令前提当作可正常交互对象。
        已知合法例外——时停中角色上线：handle_chara_on_line整体重建sp_flag(unconscious_h归0)，
        8个调用点里nation_diplomacy_panel.py/navigation_panel.py/character_handle.py没有补写3，
        故聚合上报并标为warning，不逐角色刷屏
    """
    if not modes.time_stop():
        return []
    hits = []
    for cid, chara in _iter_npcs():
        u = _u(chara)
        if u != 3:
            hits.append(
                (
                    cid,
                    _name(chara),
                    u,
                    _behavior_id(chara),
                    activity.position(chara.cid),
                )
            )
    if not hits:
        return []
    sample = "; ".join(
        f"cid={h[0]}({h[1]}) unconscious_h={h[2]} behavior={h[3]} position={h[4]}"
        for h in hits[:5]
    )
    return [
        make_failure(
            "MIND-02",
            "时停开启时已登场干员处于时停无意识",
            f"[warning] 时停开启但共{len(hits)}名已登场干员unconscious_h≠3(已知合法例外:时停中上线未补写3，"
            f"见外交/导航面板调用点): {sample}{' ...' if len(hits) > 5 else ''}",
            [h[0] for h in hits],
        )
    ]


@register_check("MIND-03", "时停关闭后不得残留时停无意识")
def check_time_stop_off_no_residual() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验TIME_STOP_OFF在同一次结算里先关time_stop_mode再清零npc_id_got|{0}的unconscious_h；
        残留的3会让角色被判为"完全无意识"永不行动，且可被玩家无限使用时停奸
        （InstructConfig.csv:5214前提仅T_UNCONSCIOUS_FLAG_3）
    """
    if modes.time_stop():
        return []
    hits = []
    pl = _pl()
    if pl is not None and _u(pl) == 3:
        hits.append((0, _name(pl), _behavior_id(pl)))
    for cid, chara in _iter_npcs():
        if _u(chara) == 3:
            hits.append((cid, _name(chara), _behavior_id(chara)))
    if not hits:
        return []
    sample = "; ".join(f"cid={h[0]}({h[1]}) behavior={h[2]}" for h in hits[:5])
    return [
        make_failure(
            "MIND-03",
            "时停关闭后不得残留时停无意识",
            f"时停已关闭(time_stop_mode=False)但共{len(hits)}名角色unconscious_h仍为3(会被判为完全无意识永不行动): "
            f"{sample}{' ...' if len(hits) > 5 else ''}",
            [h[0] for h in hits],
        )
    ]


@register_check("MIND-04", "时停开启需要玩家持有窄域时停素质")
def check_time_stop_requires_talent_316() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验时停开启时玩家持有素质316(唯一正常入口PRIMARY_TIME_STOP读素质316)；
        时停开着而玩家没有316，说明状态来自读档迁移/mod/debug。debug面板可在时停开启后删掉316，
        属明确调试例外，故加debug豁免
    """
    if modes.debug() or not modes.time_stop():
        return []
    pl = _pl()
    if pl is None:
        return []
    if bool(_talent_get(pl, 316)):
        return []
    talents = {tid: _talent_get(pl, tid) for tid in (316, 317, 318)}
    return [
        make_failure(
            "MIND-04",
            "时停开启需要玩家持有窄域时停素质",
            f"[warning] 时停开启(time_stop_mode=True)但玩家未持有素质316: talent[316/317/318]={talents}",
            [0],
        )
    ]


@register_check("MIND-05", "时停搬运/自由活动字段在正常游戏中恒为零")
def check_time_stop_carry_free_fields_zero() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验pl_ability.carry_chara_id_in_time_stop与pl_ability.free_in_time_stop_chara_id恒为0。
        写carry_chara_id_in_time_stop的效果1243在Behavior_Effect.csv零引用；写free_in_time_stop_chara_id
        的效果1245虽挂在行为945上，但对应指令前提含TO_DO，非debug下handle_todo返回0——
        两字段在当前版本正常玩法中写不出非零值，非零只可能来自旧存档/debug/mod，加debug豁免。
        carry_chara_id_in_time_stop已废弃，现行搬运用action_info.carry_chara_id(见MIND-07)
    """
    if modes.debug():
        return []
    pl = _pl()
    if pl is None:
        return []
    carry = player_ability.get(0, "carry_chara_id_in_time_stop")
    free = player_ability.get(0, "free_in_time_stop_chara_id")
    if carry == 0 and free == 0:
        return []
    return [
        make_failure(
            "MIND-05",
            "时停搬运/自由活动字段在正常游戏中恒为零",
            f"[warning] 迁移/脏状态: carry_chara_id_in_time_stop={carry!r} free_in_time_stop_chara_id={free!r} "
            f"(均应恒为0，当前版本正常路径写不出非零值)，time_stop_mode={modes.time_stop()}，"
            f"action_info.carry_chara_id={action_info.get(pl.cid, "carry_chara_id")}",
            [0],
        )
    ]


@register_check("MIND-06", "时停开启时不应残留时停解放标记")
def check_time_stop_no_residual_release_flag() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验time_stop_mode开启时，全体存活的已登场干员h_state.time_stop_release均为False。
        该标记是关时停那一刻给全体NPC的一次性状态(效果527，与TIME_STOP_OFF挂在同一行为上)，
        活着的NPC在下一次行动前检查中会清回False；重开时停时还挂着它说明上一轮解放结算没走完。
        死亡角色在character_behavior.py直接return，标记会永久残留，必须豁免；
        效果527的循环显式跳过玩家(chara_id==0则continue)，故本式不覆盖玩家
    """
    if not modes.time_stop():
        return []
    hits = []
    for cid, chara in _iter_npcs():
        if activity.dead(chara.cid):
            continue
        h_state = h_state_domain.view(cid)
        if getattr(h_state, "time_stop_release", False):
            count = getattr(h_state, "time_stop_orgasm_count", {})
            nonzero = (
                {k: v for k, v in count.items() if v}
                if isinstance(count, dict)
                else count
            )
            hits.append((cid, _name(chara), nonzero))
    if not hits:
        return []
    sample = "; ".join(
        f"cid={h[0]}({h[1]}) time_stop_orgasm_count非零项={h[2]!r}"
        for h in hits[:5]
    )
    return [
        make_failure(
            "MIND-06",
            "时停开启时不应残留时停解放标记",
            f"[warning] 时停重新开启但共{len(hits)}名存活干员h_state.time_stop_release仍为True(上一轮解放结算未走完): "
            f"{sample}{' ...' if len(hits) > 5 else ''}",
            [h[0] for h in hits],
        )
    ]


@register_check("MIND-07", "被搬运的干员必须存在且与玩家同地点")
def check_carry_target_valid_and_colocated() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验pl.action_info.carry_chara_id指向的角色存在、未死亡且与玩家同地点。搬运期间玩家每次
        结算都会把被搬运者移动到玩家所在地点(handle_npc_ai_in_h.py，位于玩家分支内，回合边界上必定已执行)，
        地点不同步或cid无效即"凭空跟随"的幽灵角色。有意不检查"被搬运者仍处于异常6"——
        被搬运的睡眠干员自然睡醒后异常6即为"正常"，而搬运不会自动停止，纳入会误报
    """
    pl = _pl()
    if pl is None:
        return []
    cid = action_info.get(pl.cid, "carry_chara_id")
    if cid == 0:
        return []
    target = identity.get(cid)
    target_pos = activity.position(target.cid) if target is not None else "?"
    pl_pos = activity.position(pl.cid)
    if target is not None and not activity.dead(target.cid):
        if target_pos == pl_pos:
            return []
    if target is None:
        reason = "不存在"
    elif activity.dead(target.cid):
        reason = "已死亡"
    else:
        reason = f"position={target_pos}与玩家position={pl_pos}不同"
    return [
        make_failure(
            "MIND-07",
            "被搬运的干员必须存在且与玩家同地点",
            f"玩家action_info.carry_chara_id={cid}指向的角色{reason}，"
            f"该角色unconscious_h={_u(target) if target is not None else '?'}",
            [0, cid],
        )
    ]


# ============================== 二、催眠 ==============================


@register_check("MIND-08", "催眠深度值域")
def check_hypnosis_degree_bound() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验hypnosis.hypnosis_degree为非bool数值且落在[0, 200]内。正常增长路径是
        min(新值, hypnosis_degree_limit_calculation())，配置最高上限200(Hypnosis_Talent_Of_Pl.csv的
        max_hypnosis_degree)，越界值说明有旁路直接写入。有意不检查"不超过玩家当前能力上限"——
        新周目可按比例继承NPC催眠深度而玩家源石技艺可选择完全不继承，"NPC深度高于当前玩家上限"是合法快照。
        debug面板直接赋值hypnosis_degree无任何钳位，加debug豁免
    """
    if modes.debug():
        return []
    failures = []
    for cid, chara in _iter_npcs():
        degree = hypnosis_domain.degree(cid)
        if _num(degree) and 0 <= degree <= 200:
            continue
        talents = {tid: _talent_get(chara, tid) for tid in (331, 332, 333, 334)}
        failures.append(
            make_failure(
                "MIND-08",
                "催眠深度值域",
                (
                    f"[warning] 角色id={cid}({_name(chara)})的hypnosis.hypnosis_degree越界: "
                    f"{degree!r}(类型{type(degree).__name__}，合法范围[0,200])，玩家talent[331-334]={talents}"
                ),
                [cid],
            )
        )
    return failures


@register_check("MIND-09", "催眠类无意识状态需要对应的催眠深度")
def check_hypnosis_type_degree_threshold() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验unconscious_h∈{4,5,6,7}(平然/空气/体控/心控)时催眠深度达到对应门槛(50/100/200/200，
        Hypnosis_Type.csv)。面板只在达标后才结算类型，深度不足却处于该状态说明状态被越级设置。
        这是近乎空真的纵深防御——对应通用效果在Behavior_Effect.csv零引用，也没有Python直接调用点，
        保留是为了挡mod/旧存档/未来剧情旁路，加debug豁免
    """
    if modes.debug():
        return []
    thresholds = {4: 50, 5: 100, 6: 200, 7: 200}
    failures = []
    for cid, chara in _iter_npcs():
        u = _u(chara)
        if u not in thresholds:
            continue
        degree = hypnosis_domain.degree(cid)
        if _num(degree) and degree >= thresholds[u]:
            continue
        pl = _pl()
        failures.append(
            make_failure(
                "MIND-09",
                "催眠类无意识状态需要对应的催眠深度",
                (
                    f"[warning] 角色id={cid}({_name(chara)})unconscious_h={u}但hypnosis_degree={degree!r}未达门槛"
                    f"{thresholds[u]}，"
                    f"玩家hypnosis_type="
                    f"{player_ability.get(pl.cid, "hypnosis_type") if pl is not None else '?'}，"
                    f"talent[71/72/73]={ {tid: _talent_get(chara, tid) for tid in (71, 72, 73)} }"
                ),
                [cid],
            )
        )
    return failures


@register_check("MIND-10", "被催眠素质不早于深度阈值")
def check_hypnosis_talent_degree_order() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验干员的被催眠素质71/72/73分别在深度达到50/100/200时才可能持有(Hypnosis_Talent_Of_Npc.csv)。
        有素质而深度不足，说明深度被回退或素质被越级授予。已核实新周目继承不构成合法反例——
        深度回填前先重建角色，talent不在回填之列会随之归零。唯一违反点是debug面板独立编辑素质与深度
    """
    if modes.debug():
        return []
    failures = []
    for cid, chara in _iter_npcs():
        d = hypnosis_domain.degree(cid)
        if not _num(d):
            d = 0
        talents = {tid: _talent_get(chara, tid) for tid in (71, 72, 73)}
        ok = (
            (not talents[71] or d >= 50)
            and (not talents[72] or d >= 100)
            and (not talents[73] or d >= 200)
        )
        if not ok:
            failures.append(
                make_failure(
                    "MIND-10",
                    "被催眠素质不早于深度阈值",
                    (
                        f"[warning] 角色id={cid}({_name(chara)})的被催眠素质与深度失序: talent[71/72/73]={talents} "
                        f"hypnosis_degree={d!r}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("MIND-11", "被催眠素质需要玩家持有对应前置素质")
def check_hypnosis_talent_requires_pl_prereq() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验npc_gain_hypnosis_talent授予71/72/73前分别校验玩家的331/332/334(handle_talent.py)。
        干员有素质而玩家没有对应能力，说明素质来路不正。注意72的前置是332而73的前置是334(不是333)，
        以CSV为准。多周目会重建NPC素质，不构成合法反例，加debug豁免
    """
    if modes.debug():
        return []
    pl = _pl()
    failures = []
    for cid, chara in _iter_npcs():
        talents = {tid: _talent_get(chara, tid) for tid in (71, 72, 73)}
        pl_talents = (
            {tid: _talent_get(pl, tid) for tid in (331, 332, 334)}
            if pl is not None
            else {331: 0, 332: 0, 334: 0}
        )
        ok = (
            (not talents[71] or pl_talents[331])
            and (not talents[72] or pl_talents[332])
            and (not talents[73] or pl_talents[334])
        )
        if not ok:
            failures.append(
                make_failure(
                    "MIND-11",
                    "被催眠素质需要玩家持有对应前置素质",
                    (
                        f"[warning] 角色id={cid}({_name(chara)})的talent[71/72/73]={talents}但玩家talent[331/332/334]="
                        f"{pl_talents}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("MIND-12", "玩家催眠/时停素质链自洽")
def check_pl_talent_chain_consistency() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验玩家素质链332←331、333←332、334←333(Hypnosis_Talent_Of_Pl.csv)、317←316、318←317
        (Talent_Of_Arts.csv)不存在跳级持有。正常购买界面校验need_id，新周目继承源石技艺时整体复制
        已持有项不会自造缺口，仅debug能造缺口
    """
    if modes.debug():
        return []
    pl = _pl()
    if pl is None:
        return []
    pairs = [(332, 331), (333, 332), (334, 333), (317, 316), (318, 317)]
    bad = [
        (hi, lo)
        for hi, lo in pairs
        if _talent_get(pl, hi) and not _talent_get(pl, lo)
    ]
    if not bad:
        return []
    talents = {
        tid: _talent_get(pl, tid) for tid in (316, 317, 318, 331, 332, 333, 334)
    }
    return [
        make_failure(
            "MIND-12",
            "玩家催眠/时停素质链自洽",
            f"[warning] 玩家素质链跳级持有: {bad}(要求hi蕴含lo)，talent[316-318,331-334]={talents}",
            [0],
        )
    ]


@register_check("MIND-13", "三种催眠行为模式互斥")
def check_hypnosis_behavior_mode_exclusive() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验木头人blockhead/逆推active_h/角色扮演roleplay三个"行为主模式"至多一个生效。
        三个开启入口在写入前都调用clear_hypnosis_behavior_mode清理其余模式，两个同时为真会让
        H中AI逻辑(锁死不动 vs 主动逆推)互相打架。唯一违反点是debug面板逐项设置不执行清理，加debug豁免
    """
    if modes.debug():
        return []
    failures = []
    for cid, chara in _iter_npcs():
        h = hypnosis_domain.view(cid)
        on = [
            bool(getattr(h, "blockhead", False)),
            bool(getattr(h, "active_h", False)),
            bool(getattr(h, "roleplay", None)),
        ]
        if sum(on) > 1:
            failures.append(
                make_failure(
                    "MIND-13",
                    "三种催眠行为模式互斥",
                    (
                        f"[warning] 角色id={cid}({_name(chara)})同时命中多个催眠行为模式: blockhead={on[0]} "
                        f"active_h={on[1]} roleplay非空={on[2]}，"
                        f"unconscious_h={_u(chara)} behavior_id={_behavior_id(chara)}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("MIND-14", "体控无意识必须由木头人或逆推支撑")
def check_body_control_unconscious_needs_mode() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验unconscious_h==6(体控)时hypnosis.blockhead或hypnosis.active_h至少一个为真。
        u==6全仓只有木头人开启与逆推开启两个写入点，都在同一函数里连带写入对应模式标志，关闭效果也同步复位。
        方向已核实且不得写反：反方向(模式为真⇒u==6)会被时停开关、H结束整体重置h_state等合法路径打穿，
        故只做u==6⇒模式非空这一半
    """
    if modes.debug():
        return []
    failures = []
    for cid, chara in _iter_npcs():
        if _u(chara) != 6:
            continue
        h = hypnosis_domain.view(cid)
        if getattr(h, "blockhead", False) or getattr(h, "active_h", False):
            continue
        h_state = h_state_domain.view(cid)
        failures.append(
            make_failure(
                "MIND-14",
                "体控无意识必须由木头人或逆推支撑",
                (
                    f"角色id={cid}({_name(chara)})unconscious_h=6但blockhead={getattr(h, 'blockhead', '?')} "
                    f"active_h={getattr(h, 'active_h', '?')} "
                    f"roleplay={getattr(h, 'roleplay', '?')} "
                    f"h_state.npc_active_h="
                    f"{getattr(h_state, 'npc_active_h', '?')} "
                    f"sp_flag.is_h={flags.get(chara.cid, "is_h")} "
                    f"time_stop_mode={modes.time_stop()} "
                    f"behavior_id={_behavior_id(chara)}"
                ),
                [cid],
            )
        )
    return failures


@register_check("MIND-15", "心控无意识必须有角色扮演项")
def check_mind_control_unconscious_needs_roleplay() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验unconscious_h==7(心控)时hypnosis.roleplay非空。u==7的唯一写入点是提交非空角色扮演列表
        的分支，提交空列表时同一函数会把7清回0，处于7却无扮演项说明列表被清而状态没跟上。
        只做单向(非空⇔7中的7⇒非空这一半)——心控效果会持续到玩家主动解除，而unconscious_h会被
        时停开关、睡眠猥亵、睡奸反复覆写，三者都不动roleplay，双向等价会被打穿
    """
    if modes.debug():
        return []
    failures = []
    for cid, chara in _iter_npcs():
        if _u(chara) != 7:
            continue
        h = hypnosis_domain.view(cid)
        if getattr(h, "roleplay", None):
            continue
        failures.append(
            make_failure(
                "MIND-15",
                "心控无意识必须有角色扮演项",
                (
                    f"角色id={cid}({_name(chara)})unconscious_h=7但hypnosis.roleplay={getattr(h, 'roleplay', '?')!r}(应"
                    f"非空)，"
                    f"blockhead={getattr(h, 'blockhead', '?')} active_h={getattr(h, 'active_h', '?')}"
                ),
                [cid],
            )
        )
    return failures


@register_check("MIND-16", "角色扮演列表的形状与内容合法")
def check_roleplay_list_shape() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验hypnosis.roleplay是list，元素为正整数且均属于game_config.config_roleplay，且无重复。
        UI只append config_roleplay中的正整数cid，旧存档int被粗暴迁移成空列表；损坏/重复编号不会被
        MIND-13/MIND-15捕获，却会让角色信息面板与角色扮演前提读出无效项进而KeyError。
        config_roleplay在独立脚本环境下可能未加载，缺表时降级跳过；debug面板append无校验，加debug豁免
    """
    if modes.debug():
        return []
    try:
        from Script.Config import game_config
    except Exception:
        return []
    roleplay_config = getattr(game_config, "config_roleplay", None)
    if not roleplay_config:
        return []
    failures = []
    for cid, chara in _iter_npcs():
        rp: object = hypnosis_domain.view(cid).roleplay
        if not isinstance(rp, list):
            failures.append(
                make_failure(
                    "MIND-16",
                    "角色扮演列表的形状与内容合法",
                    f"[warning] 角色id={cid}({_name(chara)})的hypnosis.roleplay不是list: {type(rp).__name__}",
                    [cid],
                )
            )
            continue
        bad_type = [x for x in rp if type(x) is not int or x <= 0]
        dup = sorted({x for x in rp if type(x) is int and rp.count(x) > 1})
        bad_id = [
            x
            for x in rp
            if type(x) is int and x > 0 and x not in roleplay_config
        ]
        if bad_type or dup or bad_id:
            failures.append(
                make_failure(
                    "MIND-16",
                    "角色扮演列表的形状与内容合法",
                    (
                        f"[warning] 角色id={cid}({_name(chara)})的roleplay含非法内容: 非正整数项{bad_type} 重复项{dup} "
                        f"不在config_roleplay中的编号{bad_id}，"
                        f"unconscious_h={_u(chara)}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("MIND-17", "体控/心控子项需要「被完全催眠」素质")
def check_body_mind_control_sub_item_requires_talent_73() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验六个体控/心控子项(增加敏感度/强制排卵/木头人/逆推/角色扮演/苦痛快感化)任一为真时角色必须
        持有素质73(被完全催眠)。四个直接指令都以TARGET_HAS_BEEN_COMPLETE_HYPNOSIS(素质73)为前提。
        本式会在一条完全合法的操作序列上触发，那是真实旁路而非误报：催眠面板的体控/心控子项直接调
        chara_handle_instruct_common_settle绕过InstructConfig前提，而npc_gain_hypnosis_talent每次调用
        授予一个素质后就break，于是干员首次达到200%时可能只拿到71却已能从面板开启子项。
        命中时应向游戏侧提bug，不要放宽本式；加debug豁免
    """
    if modes.debug():
        return []
    failures = []
    for cid, chara in _iter_npcs():
        h = hypnosis_domain.view(cid)
        sub_items = {
            "increase_body_sensitivity": bool(
                getattr(h, "increase_body_sensitivity", False)
            ),
            "force_ovulation": bool(getattr(h, "force_ovulation", False)),
            "blockhead": bool(getattr(h, "blockhead", False)),
            "active_h": bool(getattr(h, "active_h", False)),
            "roleplay": bool(getattr(h, "roleplay", None)),
            "pain_as_pleasure": bool(getattr(h, "pain_as_pleasure", False)),
        }
        if not any(sub_items.values()) or _talent_get(chara, 73):
            continue
        pl = _pl()
        failures.append(
            make_failure(
                "MIND-17",
                "体控/心控子项需要「被完全催眠」素质",
                (
                    f"角色id={cid}({_name(chara)})缺素质73但已开启子项{[k for k, v in sub_items.items() if v]}，"
                    f"talent[71/72/73]={ {tid: _talent_get(chara, tid) for tid in (71, 72, 73)} }，"
                    f"hypnosis_degree={getattr(h, 'hypnosis_degree', '?')}，"
                    f"玩家hypnosis_type="
                    f"{player_ability.get(pl.cid, "hypnosis_type") if pl is not None else '?'}"
                ),
                [cid],
            )
        )
    return failures


@register_check("MIND-18", "空气催眠者必须与玩家同处已记录的催眠地点")
def check_air_hypnosis_colocated_with_anchor() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验全体unconscious_h==5(空气催眠)的角色的position都等于共享锚点pl_ability.air_hypnosis_position
        且等于玩家当前position。进入空气催眠时把玩家当前位置记入该共享字段，玩家/NPC离开记录地点各自
        有清理路径。已知真实成因——集体催眠+单体解除：集体催眠可让多人同时进入5，而单人解除催眠/理智
        耗尽只清当前交互对象状态却把共享锚点整个置""，剩下的人立刻违反本式；该状态会在玩家离开该地点时
        自愈，故为warning。迭代范围有意不限于npc_id_got，访客也可能被催眠
    """
    pl = _pl()
    if pl is None:
        return []
    air = player_ability.get(pl.cid, "air_hypnosis_position")
    pl_pos: object = activity.position(pl.cid)
    hits = []
    for cid, chara in _iter_all():
        if _u(chara) != 5:
            continue
        pos: object = activity.position(cid)
        if isinstance(air, str) and air != "" and pos == air == pl_pos:
            continue
        hits.append((cid, _name(chara), pos))
    if not hits:
        return []
    sample = "; ".join(f"cid={h[0]}({h[1]}) position={h[2]}" for h in hits[:5])
    return [
        make_failure(
            "MIND-18",
            "空气催眠者必须与玩家同处已记录的催眠地点",
            (
                f"[warning] 玩家position={pl_pos} air_hypnosis_position={air!r}，共{len(hits)}名unconscious_h=5的角色锚"
                f"点/位置不一致"
                f"(已知成因:集体催眠+单体解除清空共享锚点): {sample}{' ...' if len(hits) > 5 else ''}"
            ),
            [h[0] for h in hits],
        )
    ]


@register_check("MIND-19", "空气催眠地点必须处于锁门状态")
def check_air_hypnosis_scene_locked() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验unconscious_h==5的角色所在场景close_type==1(可锁门)且close_flag!=0(已锁门)。空气催眠只允许
        可锁门地点并在施放时强制锁门，仍有人处于5而门已开说明锁被别的结算解掉了。已知会命中的真实缺口：
        H结束效果会开门却不解除空气催眠，命中时应向游戏侧提缺口，故为warning而非直接放宽
    """
    scene_data = constant.scene_data
    pl = _pl()
    failures = []
    for cid, chara in _iter_all():
        if _u(chara) != 5:
            continue
        key = _scene_key(activity.position(chara.cid))
        scene = scene_data.get(key) if key is not None else None
        if (
            scene is not None
            and getattr(scene, "close_type", 0) == 1
            and scene_state.close_flag(scene.scene_path) != 0
        ):
            continue
        air_position = (
            player_ability.get(pl.cid, "air_hypnosis_position")
            if pl is not None
            else "?"
        )
        failures.append(
            make_failure(
                "MIND-19",
                "空气催眠地点必须处于锁门状态",
                f"[warning] 角色id={cid}({_name(chara)})unconscious_h=5但所在场景{key!r}未处于锁门状态: "
                f"close_type={getattr(scene, 'close_type', '?') if scene is not None else '场景不存在'} "
                f"close_flag={scene_state.close_flag(scene.scene_path) if scene is not None else '?'}，"
                f"玩家position={activity.position(pl.cid) if pl is not None else '?'}，"
                f"air_hypnosis_position={air_position}",
                [cid],
            )
        )
    return failures


@register_check("MIND-20", "空气催眠地点记录的形状可解析")
def check_air_hypnosis_anchor_shape() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验pl_ability.air_hypnosis_position为""，或为可解析成合法场景的字符串list。字段类型注解是
        str=""，但当前成功路径赋的是position(List[str])，混入任意字符串会让位置比较永远失真，无法解析
        的路径还会让MIND-19取场景时KeyError。有意不写len(air)==2——场景路径不是固定两段
    """
    pl = _pl()
    if pl is None:
        return []
    air = player_ability.get(pl.cid, "air_hypnosis_position")
    if air == "":
        return []
    scene_data = constant.scene_data
    key = _scene_key(air) if isinstance(air, list) else None
    ok = (
        isinstance(air, list)
        and bool(air)
        and all(isinstance(x, str) for x in air)
        and key in scene_data
    )
    if ok:
        return []
    has_air_u5 = any(_u(chara) == 5 for _, chara in _iter_all())
    return [
        make_failure(
            "MIND-20",
            "空气催眠地点记录的形状可解析",
            f"[warning] 玩家air_hypnosis_position无法解析成合法场景: 取值={air!r}(类型{type(air).__name__}) "
            f"scene_key={key!r}，玩家position={activity.position(pl.cid)}，当前是否有u=5的角色={has_air_u5}",
            [0],
        )
    ]


@register_check("MIND-21", "玩家当前催眠类型合法且已解锁")
def check_pl_hypnosis_type_valid() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验pl_ability.hypnosis_type∈{0,1,2,3,4}，且1需素质331、2需333、3/4需334(Hypnosis_Type.csv的
        talent_id列)。越界或未解锁的类型会让催眠完成判定去读不存在的配置或越级授予状态。类型0(无/每次
        手动选择)是字段默认值，必须豁免素质检查——CSV里类型0也写talent_id=331，但没有331的新玩家合法地
        处于0。类型2(空气)的前置是333而非332，以CSV为准
    """
    if modes.debug():
        return []
    pl = _pl()
    if pl is None:
        return []
    t = player_ability.get(pl.cid, "hypnosis_type")
    prereq = {1: 331, 2: 333, 3: 334, 4: 334}
    ok = (
        isinstance(t, int)
        and not isinstance(t, bool)
        and t in (0, 1, 2, 3, 4)
        and (t == 0 or bool(_talent_get(pl, prereq[t])))
    )
    if ok:
        return []
    talents = {tid: _talent_get(pl, tid) for tid in (331, 332, 333, 334)}
    return [
        make_failure(
            "MIND-21",
            "玩家当前催眠类型合法且已解锁",
            (
                f"[warning] 玩家pl_ability.hypnosis_type={t!r}(类型{type(t).__name__})非法或未解锁对应前置素质，"
                f"talent[331-334]={talents}"
            ),
            [0],
        )
    ]


# ============================== 三、无意识与睡眠 ==============================


@register_check("MIND-22", "无意识状态取值域")
def check_unconscious_h_range() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验sp_flag.unconscious_h∈[0,7]。存档/schema护栏，越界值会让所有unconscious_flag_N前提全部
        落空，角色进入"既非正常也非任何已知无意识"的黑洞状态。全仓所有写入点都是0-7的字面量，
        当前代码下不可能失败，归入迁移/存档完整性组，按warning处理
    """
    failures = []
    for cid, chara in _iter_pl_and_npcs():
        u = flags.get(chara.cid, "unconscious_h")
        if isinstance(u, bool) or not isinstance(u, int) or not (0 <= u <= 7):
            failures.append(
                make_failure(
                    "MIND-22",
                    "无意识状态取值域",
                    (
                        f"[warning] 角色id={cid}({_name(chara)})的sp_flag.unconscious_h越界: {u!r}，"
                        f"is_h={flags.get(chara.cid, "is_h")} "
                        f"behavior_id={_behavior_id(chara)} state={activity.state(chara.cid)}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("MIND-23", "睡眠行为与角色状态ID对齐")
def check_sleep_behavior_state_alignment() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验behavior.behavior_id=="sleep"时state==111。设置睡眠的两处(玩家睡眠面板、NPC睡觉状态机)
        都同时写这两个字段，二者分裂会让行为驱动的睡眠结算与状态驱动的显示/事件对不上。只做单向，
        有意不写双条件——state会在其他场景被赋成字符串行为id，双向式会以"类型不符"而非"状态不同步"的
        形式失败。行为正常/强制结束时二者一起重置，不产生半态
    """
    failures = []
    for cid, chara in _iter_pl_and_npcs():
        if _behavior_id(chara) != "sleep":
            continue
        state = activity.state(chara.cid)
        if state == 111:
            continue
        behavior = activity.behavior(chara.cid)
        failures.append(
            make_failure(
                "MIND-23",
                "睡眠行为与角色状态ID对齐",
                (
                    f"角色id={cid}({_name(chara)})behavior_id=sleep但state="
                    f"{state!r}(类型{type(state).__name__}，应为111)，"
                    f"start_time={getattr(behavior, 'start_time', '?')} duration={getattr(behavior, 'duration', '?')} "
                    f"sleep_point={num.shown(needs.of(cid)['sleep'])}"
                ),
                [cid],
            )
        )
    return failures


@register_check("MIND-24", "熟睡值值域")
def check_sleep_point_bound() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验玩家与已登场干员的熟睡值（needs.of(cid)["sleep"]）是非bool数值且落在[0,100]内。
        debug面板可以直接改熟睡值，所以debug模式下不检查。失败信息附带body.needs里的疲劳tired。
    """
    if modes.debug():
        return []
    failures = []
    for cid, chara in _iter_pl_and_npcs():
        sp = needs.of(cid)["sleep"]
        if _num(sp) and 0 <= sp <= 100:
            continue
        failures.append(
            make_failure(
                "MIND-24",
                "熟睡值值域",
                (
                    f"角色id={cid}({_name(chara)})的sleep_point越界: {sp!r}(合法范围[0,100])，"
                    f"tired={num.shown(needs.of(cid)['tired'])} behavior_id={_behavior_id(chara)} "
                    f"unconscious_h={_u(chara)}"
                ),
                [cid],
            )
        )
    return failures


@register_check("MIND-25", "睡眠无意识必须依附睡眠行为或装睡")
def check_sleep_unconscious_needs_sleep_or_pretend() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验unconscious_h==1(睡眠)时behavior_id=="sleep"或h_state.pretend_sleep为真。进入睡奸/睡眠
        猥亵的前提都含T_ACTION_SLEEP，退出时unconscious_h归零；u==1却既不在睡也不在装睡，等于对一个
        清醒角色持续跑无意识H结算。pretend_sleep是必要的合法例外，即便该分支当前不可达(见MIND-30)也要
        保留。已知真实失败途径：睡奸中NPC睡眠行为自然到期时只重置behavior并刷新第5/6位，不动unconscious_h
    """
    failures = []
    for cid, chara in _iter_npcs():
        if _u(chara) != 1:
            continue
        if _behavior_id(chara) == "sleep" or h_state_domain.get(
            cid, "pretend_sleep"
        ):
            continue
        failures.append(
            make_failure(
                "MIND-25",
                "睡眠无意识必须依附睡眠行为或装睡",
                (
                    f"角色id={cid}({_name(chara)})unconscious_h=1但既不在sleep行为中也未装睡: "
                    f"behavior_id={_behavior_id(chara)} "
                    f"pretend_sleep={h_state_domain.get(cid, 'pretend_sleep')} "
                    f"sleep_h_awake={flags.get(cid, 'sleep_h_awake')} "
                    f"sleep_point={num.shown(needs.of(cid)['sleep'])} state={activity.state(chara.cid)}"
                ),
                [cid],
            )
        )
    return failures


@register_check("MIND-28", "时停高潮计数结构合法")
def check_time_stop_orgasm_count_shape() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验h_state.time_stop_orgasm_count是dict，键为int、值为非负整数。存档/schema护栏，每个部位的
        时停高潮计数必须是非负整数，负数或非整数会破坏any(values())判定与解除时停时的高潮换算。
        当前代码下不可失败——键来自config_character_state的int主键，值来自orgasm_settle.py的
        += climax_count(两个非负int之和)，旧存档由setdefault补齐，归入迁移组，按warning处理
    """
    failures = []
    for cid, chara in _iter_npcs():
        h_state = h_state_domain.view(cid)
        d = getattr(h_state, "time_stop_orgasm_count", None)
        ok = isinstance(d, dict) and all(
            type(k) is int and _num(v) and v >= 0 for k, v in d.items()
        )
        if not ok:
            failures.append(
                make_failure(
                    "MIND-28",
                    "时停高潮计数结构合法",
                    (
                        f"[warning] 角色id={cid}({_name(chara)})的h_state.time_stop_orgasm_count结构非法: {d!r}，"
                        f"time_stop_release={getattr(h_state, 'time_stop_release', '?')} "
                        f"time_stop_mode={modes.time_stop()}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("MIND-29", "睡眠计划时分字段合法")
def check_sleep_plan_time_shape() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验action_info.plan_to_sleep_time与plan_to_wake_time均为[时,分]形状的二元int列表，
        小时0-23、分钟0-59。存档/schema护栏，坏值会在datetime.replace()或AI时间比较处炸开。
        唯一写入点全部经过钳位且只写玩家(cid 0)，NPC永远保持默认[6,0]/[18,0]，当前代码下不可失败，
        归入迁移组，按warning处理
    """
    failures = []
    for cid, chara in _iter_pl_and_npcs():
        sleep_t = action_info.get(cid, "plan_to_sleep_time")
        wake_t = action_info.get(cid, "plan_to_wake_time")

        def _time_ok(t: object) -> bool:
            """检查单个[时,分]字段是否合法"""
            return (
                isinstance(t, list)
                and len(t) == 2
                and type(t[0]) is int
                and type(t[1]) is int
                and 0 <= t[0] <= 23
                and 0 <= t[1] <= 59
            )

        if _time_ok(sleep_t) and _time_ok(wake_t):
            continue
        failures.append(
            make_failure(
                "MIND-29",
                "睡眠计划时分字段合法",
                (
                    f"[warning] 角色id={cid}({_name(chara)})的睡眠计划时分字段非法: plan_to_sleep_time={sleep_t!r} "
                    f"plan_to_wake_time={wake_t!r}，"
                    f"sleep_time={action_info.get(cid, 'sleep_time')} "
                    f"wake_time={action_info.get(cid, 'wake_time')}"
                ),
                [cid],
            )
        )
    return failures


@register_check("MIND-30", "装睡标记在当前版本不应出现")
def check_pretend_sleep_should_be_unreachable() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]
    功能:
        校验h_state.pretend_sleep恒为False。全仓只有一个写入点，而该分支因赋值顺序不可达：同函数内
        先调用judge_character_status_time_over(end_now=2)把behavior整体换成默认Behavior(behavior_id
        回到share_blankly)，导致后续两次handle_action_sleep判定必然为假。这是一条"死代码复活警报"，
        不是状态一致性断言——合取式版本(pretend_sleep⇒is_h and u==1)今天恒为空真，且一旦顺序bug被修好
        就立刻变成误报源(玩家离开场景会清is_h/unconscious_h却不重置h_state)，故只做"不应出现"这一半
    """
    failures = []
    for cid, chara in _iter_npcs():
        h_state = h_state_domain.view(cid)
        if not getattr(h_state, "pretend_sleep", False):
            continue
        failures.append(
            make_failure(
                "MIND-30",
                "装睡标记在当前版本不应出现",
                (
                    f"[warning] 角色id={cid}({_name(chara)})的h_state.pretend_sleep=True(当前版本该写入路径应不可达，"
                    f"属死代码复活警报): "
                    f"is_h={flags.get(cid, 'is_h')} unconscious_h={_u(chara)} behavior_id={_behavior_id(chara)} "
                    f"sleep_h_awake={flags.get(cid, 'sleep_h_awake')}"
                ),
                [cid],
            )
        )
    return failures
