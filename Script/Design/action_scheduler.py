"""行动调度器：按开始时刻先后执行玩家和各 NPC 的行动，直到再次轮到玩家输入。

每个角色最多一条待办（Entry），存在 Scheduler.pending 里。每一步取最早的待办：同一时刻立即待办先行，其次是玩家。
待办要么带一个具体行动（Action，开始时一次结算完整段效果），要么不带行动，表示到时再定：玩家等待输入，NPC 由 AI 选择。
行动执行完后，若结算过程中没有为该角色写入新待办，就在行动结束时刻为它安排一条"到时再定"。
结算代码要某角色立刻做某事时，用 submit_current 写入立即待办；它不会被调度器覆盖。
本调度器不随存档保存，新开局或读档后丢弃，首次推进时按各角色当前的行为重建。
"""

import datetime
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable, Optional

from Script.Core import cache_control, constant, game_type
from Script.Design import game_time

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
WAIT_RECHECK_MINUTES = 5
""" 等待别人的行动时，相邻两次复查至多相隔的分钟数 """
SLEEP_CHUNK_MINUTES = 30
""" NPC 睡眠每段至多的分钟数，段间重新判断是否醒来 """
_scheduler = None
""" 本局的调度器；不随存档保存 """


@dataclass
class Action:
    """
    一个尚未开始的行动：要写到角色身上的行为副本、交互对象、状态，以及是否延续上一段\n
    continued 为真时本段延续上一段同一行动（如睡眠的第二个 30 分钟），不重复结算只在开始时发生一次的效果
    """

    behavior: game_type.Behavior
    target: int
    state: int
    continued: bool = False

    @classmethod
    def of(cls, character: game_type.Character, continued: bool = False):
        """
        复制角色身上已写好的行为，作为一个行动
        Keyword arguments:
        character -- 角色对象
        continued -- 是否延续上一段同一行动
        Return arguments:
        Action -- 行动，时长至少 1 分钟
        """
        behavior = deepcopy(character.behavior)
        behavior.duration = max(behavior.duration, 1)
        return cls(behavior, character.target_character_id, character.state, continued)

    def apply(self, character: game_type.Character, now: datetime.datetime):
        """
        把行动写成角色当前的行为，开始时刻为 now
        Keyword arguments:
        character -- 角色对象
        now -- 开始时刻
        Return arguments:
        None
        """
        character.behavior = deepcopy(self.behavior)
        character.behavior.start_time = now
        character.target_character_id = self.target
        character.state = self.state


@dataclass
class Entry:
    """一条待办：开始时刻 at；行动 action，为 None 表示到时再定；是否立即执行 immediate；执行完后的收尾回调 after"""

    at: datetime.datetime
    action: Optional[Action] = None
    immediate: bool = False
    after: Optional[Callable[[], None]] = None


def minutes_between(start: datetime.datetime, end: datetime.datetime) -> float:
    """
    按游戏日历计算两个时刻之间的分钟数
    Keyword arguments:
    start -- 起始时刻
    end -- 结束时刻
    Return arguments:
    float -- 分钟数，end 早于 start 时为负
    """
    return (game_time.to_game_time(end) - start).total_seconds() / 60


def behavior_end(behavior: game_type.Behavior) -> datetime.datetime:
    """
    取行为的结束时刻
    Keyword arguments:
    behavior -- 行为对象
    Return arguments:
    datetime.datetime -- 开始时刻加时长
    """
    return game_time.get_sub_date(minute=behavior.duration, old_date=behavior.start_time)


def wait_slice(remaining: float) -> float:
    """
    等待别人的行动时本段等多久：至多五分钟、至少一分钟，对方行动结束时恰好放开
    Keyword arguments:
    remaining -- 对方行动的剩余分钟数
    Return arguments:
    float -- 本段等待的分钟数
    """
    return max(1, min(WAIT_RECHECK_MINUTES, remaining))


