"""群体意图只选择，执行阶段才更新模板。"""

from copy import deepcopy
from datetime import datetime
import ast
import random
import pickle
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch


from Script.Modules.scheduler.action import Action
from Script.Core.game_type import UnnormalFlagMask


class GroupIntentTests(unittest.TestCase):
    """以真实群体模块检查候选、决策和模板执行的边界。"""

    def setUp(self):
        """无需参数，安装最小外围环境并加载真实模块；返回 None。"""
        self.characters = {
            actor: SimpleNamespace(
                behavior=SimpleNamespace(behavior_id="idle", duration=0),
                state="idle",
                target_character_id=7,
                sp_flag=SimpleNamespace(is_h=True, masturebate=0, unnormal_flag=UnnormalFlagMask()),
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
        modules["Script.Core"].game_type = SimpleNamespace(UnnormalFlagMask=UnnormalFlagMask)
        modules["Script.Core"].get_text = SimpleNamespace(_=lambda text: text)
        modules["Script.Design"].handle_premise = self.premise
        modules["Script.Design"].handle_npc_ai = SimpleNamespace(choose_character_target=self.target_selector)
        modules["Script.System.Sex_System"].group_sex_panel = self.panel
        environment = patch.dict(sys.modules, modules)
        environment.start()
        self.addCleanup(environment.stop)
        # 原文件还包含界面与结算入口；只加载受测函数及其真实源码依赖。
        source = Path(__file__).resolve().parents[1] / "Script/Design/handle_npc_ai_in_h.py"
        tree = ast.parse(source.read_text())
        names = {"npc_ai_in_group_sex", "execute_group_action"}
        tree.body = [node for node in tree.body if getattr(node, "name", None) in names]
        self.group = ModuleType("_group_action_test_subject")
        self.group.__dict__.update(vars(modules["Script.Core"]), Action=Action, random=random, cache=self.cache, handle_premise=self.premise, _=lambda text: text)
        sys.modules[self.group.__name__] = self.group
        self.addCleanup(sys.modules.pop, self.group.__name__, None)
        exec(compile(tree, str(source), "exec"), self.group.__dict__)

    def test_choice_queries_selected_part_without_world_writes(self):
        """成功或失败的候选查询只查抽中部位，保留玩家及 NPC 行为；返回 None。"""
        self.panel.get_now_template_part_list = lambda: (["mouth", "other", "加入侍奉"], [])
        for failure in (False, True):
            with self.subTest(failure=failure):
                before = pickle.dumps(self.cache)
                self.panel.get_status_id_list_from_group_sex_body_part.reset_mock()
                self.panel.get_status_id_list_from_group_sex_body_part.side_effect = RuntimeError("query") if failure else None
                with patch.object(self.group.random, "choice", side_effect=["mouth", 12]) as choose:
                    if failure:
                        with self.assertRaisesRegex(RuntimeError, "query"):
                            self.group.npc_ai_in_group_sex(1)
                    else:
                        result = self.group.npc_ai_in_group_sex(1)
                        self.assertIs(type(result), Action)
                        self.assertEqual(pickle.loads(pickle.dumps(result)), Action("group_fill", 0, 0, params={"body_part": "mouth", "status_id": 12}))
                        self.assertEqual(choose.call_args_list, [call(["mouth", "other", "加入侍奉"]), call([11, 12])])
                self.panel.get_status_id_list_from_group_sex_body_part.assert_called_once_with("mouth", target_id=1)
                self.assertEqual(pickle.dumps(self.cache), before)

    def test_join_and_unavailable_actions_preserve_existing_behavior(self):
        """加入无需查询动作，无候选交回外层且不重选部位；返回 None。"""
        self.panel.get_status_id_list_from_group_sex_body_part.return_value = []
        for existing in ("idle", "existing", "wait"):
            self.characters[1].behavior.behavior_id = existing
            self.characters[1].behavior.duration = 9
            before = pickle.dumps(self.cache)
            for part, expected in (("加入侍奉", Action("group_join", 0, 0)), ("mouth", None)):
                with self.subTest(existing=existing, part=part), patch.object(self.group.random, "choice", return_value=part) as choose:
                    self.panel.get_status_id_list_from_group_sex_body_part.reset_mock()
                    result = self.group.npc_ai_in_group_sex(1)
                    choose.assert_called_once_with(["mouth", "加入侍奉"])
                    self.assertEqual(result, expected)
                    self.assertEqual(pickle.dumps(self.cache), before)
                    if part == "加入侍奉":
                        self.panel.get_status_id_list_from_group_sex_body_part.assert_not_called()

        self.characters[1].sp_flag.is_h = False
        self.panel.count_group_sex_character_list = Mock(side_effect=AssertionError("非 H 角色不读模板"))
        self.assertIsNone(self.group.npc_ai_in_group_sex(1))
        self.panel.count_group_sex_character_list.assert_not_called()

    def test_masturbation_records_own_need_then_selects(self):
        """两种自慰条件均只记录自身需求，并交给目标选择器；返回 None。"""
        # 加载原需求刷新函数及真实判定依赖，验证它只更新本角色的需求记录。
        from typing import Callable, Optional

        namespace = dict(cache=self.cache, game_type=SimpleNamespace(Character=SimpleNamespace, UnnormalFlagMask=UnnormalFlagMask), Callable=Callable, Optional=Optional)
        names = {"settle_chara_unnormal_flag", "_ensure_unnormal_flag_storage", "_get_unnormal_flag_handlers", "_quick_check_normal_by_mask", "handle_normal_1",
                 "handle_rest_flag_1", "handle_sleep_flag_1", "handle_pee_flag_1", "handle_eat_food_flag_ge_1", "handle_shower_flag_123", "handle_milk_flag_1", "handle_masturebate_flag_g_0"}
        for filename in ("__init__.py", "handle_premise_sp_flag.py"):
            tree = ast.parse((Path(__file__).resolve().parents[1] / "Script/Design/handle_premise" / filename).read_text())
            tree.body = [node for node in tree.body if getattr(node, "name", None) in names]
            for node in tree.body:
                node.decorator_list = []
            exec(compile(tree, filename, "exec"), namespace)
        namespace["_UNNORMAL_FLAG_HANDLERS"] = {1: namespace["handle_normal_1"]}
        self.premise.settle_chara_unnormal_flag = namespace["settle_chara_unnormal_flag"]
        for field in ("rest", "sleep", "pee", "eat_food", "help_buy_food", "help_make_food", "shower", "milk", "npc_masturebate_for_player"):
            setattr(self.characters[1].sp_flag, field, 0)
        for only in (False, True):
            with self.subTest(only=only):
                self.premise.handle_npc_ai_type_1_in_group_sex = lambda actor: only
                self.panel.get_now_template_part_list = lambda: (["mouth"] if only else [], [])
                player_before = pickle.dumps(self.characters[0])
                self.characters[1].sp_flag.unnormal_flag = {1: False, 2: True}
                result = self.group.npc_ai_in_group_sex(1)
                self.assertIs(result, self.target_selector.return_value)
                self.assertEqual(self.characters[1].sp_flag.masturebate, 3)
                self.assertTrue(self.characters[1].sp_flag.unnormal_flag[1])
                self.assertTrue(self.characters[1].sp_flag.unnormal_flag[2])
                self.assertEqual(self.characters[1].behavior.behavior_id, "idle")
                self.assertEqual(self.characters[1].state, "idle")
                self.assertEqual(pickle.dumps(self.characters[0]), player_before)
        self.panel.get_status_id_list_from_group_sex_body_part.assert_not_called()
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
        """隔离导入真实查询函数链，检查不同目标、逆推跳过以及派生缓存仅写决策角色自身；返回 None。"""
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
            cache=self.cache, constant=constant, signature=signature, game_type=SimpleNamespace(Character=SimpleNamespace, UnnormalFlagMask=UnnormalFlagMask),
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
            before = pickle.dumps([self.characters[0], self.characters[7]])
            own_before = pickle.dumps({key: value for key, value in vars(self.characters[1]).items() if key != "sp_flag"})
            with patch.object(self.group.random, "choice", side_effect=["mouth", 11]):
                result = self.group.npc_ai_in_group_sex(1)
            self.assertEqual(result.params, {"body_part": "mouth", "status_id": 11})
            self.assertEqual(self.panel.get_status_id_list_from_group_sex_body_part("mouth", target_id=1), [11, 13, 14])
            self.assertEqual(pickle.dumps([self.characters[0], self.characters[7]]), before)
            self.assertEqual(pickle.dumps({key: value for key, value in vars(self.characters[1]).items() if key != "sp_flag"}), own_before)
            self.assertIsInstance(self.characters[1].sp_flag.unnormal_flag, UnnormalFlagMask)
            # 改查另一名 NPC 时，原 NPC 与玩家数据均保留。
            before = pickle.dumps([self.characters[0], self.characters[1]])
            self.assertEqual(self.panel.get_status_id_list_from_group_sex_body_part("mouth", target_id=7), [13, 14])
            self.assertEqual(pickle.dumps([self.characters[0], self.characters[1]]), before)
            self.assertEqual(self.characters[0].target_character_id, 7)
