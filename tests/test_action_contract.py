"""Action 意图的数据隔离与保留参数契约。"""

from datetime import datetime
import unittest
from types import SimpleNamespace

from Script.Modules.scheduler.action import Action, CONTINUED, STATE


class ActionContractTests(unittest.TestCase):
    """检查行动意图与执行状态的参数隔离，以及 state、continued 两个保留参数。"""

    def test_from_character_deep_copies_nested_parameters(self):
        """无需参数；验证行动意图独立保存嵌套参数；无返回值。"""
        behavior = SimpleNamespace(behavior_id="work", duration=10, start_time=datetime(2026, 1, 1), nested={"values": []})
        character = SimpleNamespace(behavior=behavior, target_character_id=3, state="working")

        action = Action.from_character(character)
        behavior.nested["values"].append("changed")

        self.assertEqual(action.params["nested"]["values"], [])

    def test_from_character_records_state_and_extra_execution_params(self):
        """无需参数；意图带出角色状态，追加的执行参数进入 params，且不带出开始时间；无返回值。"""
        behavior = SimpleNamespace(behavior_id="work", duration=0, start_time=datetime(2026, 1, 1))
        character = SimpleNamespace(behavior=behavior, target_character_id=3, state="working")

        action = Action.from_character(character, continued=True)

        self.assertEqual(action, Action("work", 1, 3, {STATE: "working", CONTINUED: True}))
        self.assertTrue(action.continued)
        self.assertFalse(Action.from_character(character).continued)

    def test_apply_writes_state_and_keeps_execution_params_out_of_behavior(self):
        """无需参数；安装时状态写入角色，state 与 continued 不进入 Behavior；无返回值。"""
        action = Action("work", 10, 3, params={STATE: "working", CONTINUED: True, "book_id": 7})
        character = SimpleNamespace(behavior=None, target_character_id=0, state=None)

        action.apply(character, datetime(2026, 1, 1))

        self.assertEqual(character.state, "working")
        self.assertEqual(character.target_character_id, 3)
        self.assertEqual((character.behavior.behavior_id, character.behavior.duration, character.behavior.start_time, character.behavior.book_id), ("work", 10, datetime(2026, 1, 1), 7))
        self.assertFalse(hasattr(character.behavior, STATE))
        self.assertFalse(hasattr(character.behavior, CONTINUED))
        self.assertEqual(action.params, {STATE: "working", CONTINUED: True, "book_id": 7})

    def test_apply_defaults_state_to_behavior_id(self):
        """无需参数；未指定状态时以行为编号作为状态；无返回值。"""
        character = SimpleNamespace(behavior=None, target_character_id=0, state=None)
        Action("rest", 10, 0).apply(character, datetime(2026, 1, 1))
        self.assertEqual(character.state, "rest")

    def test_apply_deep_copies_parameters_for_each_character(self):
        """无需参数；验证同一行动生成的执行状态彼此隔离；无返回值。"""
        action = Action("work", 10, 3, params={"nested": {"values": []}})
        first = SimpleNamespace(behavior=None, target_character_id=0, state=None)
        second = SimpleNamespace(behavior=None, target_character_id=0, state=None)

        action.apply(first, datetime(2026, 1, 1))
        first.behavior.nested["values"].append("changed")
        self.assertEqual(action.params["nested"]["values"], [])
        action.apply(second, datetime(2026, 1, 1))

        self.assertEqual(second.behavior.nested["values"], [])


if __name__ == "__main__":
    unittest.main()
