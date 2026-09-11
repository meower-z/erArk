"""以真实 Action 和 Scheduler 检查游戏接入的执行顺序。"""

from collections import deque
from datetime import datetime, timedelta
from functools import partial
import ast
import importlib
import pickle
import re
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from Script.Modules.action import Action, CONTINUED, STATE
from Script.Modules.scheduler import AI, INPUT, Task
from Script.Design.action_execution import state_machine_action


class Behavior:
    """测试中的旧行为记录，保留行动接入需要的字段。"""

    def __init__(self):
        """无需参数，初始化空闲行为；无返回值。"""
        self.behavior_id = "idle"
        self.duration = 0
        self.start_time = datetime.min
        self.plan_start_time = datetime.min
        self.plan_end_time = datetime.min
        self.wait_on_behavior_id = ""


class GameActionsTests(unittest.TestCase):
    """只替换游戏外围效果，保留调度与动作接入的真实调用。"""

    def setUp(self):
        """无需参数，建立可记录调用的轻量游戏环境；无返回值。"""
        self.now = datetime(2026, 3, 1, 10)
        self.events = []
        self.characters = {
            actor: SimpleNamespace(
                behavior=Behavior(),
                target_character_id=actor,
                state="idle",
                dead=False,
                sp_flag=SimpleNamespace(see_pl_h=False, is_h=False),
                hypnosis=SimpleNamespace(blockhead=False),
                action_info=SimpleNamespace(plan_to_wake_time=(10, 40)),
            )
            for actor in (0, 1)
        }
        self.cache = SimpleNamespace(
            game_time=self.now,
            pre_game_time=self.now,
            character_data=self.characters,
            npc_id_got={1},
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
        # 游戏接入代码本身从真实目录导入，其余 Script.Design 模块仍用上面的替身。
        modules["Script.Design"].__path__ = [str(Path(__file__).resolve().parents[1] / "Script/Design")]

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
        sys.modules.pop("Script.Design.game_actions", None)
        self.game = importlib.import_module("Script.Design.game_actions")

    def finish(self, actor, now, end_now=2):
        """输入角色与收尾时刻，记录收尾并清空旧行为；返回 True。"""
        self.events.append(("finish", actor, now))
        self.characters[actor].behavior = Behavior()
        self.characters[actor].state = "idle"
        return True

    def use_real_ai(self):
        """无需参数，改用真实的 NPC 自主行动模块；返回该模块。"""
        sys.modules.pop("Script.Modules.npc_ai", None)
        npc_ai = importlib.import_module("Script.Modules.npc_ai")
        import Script.Modules

        patcher = patch.object(Script.Modules, "npc_ai", npc_ai, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        return npc_ai

    def write_behavior(self, actor, behavior_id, duration, target=None, start=None, **fields):
        """输入角色、行为编号、时长、对象、开始时刻及附加字段，直接写入角色行为；返回 None。"""
        character = self.characters[actor]
        character.behavior = Behavior()
        character.behavior.behavior_id = behavior_id
        character.behavior.duration = duration
        character.behavior.start_time = self.now if start is None else start
        character.behavior.__dict__.update(fields)
        character.target_character_id = actor if target is None else target
        character.state = behavior_id

    def advance(self, behavior_id, duration):
        """输入玩家行为编号与时长，提交玩家行动并运行至下一次输入；返回执行器。"""
        self.write_behavior(0, behavior_id, duration)
        runtime = self.game.get_runtime()
        runtime.advance(duration)
        return runtime

    def realtime(self, actor):
        """输入角色编号，返回其按时间结算的分钟数列表。"""
        return [event[2] for event in self.events if event[0] == "realtime" and event[1] == actor]

    def settled(self, actor):
        """输入角色编号，返回其一次性结算的行为编号列表。"""
        return [event[2] for event in self.events if event[0] == "settle" and event[1] == actor]

    def finished(self, actor):
        """输入角色编号，返回其行为被收尾的时刻列表。"""
        return [event[2] for event in self.events if event[0] == "finish" and event[1] == actor]

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
        """无需参数；真实目标搜索仅返回意图，选择时不触碰状态机与世界；无返回值。"""
        selector = self.load_real_target_selector()
        npc_ai = self.use_real_ai()
        constant = sys.modules["Script.Core.constant"]
        constant.handle_state_machine_data = {77: lambda actor: self.fail("选择阶段调用了状态机")}
        self.characters[1].behavior.start_time = self.now
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
        runtime = self.game.get_runtime()
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
        self.assertEqual(self.settled(1), ["work"])
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
        npc_ai = self.use_real_ai()
        self.characters[0].h_state = SimpleNamespace(group_sex_body_template_dict={"A": [{"mouth": [-1, -1]}, [[], -1]]})
        self.characters[1].sp_flag.is_h = True
        self.characters[1].sp_flag.masturebate = 3
        panel = SimpleNamespace(count_group_sex_character_list=lambda: [])
        sex_system = ModuleType("Script.System.Sex_System")
        sex_system.group_sex_panel = panel
        runtime = self.game.get_runtime()
        for initial, part, statuses, kind, duration in (
            ("idle", "mouth", (12,), "group_fill", 5),
            ("idle", "加入侍奉", (), "group_join", 5),
            ("wait", "mouth", (12,), "group_fill", 5),
            ("wait", "加入侍奉", (), "group_join", 5),
            ("idle", "mouth", (), "need", 7),
            ("wait", "mouth", (), "wait", 5),
            ("existing", "mouth", (), "existing", 9),
        ):
            with self.subTest(initial=initial, part=part):
                self.characters[0].h_state.group_sex_body_template_dict["A"] = [{"mouth": [-1, -1]}, [[], -1]]
                # 等待中的角色刚等满四分钟，先收尾再参与群交选择；他人此刻写入的非移动行为只占用时间。
                self.write_behavior(1, initial, {"idle": 0, "wait": 4, "existing": 9}[initial], start=self.now - timedelta(minutes=4) if initial == "wait" else None)
                self.events.clear()
                player_before = pickle.dumps(self.characters[0])
                npc_before = pickle.dumps(self.characters[1])
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
                self.assertEqual(pickle.dumps(self.characters[0]), player_before)
                # 选择阶段只收尾自己到期的等待，不改动其他数据。
                self.assertEqual(self.finished(1), [self.now] if initial == "wait" else [])
                if initial != "wait":
                    self.assertEqual(pickle.dumps(self.characters[1]), npc_before)
                with patch.dict(sys.modules, {"Script.Design.handle_npc_ai_in_h": group}):
                    self.assertEqual(runtime.execute(1, pickle.loads(pickle.dumps(choice))), duration)
                behavior = kind if kind in {"existing", "need"} else "wait"
                self.assertEqual(self.characters[1].behavior.behavior_id, behavior)
                # 延续的等待和他人写入的行为不触发一次性结算，群交安排的等待和自选的新行为结算一次。
                self.assertEqual(self.settled(1), [] if kind in {"wait", "existing"} else [behavior])
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
        self.assertEqual(self.settled(1), ["wait"])

    def test_idle_choice_reads_current_task_time(self):
        """无需参数；闲置 NPC 选择时行为开始时刻已是当前待办时刻；无返回值。"""
        self.use_real_ai()
        seen = []
        with patch.object(sys.modules["Script.Design.handle_npc_ai"], "choose_character_target", side_effect=lambda actor, now: (seen.append((now, self.characters[actor].behavior.start_time)), Action("rest", 20, actor))[1]):
            self.advance("wait", 30)
        self.assertEqual(seen, [(self.now, self.now), (self.now + timedelta(minutes=20), self.now + timedelta(minutes=20))])

    def test_precheck_replacement_skips_choice(self):
        """无需参数；行动前检查替换待办后不再调用选择，直接执行替代行动；无返回值。"""
        runtime = self.game.get_runtime()

        def precheck(actor, now):
            """输入角色与时刻，模拟行动前检查改写行为并强制安排；返回 None。"""
            self.write_behavior(actor, "tired_sleep", 15)
            self.game.submit_current(actor)

        with patch.object(sys.modules["Script.Design.handle_npc_ai"], "run_npc_pre_behavior_checks", side_effect=precheck), patch.object(
            sys.modules["Script.Modules.npc_ai"], "choose_next", side_effect=AssertionError("替换后不应再选择")
        ):
            runtime.scheduler.submit(Task(0, self.now + timedelta(minutes=1), INPUT))
            runtime.scheduler.advance_until_input()
        self.assertEqual(self.settled(1), ["tired_sleep"])
        self.assertEqual(runtime.scheduler.pending(1).at, self.now + timedelta(minutes=15))

    def test_player_sleep_is_one_whole_action(self):
        """无需参数；玩家睡眠不切段，一次性效果、时间结算和睡眠收尾各一次；无返回值。"""
        self.advance("sleep", 65)
        self.assertEqual(self.settled(0), ["sleep"])
        self.assertEqual(self.realtime(0), [65])
        self.assertEqual(self.events.count(("sleep_once", 65)), 1)
        self.assertEqual(self.finished(0), [self.now + timedelta(minutes=65)])
        self.assertEqual(self.cache.game_time, self.now + timedelta(minutes=65))

    def test_rest_executes_as_one_atomic_action(self):
        """无需参数；玩家休息作为一个整体结算并在输入前收尾；无返回值。"""
        self.advance("rest", 40)
        self.assertEqual(self.settled(0), ["rest"])
        self.assertEqual(self.realtime(0), [40])
        self.assertEqual(self.finished(0), [self.now + timedelta(minutes=40)])
        self.assertEqual(self.characters[0].behavior.behavior_id, "idle")

    def test_idle_player_is_not_closed_at_input(self):
        """无需参数；玩家行为已被他人收尾时输入前不再重复收尾；无返回值。"""
        runtime = self.game.get_runtime()
        runtime.scheduler.submit(Task(0, self.now, INPUT))
        runtime.scheduler.advance_until_input()
        self.assertEqual(self.finished(0), [])

    def test_wait_on_npc_rechecks_owner_every_five_minutes(self):
        """无需参数；NPC 等待玩家的双人行为时每五分钟复查，主体换目标后收尾并重新选择；无返回值。"""
        self.use_real_ai()
        runtime = self.game.get_runtime()
        self.write_behavior(0, "h_act", 30, target=1)
        self.game.wait_on(1, 0, "h_act")
        pending = runtime.scheduler.pending(1)
        self.assertEqual((pending.at, pending.item.behavior_id, pending.item.duration, pending.item.continued, pending.immediate), (self.now, "wait", 5, True, False))
        runtime.advance(30)
        self.assertEqual(self.settled(1), [])
        self.assertEqual(self.realtime(1), [5] * 6)
        self.assertEqual(self.characters[1].behavior.wait_on_behavior_id, "h_act")
        self.assertEqual(self.finished(1), [])
        self.events.clear()
        self.write_behavior(0, "wait", 1, target=1)
        runtime.advance(1)
        self.assertEqual(self.finished(1), [self.now + timedelta(minutes=30)])
        self.assertEqual(self.settled(1), ["wait"])
        self.assertEqual(self.characters[1].behavior.wait_on_behavior_id, "")

    def test_wait_on_npc_stops_when_owner_targets_someone_else(self):
        """无需参数；主体行为相同但对象换人时 NPC 不再延续等待；无返回值。"""
        self.use_real_ai()
        self.write_behavior(0, "h_act", 30, target=1)
        self.characters[2] = SimpleNamespace(behavior=Behavior(), target_character_id=2, state="idle", dead=False, sp_flag=SimpleNamespace(see_pl_h=False, is_h=False), hypnosis=SimpleNamespace(blockhead=False))
        runtime = self.game.get_runtime()
        self.game.wait_on(1, 0, "h_act")
        with patch.object(sys.modules["Script.Design.character_behavior"], "judge_character_status", side_effect=lambda actor: self.characters[0].__setattr__("target_character_id", 2) if actor == 0 else None):
            runtime.advance(30)
        self.assertEqual(self.realtime(1), [5] * 6)
        self.assertEqual(self.finished(1)[0], self.now + timedelta(minutes=5))

    def test_wait_on_waiting_owner_lasts_for_owner_duration(self):
        """无需参数；主体只是在等待时 NPC 不带复查标记，陪等主体时长后收尾，玩家随后继续等待也不再延续；无返回值。"""
        self.use_real_ai()
        runtime = self.game.get_runtime()
        self.write_behavior(0, "wait", 1, target=1)
        self.game.wait_on(1, 0, "wait")
        pending = runtime.scheduler.pending(1)
        self.assertEqual((pending.at, pending.item.behavior_id, pending.item.duration, pending.item.continued, pending.immediate), (self.now, "wait", 1, True, False))
        self.assertNotIn("wait_on_behavior_id", pending.item.params)
        self.write_behavior(0, "wait", 60, target=1)
        runtime.advance(60)
        self.assertEqual(self.finished(1)[0], self.now + timedelta(minutes=1))
        self.assertEqual(self.realtime(1)[:2], [1, 5])
        self.assertEqual(self.characters[1].behavior.wait_on_behavior_id, "")

    def test_precheck_uses_player_start_time(self):
        """无需参数；NPC 行动前检查收到的是玩家本次行动的开始时刻，而非待办时刻；无返回值。"""
        runtime = self.game.get_runtime()
        seen = []
        runtime.scheduler.replace(Task(1, self.now + timedelta(minutes=5), AI))
        with patch.object(sys.modules["Script.Design.handle_npc_ai"], "run_npc_pre_behavior_checks", side_effect=lambda actor, start: seen.append((runtime.scheduler.now, start))):
            self.advance("wait", 10)
        self.assertEqual(seen, [(self.now + timedelta(minutes=5), self.now)])

    def test_player_wait_on_lasts_for_owner_remaining_time(self):
        """无需参数；玩家成为第二主体时等完主体行为全程，期间不需要 AI；无返回值。"""
        chosen = []

        def choose(actor, now):
            """输入角色与时刻，记录选择并对玩家发起三十分钟双人行为；返回 Action。"""
            chosen.append(now)
            return Action("h_act", 30, 0)

        def settle(actor):
            """输入角色，模拟主体行为的结算让玩家等待；返回 None。"""
            self.events.append(("settle", actor, self.characters[actor].behavior.behavior_id))
            if actor == 1:
                self.game.wait_on(0, 1, "h_act")

        with patch.object(sys.modules["Script.Modules.npc_ai"], "choose_next", side_effect=choose), patch.object(sys.modules["Script.Design.character_behavior"], "judge_character_status", side_effect=settle):
            self.advance("wait", 1)
        self.assertEqual(chosen, [self.now])
        self.assertEqual(self.settled(0), ["wait", "wait"])
        self.assertEqual(self.realtime(0), [1, 30])
        self.assertEqual(self.characters[0].target_character_id, 1)
        self.assertEqual(self.cache.game_time, self.now + timedelta(minutes=30))

    def test_forced_chain_preserves_submission_order(self):
        """无需参数；同一角色的多个强制后续按提交顺序依次执行，之后才恢复自主选择；无返回值。"""
        runtime = self.game.get_runtime()

        def settle(actor):
            """输入角色，玩家结算时为 NPC 连续安排两个后续；返回 None。"""
            self.events.append(("settle", actor, self.characters[actor].behavior.behavior_id))
            if actor == 0 and self.characters[0].behavior.behavior_id == "order":
                self.write_behavior(1, "first", 3)
                self.game.submit_current(1)
                self.write_behavior(1, "second", 4)
                self.game.submit_current(1)
                self.write_behavior(1, "third", 2)
                self.game.submit_current(1)

        with patch.object(sys.modules["Script.Design.character_behavior"], "judge_character_status", side_effect=settle):
            self.write_behavior(0, "order", 10)
            runtime.advance(10)
        self.assertEqual(self.settled(1), ["first", "second", "third", "wait"])
        self.assertEqual(self.realtime(1), [3, 4, 2, 60])
        self.assertEqual(runtime._forced[1], deque())

    def test_after_callback_runs_when_forced_action_completes(self):
        """无需参数；收尾回调在强制行动结算后执行，回调可以继续安排后续；无返回值。"""
        runtime = self.game.get_runtime()

        def exit_done(actor):
            """输入角色，记录退出完成并为玩家安排立即后续；返回 None。"""
            self.events.append(("group_exit", actor))
            self.write_behavior(0, "reaction", 2)
            self.game.submit_current(0)

        def settle(actor):
            """输入角色，玩家结算时安排 NPC 的退出行动；返回 None。"""
            self.events.append(("settle", actor, self.characters[actor].behavior.behavior_id))
            if actor == 0 and self.characters[0].behavior.behavior_id == "order":
                self.write_behavior(1, "exit", 5)
                self.game.submit_current(1, after="group_exit")

        with patch.object(sys.modules["Script.Design.handle_npc_ai"], "finish_group_sex_tired_exit", side_effect=exit_done), patch.object(sys.modules["Script.Design.character_behavior"], "judge_character_status", side_effect=settle):
            self.write_behavior(0, "order", 10)
            runtime.advance(10)
        kinds = [(event[0], event[1]) + ((event[2],) if event[0] == "settle" else ()) for event in self.events if event[0] in {"settle", "group_exit"}]
        self.assertEqual(kinds, [("settle", 0, "order"), ("settle", 1, "exit"), ("group_exit", 1), ("settle", 0, "reaction")])
        self.assertEqual(self.cache.game_time, self.now + timedelta(minutes=2))

    def test_forced_action_replaces_pending_without_repeating_it(self):
        """无需参数；强制后续替换角色原待办，原待办不再执行；无返回值。"""
        runtime = self.game.get_runtime()
        self.write_behavior(1, "forced", 7)
        self.game.submit_current(1)
        self.assertTrue(runtime.scheduler.pending(1).immediate)
        self.advance("wait", 7)
        self.assertEqual(self.settled(1), ["forced"])
        self.assertEqual(runtime.scheduler.pending(1).at, self.now + timedelta(minutes=7))

    def test_saved_behavior_resumes_remaining_time_without_replaying(self):
        """无需参数；读档后进行中的行为不再结算，到期后才由 NPC 自己收尾并选择；无返回值。"""
        self.use_real_ai()
        self.write_behavior(1, "work", 60, start=self.now - timedelta(minutes=30))
        runtime = self.game.get_runtime()
        self.assertEqual(runtime.scheduler.pending(1), Task(1, self.now + timedelta(minutes=30), AI))
        self.advance("wait", 30)
        self.assertEqual(self.settled(1), [])
        self.assertEqual(self.realtime(1), [])
        self.assertEqual(self.finished(1), [])
        self.advance("wait", 1)
        self.assertEqual(self.finished(1), [self.now + timedelta(minutes=30)])
        self.assertEqual(self.settled(1), ["wait"])

    def test_finished_saved_behavior_starts_with_ai(self):
        """无需参数；读档时已到期的行为直接进入自主选择；无返回值。"""
        self.write_behavior(1, "work", 60, start=self.now - timedelta(minutes=60))
        runtime = self.game.get_runtime()
        self.assertEqual(runtime.scheduler.pending(1), Task(1, self.now, AI))

    def test_runtime_is_not_part_of_the_save(self):
        """无需参数；缓存不携带执行器，读档重置后按角色状态重新建队；无返回值。"""
        runtime = self.game.get_runtime()
        self.advance("wait", 10)
        self.assertNotIn("runtime", pickle.dumps(self.cache).decode("latin-1"))
        self.game.reset()
        self.write_behavior(1, "work", 20)
        rebuilt = self.game.get_runtime()
        self.assertIsNot(rebuilt, runtime)
        self.assertEqual(rebuilt.scheduler.pending(1), Task(1, self.now + timedelta(minutes=20), AI))

    def test_time_stop_keeps_npc_pending_and_world_time(self):
        """无需参数；时停中玩家行动不推进时间，NPC 待办保持原样；无返回值。"""
        self.cache.time_stop_mode = True
        runtime = self.advance("touch", 10)
        self.assertEqual(self.cache.game_time, self.now)
        self.assertEqual(runtime.scheduler.pending(1), Task(1, self.now, AI))
        self.assertEqual(self.realtime(1), [])
        self.assertEqual(self.cache.achievement.time_stop_duration, 10)
        self.assertEqual(self.finished(0), [self.now])

    def test_time_stop_wait_on_does_nothing(self):
        """无需参数；时停中的等待请求不改变任何待办；无返回值。"""
        self.cache.time_stop_mode = True
        runtime = self.game.get_runtime()
        self.write_behavior(0, "h_act", 10, target=1)
        self.game.wait_on(1, 0, "h_act")
        self.assertEqual(runtime.scheduler.pending(1), Task(1, self.now, AI))

    def test_time_stop_does_not_interrupt_working_npc(self):
        """无需参数；玩家行动开始时打断工作 NPC，时停中不打断；无返回值。"""
        for time_stop in (False, True):
            with self.subTest(time_stop=time_stop):
                self.game.reset()
                self.events.clear()
                self.cache.game_time = self.cache.pre_game_time = self.now
                self.cache.time_stop_mode = time_stop
                self.write_behavior(1, "work", 60)
                runtime = self.game.get_runtime()
                with patch.object(sys.modules["Script.Design.handle_premise"], "handle_action_work_or_entertainment", return_value=True), patch.object(
                    sys.modules["Script.Design.handle_npc_ai"], "judge_interrupt_character_behavior", return_value=True
                ), patch.object(sys.modules["Script.Modules.npc_ai"], "choose_next", return_value=Action("bath", 15, 1)) as choose:
                    self.write_behavior(0, "wait", 1)
                    runtime.advance(1)
                self.assertEqual(choose.call_count, 0 if time_stop else 1)
                self.assertEqual(self.settled(1), [] if time_stop else ["bath"])
                pending = runtime.scheduler.pending(1)
                if time_stop:
                    self.assertEqual(pending, Task(1, self.now + timedelta(minutes=60), AI))
                else:
                    self.assertEqual(pending, Task(1, self.now + timedelta(minutes=15), AI))

    def test_npc_sleep_plan_is_chunked_and_closed_once(self):
        """无需参数；NPC 睡眠按计划切成最多三十分钟的片段，只结算一次入睡并在计划结束后收尾；无返回值。"""
        self.use_real_ai()
        installed = []

        def sleep_plan(actor):
            """输入角色，模拟睡眠状态机写入六十五分钟计划；返回 None。"""
            installed.append(actor)
            self.write_behavior(actor, "sleep", 30, plan_start_time=self.cache.game_time, plan_end_time=self.cache.game_time + timedelta(minutes=65))

        sys.modules["Script.Core.constant"].handle_state_machine_data = {77: sleep_plan}
        choices = [state_machine_action(1, 77), Action("wait", 5, 1)]
        with patch.object(sys.modules["Script.Design.handle_npc_ai"], "choose_character_target", side_effect=lambda actor, now: choices.pop(0) if choices else Action("wait", 5, actor)):
            self.advance("wait", 70)
        self.assertEqual(installed, [1])
        self.assertEqual(self.realtime(1), [30, 30, 5, 5])
        self.assertEqual(self.settled(1), ["sleep", "wait"])
        self.assertEqual(self.finished(1), [self.now + timedelta(minutes=65)])

    def test_npc_wakes_when_recovered_outside_sleep_time(self):
        """无需参数；恢复完毕且不在睡眠时段时 NPC 在片段之间醒来；无返回值。"""
        self.use_real_ai()
        self.write_behavior(1, "sleep", 30, start=self.now - timedelta(minutes=30), plan_start_time=self.now - timedelta(minutes=30), plan_end_time=self.now + timedelta(minutes=90))
        premise = sys.modules["Script.Design.handle_premise"]
        with patch.object(premise, "handle_tired_le_0", return_value=True), patch.object(premise, "handle_hp_max", return_value=True), patch.object(premise, "handle_mp_max", return_value=True):
            self.advance("wait", 10)
        self.assertEqual(self.finished(1), [self.now, self.now + timedelta(minutes=5)])
        self.assertEqual(self.settled(1), ["wait", "wait"])

    def test_assistant_wakes_when_chunk_crosses_greeting_time(self):
        """无需参数；整夜睡眠在片段末越过早安问候时刻时醒来，短睡不受影响；无返回值。"""
        self.use_real_ai()
        premise = sys.modules["Script.Design.handle_premise"]
        for total, woke in ((480, self.now + timedelta(minutes=60)), (120, self.now + timedelta(minutes=90))):
            with self.subTest(total=total):
                self.game.reset()
                self.events.clear()
                self.cache.game_time = self.cache.pre_game_time = self.now
                self.write_behavior(1, "sleep", 30, start=self.now - timedelta(minutes=30), plan_start_time=self.now - timedelta(minutes=30), plan_end_time=self.now - timedelta(minutes=30) + timedelta(minutes=total))
                with patch.object(premise, "handle_assistant_morning_salutation_on", return_value=True):
                    self.advance("wait", 120)
                self.assertEqual(self.finished(1)[0], woke)

    def test_forced_action_interrupts_sleep_plan(self):
        """无需参数；睡眠中被强制安排其他行为后不再回到原睡眠计划；无返回值。"""
        self.use_real_ai()
        self.write_behavior(1, "sleep", 30, start=self.now - timedelta(minutes=30), plan_start_time=self.now - timedelta(minutes=30), plan_end_time=self.now + timedelta(minutes=450))

        def settle(actor):
            """输入角色，玩家结算时叫醒 NPC；返回 None。"""
            self.events.append(("settle", actor, self.characters[actor].behavior.behavior_id))
            if actor == 0 and self.characters[0].behavior.behavior_id == "shout":
                self.write_behavior(1, "wake", 5)
                self.game.submit_current(1)

        with patch.object(sys.modules["Script.Design.character_behavior"], "judge_character_status", side_effect=settle):
            self.advance("shout", 40)
        self.assertEqual(self.settled(1), ["wake", "wait"] + ["wait"] * 6)
        self.assertEqual(self.realtime(1), [5] * 8)

    def test_locked_wait_is_silent_and_checks_every_five_minutes(self):
        """无需参数；H 或木头人状态的等待每五分钟收尾后静默续等，不重复结算；无返回值。"""
        self.use_real_ai()
        self.characters[1].sp_flag.is_h = True
        self.write_behavior(1, "wait", 5, target=0, start=self.now - timedelta(minutes=5))
        self.advance("wait", 15)
        self.assertEqual(self.settled(1), [])
        self.assertEqual(self.realtime(1), [5, 5, 5])
        self.assertEqual(self.finished(1), [self.now + timedelta(minutes=step) for step in (0, 5, 10)])

    def test_directly_written_behavior_runs_to_its_end_before_closing(self):
        """无需参数；他人此刻写入的非移动行为不结算效果，只执行到结束，再由 NPC 自己收尾并重新选择；无返回值。"""
        self.use_real_ai()
        self.game.get_runtime()
        self.write_behavior(1, "wait", 10, target=0)
        self.advance("wait", 15)
        self.assertEqual(self.settled(1), ["wait"])
        self.assertEqual(self.realtime(1), [10, 5])
        self.assertEqual(self.finished(1), [self.now + timedelta(minutes=10)])

    def test_written_wait_with_replan_finishes_at_its_own_end(self):
        """无需参数；NPC 待办尚在远处时被写入等待并重排，等待不结算效果，到其自身结束时刻收尾；无返回值。"""
        self.use_real_ai()
        self.write_behavior(1, "work", 60)
        runtime = self.game.get_runtime()
        self.write_behavior(1, "wait", 10, target=0, start=self.now)
        self.game.replan(1)
        self.assertEqual(runtime.scheduler.pending(1), Task(1, self.now, AI))
        self.advance("end_h", 5)
        self.advance("wait", 10)
        self.assertEqual(self.realtime(1)[0], 10)
        self.assertEqual(self.finished(1), [self.now + timedelta(minutes=10)])
        self.assertEqual(self.settled(1), ["wait"])

    def test_h_end_replans_every_directly_written_wait(self):
        """无需参数；指令处理里每处直接写给对方的十分钟等待都紧跟重排；无返回值。"""
        source = Path(__file__).resolve().parents[1] / "Script/System/Instruct_System/handle_instruct.py"
        text = source.read_text()
        writes = re.findall(r"^( +)target_data\.behavior\.duration = 10\n(?:\1.*\n){2}((?:\1.*\n){0,2})", text, re.M)
        self.assertEqual(len(writes), 5)
        for _, follow in writes:
            self.assertIn("game_actions.replan(target_data.cid)", follow)

    def test_unconscious_recovery_writes_wait_and_replans(self):
        """无需参数；无意识恢复回调直接写入对方的十分钟或一分钟等待并重排，不再让对方等待玩家的等待；无返回值。"""
        source = Path(__file__).resolve().parents[1] / "Script/Design/handle_npc_ai_in_h.py"
        text = source.read_text()
        start = text.index("def finish_unconscious_h_recovery(")
        body = text[start : start + re.search(r"\n(?:def|class) ", text[start + 1 :]).start()]
        self.assertNotIn("wait_on", body)
        self.assertIn("target_data.behavior.duration = 10\n", body)
        self.assertIn("target_data.behavior.duration = 1\n", body)
        self.assertIn("target_data.behavior.start_time = cache.game_time\n", body)
        self.assertIn("replan(target_character_id)\n", body)

    def test_behavior_written_while_pending_continues_its_remaining_time(self):
        """无需参数；NPC 待办尚在未来时已在别处结算过的移动，到期时只延续剩余时间；无返回值。"""
        self.use_real_ai()
        self.write_behavior(1, "work", 10)
        runtime = self.game.get_runtime()
        self.advance("wait", 4)
        self.write_behavior(1, "move", 10, target=1, start=self.now + timedelta(minutes=4))
        self.events.clear()
        self.advance("wait", 10)
        self.assertEqual(self.settled(1), [])
        self.assertEqual(self.realtime(1), [4])
        self.assertEqual(runtime.scheduler.pending(1), Task(1, self.now + timedelta(minutes=14), AI))

    def test_precheck_written_behavior_is_settled_once(self):
        """无需参数；行动前检查在待办时刻写入的行为按新行为结算一次；无返回值。"""
        self.use_real_ai()
        written = []

        def precheck(actor, now):
            """输入角色与时刻，首次检查时写入三分钟移动；返回 None。"""
            if not written:
                written.append(now)
                self.write_behavior(1, "move", 3, start=now)

        with patch.object(sys.modules["Script.Design.handle_npc_ai"], "run_npc_pre_behavior_checks", side_effect=precheck):
            self.advance("wait", 3)
        self.assertEqual(self.settled(1), ["move"])
        self.assertEqual(self.realtime(1), [3])
        self.assertEqual(self.finished(1), [])

    def test_state_machine_forced_follow_up_settles_once(self):
        """无需参数；状态机在准备阶段安排强制后续时，本次行动让位且只结算一次，收尾回调照常执行；无返回值。"""
        runtime = self.game.get_runtime()

        def machine(actor):
            """输入角色编号，写入反应行为并安排强制后续；返回 None。"""
            self.write_behavior(actor, "react", 10, start=self.cache.game_time)
            self.game.submit_current(actor, after="group_exit")

        sys.modules["Script.Core.constant"].handle_state_machine_data = {5: machine}
        with patch.object(sys.modules["Script.Modules.npc_ai"], "choose_next", return_value=state_machine_action(1, 5)):
            self.advance("wait", 10)
        self.assertEqual(self.settled(1), ["react"])
        self.assertEqual(self.realtime(1), [10])
        self.assertIn(("group_exit", 1), self.events)
        self.assertEqual(runtime.scheduler.pending(1), Task(1, self.now + timedelta(minutes=10), AI))

    def test_player_action_replaced_during_preparation_is_not_settled(self):
        """无需参数；行动前置面板改写玩家行动并推进时，只有新行动结算一次；无返回值。"""
        runtime = self.game.get_runtime()
        calls = []

        def prepare():
            """无需参数，首次调用时改写玩家行动并再次推进；返回 None。"""
            if not calls:
                calls.append(True)
                self.write_behavior(0, "action2", 20)
                runtime.advance(20)

        with patch.object(sys.modules["Script.Design.character_behavior"], "judge_before_pl_behavior", side_effect=prepare):
            self.advance("action1", 10)
        self.assertEqual(self.settled(0), ["action2"])
        self.assertEqual(self.realtime(0), [20])
        self.assertEqual(self.cache.game_time, self.now + timedelta(minutes=20))

    def test_replan_is_ordinary_and_yields_to_time_stop_input(self):
        """无需参数；改写行为后的重排是普通待办，时停中玩家输入先于它，NPC 不动；无返回值。"""
        self.write_behavior(1, "work", 60)
        runtime = self.game.get_runtime()
        self.game.replan(1)
        self.assertEqual(runtime.scheduler.pending(1), Task(1, self.now, AI))
        self.cache.time_stop_mode = True
        with patch.object(sys.modules["Script.Modules.npc_ai"], "choose_next", return_value=Action("wait", 5, 1)) as choose:
            self.advance("touch", 10)
        choose.assert_not_called()
        self.assertEqual(runtime.scheduler.pending(1), Task(1, self.now, AI))

    def test_npc_closes_each_finished_action_before_next_choice(self):
        """无需参数；NPC 每个行动到期后先收尾再选择下一个，选择时行为已闲置；无返回值。"""
        self.use_real_ai()
        seen = []
        with patch.object(sys.modules["Script.Design.handle_npc_ai"], "choose_character_target", side_effect=lambda actor, now: (seen.append(self.characters[actor].behavior.behavior_id), Action("rest", 20, actor))[1]):
            self.advance("wait", 60)
        self.assertEqual(seen, ["idle"] * 3)
        self.assertEqual(self.settled(1), ["rest"] * 3)
        self.assertEqual(self.finished(1), [self.now + timedelta(minutes=20), self.now + timedelta(minutes=40)])

    def test_new_day_settles_before_first_new_day_action_and_syncs_newcomers(self):
        """无需参数；跨日时先日结再执行当天首个行动，日结新增的角色在输入前进入队列；无返回值。"""
        midnight = datetime(2026, 3, 2)

        def new_day():
            """无需参数，日结时登记新角色；返回 None。"""
            self.new_day()
            self.characters[2] = SimpleNamespace(behavior=Behavior(), target_character_id=2, state="idle", dead=False, sp_flag=SimpleNamespace(see_pl_h=False, is_h=False), hypnosis=SimpleNamespace(blockhead=False))
            self.cache.npc_id_got.add(2)

        with patch.object(sys.modules["Script.Settle.past_day_settle"], "update_new_day", side_effect=new_day):
            runtime = self.advance("sleep", 15 * 60)
        days = [index for index, event in enumerate(self.events) if event[0] == "day"]
        self.assertEqual([self.events[index][1] for index in days], [midnight])
        first_new_day_settle = next(index for index, event in enumerate(self.events) if event[0] == "settle" and self.cache.game_time >= midnight and index > days[0])
        self.assertLess(days[0], first_new_day_settle)
        self.assertEqual(self.settled(2), ["wait"])
        self.assertEqual(runtime.scheduler.pending(2).at, datetime(2026, 3, 2, 1))

    def test_departed_npc_is_dropped_before_choice_and_returns_by_sync(self):
        """无需参数；离队 NPC 在选择前撤销待办，归队时重新加入；无返回值。"""
        runtime = self.game.get_runtime()

        def settle(actor):
            """输入角色，玩家结算时让 NPC 离队；返回 None。"""
            self.events.append(("settle", actor, self.characters[actor].behavior.behavior_id))
            if actor == 0:
                self.cache.npc_id_got.discard(1)

        with patch.object(sys.modules["Script.Design.character_behavior"], "judge_character_status", side_effect=settle):
            self.write_behavior(0, "send", 10)
            runtime.advance(10)
        self.assertIsNone(runtime.scheduler.pending(1))
        self.assertEqual(self.settled(1), [])
        self.cache.npc_id_got.add(1)
        self.advance("wait", 5)
        self.assertEqual(self.settled(1), ["wait"])

    def test_reset_character_cancels_offline_and_restarts_online(self):
        """无需参数；下线撤销待办，上线后进行中的行为到期时再自主选择；无返回值。"""
        self.assertIsNone(self.game.reset_character(1))
        runtime = self.advance("wait", 5)
        self.assertEqual(runtime.scheduler.pending(1).at, self.now + timedelta(minutes=60))
        self.cache.npc_id_got.discard(1)
        self.game.reset_character(1)
        self.assertIsNone(runtime.scheduler.pending(1))
        self.cache.npc_id_got.add(1)
        self.game.reset_character(1)
        self.assertEqual(runtime.scheduler.pending(1), Task(1, self.now + timedelta(minutes=60), AI))

    def test_departing_during_own_action_leaves_no_successor(self):
        """无需参数；NPC 在自己的行动结算中离队时不再安排后续；无返回值。"""
        runtime = self.game.get_runtime()

        def settle(actor):
            """输入角色，NPC 结算时离队；返回 None。"""
            self.events.append(("settle", actor, self.characters[actor].behavior.behavior_id))
            if actor == 1:
                self.cache.npc_id_got.discard(1)

        with patch.object(sys.modules["Script.Design.character_behavior"], "judge_character_status", side_effect=settle):
            self.write_behavior(0, "wait", 120)
            runtime.advance(120)
        self.assertEqual(self.settled(1), ["wait"])
        self.assertIsNone(runtime.scheduler.pending(1))

    def test_dead_npc_is_skipped(self):
        """无需参数；死亡角色不建队，执行时不结算；无返回值。"""
        self.characters[1].dead = True
        runtime = self.game.get_runtime()
        self.assertIsNone(runtime.scheduler.pending(1))
        self.assertEqual(runtime.execute(1, Action("wait", 5, 1)), 5)
        self.assertEqual(self.events, [])

    def test_advance_while_running_forces_player_action(self):
        """无需参数；执行中再次提交玩家行动时作为立即后续替换输入；无返回值。"""
        runtime = self.game.get_runtime()

        def settle(actor):
            """输入角色，NPC 结算时为玩家追加反应行动；返回 None。"""
            self.events.append(("settle", actor, self.characters[actor].behavior.behavior_id))
            if actor == 1:
                self.write_behavior(0, "reaction", 3)
                runtime.advance(3)

        with patch.object(sys.modules["Script.Design.character_behavior"], "judge_character_status", side_effect=settle):
            self.advance("wait", 1)
        self.assertEqual(self.settled(0), ["wait", "reaction"])
        self.assertEqual(self.cache.game_time, self.now + timedelta(minutes=3))

    def test_continuation_runs_after_player_action_ends_and_chains(self):
        """无需参数；结算中登记的接续在玩家行动收尾后、回到输入前执行，接续提交的行动从该时刻立即开始，接续中再登记的接续留到下一段结束；无返回值。"""
        runtime = self.game.get_runtime()

        def walk(step):
            """输入段号，记录接续时刻与玩家行为，写入下一段并在其结束后继续；返回 None。"""
            self.events.append(("continue", step, self.cache.game_time, self.characters[0].behavior.behavior_id))
            if step > 3:
                return
            self.write_behavior(0, "leg%d" % step, step)
            runtime.advance(step)
            self.game.continue_after(partial(walk, step + 1))

        def settle(actor):
            """输入角色，玩家的指令结算中开始分段行走；返回 None。"""
            self.events.append(("settle", actor, self.characters[actor].behavior.behavior_id, self.cache.game_time))
            if actor == 0 and self.characters[0].behavior.behavior_id == "order":
                walk(1)

        with patch.object(sys.modules["Script.Design.character_behavior"], "judge_character_status", side_effect=settle):
            self.advance("order", 10)
        minute = lambda n: self.now + timedelta(minutes=n)
        self.assertEqual([event[1:] for event in self.events if event[0] == "settle" and event[1] == 0], [(0, "order", minute(0)), (0, "leg1", minute(0)), (0, "leg2", minute(1)), (0, "leg3", minute(3))])
        self.assertEqual([event[1:] for event in self.events if event[0] == "continue"], [(1, minute(0), "order"), (2, minute(1), "idle"), (3, minute(3), "idle"), (4, minute(6), "idle")])
        self.assertEqual(self.finished(0), [minute(1), minute(3), minute(6)])
        self.assertEqual(self.cache.game_time, minute(6))

    def test_pathing_started_in_settlement_walks_leg_by_leg_to_the_target(self):
        """无需参数；结算中调用真实的玩家寻路时只排入当前一段，余下各段在每段走完后接续，直到抵达目标才回到输入；无返回值。"""
        runtime = self.game.get_runtime()
        constant = sys.modules["Script.Core.constant"]
        constant.CharacterStatus.STATUS_MOVE = "move"
        constant.Panel = SimpleNamespace(SEE_MAP="map", IN_SCENE="scene")
        player = self.characters[0]
        player.position = ["start"]
        player.sp_flag.move_stop = False
        player.sp_flag.hidden_sex_mode = 0
        path = [["start"], ["a"], ["b"], ["end"]]
        stubs = {name: ModuleType(name) for name in ("Script.Design.map_handle", "Script.Design.update", "Script.UI.Moudle", "Script.UI.Moudle.draw")}
        stubs["Script.Design.update"].game_update_flow = runtime.advance
        stubs["Script.UI.Moudle.draw"].NormalDraw = SimpleNamespace
        patcher = patch.dict(sys.modules, stubs)
        patcher.start()
        self.addCleanup(patcher.stop)
        sys.modules["Script.Design"].__path__ = [str(Path(__file__).resolve().parents[1] / "Script/Design")]
        sys.modules.pop("Script.Design.character_move", None)
        move = importlib.import_module("Script.Design.character_move")
        queries = []

        def next_leg(actor, target):
            """输入角色与目标，记录查询时刻并给出通往下一场景的一段路；返回 (通行状态, 路径, 下一场景, 耗时)。"""
            queries.append(self.cache.game_time)
            return "open", path, path[path.index(player.position) + 1], 1

        def finish(actor, now, end_now=2):
            """输入角色与收尾时刻，照游戏本体的做法在收尾后保留移动的最终目标；返回 True。"""
            final_target = getattr(self.characters[actor].behavior, "move_final_target", [])
            result = self.finish(actor, now, end_now)
            self.characters[actor].behavior.move_final_target = final_target
            return result

        def settle(actor):
            """输入角色，玩家的指令结算触发寻路，移动段结算时把玩家挪到该段终点；返回 None。"""
            self.events.append(("settle", actor, self.characters[actor].behavior.behavior_id))
            if actor == 0 and player.behavior.behavior_id == "order":
                move.own_charcter_move(["end"])
            elif actor == 0 and player.behavior.behavior_id == "move":
                player.position = player.behavior.move_target

        behavior_module = sys.modules["Script.Design.character_behavior"]
        with patch.object(move, "character_move", side_effect=next_leg), patch.object(behavior_module, "judge_character_status", side_effect=settle), patch.object(behavior_module, "judge_character_status_time_over", side_effect=finish):
            self.advance("order", 10)
        self.assertEqual(player.position, ["end"])
        self.assertEqual(self.settled(0), ["order", "move", "move", "move"])
        self.assertEqual(queries, [self.now + timedelta(minutes=n) for n in (0, 1, 2)])
        self.assertEqual(self.cache.game_time, self.now + timedelta(minutes=3))
        self.assertEqual(self.cache.now_panel_id, "scene")
        self.assertEqual(list(runtime._continuations), [])

    def test_player_move_resets_h_sight_and_records_instruction(self):
        """无需参数；玩家移动时清除 NPC 的目击标记并记录指令；无返回值。"""
        self.characters[1].sp_flag.see_pl_h = True
        self.advance("move", 5)
        self.assertFalse(self.characters[1].sp_flag.see_pl_h)
        self.assertEqual(self.cache.pl_pre_behavior_instruce, ["move"])
        self.assertEqual(self.cache.daily_intsruce, 1)


if __name__ == "__main__":
    unittest.main()