def wait_action(target: int, minutes: float, continued: bool = False, wait_on_behavior_id: str = "") -> Action:
    """
    构造一个等待行动
    Keyword arguments:
    target -- 交互对象id
    minutes -- 等待分钟数
    continued -- 是否不结算一次性效果
    wait_on_behavior_id -- 所等待的对方行为id，空串表示不复查对方
    Return arguments:
    Action -- 等待行动
    """
    behavior = game_type.Behavior()
    behavior.behavior_id = constant.Behavior.WAIT
    behavior.duration = minutes
    behavior.wait_on_behavior_id = wait_on_behavior_id
    return Action(behavior, target, constant.CharacterStatus.STATUS_WAIT, continued)


def continue_current(character: game_type.Character, minutes: float) -> Action:
    """
    构造延续角色当前行为的一段
    Keyword arguments:
    character -- 角色对象
    minutes -- 本段分钟数
    Return arguments:
    Action -- 延续片段，时长至少 1 分钟
    """
    action = Action.of(character, continued=True)
    action.behavior.duration = max(minutes, 1)
    return action


def can_continue_sleep(character_id: int, now: datetime.datetime) -> bool:
    """
    判断睡眠中的 NPC 是否接着睡下一段
    Keyword arguments:
    character_id -- 角色id
    now -- 当前时刻
    Return arguments:
    bool -- 是否继续睡
    """
    from Script.Design import handle_premise

    behavior = cache.character_data[character_id].behavior
    if behavior.plan_end_time <= now:
        return False
    # 仅原定八小时的整夜睡眠响应早安问候，到玩家醒来时刻即醒
    if (
        minutes_between(behavior.plan_start_time, behavior.plan_end_time) == 480
        and handle_premise.handle_self_not_sleep_pills(character_id)
        and handle_premise.handle_assistant_morning_salutation_on(character_id)
        and handle_premise.handle_morning_salutation_flag_0(character_id)
    ):
        hour, minute = cache.character_data[0].action_info.plan_to_wake_time
        wake = behavior.plan_start_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if wake <= behavior.plan_start_time:
            wake = game_time.get_sub_date(day=1, old_date=wake)
        if now >= wake:
            return False
    # 疲劳清零、体力气力全满、不在睡觉时间、未服安眠药且未醉酒时醒来
    recovered = handle_premise.handle_tired_le_0(character_id) and handle_premise.handle_hp_max(character_id) and handle_premise.handle_mp_max(character_id)
    return not (
        recovered
        and not handle_premise.handle_game_time_is_sleep_time(character_id)
        and handle_premise.handle_self_not_sleep_pills(character_id)
        and handle_premise.handle_drunk_level_0(character_id)
    )


def settle_sleep(character_id: int, minutes: float, continued: bool, now: datetime.datetime):
    """
    结算一段睡眠：首段结算入睡效果，后续各段只补睡眠恢复；每段都按时长结算随时间变化的数值
    Keyword arguments:
    character_id -- 角色id
    minutes -- 本段分钟数
    continued -- 是否为后续段
    now -- 本段开始时刻
    Return arguments:
    None
    """
    from Script.Design import character_behavior
    from Script.Settle import default, realtime_settle, sleep_settle

    end = game_time.get_sub_date(minute=minutes, old_date=now)
    if continued:
        changes = game_type.CharacterStatusChange()
        default.handle_add_small_sanity_point(character_id, minutes, changes, end)
        default.handle_add_small_semen_point(character_id, minutes, changes, end)
    else:
        character_behavior.judge_character_status(character_id)
    realtime_settle.character_aotu_change_value(character_id, end, now)
    if character_id == 0 and not continued:
        sleep_settle.update_sleep()


