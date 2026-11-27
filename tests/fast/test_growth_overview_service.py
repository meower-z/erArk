"""
养成总览服务测试
================
验证养成总览服务的阶段、胎教、科目、出勤、成绩单、性格、履历与待处理文本。
验证面板翻页与网格绘制行为，并在独立无界面子进程中确认不加载界面与结算模块。
"""

import datetime
from typing import Any
from unittest import mock

from Script.Config import game_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, growth, official, pregnancy
from Script.Modules.domains import relations
from Script.Modules.gameplay_resolution import growth_overview_service as svc
from Script.Modules.gameplay_resolution import working
from Script.Modules.tk_ui import student_select
from Script.System.Education_System import education_constant as ec
from Script.UI.Panel import growth_panel
from Script.System.Pregnancy_System import pregnancy_constant
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

CHILD = 10
""" 主测试女儿角色编号常量。 """
MOTHER = 1
""" 测试母亲角色编号常量。 """
OTHER = 11
""" 用于切换学生的次女角色编号常量。 """
EVENTS = {
    "g1": {"text": "一" * 30 + "\n第二行", "option_1": "选一"},
    "g2": {"text": "二号事件\n第二行", "option_0": "选零"},
    **{f"n{n}": {"text": f"事件{n}"} for n in range(10)},
}
""" 供养成履历测试注入的模拟公务事件配置表。 """
UI_FREE_RUN = """
import datetime
from Script.Config import game_config
from Script.Design import attr_calculation, game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, growth, identity, official, pregnancy, relations, roster
from Script.Modules.gameplay_resolution import growth_overview_service as svc
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import kernel_state
from Script.System.Education_System import education_constant as ec
core.reset_state(core.GameState(kernel_state.first_clock(), {}, {}))
texts, uids, subject = [], sorted(game_config.config_official_event), ec.SUBJECT_ABILITY_LIST[0]
with working.based_on(core.state()):
    for cid in (0, 1, 10, 11, 12, 13):
        identity.put(identity.Identity(cid, name=f"c{cid}", sex=1))
        abilities.ability(cid).replace(attr_calculation.get_ability_zero({}))
        abilities.talent(cid).replace(attr_calculation.get_talent_zero({}))
    for cid, stage in ((10, 103), (11, 104), (12, 103), (13, 0)):
        if stage:
            abilities.talent(cid)[stage] = 1
            roster.add(cid)
        relations.father_id.set(cid, 0)
        relations.mother_id.set(cid, 1 if cid != 12 else 99)
        pregnancy.update(cid, born_time=game_time.now() - datetime.timedelta(days=100))
    abilities.talent(12)[ec.GROWTH_STOP_TALENT_ID] = 1
    abilities.ability(10)[subject] = 3
    with growth.editing(10) as g:
        g.attend_class_count, g.absent_count, g.prenatal_point = 29, 21, 7.5
        g.personality_point = {0: 2.0, 1: -3.0}
        g.event_history = {"missing": {"choice": 1, "time": game_time.now()}}
        for n, uid in enumerate(uids[:10]):
            g.event_history[uid] = {"time": game_time.now() - datetime.timedelta(days=n), "choice": n % 3}
        g.report_card_history = [{"year": 2020, "month": 9, "reason": "r"}, {"level_change": {subject: [0, 1]}}]
        g.report_card_flag, g.show_off_ability, g.skip_class_flag = True, {subject: 1}, True
        g.skip_class_day = game_time.now().toordinal()
    with growth.editing(11) as g:
        g.report_card_flag, g.report_card_history = True, [{"year": 2020, "month": 9}]
    official.set_queue([{"uid": u, "chara_id": 10, "partner_id": 0} for u in ("missing", uids[0])])
    for cid in (10, 11, 12, 13):
        texts += [svc.stage_text(cid), svc.prenatal_text(cid), *svc.pending_texts(cid)]
        texts += [text for text, _ in svc.subject_cells(cid) + (svc.personality_cells(cid) or [])]
        texts += list(svc.attendance_texts(cid) or ())
        omit, rows = svc.event_history(cid) or ("", [])
        texts += [omit, *rows]
        for page in filter(None, (svc.report_card_page(cid, index) for index in (-1, 0, 5))):
            texts += [page.summary, page.reason, page.progress, svc.report_card_index_text(page)]
payload["texts"] = len([text for text in texts if text])
"""
""" 在拦截界面与结算导入的子进程中调用服务各公开函数的脚本。 """


