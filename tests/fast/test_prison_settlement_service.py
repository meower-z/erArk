"""
囚犯每日结算与逃脱结果服务测试
==============================
- 逃脱结果处理（escape_success、escape_fail）：覆盖状态标志、移出名册、离线、追捕委托、概率清零与提示参数。
- 每日结算入口（settle_prisoners）：覆盖无监狱长逃脱、有监狱长失败与零概率跳过分支。
- Tk 提示回调（tk_ui.callbacks）：保留启动登记回调，验证 WaitDraw 与 NormalDraw 的样式、宽度与文本。
- 模块边界：验证 basement.py 导入 prison_service 而非面板，且面板文件不绑定三个结算函数。
"""

import ast
from pathlib import Path
from unittest import mock

from Script.Config import normal_config
from Script.Core import get_text
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import activity, flags, prison, roster, work
from Script.Modules.gameplay_resolution import prison_service, ui_hooks
from Script.Modules.gameplay_resolution import working
from Script.System.Field_Commission_System import field_commission_function
from Script.UI.Moudle import draw
from tests import chara_abilities as ca
from tests.fast.base import FastTestCase
from tests.fast.test_ejaculation_services import imports_in

_ = get_text._
""" 文本翻译函数 """
ROOT = Path(__file__).resolve().parents[2]
""" 仓库根目录路径 """
PRISONER = 1
""" 测试用主囚犯角色编号 """
OTHER = 2
""" 测试用第二名囚犯角色编号 """
WARDEN = 3
""" 测试用监狱长角色编号 """
PANEL = "Script.UI.Panel.confinement_and_training"
""" 监禁调教管理面板模块全名 """
BASEMENT = "Script/Design/basement.py"
""" 基地每日结算模块的仓库相对路径 """
PANEL_FILE = "Script/UI/Panel/confinement_and_training.py"
""" 监禁调教管理面板文件的仓库相对路径 """
MOVED = ("settle_prisoners", "escape_success", "escape_fail")
""" 囚犯结算与逃脱结果处理函数名元组 """


def success_text(name: str) -> str:
    """
    生成指定角色名的逃脱成功提示文本。
    Keyword arguments:
    name -- str，逃脱囚犯的角色名称
    Return arguments:
    str -- 经翻译格式化后的逃脱成功提示文本
    """
    return _("\n囚犯{0}逃脱成功，请尽快派遣外勤干员进行追捕！\n").format(name)


def fail_text(name: str) -> str:
    """
    生成指定角色名的逃脱失败提示文本。
    Keyword arguments:
    name -- str，逃脱失败囚犯的角色名称
    Return arguments:
    str -- 经翻译格式化后的逃脱失败提示文本
    """
    return _("囚犯{0}逃脱失败，监狱长已经加强了对其的监视！\n").format(name)


def file_imports(path: str) -> set[str]:
    """
    读取仓库相对路径对应文件并解析其导入的完整模块名集合。
    Keyword arguments:
    path -- str，相对仓库根目录的源码文件路径
    Return arguments:
    set[str] -- 该文件导入的完整模块名集合
    """
    package = ".".join(Path(path).parent.parts)
    return imports_in((ROOT / path).read_text(encoding="utf-8"), package)


def bound_names(path: str) -> set[str]:
    """
    解析文件语法树，收集各作用域的函数、类、导入别名与赋值绑定名。
    Keyword arguments:
    path -- str，相对仓库根目录的源码文件路径
    Return arguments:
    set[str] -- 文件中各作用域绑定的名称集合
    """
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            bound.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update(
                alias.asname or alias.name.split(".")[0] for alias in node.names
            )
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
    return bound


class PrisonCase(FastTestCase):
    """囚犯结算测试基类，准备测试角色、工作集缓冲区、监禁设置与临时委托桩。"""

    def setUp(self) -> None:
        """创建博士、两名囚犯与监狱长角色，开启工作集缓冲区，重置监禁设置并打桩临时委托写入。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(PRISONER, "囚犯甲")
        self.world.chara(OTHER, "囚犯乙")
        self.world.chara(WARDEN, "监狱长")
        self.enterContext(working.based_on(core.state()))
        prison.reset_settings()
        self.commission = self.enterContext(
            mock.patch.object(
                field_commission_function, "create_temp_commission"
            )
        )

    def lock_up(self, cid: int, escape: int) -> None:
        """
        将指定角色登记为囚犯并设置初始逃脱概率与囚禁标志。
        Keyword arguments:
        cid -- int，角色编号
        escape -- int，初始逃脱概率
        Return arguments:
        None -- 无返回值
        """
        prison.imprison(cid, game_time.now(), escape)
        flags.set(cid, imprisonment=True)


class NoticeCase(PrisonCase):
    """捕获 ui_hooks 提示回调的测试基类，提供逃脱状态与追捕委托断言。"""

    def setUp(self) -> None:
        """初始化提示记录列表并将 ui_hooks._notices 替换为内存记录回调。"""
        super().setUp()
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.notice])
        )

    def notice(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        记录一次提示回调的文本与显示选项。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待确认
        style -- str | None，文本样式名
        use_text_width -- bool，是否按配置文本宽度排版
        Return arguments:
        None -- 无返回值
        """
        self.notices.append((text, wait, style, use_text_width))

    def assert_escaped(self, cid: int, combat: int) -> None:
        """
        断言指定囚犯逃脱后的状态标志、离线位置与追捕临时委托参数。
        Keyword arguments:
        cid -- int，逃脱囚犯的角色编号
        combat -- int，囚犯能力 42 数值，用于核对委托需求
        Return arguments:
        None -- 无返回值
        """
        self.assertTrue(flags.get(cid, "escaping"))
        self.assertTrue(flags.get(cid, "imprisonment"))
        self.assertFalse(prison.is_prisoner(cid))
        self.assertFalse(roster.has(cid))
        self.assertEqual(activity.position(cid), ["0", "0"])
        self.commission.assert_called_once()
        kwargs = self.commission.call_args.kwargs
        self.assertEqual(kwargs["reward"], f"追捕_{cid}_1")
        self.assertEqual(kwargs["demand"], f"a_42_{combat * 4}")


