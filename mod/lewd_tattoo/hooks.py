# -*- coding: UTF-8 -*-
"""
钩子胶水：把本体 mod_hook 的五个钩子点接到 effects（数学）+ store（数据）上

每个 on_* 函数第一件事都是 store.active_keys；没淫纹的角色（绝大多数）一次 dict.get 就返回原值。
异常一律直接传播（mod_hook 约定），不吞错后用原值继续。
"""
import random
from typing import Dict, List, Optional, Tuple

from Script.Core import cache_control, game_type, get_text, mod_hook

from . import MOD_ID, effects, store

_ = get_text._
""" 翻译api """

_durability: Dict[int, int] = {}
""" 寸止压制的淫纹耐久 {角色id: 耐久}；只在一轮寸止内有意义（H 中不能存档），所以放模块变量，不进存档 """
BEAST_TALENTS = (111, 112, 113)
""" 兽耳/兽角/兽尾：有任一素质才有兽部快感 """


def register_all() -> None:
    """
    把本模块五个函数挂到本体钩子点
    Keyword arguments:
    无
    Return arguments:
    None
    """
    mod_hook.state_gain.register(on_state_gain, owner=MOD_ID)
    mod_hook.edge_judged.register(on_edge_judged, owner=MOD_ID)
    mod_hook.daily_desire_growth.register(on_daily_desire_growth, owner=MOD_ID)
    mod_hook.character_info_draw_list.register(on_character_info_draw_list, owner=MOD_ID)
    mod_hook.desire_written.register(on_desire_written, owner=MOD_ID)


def unregister_all() -> None:
    """
    从全部钩子点摘掉本 mod（测试用）
    Keyword arguments:
    无
    Return arguments:
    None
    """
    for hook in (mod_hook.state_gain, mod_hook.edge_judged, mod_hook.daily_desire_growth, mod_hook.character_info_draw_list, mod_hook.desire_written):
        hook.unregister(MOD_ID)


def clamp_desire(character_data: game_type.Character, profile: effects.Profile) -> None:
    """
    媚药式：把欲望值钳到下限以上（无媚药式时下限为 0，不做任何事）
    Keyword arguments:
    character_data -- 角色对象
    profile -- 该角色的数值画像
    Return arguments:
    None
    """
    if character_data.desire_point < profile.desire_floor:
        character_data.desire_point = profile.desire_floor


def on_state_gain(value: int, character_id: int, state_id: int, change_data, change_data_to_target_change) -> Optional[int]:
    """
    状态增量写入前的改写（钩子 state_gain）
    位置在本体心控苦痛快感化之后，所以心控优先；心控或本 mod 把苦痛/负面转成 23 后，那次 23 结算仍会经过本函数
    Keyword arguments:
    value -- 本体算好的增量(int)
    character_id -- 角色id
    state_id -- 状态id
    change_data -- 本体的结算记录对象（可能为 None）
    change_data_to_target_change -- 交互对象的结算记录对象（可能为 None）
    Return arguments:
    Optional[int] -- 写回本状态的增量；None 表示已转成心理快感并自行结算完毕
    """
    keys = store.active_keys(character_id)
    if keys is None:
        return value
    profile = effects.compile_profile(keys)
    character_data = cache_control.cache.character_data[character_id]
    # 欲望锁：任何一次状态结算都顺带钳一次，覆盖读档后、本体未通知过的降欲望路径
    clamp_desire(character_data, profile)
    # 只处理正增量；负增量（消退、扣减）原样
    if value <= 0:
        return value
    plan = effects.plan_gain(profile, state_id, value)
    if plan.to_mind:
        # 同本体心控苦痛快感化：以原增量递归结算心理快感，受虐(36)当能力等级，不再加十分之一
        from Script.Settle import common_default

        common_default.base_chara_state_common_settle(
            character_id,
            value,
            effects.MIND,
            0,
            ability_level=character_data.ability[36],
            tenths_add=False,
            change_data=change_data,
            change_data_to_target_change=change_data_to_target_change,
        )
        return None
    if plan.side:
        present = present_feel_parts(character_id)
        for sid, gain in plan.side:
            if sid in present:
                _write_raw_gain(character_data, sid, gain, change_data, change_data_to_target_change)
    return plan.main


def present_feel_parts(character_id: int, include_transient: bool = True) -> frozenset:
    """
    角色"拥有并能结算"的快感部位，联结只发给这些部位
    规则同本体：男性(sex==0)无 2/4/7，女性(sex==1)无 3（sleep_settle 同规则）；
    兽部 22 需要兽耳/兽角/兽尾任一素质；心理 23 在无意识或睡眠时不结算（同 common_default）
    Keyword arguments:
    character_id -- 角色id
    include_transient -- 是否计入"无意识/睡眠时没有心理"这种暂时规则（面板只看身体，传 False）
    Return arguments:
    frozenset -- 快感状态id集合
    """
    character_data = cache_control.cache.character_data[character_id]
    parts = set(effects.FEEL_PARTS)
    if character_data.sex == 0:
        parts -= {2, 4, 7}
    elif character_data.sex == 1:
        parts.discard(3)
    if not any(character_data.talent.get(talent_id, 0) for talent_id in BEAST_TALENTS):
        parts.discard(22)
    if include_transient:
        from Script.Design import handle_premise

        if handle_premise.handle_unconscious_flag_ge_1(character_id) or handle_premise.handle_action_sleep(character_id):
            parts.discard(effects.MIND)
    return frozenset(parts)


