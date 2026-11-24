"""
群交模板服务测试
================
- 群交结算：验证守卫条件、各部位写入规则、双手顶替、六九式覆盖，以及道具类行为不改模板且模板 B 不变。
- 模板统计与部位查询：验证空模板、仅模板 A、双模板启用后的统计结果，以及部位空缺与占用状态。
- 行为筛选与清理：验证部位映射、过滤开关、无指令映射项、处女保护过滤及双模板角色清理。
- 调用方与面板：验证状态重置、指令启动、NPC 群交补位经服务生效，以及面板不定义六个模板函数。
- 导入边界：验证导入解析自测、服务与五处后端调用方不导入面板，以及屏蔽面板子进程运行全部六个函数。
"""

import ast
import datetime
import json
import subprocess
import sys
from importlib.util import resolve_name
from pathlib import PurePosixPath
from typing import Any
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant, game_type, get_text
from Script.Design import handle_npc_ai_in_h
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, flags, h_state, modes
from Script.Modules.gameplay_resolution import group_sex_service, working
from Script.Settle import default as settle_default
from Script.System.Instruct_System import handle_instruct
from Script.System.Sex_System import group_sex_panel
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

PANEL = "Script.System.Sex_System.group_sex_panel"
"""导入边界测试中禁止后端调用方导入的群交面板模块全名。"""
SERVICE = "Script/Modules/gameplay_resolution/group_sex_service.py"
"""群交模板服务模块在仓库中的相对路径。"""
CALLERS = (
    "Script/Design/handle_npc_ai_in_h.py",
    "Script/Design/settle_behavior.py",
    "Script/Settle/default.py",
    "Script/System/Education_System/sex_class_handle.py",
    "Script/System/Instruct_System/handle_instruct.py",
)
"""五个后端调用方模块在仓库中的相对路径元组。"""
MOVED = (
    "group_sex_settle",
    "count_group_sex_instruct_list",
    "count_group_sex_character_list",
    "get_status_id_list_from_group_sex_body_part",
    "get_now_template_part_list",
    "clear_character_data_in_group_sex_template",
)
"""群交模板服务提供的六个核心函数名元组。"""
EMPTY = [-1, -1]
"""表示未占用对单部位槽位的默认值 [-1, -1]。"""
NO_SERVE = [[-1], -1]
"""表示未启用侍奉槽位的默认值 [[-1], -1]。"""
PARTS = ["mouth", "L_hand", "R_hand", "penis", "anal"]
"""按模板键顺序排列的五个对单部位键名列表。"""

_ = get_text._


