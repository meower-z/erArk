# -*- coding: UTF-8 -*-
"""
mod_info.json 里登记的 10 个替换函数，全部是薄包装：判断是否在接管的一轮内，不在就直接调用原函数

一轮内的分工：
- init_character_behavior：轮次边界；结算完后画摘要页，再回放保留信息
- handle_instruct_data：标记模板派发 / 玩家真实指令窗口；本轮已绝顶的 NPC 跳过后续模板派发；记太累退出
- handle_settle_behavior：没有玩家真实指令时不把属性变化面板交给本体画
- handle_talk_draw：按 policy.talk_decision 直显 / 缓冲 / 吞掉口上
- orgasm_settle_in_second_behavior、judge_orgasm_edge_success、check_second_effect：先捕获，拿到结果后再决定显示；
  同时记录本轮绝顶与寸止
- draw_achievement_notice、mark_effect、gain_talent：缓冲到摘要页之后回放
原函数一律用位置参数调用，与本体签名一一对应。
"""
from Script.Core.mod_manager import call_original_function

from . import capture, page, policy, records, state

_CHARACTER_BEHAVIOR = "Script.Design.character_behavior"
_TALK = "Script.Design.talk"
_SETTLE_BEHAVIOR = "Script.Design.settle_behavior"
_ORGASM_SETTLE = "Script.Settle.orgasm_settle"
_ACHIEVEMENT = "Script.UI.Panel.achievement_panel"
_SECOND_BEHAVIOR = "Script.Design.second_behavior"
_HANDLE_TALENT = "Script.Design.handle_talent"


def _cache():
    """
    取当前游戏缓存；每次现取，不持有可能被整体替换的旧引用
    Keyword arguments:
    无
    Return arguments:
    Cache -- cache_control.cache
    """
    from Script.Core import cache_control

    return cache_control.cache


def _is_web_draw() -> bool:
    """
    是否 Web 绘制模式；本 mod 只支持 Tk，Web 模式下全部直通
    Keyword arguments:
    无
    Return arguments:
    bool -- 是否 Web 模式
    """
    from Script.Config import normal_config

    return bool(getattr(normal_config.config_normal, "web_draw", False))


def _is_active() -> bool:
    """
    是否处在本 mod 接管的一轮内
    Keyword arguments:
    无
    Return arguments:
    bool -- 是否接管中
    """
    return state.turn_active and not _is_web_draw()


def _mark_edge_break(character_id: int, reason: str, live: bool = True) -> None:
    """
    记一次寸止断因；live 时该角色的绝顶链在本轮内实时显示
    全体结束指令触发的批量释放、以及太累退出只记断因不实时显示，免得一条指令刷出一大串结算
    Keyword arguments:
    character_id -- 角色id
    reason -- "tired" / "release" / "fail"
    live -- 是否实时显示该角色的绝顶链
    Return arguments:
    None
    """
    turn = state.turn
    if live:
        turn.edge_break_live.add(character_id)
    records.mark_break_reason(turn.break_reason, character_id, reason)


def _replay_queue() -> None:
    """
    摘要页之后按发生顺序回放缓冲的保留信息，然后清空队列
    Keyword arguments:
    无
    Return arguments:
    None
    """
    turn = state.turn
    capture.replay(turn.replay_queue)
    turn.replay_queue = []


def modded_init_character_behavior():
    """
    轮次边界：只有最外层、Tk 模式、群交模式开着时才接管；结算完画摘要页，再回放保留信息
    Keyword arguments:
    无
    Return arguments:
    原函数返回值
    """
    state.depth += 1
    try:
        if state.depth > 1 or _is_web_draw() or not _cache().group_sex_mode:
            return call_original_function(_CHARACTER_BEHAVIOR, "init_character_behavior")
        state.begin_turn(_cache().character_data[0].behavior.behavior_id)
        result = call_original_function(_CHARACTER_BEHAVIOR, "init_character_behavior")
        page.draw_page(page.build_rows(state.turn, _cache().character_data))
        _replay_queue()
        return result
    finally:
        state.depth -= 1
        if state.depth == 0:
            state.end_turn()


def modded_handle_talk_draw(character_id: int, talk_text: str, now_talk_id: str, second_behavior_id="", common_behavior_id=None):
    """
    口上：按 policy.talk_decision 直显、缓冲到摘要页之后、或吞掉
    Keyword arguments:
    character_id -- 角色id
    talk_text -- 口上文本
    now_talk_id -- 口上id
    second_behavior_id -- 二段行为id
    common_behavior_id -- 纸娃娃地文的行为id
    Return arguments:
    原函数返回值；吞掉时为 None
    """
    args = (character_id, talk_text, now_talk_id, second_behavior_id, common_behavior_id)
    if not _is_active():
        return call_original_function(_TALK, "handle_talk_draw", *args)
    now_behavior_id = policy.derive_talk_behavior_id(now_talk_id, common_behavior_id)
    decision = policy.talk_decision(character_id, now_behavior_id, second_behavior_id, lambda: bool(_cache().character_data[character_id].sp_flag.is_h))
    if decision == policy.TALK_DROP:
        return None
    if decision == policy.TALK_BUFFER:
        with capture.capture_into(state.turn.replay_queue):
            return call_original_function(_TALK, "handle_talk_draw", *args)
    return call_original_function(_TALK, "handle_talk_draw", *args)


