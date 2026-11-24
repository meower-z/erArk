"""
助理任命服务测试
================
- 候选角色筛选（get_assistant_candidates）：验证跳过玩家、异常状态角色、监狱长与访客。
- 每周随机抽选（select_random_assistant）：验证抽选候选列表、发出抽选提示并调用任命函数。
- 助理更换分支（assistant_replace）：验证同人卸任、异常拒绝、换任清理与首次任命。
- Tk 回调绘制（tk_ui.callbacks）：保留启动登记回调，验证 LineDraw 与 WaitDraw 的顺序与参数。
- 模块边界：验证结算导入服务而非面板，面板模块级不暴露三函数、* 与 __getattr__，并自测辅助函数。
"""

import ast
import random
from pathlib import Path
from unittest import mock

from Script.Config import normal_config
from Script.Core import get_text
from Script.Design import game_time, map_handle
from Script.Kernel import core
from Script.Modules.domains import activity, chara_life, flags, relations
from Script.Modules.domains import visitor, work
from Script.Modules.gameplay_resolution import assistant_service, ui_hooks
from Script.Modules.gameplay_resolution import working
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.fast.test_ejaculation_services import imports_in
from tests.world import ROOT

_ = get_text._
""" 文本翻译函数 """
OLD = 1
""" 测试用原助理角色编号 """
NEW = 2
""" 测试用新助理角色编号 """
SETTLE_FILE = "Script/Settle/past_day_settle.py"
""" 每日结算模块的仓库相对路径 """
PANEL_FILE = "Script/UI/Panel/assistant_panel.py"
""" 助理面板文件的仓库相对路径 """
DOCTOR_ROOM = map_handle.get_map_system_path_str_for_list(["中枢", "博士房间"])
""" 中枢/博士房间的地图路径字符串 """
MOVED = (
    "get_assistant_candidates",
    "select_random_assistant",
    "assistant_replace",
)
""" 助理服务函数名元组 """
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
""" 推导式与生成器表达式的语法树节点类型元组 """


def appointed_text(name: str) -> str:
    """
    生成指定角色名的任命提示文本。
    Keyword arguments:
    name -- str，被任命为助理的角色名称
    Return arguments:
    str -- 经翻译格式化后的任命提示文本
    """
    return _("\n{0}成为助理干员了，并默认开启智能跟随模式\n").format(name)


def dismissed_text(name: str) -> str:
    """
    生成指定角色名的卸任提示文本。
    Keyword arguments:
    name -- str，卸任助理的角色名称
    Return arguments:
    str -- 经翻译格式化后的卸任提示文本
    """
    return _("\n\n{0}不再是助理干员了，已清零助理服务相关的设置\n\n").format(
        name
    )


def module_scope_names(source: str) -> set[str]:
    """
    解析源码语法树，收集模块作用域内绑定的全部名称。
    遍历收集函数、异步函数、类、导入名（含 *）、赋值目标及 match 模式捕获名（含 * 与 ** 捕获）。
    遍历不进入函数体、类体与 lambda，在模块级推导式中仅收集 := 赋值表达式目标。
    Keyword arguments:
    source -- str，待解析的 Python 模块源码文本
    Return arguments:
    set[str] -- 模块作用域内绑定的名称集合
    """
    names: set[str] = set()
    pending: list[tuple[ast.AST, bool]] = [(ast.parse(source), False)]
    while pending:
        node, in_comprehension = pending.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Lambda):
                continue
            if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                names.add(child.name)
                continue
            if isinstance(child, (ast.Import, ast.ImportFrom)):
                names.update(
                    alias.asname or alias.name.split(".")[0]
                    for alias in child.names
                )
                continue
            if isinstance(child, ast.NamedExpr):
                names.add(child.target.id)
            elif not in_comprehension:
                if isinstance(child, ast.Name):
                    if isinstance(child.ctx, ast.Store):
                        names.add(child.id)
                elif isinstance(child, (ast.MatchAs, ast.MatchStar)):
                    if child.name:
                        names.add(child.name)
                elif isinstance(child, ast.MatchMapping) and child.rest:
                    names.add(child.rest)
            nested = in_comprehension or isinstance(child, COMPREHENSIONS)
            pending.append((child, nested))
    return names


