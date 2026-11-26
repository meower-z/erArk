"""
课表与实操课排课服务测试
========================
验证全局课表服务的缺位标注、文本格式化、周表格子、覆盖提示与自动排课文案。
验证实操课排课服务的草稿载入、主修按钮、出勤预览与必修学生顶替说明规则。
在拦截 Script.UI 与 Script.Settle 的子进程中运行服务入口以确认无受限导入。
"""

from Script.Config import game_config
from Script.Core import text_handle
from Script.Design import attr_calculation
from Script.System.Education_System import education_constant as E
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

SCENARIO = """
import contextlib, datetime, io
from Script.Config import game_config, map_config
with contextlib.redirect_stdout(io.StringIO()):
    map_config.init_map_data()
from Script.Design import attr_calculation, game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, chara_life, facility, flags
from Script.Modules.domains import identity, relations, roster, status, wardrobe
from Script.Modules.gameplay_resolution import working
from Script.Modules.gameplay_resolution import class_schedule_service as svc
from Script.Modules.gameplay_resolution import sex_class_plan_service as plan
from Script.Modules.save_load import kernel_state
from Script.System.Education_System import education_constant as E
from Script.System.Education_System import schedule_handle as sh
from Script.System.Education_System import sex_class_handle as sc
from Script.System.Pregnancy_System import pregnancy_constant
core.reset_state(core.GameState(kernel_state.first_clock(), {}, {}))
out = payload
TEACHERS = (101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113)
NAMES = {0: "Doc", 104: "LongNameTeacherX", 201: "d1", 202: "d2", 203: "d3"}
with working.based_on(core.state()):
    for cid in (0, *TEACHERS, 201, 202, 203, 301):
        identity.put(identity.Identity(cid, name=NAMES.get(cid, f"t{cid}"), sex=1))
        abilities.talent(cid).replace(attr_calculation.get_talent_zero({}))
        abilities.ability(cid).replace(attr_calculation.get_ability_zero({}))
        abilities.experience(cid).replace(attr_calculation.get_experience_zero({}))
        abilities.juel(cid).replace(attr_calculation.get_juel_zero({}))
        status.replace(cid, attr_calculation.get_status_zero({}))
        wardrobe.put(cid, attr_calculation.get_cloth_zero())
        relations.favorability.set(cid, {0: 0})
        relations.assistant_services.set(cid, attr_calculation.get_assistant_services_zero())
        chara_life.work_type.set(cid, 152 if cid > 200 else 151 if cid else 0)
        if cid:
            roster.add(cid)
    for cid in (201, 202, 203):
        relations.father_id.set(cid, 0)
        abilities.talent(cid)[103] = 1
    abilities.ability(101)[45] = 5
    abilities.ability(106)[45] = 5
    abilities.ability(105)[45] = 3
    for open_cid in game_config.config_facility_open:
        facility.set_open(open_cid, True)
    rooms = sh.get_classroom_list()
    R1, R2 = rooms[0], rooms[1]
    RP = sh.get_classroom_list(E.COURSE_TYPE_PRACTICE)[0]
    HALL = sh.get_classroom_list(E.COURSE_TYPE_PUBLIC)[0]
    TODAY = game_time.now().weekday()
    out["rooms"] = [R1, RP, HALL]
    chara_life.work_type.set(102, 21)
    flags.set(102, imprisonment=True)
    flags.set(103, imprisonment=True)
    roster.discard(103)
    roster.discard(104)
    out["marks"] = [
        [svc.get_teacher_absent_mark(cid, short) for cid in (0, -1, 101, 102, 103, 104)]
        for short in (False, True)
    ]
    out["fit"] = [svc.fit_text_width("tA", 5), svc.fit_text_width("学识abc", 5), svc.fit_text_width("ab", -1)]
    out["heads"] = [svc.cell_width(190), svc.period_head_text(0), svc.period_head_text(8)]
    out["info"] = [svc.classroom_info_text(R1), svc.subject_header_text(R1, 0, 3)]
    sh.set_class_cell(R1, 0, 0, 70, 101)
    sh.set_class_cell(R1, 0, 1, 45, -1)
    sh.set_class_cell(R1, 0, 2, 45, 103)
    sh.set_class_cell(R1, 0, 3, 45, 104)
    sh.set_class_cell(R1, TODAY, 8, 45, 101)
    sh.set_class_cell(R2, 0, 7, 45, 101)
    sh.set_class_cell(RP, 2, 5, 43, -1)
    sh.set_class_cell(RP, 2, 6, 9999, -1)
    today_ord = game_time.now().date().toordinal()
    od = sc.get_date_ordinal_by_week_day(TODAY, 8)
    for ordinal in {today_ord, od}:
        sc.set_temp_class(ordinal, 8, RP, 70, must_attend=[202])
    cell_args = [(R1, 0, 0), (R1, 0, 1), (R1, 0, 2), (R1, 0, 3), (R1, 0, 4), (RP, TODAY, 8), (R1, TODAY, 8)]
    out["cells"] = [list(map(str, (c.text, c.absent, c.tooltip))) for c in (svc.week_cell(*a, 25) for a in cell_args)]
    overlays = [svc.overlay_text(R1, TODAY, 8), svc.overlay_text(RP, TODAY, 8)]
    sh.set_class_cell(RP, TODAY, 8, 45, 103)
    overlays.append(svc.overlay_text(RP, TODAY, 8))
    sh.set_class_cell(RP, TODAY, 8, 45, -1)
    overlays.append(svc.overlay_text(RP, TODAY, 8))
    out["overlay"] = overlays
    out["labels"] = [len(svc.subject_labels()), svc.subject_labels()[0], svc.ability_label(45), svc.ability_label(-5)]
    out["entry"] = [svc.has_sex_class_entry(r) for r in (R1, RP, HALL)]
    for desc in (True, False):
        rows = svc.teacher_rows(45, 0, 0, R2, desc)
        out[f"rows{desc}"] = [[r.teacher_id, r.label, r.conflict] for r in rows[:3]]
        out[f"summary{desc}"] = svc.conflict_summary(rows)
    out["no_conflict"] = svc.conflict_summary(svc.teacher_rows(45, 0, 5, R2, True))
    drafts = [plan.load_draft(room, TODAY, 8) for room in (RP, R1)] + [plan.load_draft(R1, 2, 4)]
    out["drafts"] = [[d.exists, d.other_classroom, d.ability_id, d.must_attend] for d in drafts]
    out["draft_day"] = drafts[0].date_ordinal == od
    date_text = pregnancy_constant.format_season_date(datetime.datetime.fromordinal(od + 5))
    out["date"] = [plan.info_text(RP, 2, 3, od + 5), date_text]
    out["subjects"] = [list(b) for b in plan.subject_buttons(71)[:2]]
    for cid in (201, 203):
        sh.set_selected_course(cid, 0, 0, E.COURSE_TYPE_THEORY, R1)
    for cid in (201, 202, 203):
        sh.set_selected_course(cid, 2, 3, E.COURSE_TYPE_PRACTICE, RP)
    sh.set_selected_course(201, 2, 5, E.COURSE_TYPE_PRACTICE, RP)
    sh.set_selected_course(202, 2, 5, E.COURSE_TYPE_PE, list(E.PE_PLACE_DATA)[0])
    sh.set_selected_course(201, 2, 6, E.COURSE_TYPE_PRACTICE, RP)
    sh.set_selected_course(202, 2, 6, E.COURSE_TYPE_THEORY, R2)
    sh.set_selected_course(201, 2, 7, E.COURSE_TYPE_INTEREST, 0)
    flags.set(203, imprisonment=True)
    out["attend"] = [
        plan.attendance_lines(RP, 2, 3, must)
        for must in ([], [201], [201, 202, 203, 301])
    ] + [plan.attendance_lines(RP, 2, 4, [])]
    must = {}
    for period in (5, 6, 7):
        rows = plan.must_rows([201], 2, period)
        must[period] = [[[r.character_id, r.label, r.replace_text] for r in rows], plan.replace_summary(rows)]
    out["must"] = must
    out["toggled"] = [plan.toggled([201, 202], 201), plan.toggled([202], 201)]
    fills = [svc.auto_fill(), svc.auto_fill()]
    for cid in TEACHERS[1:]:
        chara_life.work_type.set(cid, 21)
    svc.clear_room(R1)
    out["cleared"] = sum(sh.get_class_cell(R1, d, p) is None for d in range(7) for p in range(9))
    fills += [svc.auto_fill(), svc.auto_fill()]
    chara_life.work_type.set(101, 21)
    fills.append(svc.auto_fill())
    out["fills"] = fills
"""
""" 在无界面子进程中构造测试数据并调用两项服务各公开入口的脚本。 """