class TemplateCase(FastTestCase):
    """群交模板测试基类，准备测试角色、工作集与群交模式，并提供模板读写辅助方法。"""

    def setUp(self) -> None:
        """创建玩家 0 与干员 1 至 4，打开内核状态工作集并开启群交模式。"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid in (1, 2, 3, 4):
            self.world.chara(cid, f"干员{cid}")
        self.enterContext(working.based_on(core.state()))
        modes.set_group_sex(True)

    def tpl(self, name: str = "A") -> list[Any]:
        """读取玩家 0 指定名称（默认为 A）的群交模板数据。"""
        return h_state.view(0).group_sex_body_template_dict[name]

    def snapshot(self, cid: int) -> dict[str, Any]:
        """经 JSON 往返深拷贝返回角色 cid 的完整群交模板字典（含模板 A 与 B）。"""
        return json.loads(
            json.dumps(h_state.view(cid).group_sex_body_template_dict)
        )

    def fill(
        self,
        name: str = "A",
        /,
        serve: list[Any] | None = None,
        **parts: list[Any],
    ) -> None:
        """向玩家 0 指定模板写入对单部位槽位与可选的侍奉槽位数据。"""
        with h_state.editing(0) as hs:
            tpl = hs.group_sex_body_template_dict[name]
            tpl[0].update(parts)
            if serve is not None:
                tpl[1] = serve


class SettleTest(TemplateCase):
    """验证 group_sex_settle 的守卫条件与各行为分组的模板写入规则。"""

    def test_guards_leave_template_unchanged(self) -> None:
        """验证群交模式关闭、非玩家执行、目标为自身或模板锁定时，玩家与执行者的完整模板均保持不变。"""
        cases = {
            "mode_off": (lambda: modes.set_group_sex(False), 0, 1),
            "npc_actor": (lambda: None, 1, 2),
            "self_target": (lambda: None, 0, 0),
            "locked": (lambda: h_state.set(0, group_sex_lock_flag=True), 0, 1),
        }
        for label, (arrange, actor, target) in cases.items():
            with self.subTest(label), working.based_on(core.state()):
                modes.set_group_sex(True)
                arrange()
                before = [self.snapshot(0), self.snapshot(actor)]
                group_sex_service.group_sex_settle(actor, target, "kiss_h")
                after = [self.snapshot(0), self.snapshot(actor)]
                self.assertEqual(after, before)

    def test_insert_takes_penis_and_clears_service(self) -> None:
        """验证插入类行为写入 penis 槽位并清空侍奉槽位。"""
        self.fill(serve=[[2], "handjob"])
        group_sex_service.group_sex_settle(0, 1, "normal_sex")
        self.assertEqual(self.tpl()[0]["penis"], [1, "normal_sex"])
        self.assertEqual(self.tpl()[1], NO_SERVE)

    def test_service_resets_on_new_behavior_and_appends_on_same(self) -> None:
        """验证侍奉类行为清空 penis、异行为重置侍奉并在同行为时去重追加目标。"""
        self.fill(penis=[1, "normal_sex"])
        steps = [
            (2, "handjob", [[2], "handjob"]),
            (3, "handjob", [[2, 3], "handjob"]),
            (2, "handjob", [[2, 3], "handjob"]),
            (1, "blowjob", [[1], "blowjob"]),
        ]
        for target, behavior, serve in steps:
            group_sex_service.group_sex_settle(0, target, behavior)
            self.assertEqual(self.tpl()[1], serve)
        self.assertEqual(self.tpl()[0]["penis"], EMPTY)

    def test_mouth_and_anal_take_their_slot(self) -> None:
        """验证口类与肛类行为分别写入 mouth 与 anal 槽位且不影响侍奉槽位。"""
        group_sex_service.group_sex_settle(0, 1, "kiss_h")
        group_sex_service.group_sex_settle(0, 2, "make_lick_anal")
        self.assertEqual(self.tpl()[0]["mouth"], [1, "kiss_h"])
        self.assertEqual(self.tpl()[0]["anal"], [2, "make_lick_anal"])
        self.assertEqual(self.tpl()[1], NO_SERVE)

    def test_hands_fill_left_then_right_then_shift(self) -> None:
        """验证手类行为依次占用左手与右手、同目标原地更新并在第三目标时左移顶替。"""
        steps = [
            (1, "making_out", [1, "making_out"], EMPTY),
            (2, "breast_caress", [1, "making_out"], [2, "breast_caress"]),
            (
                1,
                "twiddle_nipples",
                [1, "twiddle_nipples"],
                [2, "breast_caress"],
            ),
            (2, "clit_caress", [1, "twiddle_nipples"], [2, "clit_caress"]),
            (3, "open_labia", [2, "clit_caress"], [3, "open_labia"]),
        ]
        for target, behavior, left, right in steps:
            group_sex_service.group_sex_settle(0, target, behavior)
            hands = [self.tpl()[0]["L_hand"], self.tpl()[0]["R_hand"]]
            self.assertEqual(hands, [left, right], behavior)

    def test_sixty_nine_takes_mouth_and_resets_service(self) -> None:
        """验证六九式行为写入 mouth、清空 penis 并将侍奉重置为该单人目标。"""
        self.fill(serve=[[2, 3], "sixty_nine"], penis=[2, "normal_sex"])
        group_sex_service.group_sex_settle(0, 1, "sixty_nine")
        self.assertEqual(self.tpl()[0]["mouth"], [1, "sixty_nine"])
        self.assertEqual(self.tpl()[0]["penis"], EMPTY)
        self.assertEqual(self.tpl()[1], [[1], "sixty_nine"])

    def test_item_behavior_and_template_b_untouched(self) -> None:
        """验证道具类行为 put_condom 不改动玩家完整模板，且后续结算 kiss_h 写入 mouth 后模板 B 仍保持不变。"""
        before = self.snapshot(0)
        group_sex_service.group_sex_settle(0, 1, "put_condom")
        self.assertEqual(self.snapshot(0), before)
        group_sex_service.group_sex_settle(0, 1, "kiss_h")
        self.assertEqual(self.tpl()[0]["mouth"], [1, "kiss_h"])
        self.assertEqual(self.snapshot(0)["B"], before["B"])


class CountTest(TemplateCase):
    """验证群交模板行为统计与参与角色统计函数。"""

    def counts(self) -> tuple[list[str], list[list[Any]], list[int]]:
        """同时调用行为统计与角色统计函数，返回排序后的去重列表与完整槽位记录。"""
        instructs, full = group_sex_service.count_group_sex_instruct_list()
        chara = group_sex_service.count_group_sex_character_list()
        return sorted(instructs), full, sorted(chara)

    def test_empty_template_counts_nothing(self) -> None:
        """验证空模板下两项统计函数均返回空列表。"""
        self.assertEqual(self.counts(), ([], [], []))

    def test_counts_template_a_slots_and_service(self) -> None:
        """验证双模板未启用时仅统计模板 A 的槽位与侍奉，并折叠重复行为编号。"""
        self.fill(
            serve=[[2, 3], "handjob"],
            mouth=[1, "kiss_h"],
            L_hand=[2, "making_out"],
            R_hand=[1, "kiss_h"],
        )
        self.fill("B", mouth=[4, "kiss_h"])
        self.assertEqual(
            self.counts(),
            (
                ["handjob", "kiss_h", "making_out"],
                [
                    [[1], "kiss_h"],
                    [[2], "making_out"],
                    [[1], "kiss_h"],
                    [[2, 3], "handjob"],
                ],
                [1, 2, 3],
            ),
        )

    def test_full_template_run_adds_template_b(self) -> None:
        """验证启用全模板运行标志后将模板 B 的槽位与侍奉一并纳入统计。"""
        self.fill(mouth=[1, "kiss_h"])
        self.fill("B", serve=[[4], "blowjob"], anal=[1, "make_lick_anal"])
        h_state.set(0, all_group_sex_temple_run=True)
        self.assertEqual(
            self.counts(),
            (
                ["blowjob", "kiss_h", "make_lick_anal"],
                [
                    [[1], "kiss_h"],
                    [[1], "make_lick_anal"],
                    [[4], "blowjob"],
                ],
                [1, 4],
            ),
        )


class PartListTest(TemplateCase):
    """验证 get_now_template_part_list 的空缺与占用部位划分逻辑。"""

    def test_part_lists_follow_penis_and_service(self) -> None:
        """验证空模板、penis 已占、二人侍奉与四人侍奉四种场景的空缺与占用结果。"""
        join = _("加入侍奉")
        cases = {
            "empty": ({}, (PARTS + ["侍奉"], [])),
            "penis": (
                {"penis": [1, "normal_sex"], "mouth": [2, "kiss_h"]},
                (["L_hand", "R_hand", "anal"], ["mouth", "penis"]),
            ),
            "serve_two": (
                {"serve": [[1, 2], "handjob"]},
                (["mouth", "L_hand", "R_hand", "anal", join], ["侍奉"]),
            ),
            "serve_four": (
                {"serve": [[1, 2, 3, 4], "handjob"]},
                (["mouth", "L_hand", "R_hand", "anal"], ["侍奉"]),
            ),
        }
        for label, (fill, expected) in cases.items():
            with self.subTest(label), working.based_on(core.state()):
                self.fill(**fill)
                self.assertEqual(
                    group_sex_service.get_now_template_part_list(), expected
                )


class StatusListTest(TemplateCase):
    """验证 get_status_id_list_from_group_sex_body_part 的映射与过滤逻辑。"""

    def setUp(self) -> None:
        """为全部群交部位行为填充指令映射，并清空前提配置与指令过滤开关。"""
        super().setUp()
        lists = game_config.config_behavior_id_list_of_group_sex_body_part
        ids = {b: f"I_{b}" for part in lists.values() for b in part}
        self.enterContext(
            mock.patch.dict(constant.behavior_id_to_instruct_id, ids)
        )
        self.enterContext(
            mock.patch.dict(constant.instruct_premise_data, clear=True)
        )
        self.enterContext(
            mock.patch.dict(
                normal_config.system_setting.instruct_index_filter, clear=True
            )
        )

    def test_each_body_part_lists_its_behaviors(self) -> None:
        """验证六个部位键分别返回配置中对应分组的全部行为编号。"""
        lists = game_config.config_behavior_id_list_of_group_sex_body_part
        parts = {
            "mouth": "口",
            "L_hand": "手",
            "R_hand": "手",
            "penis": "插入",
            "侍奉": "侍奉",
            "anal": "肛",
        }
        for part, config_part in parts.items():
            with self.subTest(part):
                self.assertEqual(
                    group_sex_service.get_status_id_list_from_group_sex_body_part(
                        part
                    ),
                    lists[config_part],
                )

    def test_filter_and_virgin_gate_drop_behaviors(self) -> None:
        """验证指令关闭、缺少指令映射与目标仍有处女素质时的行为过滤及恢复效果。"""
        find = group_sex_service.get_status_id_list_from_group_sex_body_part
        normal_config.system_setting.instruct_index_filter["I_back_sex"] = False
        del constant.behavior_id_to_instruct_id["riding_sex"]
        listed = find("penis")
        self.assertEqual(listed[:2], ["normal_sex", "back_riding_sex"])
        activity.set_target(0, 1)
        abilities.talent(1).merge({0: 1, 1: 0, 2: 0, 3: 0, 4: 1})
        self.assertNotIn("normal_sex", find("penis"))
        self.assertEqual(find("mouth")[:1], ["breast_sucking"])
        abilities.talent(1).merge({0: 0, 4: 0})
        self.assertEqual(find("penis"), listed)
        self.assertEqual(find("mouth")[:1], ["kiss_h"])


class ClearTest(TemplateCase):
    """验证 clear_character_data_in_group_sex_template 的清理行为与返回值。"""

    def test_clear_resets_character_in_both_templates(self) -> None:
        """验证清理角色会重置模板 A 与 B 中对应槽位并缩减侍奉列表，重复清理返回 False。"""
        self.fill(serve=[[2, 3], "handjob"], mouth=[2, "kiss_h"])
        self.fill("B", L_hand=[2, "making_out"], anal=[1, "make_lick_anal"])
        self.assertTrue(
            group_sex_service.clear_character_data_in_group_sex_template(2)
        )
        self.assertEqual(self.tpl()[0]["mouth"], EMPTY)
        self.assertEqual(self.tpl()[1], [[3], "handjob"])
        self.assertEqual(self.tpl("B")[0]["L_hand"], EMPTY)
        self.assertEqual(self.tpl("B")[0]["anal"], [1, "make_lick_anal"])
        self.assertFalse(
            group_sex_service.clear_character_data_in_group_sex_template(2)
        )


class CallerTest(TemplateCase):
    """验证三处后端调用方经由群交模板服务生效，以及面板模块不定义六个模板函数。"""

    def test_h_state_reset_clears_character_from_template(self) -> None:
        """验证 handle_self_h_state_reset 会从模板 A 与 B 清除指定角色。"""
        self.fill(serve=[[2, 3], "handjob"], mouth=[1, "kiss_h"])
        self.fill("B", penis=[2, "normal_sex"])
        settle_default.handle_self_h_state_reset(
            2, 1, game_type.CharacterStatusChange(), datetime.datetime.now()
        )
        self.assertEqual(self.tpl()[0]["mouth"], [1, "kiss_h"])
        self.assertEqual(self.tpl()[1], [[3], "handjob"])
        self.assertEqual(self.tpl("B")[0]["penis"], EMPTY)

    def test_start_instruct_records_template(self) -> None:
        """验证 start_instruct 执行交互行为时会在模板 A 记录对应部位。"""
        chosen: Any = dict(behavior_id="kiss_h", target=1, minutes=5, args={})
        handle_instruct.start_instruct(0, chosen)
        self.assertEqual(self.tpl()[0]["mouth"], [1, "kiss_h"])

    def test_npc_ai_joins_service_once(self) -> None:
        """验证 npc_ai_in_group_sex 在仅余加入侍奉空位时将 NPC 纳入侍奉且不重复加入。"""
        flags.set(3, is_h=True)
        taken = {part: [1, "kiss_h"] for part in PARTS if part != "penis"}
        self.fill(serve=[[2], "handjob"], **taken)
        handle_npc_ai_in_h.npc_ai_in_group_sex(3)
        self.assertEqual(self.tpl()[1], [[2, 3], "handjob"])
        handle_npc_ai_in_h.npc_ai_in_group_sex(3)
        self.assertEqual(self.tpl()[1], [[2, 3], "handjob"])

    def test_panel_keeps_no_template_functions(self) -> None:
        """验证 group_sex_panel 模块不暴露 MOVED 中的六个模板服务函数。"""
        self.assertEqual(
            [name for name in MOVED if hasattr(group_sex_panel, name)], []
        )


def imported(source: str | bytes, path: str) -> set[str]:
    """解析源码中的绝对、相对与嵌套导入语句，返回按模块路径展开后的完整导入名集合。"""
    package = ".".join(PurePosixPath(path).parent.parts)
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def forbidden(source: str | bytes, path: str) -> list[str]:
    """筛选源码导入名中等于或位于 group_sex_panel 下的条目并按字典序返回。"""
    return sorted(
        name
        for name in imported(source, path)
        if name == PANEL or name.startswith(PANEL + ".")
    )


BLOCKED_RUN = """
import importlib.abc, json, sys