def _write_raw_gain(character_data: game_type.Character, state_id: int, gain: int, change_data, change_data_to_target_change) -> None:
    """
    联结裸增量：直接写入并夹到 [0, 99999]，按本体 base_chara_state_common_settle 的格式记入两份结算记录；
    不经过 base_chara_state_common_settle，所以不再吃倍率、不再联结、不触发 extra_feel_settle
    Keyword arguments:
    character_data -- 角色对象
    state_id -- 目标快感状态id
    gain -- 裸增量(>0)
    change_data -- 结算记录对象（可能为 None）
    change_data_to_target_change -- 交互对象的结算记录对象（可能为 None）
    Return arguments:
    None
    """
    character_data.status_data[state_id] = max(0, min(99999, character_data.status_data.get(state_id, 0) + gain))
    if change_data is not None:
        change_data.status_data.setdefault(state_id, 0)
        change_data.status_data[state_id] += gain
    if change_data_to_target_change is not None:
        target_change = change_data_to_target_change.target_change.setdefault(character_data.cid, game_type.TargetChange())
        target_change.status_data.setdefault(state_id, 0)
        target_change.status_data[state_id] += gain


def on_desire_written(character_data: game_type.Character) -> game_type.Character:
    """
    本体降低欲望值之后的通知（钩子 desire_written）：媚药式立刻钳回下限
    Keyword arguments:
    character_data -- 刚被改写欲望值的角色对象
    Return arguments:
    game_type.Character -- 原样返回
    """
    keys = store.active_keys(character_data.cid)
    if keys is not None:
        clamp_desire(character_data, effects.compile_profile(keys))
    return character_data


def on_edge_judged(value: Tuple[bool, str], character_id: int, over_count: int) -> Tuple[bool, str]:
    """
    寸止失败后的淫纹追加判定（钩子 edge_judged）
    只改判定那一行提示；之后调用方照常显示"{角色}{部位}绝顶寸止"等后续文本
    Keyword arguments:
    value -- (本体判定是否成功, 本体提示文本)
    character_id -- 被寸止的角色id
    over_count -- 本体的 over_count（技巧*3 - Σ寸止次数²）
    Return arguments:
    Tuple[bool, str] -- 新的 (是否成功, 提示文本)
    """
    keys = store.active_keys(character_id)
    if keys is None or not effects.compile_profile(keys).edge_suppress:
        return value
    character_data = cache_control.cache.character_data[character_id]
    # 本次之前的寸止计数全为 0 = 新一轮寸止开始（绝顶释放、H 结束、重新开启寸止都会清零），耐久回满；本体成功时也要检查，否则旧耐久会带进新一轮
    if not any(character_data.h_state.orgasm_edge_count.values()):
        _durability[character_id] = effects.EDGE_DURABILITY
    success, _text = value
    if success:
        return value
    outcome, _durability[character_id] = effects.judge_edge_suppress(-over_count, _durability.get(character_id, effects.EDGE_DURABILITY), random.random)
    if outcome == "fail":
        return value
    text = effects.EDGE_EXHAUST_TEXT if outcome == "exhaust" else random.choice(effects.EDGE_RESCUE_TEXTS)
    return True, "\n" + _(text).format(NPCName=character_data.name) + "\n"


def on_daily_desire_growth(growth: int, character_id: int) -> int:
    """
    媚药式：每日欲望增长 ×2，并先把欲望值抬到 60（钩子 daily_desire_growth，只对 NPC 调用）
    Keyword arguments:
    growth -- 本体算出的本日增长量
    character_id -- 角色id
    Return arguments:
    int -- 新增长量
    """
    keys = store.active_keys(character_id)
    if keys is None:
        return growth
    profile = effects.compile_profile(keys)
    return effects.daily_growth(profile, cache_control.cache.character_data[character_id].desire_point, growth)


def on_character_info_draw_list(draw_list: List, character_id: int, width: int) -> List:
    """
    在肉体情况页末尾追加淫纹信息块（钩子 character_info_draw_list）
    Keyword arguments:
    draw_list -- 本体的绘制对象列表
    character_id -- 角色id
    width -- 绘制宽度
    Return arguments:
    List -- 新列表（不改原列表）
    """
    if character_id == 0 or not store.has_tattoo(character_id):
        return draw_list
    from . import ui

    return draw_list + [ui.TattooInfoDraw(character_id, width)]
