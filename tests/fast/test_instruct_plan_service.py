"""
指令规划服务测试
================
覆盖时长解析、目标等待入队、群交成员与判定、通用结算入队、综合指令状态结算、handle_instruct 兼容导出与界面导入隔离。
"""

import ast
import datetime
import json
import subprocess
import sys
from collections.abc import Mapping
from importlib.util import resolve_name
from pathlib import PurePosixPath
from typing import Any
from unittest import mock

from Script.Config import game_config
from Script.Core import constant, game_type, get_text
from Script.Design import instuct_judege
from Script.Kernel import core
from Script.Modules.domains import action_info, activity, plan
from Script.Modules.gameplay_resolution import group_sex_service
from Script.Modules.gameplay_resolution import instruct_plan_service as svc
from Script.Modules.gameplay_resolution import intent, plan_queue, start_gate
from Script.Modules.gameplay_resolution import working
from Script.System.Instruct_System import handle_instruct
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports

_ = get_text._

SERVICE_PATH = "Script/Modules/gameplay_resolution/instruct_plan_service.py"
""" 指令规划服务模块的仓库相对路径。 """
NO_HANDLE_INSTRUCT_CALLERS = (
    "Script/Design/settle_behavior.py",
    "Script/Settle/realtime_settle.py",
)
""" 不导入 handle_instruct 的后端调用方路径元组。 """
HANDLE_INSTRUCT_MODULE = "Script.System.Instruct_System.handle_instruct"
""" 禁止上述后端调用方导入的交互指令模块全名。 """
SCENE_A = ["宿舍", "1区", "102"]
""" 测试同场景群交成员时使用的第一个场景路径。 """
SCENE_B = ["宿舍", "1区", "103"]
""" 测试排除其他场景成员时使用的第二个场景路径。 """
BLOCKED_IMPORT_RUN = """
import importlib, importlib.abc, json, sys
BLOCKED = (
    "Script.UI",
    "Script.Core.flow_handle",
    "Script.Core.game_init",
    "Script.Modules.tk_ui",
    "tkinter",
    "_tkinter",
)
ALLOWED_TK_UI = frozenset({"Script.Modules.tk_ui", "Script.Modules.tk_ui.orders"})
def is_blocked(name):
    if name in ALLOWED_TK_UI:
        return False
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
from Script.Config import normal_config
normal_config.init_normal_config()
from Script.Core import constant
from Script.Modules.gameplay_resolution import instruct_plan_service
importlib.import_module("Script.Design.second_behavior")
importlib.import_module("Script.Design.settle_behavior")
print(json.dumps({
    "duration": instruct_plan_service.instruct_duration(constant.Behavior.WAIT, 5),
    "loaded": sorted(name for name in sys.modules if is_blocked(name)),
}))
"""
""" 子进程脚本：屏蔽界面与窗口模块后导入指令规划服务、二段行为与行为结算模块，核对零误加载。 """


def _imported_names(source: bytes, path: str) -> list[tuple[int, str]]:
    """解析源码语法树，返回全部解析后的导入模块或成员全名列表。"""
    package = ".".join(PurePosixPath(path).parent.parts)
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package)
            found.append((node.lineno, base))
            found.extend(
                (node.lineno, f"{base}.{alias.name}") for alias in node.names
            )
    return sorted(found)


def _run_json(script: str) -> dict[str, Any]:
    """在独立子进程执行隔离导入脚本并解析末行 JSON 输出。"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr[-2000:])
    return json.loads(result.stdout.splitlines()[-1])


class InstructPlanCase(FastTestCase):
    """指令规划服务测试基类，准备玩家 0 与干员 1、2、3 并打开工作集。"""

    def setUp(self) -> None:
        """创建测试角色、打开内核工作集并清空待提交打断。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.world.chara(2, "干员乙")
        self.world.chara(3, "干员丙")
        self.enterContext(working.based_on(core.state()))
        plan_queue.forget()


