"""玩家一方：回到输入前的收尾、执行玩家行动，以及一次推进的前后处理"""

from contextlib import contextmanager
from typing import Callable, Optional

from Script.Core import cache_control, constant, game_type
from Script.Design.action_scheduler.action import Action
from Script.Design.action_scheduler.settle import settle_action
from Script.Design.action_scheduler.timeline import Entry, Timeline

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """


def prepare(take_after_input: Callable[[], Optional[Callable[[], None]]]):
    """
    回到玩家输入前：收尾玩家的行为，再取出并执行登记的接续
    Keyword arguments:
    take_after_input -- 取出登记的接续（可为 None）并清空登记；收尾过程中可能新登记接续，故收尾后再取。接续可能再推进时间，此时会写入玩家的立即待办，本次输入让位
    Return arguments:
    None
    """
    from Script.Design import character_behavior
    from Script.Settle import realtime_settle

    if cache.character_data[0].behavior.behavior_id != constant.Behavior.SHARE_BLANKLY:
        character_behavior.judge_character_status_time_over(0, cache.game_time, end_now=2)
    realtime_settle.judge_pl_real_time_data()
    after_input = take_after_input()
    if after_input is not None:
        after_input()


def act(action: Action, timeline: Timeline) -> Optional[float]:
    """
    把行动写成玩家的行为并结算
    Keyword arguments:
    action -- 行动
    timeline -- 时间线
    Return arguments:
    float | None -- 占用的分钟数，时停中为 0；行动前置结算为玩家写入了立即待办时返回 None，本次让位
    """
    from Script.Design import handle_npc_ai, handle_npc_ai_in_h, handle_talent
    from Script.Settle import realtime_settle

    now = cache.game_time
    action.apply(cache.character_data[0], now)
    if not action.continued:
        start_hooks(timeline)
    if timeline.has_immediate(0):
        return None
    duration = settle_action(0, action)
    handle_npc_ai.judge_character_tired_sleep(0)
    handle_npc_ai_in_h.judge_character_h_obscenity_unconscious(0, now)
    realtime_settle.judge_pl_real_time_data()
    handle_talent.gain_talent(0, now_gain_type=0)
    # 时停中的玩家行动不占用时间，体力消耗仍按行动时长结算
    if cache.time_stop_mode:
        cache.achievement.time_stop_duration += duration
        return 0
    return duration


def start_hooks(timeline: Timeline):
    """
    玩家行动开始时只发生一次的处理：打断到点淋浴的 NPC、记录指令、移动时带上跟随者，以及行动前事件
    Keyword arguments:
    timeline -- 时间线
    Return arguments:
    None
    """
    from Script.Design import character_behavior, handle_npc_ai, handle_premise

    now = cache.game_time
    behavior_id = cache.character_data[0].behavior.behavior_id
    # 检查工作、娱乐中的角色是否到了淋浴时间
    if not cache.time_stop_mode:
        for npc_id in cache.npc_id_got:
            entry = timeline.get(npc_id)
            if entry is not None and not entry.immediate and handle_premise.handle_action_work_or_entertainment(npc_id) and handle_npc_ai.judge_interrupt_character_behavior(npc_id):
                timeline.put(npc_id, Entry(now))
    cache.daily_intsruce += character_behavior.character_instruct_record(0)
    cache.pl_pre_behavior_instruce.append(behavior_id)
    cache.pl_pre_behavior_instruce[:] = cache.pl_pre_behavior_instruce[-10:]
    if behavior_id in {constant.Behavior.MOVE, constant.Behavior.CARRY_MOVE}:
        # 同场景 NPC 的跟随与被携带角色的同步移动，并重置全员的目击玩家H
        handle_npc_ai.judge_same_position_npc_follow()
        for npc_id in cache.npc_id_got:
            cache.character_data[npc_id].sp_flag.see_pl_h = False
    character_behavior.judge_before_pl_behavior()


@contextmanager
def turn_session(scheduler):
    """
    一次推进的前后处理：推进期间调度器标记为运行中；Web 模式下记录文本并提示前端正在结算；推进正常结束后结算外勤委托、睡觉存档、成就，并把焦点还给输入框
    Keyword arguments:
    scheduler -- 调度器
    Return arguments:
    None
    """
    from Script.Core import py_cmd
    from Script.Core.get_text import _
    from Script.Settle import sleep_settle
    from Script.System.Field_Commission_System import field_commission_function
    from Script.UI.Panel import achievement_panel

    scheduler.running = True
    web = getattr(cache, "web_mode", False)
    if web:
        from Script.Core import web_server

        # 开始记录文本（用于Web模式文本回溯），并通知前端显示结算提示
        cache.web_text_recording_flag = True
        web_server.emit_settlement_status(True)
    try:
        yield
        field_commission_function.update_field_commission()
        # 玩家睡觉存档
        if cache.pl_sleep_save_flag:
            cache.pl_sleep_save_flag = False
            sleep_settle.update_save()
        achievement_panel.achievement_flow(_("时停"))
        achievement_panel.achievement_flow(_("群交"))
        py_cmd.focus_cmd()
    finally:
        scheduler.running = False
        if web:
            cache.web_text_recording_flag = False
            web_server.emit_settlement_status(False)
