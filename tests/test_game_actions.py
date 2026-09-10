"""以真实 Action 和 Scheduler 检查游戏接入的执行顺序。"""

from datetime import datetime, timedelta
import ast
import importlib
import pickle
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from Script.Modules.action import Action, ActionProgress
from Script.Modules.scheduler import AI, INPUT, Task
from Script.Modules.npc_actions import state_machine_action


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
        module("Script.Core.game_type", Behavior=Behavior, Cache=SimpleNamespace, CharacterStatusChange=SimpleNamespace)
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
            choose_character_target=lambda actor, now: Action("wait", 5, actor),
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
        module(
            "Script.Design.handle_npc_ai_in_h",
            judge_character_h_obscenity_unconscious=lambda actor, now: None,
            npc_ai_in_group_sex=lambda actor: None,
            execute_group_action=lambda actor, action: None,
        )
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

    def load_real_target_selector(self):
        """无需参数，加载真实目标选择及搜索链，提供最小配置；返回模块。"""
        modules = {}
        for name in (
            "Script.Core.game_path_config",
            "Script.Core.value_handle",
            "Script.Design.instuct_judege",
            "Script.Design.character_move",
            "Script.Design.attr_calculation",
            "Script.Design.map_handle",
            "Script.UI.Moudle",
            "Script.UI.Moudle.draw",
            "Script.Config",
            "Script.Config.game_config",
            "Script.Config.normal_config",
        ):
            modules[name] = ModuleType(name)
            modules[name].__path__ = []
        modules["Script.Core.game_path_config"].game_path = ""
        modules["Script.Core.value_handle"].get_rand_value_for_value_region = lambda values: values[0]
        modules["Script.UI.Moudle.draw"].NormalDraw = SimpleNamespace
        modules["Script.Config.normal_config"].config_normal = SimpleNamespace(text_width=80)
        config = modules["Script.Config.game_config"]
        config.config_target = {1: SimpleNamespace(state_machine_id=77)}
        config.config_target_type_index = {0: [1]}
        config.config_target_premise_data = {}
        patcher = patch.dict(sys.modules, modules)
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules["Script.Design"].__path__ = [str(Path(__file__).resolve().parents[1] / "Script/Design")]
        sys.modules.pop("Script.Design.handle_npc_ai", None)
        selector = importlib.import_module("Script.Design.handle_npc_ai")
        return selector

    def test_real_target_search_returns_intent_without_effects(self):
        """无需参数；真实目标搜索仅返回意图，选择时保持角色和世界状态；无返回值。"""
        selector = self.load_real_target_selector()
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        constant = sys.modules["Script.Core.constant"]
        constant.handle_state_machine_data = {77: lambda actor: self.fail("选择阶段调用了状态机")}
        before = pickle.dumps(self.cache)
        intent = npc_ai.choose_next(1, self.now)
        self.assertIs(type(intent), Action)
        self.assertEqual(intent, state_machine_action(1, 77))
        self.assertEqual(pickle.loads(pickle.dumps(intent)), intent)
        self.assertEqual(pickle.dumps(self.cache), before)
        self.assertEqual(self.events, [])
        self.assertIs(npc_ai.handle_npc_ai, selector)

    def test_action_intent_executes_handler_and_propagates_duration(self):
        """无需参数；选择返回状态机，执行时才写入行动并结算一次；无返回值。"""
        selector = self.load_real_target_selector()
        self.cache.npc_id_got.clear()
        runtime = self.game.get_runtime()
        self.cache.npc_id_got.add(1)
        constant = sys.modules["Script.Core.constant"]

        def handler(actor):
            """输入角色，准备动作并记录执行；返回 None。"""
            self.events.append(("handler", actor))
            Action("work", 17, actor).apply(self.characters[actor], self.now)

        constant.handle_state_machine_data = {77: handler}
        intent = selector.choose_character_target(1, self.now)
        self.assertEqual(self.events, [])
        duration = runtime.execute(1, intent)
        self.assertEqual(self.events.count(("handler", 1)), 1)
        self.assertEqual(self.events.count(("settle", 1, "work")), 1)
        self.assertEqual(duration, 17)

    def test_generic_execution_resolves_group_actions_before_installing_behavior(self):
        """输入真实群体选择，统一执行入口才改模板并安装等待行为；无返回值。"""
        import random

        source = Path(__file__).resolve().parents[1] / "Script/Design/handle_npc_ai_in_h.py"
        tree = ast.parse(source.read_text())
        names = {"npc_ai_in_group_sex", "execute_group_action"}
        tree.body = [node for node in tree.body if getattr(node, "name", None) in names]
        group = ModuleType("_game_group_action_subject")
        group.__dict__.update(
            Action=Action, random=random, cache=self.cache, cache_control=SimpleNamespace(cache=self.cache), constant=sys.modules["Script.Core.constant"], _=lambda text: text,
            handle_premise=SimpleNamespace(
                handle_group_sex_mode_off=lambda actor: False, handle_normal_6=lambda actor, **kw: True,
                handle_npc_ai_type_1_in_group_sex=lambda actor: False, handle_npc_ai_type_2_in_group_sex=lambda actor: True, handle_self_now_bondage=lambda actor: False,
            ),
        )
        with patch.dict(sys.modules, {group.__name__: group}):
            exec(compile(tree, str(source), "exec"), group.__dict__)
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        self.characters[0].h_state = SimpleNamespace(group_sex_body_template_dict={"A": [{"mouth": [-1, -1]}, [[], -1]]})
        self.characters[1].sp_flag.is_h = True
        self.characters[1].sp_flag.masturebate = 3
        panel = SimpleNamespace(count_group_sex_character_list=lambda: [])
        sex_system = ModuleType("Script.System.Sex_System")
        sex_system.group_sex_panel = panel
        runtime = self.game.get_runtime()
        for initial, part, statuses, kind in (
            ("idle", "mouth", (12,), "group_fill"), ("idle", "加入侍奉", (), "group_join"),
            ("wait", "mouth", (12,), "group_fill"), ("wait", "加入侍奉", (), "group_join"),
            ("idle", "mouth", (), "need"), ("wait", "mouth", (), "wait"), ("existing", "mouth", (), "existing"),
        ):
            with self.subTest(initial=initial, part=part):
                self.characters[0].h_state.group_sex_body_template_dict["A"] = [{"mouth": [-1, -1]}, [[], -1]]
                Action(initial, 9, 1).apply(self.characters[1], self.now)
                self.characters[1].action_progress = None
                self.events.clear()
                before = pickle.dumps(self.cache.character_data)
                panel.get_now_template_part_list = lambda: ([part], [])
                panel.get_status_id_list_from_group_sex_body_part = lambda body_part, **kw: statuses
                with patch.dict(sys.modules, {"Script.Design.handle_npc_ai_in_h": group, "Script.System.Sex_System": sex_system}), patch.object(
                    group.random, "choice", side_effect=[part, 12] if statuses else [part]
                ), patch.object(sys.modules["Script.Design.handle_npc_ai"], "choose_character_target", return_value=Action("need", 7, 1)) as choose_need:
                    choice = npc_ai.choose_next(1, self.now)
                if kind == "need":
                    choose_need.assert_called_once_with(1, self.now)
                else:
                    choose_need.assert_not_called()
                self.assertIs(type(choice), Action)
                self.assertEqual(choice.behavior_id, kind)
                self.assertEqual(pickle.dumps(self.cache.character_data), before)
                with patch.dict(sys.modules, {"Script.Design.handle_npc_ai_in_h": group}):
                    duration = runtime.execute(1, pickle.loads(pickle.dumps(choice)))
                behavior = kind if kind in {"existing", "need"} else "wait"
                self.assertEqual(duration, {"existing": 9, "need": 7}.get(behavior, 5))
                self.assertEqual(self.characters[1].behavior.behavior_id, behavior)
                self.assertEqual([event for event in self.events if event[0] == "settle"], [] if initial == "wait" else [("settle", 1, behavior)])
                template = self.characters[0].h_state.group_sex_body_template_dict["A"]
                if kind == "group_fill":
                    self.assertEqual(template[0]["mouth"], [1, 12])
                elif kind == "group_join":
                    self.assertEqual(template[1][0], [1])
                else:
                    self.assertEqual(template, [{"mouth": [-1, -1]}, [[], -1]])

    def test_absence_is_settled_only_when_intent_executes(self):
        """无需参数；缺课意图到执行时才结算缺课且先于状态机；无返回值。"""
        education = ModuleType("Script.System.Education_System")
        education.class_ai = SimpleNamespace(settle_absent=lambda actor: self.events.append(("absent", actor)))
        runtime = self.game.get_runtime()
        constant = sys.modules["Script.Core.constant"]
        constant.handle_state_machine_data = {77: lambda actor: Action("rest", 10, actor).apply(self.characters[actor], self.now)}
        intent = state_machine_action(1, 77, record_absence=True)
        self.assertEqual(self.events, [])
        with patch.dict(sys.modules, {education.__name__: education}):
            runtime.execute(1, intent)
        self.assertEqual(self.events[0], ("absent", 1))
        self.assertEqual(self.events.count(("absent", 1)), 1)

    def test_handler_exception_releases_scheduler_guard(self):
        """无需参数；状态机失败向上传播，调度器释放运行锁；无返回值。"""
        runtime = self.game.get_runtime()
        constant = sys.modules["Script.Core.constant"]

        def fail(actor):
            """输入角色，模拟状态机失败；抛出 ValueError。"""
            raise ValueError("状态机失败")

        constant.handle_state_machine_data = {77: fail}
        runtime.scheduler.replace(Task(1, self.now, state_machine_action(1, 77)))
        with self.assertRaisesRegex(ValueError, "状态机失败"):
            runtime.scheduler.advance_until_input()
        self.assertFalse(runtime.scheduler.running)
        self.assertEqual(runtime.active, {})
        runtime.scheduler.submit(Task(0, self.now, INPUT))
        self.assertIs(runtime.scheduler.advance_until_input().item, INPUT)

    def test_need_only_state_machine_waits_five_minutes(self):
        """无需参数；只更新需求的状态机等待五分钟，保持原选择间隔；无返回值。"""
        runtime = self.game.get_runtime()
        self.characters[1].need = "idle"

        def handler(actor):
            """输入角色，仅更新自身需求；返回 None。"""
            self.characters[actor].need = "milk"

        sys.modules["Script.Core.constant"].handle_state_machine_data = {77: handler}
        runtime.scheduler.replace(Task(1, self.now, state_machine_action(1, 77)))
        runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=1), INPUT))
        runtime.scheduler.advance_until_input()
        self.assertEqual(self.characters[1].need, "milk")
        self.assertEqual(runtime.scheduler.pending(1).at, self.now + timedelta(minutes=5))
        self.assertEqual(self.events.count(("settle", 1, "wait")), 1)
        self.assertEqual(self.events.count(("realtime", 1, 5)), 1)
        self.assertNotIn(("settle", 1, "idle"), self.events)

    def test_state_machine_submitted_response_executes_once(self):
        """无需参数；状态机提交的响应只由待办执行一次；无返回值。"""
        runtime = self.game.get_runtime()

        def handler(actor):
            """输入角色，准备并提交响应行动；返回 None。"""
            Action("response", 5, actor).apply(self.characters[actor], self.now)
            self.game.submit_current(actor)

        sys.modules["Script.Core.constant"].handle_state_machine_data = {77: handler}
        runtime.scheduler.replace(Task(1, self.now, state_machine_action(1, 77)))
        runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=1), INPUT))
        runtime.scheduler.advance_until_input()
        self.assertEqual(self.events.count(("settle", 1, "response")), 1)
        self.assertEqual(self.events.count(("realtime", 1, 5)), 1)

    def test_idle_choice_reads_current_task_time(self):
        """无需参数；闲置角色首次选择时读取当前待办时刻；无返回值。"""
        runtime = self.game.get_runtime()
        seen = []

        def choose(actor, now):
            """输入角色和候选，记录行为时刻并返回等待；返回 Action。"""
            seen.append(self.characters[actor].behavior.start_time)
            return Action("wait", 5, actor)

        with patch.object(sys.modules["Script.Modules.npc_ai"], "choose_next", choose):
            runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=1), INPUT))
            runtime.scheduler.advance_until_input()
        self.assertEqual(seen, [self.now])

    def test_precheck_replacement_skips_choice(self):
        """无需参数；维护阶段提交强制动作后跳过该次自主选择；无返回值。"""
        runtime = self.game.get_runtime()

        def prepare(actor, now):
            """输入角色与时刻，提交强制退出；返回 None。"""
            runtime.enqueue(actor, Action("forced_exit", 5, actor))

        with patch.object(sys.modules["Script.Design.handle_npc_ai"], "run_npc_pre_behavior_checks", prepare), patch.object(
            runtime.scheduler, "_choose_next", side_effect=AssertionError("不应调用 AI")
        ):
            runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=1), INPUT))
            runtime.scheduler.advance_until_input()
        self.assertEqual(self.events.count(("settle", 1, "forced_exit")), 1)

    def test_player_sleep_chunks_once_effect_and_total_time(self):
        """无需参数；睡眠拆段但入睡效果一次、总占用不变；无返回值。"""
        runtime = self.game.get_runtime()
        Action("sleep", 65, 0).apply(self.characters[0], self.now)
        default = sys.modules["Script.Settle.default"]
        with patch.object(default, "handle_add_small_sanity_point") as sanity, patch.object(default, "handle_add_small_semen_point") as semen:
            runtime.advance(65)
        self.assertEqual([call.args[1] for call in sanity.call_args_list], [30, 5])
        self.assertEqual([call.args[1] for call in semen.call_args_list], [30, 5])
        self.assertEqual(self.cache.game_time, self.now + timedelta(minutes=65))
        self.assertEqual([event for event in self.events if event[:2] == ("realtime", 0)], [("realtime", 0, 30), ("realtime", 0, 30), ("realtime", 0, 5)])
        self.assertEqual(len([event for event in self.events if event[0] == "sleep_once"]), 1)
        self.assertEqual(len([event for event in self.events if event == ("settle", 0, "sleep")]), 1)

    def test_rest_executes_as_one_atomic_action(self):
        """无需参数；休息按指定时长完整执行一次；无返回值。"""
        runtime = self.game.get_runtime()
        runtime.scheduler.replace(Task(0, self.now, Action("rest", 45, 0), immediate=True))
        self.assertEqual(runtime.scheduler.advance_until_input().at, self.now + timedelta(minutes=45))
        self.assertEqual([event for event in self.events if event[:2] == ("realtime", 0)], [("realtime", 0, 45)])
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
            runtime.scheduler.replace(Task(1, self.now, Action("sleep", 65, 1), immediate=True))
            runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=61), INPUT))
            runtime.scheduler.advance_until_input()
        self.assertEqual([event for event in self.events if event[:2] == ("realtime", 1)], [("realtime", 1, 30), ("realtime", 1, 30), ("realtime", 1, 5)])
        self.assertEqual(self.events.count(("settle", 1, "sleep")), 1)

    def test_npc_sleep_finishes_before_new_choice(self):
        """无需参数；睡眠到期先收尾和维护状态，再选择新动作；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        import Script.Modules

        def prepare(actor, now):
            """输入角色和时刻，记录收尾后的维护；返回 None。"""
            self.assertEqual(self.characters[actor].behavior.behavior_id, "idle")
            self.events.append(("prepare", actor))

        def choose(actor, now):
            """输入角色和时刻，确认选择读取完整收尾结果；返回等待动作。"""
            self.assertEqual(self.characters[actor].behavior.behavior_id, "idle")
            self.assertIsNone(self.characters[actor].action_progress)
            self.events.append(("choose", actor))
            return Action("wait", 5, actor)

        legacy = sys.modules["Script.Design.handle_npc_ai"]
        with patch.object(Script.Modules, "npc_ai", npc_ai), patch.object(legacy, "run_npc_pre_behavior_checks", prepare), patch.object(legacy, "choose_character_target", choose):
            runtime = self.game.get_runtime()
            runtime.scheduler.replace(Task(1, self.now, Action("sleep", 30, 1), immediate=True))
            runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=31), INPUT))
            runtime.scheduler.advance_until_input()
        relevant = [event for event in self.events if event[0] in {"finish", "prepare", "choose"}]
        self.assertEqual(relevant, [("finish", 1), ("prepare", 1), ("choose", 1)])
        self.assertEqual(self.events.count(("settle", 1, "sleep")), 1)
        self.assertEqual(self.events.count(("settle", 1, "wait")), 1)

    def test_npc_rest_is_selected_again_after_each_complete_action(self):
        """无需参数；两次三十分钟休息各自收尾并结算，不产生续段；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        import Script.Modules

        legacy = sys.modules["Script.Design.handle_npc_ai"]
        with patch.object(Script.Modules, "npc_ai", npc_ai), patch.object(legacy, "choose_character_target", lambda actor, now: Action("rest", 30, actor)):
            runtime = self.game.get_runtime()
            runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=31), INPUT))
            runtime.scheduler.advance_until_input()
        self.assertEqual(self.events.count(("settle", 1, "rest")), 2)
        self.assertEqual(self.events.count(("finish", 1)), 1)
        self.assertFalse(npc_ai.choose_next(1, self.now).continued)

    def test_wake_prechecks_preserve_forced_followup(self):
        """无需参数；醒来检查提交的强制行动优先执行，AI 不覆盖它；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        import Script.Modules

        runtime = self.game.get_runtime()
        def prepare(actor, now):
            """输入角色和时刻，提交一次强制响应；返回 None。"""
            runtime.enqueue(actor, Action("forced", 5, actor))

        legacy = sys.modules["Script.Design.handle_npc_ai"]
        with patch.object(Script.Modules, "npc_ai", npc_ai), patch.object(legacy, "run_npc_pre_behavior_checks", prepare), patch.object(legacy, "choose_character_target", side_effect=AssertionError("强制响应应先执行")):
            runtime.scheduler.replace(Task(1, self.now, Action("sleep", 30, 1), immediate=True))
            runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=31), INPUT))
            runtime.scheduler.advance_until_input()
        self.assertEqual(self.events.count(("finish", 1)), 1)
        self.assertEqual(self.events.count(("settle", 1, "forced")), 1)

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
        """无需参数；助理整夜睡眠跨问候时刻醒来，小睡继续；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        self.characters[0].action_info = SimpleNamespace(plan_to_wake_time=(7, 0))
        start = self.now.replace(hour=6, minute=40)
        Action("sleep", 30, 1).apply(self.characters[1], start)
        with patch.object(sys.modules["Script.Design.handle_premise"], "handle_assistant_morning_salutation_on", lambda actor: True):
            for duration in (480, 300, 65):
                with self.subTest(duration=duration):
                    self.cache.game_time = start + timedelta(minutes=10)
                    self.characters[1].action_progress = ActionProgress(Action("sleep", duration, 1), 30)
                    self.assertTrue(npc_ai.choose_next(1, self.cache.game_time).continued)
                    self.cache.game_time = start + timedelta(minutes=30)
                    choice = npc_ai.choose_next(1, self.cache.game_time)
                    if duration == 480:
                        self.assertEqual(choice, Action("finish_current", 0, 1))
                    else:
                        self.assertEqual((choice.behavior_id, choice.duration, choice.continued), ("sleep", 30, True))

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
            self.characters[1].behavior.behavior_id = "sleep"
            self.characters[1].target_character_id = 99
            self.characters[1].action_progress = ActionProgress(Action("sleep", 60, 1), 30)
            action = npc_ai.choose_next(1, self.now)
        self.assertIs(type(action), Action)
        self.assertEqual(action, Action("finish_current", 0, 1))
        self.assertEqual(pickle.loads(pickle.dumps(action)), action)

    def test_recovery_ai_returns_one_chunk(self):
        """无需参数；恢复计划的下一行动占用一个三十分钟片段；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        self.cache.npc_id_got.clear()
        runtime = self.game.get_runtime()
        self.characters[1].behavior.behavior_id = "sleep"
        self.characters[1].action_progress = ActionProgress(Action("sleep", 95, 1), 30)

        action = npc_ai.choose_next(1, self.now)

        self.assertEqual((action.behavior_id, action.duration, action.target), ("sleep", 30, 1))
        self.assertTrue(action.continued)

    def test_repeated_choice_consumes_each_progress_only_once(self):
        """无需参数；同一累计进度重复选择不重复扣减剩余时间；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        character = self.characters[1]
        request = Action("sleep", 65, 1)
        request.apply(character, self.now)
        progress = character.action_progress = ActionProgress(request, 30)
        before = pickle.dumps(character)
        for elapsed, duration in ((30, 30), (30, 30), (60, 5), (60, 5)):
            progress.elapsed = elapsed
            choice = npc_ai.choose_next(1, self.now)
            self.assertIs(type(choice), Action)
            self.assertEqual(pickle.loads(pickle.dumps(choice)), choice)
            self.assertEqual(choice.duration, duration)
            self.assertTrue(choice.continued)
        self.assertIs(character.action_progress, progress)
        self.assertEqual(request.duration, 65)
        progress.elapsed = 30
        self.assertEqual(pickle.dumps(character), before)
        self.assertEqual(self.events, [])

    def test_restored_ai_resumes_from_saved_progress(self):
        """无需参数；存档恢复后按累计执行时间继续，重复选择保持剩余时长；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        request = Action("sleep", 65, 1)
        request.apply(self.characters[1], self.now)
        self.characters[1].action_progress = ActionProgress(request, 30)
        self.assertEqual(npc_ai.choose_next(1, self.now).duration, 30)
        self.characters[1] = pickle.loads(pickle.dumps(self.characters[1]))
        self.assertEqual(npc_ai.choose_next(1, self.now).duration, 30)
        self.characters[1].action_progress.elapsed = 60
        self.assertEqual(npc_ai.choose_next(1, self.now).duration, 5)

    def test_legacy_character_without_ai_records_can_choose(self):
        """无需参数；旧档没有执行和决策记录时仍能选择，首次执行后正常续段；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        character = self.characters[1]
        Action("sleep", 65, 1).apply(character, self.now)
        first = npc_ai.choose_next(1, self.now)
        self.assertFalse(first.continued)
        character.action_progress = ActionProgress(first, 30)
        self.assertEqual(npc_ai.choose_next(1, self.now).duration, 30)

    def test_reset_clears_progress_before_runtime_exists(self):
        """无需参数；执行器尚未创建时，角色重置仍清空存档中的旧进度；无返回值。"""
        self.characters[1].action_progress = ActionProgress(Action("sleep", 65, 1), 30)
        self.assertIsNone(self.cache.action_scheduler)
        self.game.reset_character(1)
        self.assertIsNone(self.characters[1].action_progress)
        self.assertIsNone(self.cache.action_scheduler)

    def test_cancelled_sleep_does_not_resume_old_plan(self):
        """无需参数；取消后的同类型新行动使用新时长，不沿用旧恢复计划；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        character = self.characters[1]
        Action("sleep", 65, 1).apply(character, self.now)
        character.action_progress = ActionProgress(Action("sleep", 65, 1), 30)
        npc_ai.choose_next(1, self.now)
        self.game.get_runtime()
        self.game.reset_character(1)
        self.assertIsNone(character.action_progress)
        Action("sleep", 12, 1).apply(character, self.now)
        choice = npc_ai.choose_next(1, self.now)
        self.assertEqual(choice.duration, 12)
        self.assertFalse(choice.continued)
        character.action_progress = ActionProgress(choice, 10)
        self.assertEqual(npc_ai.choose_next(1, self.now).duration, 2)

    def test_execution_records_original_duration_and_elapsed(self):
        """无需参数；执行记录保存原请求时长及累计时间；无返回值。"""
        character = self.characters[1]
        runtime = self.game.get_runtime()
        runtime.scheduler.replace(Task(1, self.now, Action("sleep", 65, 1), immediate=True))
        runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=1), INPUT))
        runtime.scheduler.advance_until_input()
        self.assertEqual(character.action_progress.action.duration, 65)
        self.assertEqual(character.action_progress.elapsed, 30)

    def test_continued_execution_accumulates_progress(self):
        """无需参数；续段累计执行进度，下一次 AI 查询据此计算剩余时长；无返回值。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        character = self.characters[1]
        request = Action("sleep", 65, 1)
        request.apply(character, self.now)
        progress = character.action_progress = ActionProgress(request, 30)
        choice = npc_ai.choose_next(1, self.now)
        runtime = self.game.get_runtime()
        runtime.execute(1, choice)
        self.assertEqual(request.duration, 65)
        self.assertIs(character.action_progress, progress)
        self.assertEqual(progress.elapsed, 60)
        self.assertEqual(npc_ai.choose_next(1, self.now).duration, 5)

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
        self.assertIs(type(action), Action)
        self.assertEqual(pickle.loads(pickle.dumps(action)), action)
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

    def test_end_wait_cancels_recovery_and_uses_normal_pending(self):
        """无需参数；真实结束等待函数清空旧进度，并排普通续段而非立即行动；无返回值。"""
        source = Path(__file__).resolve().parents[1] / "Script/System/Instruct_System/handle_instruct.py"
        tree = ast.parse(source.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_schedule_h_end_wait")
        namespace = {"cache": self.cache}
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
        runtime = self.game.get_runtime()
        player_progress = self.characters[0].action_progress = ActionProgress(Action("sleep", 65, 0), 30)
        for actor in (1, 0):
            with self.subTest(actor=actor):
                character = self.characters[actor]
                character.action_progress = ActionProgress(Action("sleep", 65, actor), 30)
                Action("wait", 5, actor).apply(character, self.now)
                namespace["_schedule_h_end_wait"](actor)
                self.assertIsNone(character.action_progress)
                pending = runtime.scheduler.pending(actor)
                self.assertEqual((pending.at, pending.item.behavior_id, pending.item.duration), (self.now, "wait", 5))
                self.assertTrue(pending.item.continued)
                self.assertFalse(pending.immediate)
                if actor == 1:
                    self.assertIs(self.characters[0].action_progress, player_progress)

    def test_offline_online_drops_old_action_and_recovery_plan(self):
        """无需参数；离队期间无效果，上线立即自主选择且不恢复旧睡眠；无返回值。"""
        runtime = self.game.get_runtime()
        old = Action("sleep", 30, 1, continued=True)
        old.apply(self.characters[1], self.now)
        runtime.current[1] = (self.characters[1].behavior, 1, "sleep")
        self.characters[1].action_progress = ActionProgress(old, 0)
        runtime.scheduler.replace(Task(1, self.now + timedelta(minutes=30), old))
        self.cache.npc_id_got.remove(1)
        self.game.reset_character(1)
        runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=5), INPUT))
        runtime.scheduler.advance_until_input()
        self.assertFalse(any(event[:2] == ("realtime", 1) for event in self.events))
        self.assertNotIn(1, runtime.current)
        self.assertIsNone(self.characters[1].action_progress)

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