class InstructDurationAndWaitTest(InstructPlanCase):
    """时长解析与交互对象等待入队行为测试。"""

    def test_instruct_duration_explicit_and_table_and_floor(self) -> None:
        """验证显式正时长原样返回、为 0 时查配置表，以及配置值不大于 0 时夹紧为 1。"""
        self.assertEqual(svc.instruct_duration(constant.Behavior.WAIT, 12), 12)
        patched = {
            "sample_pos": type("Cfg", (), {"duration": 15})(),
            "sample_zero": type("Cfg", (), {"duration": 0})(),
            "sample_neg": type("Cfg", (), {"duration": -5})(),
        }
        with mock.patch.dict(game_config.config_behavior, patched):
            self.assertEqual(svc.instruct_duration("sample_pos", 0), 15)
            self.assertEqual(svc.instruct_duration("sample_zero", 0), 1)
            self.assertEqual(svc.instruct_duration("sample_neg", 0), 1)

    def test_plan_target_wait_player_present_and_absent(self) -> None:
        """验证玩家与在编干员排入打断等待，未在编角色直接跳过且不产生打断。"""
        mark = plan_queue.mark()
        svc.plan_target_wait(0, 7)
        svc.plan_target_wait(1, 9)
        svc.plan_target_wait(99, 11)
        self.assertEqual(plan_queue.take_since(mark), ["0", "1"])
        for who, minutes in ((0, 7), (1, 9)):
            q = plan.queue(who)
            self.assertEqual(len(q), 1)
            self.assertEqual(q[0][1]["behavior_id"], constant.Behavior.WAIT)
            self.assertEqual(q[0][1]["minutes"], minutes)
            self.assertEqual(
                q[0][1]["state"], constant.CharacterStatus.STATUS_WAIT
            )
        self.assertEqual(plan.queue(99), [])