class AssistantCase(FastTestCase):
    """助理服务测试基类，准备测试角色、工作集缓冲区与界面回调记录器。"""

    def setUp(self) -> None:
        """创建博士、旧助理与新助理角色，开启工作集缓冲区并替换界面回调记录器。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(OLD, "旧助理")
        self.world.chara(NEW, "新助理")
        self.enterContext(working.based_on(core.state()))
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.dividers: list[str] = []
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.notice])
        )
        self.enterContext(
            mock.patch.object(ui_hooks, "_dividers", [self.divider])
        )

    def notice(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        记录测试期间收到的提示文本回调参数。
        Keyword arguments:
        text -- str，收到的提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名
        use_text_width -- bool，是否按配置的文本宽度排版
        Return arguments:
        None -- 无返回值
        """
        self.notices.append((text, wait, style, use_text_width))

    def divider(self, char: str) -> None:
        """
        记录测试期间收到的分隔线字符。
        Keyword arguments:
        char -- str，收到的分隔线字符
        Return arguments:
        None -- 无返回值
        """
        self.dividers.append(char)

    def appoint(self, cid: int) -> None:
        """
        将指定角色设为当前助理，开启跟随、2 号与 7 号助理服务，并将宿舍设为博士房间。
        Keyword arguments:
        cid -- int，要设为当前助理的角色编号
        Return arguments:
        None -- 无返回值
        """
        relations.assistant_character_id.set(0, cid)
        flags.set(cid, is_follow=1)
        relations.assistant_services.set_item(cid, 2, 1)
        relations.assistant_services.set_item(cid, 7, 1)
        chara_life.dormitory.set(cid, DOCTOR_ROOM)


class CandidatesTest(AssistantCase):
    """助理候选角色筛选测试。"""

    def test_skips_player_unnormal_warden_and_visitor(self) -> None:
        """验证候选筛选跳过玩家、监禁角色、逃跑角色、监狱长与访客，仅保留正常干员。"""
        for cid, name in ((3, "监禁"), (4, "逃跑"), (5, "监狱长"), (6, "访客")):
            self.world.chara(cid, name)
        flags.set(3, imprisonment=True)
        flags.set(4, escaping=True)
        work.set_warden(5)
        visitor.arrive(6, game_time.now())
        self.assertEqual(
            assistant_service.get_assistant_candidates(), [OLD, NEW]
        )


class SelectRandomTest(AssistantCase):
    """每周随机抽选助理测试。"""

    def test_draw_announces_and_appoints(self) -> None:
        """验证抽选向 random.choice 传入候选列表、发出抽选提示并调用 assistant_replace。"""
        with (
            mock.patch.object(
                random, "choice", side_effect=lambda ids: ids[-1]
            ) as choice,
            mock.patch.object(
                assistant_service, "assistant_replace"
            ) as replace,
        ):
            assistant_service.select_random_assistant()
        choice.assert_called_once_with([OLD, NEW])
        replace.assert_called_once_with(NEW)
        text = _("\n○本周抽签选中了{0}作为{1}的助理\n").format("新助理", "博士")
        self.assertEqual(self.notices, [(text, True, None, True)])


class ReplaceTest(AssistantCase):
    """助理更换与卸任分支测试。"""

    def test_same_assistant_is_dismissed(self) -> None:
        """验证选择当前助理会清零助理编号、跟随与服务，设置卸任标记并输出分隔线与卸任提示。"""
        self.appoint(OLD)
        assistant_service.assistant_replace(OLD)
        self.assertEqual(relations.assistant_character_id(0), 0)
        self.assertEqual(flags.get(OLD, "is_follow"), 0)
        self.assertEqual(set(relations.assistant_services(OLD).values()), {0})
        self.assertEqual(activity.second_behavior(OLD, "not_as_assistant"), 1)
        self.assertEqual(self.dividers, ["-"])
        self.assertEqual(
            self.notices, [(dismissed_text("旧助理"), True, None, True)]
        )

    def test_unnormal_candidate_is_refused(self) -> None:
        """验证目标处于监禁或逃跑状态时拒绝任命，不开启跟随与 2 号服务并输出分隔线与异常提示。"""
        for flag in ("imprisonment", "escaping"):
            with self.subTest(flag=flag):
                self.notices.clear()
                self.dividers.clear()
                self.appoint(OLD)
                flags.set(NEW, **{flag: True})
                assistant_service.assistant_replace(NEW)
                flags.set(NEW, **{flag: False})
                self.assertNotEqual(relations.assistant_character_id(0), NEW)
                self.assertEqual(flags.get(NEW, "is_follow"), 0)
                self.assertEqual(relations.assistant_services(NEW)[2], 0)
                text = _("\n{0}的状态异常，无法任命为助理干员\n").format(
                    "新助理"
                )
                self.assertEqual(self.dividers, ["-"])
                self.assertEqual(self.notices, [(text, True, None, True)])

    def test_new_assistant_replaces_old(self) -> None:
        """验证换任会设置新助理状态、清理旧助理状态与宿舍，并输出分隔线与合并后的任免提示。"""
        self.appoint(OLD)
        assistant_service.assistant_replace(NEW)
        self.assertEqual(relations.assistant_character_id(0), NEW)
        self.assertEqual(flags.get(NEW, "is_follow"), 1)
        self.assertEqual(relations.assistant_services(NEW)[2], 1)
        self.assertEqual(activity.second_behavior(NEW, "not_as_assistant"), 0)
        self.assertEqual(activity.second_behavior(OLD, "not_as_assistant"), 1)
        self.assertEqual(flags.get(OLD, "is_follow"), 0)
        self.assertNotEqual(chara_life.dormitory(OLD), DOCTOR_ROOM)
        self.assertEqual(set(relations.assistant_services(OLD).values()), {0})
        self.assertEqual(self.dividers, ["-"])
        self.assertEqual(
            self.notices,
            [
                (
                    appointed_text("新助理") + dismissed_text("旧助理"),
                    True,
                    None,
                    True,
                )
            ],
        )

    def test_first_assistant_is_appointed(self) -> None:
        """验证无旧助理时首次任命会写入助理编号、设置 chosen_as_assistant 标记并输出任命提示。"""
        assistant_service.assistant_replace(NEW)
        self.assertEqual(relations.assistant_character_id(0), NEW)
        self.assertEqual(
            activity.second_behavior(NEW, "chosen_as_assistant"), 1
        )
        self.assertEqual(
            self.notices, [(appointed_text("新助理"), True, None, True)]
        )


