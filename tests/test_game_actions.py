"""以真实 Action 和 Scheduler 检查游戏接入的执行顺序。"""

from datetime import datetime, timedelta
import importlib
import pickle
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from Script.Modules.action import Action
from Script.Modules.scheduler import AI, INPUT, Task


class Behavior:
    """测试中的旧行为记录，保留行动接入需要的字段。"""

    def __init__(self):
        """无需参数，初始化空闲行为；无返回值。"""
        self.behavior_id = "idle"
        self.duration = 0
        self.start_time = datetime.min


class GameActionsTests(unittest.TestCase):
    """只替换游戏外围效果，保留调度与动作接入的真实调用。"""

    def setUp(self):
        """无需参数，建立可记录调用的轻量游戏环境；无返回值。"""
        self.now = datetime(2026, 3, 1, 10)
        self.events = []
        self.characters = {
            actor: SimpleNamespace(
                behavior=Behavior(), target_character_id=actor, state="idle", dead=False, sp_flag=SimpleNamespace(see_pl_h=False, is_h=False), hypnosis=SimpleNamespace(blockhead=False)
            )
            for actor in (0, 1)
        }
        self.cache = SimpleNamespace(
            game_time=self.now,
            pre_game_time=self.now,
            character_data=self.characters,
            npc_id_got={1},
            action_scheduler=None,
            daily_intsruce=0,
            pl_pre_behavior_instruce=[],
            time_stop_mode=False,
            achievement=SimpleNamespace(time_stop_duration=0),
            pl_sleep_save_flag=False,
        )
        modules = {}
        for name in ("Script.Core", "Script.Design", "Script.Settle", "Script.System", "Script.System.Field_Commission_System", "Script.UI", "Script.UI.Panel"):
            modules[name] = ModuleType(name)
            modules[name].__path__ = []

        def module(name, **values):
            """输入模块名与公开属性，创建外围替身并返回模块。"""
            result = ModuleType(name)
            result.__dict__.update(values)
            modules[name] = result
            return result

        behaviors = SimpleNamespace(SHARE_BLANKLY="idle", WAIT="wait", REST="rest", SLEEP="sleep", MOVE="move", CARRY_MOVE="carry")
        module("Script.Core.constant", Behavior=behaviors, CharacterStatus=SimpleNamespace(STATUS_WAIT="wait"))
        module("Script.Core.cache_control", cache=self.cache)
        module("Script.Core.game_type", Behavior=Behavior, CharacterStatusChange=SimpleNamespace)
        module("Script.Core.py_cmd", focus_cmd=lambda: None)
        module("Script.Core.get_text", _=lambda text: text)
        module(
            "Script.Design.game_time",
            get_sub_date=lambda old_date, minute=0, day=0: old_date + timedelta(minutes=minute, days=day),
            elapsed_minutes=lambda start, end: (end - start).total_seconds() / 60,
        )
        module(
            "Script.Design.character_behavior",
            judge_character_status_time_over=self.finish,
            character_instruct_record=lambda actor: 1,
            judge_before_pl_behavior=lambda: None,
            judge_character_status=lambda actor: self.events.append(("settle", actor, self.characters[actor].behavior.behavior_id)),
        )
        module(
            "Script.Design.handle_npc_ai",
            judge_same_position_npc_follow=lambda: None,
            judge_character_cant_move=lambda actor: None,
            judge_assistant_character=lambda actor: None,
            judge_character_tired_sleep=lambda actor: None,
            finish_group_sex_tired_exit=lambda actor: self.events.append(("group_exit", actor)),
            judge_interrupt_character_behavior=lambda actor: False,
            run_npc_pre_behavior_checks=lambda actor, now: None,
            find_character_target=lambda actor, now: None,
        )
        module(
            "Script.Design.handle_premise",
            handle_tired_le_0=lambda actor: False,
            handle_hp_max=lambda actor: False,
            handle_mp_max=lambda actor: False,
            handle_game_time_is_sleep_time=lambda actor: False,
            handle_self_not_sleep_pills=lambda actor: True,
            handle_drunk_level_0=lambda actor: True,
            handle_assistant_morning_salutation_on=lambda actor: False,
            handle_morning_salutation_flag_0=lambda actor: True,
            handle_action_work_or_entertainment=lambda actor: False,
        )
        module("Script.Design.handle_npc_ai_in_h", judge_character_h_obscenity_unconscious=lambda actor, now: None)
        module("Script.Design.handle_talent", gain_talent=lambda *args, **kwargs: None)
        module(
            "Script.Settle.realtime_settle",
            character_aotu_change_value=lambda actor, end, start: self.events.append(("realtime", actor, (end - start).total_seconds() / 60)),
            change_character_persistent_state=lambda actor: None,
            judge_pl_real_time_data=lambda: None,
        )
        module("Script.Settle.sleep_settle", update_sleep=lambda: self.events.append(("sleep_once", self.characters[0].behavior.duration)), update_save=lambda: None)
        module("Script.Settle.default", handle_add_small_sanity_point=lambda *args: None, handle_add_small_semen_point=lambda *args: None)
        module("Script.Settle.past_day_settle", update_new_day=self.new_day)
        module("Script.System.Field_Commission_System.field_commission_function", update_field_commission=lambda: None)
        module("Script.UI.Panel.achievement_panel", achievement_flow=lambda text: None)
        module("Script.Modules.npc_ai", choose_next=lambda actor, now: Action("wait", 60, actor))
        self.patches = patch.dict(sys.modules, modules)
        self.patches.start()
        self.addCleanup(self.patches.stop)
        import Script.Modules

        npc_patch = patch.object(Script.Modules, "npc_ai", modules["Script.Modules.npc_ai"], create=True)
        npc_patch.start()
        self.addCleanup(npc_patch.stop)
        sys.modules.pop("Script.Modules.game_actions", None)
        self.game = importlib.import_module("Script.Modules.game_actions")

    def finish(self, actor, now, end_now=2):
        """输入角色与收尾时刻，记录收尾并清空旧行为；返回 True。"""
        self.events.append(("finish", actor))
        self.characters[actor].behavior = Behavior()
        return True

    def new_day(self):
        """无需参数，记录日结并更新旧时间；无返回值。"""
        self.events.append(("day", self.cache.game_time))
        self.cache.pre_game_time = self.cache.game_time

    def test_player_sleep_chunks_once_effect_and_total_time(self):
        """无需参数；睡眠拆段但入睡效果一次、总占用不变；无返回值。"""
        runtime = self.game.get_runtime()
        Action("sleep", 65, 0).apply(self.characters[0], self.now)
        runtime.advance(65)
        self.assertEqual(self.cache.game_time, self.now + timedelta(minutes=65))
        self.assertEqual([event for event in self.events if event[:2] == ("realtime", 0)], [("realtime", 0, 30), ("realtime", 0, 30), ("realtime", 0, 5)])
        self.assertEqual(len([event for event in self.events if event[0] == "sleep_once"]), 1)
        self.assertEqual(len([event for event in self.events if event == ("settle", 0, "sleep")]), 1)

    def test_rest_continuation_does_not_repeat_initial_settlement(self):
        """无需参数；休息续段只结算片段效果；无返回值。"""
        runtime = self.game.get_runtime()
        runtime.scheduler.replace(Task(0, self.now, Action("rest", 45, 0), immediate=True))
        self.assertEqual(runtime.scheduler.advance_until_input().at, self.now + timedelta(minutes=45))
        self.assertEqual([event for event in self.events if event[:2] == ("realtime", 0)], [("realtime", 0, 30), ("realtime", 0, 15)])
        self.assertEqual(self.events.count(("settle", 0, "rest")), 1)

    def test_wait_on_checks_owner_before_restoring_ai(self):
        """无需参数；主人行为停止后等待者恢复 AI；无返回值。"""
        runtime = self.game.get_runtime()
        self.characters[0].behavior.behavior_id = "office"
        self.characters[0].target_character_id = 1
        self.game.wait_on(1, 0, "office")
        runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=3), INPUT))
        runtime.scheduler.advance_until_input()
        self.assertEqual(runtime.scheduler.pending(1).at, self.now + timedelta(minutes=5))
        self.characters[0].behavior.behavior_id = "idle"
        runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=6), INPUT))
        runtime.scheduler.advance_until_input()
        self.assertEqual(runtime.scheduler.pending(1).item, AI)
        self.assertEqual(runtime.scheduler.pending(1).at, self.now + timedelta(minutes=65))

    def test_forced_chain_preserves_submission_order(self):
        """无需参数；同角色多个强制后续按提交顺序执行；无返回值。"""
        runtime = self.game.get_runtime()
        runtime.enqueue(1, Action("first", 5, 1))
        runtime.enqueue(1, Action("second", 5, 1))
        runtime.enqueue(1, Action("third", 5, 1))
        runtime.scheduler.submit(Task(0, self.now, INPUT))
        runtime.scheduler.advance_until_input()
        self.assertEqual([event[2] for event in self.events if event[:2] == ("settle", 1)], ["first", "second", "third"])

    def test_new_followup_keeps_previously_submitted_order(self):
        """无需参数；A 中提交 D 时，先前提交的 B、C 仍先执行；无返回值。"""
        runtime = self.game.get_runtime()
        for name in ("A", "B", "C"):
            runtime.enqueue(1, Action(name, 5, 1))
        original = sys.modules["Script.Design.character_behavior"].judge_character_status

        def settle(actor):
            """记录结算，并让 A 额外提交 D；参数为角色编号，返回 None。"""
            original(actor)
            if self.characters[actor].behavior.behavior_id == "A":
                runtime.enqueue(actor, Action("D", 5, actor))

        with patch.object(sys.modules["Script.Design.character_behavior"], "judge_character_status", settle):
            runtime.scheduler.submit(Task(0, self.now, INPUT))
            runtime.scheduler.advance_until_input()
        self.assertEqual([event[2] for event in self.events if event[:2] == ("settle", 1)], ["A", "B", "C", "D"])

    def test_cleanup_keeps_target_changed_by_another_actor(self):
        """无需参数；NPC 改变玩家目标后，输入前收尾保留该目标；无返回值。"""
        runtime = self.game.get_runtime()
        runtime.current[0] = (Behavior(), 0, "idle")
        self.characters[0].target_character_id = 1
        runtime.finish_current(0, self.now)
        self.assertEqual(self.characters[0].target_character_id, 1)

    def test_old_save_resumes_at_behavior_end_without_replaying(self):
        """无需参数；旧档补算剩余时间效果，到期再选行动；无返回值。"""
        self.characters[1].behavior.behavior_id = "office"
        self.characters[1].behavior.start_time = self.now - timedelta(minutes=10)
        self.characters[1].behavior.duration = 60
        self.game.restore(None)
        runtime = self.game.get_runtime()
        self.assertEqual(runtime.scheduler.pending(1).at, self.now)
        self.assertTrue(runtime.scheduler.pending(1).item.continued)
        self.assertEqual(runtime.scheduler.pending(1).item.duration, 50)
        runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=51), INPUT))
        runtime.scheduler.advance_until_input()
        self.assertNotIn(("settle", 1, "office"), self.events)
        self.assertEqual(self.events.count(("realtime", 1, 50)), 1)
        self.assertEqual(runtime.scheduler.pending(1).at, self.now + timedelta(minutes=110))

    def test_pickle_rebinds_callbacks_to_restored_runtime(self):
        """无需参数；存档往返后回调属于新执行器且强制链保留；无返回值。"""
        runtime = self.game.get_runtime()
        runtime.enqueue(1, Action("forced", 5, 0))
        runtime.scheduler._running = True
        runtime.active[0] = "stale"
        restored = pickle.loads(pickle.dumps(runtime))
        self.game.restore(restored)
        self.assertIs(self.game.get_runtime(), restored)
        self.assertFalse(restored.scheduler.running)
        self.assertEqual(restored.active, {})
        self.assertIs(restored.scheduler._execute.__self__, restored)
        self.assertIs(restored.scheduler._choose_next.__self__, restored)
        restored.scheduler.submit(Task(0, self.now, INPUT))
        restored.scheduler.advance_until_input()
        self.assertIn(("settle", 1, "forced"), self.events)

    def test_time_stop_keeps_npc_pending_and_world_time(self):
        """无需参数；时停玩家行动不消耗世界时间也不推进 NPC；无返回值。"""
        self.cache.time_stop_mode = True
        runtime = self.game.get_runtime()
        npc_task = runtime.scheduler.pending(1)
        runtime.scheduler.submit(Task(0, self.now, Action("office", 60, 0), immediate=True))
        self.assertEqual(runtime.scheduler.advance_until_input().at, self.now)
        self.assertEqual(self.cache.game_time, self.now)
        self.assertIs(runtime.scheduler.pending(1), npc_task)
        self.assertEqual(self.cache.achievement.time_stop_duration, 60)

    def test_time_stop_sleep_must_not_advance_npcs(self):
        """无需参数；时停中的睡眠续段也不能推进 NPC 或世界时间；无返回值。"""
        self.cache.time_stop_mode = True
        runtime = self.game.get_runtime()
        npc_task = runtime.scheduler.pending(1)
        runtime.scheduler.submit(Task(0, self.now, Action("sleep", 60, 0), immediate=True))
        self.assertEqual(runtime.scheduler.advance_until_input().at, self.now)
        self.assertEqual(self.cache.game_time, self.now)
        self.assertIs(runtime.scheduler.pending(1), npc_task)

    def test_npc_recovery_uses_real_ai_to_continue(self):
        """无需参数；真实 AI 在片段边界延续未恢复的计划；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        import Script.Modules

        with patch.object(Script.Modules, "npc_ai", npc_ai):
            runtime = self.game.get_runtime()
            runtime.scheduler.replace(Task(1, self.now, Action("rest", 65, 1), immediate=True))
            runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=61), INPUT))
            runtime.scheduler.advance_until_input()
        self.assertEqual([event for event in self.events if event[:2] == ("realtime", 1)], [("realtime", 1, 30), ("realtime", 1, 30), ("realtime", 1, 5)])
        self.assertEqual(self.events.count(("settle", 1, "rest")), 1)

    def test_locked_wait_is_silent_and_checks_every_five_minutes(self):
        """无需参数；H 中等待每五分钟检查，跳过普通动作口上；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        import Script.Modules

        self.characters[1].sp_flag.is_h = True

        def prepare(actor, now):
            """输入角色与时间，模拟旧检查生成被动等待；返回 None。"""
            Action("wait", 60, actor).apply(self.characters[actor], now)

        with patch.object(Script.Modules, "npc_ai", npc_ai), patch.object(sys.modules["Script.Design.handle_npc_ai"], "run_npc_pre_behavior_checks", prepare):
            runtime = self.game.get_runtime()
            runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=10), INPUT))
            runtime.scheduler.advance_until_input()
        self.assertNotIn(("settle", 1, "wait"), self.events)
        self.assertEqual(self.events.count(("realtime", 1, 5)), 2)

    def test_assistant_wakes_when_chunk_crosses_greeting_time(self):
        """无需参数；助理睡眠跨过问候时刻后不再延续；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        self.characters[0].action_info = SimpleNamespace(plan_to_wake_time=(7, 0))
        start = self.now.replace(hour=6, minute=40)
        Action("sleep", 30, 1).apply(self.characters[1], start)
        self.cache.game_time = start + timedelta(minutes=30)
        with patch.object(sys.modules["Script.Design.handle_premise"], "handle_assistant_morning_salutation_on", lambda actor: True):
            self.assertFalse(npc_ai._continue_recovery(1, Action("sleep", 300, 1)))
            self.cache.game_time = start + timedelta(minutes=10)
            self.assertTrue(npc_ai._continue_recovery(1, Action("sleep", 300, 1)))

    def test_daily_new_character_receives_pending_before_input(self):
        """无需参数；日结招募新角色后，返回输入时该角色已有待办；无返回值。"""
        self.cache.npc_id_got.remove(1)
        runtime = self.game.get_runtime()

        def recruit():
            """无需参数，在日结中加入测试角色；无返回值。"""
            self.new_day()
            self.cache.npc_id_got.add(1)

        with patch.object(sys.modules["Script.Settle.past_day_settle"], "update_new_day", recruit):
            runtime.scheduler.submit(Task(0, self.now + timedelta(days=1), INPUT))
            runtime.scheduler.advance_until_input()
        self.assertIs(runtime.scheduler.pending(1).item, AI)

    def test_new_day_settles_before_first_new_day_action(self):
        """无需参数；日期结算早于新日期第一个行动；无返回值。"""
        runtime = self.game.get_runtime()
        tomorrow = self.now + timedelta(days=1)
        runtime.scheduler.replace(Task(1, tomorrow, Action("office", 60, 1)))
        runtime.scheduler.submit(Task(0, tomorrow + timedelta(minutes=1), INPUT))
        runtime.scheduler.advance_until_input()
        day_index = self.events.index(("day", tomorrow))
        settle_index = self.events.index(("settle", 1, "office"))
        self.assertLess(day_index, settle_index)
        self.assertEqual(len([event for event in self.events if event[0] == "day"]), 1)

    def test_prepared_action_is_not_finished_before_execution(self):
        """无需参数；UI 刚准备的动作只在实际结算之后收尾；无返回值。"""
        runtime = self.game.get_runtime()
        Action("office", 10, 0).apply(self.characters[0], self.now)
        runtime.advance(10)
        self.assertEqual(self.events.count(("finish", 0)), 1)
        self.assertLess(self.events.index(("settle", 0, "office")), self.events.index(("finish", 0)))

    def test_before_hook_submits_successor_without_overwriting_current(self):
        """无需参数；前置钩子提交 B 后，A 仍先完整结算一次；无返回值。"""
        runtime = self.game.get_runtime()

        def before():
            """无需参数，A 的前置钩子准备并提交 B；无返回值。"""
            if self.characters[0].behavior.behavior_id == "first":
                Action("second", 5, 0).apply(self.characters[0], self.now)
                self.game.submit_current(0)

        with patch.object(sys.modules["Script.Design.character_behavior"], "judge_before_pl_behavior", before):
            runtime.scheduler.submit(Task(0, self.now, Action("first", 5, 0), immediate=True))
            runtime.scheduler.advance_until_input()
        self.assertEqual([event[2] for event in self.events if event[:2] == ("settle", 0)], ["first", "second"])
        self.assertEqual(self.events.count(("realtime", 0, 5)), 2)

    def test_time_stop_wait_on_preserves_npc_task_without_recovery(self):
        """无需参数；时停中的双人等待不替换 NPC 待办或增加恢复；无返回值。"""
        runtime = self.game.get_runtime()
        self.cache.time_stop_mode = True
        original = runtime.scheduler.pending(1)
        self.game.wait_on(1, 0, "office")
        self.assertIs(runtime.scheduler.pending(1), original)
        runtime.scheduler.submit(Task(0, self.now, INPUT))
        runtime.scheduler.advance_until_input()
        self.assertFalse(any(event[:2] == ("realtime", 1) for event in self.events))

    def test_time_stop_does_not_interrupt_working_npc(self):
        """无需参数；时停期间工作 NPC 的待办保持原定安排；无返回值。"""
        runtime = self.game.get_runtime()
        self.characters[1].behavior.behavior_id = "office"
        self.characters[1].behavior.duration = 60
        original = runtime.scheduler.pending(1)
        with patch.object(sys.modules["Script.Design.handle_premise"], "handle_action_work_or_entertainment", return_value=True), patch.object(
            sys.modules["Script.Design.handle_npc_ai"], "judge_interrupt_character_behavior", return_value=True
        ):
            self.cache.time_stop_mode = True
            runtime.scheduler.submit(Task(0, self.now, Action("office", 10, 0), immediate=True))
            runtime.scheduler.advance_until_input()
        self.assertIs(runtime.scheduler.pending(1), original)

    def test_wait_on_rejects_changed_owner_target(self):
        """无需参数；等待主体改换目标后，参与者恢复自主选择；无返回值。"""
        runtime = self.game.get_runtime()
        self.characters[0].behavior.behavior_id = "office"
        self.characters[0].target_character_id = 1
        self.game.wait_on(1, 0, "office")
        self.characters[0].target_character_id = 99
        runtime.scheduler.submit(Task(0, self.now, INPUT))
        runtime.scheduler.advance_until_input()
        self.assertIs(runtime.scheduler.pending(1).item, AI)

    def test_recovery_plan_rejects_changed_target(self):
        """无需参数；恢复计划目标改变后重新选择行动；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        import Script.Modules

        with patch.object(Script.Modules, "npc_ai", npc_ai):
            self.cache.npc_id_got.clear()
            runtime = self.game.get_runtime()
            self.cache.npc_id_got.add(1)
            self.characters[1].behavior.behavior_id = "rest"
            self.characters[1].target_character_id = 99
            runtime.plans[1] = Action("rest", 30, 1)
            action = npc_ai.choose_next(1, self.now)
        self.assertFalse(action.continued)

    def test_recovery_ai_returns_one_chunk(self):
        """无需参数；恢复计划的下一行动占用一个三十分钟片段；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        self.cache.npc_id_got.clear()
        runtime = self.game.get_runtime()
        self.characters[1].behavior.behavior_id = "rest"
        runtime.plans[1] = Action("rest", 65, 1)

        action = npc_ai.choose_next(1, self.now)

        self.assertEqual((action.behavior_id, action.duration, action.target), ("rest", 30, 1))
        self.assertTrue(action.continued)

    def test_fallback_wait_keeps_five_minute_interval(self):
        """无需参数；空闲 NPC 的回退等待保持五分钟；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        import Script.Modules

        with patch.object(Script.Modules, "npc_ai", npc_ai):
            self.cache.npc_id_got.clear()
            self.game.get_runtime()
            self.characters[1].behavior.behavior_id = "idle"
            action = npc_ai.choose_next(1, self.now)
        self.assertEqual(action.duration, 5)

    def test_player_wait_end_returns_input_without_npc_ai(self):
        """无需参数；玩家等待的主体已停止时直接返回输入；无返回值。"""
        runtime = self.game.get_runtime()
        self.game.wait_on(0, 1, "office")
        result = runtime.scheduler.advance_until_input()
        self.assertEqual(result.actor, 0)
        self.assertIs(result.item, INPUT)
        self.assertEqual(result.at, self.now)
        self.assertFalse(any(event[:2] == ("realtime", 0) for event in self.events))

    def test_offline_online_drops_old_action_and_recovery_plan(self):
        """无需参数；离队期间无效果，上线立即自主选择且不恢复旧睡眠；无返回值。"""
        runtime = self.game.get_runtime()
        old = Action("sleep", 30, 1, continued=True)
        old.apply(self.characters[1], self.now)
        runtime.current[1] = (self.characters[1].behavior, 1, "sleep")
        runtime.plans[1] = old
        runtime.scheduler.replace(Task(1, self.now + timedelta(minutes=30), old))
        self.cache.npc_id_got.remove(1)
        self.game.reset_character(1)
        runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=5), INPUT))
        runtime.scheduler.advance_until_input()
        self.assertFalse(any(event[:2] == ("realtime", 1) for event in self.events))
        self.assertNotIn(1, runtime.current)
        self.assertNotIn(1, runtime.plans)

        self.cache.npc_id_got.add(1)
        self.characters[1].behavior = Behavior()
        self.game.reset_character(1)
        runtime.scheduler.submit(Task(0, runtime.scheduler.now + timedelta(minutes=31), INPUT))
        with patch.object(runtime.scheduler, "_choose_next", return_value=Action("office", 60, 1)):
            runtime.scheduler.advance_until_input()
        self.assertEqual([event for event in self.events if event[:2] == ("settle", 1)], [("settle", 1, "office")])
        self.assertNotIn(("realtime", 1, 30), self.events)

    def test_actor_going_offline_during_action_has_no_old_successor(self):
        """无需参数；结算中离队撤销已排后续，之后上线重新选择；无返回值。"""
        runtime = self.game.get_runtime()

        def leave(actor):
            """输入当前执行者，模拟离队效果并清理调度计划；返回 None。"""
            runtime.enqueue(actor, Action("must_not_run", 10, actor))
            self.cache.npc_id_got.remove(actor)
            self.game.reset_character(actor)

        runtime.scheduler.replace(Task(1, self.now, Action("leave", 10, 1)))
        runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=5), INPUT))
        with patch.object(sys.modules["Script.Design.character_behavior"], "judge_character_status", leave):
            runtime.scheduler.advance_until_input()
        self.assertIs(runtime.scheduler.pending(1).item, AI)
        self.assertEqual([event for event in self.events if event[:2] == ("realtime", 1)], [("realtime", 1, 10)])
        self.assertNotIn(1, runtime.current)
        self.cache.npc_id_got.add(1)
        self.game.reset_character(1)
        self.assertNotIn(1, runtime.current)
        self.assertEqual(runtime.scheduler.pending(1).at, runtime.scheduler.now)


if __name__ == "__main__":
    unittest.main()