def modded_handle_settle_behavior(character_id: int, now_time, event_flag=1):
    """
    属性变化面板：只有这次结算里出现过玩家真实指令时才把面板交给本体画，其余返回 None 由摘要页代替
    Keyword arguments:
    character_id -- 角色id
    now_time -- 结算时间
    event_flag -- 本体参数，原样传递
    Return arguments:
    原函数返回的面板，或 None
    """
    if not _is_active():
        return call_original_function(_SETTLE_BEHAVIOR, "handle_settle_behavior", character_id, now_time, event_flag)
    turn = state.turn
    previous_seen = turn.player_real_seen
    turn.player_real_seen = False
    try:
        panel = call_original_function(_SETTLE_BEHAVIOR, "handle_settle_behavior", character_id, now_time, event_flag)
        seen = turn.player_real_seen
    finally:
        turn.player_real_seen = previous_seen
    return panel if seen else None


def modded_handle_instruct_data(character_id: int, behavior_id: str, now_time, add_time, change_data):
    """
    指令结算：
    - 太累退出：记 <累>，不实时显示
    - 模板派发：目标本轮已绝顶就跳过（一轮内每个 NPC 只绝顶一轮），否则在模板派发窗口内结算
    - 玩家真实指令：在真实指令窗口内结算，期间的口上与结算原样实时显示
    Keyword arguments:
    character_id -- 角色id
    behavior_id -- 行为id
    now_time -- 结算时间
    add_time -- 行为时长
    change_data -- 状态变化记录
    Return arguments:
    原函数返回值；跳过时原样返回 change_data
    """
    if not state.turn_active or _is_web_draw():
        return call_original_function(_SETTLE_BEHAVIOR, "handle_instruct_data", character_id, behavior_id, now_time, add_time, change_data)
    if policy.is_tired_exit(behavior_id):
        _mark_edge_break(character_id, "tired", live=False)
    cache = _cache()
    turn = state.turn
    is_template = policy.is_template_dispatch(cache.group_sex_mode, character_id, behavior_id)
    if is_template and cache.character_data[0].target_character_id in turn.orgasm_record:
        return change_data
    is_player_real = policy.is_player_real(cache.group_sex_mode, character_id, behavior_id, cache.character_data[0].target_character_id)
    if is_player_real:
        turn.player_real_seen = True
    previous_real, previous_template = turn.player_real_active, turn.template_dispatch_active
    if is_player_real:
        turn.player_real_active = True
    if is_template:
        turn.template_dispatch_active = True
    try:
        return call_original_function(_SETTLE_BEHAVIOR, "handle_instruct_data", character_id, behavior_id, now_time, add_time, change_data)
    finally:
        turn.player_real_active, turn.template_dispatch_active = previous_real, previous_template


def modded_orgasm_settle_in_second_behavior(character_id: int, change_data, normal_orgasm_dict: dict = {}, extra_orgasm_dict: dict = {}, un_count_orgasm_dict: dict = {}):
    """
    NPC 绝顶结算：先捕获，寸止断了（非批量释放）或玩家真实指令期间才实时显示；结算后把置位的绝顶/寸止并入本轮记录
    默认参数照抄本体签名，原样传给原函数
    Keyword arguments:
    character_id -- 角色id
    change_data -- 状态变化记录
    normal_orgasm_dict -- 本体参数
    extra_orgasm_dict -- 本体参数
    un_count_orgasm_dict -- 本体参数
    Return arguments:
    原函数返回值
    """
    args = (character_id, change_data, normal_orgasm_dict, extra_orgasm_dict, un_count_orgasm_dict)
    if not _is_active() or character_id == 0:
        return call_original_function(_ORGASM_SETTLE, "orgasm_settle_in_second_behavior", *args)
    cache = _cache()
    h_state = cache.character_data[character_id].h_state
    if records.is_edge_release_event(h_state.orgasm_edge, h_state.orgasm_edge_count):
        is_mass_release = policy.is_mass_end_release_source(cache.character_data[0].behavior.behavior_id)
        _mark_edge_break(character_id, "release", live=not is_mass_release)
    captured = []
    with capture.capture_into(captured):
        result = call_original_function(_ORGASM_SETTLE, "orgasm_settle_in_second_behavior", *args)
    turn = state.turn
    if character_id in turn.edge_break_live or turn.player_real_active:
        capture.draw_live(captured)
    from Script.Settle import orgasm_settle

    character_data = _cache().character_data[character_id]
    records.merge_second_behavior(turn.orgasm_record, turn.edge_record, character_id, character_data.second_behavior, orgasm_settle.get_orgasm_part_and_degree)
    return result