class GroupMembersAndJudgeTest(InstructPlanCase):
    """同场景群交成员查询、群交判定与行为判定映射测试。"""

    def test_group_members_returns_non_player_occupants_in_same_scene(
        self,
    ) -> None:
        """验证 group_members 返回调用角色所在场景中除玩家 0 外的全部在编角色。"""
        for cid, pos in (
            (0, SCENE_A),
            (1, SCENE_A),
            (2, SCENE_A),
            (3, SCENE_B),
        ):
            activity.set_position(cid, pos)
        self.assertEqual(svc.group_members(0), [1, 2])
        self.assertEqual(svc.group_members(1), [1, 2])
        self.assertEqual(svc.group_members(3), [3])

    def test_judged_group_sex_accept_and_refusal(self) -> None:
        """验证全员同意返回原行为，有人拒绝时写入拒绝列表并返回邀请群交失败。"""
        for cid, pos in (
            (0, SCENE_A),
            (1, SCENE_A),
            (2, SCENE_A),
            (3, SCENE_B),
        ):
            activity.set_position(cid, pos)
        with mock.patch.object(
            instuct_judege, "calculation_instuct_judege", return_value=[1]
        ) as mocked:
            res = svc.judged_group_sex(constant.Behavior.ASK_GROUP_SEX, 0)
        self.assertEqual(res, constant.Behavior.ASK_GROUP_SEX)
        self.assertEqual(
            mocked.call_args_list,
            [
                mock.call(0, 1, _("群交"), not_draw_flag=True),
                mock.call(0, 2, _("群交"), not_draw_flag=True),
            ],
        )
        with mock.patch.object(
            instuct_judege,
            "calculation_instuct_judege",
            side_effect=lambda a, t, j, *, not_draw_flag=False: (
                [1] if t == 1 else [0]
            ),
        ):
            failed = svc.judged_group_sex(constant.Behavior.ASK_GROUP_SEX, 0)
        self.assertEqual(failed, constant.Behavior.ASK_GROUP_SEX_FAIL)
        self.assertEqual(
            action_info.get(0, "ask_group_sex_refuse_chara_id_list"), [2]
        )

    def test_judged_behavior_id_empty_group_pass_and_fail_mappings(
        self,
    ) -> None:
        """验证空判定直通、群交分派、判定通过原样返回，以及失败时映射到对应失败行为。"""
        with mock.patch.object(
            instuct_judege, "calculation_instuct_judege"
        ) as mocked:
            self.assertEqual(svc.judged_behavior_id("kiss", 0, 1, ""), "kiss")
            mocked.assert_not_called()
        with mock.patch.object(
            svc,
            "judged_group_sex",
            return_value=constant.Behavior.ASK_GROUP_SEX_FAIL,
        ) as group_mock:
            self.assertEqual(
                svc.judged_behavior_id(
                    constant.Behavior.ASK_GROUP_SEX, 0, 1, _("群交")
                ),
                constant.Behavior.ASK_GROUP_SEX_FAIL,
            )
            group_mock.assert_called_once_with(
                constant.Behavior.ASK_GROUP_SEX, 0
            )
        with mock.patch.object(
            instuct_judege, "calculation_instuct_judege", return_value=[1]
        ):
            self.assertEqual(
                svc.judged_behavior_id("kiss", 0, 1, _("亲吻")), "kiss"
            )
        cases = (
            (_("初级骚扰"), constant.Behavior.LOW_OBSCENITY_ANUS),
            (_("道具"), constant.Behavior.LOW_OBSCENITY_ANUS),
            (_("口交"), constant.Behavior.LOW_OBSCENITY_ANUS),
            (_("严重骚扰"), constant.Behavior.HIGH_OBSCENITY_ANUS),
            (_("药物"), constant.Behavior.HIGH_OBSCENITY_ANUS),
            (_("SM"), constant.Behavior.HIGH_OBSCENITY_ANUS),
            (_("性交"), constant.Behavior.HIGH_OBSCENITY_ANUS),
            (_("A性交"), constant.Behavior.HIGH_OBSCENITY_ANUS),
            (_("U开发"), constant.Behavior.HIGH_OBSCENITY_ANUS),
            (_("U性交"), constant.Behavior.HIGH_OBSCENITY_ANUS),
            (_("亲吻"), constant.Behavior.KISS_FAIL),
            (_("H模式"), constant.Behavior.DO_H_FAIL),
            (_("告白"), constant.Behavior.CONFESSION_FAILED),
            (_("戴上项圈"), constant.Behavior.GIVE_NECKLACE_FAILED),
            (_("隐奸"), constant.Behavior.ASK_HIDDEN_SEX_FAIL),
            (_("露出"), constant.Behavior.ASK_EXHIBITIONISM_SEX_FAIL),
            ("未知判定条件", "orig_behavior"),
        )
        with mock.patch.object(
            instuct_judege, "calculation_instuct_judege", return_value=[0]
        ):
            for judge_name, expected in cases:
                with self.subTest(judge=judge_name):
                    self.assertEqual(
                        svc.judged_behavior_id(
                            "orig_behavior", 0, 1, judge_name
                        ),
                        expected,
                    )