class TkAssistantDrawTest(FastTestCase):
    """Tk 界面回调绘制助理分隔线与提示的测试。"""

    def test_tk_draws_divider_then_waiting_notice(self) -> None:
        """验证保留启动登记的 Tk 回调时，assistant_replace 按文本宽度依次调用 LineDraw 与 WaitDraw。"""
        self.world.chara(0, "博士")
        self.world.chara(NEW, "新助理")
        self.enterContext(working.based_on(core.state()))
        drawn: list[tuple[str, str, float]] = []
        self.enterContext(
            mock.patch.object(
                draw.LineDraw,
                "draw",
                autospec=True,
                side_effect=lambda now: drawn.append(
                    ("LineDraw", now.text, now.width)
                ),
            )
        )
        self.enterContext(
            mock.patch.object(
                draw.WaitDraw,
                "draw",
                autospec=True,
                side_effect=lambda now: drawn.append(
                    ("WaitDraw", now.text, now.width)
                ),
            )
        )
        assistant_service.assistant_replace(NEW)
        width = normal_config.config_normal.text_width
        self.assertEqual(
            drawn,
            [
                ("LineDraw", "-", width),
                ("WaitDraw", appointed_text("新助理"), width),
            ],
        )


class AssistantBoundaryTest(FastTestCase):
    """助理服务与界面面板模块边界测试。"""

    def test_new_day_settle_imports_service_not_panel(self) -> None:
        """验证 past_day_settle.py 导入 assistant_service 且不导入任何 Script.UI.Panel 模块。"""
        source = (Path(ROOT) / SETTLE_FILE).read_text(encoding="utf-8")
        imports = imports_in(source, "Script.Settle")
        self.assertIn(assistant_service.__name__, imports)
        self.assertEqual(
            sorted(
                name for name in imports if name.startswith("Script.UI.Panel")
            ),
            [],
        )

    def test_panel_module_exposes_no_moved_function(self) -> None:
        """验证 assistant_panel.py 模块作用域不暴露 MOVED 中的三个函数名、* 与 __getattr__。"""
        source = (Path(ROOT) / PANEL_FILE).read_text(encoding="utf-8")
        exposed = module_scope_names(source) & {*MOVED, "*", "__getattr__"}
        self.assertEqual(exposed, set())


class ModuleScopeNamesTest(FastTestCase):
    """module_scope_names 辅助函数自测。"""

    def test_reports_module_scope_bindings_only(self) -> None:
        """验证 module_scope_names 报告 match 捕获与推导式 := 绑定，且跳过局部作用域与循环变量。"""
        cases = {
            "match v:\n    case {'k': assistant_replace}:\n        pass\n": {
                "assistant_replace"
            },
            "match v:\n    case [1] as assistant_replace:\n        pass\n": {
                "assistant_replace"
            },
            "match v:\n    case [*select_random_assistant]:\n        pass\n": {
                "select_random_assistant"
            },
            "match v:\n    case {**get_assistant_candidates}:\n        pass\n": {
                "get_assistant_candidates"
            },
            "x = [(assistant_replace := n) for n in range(2)]\n": {
                "assistant_replace"
            },
            "x = [assistant_replace for assistant_replace in range(2)]\n": set(),
            "def f():\n    assistant_replace = 1\n": set(),
            "class C:\n    assistant_replace = 1\n": set(),
            "f = lambda assistant_replace: assistant_replace\n": set(),
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(
                    module_scope_names(source) & set(MOVED), expected
                )