BLOCKED = ("Script.UI.Panel", "Script.System.Sex_System.group_sex_panel")

class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if any(fullname == b or fullname.startswith(b + ".") for b in BLOCKED):
            raise ImportError(fullname)
        return None

sys.meta_path.insert(0, Block())
from tests import kernel_data
from tests.fast import WORLD
from Script.Core import constant
from Script.Kernel import core
from Script.Modules.domains import modes, warehouse
from Script.Modules.gameplay_resolution import working
from Script.Modules.gameplay_resolution import group_sex_service as s

WORLD.reset()
kernel_data.written(warehouse.start, {})
for cid in range(4):
    WORLD.chara(cid, str(cid))
with working.based_on(core.state()):
    modes.set_group_sex(True)
    s.group_sex_settle(0, 1, "kiss_h")
    s.group_sex_settle(0, 2, "handjob")
    s.group_sex_settle(0, 3, "handjob")
    instructs, full = s.count_group_sex_instruct_list()
    out = [sorted(instructs), full, sorted(s.count_group_sex_character_list())]
    out.append(s.get_now_template_part_list()[1])
    out.append(s.clear_character_data_in_group_sex_template(2))
    out.append(sorted(s.count_group_sex_character_list()))
    constant.behavior_id_to_instruct_id["kiss_h"] = "I_kiss_h"
    out.append(s.get_status_id_list_from_group_sex_body_part("mouth"))