class PlanInstructCommonSettleTest(InstructPlanCase):
    """plan_instruct_common_settle 目标解析、等待、群交结算与入队测试。"""

    def test_default_target_and_player_no_interrupt(self) -> None:
        """验证未传目标时沿用当前交互对象，玩家入队不打断且触发群交模板结算。"""
        activity.set_target(0, 1)
        mark = plan_queue.mark()
        with mock.patch.object(group_sex_service, "group_sex_settle") as gs:
            ret = svc.plan_instruct_common_settle(
                constant.Behavior.WAIT, duration=6
            )
        self.assertEqual(ret, ())
        self.assertEqual(plan_queue.take_since(mark), [])
        gs.assert_called_once_with(0, 1, constant.Behavior.WAIT)
        item = plan.queue(0)[0][1]
        self.assertEqual(
            (item["behavior_id"], item["minutes"], item["target"]),
            (constant.Behavior.WAIT, 6, 1),
        )

    def test_npc_interrupt_and_force_target_wait(self) -> None:
        """验证干员入队附带打断、开启 force_taget_wait 时目标排等待，目标为自身不重复排等待。"""
        mark = plan_queue.mark()
        with mock.patch.object(group_sex_service, "group_sex_settle") as gs:
            ret = svc.plan_instruct_common_settle(
                constant.Behavior.REST,
                character_id=1,
                target_character_id=2,
                duration=8,
                force_taget_wait=True,
            )
        self.assertEqual(ret, ())
        self.assertEqual(plan_queue.take_since(mark), ["2", "1"])
        gs.assert_called_once_with(1, 2, constant.Behavior.REST)
        self.assertEqual(
            (
                plan.queue(1)[0][1]["behavior_id"],
                plan.queue(1)[0][1]["minutes"],
            ),
            (constant.Behavior.REST, 8),
        )
        self.assertEqual(
            (
                plan.queue(2)[0][1]["behavior_id"],
                plan.queue(2)[0][1]["minutes"],
            ),
            (constant.Behavior.WAIT, 8),
        )
        mark_self = plan_queue.mark()
        svc.plan_instruct_common_settle(
            constant.Behavior.REST,
            character_id=3,
            target_character_id=3,
            duration=4,
            force_taget_wait=True,
        )
        self.assertEqual(plan_queue.take_since(mark_self), ["3"])
        self.assertEqual(len(plan.queue(3)), 1)

    def test_failed_judge_uses_failed_behavior_duration(self) -> None:
        """验证判定失败后按失败行为查表计算时长并排入队列。"""
        fail_cfg = type("Cfg", (), {"duration": 3})()
        with (
            mock.patch.object(
                instuct_judege, "calculation_instuct_judege", return_value=[0]
            ),
            mock.patch.dict(
                game_config.config_behavior,
                {constant.Behavior.KISS_FAIL: fail_cfg},
            ),
            mock.patch.object(group_sex_service, "group_sex_settle") as gs,
        ):
            ret = svc.plan_instruct_common_settle(
                "kiss", character_id=0, target_character_id=1, judge=_("亲吻")
            )
        self.assertEqual(ret, ())
        gs.assert_called_once_with(0, 1, constant.Behavior.KISS_FAIL)
        item = plan.queue(0)[0][1]
        self.assertEqual(
            (item["behavior_id"], item["minutes"]),
            (constant.Behavior.KISS_FAIL, 3),
        )


class ComprehensiveStateEffectTest(InstructPlanCase):
    """handle_comprehensive_state_effect 各类目标分支与返回值测试。"""

    def _call(
        self, effect_list: list[str], character_id: int, add_time: int
    ) -> int | None:
        """使用固定时间戳与空白状态变更对象调用综合指令状态结算。"""
        return svc.handle_comprehensive_state_effect(
            effect_list,
            character_id,
            add_time,
            game_type.CharacterStatusChange(),
            datetime.datetime(2026, 1, 1, 8, 0),
        )

    def test_zero_add_time_and_a1(self) -> None:
        """验证结算时长为 0 时直接返回 None 不入队，A1 沿用玩家目标排入行动。"""
        self.assertIsNone(self._call(["A1", constant.Behavior.WAIT], 0, 0))
        self.assertEqual(plan.queue(0), [])
        activity.set_target(0, 1)
        self.assertIsNone(self._call(["A1", constant.Behavior.WAIT], 0, 5))
        item = plan.queue(0)[0][1]
        self.assertEqual(
            (item["behavior_id"], item["target"]), (constant.Behavior.WAIT, 1)
        )

    def test_a2_missing_existing_and_npc_retarget(self) -> None:
        """验证 A2 无目标返回 0、有目标正常排入、非当前目标 NPC 触发先改写玩家交互对象。"""
        activity.set_target(0, 0)
        self.assertEqual(self._call(["A2", constant.Behavior.WAIT], 0, 5), 0)
        self.assertEqual(plan.queue(0), [])
        activity.set_target(0, 1)
        self.assertIsNone(self._call(["A2", constant.Behavior.WAIT], 0, 5))
        self.assertEqual(plan.queue(0)[-1][1]["target"], 1)
        self.assertIsNone(self._call(["A2", constant.Behavior.REST], 2, 5))
        self.assertEqual(activity.target(0), 2)
        item = plan.queue(0)[-1][1]
        self.assertEqual(
            (item["behavior_id"], item["target"]), (constant.Behavior.REST, 2)
        )

    def test_a3_owned_and_unowned(self) -> None:
        """验证 A3|<id> 对在编角色正常排入，对未持有角色返回 0 且不入队。"""
        self.assertEqual(self._call(["A3|99", constant.Behavior.WAIT], 0, 5), 0)
        self.assertEqual(plan.queue(0), [])
        self.assertIsNone(self._call(["A3|2", constant.Behavior.WAIT], 0, 5))
        item = plan.queue(0)[0][1]
        self.assertEqual(
            (item["behavior_id"], item["target"]), (constant.Behavior.WAIT, 2)
        )