def modded_draw_achievement_notice(achievement_id_list: list):
    """
    成就提示：缓冲到摘要页之后回放
    Keyword arguments:
    achievement_id_list -- 成就id列表
    Return arguments:
    原函数返回值
    """
    if not _is_active():
        return call_original_function(_ACHIEVEMENT, "draw_achievement_notice", achievement_id_list)
    with capture.capture_into(state.turn.replay_queue):
        return call_original_function(_ACHIEVEMENT, "draw_achievement_notice", achievement_id_list)


def modded_mark_effect(character_id: int, change_data):
    """
    刻印变化：缓冲到摘要页之后回放
    Keyword arguments:
    character_id -- 角色id
    change_data -- 状态变化记录
    Return arguments:
    原函数返回值
    """
    if not _is_active():
        return call_original_function(_SECOND_BEHAVIOR, "mark_effect", character_id, change_data)
    with capture.capture_into(state.turn.replay_queue):
        return call_original_function(_SECOND_BEHAVIOR, "mark_effect", character_id, change_data)


def modded_gain_talent(character_id: int, now_gain_type: int, traget_talent_id=0):
    """
    素质取得：缓冲到摘要页之后回放
    Keyword arguments:
    character_id -- 角色id
    now_gain_type -- 本体参数
    traget_talent_id -- 本体参数（本体拼写如此）
    Return arguments:
    原函数返回值
    """
    if not _is_active():
        return call_original_function(_HANDLE_TALENT, "gain_talent", character_id, now_gain_type, traget_talent_id)
    with capture.capture_into(state.turn.replay_queue):
        return call_original_function(_HANDLE_TALENT, "gain_talent", character_id, now_gain_type, traget_talent_id)


def modded_judge_orgasm_edge_success(character_id: int, orgasm_edge_count: dict = {}, crossed_part_count: int = 1) -> bool:
    """
    寸止判定：先捕获提示；失败记 <寸止失败> 并实时显示；成功但余量 <=2 时也实时显示，让玩家当场看到快憋不住了
    默认参数照抄本体签名，原样传给原函数
    Keyword arguments:
    character_id -- 角色id
    orgasm_edge_count -- 本体参数：{部位: 寸止次数}，空时本体读角色当前值
    crossed_part_count -- 本体参数
    Return arguments:
    bool -- 是否寸止成功
    """
    if not _is_active():
        return call_original_function(_ORGASM_SETTLE, "judge_orgasm_edge_success", character_id, orgasm_edge_count, crossed_part_count)
    captured = []
    with capture.capture_into(captured):
        success = call_original_function(_ORGASM_SETTLE, "judge_orgasm_edge_success", character_id, orgasm_edge_count, crossed_part_count)
    if not success:
        _mark_edge_break(character_id, "fail")
    near_limit = False
    if success:
        # 与本体同口径：传入的计数为空时读角色当前的寸止计数
        now_edge_count = orgasm_edge_count or _cache().character_data[character_id].h_state.orgasm_edge_count
        near_limit = records.is_near_limit(records.edge_margin(_cache().character_data[0].ability[30], now_edge_count))
        if near_limit:
            state.turn.edge_near_limit.add(character_id)
    if not success or near_limit or state.turn.player_real_active:
        capture.draw_live(captured)
    return success


def modded_check_second_effect(character_id: int, change_data, pl_to_npc: bool = False):
    """
    NPC 二段结算：先捕获，寸止断了、接近极限或玩家真实指令期间才实时显示
    窗口期间记下当前角色，让口上判断"这条寸止链口上是不是这个角色自己的"
    Keyword arguments:
    character_id -- 角色id
    change_data -- 状态变化记录
    pl_to_npc -- 本体参数
    Return arguments:
    原函数返回值
    """
    if not _is_active() or character_id == 0:
        return call_original_function(_SECOND_BEHAVIOR, "check_second_effect", character_id, change_data, pl_to_npc)
    turn = state.turn
    captured = []
    previous_character = turn.second_effect_character
    turn.second_effect_character = character_id
    try:
        with capture.capture_into(captured):
            result = call_original_function(_SECOND_BEHAVIOR, "check_second_effect", character_id, change_data, pl_to_npc)
    finally:
        turn.second_effect_character = previous_character
    if character_id in turn.edge_break_live or character_id in turn.edge_near_limit or turn.player_real_active:
        capture.draw_live(captured)
    return result