class Scheduler:
    """本局的行动调度器：pending 为角色id到待办的字典，after_input 为玩家回到输入前要执行的接续"""

    def __init__(self):
        """
        建立空调度器，并为在队 NPC 建立待办
        Return arguments:
        None
        """
        self.pending: dict[int, Entry] = {}
        self.running = False
        self.after_input: Optional[Callable[[], None]] = None
        self.sync_characters()

    def put(self, character_id: int, entry: Entry):
        """
        写入角色的待办，替换其原有待办；同时刻同优先级时后写入的排在后面
        Keyword arguments:
        character_id -- 角色id
        entry -- 待办
        Return arguments:
        None
        """
        self.pending.pop(character_id, None)
        self.pending[character_id] = entry

    def force(self, character_id: int, action: Action, after: Optional[Callable[[], None]] = None):
        """
        让角色此刻立即执行行动；角色已有立即待办时，排在它完成之后
        Keyword arguments:
        character_id -- 角色id
        action -- 行动
        after -- 行动完成后的收尾回调
        Return arguments:
        None
        """
        entry = self.pending.get(character_id)
        if entry is not None and entry.immediate:
            chain_after(entry, lambda: self.force(character_id, action, after))
            return
        self.put(character_id, Entry(cache.game_time, action, True, after))

    def sync_characters(self):
        """
        为没有待办的在队 NPC 建立待办：进行中的行为已在开始时结算，到期后再由 AI 选择
        Return arguments:
        None
        """
        for character_id in sorted(set(cache.npc_id_got) - {0}):
            character = cache.character_data[character_id]
            if character_id in self.pending or character.dead:
                continue
            at = cache.game_time
            behavior = character.behavior
            if behavior.behavior_id != constant.Behavior.SHARE_BLANKLY and behavior.start_time.year > 1:
                at = max(at, behavior_end(behavior))
            self.put(character_id, Entry(at))

    def before(self, character_id: int, entry: Entry):
        """
        执行待办前同步世界：游戏时间设为待办时刻，跨天先日结；回到玩家输入前收尾玩家行为并执行接续，NPC 选择行动前运行行动前检查
        Keyword arguments:
        character_id -- 角色id
        entry -- 待办
        Return arguments:
        None
        """
        from Script.Design import character_behavior, handle_npc_ai
        from Script.Settle import past_day_settle, realtime_settle

        cache.game_time = entry.at
        if cache.pre_game_time.date() != entry.at.date():
            past_day_settle.update_new_day()
            self.sync_characters()
        is_input = character_id == 0 and entry.action is None
        # 随时间到期的状态按待办时刻结算：回到玩家输入前结算全员，其余待办结算本人
        for now_id in ({0} | cache.npc_id_got) if is_input else (character_id,):
            realtime_settle.change_character_persistent_state(now_id)
        if is_input:
            if cache.character_data[0].behavior.behavior_id != constant.Behavior.SHARE_BLANKLY:
                character_behavior.judge_character_status_time_over(0, entry.at, end_now=2)
            realtime_settle.judge_pl_real_time_data()
            # 接续可能再推进时间，此时会写入玩家的立即待办，本次输入让位
            callback, self.after_input = self.after_input, None
            if callback is not None:
                callback()
        elif character_id and entry.action is None:
            if character_id not in cache.npc_id_got or cache.character_data[character_id].dead:
                # 离队或死亡的角色退出队列，归队时由同步重新加入
                self.pending.pop(character_id, None)
                return
            # 行动前检查以玩家本次行动的开始时刻为基准，与旧主循环一致
            handle_npc_ai.run_npc_pre_behavior_checks(character_id, cache.character_data[0].behavior.start_time)

    def decide(self, character_id: int) -> Optional[Action]:
        """
        轮到 NPC 自己选择时决定行动：先续睡、续等和走完未完的行为，到期的行为先收尾，再交给 NPC AI
        Keyword arguments:
        character_id -- 角色id
        Return arguments:
        Action | None -- 行动；AI 的状态机为该角色写入了立即待办时返回 None，本次让位
        """
        from Script.Design import character_behavior, handle_npc_ai

        now = cache.game_time
        character = cache.character_data[character_id]
        behavior = character.behavior
        # 睡眠按计划分段
        if behavior.behavior_id == constant.Behavior.SLEEP and can_continue_sleep(character_id, now):
            return continue_current(character, min(SLEEP_CHUNK_MINUTES, minutes_between(now, behavior.plan_end_time)))
        # 等待对方的双人行为：对方仍在对自己做该行为时，再等一段
        if behavior.behavior_id == constant.Behavior.WAIT and behavior.wait_on_behavior_id:
            owner = cache.character_data.get(character.target_character_id)
            if owner is not None and owner.behavior.behavior_id == behavior.wait_on_behavior_id and owner.target_character_id == character_id:
                return continue_current(character, wait_slice(minutes_between(now, behavior_end(owner.behavior))))
        finished_id = behavior.behavior_id
        if behavior.behavior_id != constant.Behavior.SHARE_BLANKLY:
            remaining = minutes_between(now, behavior_end(behavior))
            if remaining > 0:
                # 别人此刻写入的移动要结算才真正走动
                if behavior.behavior_id == constant.Behavior.MOVE and behavior.start_time >= now:
                    return Action.of(character)
                # H 中或木头人的等待由行动前检查写成"等到玩家本次行动结束"，分段复查
                if behavior.behavior_id == constant.Behavior.WAIT and (character.sp_flag.is_h or character.hypnosis.blockhead):
                    return continue_current(character, wait_slice(remaining))
                # 其余写入或已开始的行为只走完剩余时间
                return continue_current(character, remaining)
            character_behavior.judge_character_status_time_over(character_id, now, end_now=2)
        # 受限状态下等待到期后继续等待，定期复查
        if finished_id == constant.Behavior.WAIT and (character.sp_flag.is_h or character.hypnosis.blockhead):
            return wait_action(character.target_character_id, WAIT_RECHECK_MINUTES, continued=True)
        character.behavior.start_time = now
        handle_npc_ai.find_character_target(character_id, now)
        # 状态机（如撞见 H 的面板）可能已为本角色写入立即待办
        entry = self.pending.get(character_id)
        if entry is not None and entry.immediate:
            return None
        # 只更新需求的状态机保持闲置，按原节奏等待后再选择
        if character.behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
            return wait_action(character_id, WAIT_RECHECK_MINUTES)
        return Action.of(character)

    def execute(self, character_id: int, action: Action) -> Optional[float]:
        """
        把行动写成角色的行为并结算
        Keyword arguments:
        character_id -- 角色id
        action -- 行动
        Return arguments:
        float | None -- 占用的分钟数；行动前置结算为该角色写入了立即待办时返回 None，本次让位
        """
        from Script.Design import character_behavior, handle_npc_ai, handle_npc_ai_in_h, handle_talent, handle_premise
        from Script.Settle import realtime_settle
        from Script.System.Education_System import class_ai

        character = cache.character_data[character_id]
        if character.dead or (character_id and character_id not in cache.npc_id_got):
            return action.behavior.duration
        now = cache.game_time
        action.apply(character, now)
        behavior_id = character.behavior.behavior_id
        if character_id == 0 and not action.continued:
            # 玩家行动开始时检查工作、娱乐中的角色是否到了淋浴时间
            if not cache.time_stop_mode:
                for npc_id in cache.npc_id_got:
                    entry = self.pending.get(npc_id)
                    if entry is not None and not entry.immediate and handle_premise.handle_action_work_or_entertainment(npc_id) and handle_npc_ai.judge_interrupt_character_behavior(npc_id):
                        self.put(npc_id, Entry(now))
            cache.daily_intsruce += character_behavior.character_instruct_record(0)
            cache.pl_pre_behavior_instruce.append(behavior_id)
            cache.pl_pre_behavior_instruce[:] = cache.pl_pre_behavior_instruce[-10:]
            if behavior_id in {constant.Behavior.MOVE, constant.Behavior.CARRY_MOVE}:
                # 同场景 NPC 的跟随与被携带角色的同步移动，并重置全员的目击玩家H
                handle_npc_ai.judge_same_position_npc_follow()
                for npc_id in cache.npc_id_got:
                    cache.character_data[npc_id].sp_flag.see_pl_h = False
            character_behavior.judge_before_pl_behavior()
        entry = self.pending.get(character_id)
        if entry is not None and entry.immediate:
            return None
        if character_id:
            # 学生岗赶去上课：整段行动在开始时一次结算，故在结算前截到应离开的时刻
            leave_time = class_ai.get_student_leave_time(character_id)
            if leave_time is not None:
                character.behavior.duration = max(1, int(minutes_between(now, leave_time)))
        duration = character.behavior.duration
        end = game_time.get_sub_date(minute=duration, old_date=now)
        if behavior_id == constant.Behavior.SLEEP:
            settle_sleep(character_id, duration, action.continued, now)
        else:
            # 延续片段只结算经过时间，一次性效果由首段结算
            if not action.continued:
                character_behavior.judge_character_status(character_id)
            realtime_settle.character_aotu_change_value(character_id, end, now)
        if character_id == 0:
            handle_npc_ai.judge_character_tired_sleep(0)
            handle_npc_ai_in_h.judge_character_h_obscenity_unconscious(0, now)
            realtime_settle.judge_pl_real_time_data()
        handle_talent.gain_talent(character_id, now_gain_type=0)
        # NPC 自己的结算把行为改写成此刻开始的移动（如撞见 H 后离开）时，此刻由 AI 按新移动结算
        if (
            character_id
            and character_id not in self.pending
            and behavior_id != constant.Behavior.MOVE
            and character.behavior.behavior_id == constant.Behavior.MOVE
            and character.behavior.start_time >= now
        ):
            self.put(character_id, Entry(now))
        # 时停中的玩家行动不占用时间，体力消耗仍按行动时长结算
        if character_id == 0 and cache.time_stop_mode:
            cache.achievement.time_stop_duration += duration
            return 0
        return duration

    def run_until_input(self):
        """
        按时刻先后执行待办，直到轮到玩家输入
        Return arguments:
        None
        """
        while True:
            # 立即待办最先，其次按时刻，同一时刻玩家优先
            character_id, entry = min(self.pending.items(), key=lambda item: (not item[1].immediate, item[1].at, item[0] != 0))
            self.before(character_id, entry)
            # 执行前的维护可能替换或撤销了这条待办
            if self.pending.get(character_id) is not entry:
                continue
            del self.pending[character_id]
            if character_id == 0 and entry.action is None:
                return
            action = entry.action or self.decide(character_id)
            minutes = None if action is None else self.execute(character_id, action)
            if minutes is None:
                # 让位给新写入的立即待办，收尾回调排在它之后
                chain_after(self.pending[character_id], entry.after)
                continue
            if entry.after is not None:
                entry.after()
            if character_id not in self.pending:
                self.put(character_id, Entry(game_time.get_sub_date(minute=minutes, old_date=entry.at)))

    def advance(self, minutes: int):
        """
        执行玩家已写好的行动并推进时间，直到再次轮到玩家输入；结算过程中被调用时，改为让玩家立即执行该行动
        Keyword arguments:
        minutes -- 玩家行动的分钟数
        Return arguments:
        None
        """
        from Script.Core import py_cmd
        from Script.Core.get_text import _
        from Script.Settle import sleep_settle
        from Script.System.Field_Commission_System import field_commission_function
        from Script.UI.Panel import achievement_panel

        action = Action.of(cache.character_data[0])
        action.behavior.duration = max(minutes, 1)
        if self.running:
            self.force(0, action)
            return
        self.sync_characters()
        self.put(0, Entry(cache.game_time, action, True))
        self.running = True
        web = getattr(cache, "web_mode", False)
        if web:
            from Script.Core import web_server

            # 开始记录文本（用于Web模式文本回溯），并通知前端显示结算提示
            cache.web_text_recording_flag = True
            web_server.emit_settlement_status(True)
        try:
            self.run_until_input()
            field_commission_function.update_field_commission()
            # 玩家睡觉存档
            if cache.pl_sleep_save_flag:
                cache.pl_sleep_save_flag = False
                sleep_settle.update_save()
            achievement_panel.achievement_flow(_("时停"))
            achievement_panel.achievement_flow(_("群交"))
            py_cmd.focus_cmd()
        finally:
            self.running = False
            if web:
                cache.web_text_recording_flag = False
                web_server.emit_settlement_status(False)