class HandleInstructCompatibilityTest(InstructPlanCase):
    """handle_instruct 兼容导出与既有调用及测试替换路径兼容性测试。"""

    def test_handle_instruct_exports_delegate_and_monkeypatch(self) -> None:
        """验证 handle_instruct 七个兼容符号指向服务且属性替换对 start_gate._judged 生效。"""
        pairs = (
            (handle_instruct._group_members, svc.group_members),
            (handle_instruct._judged_group_sex, svc.judged_group_sex),
            (handle_instruct._judged_behavior_id, svc.judged_behavior_id),
            (handle_instruct._instruct_duration, svc.instruct_duration),
            (handle_instruct._plan_target_wait, svc.plan_target_wait),
            (
                handle_instruct.plan_instruct_common_settle,
                svc.plan_instruct_common_settle,
            ),
            (
                handle_instruct.handle_comprehensive_state_effect,
                svc.handle_comprehensive_state_effect,
            ),
        )
        for exported, expected in pairs:
            self.assertIs(exported, expected)
        self.assertEqual(
            handle_instruct.plan_instruct_common_settle(
                constant.Behavior.WAIT, 0, 1, 5
            ),
            (),
        )
        self.assertIsNone(
            handle_instruct.handle_comprehensive_state_effect(
                ["A3|2", constant.Behavior.REST],
                0,
                5,
                game_type.CharacterStatusChange(),
                datetime.datetime(2026, 1, 1, 8, 0),
            )
        )
        self.assertEqual(plan.queue(0)[-1][1]["target"], 2)
        chosen = intent.Intent(behavior_id="kiss", minutes=5, target=1)
        chosen["judge"] = _("亲吻")
        act = intent.behavior_action(0, chosen)
        data = act.action_data
        assert isinstance(data, Mapping)
        with (
            mock.patch.object(
                handle_instruct, "_judged_behavior_id", lambda *a: "kiss_fail"
            ),
            mock.patch.object(
                handle_instruct, "_instruct_duration", lambda b, d: 2
            ),
        ):
            judged = start_gate._judged(act, 0, data)
        judged_data = judged.action_data
        assert isinstance(judged_data, Mapping)
        self.assertEqual(
            (judged_data["behavior_id"], judged_data["minutes"]),
            ("kiss_fail", 2),
        )


class ImportBoundaryTest(FastTestCase):
    """指令规划服务与后端调用方导入边界及屏蔽界面子进程隔离测试。"""

    def test_sources_import_no_ui_or_handle_instruct(self) -> None:
        """验证服务无禁用界面导入，且 settle_behavior 与 realtime_settle 不导入 handle_instruct。"""
        self.assertEqual(
            banned_imports((ROOT / SERVICE_PATH).read_bytes(), SERVICE_PATH),
            [],
        )
        for path in NO_HANDLE_INSTRUCT_CALLERS:
            with self.subTest(path=path):
                hits = [
                    (line, name)
                    for line, name in _imported_names(
                        (ROOT / path).read_bytes(), path
                    )
                    if name == HANDLE_INSTRUCT_MODULE
                    or name.startswith(HANDLE_INSTRUCT_MODULE + ".")
                ]
                self.assertEqual(hits, [])

    def test_modules_load_without_ui_in_subprocess(self) -> None:
        """验证独立子进程屏蔽界面后可加载服务、settle_behavior 与 second_behavior 且零误加载。"""
        self.assertEqual(
            _run_json(BLOCKED_IMPORT_RUN), {"duration": 5, "loaded": []}
        )