out.append(sorted(m for m in sys.modules if m.startswith(BLOCKED)))
print(json.dumps(out))
"""
"""在子进程中屏蔽界面面板与群交面板后导入并运行群交模板服务的验证脚本源码。"""


class ImportBoundaryTest(FastTestCase):
    """验证群交模板服务与五处后端调用方的导入边界，以及屏蔽面板时的独立运行能力。"""

    def test_checker_resolves_relative_and_multi_name_imports(self) -> None:
        """验证 forbidden 能正确识别相对、多名与函数内嵌套导入，且不误报同前缀模块。"""
        source = (
            "from . import group_sex_panel, hidden_sex_panel\n"
            "import Script.System.Sex_System.group_sex_panel_extra\n"
            "def f():\n"
            "    from ..Sex_System.group_sex_panel import SeeGroupSexInfoPanel\n"
        )
        self.assertEqual(
            forbidden(source, "Script/System/Sex_System/probe.py"),
            [PANEL, f"{PANEL}.SeeGroupSexInfoPanel"],
        )

    def test_service_and_callers_import_no_group_sex_panel(self) -> None:
        """验证 group_sex_service.py 与五个后端调用方模块均不导入 group_sex_panel 及其成员。"""
        for path in (SERVICE, *CALLERS):
            with self.subTest(path):
                self.assertEqual(
                    forbidden((ROOT / path).read_bytes(), path), []
                )

    def test_service_runs_with_panels_blocked(self) -> None:
        """验证屏蔽 Script.UI.Panel 与 group_sex_panel 的子进程可运行全部六个服务函数且不加载被屏蔽模块。"""
        result = subprocess.run(
            [sys.executable, "-c", BLOCKED_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(
            json.loads(result.stdout.splitlines()[-1]),
            [
                ["handjob", "kiss_h"],
                [[[1], "kiss_h"], [[2, 3], "handjob"]],
                [1, 2, 3],
                ["mouth", "侍奉"],
                True,
                [1, 3],
                ["kiss_h"],
                [],
            ],
        )