def chain_after(entry: Entry, callback: Optional[Callable[[], None]]):
    """
    在待办原有的收尾回调之后追加一个回调
    Keyword arguments:
    entry -- 待办
    callback -- 追加的回调，为 None 时不做任何事
    Return arguments:
    None
    """
    if callback is None:
        return
    previous = entry.after
    if previous is None:
        entry.after = callback
    else:
        entry.after = lambda: (previous(), callback())


def get_scheduler() -> Scheduler:
    """
    取本局的调度器，首次使用时按角色当前行为建立
    Return arguments:
    Scheduler -- 调度器
    """
    global _scheduler
    if _scheduler is None:
        _scheduler = Scheduler()
    return _scheduler


def reset():
    """
    新开局或读档后丢弃调度器，首次推进时重建
    Return arguments:
    None
    """
    global _scheduler
    _scheduler = None


def submit_current(character_id: int, after: Optional[Callable[[], None]] = None):
    """
    让角色立即执行身上已写好的行为
    Keyword arguments:
    character_id -- 角色id
    after -- 行动完成后的收尾回调
    Return arguments:
    None
    """
    get_scheduler().force(character_id, Action.of(cache.character_data[character_id]), after)


def continue_after_input(callback: Callable[[], None]):
    """
    登记玩家本次行动结束、回到输入之前执行的接续（如分段寻路的下一段）
    Keyword arguments:
    callback -- 无参回调
    Return arguments:
    None
    """
    get_scheduler().after_input = callback


