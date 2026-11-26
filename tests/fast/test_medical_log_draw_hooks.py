"""
医疗经营日志经 ui_hooks 发出的测试
==================================
- 日志提示（MedicalReportNoticeTest）：验证 log_system.render_medical_reports
  的文本返回、ui_hooks.emit_notice 提示派发参数与 Tk 回调绘制结果，
  并覆盖每日结算与财务报表面板的日志输出。
- 导入边界（MedicalImportBoundaryTest）：用后端界面边界守卫检查直接位于
  Script/System/Medical_System 目录的每个 .py 文件，断言其中无违规界面导入。
"""

from typing import Any
from unittest import mock

from Script.Config import normal_config
from Script.Kernel import core
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.System.Medical_System import log_system, medical_service
from Script.UI.Moudle import draw
from Script.UI.Panel import medical_department_panel
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports

MEDICAL_DIR = "Script/System/Medical_System"
"""医疗系统包目录的仓库相对路径。"""
EMPTY = "\n暂无医疗经营日志记录。\n"
"""日志列表为空且未传入自定义提示时返回的默认空日志提示。"""
FIRST: dict[str, Any] = {
    "title": "○甲",
    "time_str": "1日",
    "price_ratio": 1.5,
    "income": 120,
}
"""测试用第一条日志条目，包含标题、记录时间、收费系数与收入字段。"""
SECOND: dict[str, Any] = {
    "title": "○乙",
    "time_str": "2日",
    "income": 30,
    "text": "备注",
}
"""测试用第二条日志条目，包含标题、记录时间、收入与附加文本字段。"""
BODY = (
    " - 诊疗完成：0 人（门诊 0 / 住院 0）\n"
    " - 用药完成：0 人（门诊 0 / 住院 0）\n"
    " - 药品消耗：今日总消耗 0.00 单位\n"
    " - 今日入院：0 人 / 出院：0 人\n"
    " - 队列概况：待诊 0 人 / 待发药 0 人 / 已拿药 0 人 / 住院 0 人 / 待手术 0 人"
)
"""各项统计、药品消耗与队列计数均为零时，日志条目在收入行之后的固定正文。"""

type Notice = tuple[str, bool, str | None, bool]
"""一条提示的参数元组类型，依次为 text、wait、style 与 use_text_width。"""


