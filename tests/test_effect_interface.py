"""结算接口测试。用标准库隔离加载生产函数，不启动界面或指令线程。"""

import ast
import datetime
import inspect
import sys
import unittest
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from typing import Optional, Union
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Script.Core import constant_effect, game_type


def load_functions(path, namespace, predicate):
    """输入文件路径、命名空间和筛选函数；编译生产函数，返回函数名列表。"""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and predicate(node)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / path), "exec"), namespace)
    return [node.name for node in nodes]


def decorated_by(attr):
    """输入装饰器属性名；返回判断函数节点是否使用该装饰器的筛选函数。"""
    return lambda node: any(isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr == attr for item in node.decorator_list)


ordinary_effect = decorated_by("add_settle_behavior_effect")
second_effect = decorated_by("add_settle_second_behavior_effect")


def call_name(node):
    """输入调用节点；返回被调用的函数名，无法识别时返回None。"""
    return node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None


class EffectInterfaceTest(unittest.TestCase):
    """验证真实注册函数、显式目标以及目标在结算链中的传递。"""

    def setUp(self):
        """无输入和返回值；创建角色、注册表和隔离的生产函数环境。"""
        self.now = datetime.datetime(2026, 1, 1, 12)
        characters = {}
        for cid in range(4):
            character = game_type.Character()
            character.cid = cid
            character.target_character_id = (cid + 1) % 4
            character.behavior.start_time = self.now
            character.behavior.duration = 1
            character.event.skip_instruct_talk = True
            characters[cid] = character
        self.cache = SimpleNamespace(character_data=characters, time_stop_mode=False)
        self.constants = SimpleNamespace(settle_behavior_effect_data={}, settle_second_behavior_effect_data={}, Behavior=SimpleNamespace(TIME_STOP_OFF="time_stop_off"))
        self.config = SimpleNamespace(config_behavior_effect_data={}, config_behavior={}, config_event={})
        self.ns = {
            "cache": self.cache,
            "constant": self.constants,
            "constant_effect": constant_effect,
            "game_type": game_type,
            "datetime": datetime,
            "Optional": Optional,
            "Union": Union,
            "wraps": wraps,
            "game_config": self.config,
            "talk": SimpleNamespace(handle_talk=Mock()),
            "second_behavior": SimpleNamespace(check_second_effect=Mock()),
            "extra_exp_settle": Mock(),
            "game_time": SimpleNamespace(get_sub_date=lambda **kwargs: self.now),
            "_": lambda value: value,
        }
        load_functions("Script/Design/settle_behavior.py", self.ns, lambda node: node.name in {"add_settle_behavior_effect", "add_settle_second_behavior_effect", "handle_instruct_data", "handle_event_data", "settle_effect_list"})
        self.ns["settle_behavior"] = SimpleNamespace(add_settle_behavior_effect=self.ns["add_settle_behavior_effect"], add_settle_second_behavior_effect=self.ns["add_settle_second_behavior_effect"])
        self.effect_names = []
        for filename in ("default.py", "default_cloth.py", "item_effect.py"):
            self.effect_names.extend(load_functions("Script/Settle/" + filename, self.ns, ordinary_effect))
        self.effects = self.constants.settle_behavior_effect_data

    def test_registry_requires_explicit_target(self):
        """所有注册效果接受五个必填参数，且注册表保留原函数；无返回值。"""
        expected = ["character_id", "target_character_id", "add_time", "change_data", "now_time"]
        self.assertEqual(len(self.effects), len(self.effect_names))
        for effect in self.effects.values():
            with self.subTest(effect=effect.__name__):
                signature = inspect.signature(effect)
                self.assertEqual(list(signature.parameters), expected)
                self.assertTrue(all(param.default is inspect.Parameter.empty for param in signature.parameters.values()))
                with self.assertRaises(TypeError):
                    signature.bind(1, 1, game_type.CharacterStatusChange(), self.now)

    def test_second_effects_receive_explicit_target(self):
        """所有二段效果接受角色、目标、变化记录三个必填参数；无返回值。"""
        names = load_functions("Script/Settle/Second_effect.py", self.ns, second_effect)
        registry = self.constants.settle_second_behavior_effect_data
        self.assertEqual(len(registry), len(names))
        self.assertGreater(len(registry), 100)
        for effect in registry.values():
            with self.subTest(effect=effect.__name__):
                signature = inspect.signature(effect)
                self.assertEqual(list(signature.parameters), ["character_id", "target_character_id", "change_data"])
                self.assertTrue(all(param.default is inspect.Parameter.empty for param in signature.parameters.values()))

    def test_no_target_flag_or_sentinel_in_sources(self):
        """生产代码不再含目标开关或读取交互对象的哨兵字符串；无返回值。"""
        for path in (ROOT / "Script").rglob("*.py"):
            text = path.read_text(encoding="utf-8-sig")
            with self.subTest(path=str(path)):
                self.assertNotIn("CURRENT_TARGET", text)
                self.assertNotIn("target_flag", text)

    def test_helper_signatures_and_all_calls_bind(self):
        """辅助函数按受体或目标定义参数，所有生产调用与签名匹配；无返回值。"""
        recipient_only = {"base_chara_hp_mp_common_settle": "add_time", "base_chara_experience_common_settle": "experience_id", "base_chara_climix_common_settle": "part_id"}
        with_target = {
            "base_chara_favorability_and_trust_common_settle",
            "handle_comprehensive_value_effect", "extra_exp_settle",
            "handle_settle_behavior", "handle_instruct_data", "handle_event_data",
            "settle_effect_list", "handle_comprehensive_state_effect",
            "check_second_effect", "second_behavior_effect", "must_settle_check", "release_orgasm_edge_now",
            "recover_from_unconscious_h",
        }
        helper_names = set(recipient_only) | with_target
        for path in (
            "Script/Settle/common_default.py",
            "Script/Design/settle_behavior.py",
            "Script/System/Instruct_System/handle_instruct.py",
            "Script/Design/second_behavior.py",
            "Script/Settle/orgasm_settle.py",
            "Script/Design/handle_npc_ai_in_h.py",
        ):
            load_functions(path, self.ns, lambda node: node.name in helper_names)
        signatures = {name: inspect.signature(self.ns[name]) for name in helper_names}
        for name, second in recipient_only.items():
            self.assertEqual(list(signatures[name].parameters)[:2], ["character_id", second], name)
            self.assertNotIn("target_character_id", signatures[name].parameters, name)
        for name in with_target:
            self.assertEqual(list(signatures[name].parameters)[:2], ["character_id", "target_character_id"], name)
            self.assertIs(signatures[name].parameters["target_character_id"].default, inspect.Parameter.empty, name)
        checked = 0
        for path in (ROOT / "Script").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if not isinstance(node, ast.Call) or call_name(node) not in signatures:
                    continue
                with self.subTest(path=str(path), line=node.lineno):
                    signatures[call_name(node)].bind(*[object() for _ in node.args], **{k.arg: object() for k in node.keywords})
                checked += 1
        self.assertGreater(checked, 150)

    def test_direct_effect_calls_pass_five_arguments(self):
        """生产代码内直接调用普通效果时传递完整的五个参数；无返回值。"""
        names = set(self.effect_names)
        checked = 0
        for path in (ROOT / "Script").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            local_effects = {node.name for node in tree.body if isinstance(node, ast.FunctionDef) and ordinary_effect(node)}
            effect_modules = set()
            for imported in ast.walk(tree):
                if not isinstance(imported, ast.ImportFrom):
                    continue
                if imported.module in {"Script.Settle.default", "Script.Settle.default_cloth", "Script.Settle.item_effect"}:
                    for alias in imported.names:
                        local_effects.update(names if alias.name == "*" else [alias.asname or alias.name])
                elif imported.module == "Script.Settle":
                    effect_modules.update(alias.asname or alias.name for alias in imported.names if alias.name in {"default", "default_cloth", "item_effect"})
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = call_name(node)
                registry = isinstance(node.func, ast.Subscript) and ast.unparse(node.func.value) == "constant.settle_behavior_effect_data"
                if isinstance(node.func, ast.Name) and name not in local_effects:
                    continue
                if isinstance(node.func, ast.Attribute) and ast.unparse(node.func.value) not in effect_modules:
                    continue
                if name not in names and not registry:
                    continue
                with self.subTest(path=str(path), line=node.lineno):
                    self.assertEqual(len(node.args) + len(node.keywords), 5)
                checked += 1
        self.assertGreater(checked, 100)

    def test_target_effect_uses_supplied_target(self):
        """对目标的效果只修改传入的目标，不读取执行者的交互对象；无返回值。"""
        for character in self.cache.character_data.values():
            character.h_state.body_item = {2: [0, False]}
        self.cache.character_data[0].target_character_id = 1
        self.ns["handle_target_vibrator_on"](0, 2, 1, game_type.CharacterStatusChange(), self.now)
        self.assertEqual([character.h_state.body_item[2][1] for character in self.cache.character_data.values()], [False, False, True, False])
        self.assertEqual(self.cache.character_data[0].target_character_id, 1)

    def test_selector_result_reaches_following_effects(self):
        """选目标效果返回的id传给后续效果，零时长时保持原目标；无返回值。"""
        ids = constant_effect.BehaviorEffect
        self.constants.Behavior.MASTUREBATE = "masturebate"
        self.ns["map_handle"] = SimpleNamespace(get_map_system_path_str_for_list=lambda position: "room")
        self.cache.scene_data = {"room": SimpleNamespace(character_list=[0, 1, 2, 3])}
        self.cache.character_data[2].behavior.behavior_id = "masturebate"
        for cid, character in self.cache.character_data.items():
            character.desire_point = cid * 10
        seen = []
        self.effects[-1] = lambda cid, target, *args: seen.append(target)
        cases = [(ids.TARGET_TO_PLAYER, 0), (ids.TARGET_TO_SELF, 1), (ids.TARGET_TO_MASTUREBATE, 2), (ids.TARGET_TO_MOST_DESIRE, 3)]
        for effect_id, expected in cases:
            for duration in (0, 1):
                with self.subTest(effect=effect_id, duration=duration):
                    seen.clear()
                    self.cache.character_data[1].target_character_id = 0
                    target = self.ns["settle_effect_list"](1, 2, [-1, effect_id, -1], duration, game_type.CharacterStatusChange(), self.now)
                    self.assertEqual(target, expected if duration else 2)
                    self.assertEqual(seen, [2, expected if duration else 2])
                    self.assertEqual(self.cache.character_data[1].target_character_id, expected if duration else 0)

    def test_persistent_write_without_return_does_not_retarget(self):
        """未返回id的效果即使改写交互对象，后续效果仍收到传入目标；无返回值。"""
        seen = []
        self.effects[-1] = lambda cid, target, *args: seen.append(target)
        sequence = [-1, constant_effect.BehaviorEffect.PL_TARGET_TO_ME, -1]
        target = self.ns["settle_effect_list"](2, 1, sequence, 1, game_type.CharacterStatusChange(), self.now)
        self.assertEqual(seen, [1, 1])
        self.assertEqual(target, 1)
        self.assertEqual(self.cache.character_data[0].target_character_id, 2)

    def run_target_switch(self, event=False, facility=False):
        """输入事件和设施分支标志；执行真实效果切换顺序并断言结果，无返回值。"""
        ids = constant_effect.BehaviorEffect
        sequence = [ids.TARGET_TO_PLAYER, ids.TARGET_VIBRATOR_ON]
        for character in self.cache.character_data.values():
            character.h_state.body_item = {2: [0, False]}
        changes = game_type.CharacterStatusChange()
        if event:
            self.config.config_event["example"] = SimpleNamespace(effect=[str(item) for item in sequence])
            self.ns["handle_event_data"](1, 2, "example", 1, changes, self.now)
        else:
            self.config.config_behavior_effect_data["example"] = sequence
            if facility:
                self.config.config_behavior["example"] = SimpleNamespace(tag=["工作"])
                self.effects[1751] = Mock(return_value=None)
            self.ns["handle_instruct_data"](1, 2, "example", self.now, 1, changes)
            if facility:
                self.effects[1751].assert_called_once_with(1, 0, 1, changes, self.now)
        self.assertEqual(self.cache.character_data[1].target_character_id, 0)
        self.assertTrue(self.cache.character_data[0].h_state.body_item[2][1])
        self.assertFalse(self.cache.character_data[2].h_state.body_item[2][1])

    def test_instruction_target_switch(self):
        """指令效果间的选目标效果对后续效果生效；无返回值。"""
        self.run_target_switch()

    def test_event_target_switch(self):
        """事件效果间的选目标效果对后续效果生效；无返回值。"""
        self.run_target_switch(event=True)

    def test_facility_target_switch(self):
        """额外设施效果也接收结算后的目标；无返回值。"""
        self.run_target_switch(facility=True)

    def test_second_settlement_receives_targets_both_ways(self):
        """二段与额外经验结算收到显式目标，对方一侧以执行者为目标；无返回值。"""
        changes = game_type.CharacterStatusChange()
        self.ns["handle_instruct_data"](0, 2, "no_effects", self.now, 1, changes)
        target_change = changes.target_change[2]
        check = self.ns["second_behavior"].check_second_effect
        self.assertEqual(check.call_args_list[0].args, (0, 2, changes))
        self.assertEqual(check.call_args_list[1].args, (2, 0, target_change))
        self.assertEqual(check.call_args_list[1].kwargs, {"pl_to_npc": True})
        self.assertEqual([call.args for call in self.ns["extra_exp_settle"].call_args_list], [(0, 2, changes), (2, 0, target_change)])

    def load_hp_helper(self):
        """无输入；加载真实体力气力辅助函数并初始化角色数值，无返回值。"""
        self.ns["handle_premise"] = SimpleNamespace(handle_time_stop_on=lambda cid: False, handle_self_is_h=lambda cid: False, handle_group_sex_mode_on=lambda cid: False, handle_hidden_sex_mode_5=lambda cid: False)
        self.ns["handle_npc_ai"] = Mock()
        load_functions("Script/Settle/common_default.py", self.ns, lambda node: node.name == "base_chara_hp_mp_common_settle")
        for character in self.cache.character_data.values():
            character.hit_point = character.mana_point = 50
            character.hit_point_max = character.mana_point_max = 100

    def test_hp_helper_modifies_recipient_only(self):
        """体力气力辅助函数只修改第一个参数指定的受体，记录归属由调用方选择；无返回值。"""
        self.load_hp_helper()
        settle = self.ns["base_chara_hp_mp_common_settle"]
        changes = game_type.CharacterStatusChange()
        settle(1, 5, hp_value=-5, change_data=changes)
        settle(3, 5, hp_value=-5, change_data_to_target_change=changes)
        self.assertEqual([self.cache.character_data[cid].hit_point for cid in range(4)], [50, 45, 50, 45])
        self.assertEqual(changes.hit_point, -5)
        self.assertEqual(set(changes.target_change), {3})
        self.assertEqual(changes.target_change[3].hit_point, -5)

    def test_both_effect_settles_actor_and_target(self):
        """双方体力效果对执行者和目标各结算一次，目标为自身时只结算一次；无返回值。"""
        self.load_hp_helper()
        changes = game_type.CharacterStatusChange()
        self.ns["handle_sub_both_small_hit_point"](0, 2, 5, changes, self.now)
        self.assertEqual([self.cache.character_data[cid].hit_point for cid in range(4)], [45, 50, 45, 50])
        self.assertEqual(changes.hit_point, -5)
        self.assertEqual(set(changes.target_change), {2})
        self.assertEqual(changes.target_change[2].hit_point, -5)
        self.ns["handle_sub_both_small_hit_point"](1, 1, 5, game_type.CharacterStatusChange(), self.now)
        self.assertEqual(self.cache.character_data[1].hit_point, 45)

    def test_experience_helper_recipient_and_record_routing(self):
        """经验加给第一个参数指定的受体，记录按传入的记录对象归属；无返回值。"""
        load_functions("Script/Settle/common_default.py", self.ns, lambda node: node.name == "base_chara_experience_common_settle")
        self.ns["handle_premise"] = SimpleNamespace(handle_normal_6=lambda cid: True, handle_unconscious_flag_ge_1=lambda cid: False, handle_self_time_stop_orgasm_relase=lambda cid: False)
        self.config.config_experience = {35: SimpleNamespace(type=0)}
        settle = self.ns["base_chara_experience_common_settle"]
        for character in self.cache.character_data.values():
            character.experience = {}
        changes = game_type.CharacterStatusChange()
        settle(1, 35, change_data=changes)
        settle(3, 35, change_data_to_target_change=changes)
        self.assertEqual([character.experience.get(35, 0) for character in self.cache.character_data.values()], [0, 1, 0, 1])
        self.assertEqual(changes.experience[35], 1)
        self.assertEqual(set(changes.target_change), {3})
        self.assertEqual(changes.target_change[3].experience[35], 1)

    def test_cve_a2_and_target_switch(self):
        """综合数值A2使用传入目标，ChangeTargetId更新后续目标；无返回值。"""
        load_functions("Script/Design/settle_behavior.py", self.ns, lambda node: node.name == "handle_comprehensive_value_effect")
        modules = {"Script.Settle.common_default": SimpleNamespace(base_chara_experience_common_settle=Mock(), base_chara_climix_common_settle=Mock()),
                   "Script.UI.Panel": SimpleNamespace(event_option_panel=Mock()),
                   "Script.Design": SimpleNamespace(character=SimpleNamespace(get_character_id_from_adv=lambda adv: 3))}
        self.cache.npc_id_got = {1, 2, 3}
        self.cache.character_data[2].status_data[8] = 0
        seen = []
        self.effects[-1] = lambda cid, target, *args: seen.append(target)
        changes = game_type.CharacterStatusChange()
        with patch.dict(sys.modules, modules):
            self.ns["settle_effect_list"](0, 2, ["CVE_A2_S|8_G_5", "CVE_A3|3_ChangeTargetId|0_E_0", -1], 1, changes, self.now)
        self.assertEqual(self.cache.character_data[2].status_data[8], 5)
        self.assertEqual(changes.target_change[2].status_data[8], 5)
        self.assertNotIn(1, changes.target_change)
        self.assertEqual(seen, [3])

    def test_climax_pleasure_goes_to_climaxer(self):
        """绝顶辅助函数把部位快感和绝顶记录都加给绝顶者本人，不读其交互对象；无返回值。"""
        load_functions("Script/Settle/common_default.py", self.ns, lambda node: node.name == "base_chara_climix_common_settle")
        self.ns["random"] = SimpleNamespace(uniform=lambda low, high: 1.0)
        state_calls = []
        self.ns["base_chara_state_common_settle"] = lambda cid, *args, **kwargs: state_calls.append(cid)
        second = SimpleNamespace(character_get_second_behavior=Mock())
        for character in self.cache.character_data.values():
            character.h_state.orgasm_level[4] = 0
        changes = game_type.CharacterStatusChange()
        with patch.dict(sys.modules, {"Script.Design": SimpleNamespace(second_behavior=second)}):
            self.ns["handle_target_hypnosis_force_climax"](0, 2, 5, changes, self.now)
        self.assertEqual(state_calls, [2])
        self.assertEqual(second.character_get_second_behavior.call_args.args, (2, "v_orgasm_small"))
        self.assertEqual(self.cache.character_data[2].h_state.orgasm_level[4], 1)
        self.assertEqual(self.cache.character_data[3].h_state.orgasm_level[4], 0)

    def test_favorability_direction_uses_explicit_pair(self):
        """输入双方与持久目标不同的组合；验证好感方向、记录和累计值，无返回值。"""
        load_functions("Script/Design/character_handle.py", self.ns, lambda node: node.name == "add_favorability")
        for actor, target, saved, recipient, other in [(0, 2, 0, 2, 0), (1, 0, 3, 1, 0), (1, 2, 0, 2, 1)]:
            with self.subTest(actor=actor, target=target):
                for character in self.cache.character_data.values():
                    character.favorability = {}
                self.cache.character_data[actor].target_character_id = saved
                self.cache.rhodes_island = SimpleNamespace(total_favorability_increased=0)
                changes, target_changes = game_type.CharacterStatusChange(), game_type.TargetChange()
                self.ns["add_favorability"](actor, target, 10, changes, target_changes)
                self.assertEqual(self.cache.character_data[recipient].favorability[other], 10)
                self.assertEqual(self.cache.character_data[other].favorability[recipient], 0)
                self.assertEqual(changes.favorability, 10 if target == 0 else 0)
                self.assertEqual(target_changes.favorability, 0 if target == 0 else 10)
                self.assertEqual(self.cache.rhodes_island.total_favorability_increased, 10 if 0 in (actor, target) else 0)
                self.assertEqual(self.cache.character_data[actor].target_character_id, saved)

    def test_body_management_changes_self_without_retargeting(self):
        """分别执行日间与睡眠道具管理；只改变本人的装备并保留交互对象，无返回值。"""
        for period in ("day", "sleep"):
            for enabled in (True, False):
                with self.subTest(period=period, enabled=enabled):
                    for cid, character in self.cache.character_data.items():
                        character.h_state.body_item = {i: [0, not enabled, None] for i in range(4)}
                        character.target_character_id = (cid + 1) % 4
                    premise = SimpleNamespace()
                    for item in ("nipple_clamp", "clit_clamp", "v_bibrator", "a_bibrator"):
                        setattr(premise, f"handle_ask_equp_{item}_in_{period}", lambda cid: enabled)
                    for index, item in enumerate(("nipple_clamp", "clit_clamp", "vibrator_insertion", "vibrator_insertion_anal")):
                        setattr(premise, f"handle_self_now_{item}", lambda cid, i=index: self.cache.character_data[cid].h_state.body_item[i][1])
                    self.ns["handle_premise"] = premise
                    self.ns[f"handle_adjust_body_manage_{period}_item"](1, 3, 1, game_type.CharacterStatusChange(), self.now)
                    for cid, character in self.cache.character_data.items():
                        self.assertEqual([character.h_state.body_item[i][1] for i in range(4)], [enabled if cid == 1 else not enabled] * 4)
                        self.assertEqual(character.target_character_id, (cid + 1) % 4)

    def test_group_refusal_preserves_target_and_reduces_favorability(self):
        """群交失败逐人结算拒绝者；保留博士交互对象并正确降低好感，无返回值。"""
        self.load_hp_helper()
        load_functions("Script/Design/character_handle.py", self.ns, lambda node: node.name == "add_favorability")
        load_functions("Script/Settle/common_default.py", self.ns, lambda node: node.name == "base_chara_favorability_and_trust_common_settle")
        self.ns["character_handle"] = SimpleNamespace(add_favorability=self.ns["add_favorability"])
        self.ns["calculation_favorability"] = lambda actor, target, value: value
        self.ns["attr_calculation"] = SimpleNamespace(get_character_fall_level=lambda cid: 0)
        self.ns["handle_ability"] = SimpleNamespace(get_ability_adjust=lambda value: 1)
        self.ns["map_handle"] = SimpleNamespace(get_map_system_path_str_for_list=lambda position: "room")
        self.cache.scene_data = {"room": SimpleNamespace(character_list=[0, 1, 2, 3])}
        self.cache.rhodes_island = SimpleNamespace(total_favorability_increased=0)
        self.cache.pl_pre_behavior_instruce = []
        self.cache.all_system_setting = SimpleNamespace(difficulty_setting={1: 1})
        self.ns["system_setting"] = SimpleNamespace(get_difficulty_coefficient=lambda difficulty: 1)
        self.cache.character_data[0].pl_collection.eqip_token = {1: []}
        self.cache.character_data[0].target_character_id = 0
        seen_targets = []

        def is_refuser(cid):
            """输入角色id并记录此时博士的交互对象；返回该角色是否拒绝，bool。"""
            seen_targets.append(self.cache.character_data[0].target_character_id)
            return cid in (1, 2)

        self.ns["handle_premise"].handle_group_sex_fail_and_self_refuse = is_refuser
        self.ns["handle_premise"].handle_unconscious_flag_ge_1 = lambda cid: False
        for character in self.cache.character_data.values():
            character.ability[18] = 0
            character.favorability = {}
        changes = game_type.CharacterStatusChange()
        self.ns["handle_group_sex_fail_add_just"](0, 3, 1, changes, self.now)
        self.assertEqual(seen_targets, [0, 0, 0])
        self.assertEqual(self.cache.character_data[0].target_character_id, 0)
        for cid in (1, 2):
            self.assertEqual(self.cache.character_data[cid].favorability[0], -15)
            self.assertEqual(changes.target_change[cid].favorability, -15)
        self.assertEqual(self.cache.character_data[3].favorability, {})
        self.assertEqual(self.cache.rhodes_island.total_favorability_increased, -30)

    def test_recovery_keeps_explicit_target_through_response(self):
        """恢复流程使用指定角色；中途改变交互对象也不影响装睡或双方重置，无返回值。"""
        load_functions("Script/Design/handle_npc_ai_in_h.py", self.ns, lambda node: node.name == "recover_from_unconscious_h")
        self.ns["handle_npc_ai_in_h"] = SimpleNamespace(recover_from_unconscious_h=self.ns["recover_from_unconscious_h"])
        self.ns["UnconsciousHResponse"] = SimpleNamespace(CONTINUE_H=1)
        self.constants.Behavior.WAIT = "wait"
        self.constants.CharacterStatus = SimpleNamespace(STATUS_WAIT="wait")
        self.ns["window_width"] = 80
        self.ns["map_handle"] = SimpleNamespace(get_map_system_path_str_for_list=lambda position: "room")
        self.cache.scene_data = {"room": SimpleNamespace(character_list=[0, 1, 2, 3], close_flag=1)}
        self.cache.game_time = self.now
        self.cache.achievement = SimpleNamespace(sleep_sex_record={1: 0})
        for response_value in (1, 5):
            with self.subTest(response=response_value):
                self.cache.character_data[0].target_character_id = 1
                for cid, character in self.cache.character_data.items():
                    character.sp_flag.unconscious_h = 1
                    character.sp_flag.is_h = cid == 2
                    character.h_state.pretend_sleep = False
                    character.behavior.duration = 99
                effects = Mock()
                stop, sleep, abnormal, settle, update = Mock(), Mock(return_value=True), Mock(), Mock(), Mock()
                self.ns["character_behavior"] = SimpleNamespace(judge_character_status_time_over=stop)
                self.ns["instuct_judege"] = SimpleNamespace(init_character_behavior_start_time=Mock())
                self.ns["handle_premise"] = SimpleNamespace(
                    handle_self_is_h=lambda cid: self.cache.character_data[cid].sp_flag.is_h,
                    handle_group_sex_mode_on=lambda cid: False,
                    handle_action_sleep=sleep,
                    settle_chara_unnormal_flag=abnormal,
                )
                self.ns["draw"] = SimpleNamespace(WaitDraw=Mock())
                self.ns["settle_unconscious_semen_and_cloth"] = settle
                self.ns["update"] = SimpleNamespace(game_update_flow=update)

                def respond(actor, target):
                    """输入执行者与目标id；模拟响应中切换交互对象，返回裁决int。"""
                    self.cache.character_data[actor].target_character_id = 3
                    return response_value

                response = Mock(side_effect=respond)
                self.ns["handle_unconscious_h_response"] = response
                with patch.dict(sys.modules, {"Script.Settle": SimpleNamespace(default=effects)}):
                    self.ns["handle_recover_from_unconscious_add_adjust"](0, 2, 1, game_type.CharacterStatusChange(), self.now)
                stop.assert_called_once_with(2, self.now, end_now=2)
                settle.assert_called_once_with(2)
                response.assert_called_once_with(0, 2)
                self.assertTrue(all(call.args == (2,) for call in sleep.call_args_list))
                self.assertEqual(self.cache.character_data[1].behavior.duration, 99)
                self.assertEqual(self.cache.character_data[3].behavior.duration, 99)
                if response_value == 1:
                    self.assertTrue(self.cache.character_data[2].h_state.pretend_sleep)
                    self.assertTrue(all(call.args == (2, 5) for call in abnormal.call_args_list))
                    self.assertEqual(effects.handle_h_flag_to_1.call_args.args[:2], (2, None))
                    effects.handle_both_h_state_reset.assert_not_called()
                else:
                    self.assertEqual(effects.handle_both_h_state_reset.call_args.args[:2], (0, 2))
                update.assert_called_once_with(5)


if __name__ == "__main__":
    unittest.main()
