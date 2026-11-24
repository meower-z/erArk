"""
二段行为无界面依赖测试
======================
本模块验证部位绝顶行为标识解析规则与部位映射覆盖范围。
本模块验证 character_get_second_behavior 在屏蔽 Script.Settle 及界面相关模块时可正常运行。
本模块还在替换口上函数后验证 second_behavior_effect 按部位筛选绝顶口上。
"""

import json
import re
import subprocess
import sys

from Script.Core.constant.SecondBehavior import SecondBehavior
from Script.Modules.gameplay_resolution import orgasm_ids
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

PART_ORGASM_ID = re.compile(r"[a-z]_orgasm_(small|normal|strong|super)")
"""匹配单字母部位绝顶二段行为 id 的正则表达式。"""
BLOCKED_RUN = """
import importlib.abc, json, sys
from unittest import mock
BLOCKED = (
    "Script.Settle",
    "Script.UI.Panel",
    "Script.System.Instruct_System.handle_instruct",
    "tkinter",
    "_tkinter",
    "PIL.ImageTk",
)
def blocked(name):
    return any(name == b or name.startswith(b + ".") for b in BLOCKED)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Block())
from tests.fast.base import FastTestCase
case = FastTestCase()
case.setUp()
for cid in (0, 1):
    case.world.chara(cid, str(cid))
from Script.Config import game_config
from Script.Core import game_type
from Script.Design import second_behavior as sb, talk
from Script.Kernel import core
from Script.Modules.domains import activity, first_record
from Script.Modules.gameplay_resolution import working
out = {"settle_before": "Script.Settle" in sys.modules}
before = set(sys.modules)
settle_id = game_config.config_behavior_must_settle_cid_list[0]
show_id = game_config.config_behavior_must_show_cid_list[0]
def records():
    fr = first_record.view(1)
    return [
        sorted(fr.first_strong_orgasm_dict),
        sorted(fr.first_super_orgasm_dict),
        sorted(fr.first_mark_dict),
        {k: v[2] for k, v in sorted(fr.first_special_record_dict.items())},
    ]
with working.based_on(core.state()):
    sb.character_get_second_behavior(1, "chosen_as_assistant")
    out["ordinary"] = [
        activity.second_behavior(1, "chosen_as_assistant"),
        activity.must_settle(1),
        activity.must_show(1),
        records(),
    ]
    sb.character_get_second_behavior(1, settle_id)
    sb.character_get_second_behavior(1, show_id)
    out["must"] = [settle_id, show_id, activity.must_settle(1), activity.must_show(1)]
    sb.character_get_second_behavior(1, settle_id, reset=True)
    sb.character_get_second_behavior(1, show_id, reset=True)
    out["reset"] = [
        activity.second_behavior(1, settle_id),
        activity.second_behavior(1, show_id),
        activity.must_settle(1),
        activity.must_show(1),
    ]
    steps = ["v_orgasm_normal", "v_orgasm_strong", "v_orgasm_super", "a_orgasm_super"]
    steps += ["happy_mark_1", "fertilization", "b_orgasm_to_milk", "u_orgasm_to_pee"]
    out["steps"] = {}
    for bid in steps:
        sb.character_get_second_behavior(1, bid)
        out["steps"][bid] = records()
    fr = first_record.view(1)
    out["place"] = [fr.first_super_orgasm_dict[5][1], activity.position(1)]
with working.based_on(core.state()):
    for bid in ("v_orgasm_normal", "v_orgasm_strong", "b_orgasm_small"):
        activity.set_second_behavior(1, bid, 1)
    talked = []
    with mock.patch.object(talk, "handle_second_talk", lambda cid, bid: talked.append(bid)):
        sb.second_behavior_effect(1, game_type.CharacterStatusChange(), orgasm_settle_flag=True)
    out["effect"] = [sorted(talked), dict(activity.second_behaviors(1))]
out["loaded"] = sorted(m for m in set(sys.modules) - before if blocked(m) or m.startswith("Script.UI"))
print(json.dumps(out, ensure_ascii=False))
"""
"""子进程脚本：屏蔽 Script.Settle 与界面相关模块后运行二段行为流程并打印 JSON 结果。"""