class GrowthCase(FastTestCase):
    """养成总览测试基类，负责初始化角色、工作区与默认测试女儿。"""

    def setUp(self) -> None:
        """创建测试角色与工作区上下文并初始化默认女儿状态。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(MOTHER, "母亲")
        self.world.chara(CHILD, "女儿")
        self.world.chara(OTHER, "次女")
        self.enterContext(working.based_on(core.state()))
        self.child(CHILD, 103)

    def child(self, cid: int, stage: int, born_days: int = 100) -> None:
        """配置指定角色的成长阶段素质、父母关系与出生时间。"""
        if stage:
            abilities.talent(cid)[stage] = 1
        relations.father_id.set(cid, 0)
        relations.mother_id.set(cid, MOTHER)
        born = game_time.now() - datetime.timedelta(days=born_days)
        pregnancy.update(cid, born_time=born)

    def grow(self, **fields: object) -> None:
        """在养成数据编辑块内批量更新主测试女儿的指定字段。"""
        with growth.editing(CHILD) as data:
            assert data is not None
            for key, value in fields.items():
                setattr(data, key, value)


class StageTest(GrowthCase):
    """阶段进度文本与胎教底子文本测试集。"""

    def test_next_stage_and_predicted_date(self) -> None:
        """验证常规阶段文本输出母亲、阶段名、剩余时长与预计日期。"""
        predict = game_time.get_predict_date(50, game_time.now())
        self.assertEqual(
            svc.stage_text(CHILD),
            "\n  母亲：母亲｜当前阶段：学员｜距成长为少女还有 1季月20天，预计在 "
            f"{predict.year}年{pregnancy_constant.format_season_date(predict)}\n",
        )

    def test_other_stage_lines(self) -> None:
        """验证零剩余天数、未知母亲、成长停滞与已毕业分支的阶段文本。"""
        self.child(CHILD, 103, born_days=400)
        now = game_time.now()
        date = f"{now.year}年{pregnancy_constant.format_season_date(now)}"
        self.assertTrue(
            svc.stage_text(CHILD).endswith(f"还有 0天，预计在 {date}\n")
        )
        abilities.talent(CHILD)[ec.GROWTH_STOP_TALENT_ID] = 1
        relations.mother_id.set(CHILD, 999)
        self.assertEqual(
            svc.stage_text(CHILD),
            "\n  母亲：未知｜当前阶段：学员｜成长停滞中，阶段不会推进"
            "（解除后距成长为少女还需 0天）\n",
        )
        abilities.talent(CHILD)[103] = 0
        self.assertEqual(
            svc.stage_text(CHILD),
            "\n  母亲：未知｜当前阶段：已成年（已毕业，没有下一阶段）\n",
        )

    def test_prenatal_line(self) -> None:
        """验证无胎教习得珠时返回空字符串，有胎教点时输出胎教底子说明行。"""
        self.assertEqual(svc.prenatal_text(CHILD), "")
        self.grow(prenatal_point=7.5)
        text = svc.prenatal_text(CHILD)
        self.assertTrue(
            text.startswith("  胎教底子：孕期听过15次胎教，出生时带来 ")
        )
        self.assertTrue(text.endswith("\n"))


class SubjectAndAttendanceTest(GrowthCase):
    """科目水平单元格与出勤统计文本测试集。"""

    def test_subject_cells(self) -> None:
        """验证升级高亮、普通非零等级与零级灰显三种科目单元样式与文本。"""
        first, second, third = ec.SUBJECT_ABILITY_LIST[:3]
        abilities.ability(CHILD)[first] = 3
        abilities.ability(CHILD)[second] = 2
        self.grow(semester_base_ability={first: 1, second: 2})
        cells = svc.subject_cells(CHILD)
        self.assertEqual(len(cells), len(ec.SUBJECT_ABILITY_LIST))
        name = game_config.config_ability[first].name
        self.assertEqual(cells[0][1], svc.HIGHLIGHT)
        self.assertTrue(cells[0][0].startswith(f" {name}："))
        self.assertTrue(cells[0][0].endswith("（本学期+2）"))
        self.assertEqual(cells[1][1], "")
        self.assertNotIn("本学期", cells[1][0])
        self.assertEqual(cells[2][1], svc.GRAY)
        self.assertTrue(
            cells[2][0].startswith(f" {game_config.config_ability[third].name}")
        )

    def test_attendance(self) -> None:
        """验证无养成数据返回空，零课与混合出勤时累计及本学期文本正确。"""
        self.assertIsNone(svc.attendance_texts(CHILD))
        self.grow(attend_class_count=0, absent_count=0)
        self.assertEqual(
            svc.attendance_texts(CHILD),
            (
                "  累计：听课 0 节，缺课 0 节（出勤率 100%）\n",
                "  本学期：听课 0 节，缺课 0 节（出勤率 100%）\n",
            ),
        )
        self.grow(
            attend_class_count=29,
            absent_count=21,
            semester_base_attend=0,
            semester_base_absent=0,
        )
        self.assertEqual(
            svc.attendance_texts(CHILD),
            (
                "  累计：听课 29 节，缺课 21 节（出勤率 57%）\n",
                "  本学期：听课 29 节，缺课 21 节（出勤率 58%）\n",
            ),
        )


class ReportCardTest(GrowthCase):
    """学期成绩单翻页与文案格式化测试集。"""

    def test_paging_and_texts(self) -> None:
        """验证空记录、索引越界回落、页码文案、原因行与进步行样式。"""
        self.assertIsNone(svc.report_card_page(CHILD, -1))
        subject = ec.SUBJECT_ABILITY_LIST[0]
        good = ec.REPORT_GRADE_NAME[ec.REPORT_GRADE_GOOD]
        self.grow(
            report_card_history=[
                {"year": 2020, "month": 9, "grade": ec.REPORT_GRADE_GOOD},
                {"grade": 99, "reason": "改岗", "rate": 80},
                {"level_change": {subject: [0, 2]}},
            ]
        )
        latest = svc.report_card_page(CHILD, -1)
        assert latest is not None
        self.assertEqual(
            (latest.index, latest.count, latest.reason, latest.progress_style),
            (2, 3, "", ""),
        )
        self.assertTrue(latest.progress.startswith("  那个学期的进步："))
        self.assertIn(
            ec.REPORT_GRADE_NAME[ec.REPORT_GRADE_NO_CLASS], latest.summary
        )
        self.assertEqual(
            svc.report_card_index_text(latest), "第 3 / 3 份（含最近一份）"
        )
        self.assertEqual(svc.report_card_page(CHILD, 3), latest)
        middle = svc.report_card_page(CHILD, 1)
        assert middle is not None
        self.assertEqual(middle.index, 1)
        self.assertEqual(middle.reason, "  ※ 改岗\n")
        self.assertIn(
            "　评定：无课可评　出勤 0 节／缺课 0 节（出勤率 80%）\n",
            middle.summary,
        )
        self.assertEqual(
            (middle.progress, middle.progress_style),
            ("  那个学期没有科目升级\n", svc.GRAY),
        )
        first = svc.report_card_page(CHILD, 0)
        assert first is not None
        self.assertIn(
            f"　评定：{good}　出勤 0 节／缺课 0 节（出勤率 100%）\n",
            first.summary,
        )
        self.assertTrue(first.summary.startswith("  2020"))


class PersonalityAndHistoryTest(GrowthCase):
    """性格倾向单元格与养成履历列表测试集。"""

    def test_personality(self) -> None:
        """验证正负倾向按整数格式化展示与零值未形成灰显样式。"""
        self.assertIsNone(svc.personality_cells(CHILD))
        pairs = sorted(ec.PERSONALITY_PAIR_NAME)
        self.grow(personality_point={pairs[0]: 2.4, pairs[1]: -3.6})
        cells = svc.personality_cells(CHILD)
        assert cells is not None
        names = [ec.PERSONALITY_PAIR_NAME[p] for p in pairs]
        self.assertEqual(cells[0], (f" 偏{names[0][0]}（2）", ""))
        self.assertEqual(cells[1], (f" 偏{names[1][1]}（4）", ""))
        self.assertEqual(
            cells[2], (f" {names[2][0]}/{names[2][1]}：尚未形成", svc.GRAY)
        )
        self.assertEqual(len(cells), len(pairs))

    def test_event_history(self) -> None:
        """验证时间排序、缺失事件过滤、标题截断、默认选项与超长省略提示。"""
        self.assertIsNone(svc.event_history(CHILD))
        when = datetime.datetime(2020, 3, 5, 8)
        self.grow(
            event_history={
                "g2": {"time": when + datetime.timedelta(days=2)},
                "g1": {"time": when, "choice": 1},
                "missing": {"time": when},
                "n0": {"choice": 3},
            }
        )
        with mock.patch.dict(game_config.config_official_event, EVENTS):
            self.assertEqual(
                svc.event_history(CHILD),
                (
                    "",
                    [
                        "   事件0 → （未作选择）\n",
                        "  2020/03/05 " + "一" * 24 + " → 选一\n",
                        "  2020/03/07 二号事件 → 选零\n",
                    ],
                ),
            )
            self.grow(
                event_history={
                    f"n{n}": {"time": when + datetime.timedelta(days=n)}
                    for n in range(10)
                }
            )
            history = svc.event_history(CHILD)
        assert history is not None
        omit, rows = history
        self.assertEqual(omit, "  （更早的 2 条已略去）\n")
        self.assertEqual(len(rows), ec.HISTORY_SHOW_MAX)
        self.assertTrue(rows[0].startswith("  2020/03/07 事件2"))


class PendingTest(GrowthCase):
    """待处理分区提示文本与事件队列清理测试集。"""

    def test_no_growth_data(self) -> None:
        """验证无养成数据时待处理提示列表为空。"""
        self.assertEqual(svc.pending_texts(CHILD), [])

    def test_every_pending_item(self) -> None:
        """验证未命名成绩单、炫耀过滤、今日翘课及事件队列计数与清理。"""
        subject = ec.SUBJECT_ABILITY_LIST[0]
        name = game_config.config_ability[subject].name
        self.grow(
            report_card_flag=True,
            show_off_ability={subject: 1, 99999: 1},
            skip_class_flag=True,
            skip_class_day=game_time.now().toordinal(),
        )
        uid = sorted(game_config.config_official_event)[0]
        owners = ((uid, CHILD), (uid, CHILD), ("missing", CHILD), (uid, MOTHER))
        official.set_queue(
            [{"uid": u, "chara_id": c, "partner_id": 0} for u, c in owners]
        )
        self.assertEqual(
            svc.pending_texts(CHILD),
            [
                "  ○新的成绩单待查看（用「检查成绩单」指令）\n",
                f"  ○有想炫耀的进步：{name}（下次见到你时会说）\n",
                "  ○今天正在翘课\n",
                "  ○有 2 件关于她的事等你在博士办公室「处理公务」时决断\n",
            ],
        )
        self.assertEqual(len(official.queue()), 3)

    def test_last_report_card_named(self) -> None:
        """验证存在最新成绩单年月时带学期名输出并忽略非当日翘课。"""
        self.grow(
            report_card_flag=True,
            report_card_history=[{"year": 2020, "month": 9}],
            skip_class_flag=True,
            skip_class_day=game_time.now().toordinal() - 1,
        )
        texts = svc.pending_texts(CHILD)
        self.assertEqual(len(texts), 1)
        self.assertTrue(texts[0].startswith("  ○2020"))
        self.assertTrue(
            texts[0].endswith("的成绩单待查看（用「检查成绩单」指令）\n")
        )


class PanelTest(GrowthCase):
    """养成总览面板绘制与翻页交互测试集。"""

    def setUp(self) -> None:
        """打桩绘制类、选人接口与候选名单以记录页面输出。"""
        super().setUp()
        self.drawn: list[tuple[str, str, str]] = []
        """ 记录已调用绘制对象的类名、文本与样式列表。 """
        for cls in (draw.NormalDraw, draw.LeftDraw, draw.CenterDraw):
            self.patch(cls, "draw", autospec=True, side_effect=self.record)
        for cls in (draw.LittleTitleLineDraw, draw.LineDraw, draw.CenterButton):
            self.patch(cls, "draw", new=lambda self: None)
        line = "draw_select_student_line"
        self.patch(student_select, line, side_effect=lambda w, s, r: s != -1)
        roster = growth_panel.growth_handle
        listed = [CHILD, OTHER]
        self.patch(roster, "get_student_candidate_list", return_value=listed)
        self.picker = self.patch(
            student_select, "select_student", return_value=CHILD
        )
        """ 选人弹窗函数 select_student 的模拟对象。 """

    def patch(
        self, target: object, name: str, **options: Any
    ) -> mock.MagicMock:
        """在当前测试用例上下文中为目标对象属性安装补丁。"""
        return self.enterContext(mock.patch.object(target, name, **options))

    def opened(self) -> growth_panel.Growth_Panel:
        """创建面板、选中主测试女儿并清空初始绘制记录。"""
        page = growth_panel.Growth_Panel(120)
        page.draw_page([])
        page.handle_yrn(ec.SELECT_STUDENT_RETURN)
        self.drawn.clear()
        return page

    def record(self, item: draw.NormalDraw) -> None:
        """将普通文本绘制对象的类名、文本与样式写入记录列表。"""
        self.drawn.append(
            (type(item).__name__, item.text, getattr(item, "style", ""))
        )

    def test_report_card_paging(self) -> None:
        """验证多份成绩单下的翻页按钮返回值、禁用占位与索引切换。"""
        self.grow(report_card_history=[{}, {}, {}])
        page = self.opened()
        offered: list[str] = []
        page.draw_page(offered)
        self.assertEqual(page.report_card_index, 2)
        self.assertEqual(offered, [ec.REPORT_CARD_PREV])
        self.assertIn(
            ("CenterDraw", "第 3 / 3 份（含最近一份）", "standard"), self.drawn
        )
        self.assertIn(("CenterDraw", "　下一学期 →", svc.GRAY), self.drawn)
        page.handle_yrn(ec.REPORT_CARD_PREV)
        offered.clear()
        page.draw_page(offered)
        self.assertEqual(page.report_card_index, 1)
        self.assertEqual(offered, [ec.REPORT_CARD_PREV, ec.REPORT_CARD_NEXT])
        page.handle_yrn(ec.REPORT_CARD_PREV)
        offered.clear()
        page.draw_page(offered)
        self.assertEqual(
            (page.report_card_index, offered), (0, [ec.REPORT_CARD_NEXT])
        )

    def test_single_card_has_no_paging(self) -> None:
        """验证单份成绩单时不输出翻页按钮与翻页返回值。"""
        self.grow(report_card_history=[{}])
        page = self.opened()
        offered: list[str] = []
        page.draw_page(offered)
        self.assertEqual((page.report_card_index, offered), (0, []))
        self.assertFalse(any("学期 →" in text for _, text, _ in self.drawn))

    def test_switching_child_resets_paging(self) -> None:
        """验证切换孩子时重置成绩单索引，重选同一孩子时保持索引。"""
        self.child(OTHER, 103)
        with growth.editing(OTHER) as data:
            assert data is not None
            data.report_card_history = [{}, {}]
        self.grow(report_card_history=[{}, {}, {}])
        page = self.opened()
        page.draw_page([])
        page.handle_yrn(ec.REPORT_CARD_PREV)
        page.handle_yrn(ec.REPORT_CARD_PREV)
        self.picker.return_value = OTHER
        page.handle_yrn(ec.SELECT_STUDENT_RETURN)
        self.assertEqual(
            (page.now_student, page.report_card_index), (OTHER, -1)
        )
        page.draw_page([])
        self.assertEqual(page.report_card_index, 1)
        page.handle_yrn(ec.REPORT_CARD_PREV)
        page.handle_yrn(ec.SELECT_STUDENT_RETURN)
        self.assertEqual(page.report_card_index, 0)

    def test_subject_rows_wrap_every_four(self) -> None:
        """验证科目水平网格每绘制四个左对齐单元后插入一次换行。"""
        page = self.opened()
        page.draw_page([])
        kinds = [kind[0] if kind[1] != "\n" else "/" for kind in self.drawn]
        start = kinds.index("LeftDraw")
        self.assertEqual(
            kinds[start : start + 10],
            ["LeftDraw"] * 4 + ["/"] + ["LeftDraw"] * 4 + ["/"],
        )


class UiFreeRunTest(FastTestCase):
    """无界面独立子进程导入隔离测试集。"""

    child: ChildRun
    """ 子进程执行结果对象，保存负载与受限模块检测记录。 """
    error: str
    """ 子进程运行抛出异常时的错误信息字符串。 """

    @classmethod
    def setUpClass(cls) -> None:
        """启动拦截界面与结算导入的子进程并缓存执行结果。"""
        super().setUpClass()
        cls.error = ""
        try:
            cls.child = run_ui_free(UI_FREE_RUN, boot=True)
        except RuntimeError as error:
            cls.error = str(error)
            cls.child = ChildRun({}, [], [])

    def test_no_ui_or_settle_loaded(self) -> None:
        """验证子进程无报错、未加载或尝试导入受限模块且返回预期数量的非空文本。"""
        self.assertEqual(self.error, "")
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))
        self.assertEqual(self.child.payload["texts"], 121)
