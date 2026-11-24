"""
助理服务测试
============
- 候选筛选（CandidatesTest）：覆盖按编号升序、排除 2/7 异常、监狱长与访客，且不排除当前助理。
- 每周抽选（RandomPickTest）：覆盖抽中候选后任命与抽中当前助理时卸任两种路径及绘制序列。
- 助理替换（ReplaceTest）：覆盖首次任命、换人保新项、标记经二段行为调用、同人卸任、异常拒绝与宿舍恢复。
- 分隔线回调（DividerTest）：覆盖正常字符按文本宽度绘制分隔线与零宽字符被拒绝。
- 模块边界（AssistantServiceBoundaryTest）：覆盖无直接界面导入、无面板加载、结算无面板导入与面板属性检查。
"""

import ast
import datetime
import subprocess
import sys
from importlib.util import resolve_name
from unittest import mock

from Script.Config import normal_config
from Script.Core import get_text
from Script.Design import map_handle, second_behavior
from Script.Kernel import core
from Script.Modules.domains import activity, chara_life, flags, identity
from Script.Modules.domains import npc_template, relations, visitor, work
from Script.Modules.gameplay_resolution import assistant_service, ui_hooks
from Script.Modules.gameplay_resolution import working
from Script.System.Dormitory_System import common as dormitory_common
from Script.UI.Moudle import draw
from Script.UI.Panel import assistant_panel
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports

_ = get_text._
""" 文本翻译函数。 """
SERVICE = "Script/Modules/gameplay_resolution/assistant_service.py"
""" 助理服务源码的仓库相对路径。 """
SETTLE = "Script/Settle/past_day_settle.py"
""" 跨日结算源码的仓库相对路径。 """
PLAYER_ROOM = map_handle.get_map_system_path_str_for_list(["中枢", "博士房间"])
""" 中枢/博士房间的场景路径字符串。 """
PANEL = "Script.UI.Panel"
""" 跨日结算导入检查中禁止指向的界面面板包名。 """
BLOCKED_IMPORT = """
import sys


class Block:
    def find_spec(self, name, path=None, target=None):
        if name == "Script.UI.Panel" or name.startswith("Script.UI.Panel."):
            raise ImportError(name)


sys.meta_path.insert(0, Block())
from Script.Config import normal_config

normal_config.init_normal_config()
import Script.Modules.gameplay_resolution.assistant_service
"""
""" 在子进程中拦截 Script.UI.Panel 加载后再导入助理服务的源码片段。 """


def picked_text(name: str) -> str:
    """返回指定角色被抽中为博士助理时的抽签结果提示文本。"""
    return _("\n○本周抽签选中了{0}作为{1}的助理\n").format(name, "博士")


def appointed_text(name: str) -> str:
    """返回指定角色的任命提示文本。"""
    return _("\n{0}成为助理干员了，并默认开启智能跟随模式\n").format(name)


def rejected_text(name: str) -> str:
    """返回指定角色的状态异常提示文本。"""
    return _("\n{0}的状态异常，无法任命为助理干员\n").format(name)


def dismissed_text(name: str) -> str:
    """返回指定角色的卸任提示文本。"""
    return _("\n\n{0}不再是助理干员了，已清零助理服务相关的设置\n\n").format(
        name
    )


