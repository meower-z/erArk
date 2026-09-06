"""普通效果接口测试。用标准库隔离加载生产函数，不启动界面或指令线程。"""

import ast
import datetime
import inspect
import sys
import unittest
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
from typing import Optional, Union
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Script.Core import constant_effect, game_type


def load_functions(path, namespace, predicate):
    """输入文件路径、命名空间和筛选函数；编译生产函数，返回函数名列表。"""
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and predicate(node)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / path), "exec"), namespace)
    return [node.name for node in nodes]


def ordinary_effect(node):
    """输入函数语法节点；返回是否注册为普通效果的布尔值。"""
    return any(isinstance(item, ast.Call) and isinstance(item.func, ast.Attribute) and item.func.attr == "add_settle_behavior_effect" for item in node.decorator_list)


class EffectInterfaceTest(unittest.TestCase):
    """验证真实注册函数、明确目标以及调用顺序。"""

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
        self.cache = SimpleNamespace(character_data=characters)
        self.constants = SimpleNamespace(settle_behavior_effect_data={}, Behavior=SimpleNamespace(TIME_STOP_OFF="time_stop_off"))
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
        load_functions("Script/Design/settle_behavior.py", self.ns, lambda node: node.name in {"add_settle_behavior_effect", "handle_instruct_data", "handle_event_data", "settle_effect_list"})
        self.ns["settle_behavior"] = SimpleNamespace(add_settle_behavior_effect=self.ns["add_settle_behavior_effect"])
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
                signature.bind(1, 2, 1, game_type.CharacterStatusChange(), self.now)
                with self.assertRaises(TypeError):
                    signature.bind(1, 1, game_type.CharacterStatusChange(), self.now)

    def test_equipment_uses_supplied_target(self):
        """装备开关只修改明确目标的指定槽位，不读取角色选择；无返回值。"""
        for item, slot in (("nipple_clamp", 0), ("clit_clamp", 1), ("vibrator", 2), ("anal_vibrator", 3)):
            for operation, active in (("on", True), ("off", False)):
                for duration in (0, 1):
                    with self.subTest(item=item, operation=operation, duration=duration):
                        for character in self.cache.character_data.values():
                            character.h_state.body_item = {key: [17, not active, 23] for key in range(5)}
                        # 执行者选择角色1，但本次明确作用于角色2。
                        self.cache.character_data[0].target_character_id = 1
                        self.ns[f"handle_target_{item}_{operation}"](0, 2, duration, game_type.CharacterStatusChange(), self.now)
                        for cid, character in self.cache.character_data.items():
                            for key, value in character.h_state.body_item.items():
                                expected = active if duration and cid == 2 and key == slot else not active
                                self.assertEqual(value, [17, expected, 23])
                        self.assertEqual(self.cache.character_data[0].target_character_id, 1)

    def test_explicit_player_target(self):
        """目标0表示玩家，不是回读当前选择的特殊值；无返回值。"""
        for character in self.cache.character_data.values():
            character.h_state.body_item = {2: [0, False]}
        self.ns["handle_target_vibrator_on"](1, 0, 1, game_type.CharacterStatusChange(), self.now)
        self.assertTrue(self.cache.character_data[0].h_state.body_item[2][1])
        self.assertFalse(self.cache.character_data[2].h_state.body_item[2][1])

    def run_target_switch(self, event=False, facility=False):
        """输入事件和设施分支标志；执行真实效果切换顺序并断言结果，无返回值。"""
        ids = constant_effect.BehaviorEffect
        sequence = [ids.TARGET_TO_PLAYER, ids.TARGET_VIBRATOR_ON]
        for character in self.cache.character_data.values():
            character.h_state.body_item = {2: [0, False]}
        changes = game_type.CharacterStatusChange()
        if event:
            self.config.config_event["example"] = SimpleNamespace(effect=[str(item) for item in sequence])
            self.ns["handle_event_data"]("example", 1, 2, 1, changes, self.now)
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
        """普通效果间的主动目标切换对后续效果生效；无返回值。"""
        self.run_target_switch()

    def test_event_target_switch(self):
        """事件效果间的主动目标切换对后续效果生效；无返回值。"""
        self.run_target_switch(event=True)

    def test_facility_target_switch(self):
        """额外设施效果也接收调用时的目标；无返回值。"""
        self.run_target_switch(facility=True)

    def test_nested_self_effect_does_not_read_interaction_target(self):
        """对目标执行自身效果时，无需读取该角色的交互对象；无返回值。"""
        self.cache.character_data[1] = SimpleNamespace(angry_point=50)
        changes = game_type.CharacterStatusChange()
        self.ns["handle_target_mood_to_good"](0, 1, 1, changes, self.now)
        self.assertEqual(self.cache.character_data[1].angry_point, 0)

    def test_self_effect_does_not_need_target_state(self):
        """自身效果可以忽略目标参数，不访问目标角色；无返回值。"""
        self.cache.character_data[1].angry_point = 50
        self.ns["handle_mood_to_good"](1, None, 1, game_type.CharacterStatusChange(), self.now)
        self.assertEqual(self.cache.character_data[1].angry_point, 0)


    def test_explicit_target_survives_ordinary_chain(self):
        """传入目标与持久目标不同时，连续普通效果使用传入值；无返回值。"""
        seen = []
        self.effects[-1] = lambda cid, target, *args: seen.append(target)
        self.assertEqual(self.ns["settle_effect_list"](0, 2, [-1, -1], 1, game_type.CharacterStatusChange(), self.now), 2)
        self.assertEqual(seen, [2, 2])
        self.assertEqual(self.cache.character_data[0].target_character_id, 1)

    def test_select_existing_persistent_target(self):
        """选择器选中原持久目标时仍更新当前效果目标；无返回值。"""
        self.cache.character_data[1].target_character_id = 0
        target = self.ns["settle_effect_list"](1, 2, [constant_effect.BehaviorEffect.TARGET_TO_PLAYER], 1, game_type.CharacterStatusChange(), self.now)
        self.assertEqual(target, 0)

    def test_interrupt_target_activity_keeps_time_helper_interface(self):
        """中断明确目标的活动时，时间同步函数仍接收角色和时间；无返回值。"""
        self.constants.CharacterStatus = SimpleNamespace(STATUS_ARDER="idle")
        self.constants.Behavior.MOVE = "moving"
        actor = self.cache.character_data[0]
        target = self.cache.character_data[2]
        target.behavior.behavior_id = "moving"
        self.ns["game_time"].get_sub_date = lambda *args, **kwargs: self.now
        self.ns["instuct_judege"] = SimpleNamespace(init_character_behavior_start_time=Mock())
        self.ns["handle_interrupt_target_activity"](0, 2, 1, game_type.CharacterStatusChange(), self.now)
        self.ns["instuct_judege"].init_character_behavior_start_time.assert_called_once_with(2, actor.behavior.start_time)

    def test_all_selectors_and_zero_duration(self):
        """四类选择器按条件选择目标，零时长保持原目标；无返回值。"""
        ids = constant_effect.BehaviorEffect
        self.constants.Behavior.MASTUREBATE = "masturebate"
        self.ns["map_handle"] = SimpleNamespace(get_map_system_path_str_for_list=lambda position: "room")
        self.cache.scene_data = {"room": SimpleNamespace(character_list=[0, 1, 2, 3])}
        self.cache.character_data[2].behavior.behavior_id = "masturebate"
        for cid, character in self.cache.character_data.items():
            character.desire_point = cid * 10
        cases = [(ids.TARGET_TO_PLAYER, 0), (ids.TARGET_TO_SELF, 1), (ids.TARGET_TO_MASTUREBATE, 2), (ids.TARGET_TO_MOST_DESIRE, 3)]
        for effect_id, expected in cases:
            for duration in (0, 1):
                with self.subTest(effect=effect_id, duration=duration):
                    self.cache.character_data[1].target_character_id = 0
                    target = self.ns["settle_effect_list"](1, 2, [effect_id], duration, game_type.CharacterStatusChange(), self.now)
                    self.assertEqual(target, expected if duration else 2)
                    self.assertEqual(self.cache.character_data[1].target_character_id, expected if duration else 0)
        # 场景内没有候选者时，保留调用方的目标。
        self.cache.scene_data["room"].character_list = [1]
        for effect_id in (ids.TARGET_TO_MASTUREBATE, ids.TARGET_TO_MOST_DESIRE):
            self.cache.character_data[1].target_character_id = 0
            target = self.ns["settle_effect_list"](1, 2, [effect_id], 1, game_type.CharacterStatusChange(), self.now)
            self.assertEqual(target, 2)
            self.assertEqual(self.cache.character_data[1].target_character_id, 0)

    def test_ordinary_effect_persistent_write_retargets_following_effect(self):
        """普通效果修改执行者的持久目标后，后续效果沿用新值；无返回值。"""
        seen = []
        self.effects[-1] = lambda cid, target, *args: seen.append(target)
        sequence = [-1, constant_effect.BehaviorEffect.PL_TARGET_TO_ME, -1]
        target = self.ns["settle_effect_list"](0, 1, sequence, 1, game_type.CharacterStatusChange(), self.now)
        self.assertEqual(seen, [1, 0])
        self.assertEqual(target, 0)

    def test_real_event_sequence(self):
        """实际事件的选择器前后效果按原顺序收到目标；无返回值。"""
        import json
        events = json.loads((ROOT / "data/event/event.json").read_text())
        sequence = next(list(event["effect"]) for event in events.values() if list(event.get("effect", {})) == ["23", "24", "10002", "762"])
        seen = []
        for effect_id in (23, 24, 762):
            self.effects[effect_id] = lambda cid, target, *args, effect_id=effect_id: seen.append((effect_id, target))
        self.ns["settle_effect_list"](1, 2, sequence, 1, game_type.CharacterStatusChange(), self.now, event_flag=True)
        self.assertEqual(seen, [(23, 2), (24, 2), (762, 0)])

    def test_nested_cse_preserves_player_selection_side_effect(self):
        """真实CSE调用新行为后，外层效果接收新行为留下的目标；无返回值。"""
        seen = []
        self.effects[-1] = lambda cid, target, *args: seen.append(target)
        def start(behavior, target_character_id, game_update_flag):
            """记录行为目标并模拟嵌套行为切换目标；无返回值。"""
            seen.append((behavior, target_character_id, game_update_flag))
            self.cache.character_data[0].target_character_id = 3
        self.ns["chara_handle_instruct_common_settle"] = start
        load_functions("Script/System/Instruct_System/handle_instruct.py", self.ns, lambda node: node.name == "handle_comprehensive_state_effect")
        self.ns["handle_instruct"] = SimpleNamespace(handle_comprehensive_state_effect=self.ns["handle_comprehensive_state_effect"])
        self.ns["settle_effect_list"](0, 2, ["CSE_A2_wait", "-1"], 1, game_type.CharacterStatusChange(), self.now, event_flag=True)
        self.assertEqual(seen, [("wait", 2, True), 3])

    def test_parent_event_target_reaches_child_event(self):
        """真实行为入口将主事件的目标传给子事件，绘制时切换目标也生效；无返回值。"""
        from unittest.mock import patch
        load_functions("Script/Design/settle_behavior.py", self.ns, lambda node: node.name == "handle_settle_behavior")
        self.ns["first_record_handle"] = SimpleNamespace(check_first_h_mode=Mock())
        actor = self.cache.character_data[1]
        actor.position = ["different room"]
        actor.event.event_id = "parent"
        self.config.config_event["parent"] = SimpleNamespace(effect=[str(constant_effect.BehaviorEffect.TARGET_TO_SELF)])
        self.config.config_event["child"] = SimpleNamespace(effect=["-1"], type=0)
        seen = []
        self.effects[-1] = lambda cid, target, *args: seen.append(target)
        panel = Mock()
        modules = {"Script.System.Sex_System": SimpleNamespace(group_sex_panel=Mock()),
                   "Script.UI.Panel": SimpleNamespace(draw_event_text_panel=SimpleNamespace(DrawEventTextPanel=Mock(return_value=panel)))}
        for draw_target in (None, 3):
            actor.target_character_id = 2
            actor.event.son_event_id = "child"
            panel.draw.side_effect = None if draw_target is None else lambda: setattr(actor, "target_character_id", draw_target)
            with patch.dict(sys.modules, modules):
                self.ns["handle_settle_behavior"](1, 2, self.now + datetime.timedelta(minutes=1), event_flag=0)
            self.assertEqual(actor.event.son_event_id, "")
        self.assertEqual(seen, [1, 3])

    def test_talk_target_switch_precedes_first_effect(self):
        """口上修改目标后，首个效果收到新目标；无返回值。"""
        self.cache.character_data[1].event.skip_instruct_talk = False
        self.ns["talk"].handle_talk.side_effect = lambda cid: setattr(self.cache.character_data[cid], "target_character_id", 3)
        self.config.config_behavior_effect_data["example"] = [-1]
        seen = []
        self.effects[-1] = lambda cid, target, *args: seen.append(target)
        self.ns["handle_instruct_data"](1, 2, "example", self.now, 1, game_type.CharacterStatusChange())
        self.assertEqual(seen, [3])

    def test_direct_calls_match_effect_signature(self):
        """生产代码内的直接调用与注册表调用均传递完整参数；无返回值。"""
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
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
                registry = isinstance(node.func, ast.Subscript) and ast.unparse(node.func.value) == "constant.settle_behavior_effect_data"
                if isinstance(node.func, ast.Name) and name not in local_effects:
                    continue
                if isinstance(node.func, ast.Attribute) and ast.unparse(node.func.value) not in effect_modules:
                    continue
                if name not in names and not registry:
                    continue
                with self.subTest(path=str(path), line=node.lineno):
                    self.assertEqual(len(node.args) + len(node.keywords), 5)
                    target = node.args[1] if len(node.args) > 1 else next(k.value for k in node.keywords if k.arg == "target_character_id")
                    self.assertFalse(isinstance(target, ast.Constant) and isinstance(target.value, str))
                checked += 1
        self.assertGreater(checked, 100)

    def test_helper_targets_are_required_at_every_call(self):
        """辅助函数的目标参数必须显式传入，生产调用不能省略参数；无返回值。"""
        helper_names = {
            "base_chara_hp_mp_common_settle", "base_chara_experience_common_settle",
            "base_chara_climix_common_settle", "base_chara_favorability_and_trust_common_settle",
            "handle_comprehensive_value_effect", "extra_exp_settle",
        }
        for path in ("Script/Settle/common_default.py", "Script/Design/settle_behavior.py"):
            load_functions(path, self.ns, lambda node: node.name in helper_names)
        signatures = {name: inspect.signature(self.ns[name]) for name in helper_names}
        for name, signature in signatures.items():
            self.assertIs(signature.parameters["target_character_id"].default, inspect.Parameter.empty, name)
        checked = 0
        for path in (ROOT / "Script").rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8-sig"))):
                if not isinstance(node, ast.Call):
                    continue
                name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
                if name not in signatures:
                    continue
                with self.subTest(path=str(path), line=node.lineno):
                    signatures[name].bind(*[object() for _ in node.args], **{k.arg: object() for k in node.keywords})
                checked += 1
        self.assertGreater(checked, 100)


    def test_paired_hp_helper_uses_explicit_target(self):
        """双方体力效果的通用计算使用指定目标并记录其变化；无返回值。"""
        from typing import Optional
        self.ns["Optional"] = Optional
        self.ns["handle_premise"] = SimpleNamespace(handle_time_stop_on=lambda cid: False, handle_self_is_h=lambda cid: False, handle_hidden_sex_mode_5=lambda cid: False)
        self.ns["handle_npc_ai"] = Mock()
        load_functions("Script/Settle/common_default.py", self.ns, lambda node: node.name == "base_chara_hp_mp_common_settle")
        for character in self.cache.character_data.values():
            character.hit_point = character.mana_point = 50
            character.hit_point_max = character.mana_point_max = 100
        changes = game_type.CharacterStatusChange()
        self.ns["handle_sub_both_small_hit_point"](0, 2, 5, changes, self.now)
        self.assertEqual([self.cache.character_data[cid].hit_point for cid in range(4)], [45, 50, 45, 50])
        self.assertEqual(changes.hit_point, -5)
        self.assertEqual(changes.target_change[2].hit_point, -5)
        self.assertNotIn(1, changes.target_change)

    def test_helper_zero_target_is_player(self):
        """通用体力计算以0指定玩家，以CURRENT_TARGET读取角色选择；无返回值。"""
        self.test_paired_hp_helper_uses_explicit_target()
        settle = self.ns["base_chara_hp_mp_common_settle"]
        changes = game_type.CharacterStatusChange()
        settle(1, hp_value=-5, target_flag=True, change_data=changes, target_character_id=0)
        self.assertEqual(changes.target_change[0].hit_point, -5)
        self.assertNotIn(2, changes.target_change)
        changes = game_type.CharacterStatusChange()
        with self.assertRaises(TypeError):
            settle(1, hp_value=-5, target_flag=True, change_data=changes)
        settle(1, hp_value=-5, target_flag=True, change_data=changes, target_character_id="CURRENT_TARGET")
        self.assertEqual(changes.target_change[2].hit_point, -5)

    def test_self_hp_effect_accepts_none_without_interaction_target(self):
        """自身体力效果传None时无需交互对象，仍正确记录体力变化；无返回值。"""
        self.test_paired_hp_helper_uses_explicit_target()
        actor = self.cache.character_data[1]
        del actor.target_character_id
        changes = game_type.CharacterStatusChange()
        self.ns["handle_sub_self_small_hit_point"](1, None, 5, changes, self.now)
        self.assertEqual(actor.hit_point, 45)
        self.assertEqual(changes.hit_point, -5)
        self.assertEqual(changes.target_change, {})

    def test_self_experience_accepts_none_without_interaction_target(self):
        """自身经验传None时不读取交互对象，经验及记录归属自身；无返回值。"""
        load_functions("Script/Settle/common_default.py", self.ns, lambda node: node.name == "base_chara_experience_common_settle")
        self.ns["handle_premise"] = SimpleNamespace(handle_unconscious_flag_ge_1=lambda cid: False, handle_self_time_stop_orgasm_relase=lambda cid: False)
        self.config.config_experience = {35: SimpleNamespace(type=0)}
        actor = self.cache.character_data[1]
        del actor.target_character_id
        actor.experience = {}
        changes = game_type.CharacterStatusChange()
        self.ns["base_chara_experience_common_settle"](1, 35, change_data=changes, target_character_id=None)
        self.assertEqual(actor.experience[35], 1)
        self.assertEqual(changes.experience[35], 1)
        self.assertEqual(changes.target_change, {})

    def test_extra_experience_keeps_explicit_target_after_second_effect(self):
        """二段结算未改目标时沿用传入值，改目标时额外经验使用新值；无返回值。"""
        for changed in (False, True):
            with self.subTest(changed=changed):
                self.cache.character_data[1].target_character_id = 0
                self.ns["extra_exp_settle"].reset_mock()
                self.ns["second_behavior"].check_second_effect.side_effect = (
                    (lambda *args: setattr(self.cache.character_data[1], "target_character_id", 3)) if changed else None
                )
                changes = game_type.CharacterStatusChange()
                self.ns["handle_instruct_data"](1, 2, "example", self.now, 1, changes)
                self.ns["extra_exp_settle"].assert_called_once_with(1, 3 if changed else 2, changes)

    def test_experience_helper_distinguishes_explicit_target_and_current_target(self):
        """经验归属和变更记录使用明确目标；只有CURRENT_TARGET读取交互对象，无返回值。"""
        load_functions("Script/Settle/common_default.py", self.ns, lambda node: node.name == "base_chara_experience_common_settle")
        self.ns["handle_premise"] = SimpleNamespace(handle_unconscious_flag_ge_1=lambda cid: False, handle_self_time_stop_orgasm_relase=lambda cid: False)
        self.config.config_experience = {35: SimpleNamespace(type=0)}
        for target, recipient in ((0, 0), (3, 3), ("CURRENT_TARGET", 2)):
            with self.subTest(target=target):
                for character in self.cache.character_data.values():
                    character.experience = {}
                changes = game_type.CharacterStatusChange()
                self.ns["base_chara_experience_common_settle"](1, 35, target_flag=True, change_data=changes, target_character_id=target)
                for cid, character in self.cache.character_data.items():
                    self.assertEqual(character.experience.get(35, 0), int(cid == recipient))
                self.assertEqual(set(changes.target_change), {recipient})
                self.assertEqual(changes.target_change[recipient].experience[35], 1)

    def test_cve_a2_and_target_switch(self):
        """综合数值A2使用明确目标，ChangeTargetId更新后续目标；无返回值。"""
        from unittest.mock import patch
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


if __name__ == "__main__":
    unittest.main()