class EscapeSuccessTest(NoticeCase):
    """直接调用 prison_service.escape_success 的测试用例。"""

    def test_escape_takes_prisoner_offline_and_opens_hunt(self) -> None:
        """验证逃脱成功会使囚犯离线、保留囚禁标志、生成追捕委托并发出等待确认警告提示。"""
        self.lock_up(PRISONER, 40)
        ca.ability(PRISONER)[42] = 3
        self.assertTrue(roster.has(PRISONER), "前提：囚犯在当前干员列表中")
        prison_service.escape_success(PRISONER)
        self.assert_escaped(PRISONER, 3)
        self.assertEqual(
            self.notices, [(success_text("囚犯甲"), True, "warning", True)]
        )


class EscapeFailTest(NoticeCase):
    """直接调用 prison_service.escape_fail 的测试用例。"""

    def test_failed_escape_resets_probability(self) -> None:
        """验证逃脱失败会将逃脱概率清零、保留囚犯身份并发出非等待金色提示。"""
        self.lock_up(PRISONER, 25)
        prison_service.escape_fail(PRISONER)
        self.assertEqual(prison.escape_probability(PRISONER), 0)
        self.assertTrue(prison.is_prisoner(PRISONER))
        self.assertFalse(flags.get(PRISONER, "escaping"))
        self.assertEqual(
            self.notices, [(fail_text("囚犯甲"), False, "gold_enrod", True)]
        )


class SettlePrisonersTest(NoticeCase):
    """调用 prison_service.settle_prisoners 的各分支测试用例。"""

    def test_unguarded_prisoner_over_threshold_escapes(self) -> None:
        """验证无监狱长且逃脱概率超过阈值时，每日结算触发逃脱成功流程。"""
        self.lock_up(PRISONER, 30)
        ca.ability(PRISONER)[42] = 2
        prison_service.settle_prisoners()
        self.assert_escaped(PRISONER, 2)
        self.assertEqual(
            self.notices, [(success_text("囚犯甲"), True, "warning", True)]
        )

    def test_guarded_prisoner_below_threshold_fails(self) -> None:
        """验证有监狱长且逃脱概率低于阈值时，每日结算触发逃脱失败流程且不生成追捕委托。"""
        work.set_warden(WARDEN)
        self.lock_up(PRISONER, 10)
        prison_service.settle_prisoners()
        self.assertEqual(prison.escape_probability(PRISONER), 0)
        self.assertTrue(prison.is_prisoner(PRISONER))
        self.commission.assert_not_called()
        self.assertEqual(
            self.notices, [(fail_text("囚犯甲"), False, "gold_enrod", True)]
        )

    def test_zero_probability_leaves_prisoner_alone(self) -> None:
        """验证计算出的逃脱概率为 0 时，每日结算不触发逃脱提示也不改变囚犯状态。"""
        self.lock_up(PRISONER, 0)
        with mock.patch.object(
            prison_service, "calculate_escape_probability", return_value=0
        ) as calculate:
            prison_service.settle_prisoners()
        calculate.assert_called_once_with(PRISONER)
        self.assertEqual(prison.escape_probability(PRISONER), 0)
        self.assertTrue(prison.is_prisoner(PRISONER))
        self.commission.assert_not_called()
        self.assertEqual(self.notices, [])


class TkPrisonNoticeTest(PrisonCase):
    """验证启动阶段登记的 Tk 提示回调正确绘制囚犯逃脱成功与失败提示。"""

    def test_tk_draws_success_and_fail_notices(self) -> None:
        """
        保留启动阶段登记的提示回调并打桩 WaitDraw.draw 与 NormalDraw.draw，
        验证两类逃脱提示的绘制类、宽度、样式与文本。
        """
        waited = self.enterContext(
            mock.patch.object(draw.WaitDraw, "draw", autospec=True)
        )
        drawn = self.enterContext(
            mock.patch.object(draw.NormalDraw, "draw", autospec=True)
        )
        self.lock_up(PRISONER, 31)
        self.lock_up(OTHER, 0)
        prison_service.settle_prisoners()
        width = normal_config.config_normal.text_width
        self.assertEqual(
            [
                (type(now).__name__, now.width, now.style, now.text)
                for (now,), _kw in waited.call_args_list
            ],
            [("WaitDraw", width, "warning", success_text("囚犯甲"))],
        )
        self.assertEqual(
            [
                (type(now).__name__, now.width, now.style, now.text)
                for (now,), _kw in drawn.call_args_list
            ],
            [("NormalDraw", width, "gold_enrod", fail_text("囚犯乙"))],
        )


class PrisonBoundaryTest(FastTestCase):
    """验证基地每日结算与监禁调教管理面板之间的模块边界约束。"""

    def test_basement_imports_service_not_panel(self) -> None:
        """验证 Script/Design/basement.py 导入 prison_service 且不导入监禁调教管理面板。"""
        imports = file_imports(BASEMENT)
        self.assertIn(prison_service.__name__, imports)
        self.assertNotIn(PANEL, imports)

    def test_panel_binds_no_settlement_function(self) -> None:
        """验证监禁调教管理面板各作用域均不绑定 settle_prisoners、escape_success 与 escape_fail。"""
        self.assertEqual(bound_names(PANEL_FILE) & set(MOVED), set())
