"""Action 意图的数据隔离契约。"""

from datetime import datetime
import unittest
from types import SimpleNamespace

from Script.Modules.action import Action


class ActionContractTests(unittest.TestCase):
    """检查行动意图与执行状态的参数隔离。"""

    def test_from_character_deep_copies_nested_parameters(self):
        """无需参数；验证行动意图独立保存嵌套参数；无返回值。"""
        behavior = SimpleNamespace(behavior_id="work", duration=10, start_time=datetime(2026, 1, 1), nested={"values": []})
        character = SimpleNamespace(behavior=behavior, target_character_id=3, state="working")

        action = Action.from_character(character)
        behavior.nested["values"].append("changed")

        self.assertEqual(action.params["nested"]["values"], [])

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
