"""群体意图只选择，执行阶段才更新模板。"""

from copy import deepcopy
from datetime import datetime
import importlib.util
import pickle
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch


from Script.Modules.action import Action


class DecisionMask:
    """测试中保存自身需求位的轻量记录。"""

    def __init__(self, initial=None):
        """输入可选旧记录，初始化需求字典；返回 None。"""
        self.bits = dict(initial or {})

    def update(self, index, active):
        """输入需求编号与状态，保存该需求；返回 None。"""
        self.bits[index] = active


class GroupIntentTests(unittest.TestCase):
    """以真实群体模块检查候选、决策和模板执行的边界。"""

    def setUp(self):
        """无需参数，安装最小外围环境并加载真实模块；返回 None。"""
        self.characters = {
            actor: SimpleNamespace(
                behavior=SimpleNamespace(behavior_id="idle", duration=0),
                state="idle",
                target_character_id=7,
                sp_flag=SimpleNamespace(is_h=True, masturebate=0, unnormal_flag=DecisionMask()),
                h_state=SimpleNamespace(group_sex_body_template_dict={"A": [{"mouth": [-1, -1]}, [[], -1]]}),
            )
            for actor in (0, 1)
        }
        self.cache = SimpleNamespace(character_data=self.characters, game_time=datetime(2026, 1, 1))
        self.premise = SimpleNamespace(
            handle_group_sex_mode_off=lambda actor: False,
            handle_normal_6=lambda actor, **kwargs: True,
            handle_npc_ai_type_1_in_group_sex=lambda actor: False,
            handle_npc_ai_type_2_in_group_sex=lambda actor: True,
            handle_self_now_bondage=lambda actor: False,
        )
        self.panel = SimpleNamespace(
            count_group_sex_character_list=lambda: [],
            get_now_template_part_list=lambda: (["mouth", "加入侍奉"], []),
            get_status_id_list_from_group_sex_body_part=Mock(return_value=[11, 12]),
        )
        self.target_selector = Mock(return_value=Action("wait", 5, 1))
        modules = {}
        for name in ("Script.Core", "Script.Design", "Script.System", "Script.System.Sex_System"):
            modules[name] = ModuleType(name)
            modules[name].__path__ = []
        modules["Script.Core"].cache_control = SimpleNamespace(cache=self.cache)
        modules["Script.Core"].constant = SimpleNamespace(
            Behavior=SimpleNamespace(SHARE_BLANKLY="idle", WAIT="wait", SLEEP="sleep"), CharacterStatus=SimpleNamespace(STATUS_WAIT="wait")
        )
        modules["Script.Core"].game_type = SimpleNamespace(UnnormalFlagMask=DecisionMask)
        modules["Script.Core"].get_text = SimpleNamespace(_=lambda text: text)
        modules["Script.Design"].handle_premise = self.premise
        modules["Script.Design"].handle_npc_ai = SimpleNamespace(choose_character_target=self.target_selector)
        modules["Script.System.Sex_System"].group_sex_panel = self.panel
        environment = patch.dict(sys.modules, modules)
        environment.start()
        self.addCleanup(environment.stop)
        name = "_group_intent_test_subject"
        spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / "Script/Modules/group_intent.py")
        self.group = importlib.util.module_from_spec(spec)
        sys.modules[name] = self.group
        self.addCleanup(sys.modules.pop, name, None)
        spec.loader.exec_module(self.group)

    def test_prepare_preserves_player_target_on_failure(self):
        """候选查询失败也不写玩家目标；返回 None。"""
        self.panel.get_status_id_list_from_group_sex_body_part.side_effect = RuntimeError("query")
        with self.assertRaisesRegex(RuntimeError, "query"):
            self.group.prepare_group_options(1)
        self.assertEqual(self.characters[0].target_character_id, 7)

    def test_prepare_reads_candidates_for_actor_without_target_write(self):
        """查询使用当前 NPC，返回后玩家数据保持原样；返回 None。"""
        seen = []

        def candidates(body_part, *, target_id):
            """输入部位，记录查询目标并返回候选编号。"""
            seen.append((body_part, target_id, self.characters[0].target_character_id))
            return [11, 12]

        self.panel.get_status_id_list_from_group_sex_body_part.side_effect = candidates
        options = self.group.prepare_group_options(1)
        self.assertEqual(seen, [("mouth", 1, 7)])
        self.assertEqual(options.empty_parts, ("mouth", "加入侍奉"))
        self.assertEqual(options.statuses, {"mouth": (11, 12)})
        self.assertEqual(self.characters[0].target_character_id, 7)

    def test_choice_does_not_write_template_or_npc_state(self):
        """选择先抽部位再抽动作，角色数据保持原样；返回 None。"""
        before = deepcopy(self.characters)
        options = self.group.GroupOptions(("mouth", "加入侍奉"), {"mouth": (11, 12)})
        with patch.object(self.group.random, "choice", side_effect=["mouth", 12]) as choose:
            result = self.group.choose_group_action(1, options)
        self.assertEqual(choose.call_args_list, [call(options.empty_parts), call((11, 12))])
        self.assertIs(type(result), Action)
        self.assertEqual(pickle.loads(pickle.dumps(result)), result)
        self.assertEqual(result, Action("group_fill", 0, 0, params={"body_part": "mouth", "status_id": 12}))
        for actor in self.characters:
            self.assertEqual(vars(self.characters[actor].behavior), vars(before[actor].behavior))
            self.assertEqual(self.characters[actor].h_state, before[actor].h_state)
            self.assertEqual(self.characters[actor].target_character_id, before[actor].target_character_id)

    def test_empty_selected_part_does_not_choose_another(self):
        """抽中无可用动作的部位时维持原行为，保持原选择概率；返回 None。"""
        options = self.group.GroupOptions(("mouth", "加入侍奉"), {"mouth": ()})
        with patch.object(self.group.random, "choice", return_value="mouth") as choose:
            result = self.group.choose_group_action(1, options)
        choose.assert_called_once_with(options.empty_parts)
        self.assertIs(type(result), Action)
        self.assertEqual(result, Action("wait", 5, 1, state="wait"))

    def test_join_and_existing_fallback_are_plain_serializable_actions(self):
        """输入加入及无候选分支，返回可存档 Action 且不改写世界；无返回值。"""
        for existing in (False, True):
            if existing:
                self.characters[1].behavior.behavior_id = "existing"
                self.characters[1].behavior.duration = 9
            before = pickle.dumps(self.cache)
            for part, expected in (
                ("加入侍奉", Action("group_join", 0, 0)),
                ("mouth", Action.from_character(self.characters[1]) if existing else Action("wait", 5, 1, state="wait")),
            ):
                with self.subTest(existing=existing, part=part), patch.object(self.group.random, "choice", return_value=part):
                    result = self.group.choose_group_action(1, self.group.GroupOptions((part,), {"mouth": ()}))
                    self.assertIs(type(result), Action)
                    self.assertEqual(pickle.loads(pickle.dumps(result)), expected)
                    self.assertEqual(pickle.dumps(self.cache), before)

    def test_masturbation_records_own_need_then_selects(self):
        """两种自慰条件均只记录自身需求，并交给目标选择器；返回 None。"""
        for options in (self.group.GroupOptions((), {}), self.group.GroupOptions(("mouth",), {}, True)):
            with self.subTest(options=options):
                player_template = deepcopy(self.characters[0].h_state)
                result = self.group.choose_group_action(1, options)
                self.assertIs(result, self.target_selector.return_value)
                self.assertEqual(self.characters[1].sp_flag.masturebate, 3)
                self.assertTrue(self.characters[1].sp_flag.unnormal_flag.bits[1])
                self.assertEqual(self.characters[1].behavior.behavior_id, "idle")
                self.assertEqual(self.characters[1].state, "idle")
                self.assertEqual(self.characters[0].sp_flag.masturebate, 0)
                self.assertEqual(self.characters[0].h_state, player_template)
                self.assertEqual(self.characters[0].target_character_id, 7)
        self.assertEqual(self.target_selector.call_args_list, [call(1, self.cache.game_time)] * 2)

    def test_execute_fills_template_and_preserves_existing_behavior(self):
        """补位更新模板，保留原非闲置行动；返回 None。"""
        self.characters[1].behavior.behavior_id = "existing"
        self.characters[1].behavior.duration = 9
        self.group.execute_group_action(1, Action("group_fill", 0, 0, params={"body_part": "mouth", "status_id": 12}))
        self.assertEqual(self.characters[0].h_state.group_sex_body_template_dict["A"][0]["mouth"], [1, 12])
        self.assertEqual(self.characters[1].behavior.behavior_id, "existing")
        self.assertEqual(self.characters[1].behavior.duration, 9)

    def test_execute_join_prepares_idle_wait(self):
        """加入侍奉后闲置 NPC 等待五分钟；返回 None。"""
        self.group.execute_group_action(1, Action("group_join", 0, 0))
        self.assertEqual(self.characters[0].h_state.group_sex_body_template_dict["A"][1][0], [1])
        self.assertEqual(self.characters[1].behavior.behavior_id, "wait")
        self.assertEqual(self.characters[1].behavior.duration, 5)
        self.assertEqual(self.characters[1].target_character_id, 1)

    def test_real_candidate_chain_uses_explicit_target_without_writes(self):
        """隔离导入真实查询函数链，检查不同目标、逆推跳过及未知异常缓存均无写入；返回 None。"""
        import ast
        import pickle
        from inspect import signature
        from typing import Callable, Iterable, Optional

        root = Path(__file__).resolve().parents[1]
        functions = {}
        for path in (root / "Script/Design/handle_premise").glob("*.py"):
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, ast.FunctionDef):
                    functions[node.name] = node
        names = {
            "handle_premise", "handle_have_target", "handle_t_is_h", "handle_t_technique_ge_3", "handle_t_technique_ge_5",
            "handle_t_npc_active_h", "handle_t_npc_not_active_h", "handle_t_normal_5_6_or_unconscious_flag_4_7",
            "handle_normal_1", "handle_normal_2", "handle_normal_3", "handle_normal_4", "handle_normal_5", "handle_normal_6", "handle_normal_7",
        }
        # 跟随真实函数的依赖，省去模块导入时的 GUI 与指令线程副作用。
        while True:
            dependencies = {
                call_node.func.id
                for name in names
                for call_node in ast.walk(functions[name])
                if isinstance(call_node, ast.Call) and isinstance(call_node.func, ast.Name) and call_node.func.id in functions
            }
            if dependencies <= names:
                break
            names |= dependencies
        constant = sys.modules["Script.Core"].constant
        constant.InstructType = SimpleNamespace(SEX="sex")
        constant.behavior_id_to_instruct_id = {status: status for status in (11, 12, 13, 14)}
        constant.instruct_premise_data = {
            11: ("have_target", "t_is_h", "t_technique_ge_3"),
            12: ("t_technique_ge_5",),
            13: ("t_normal_5_6_or_unconscious_flag_4_7",),
            14: ("t_npc_not_active_h",),
        }
        self.cache.instruct_index_filter = {}
        self.cache.debug_mode = False
        self.cache.time_stop_mode = False
        self.characters[7] = deepcopy(self.characters[1])
        for actor, character in self.characters.items():
            character.ability = {30: 3 if actor == 1 else 0}
            character.sleep_point = 0
            character.sp_flag.unnormal_flag = {}
            character.sp_flag.unconscious_h = 0
            character.h_state.npc_active_h = actor == 1
        premise_module = ModuleType("Script.Design.handle_premise")
        namespace = premise_module.__dict__
        namespace.update(
            cache=self.cache, constant=constant, signature=signature, game_type=SimpleNamespace(Character=SimpleNamespace, UnnormalFlagMask=DecisionMask),
            Callable=Callable, Iterable=Iterable, Optional=Optional, _UNNORMAL_FLAG_HANDLERS={},
            UNNORMAL_FLAG_BITS={index: 1 << (index - 1) for index in range(1, 8)},
            attr_calculation=SimpleNamespace(get_sleep_level=lambda point: (0, 0)),
        )
        names.discard("add_premise")
        selected = [deepcopy(functions[name]) for name in names]
        for node in selected:
            node.decorator_list = []
        exec(compile(ast.Module(body=selected, type_ignores=[]), "real_premise_query", "exec"), namespace)
        constant.handle_premise_data = {
            premise: namespace["handle_" + premise]
            for premises in constant.instruct_premise_data.values()
            for premise in premises
        }
        constant.instruct_premise_data[11] += ("CVP_A2_A|30_GE_3",)
        instruct_module = ModuleType("Script.System.Instruct_System")
        instruct_module.__path__ = []
        filters = ModuleType("Script.System.Instruct_System.see_instruct_panel")
        instruct_module.see_instruct_panel = filters
        filters.__dict__.update(cache=self.cache, constant=constant, handle_premise=premise_module)
        panel_namespace = {
            "cache": self.cache, "constant": constant, "_": lambda text: text,
            "game_config": SimpleNamespace(
                config_behavior_id_list_of_group_sex_body_part={"口": [11, 12, 13, 14]},
                config_behavior={status: SimpleNamespace(tag="口") for status in (11, 12, 13, 14)},
            ),
        }
        for relative, function_name, environment in (
            ("Script/System/Instruct_System/see_instruct_panel.py", "judge_single_instruct_filter", filters.__dict__),
            ("Script/System/Sex_System/group_sex_panel.py", "get_status_id_list_from_group_sex_body_part", panel_namespace),
        ):
            node = next(node for node in ast.parse((root / relative).read_text()).body if isinstance(node, ast.FunctionDef) and node.name == function_name)
            exec(compile(ast.Module(body=[node], type_ignores=[]), relative, "exec"), environment)
        self.panel.get_status_id_list_from_group_sex_body_part = panel_namespace["get_status_id_list_from_group_sex_body_part"]
        self.premise.handle_normal_6 = namespace["handle_normal_6"]
        drunk = SimpleNamespace(get_drunk_level=lambda actor: (0, 0))
        with patch.dict(sys.modules, {"Script.System.Instruct_System": instruct_module, "Script.Design.handle_premise": premise_module}), patch.object(
            sys.modules["Script.System.Sex_System"], "drunk_sex_common", drunk, create=True
        ):
            before = pickle.dumps(self.cache)
            options = self.group.prepare_group_options(1)
            self.assertEqual(options.statuses["mouth"], (11, 13, 14))
            # 同一真实查询链对另一个显式目标应给出不同候选。
            self.assertEqual(self.panel.get_status_id_list_from_group_sex_body_part("mouth", target_id=7), [13, 14])
            self.assertEqual(pickle.dumps(self.cache), before)
            # 玩家原目标和 NPC 的旧式异常缓存也未被临时替换。
            self.assertEqual(self.characters[0].target_character_id, 7)
            self.assertEqual(self.characters[1].sp_flag.unnormal_flag, {})