class MedicalReportNoticeTest(FastTestCase):
    """医疗经营日志的文本渲染、ui_hooks 派发参数与 Tk 回调绘制测试。"""

    def setUp(self) -> None:
        """
        打开内核工作集并初始化提示与绘制记录列表。
        在已登记的提示回调旁追加 record 回调，并拦截 NormalDraw 与 WaitDraw 的 draw 方法。
        """
        super().setUp()
        self.enterContext(working.based_on(core.state()))
        self.notices: list[Notice] = []
        self.enterContext(
            mock.patch.object(
                ui_hooks, "_notices", [*ui_hooks._notices, self.record]
            )
        )
        self.drawn: list[tuple[str, float, str, str]] = []
        for cls in (draw.NormalDraw, draw.WaitDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.keep
                )
            )

    def record(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        记录一条经 ui_hooks.emit_notice 派发的提示参数。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名，为 None 时使用默认样式
        use_text_width -- bool，是否按配置文本宽度排版
        Return arguments:
        None -- 无返回值
        """
        self.notices.append((text, wait, style, use_text_width))

    def keep(self, now: draw.NormalDraw) -> None:
        """
        记录被拦截绘制对象的类名、宽度、样式与文本。
        Keyword arguments:
        now -- draw.NormalDraw，调用 draw 方法的绘制对象实例
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append((type(now).__name__, now.width, now.style, now.text))

    def render(self, reports: list[dict[str, Any]], **kwargs: Any) -> str:
        """
        清空记录后按配置文本宽度调用 log_system.render_medical_reports 并返回其文本。
        Keyword arguments:
        reports -- list[dict[str, Any]]，日志条目列表
        kwargs -- Any，透传给 render_medical_reports 的关键字参数
        Return arguments:
        str -- render_medical_reports 返回的日志文本
        """
        self.notices.clear()
        self.drawn.clear()
        return log_system.render_medical_reports(
            reports, width=normal_config.config_normal.text_width, **kwargs
        )

    def assert_waited(self, text: str) -> None:
        """
        断言 ui_hooks 仅记录一条按配置文本宽度排版且 style 为 None 的等待型提示。
        同时断言 Tk 回调仅按配置文本宽度绘出一个默认样式且文本相同的 WaitDraw。
        Keyword arguments:
        text -- str，预期的提示文本
        Return arguments:
        None -- 无返回值
        """
        self.assertEqual(self.notices, [(text, True, None, True)])
        self.assertEqual(
            self.drawn,
            [
                (
                    "WaitDraw",
                    normal_config.config_normal.text_width,
                    draw.NormalDraw.style,
                    text,
                )
            ],
        )

    def test_empty_reports(self) -> None:
        """
        空日志列表下，render_medical_reports 返回默认空日志提示或以换行结尾的 empty_message。
        该函数在 draw_flag 为 False 时不发提示也不绘制，在 draw_flag 为 True 时发出一条等待型提示。
        """
        for message, text in (
            (None, EMPTY),
            ("无记录", "无记录\n"),
            ("无记录\n", "无记录\n"),
        ):
            with self.subTest(message=message):
                self.assertEqual(
                    self.render([], draw_flag=False, empty_message=message),
                    text,
                )
                self.assertEqual((self.notices, self.drawn), ([], []))
                self.assertEqual(
                    self.render([], draw_flag=True, empty_message=message),
                    text,
                )
                self.assert_waited(text)

    def test_report_text(self) -> None:
        """
        render_medical_reports 在 day_past_flag 为 False 时输出记录时间行与收费系数行，为 True 时省略两行。
        该函数用分隔线拼接多条日志并在条目末尾附带附加文本，且 draw_flag 为 False 时不发提示也不绘制。
        """
        head = (
            "\n○甲\n - 记录时间：1日\n - 收费系数：150%\n - 收入：120 龙门币\n"
        )
        self.assertEqual(
            self.render([FIRST], draw_flag=False), head + BODY + "\n"
        )
        self.assertEqual(
            self.render([FIRST], draw_flag=False, day_past_flag=True),
            "\n○甲\n - 收入：120 龙门币\n" + BODY + "\n",
        )
        self.assertEqual(
            self.render([FIRST, SECOND], draw_flag=False),
            head
            + BODY
            + "\n--------------------\n"
            + "○乙\n - 记录时间：2日\n - 收费系数：100%\n - 收入：30 龙门币\n"
            + BODY
            + "\n备注\n",
        )
        self.assertEqual((self.notices, self.drawn), ([], []))

    def test_draw_flag_emits_wait_notice(self) -> None:
        """draw_flag 为 True 时，render_medical_reports 发出一条与返回文本相同的等待型提示。"""
        text = self.render([FIRST], draw_flag=True, day_past_flag=True)
        self.assert_waited(text)

    def test_settlement_emits_report(self) -> None:
        """打桩成就结算后，settle_medical_department 在 draw_flag 为 True 时发出等待型结算提示。
        其返回文本以结算标题行和收入行开头，且与派发及绘制文本一致。
        """
        self.enterContext(
            mock.patch.object(achievement_service, "settle_and_notify")
        )
        with kernel_data.writing():
            medical_service.init_medical_department_data()
            self.notices.clear()
            self.drawn.clear()
            result = medical_service.settle_medical_department(draw_flag=True)
        self.assertTrue(result["text"].startswith("\n○医疗部结算\n - 收入："))
        self.assert_waited(result["text"])

    def test_finance_panel_uses_own_width(self) -> None:
        """
        财务报表面板查看最近日志时不经 ui_hooks 发出提示，而是按面板自身宽度绘制 WaitDraw。
        该面板在无日志时绘出默认空日志提示，在写入两条日志后按最新在前顺序绘出日志文本。
        """
        width = normal_config.config_normal.text_width + 7
        panel = medical_department_panel.FinanceReportSubPanel(width)
        panel._show_recent_reports()
        self.assertEqual(self.notices, [])
        self.assertEqual(
            self.drawn, [("WaitDraw", width, draw.NormalDraw.style, EMPTY)]
        )
        self.drawn.clear()
        with kernel_data.writing():
            log_system.append_medical_report(dict(FIRST))
            log_system.append_medical_report(dict(SECOND))
        reports = medical_service.get_recent_medical_reports(limit=3)
        text = self.render(reports, draw_flag=False)
        self.assertTrue(text.startswith("\n○乙\n"))
        panel._show_recent_reports()
        self.assertEqual(self.notices, [])
        self.assertEqual(
            self.drawn, [("WaitDraw", width, draw.NormalDraw.style, text)]
        )


class MedicalImportBoundaryTest(FastTestCase):
    """Script/System/Medical_System 顶层 .py 文件的界面导入边界测试。"""

    def test_non_panel_modules_import_no_ui(self) -> None:
        """用 banned_imports 检查直接位于医疗系统包目录的每个 .py 文件（含 __init__.py），断言无违规导入。"""
        checked = [
            path.relative_to(ROOT).as_posix()
            for path in sorted((ROOT / MEDICAL_DIR).glob("*.py"))
        ]
        self.assertIn(f"{MEDICAL_DIR}/log_system.py", checked)
        self.assertEqual(
            [
                (path, banned_imports((ROOT / path).read_bytes(), path))
                for path in checked
            ],
            [(path, []) for path in checked],
        )

    def test_checker_catches_relative_and_later_aliases(self) -> None:
        """验证在医疗系统包路径下，banned_imports 检出相对导入与多别名中的违规模块并放行包内相对导入。"""
        source = "\n".join(
            (
                "from ...UI.Moudle import draw",
                "from Script import Core, UI",
                "from Script import Frontend, UI",
                "from . import medical_core",
            )
        )
        self.assertEqual(
            banned_imports(source, f"{MEDICAL_DIR}/sample.py"),
            [
                (1, "Script.UI.Moudle.draw"),
                (2, "Script.UI"),
                (3, "Script.Frontend"),
            ],
        )
