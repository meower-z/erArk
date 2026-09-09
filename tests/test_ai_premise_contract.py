"""隔离外围依赖，运行真实前提与课堂选择函数检查只读契约。"""

import ast
import pickle
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from Script.Modules.action import Action
from Script.Modules.npc_actions import state_machine_action

ROOT = Path(__file__).resolve().parents[1]


def load_functions(path, names, **environment):
    """输入源文件、函数名集合和依赖字典，返回保留真实函数体的测试命名空间。"""
    source = ast.parse((ROOT / path).read_text())
    functions = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names]
    for node in functions:
        node.decorator_list = []
    namespace = {"__builtins__": __builtins__, **environment}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(ROOT / path), "exec"), namespace)
    return namespace


class AiPremiseContractTests(unittest.TestCase):
    """检查前提查询保留游戏数据，执行入口仍落实消耗。"""

    def test_dormitory_query_does_not_rewrite_residence(self):
        """输入旧宿舍地址，返回判断结果并保留原地址；无返回值。"""
        character = SimpleNamespace(dormitory="中枢/控制中枢", position=["中枢", "博士房间"])
        namespace = load_functions(
            "Script/Design/handle_premise/handle_premise_place.py",
            {"handle_in_dormitory", "get_character_dormitory_path"},
            cache=SimpleNamespace(character_data={1: character}),
            map_handle=SimpleNamespace(get_map_system_path_str_for_list=lambda value: "/".join(value), get_map_system_path_for_str=lambda value: value.split("/")),
            _=lambda value: value,
        )
        self.assertTrue(namespace["handle_in_dormitory"](1))
        self.assertEqual(character.dormitory, "中枢/控制中枢")

    def test_dormitory_execution_uses_same_normalized_path(self):
        """输入翻译后的宿舍地址，前提与移动意图采用同一路径；无返回值。"""
        character = SimpleNamespace(dormitory="Control/Dorm", position=["中枢", "博士房间"])
        paths = SimpleNamespace(get_map_system_path_str_for_list=lambda value: "/".join(value), get_map_system_path_for_str=lambda value: value.split("/"))
        cache = SimpleNamespace(character_data={1: character})
        predicates = load_functions(
            "Script/Design/handle_premise/handle_premise_place.py",
            {"get_character_dormitory_path", "handle_in_dormitory"},
            cache=cache,
            map_handle=paths,
            _=lambda value: "Control" if value == "中枢" else value,
        )
        moves = []
        execution = load_functions(
            "Script/StateMachine/default.py",
            {"character_move_to_dormitory"},
            cache=cache,
            map_handle=paths,
            handle_premise=SimpleNamespace(**predicates),
            general_movement_module=lambda actor, target: moves.append(target),
            _=lambda value: value,
        )
        with patch.dict("sys.modules", {"Script.System.Dormitory_System": SimpleNamespace(common=SimpleNamespace())}):
            execution["character_move_to_dormitory"](1)
        self.assertTrue(predicates["handle_in_dormitory"](1))
        self.assertEqual(moves, [["中枢", "博士房间"]])
        self.assertEqual(character.dormitory, "Control/Dorm")

    def test_missing_settings_are_read_without_insertion(self):
        """输入缺省配置，查询后字典仍为空；无返回值。"""
        settings = {}
        namespace = load_functions(
            "Script/Design/handle_premise/handle_premise_other.py",
            {"handle_ai_chat_on"},
            cache=SimpleNamespace(ai_setting=SimpleNamespace(ai_chat_setting=settings)),
        )
        self.assertEqual(namespace["handle_ai_chat_on"](1), 0)
        self.assertEqual(settings, {})

    def test_instruction_preview_keeps_sanity_and_target_state(self):
        """输入足够或不足的理智，预览保留双方状态，执行仍扣除消耗；无返回值。"""
        actor = SimpleNamespace(sanity_point=10, pl_ability=SimpleNamespace(hormone=False, today_sanity_point_cost=0), position=["room"], assistant_character_id=1, target_character_id=1)
        target = SimpleNamespace(
            cid=1,
            favorability={0: 0},
            trust=0,
            status_data=defaultdict(int),
            ability=defaultdict(int),
            talent=defaultdict(int),
            angry_point=0,
            h_state=SimpleNamespace(h_in_love_hotel=False),
            sp_flag=SimpleNamespace(npc_masturebate_for_player=False, unconscious_h=4),
            action_info=SimpleNamespace(h_interrupt=0),
        )
        premises = SimpleNamespace(
            handle_imprisonment_1=lambda actor: False,
            handle_unconscious_flag_1=lambda actor: False,
            handle_unconscious_flag_3=lambda actor: False,
            handle_self_has_been_complete_hypnosis=lambda actor: False,
            handle_self_has_been_primary_hypnosis=lambda actor: True,
            settle_chara_unnormal_flag=lambda *args: None,
        )
        namespace = load_functions(
            "Script/Design/instuct_judege.py",
            {"calculation_instuct_judege"},
            cache=SimpleNamespace(character_data={0: actor, 1: target}, scene_data={"room": SimpleNamespace(character_list={0, 1})}, debug_mode=False),
            game_config=SimpleNamespace(config_instruct_judge_data={0: SimpleNamespace(instruct_name="初级骚扰", need_type="S", value=50)}),
            attr_calculation=SimpleNamespace(get_favorability_level=lambda value: (0, 0), get_trust_level=lambda value: (0, 0), get_status_level=lambda value: 0, get_angry_level=lambda value: 0),
            map_handle=SimpleNamespace(get_map_system_path_str_for_list=lambda value: "/".join(value)),
            handle_premise=premises,
            _=lambda value: value,
        )
        calculate = namespace["calculation_instuct_judege"]
        fake_package = SimpleNamespace(drunk_sex_common=SimpleNamespace(get_drunk_level=lambda actor: (0, "")))
        with patch.dict("sys.modules", {"Script.System.Sex_System": fake_package}):
            self.assertEqual(calculate(0, 1, "初级骚扰", not_draw_flag=True, settle_cost=False)[0], 1)
            self.assertEqual((actor.sanity_point, actor.pl_ability.today_sanity_point_cost, target.sp_flag.unconscious_h), (10, 0, 4))
            calculate(0, 1, "初级骚扰", not_draw_flag=True)
            self.assertEqual((actor.sanity_point, actor.pl_ability.today_sanity_point_cost), (5, 5))
            actor.sanity_point = 0
            calculate(0, 1, "初级骚扰", not_draw_flag=True, settle_cost=False)
            self.assertEqual(target.sp_flag.unconscious_h, 4)
            calculate(0, 1, "初级骚扰", not_draw_flag=True)
            self.assertEqual(target.sp_flag.unconscious_h, 0)

    def test_exhausted_student_returns_absence_intent_without_settlement(self):
        """输入上课时体力不足的角色，返回缺课意图并保留统计；无返回值。"""
        character = SimpleNamespace(hit_point=1, hit_point_max=100, child_growth=None)
        namespace = load_functions(
            "Script/System/Education_System/class_ai.py",
            {"choose_class_intent"},
            Optional=__import__("typing").Optional,
            Action=Action,
            state_machine_action=state_machine_action,
            cache=SimpleNamespace(character_data={1: character}),
            schedule_handle=SimpleNamespace(get_now_course=lambda actor: {}),
            clear_follow_mother_flag=lambda actor: None,
            judge_must_attend_sex_class=lambda *args: False,
            education_constant=SimpleNamespace(ABSENT_HP_RATE=0.3),
            constant=SimpleNamespace(StateMachine=SimpleNamespace(REST=17)),
        )
        before = pickle.dumps(character)
        intent = namespace["choose_class_intent"](1)
        self.assertIs(type(intent), Action)
        self.assertEqual(pickle.loads(pickle.dumps(intent)), intent)
        self.assertEqual(pickle.dumps(character), before)
        self.assertEqual(intent.params["state_machine_id"], 17)
        self.assertTrue(intent.params["record_absence"])
        self.assertIsNone(character.child_growth)