class AssistantCase(FastTestCase):
    """助理服务与分隔线测试基类。"""

    def setUp(self) -> None:
        """创建博士与五名测试角色，开启工作缓冲区并拦截三类绘制调用。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.ids = sorted(
            cid
            for cid, tem in npc_template.table().items()
            if cid and tem.Mother_id == 0 and tem.AdvNpc < 9000
        )[:5]
        for index, cid in enumerate(self.ids):
            self.world.chara(cid, f"角色{index}")
        self.enterContext(working.based_on(core.state()))
        self.drawn: list[tuple[str, float, str]] = []
        for cls in (draw.NormalDraw, draw.WaitDraw, draw.LineDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.record
                )
            )
        self.width = normal_config.config_normal.text_width
        self.rooms = list(dormitory_common.get_open_dormitory_room_occupancy())

    def record(self, now: draw.NormalDraw) -> None:
        """记录一次绘制调用的类名、宽度与文本。"""
        self.drawn.append((type(now).__name__, now.width, now.text))

    def name(self, cid: int) -> str:
        """返回指定编号角色的名称。"""
        return identity.of(cid).name

    def appoint(self, cid: int, services: dict[int, int]) -> None:
        """将指定角色设为当前助理、开启跟随并写入其服务表。"""
        relations.assistant_character_id.set(0, cid)
        flags.set(cid, is_follow=1)
        with relations.assistant_services.editing(cid) as table:
            table.update(services)

    def services(self, **items: int) -> dict[int, int]:
        """返回全部服务置零后按 sNN 关键字覆盖的服务字典。"""
        table = dict.fromkeys(relations.assistant_services(self.ids[0]), 0)
        table.update({int(key[1:]): value for key, value in items.items()})
        return table

    def wait(self, text: str) -> tuple[str, float, str]:
        """构造按文本宽度绘制的 WaitDraw 记录元组。"""
        return ("WaitDraw", self.width, text)

    def line(self) -> tuple[str, float, str]:
        """构造按文本宽度绘制字符 "-" 的 LineDraw 记录元组。"""
        return ("LineDraw", self.width, "-")


class CandidatesTest(AssistantCase):
    """助理候选角色筛选测试。"""

    def test_candidates_skip_abnormal_warden_and_visitor(self) -> None:
        """验证候选按编号升序，排除 2/7 异常、监狱长与访客，且保留当前助理。"""
        first, jailed, warden, guest, last = self.ids
        flags.set(jailed, imprisonment=True)
        work.set_warden(warden)
        visitor.arrive(guest, datetime.datetime(2030, 1, 1))
        self.appoint(first, {})
        self.assertEqual(
            assistant_service.get_assistant_candidates(), [first, last]
        )


class RandomPickTest(AssistantCase):
    """每周随机抽选助理测试。"""

    def setUp(self) -> None:
        """监禁其余四名测试角色，使候选列表仅含第一名测试角色。"""
        super().setUp()
        for cid in self.ids[1:]:
            flags.set(cid, imprisonment=True)
        self.only = self.ids[0]

    def test_pick_appoints_the_drawn_candidate(self) -> None:
        """验证无助理时抽中候选后完成任命，并依次绘制抽签结果提示、分隔线与任命提示。"""
        assistant_service.select_random_assistant()
        self.assertEqual(relations.assistant_character_id(0), self.only)
        self.assertEqual(
            self.drawn,
            [
                self.wait(picked_text(self.name(self.only))),
                self.line(),
                self.wait(appointed_text(self.name(self.only))),
            ],
        )

    def test_drawing_current_assistant_leaves_no_assistant(self) -> None:
        """验证抽中当前助理时走同人卸任分支使玩家无助理，并绘制抽签结果提示、分隔线与卸任提示。"""
        self.appoint(self.only, {2: 1})
        assistant_service.select_random_assistant()
        self.assertEqual(relations.assistant_character_id(0), 0)
        self.assertEqual(
            self.drawn,
            [
                self.wait(picked_text(self.name(self.only))),
                self.line(),
                self.wait(dismissed_text(self.name(self.only))),
            ],
        )


class ReplaceTest(AssistantCase):
    """助理替换各分支测试。"""

    def test_first_appointment(self) -> None:
        """验证首次任命开启跟随与服务 2、更新二段行为标记并绘制分隔线与任命提示。"""
        new = self.ids[0]
        assistant_service.assistant_replace(new)
        self.assertEqual(relations.assistant_character_id(0), new)
        self.assertEqual(flags.get(new, "is_follow"), 1)
        self.assertEqual(relations.assistant_services(new), self.services(s2=1))
        self.assertEqual(
            activity.second_behavior(new, "chosen_as_assistant"), 1
        )
        self.assertEqual(activity.second_behavior(new, "not_as_assistant"), 0)
        self.assertEqual(
            self.drawn, [self.line(), self.wait(appointed_text(self.name(new)))]
        )

    def test_replacing_clears_old_and_keeps_new_service_settings(self) -> None:
        """验证换人时清零旧助理跟随与服务表，新助理开启服务 2 并保留其余服务项，合并输出任命与卸任提示。"""
        old, new = self.ids[:2]
        self.appoint(old, {2: 1, 5: 2, 10: 1})
        relations.assistant_services.set_item(new, 5, 1)
        assistant_service.assistant_replace(new)
        self.assertEqual(relations.assistant_character_id(0), new)
        self.assertEqual(flags.get(old, "is_follow"), 0)
        self.assertEqual(flags.get(new, "is_follow"), 1)
        self.assertEqual(relations.assistant_services(old), self.services())
        self.assertEqual(
            relations.assistant_services(new), self.services(s2=1, s5=1)
        )
        self.assertEqual(activity.second_behavior(old, "not_as_assistant"), 1)
        self.assertEqual(
            self.drawn,
            [
                self.line(),
                self.wait(
                    appointed_text(self.name(new))
                    + dismissed_text(self.name(old))
                ),
            ],
        )

    def test_markers_go_through_second_behavior(self) -> None:
        """验证换人时四次标记更新均按顺序经 second_behavior.character_get_second_behavior 调用。"""
        old, new = self.ids[:2]
        self.appoint(old, {2: 1})
        with mock.patch.object(
            second_behavior, "character_get_second_behavior"
        ) as spy:
            assistant_service.assistant_replace(new)
        self.assertEqual(
            spy.call_args_list,
            [
                mock.call(new, "not_as_assistant", reset=True),
                mock.call(new, "chosen_as_assistant"),
                mock.call(new, "chosen_as_assistant", reset=True),
                mock.call(old, "not_as_assistant"),
            ],
        )

    def test_same_assistant_is_dismissed(self) -> None:
        """验证选中当前助理时将其卸任使玩家无助理，清零旧服务表、更新标记并输出卸任提示。"""
        old = self.ids[0]
        self.appoint(old, {2: 1, 7: 1})
        assistant_service.assistant_replace(old)
        self.assertEqual(relations.assistant_character_id(0), 0)
        self.assertEqual(flags.get(old, "is_follow"), 0)
        self.assertEqual(relations.assistant_services(old), self.services())
        self.assertEqual(activity.second_behavior(old, "not_as_assistant"), 1)
        self.assertEqual(
            activity.second_behavior(old, "chosen_as_assistant"), 0
        )
        self.assertEqual(
            self.drawn, [self.line(), self.wait(dismissed_text(self.name(old)))]
        )

    def test_abnormal_target_is_rejected_without_dismissal(self) -> None:
        """验证目标处于 2/7 异常时保留原助理编号，清零旧助理但不设卸任标记，仅输出状态异常提示。"""
        old, new = self.ids[:2]
        self.appoint(old, {2: 1})
        flags.set(new, imprisonment=True)
        assistant_service.assistant_replace(new)
        self.assertEqual(relations.assistant_character_id(0), old)
        self.assertEqual(flags.get(old, "is_follow"), 0)
        self.assertEqual(relations.assistant_services(old), self.services())
        self.assertEqual(activity.second_behavior(old, "not_as_assistant"), 0)
        self.assertEqual(flags.get(new, "is_follow"), 0)
        self.assertEqual(
            self.drawn, [self.line(), self.wait(rejected_text(self.name(new)))]
        )

    def test_old_assistant_moves_back_from_player_room(self) -> None:
        """验证住在中枢/博士房间的旧助理卸任后迁回有空床的登记宿舍，并清空其登记宿舍字段。"""
        old, new = self.ids[:2]
        home = self.rooms[-1]
        self.appoint(old, {2: 1, 7: 1})
        chara_life.dormitory.set(old, PLAYER_ROOM)
        chara_life.permanent_dormitory.set(old, home)
        assistant_service.assistant_replace(new)
        self.assertEqual(chara_life.dormitory(old), home)
        self.assertEqual(chara_life.permanent_dormitory(old), "")


class DividerTest(AssistantCase):
    """分隔线回调测试。"""

    def test_divider_draws_line_at_text_width(self) -> None:
        """验证 emit_divider 经 Tk 回调按配置文本宽度绘制一条 LineDraw 分隔线。"""
        ui_hooks.emit_divider("=")
        self.assertEqual(self.drawn, [("LineDraw", self.width, "=")])

    def test_zero_width_divider_is_refused(self) -> None:
        """验证传入零宽空格调用 emit_divider 抛出 ValueError 且不产生绘制。"""
        with self.assertRaises(ValueError):
            ui_hooks.emit_divider("\u200b")
        self.assertEqual(self.drawn, [])


class AssistantServiceBoundaryTest(FastTestCase):
    """助理服务导入与模块属性边界测试。"""

    def test_service_imports_no_ui(self) -> None:
        """验证助理服务源码经 banned_imports 检查不含界面与输入输出导入。"""
        source = (ROOT / SERVICE).read_text(encoding="utf-8")
        self.assertEqual(banned_imports(source, SERVICE), [])

    def test_service_import_loads_no_panel(self) -> None:
        """验证在禁止加载 Script.UI.Panel 的子进程中可以正常导入助理服务。"""
        run = subprocess.run(
            [sys.executable, "-c", BLOCKED_IMPORT],
            check=False,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(run.returncode, 0, run.stderr[-2000:])

    def test_settle_imports_no_panel(self) -> None:
        """验证跨日结算各作用域展开相对导入后，模块名与导入成员均不指向 Script.UI.Panel。"""
        tree = ast.parse((ROOT / SETTLE).read_text(encoding="utf-8"))
        found: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = resolve_name(
                    "." * node.level + (node.module or ""), "Script.Settle"
                )
                found += [base, *(f"{base}.{a.name}" for a in node.names)]
        self.assertEqual(
            [n for n in found if n == PANEL or n.startswith(PANEL + ".")], []
        )

    def test_panel_keeps_no_service_functions(self) -> None:
        """验证助理面板模块不含三项助理服务函数与 SeeNPCButtonList 属性。"""
        for name in (
            "get_assistant_candidates",
            "select_random_assistant",
            "assistant_replace",
            "SeeNPCButtonList",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(assistant_panel, name))
