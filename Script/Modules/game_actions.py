"""把旧行动实现接入调度器；界面继续负责获取玩家输入。"""

from copy import deepcopy
from dataclasses import replace

from Script.Core import cache_control, constant, game_type
from Script.Modules.action import Action
from Script.Modules.scheduler import AI, INPUT, Scheduler, Task


def reset():
    """新游戏清除旧调度状态，无参数，返回 None。"""
    cache_control.cache.action_scheduler = None


def restore(saved_runtime):
    """读档安装保存的调度状态；旧档传 None，返回 None。"""
    cache_control.cache.action_scheduler = saved_runtime
    if saved_runtime is not None:
        saved_runtime.scheduler._running = False
        saved_runtime.active = {}


def get_runtime():
    """返回当前游戏的行动执行器，首次使用时从角色状态建立队列。"""
    cache = cache_control.cache
    runtime = getattr(cache, "action_scheduler", None)
    if runtime is None:
        runtime = Runtime()
        cache.action_scheduler = runtime
    return runtime


def submit_current(actor, *, after=None):
    """将角色已选行为作为立即后续提交；actor 为角色编号，返回 None。"""
    runtime = get_runtime()
    action = Action.from_character(cache_control.cache.character_data[actor])
    action.after = after
    runtime.enqueue(actor, action)
    # 后续意图已独立保存，当前动作的剩余效果继续读取当前动作。
    if actor in runtime.active:
        character = cache_control.cache.character_data[actor]
        character.behavior, character.target_character_id, character.state = deepcopy(runtime.active[actor])


def reset_character(actor):
    """角色上下线时清除旧行动计划与待办；输入角色编号，返回 None。"""
    runtime = getattr(cache_control.cache, "action_scheduler", None)
    if runtime is None:
        return
    runtime.plans.pop(actor, None)
    runtime.current.pop(actor, None)
    runtime.known.add(actor)
    runtime.scheduler.replace(Task(actor, runtime.scheduler.now, INPUT if actor == 0 else AI))


def wait_on(actor, owner, behavior_id):
    """替换参与者的待办，等待主体的指定双人行为；参数均为编号，返回 None。"""
    if cache_control.cache.time_stop_mode:
        return
    runtime = get_runtime()
    action = Action(constant.Behavior.WAIT, 5, owner, state=constant.CharacterStatus.STATUS_WAIT, wait_on=(owner, behavior_id))
    runtime.plans.pop(actor, None)
    runtime.scheduler.replace(Task(actor, runtime.scheduler.now, action, immediate=True))