class ClassScheduleServiceTest(FastTestCase):
    """课表服务与实操课排课服务的规则及无界面导入隔离测试。"""

    child: ChildRun
    out: dict

    @classmethod
    def setUpClass(cls) -> None:
        """启动无界面子进程执行测试场景并保存运行结果与受限导入记录。"""
        cls.child = run_ui_free(SCENARIO, boot=True)
        cls.out = cls.child.payload

    def test_ui_free(self) -> None:
        """验证无界面子进程运行期间未加载也未尝试导入受限模块。"""
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_absent_marks(self) -> None:
        """验证教师缺位标注的全称与短写文本及离岗、监禁、离岛优先级。"""
        self.assertEqual(
            self.out["marks"],
            [
                ["", "", "", "（已离岗）", "（被监禁）", "（不在岛上）"],
                ["", "", "", "（离岗）", "（监禁）", "（离岛）"],
            ],
        )

    def test_text_helpers(self) -> None:
        """验证显示宽度截断、单元格宽度、节次列与教室和选科目页标题文本。"""
        self.assertEqual(self.out["fit"], ["tA", "学识a", ""])
        self.assertEqual(self.out["heads"], [25, "  1 09:00 ", "  9 17:00 "])
        room = self.out["rooms"][0]
        self.assertEqual(
            self.out["info"],
            [
                f"  {room}｜承载课型：理论课\n",
                f"  {room}｜周一 第4节 11:15~12:00\n",
            ],
        )

    def test_week_cells(self) -> None:
        """验证常规、待定、缺位截断、空位与当日临时课顶替等周表格子输出。"""
        name = {i: game_config.config_ability[i].name for i in (45, 70)}
        tip = "：她来不了，这一节学生会降级为自习；点格子可改排教师"
        mark = "（离岛）"
        room = 25 - text_handle.get_text_index(f"{name[45]}/{mark}")
        self.assertEqual(
            self.out["cells"],
            [
                [f"{name[70]}/t101", "False", ""],
                [f"{name[45]}/待定", "False", ""],
                [f"{name[45]}/t103（监禁）", "True", f"t103（被监禁）{tip}"],
                [
                    f"{name[45]}/{'LongNameTeacherX'[:room]}{mark}",
                    "True",
                    f"LongNameTeacherX（不在岛上）{tip}",
                ],
                ["--", "False", ""],
                [f"[临]{name[70]}/Doc", "False", ""],
                [f"{name[45]}/t101", "False", ""],
            ],
        )

    def test_overlay_text(self) -> None:
        """验证无顶替时返回空串及顶替下未排课、缺位教师与待定格子的覆盖提示。"""
        overlay = self.out["overlay"]
        self.assertEqual(overlay[0], "")
        name = game_config.config_ability[45].name
        heads = [text.split("\n")[0] for text in overlay[1:]]
        self.assertEqual(
            [head.split("：")[-1] for head in heads],
            ["未排课", f"{name}/t103（被监禁）", f"{name}/待定"],
        )
        self.assertIn("主修指技", heads[0])

    def test_subject_page(self) -> None:
        """验证 18 门科目按钮标签、未知科目名称回落及不同课型教室的实操课入口。"""
        count, first, known, unknown = self.out["labels"]
        self.assertEqual(count, 18)
        subject = game_config.config_ability[E.SUBJECT_ABILITY_LIST[0]].name
        self.assertEqual(first[0], f"[0]{subject}")
        self.assertEqual(
            (known, unknown), (game_config.config_ability[45].name, "该科目")
        )
        self.assertEqual(self.out["entry"], [False, True, True])

    def test_teacher_rows(self) -> None:
        """验证教师按科目等级升降序排列、周排课统计、冲突标记与底部冲突汇总。"""
        b5 = f"{attr_calculation.judge_grade(5)}5"
        b3 = f"{attr_calculation.judge_grade(3)}3"
        conflict = f"第1节已在{self.out['rooms'][0]}"
        self.assertEqual(
            self.out["rowsTrue"],
            [
                [101, f" t101 {b5}/3节※", conflict],
                [106, f"[t106 {b5}/0节]", ""],
                [105, f"[t105 {b3}/0节]", ""],
            ],
        )
        self.assertEqual(
            [row[0] for row in self.out["rowsFalse"]], [113, 112, 111]
        )
        expected = f"  ※本节已有课：t101（{conflict}）\n"
        self.assertEqual(self.out["summaryTrue"], expected)
        self.assertEqual(self.out["no_conflict"], "")

    def test_auto_fill_texts(self) -> None:
        """验证自动排课各结果分支提示文本及清空教室后 63 格置空。"""
        fills = self.out["fills"]
        self.assertTrue(fills[0].startswith("\n已自动排课 "))
        self.assertNotIn("另有", fills[0])
        self.assertEqual(fills[1], "\n课表已经排满了，没有空格子可排\n")
        self.assertIn("节因为当时没有空闲教师而留空\n", fills[2])
        self.assertTrue(fills[3].startswith("\n没能排上任何一节课："))
        self.assertEqual(fills[4], fills[1])
        self.assertEqual(self.out["cleared"], 63)

    def test_drafts(self) -> None:
        """验证同室、异室与未排课草稿载入、季节日期文本及主修科目按钮状态。"""
        practice = self.out["rooms"][1]
        self.assertEqual(
            self.out["drafts"],
            [
                [True, "", 70, [202]],
                [True, practice, 70, [202]],
                [False, "", 70, []],
            ],
        )
        self.assertTrue(self.out["draft_day"])
        info, date_text = self.out["date"]
        self.assertIn(f"日期：{date_text}（周三）", info)
        self.assertIn("节次：第4节 11:15~12:00", info)
        self.assertEqual(
            self.out["subjects"], [[" 指技 ", 70, False], ["[舌技]", 71, True]]
        )

    def test_attendance_lines(self) -> None:
        """验证出勤预览四段文案、深灰样式及受阻与未修前置课学生分组。"""
        attend = self.out["attend"]
        styles = [[style for _, style in lines] for lines in attend]
        self.assertEqual(
            styles,
            [
                ["", "deep_gray", "deep_gray", ""],
                ["", "deep_gray", "deep_gray", ""],
            ]
            + [["", "deep_gray", ""], ["", ""]],
        )
        texts = [[text for text, _ in lines] for lines in attend]
        self.assertIn("：1 人（d1）", texts[0][0])
        self.assertIn("：d3\n", texts[0][1])
        self.assertIn("：d2\n", texts[0][2])
        self.assertIn(
            "必修（无论原本排了什么都来，且不会翘课）：无", texts[0][3]
        )
        self.assertIn("选修的人都进不了课堂", texts[1][0])
        self.assertIn("点名必修的学生照常会来", texts[2][0])
        self.assertIn("另有 2 人会到场", texts[2][1])
        self.assertIn("：d1、d2、d3、t301\n", texts[2][2])
        self.assertIn("没有学生会来", texts[3][0])

    def test_must_rows(self) -> None:
        """验证必修学生勾选与顶替星号、教室与个人课顶替汇总及名单切换。"""
        must = self.out["must"]
        practice = self.out["rooms"][1]
        cook = game_config.config_ability[43].name
        rows5, summary5 = must["5"]
        self.assertEqual(rows5[0], [201, "[√d1*]", f"d1→{practice}的{cook}"])
        self.assertEqual(rows5[1][:2], [202, "[  d2*]"])
        self.assertTrue(rows5[1][2].startswith("d2→体育课·"))
        self.assertEqual(
            summary5, f"  *会顶替原本的课：{rows5[0][2]}、{rows5[1][2]}\n"
        )
        self.assertEqual(
            must["6"][0],
            [[201, "[√d1*]", f"d1→{practice}"], [202, "[  d2]", ""]],
        )
        self.assertEqual(
            must["7"], [[[201, "[√d1]", ""], [202, "[  d2]", ""]], ""]
        )
        self.assertEqual(self.out["toggled"], [[202], [202, 201]])