def replan(character_id: int):
    """
    别人改写了 NPC 的行为后，让它从此刻起按新行为执行；不打断此刻的其他行动
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    None
    """
    get_scheduler().put(character_id, Entry(cache.game_time))


def reset_character(character_id: int):
    """
    角色上下线时重排待办：离队者撤销，在队者按当前行为重新入队
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    None
    """
    if _scheduler is None:
        return
    _scheduler.pending.pop(character_id, None)
    if character_id in cache.npc_id_got:
        _scheduler.sync_characters()


def wait_on(character_id: int, owner_id: int, behavior_id: str):
    """
    让参与者等待主体的双人行为：NPC 分段复查，主体只是在等待时陪等其时长；玩家等完全程
    Keyword arguments:
    character_id -- 参与者id
    owner_id -- 主体id
    behavior_id -- 主体的行为id
    Return arguments:
    None
    """
    if cache.time_stop_mode:
        return
    scheduler = get_scheduler()
    source = cache.character_data[owner_id].behavior
    remaining = minutes_between(cache.game_time, behavior_end(source))
    if character_id == 0:
        scheduler.force(0, wait_action(owner_id, max(remaining, 1)))
        return
    # NPC 的等待只替换其待办，和旧代码的直接写入一样不结算一次性效果
    if behavior_id == constant.Behavior.WAIT:
        action = wait_action(owner_id, source.duration, continued=True)
    else:
        action = wait_action(owner_id, wait_slice(remaining), continued=True, wait_on_behavior_id=behavior_id)
    scheduler.put(character_id, Entry(cache.game_time, action))