class Runtime:
    """持久保存行动计划和待办，旧实现仅通过此处执行。"""

    def __init__(self):
        """从当前游戏时刻建立空调度器，无参数，返回 None。"""
        cache = cache_control.cache
        self.plans = {}
        self.active = {}
        self.current = {}
        self.scheduler = Scheduler(cache.game_time, choose_next=self.choose_next, execute=self.execute, before_task=self.before_task, advance_time=self.advance_time)
        self.known = set()
        self.sync_characters()

    @staticmethod
    def advance_time(at, minutes):
        """输入开始时刻和分钟数，返回保留旧季月规则的结束时刻。"""
        from Script.Design import game_time

        return game_time.get_sub_date(minute=minutes, old_date=at)

    def sync_characters(self):
        """为新参与角色建立一个待办，旧进行中行为不重放主效果；返回 None。"""
        from Script.Design import game_time

        cache = cache_control.cache
        for actor in sorted(set(cache.npc_id_got) - {0} - self.known):
            if self.scheduler.contains(actor):
                self.known.add(actor)
                continue
            character = cache.character_data[actor]
            at = cache.game_time
            item = AI
            behavior = character.behavior
            if behavior.behavior_id != constant.Behavior.SHARE_BLANKLY and behavior.start_time.year > 1:
                end = self.advance_time(behavior.start_time, max(behavior.duration, 0))
                self.current[actor] = (deepcopy(behavior), character.target_character_id, character.state)
                # 旧档已结算主效果，仅将尚未结算的时间恢复转换为一个延续片段。
                if end > at:
                    at = max(at, behavior.start_time)
                    item = replace(Action.from_character(character), duration=game_time.elapsed_minutes(at, end), continued=True)
                    if behavior.behavior_id in {constant.Behavior.SLEEP, constant.Behavior.REST}:
                        self.plans[actor] = deepcopy(item)
            self.scheduler.submit(Task(actor, at, item))
            self.known.add(actor)

    def before_task(self, task):
        """按待办时刻同步世界，进入新日期时先日结；输入 Task，返回 None。"""
        from Script.Settle import past_day_settle

        cache = cache_control.cache
        cache.game_time = task.at
        if cache.pre_game_time.date() != task.at.date():
            past_day_settle.update_new_day()
            self.sync_characters()
        if task.item == INPUT:
            self.finish_current(task.actor, task.at)

    def finish_current(self, actor, now):
        """在行动到期或被替换时调用原有收尾，保留 Behavior 字段；返回 None。"""
        from Script.Design import character_behavior

        character = cache_control.cache.character_data[actor]
        previous = self.current.pop(actor, None)
        if previous is not None:
            character.behavior = previous[0]
            character_behavior.judge_character_status_time_over(actor, now, end_now=2)

    def choose_next(self, actor, now):
        """输入 NPC 编号和时刻，委托 AI 模块返回 Action 或已提交的 None。"""
        from Script.Modules import npc_ai

        cache = cache_control.cache
        if actor not in cache.npc_id_got or cache.character_data[actor].dead:
            # 离队者不调用 AI；保留一个不会产出效果的等待席位。
            return Action(constant.Behavior.WAIT, 60, actor, continued=True)
        return npc_ai.choose_next(actor, now)

    def enqueue(self, actor, action):
        """输入角色和强制行动，串接同角色立即后续，替换其普通待办；返回 None。"""
        pending = self.scheduler.pending(actor)
        if pending is not None and pending.immediate and isinstance(pending.item, Action):
            pending.item.followups += (action,)
        else:
            self.plans.pop(actor, None)
            self.scheduler.replace(Task(actor, self.scheduler.now, action, immediate=True))

    def execute(self, actor, action):
        """执行一个原子行动，保留旧效果公式并提交后续；输入角色和 Action，返回 None。"""
        from Script.Design import character_behavior, handle_npc_ai, handle_npc_ai_in_h, handle_talent, handle_premise
        from Script.Settle import realtime_settle, sleep_settle, default

        cache = cache_control.cache
        character = cache.character_data[actor]
        if character.dead or (actor and actor not in cache.npc_id_got):
            return
        now = self.scheduler.now
        # 已提交的同角色后续先占位，本次新产生的后续按提交顺序排在它们之后。
        for following in action.followups:
            self.enqueue(actor, following)
        action.followups = ()
        if action.wait_on is not None:
            owner, behavior_id = action.wait_on
            source = cache.character_data.get(owner)
            if source is None or source.behavior.behavior_id != behavior_id or source.target_character_id != actor:
                self.finish_current(actor, now)
                if not self.scheduler.contains(actor):
                    self.scheduler.submit(Task(actor, now, INPUT if actor == 0 else AI))
                return
        if not action.continued:
            self.finish_current(actor, now)
        action.apply(character, now)
        self.active[actor] = (deepcopy(character.behavior), character.target_character_id, character.state)
        recovery = action.behavior_id in {constant.Behavior.REST, constant.Behavior.SLEEP}
        if recovery and not action.continued:
            self.plans[actor] = deepcopy(action)
        try:
            # 首次玩家准备读取完整睡眠计划，保留六小时阈值效果。
            if actor == 0 and not action.continued:
                # 保留旧工作/娱乐的洗澡打断条件；已支付的原子效果不回滚。
                if not cache.time_stop_mode:
                    for npc_id in cache.npc_id_got:
                        pending = self.scheduler.pending(npc_id)
                        if pending is not None and not pending.immediate and handle_premise.handle_action_work_or_entertainment(npc_id) and handle_npc_ai.judge_interrupt_character_behavior(npc_id):
                            self.current.pop(npc_id, None)
                            self.scheduler.replace(Task(npc_id, now, AI))
                cache.daily_intsruce += character_behavior.character_instruct_record(actor)
                cache.pl_pre_behavior_instruce.append(action.behavior_id)
                cache.pl_pre_behavior_instruce[:] = cache.pl_pre_behavior_instruce[-10:]
                if action.behavior_id in {constant.Behavior.MOVE, constant.Behavior.CARRY_MOVE}:
                    handle_npc_ai.judge_same_position_npc_follow()
                    for npc_id in cache.npc_id_got:
                        cache.character_data[npc_id].sp_flag.see_pl_h = False
                character_behavior.judge_before_pl_behavior()
            if recovery:
                action.duration = min(action.duration, 30)
                character.behavior.duration = action.duration
                plan = self.plans.get(actor)
                if plan is not None:
                    plan.duration = max(plan.duration - action.duration, 0)
                self.active[actor][0].duration = action.duration
            end = self.advance_time(now, action.duration)
            if not action.continued and action.wait_on is None:
                character_behavior.judge_character_status(actor)
            elif action.continued and action.behavior_id == constant.Behavior.SLEEP:
                changes = game_type.CharacterStatusChange()
                default.handle_add_small_sanity_point(actor, action.duration, changes, end)
                default.handle_add_small_semen_point(actor, action.duration, changes, end)
            realtime_settle.character_aotu_change_value(actor, end, now)
            if actor == 0 and action.behavior_id == constant.Behavior.SLEEP and not action.continued:
                sleep_settle.update_sleep()
            realtime_settle.change_character_persistent_state(actor)
            if actor == 0:
                handle_npc_ai.judge_character_tired_sleep(actor)
                handle_npc_ai_in_h.judge_character_h_obscenity_unconscious(actor, now)
                realtime_settle.judge_pl_real_time_data()
            handle_talent.gain_talent(actor, now_gain_type=0)
        finally:
            self.active.pop(actor, None)
        if actor == 0 or (actor in cache.npc_id_got and not character.dead):
            self.current[actor] = (deepcopy(character.behavior), character.target_character_id, character.state)
        if action.after == "group_exit":
            handle_npc_ai.finish_group_sex_tired_exit(actor)
        elif isinstance(action.after, tuple):
            kind, *arguments = action.after
            if kind == "unconscious_recovery":
                handle_npc_ai_in_h.finish_unconscious_h_recovery(actor, *arguments)
            elif kind in {"discoverer_join", "discoverer_end"}:
                from Script.System.Sex_System import sex_be_discovered_panel

                callback = sex_be_discovered_panel.finish_discovered_join if kind == "discoverer_join" else sex_be_discovered_panel.finish_discovered_end
                callback(actor)
        if action.wait_on is not None and self.scheduler.pending(actor) is None:
            self.scheduler.submit(Task(actor, end, replace(action, continued=True)))
        # 玩家睡眠按本人计划延续；NPC 在下一次 AI 选择时检查计划。
        plan = self.plans.get(actor)
        if actor == 0 and plan is not None and plan.duration > 0 and character.behavior.behavior_id == action.behavior_id and not cache.time_stop_mode and self.scheduler.pending(actor) is None:
            self.scheduler.submit(Task(actor, end, replace(plan, duration=min(plan.duration, 30), continued=True)))
        if recovery and character.behavior.behavior_id != action.behavior_id:
            self.plans.pop(actor, None)
        # 时停操作的占用时间为零，已计算的体力消耗仍保留。
        if actor == 0 and cache.time_stop_mode:
            cache.achievement.time_stop_duration += action.duration
            action.duration = 0

    def advance(self, minutes):
        """提交旧 UI 准备的玩家行动并运行至输入；minutes 为声明时长，返回 None。"""
        from Script.Core import py_cmd
        from Script.Settle import sleep_settle
        from Script.System.Field_Commission_System import field_commission_function
        from Script.UI.Panel import achievement_panel
        from Script.Core.get_text import _

        cache = cache_control.cache
        action = Action.from_character(cache.character_data[0])
        action.duration = max(minutes, 1)
        if self.scheduler.running:
            self.enqueue(0, action)
            if 0 in self.active:
                character = cache.character_data[0]
                character.behavior, character.target_character_id, character.state = deepcopy(self.active[0])
            return
        self.sync_characters()
        self.scheduler.replace(Task(0, self.scheduler.now, action, immediate=True))
        cache.game_update_flow_running = 1
        cache.over_behavior_character = set()
        web = getattr(cache, "web_mode", False)
        if web:
            from Script.Core import web_server

            cache.web_text_recording_flag = True
            web_server.emit_settlement_status(True)
        try:
            self.scheduler.advance_until_input()
            field_commission_function.update_field_commission()
            if cache.pl_sleep_save_flag:
                cache.pl_sleep_save_flag = False
                sleep_settle.update_save()
            achievement_panel.achievement_flow(_("时停"))
            achievement_panel.achievement_flow(_("群交"))
            py_cmd.focus_cmd()
        finally:
            cache.game_update_flow_running = 0
            if web:
                cache.web_text_recording_flag = False
                web_server.emit_settlement_status(False)