class OrgasmIdsTest(FastTestCase):
    """部位绝顶行为标识解析与部位状态映射测试。"""

    def test_part_and_degree(self) -> None:
        """验证四档部位绝顶行为 id 均返回正确的 (部位字母, 程度序号) 二元组。"""
        cases = {
            "s_orgasm_small": ("s", 0),
            "b_orgasm_normal": ("b", 1),
            "v_orgasm_strong": ("v", 2),
            "w_orgasm_super": ("w", 3),
        }
        for second_behavior_id, expected in cases.items():
            with self.subTest(second_behavior_id):
                self.assertEqual(
                    orgasm_ids.get_orgasm_part_and_degree(second_behavior_id),
                    expected,
                )

    def test_not_part_orgasm(self) -> None:
        """验证非部位绝顶行为 id 均返回 (None, -1)。"""
        for second_behavior_id in (
            "extra_orgasm",
            "plural_orgasm_2",
            "x_orgasm_edge",
            "b_orgasm_to_milk",
            "v_orgasm_ultra",
            "v_mark_strong",
            "happy_mark_1",
        ):
            with self.subTest(second_behavior_id):
                self.assertEqual(
                    orgasm_ids.get_orgasm_part_and_degree(second_behavior_id),
                    (None, -1),
                )

    def test_configured_parts_have_state(self) -> None:
        """验证 SecondBehavior 中全部部位绝顶常量的解析部位均在 orgasm_part_to_state_id 中有映射。"""
        found = [
            value
            for value in vars(SecondBehavior).values()
            if isinstance(value, str) and PART_ORGASM_ID.fullmatch(value)
        ]
        self.assertGreater(len(found), 30)
        for second_behavior_id in found:
            part, _degree = orgasm_ids.get_orgasm_part_and_degree(
                second_behavior_id
            )
            with self.subTest(second_behavior_id):
                self.assertIn(part, orgasm_ids.orgasm_part_to_state_id)


class SecondBehaviorUiFreeTest(FastTestCase):
    """二段行为登记与结算在屏蔽 Script.Settle 及界面相关模块时的运行结果测试。"""

    out: dict

    @classmethod
    def setUpClass(cls) -> None:
        """在独立子进程中执行 BLOCKED_RUN 并解析末行 JSON 作为本测试类的共享结果。"""
        result = subprocess.run(
            [sys.executable, "-c", BLOCKED_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr[-2000:])
        cls.out = json.loads(result.stdout.splitlines()[-1])

    def test_no_ui_or_settle_loaded(self) -> None:
        """验证初始化后未加载 Script.Settle 且二段行为调用期间未新增被屏蔽模块或 Script.UI 模块。"""
        self.assertFalse(self.out["settle_before"])
        self.assertEqual(self.out["loaded"], [])

    def test_ordinary_and_must_lists(self) -> None:
        """验证普通二段行为写入、必结与必显列表登记以及 reset 重置后的状态均符合预期。"""
        ordinary = [1, [], ["chosen_as_assistant"], [[], [], [], {}]]
        self.assertEqual(self.out["ordinary"], ordinary)
        settle_id, show_id, must_settle, must_show = self.out["must"]
        self.assertEqual(must_settle, [settle_id])
        self.assertEqual(must_show, ["chosen_as_assistant", show_id])
        self.assertEqual(self.out["reset"], [0, 0, [], ["chosen_as_assistant"]])

    def test_first_records(self) -> None:
        """验证首次强绝顶、首次超强绝顶、首次刻印、特殊履历及记录地点均按预期写入。"""
        steps = self.out["steps"]
        self.assertEqual(steps["v_orgasm_normal"], [[], [], [], {}])
        self.assertEqual(steps["v_orgasm_strong"], [[4], [], [], {}])
        self.assertEqual(steps["v_orgasm_super"], [[4], [4], [], {}])
        self.assertEqual(steps["a_orgasm_super"], [[4, 5], [4, 5], [], {}])
        self.assertEqual(steps["happy_mark_1"][2], ["happy_mark_1"])
        self.assertEqual(steps["fertilization"][3], {"1": ""})
        self.assertEqual(
            steps["u_orgasm_to_pee"][3], {"1": "", "3": "非H", "4": "非H"}
        )
        place, position = self.out["place"]
        self.assertEqual(place, position)

    def test_effect_talks_highest_degree(self) -> None:
        """验证高潮结算模式下每部位仅最高程度绝顶触发口上，且结算后待处理二段行为清空。"""
        self.assertEqual(
            self.out["effect"], [["b_orgasm_small", "v_orgasm_strong"], {}]
        )
