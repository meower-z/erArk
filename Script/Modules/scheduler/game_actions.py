"""将游戏行动接入调度器；界面负责获取玩家输入。"""

from collections import deque
from functools import partial

from Script.Core import cache_control, constant, game_type
from Script.Modules.scheduler.action import Action, CONTINUED, STATE
from Script.Modules.scheduler import AI, INPUT, Scheduler, Task

_runtime = None
""" 本局的行动执行器；不随存档保存，读档或新开局后重建 """


def settle_sleep(actor: int, duration: float, continued: bool, now):
    """输入角色编号、分钟数、延续标志及开始时刻 datetime；结算一段睡眠，返回 None。"""
    from Script.Design import character_behavior, game_time
    from Script.Settle import default, realtime_settle, sleep_settle

    end = game_time.get_sub_date(minute=duration, old_date=now)
    if continued:
        # 延续片段补充睡眠恢复，入睡事件和口上由首次片段处理。
        changes = game_type.CharacterStatusChange()
        default.handle_add_small_sanity_point(actor, duration, changes, end)
        default.handle_add_small_semen_point(actor, duration, changes, end)
    else:
        character_behavior.judge_character_status(actor)
    # 每段睡眠都按实际时长结算体力等随时间变化的数值。
    realtime_settle.character_aotu_change_value(actor, end, now)
    if actor == 0 and not continued:
        sleep_settle.update_sleep()


def reset():
    """新开局或读档后丢弃执行器，队列从角色当前行为重建；无参数，返回 None。"""
    global _runtime
    _runtime = None


def get_runtime():
    """返回当前游戏的行动执行器，首次使用时从角色状态建立队列。"""
    global _runtime
    if _runtime is None:
        _runtime = Runtime()
    return _runtime


def submit_current(actor: int, after=None):
    """把角色已写好的行为作为强制后续立即安排；after 为完成后的收尾标记，返回 None。"""
    runtime = get_runtime()
    runtime.force(actor, Action.from_character(cache_control.cache.character_data[actor]))
    if after is not None:
        runtime.force(actor, partial(runtime.finish_action, actor, after))


def reset_character(actor: int):
    """角色上下线时重排待办：离队者撤销，在队者按当前行为重新入队；输入角色编号，返回 None。"""
    if _runtime is None:
        return
    _runtime.scheduler.cancel(actor)
    if actor in cache_control.cache.npc_id_got:
        _runtime.sync_characters()


def replan(actor: int):
    """他人改写了 NPC 的行为后，让其从现在起按新行为执行；这是普通待办，不打断当前时刻的其他行动。输入角色编号，返回 None。"""
    runtime = get_runtime()
    runtime.scheduler.replace(Task(actor, runtime.scheduler.now, AI))


def wait_on(actor: int, owner: int, behavior_id: str):
    """让参与者等待主体的双人行为；NPC 每五分钟复查一次，玩家等完全程。参数均为编号，返回 None。"""
    cache = cache_control.cache
    if cache.time_stop_mode:
        return
    runtime = get_runtime()
    params = {STATE: constant.CharacterStatus.STATUS_WAIT}
    if actor:
        # NPC 的等待只是替换其待办，不算强制打断；和旧代码的直接写入一样不结算一次性效果。
        params["wait_on_behavior_id"] = behavior_id
        params[CONTINUED] = True
        runtime.scheduler.replace(Task(actor, runtime.scheduler.now, Action(constant.Behavior.WAIT, 5, owner, params)))
        return
    from Script.Design import game_time

    source = cache.character_data[owner].behavior
    end = game_time.get_sub_date(minute=source.duration, old_date=source.start_time)
    duration = max(game_time.elapsed_minutes(runtime.scheduler.now, end), 1)
    runtime.force(actor, Action(constant.Behavior.WAIT, duration, owner, params))


