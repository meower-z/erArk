"""
H 中的 NPC AI 无界面测试
========================
本测试包含源码导入边界检查与无界面子进程运行测试。源码检查用语法树验证
Script/Design/handle_npc_ai_in_h.py 不导入界面与输入输出等受禁模块。子进程测试在启用
默认界面与结算导入拦截的独立子进程中运行 npc_active_h 及四个不依赖 Script.Settle 的辅助
函数，验证返回结果且未加载也未尝试导入任何受拦截模块。
"""

from typing import Any, cast

from Script.Config import game_config
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports
from tests.ui_free_subprocess import run_ui_free

SOURCE = "Script/Design/handle_npc_ai_in_h.py"
"""待检查源码导入边界的目标模块仓库相对路径。"""
SEEDS = 20
"""无界面子进程中重复调用 npc_active_h 与 evaluate_npc_body_part_prefs 的次数。"""
SKIPPED_TAGS = {"道具", "药物", "SM", "非逆推"}
"""npc_active_h 过滤候选行为时排除的标签集合。"""
CHILD_RUN = """
import random
from unittest import mock
from Script.Core import constant
from Script.Design import attr_calculation, handle_npc_ai_in_h, virgin_break_gate
from Script.Kernel import core
from Script.Modules.domains import activity, dirty, flags, h_state, identity
from Script.Modules.domains import inventory
from Script.Modules.gameplay_resolution import plan_queue, working
from tests import chara_abilities, chara_data, kernel_data
from tests.chara_activity import aim, place
from tests.world import DEFAULT_SCENE, STANDARD_OUTFIT, start_time

kernel_data.reset_clock(start_time(), {})
for cid in (0, 1):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", sex=cid))
    chara_abilities.zero_tables(cid)
    chara_data.seed(cid, STANDARD_OUTFIT)
    kernel_data.put(inventory.replace_items, cid, attr_calculation.get_item_zero({}))
    place(cid, DEFAULT_SCENE)
aim(0, 1)
kernel_data.put(flags.set, 0, is_h=True)
kernel_data.put(flags.set, 1, is_h=True)
core.reset_state(kernel_data.reprojected(core.state()))


class Picked(Exception):
    pass


def choose(*args, **kwargs):
    raise Picked(list(args), kwargs)


def pick():
    try:
        returned = handle_npc_ai_in_h.npc_active_h(choose)
    except Picked as picked:
        return {"args": picked.args[0], "kwargs": picked.args[1]}
    return {"returned": returned}


payload["inactive"] = pick()
kernel_data.put(h_state.set, 1, npc_active_h=True)
picks = []
for seed in range(SEEDS):
    random.seed(seed)
    picks.append(pick())
payload["picks"] = picks
with mock.patch.object(virgin_break_gate, "takes_kept_virginity", return_value=True):
    payload["nothing_left"] = pick()
payload["parts"] = [handle_npc_ai_in_h.evaluate_npc_body_part_prefs(1) for _ in range(SEEDS)]
with working.based_on(core.state()):
    handle_npc_ai_in_h.npc_ai_in_group_sex(1)
    payload["group_sex_off"] = flags.get(1, "masturebate")
    with dirty.editing(1) as d:
        d.body_semen_in_unconscious = [0, 0]
    handle_npc_ai_in_h.settle_unconscious_semen_and_cloth(1)
    payload["semen"] = [
        list(dirty.view(1).body_semen_in_unconscious),
        activity.second_behavior(1, "in_unconscious_cum_on_body_0"),
    ]
    handle_npc_ai_in_h.end_h_left_behind(1)
    payload["left_behind"] = [
        flags.get(1, "is_h"),
        plan_queue.plan_has(1, constant.Behavior.END_H),
    ]
"""
"""在无界面子进程中初始化测试角色并运行 npc_active_h 与四个不依赖结算的辅助函数的代码片段。"""


class HandleNpcAiInHSourceTest(FastTestCase):
    """handle_npc_ai_in_h.py 的源码导入边界测试。"""

    def test_source_imports_no_ui(self) -> None:
        """断言 handle_npc_ai_in_h.py 源码不存在 banned_imports 检出的受禁导入。"""
        source = (ROOT / SOURCE).read_bytes()
        self.assertEqual(banned_imports(source, SOURCE), [])


class HandleNpcAiInHUiFreeTest(FastTestCase):
    """handle_npc_ai_in_h 的无界面子进程运行测试。"""

    @classmethod
    def setUpClass(cls) -> None:
        """在默认拦截规则的无界面子进程中执行 CHILD_RUN 并缓存结果。子进程失败时抛出 RuntimeError。"""
        super().setUpClass()
        cls.child = run_ui_free(f"SEEDS = {SEEDS}\n" + CHILD_RUN, boot=True)
        cls.payload = cast(dict[str, Any], cls.child.payload)

    def test_no_blocked_module_loaded(self) -> None:
        """断言子进程未加载也未尝试导入任何受拦截模块。"""
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_each_pick_hands_a_ten_minute_sex_behavior(self) -> None:
        """断言 SEEDS 次选择均传入 10 分钟与同名 state，且对应行为含性爱标签、无排除标签、触发方非 pl。"""
        picks = self.payload["picks"]
        self.assertEqual(len(picks), SEEDS)
        for pick in picks:
            with self.subTest(pick=pick):
                behavior_id, minutes = pick["args"]
                self.assertEqual(minutes, 10)
                self.assertEqual(pick["kwargs"], {"state": behavior_id})
                behavior = game_config.config_behavior[behavior_id]
                tags = set(behavior.tag.split("|"))
                self.assertIn("性爱", tags)
                self.assertFalse(tags & SKIPPED_TAGS)
                self.assertNotEqual(behavior.trigger, "pl")

    def test_no_pick_without_active_h_or_candidates(self) -> None:
        """断言未开启主动 H 或全部候选被处女门拦截时，npc_active_h 返回 None 且不调用 choose。"""
        self.assertEqual(self.payload["inactive"], {"returned": None})
        self.assertEqual(self.payload["nothing_left"], {"returned": None})

    def test_settle_free_helpers(self) -> None:
        """断言部位喜好、非群交自慰标记、无意识精液结算与离场结束 H 四个辅助函数的结果符合预期。"""
        parts = {
            sid
            for sid, row in game_config.config_character_state.items()
            if row.type == 0
        }
        self.assertTrue(set(self.payload["parts"]) <= parts | {0})
        self.assertEqual(self.payload["group_sex_off"], 0)
        self.assertEqual(self.payload["semen"], [[], 1])
        self.assertEqual(self.payload["left_behind"], [False, True])