class Runtime:
    """保存行动待办，按时刻执行行动并调用结算。"""

    def __init__(self):
        """从当前游戏时刻建立空调度器，无参数，返回 None。"""
        self.scheduler = Scheduler(cache_control.cache.game_time, choose_next=self.choose_next, execute=self.execute, before_task=self.before_task, advance_time=self.advance_time)
        self._forced: dict[int, deque] = {}
        self.sync_characters()

    @staticmethod
    def advance_time(at, minutes):
        """输入开始时刻和分钟数，按游戏季月历法返回结束时刻。"""
        from Script.Design import game_time

        return game_time.get_sub_date(minute=minutes, old_date=at)

    def sync_characters(self):
        """为没有待办的在队 NPC 建立待办：进行中的行为效果已在开始时结算，到期后再自主选择；返回 None。"""
        cache = cache_control.cache
        for actor in sorted(set(cache.npc_id_got) - {0}):
            character = cache.character_data[actor]
            if self.scheduler.contains(actor) or character.dead:
                continue
            at = cache.game_time
            behavior = character.behavior
            if behavior.behavior_id != constant.Behavior.SHARE_BLANKLY and behavior.start_time.year > 1:
                at = max(at, self.advance_time(behavior.start_time, max(behavior.duration, 0)))
            self.scheduler.submit(Task(actor, at, AI))

    def before_task(self, task):
        """按待办时刻同步世界；新日期先日结，玩家输入前收尾其行为，NPC 选择前做行动前检查。输入 Task，返回 None。"""
        from Script.Settle import past_day_settle

        cache = cache_control.cache
        cache.game_time = task.at
        if cache.pre_game_time.date() != task.at.date():
            past_day_settle.update_new_day()
            self.sync_characters()
        if task.item is INPUT:
            from Script.Design import character_behavior

            if cache.character_data[0].behavior.behavior_id != constant.Behavior.SHARE_BLANKLY:
                character_behavior.judge_character_status_time_over(0, task.at, end_now=2)
        elif task.item is AI:
            if task.actor not in cache.npc_id_got or cache.character_data[task.actor].dead:
                # 离队或死亡的角色退出队列，归队时由同步重新加入。
                self.scheduler.cancel(task.actor)
                return
            from Script.Design import handle_npc_ai

            handle_npc_ai.run_npc_pre_behavior_checks(task.actor, task.at)

    def choose_next(self, actor, now):
        """输入 NPC 编号和时刻，返回 AI 选定的行动意图。"""
        from Script.Modules import npc_ai

        return npc_ai.choose_next(actor, now)

    def force(self, actor, item):
        """输入角色编号及强制后续（Action 或无参回调），排在该角色已有的强制后续之后；返回 None。"""
        self._forced.setdefault(actor, deque()).append(item)
        self._dispatch(actor)

    def _dispatch(self, actor):
        """输入角色编号，在其没有立即待办时派发下一条强制后续；回调立即执行，Action 替换其待办。返回 None。"""
        queue = self._forced.get(actor)
        while queue:
            pending = self.scheduler.pending(actor)
            if pending is not None and pending.immediate:
                return
            item = queue.popleft()
            if callable(item):
                item()
            else:
                self.scheduler.replace(Task(actor, self.scheduler.now, item, immediate=True))

    def finish_action(self, actor: int, after):
        """输入角色编号及 str 或 tuple 收尾标记，执行行动完成后的回调；返回 None。"""
        from Script.Design import handle_npc_ai, handle_npc_ai_in_h

        if after == "group_exit":
            handle_npc_ai.finish_group_sex_tired_exit(actor)
        elif isinstance(after, tuple):
            kind, *arguments = after
            if kind == "unconscious_recovery":
                handle_npc_ai_in_h.finish_unconscious_h_recovery(actor, *arguments)
            elif kind in {"discoverer_join", "discoverer_end"}:
                from Script.System.Sex_System import sex_be_discovered_panel

                callback = sex_be_discovered_panel.finish_discovered_join if kind == "discoverer_join" else sex_be_discovered_panel.finish_discovered_end
                callback(actor)

    def execute(self, actor, action) -> float:
        """输入角色和行动意图，安装行为并结算效果；返回占用的分钟数 float。"""
        from Script.Design import character_behavior, handle_npc_ai, handle_npc_ai_in_h, handle_talent, handle_premise
        from Script.Settle import realtime_settle
        from Script.Modules.scheduler.action_execution import prepare_action

        cache = cache_control.cache
        character = cache.character_data[actor]
        if character.dead or (actor and actor not in cache.npc_id_got):
            return action.duration
        now = self.scheduler.now
        action = prepare_action(self, actor, action)
        action.apply(character, now)
        if actor == 0 and not action.continued:
            # 玩家行动开始时检查工作、娱乐角色的洗澡条件。
            if not cache.time_stop_mode:
                for npc_id in cache.npc_id_got:
                    pending = self.scheduler.pending(npc_id)
                    if pending is not None and not pending.immediate and handle_premise.handle_action_work_or_entertainment(npc_id) and handle_npc_ai.judge_interrupt_character_behavior(npc_id):
                        self.scheduler.replace(Task(npc_id, now, AI))
            cache.daily_intsruce += character_behavior.character_instruct_record(actor)
            cache.pl_pre_behavior_instruce.append(action.behavior_id)
            cache.pl_pre_behavior_instruce[:] = cache.pl_pre_behavior_instruce[-10:]
            if action.behavior_id in {constant.Behavior.MOVE, constant.Behavior.CARRY_MOVE}:
                handle_npc_ai.judge_same_position_npc_follow()
                for npc_id in cache.npc_id_got:
                    cache.character_data[npc_id].sp_flag.see_pl_h = False
            character_behavior.judge_before_pl_behavior()
        # 准备阶段（状态机、行动前置面板）为本角色排入了立即待办时，本次行动让位，由该待办结算一次。
        replaced = self.scheduler.pending(actor)
        if replaced is not None and replaced.immediate:
            return 0
        end = self.advance_time(now, action.duration)
        if action.behavior_id == constant.Behavior.SLEEP:
            settle_sleep(actor, action.duration, action.continued, now)
        else:
            # 延续片段只结算经过时间，一次性效果由首段结算。
            if not action.continued:
                character_behavior.judge_character_status(actor)
            realtime_settle.character_aotu_change_value(actor, end, now)
        realtime_settle.change_character_persistent_state(actor)
        if actor == 0:
            handle_npc_ai.judge_character_tired_sleep(actor)
            handle_npc_ai_in_h.judge_character_h_obscenity_unconscious(actor, now)
            realtime_settle.judge_pl_real_time_data()
        handle_talent.gain_talent(actor, now_gain_type=0)
        # 结算中登记的强制后续先于调度器的自动安排。
        self._dispatch(actor)
        # 时停操作占用零分钟，体力消耗按行动时长结算。
        if actor == 0 and cache.time_stop_mode:
            cache.achievement.time_stop_duration += action.duration
            return 0
        return action.duration

    def advance(self, minutes):
        """提交界面准备的玩家行动并运行至输入；minutes 为声明时长，返回 None。"""
        from Script.Core import py_cmd
        from Script.Settle import sleep_settle
        from Script.System.Field_Commission_System import field_commission_function
        from Script.UI.Panel import achievement_panel
        from Script.Core.get_text import _

        cache = cache_control.cache
        action = Action.from_character(cache.character_data[0])
        action.duration = max(minutes, 1)
        if self.scheduler.running:
            self.force(0, action)
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
