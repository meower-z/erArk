"""
个人课表服务测试
================
验证个人课表服务的单元格文本、教室常规课行、临时课过滤与个人式课候选项规则。
验证复制、写入与清空课表、日程槽位标签以及一键选课各分支提示文本。
在拦截 Script.UI 与 Script.Settle 的子进程中运行服务入口以确认无受限导入。
"""

from Script.Config import game_config
from Script.System.Education_System import education_constant as E
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

SCENARIO = """
import contextlib, io
from Script.Config import game_config, map_config
with contextlib.redirect_stdout(io.StringIO()):
    map_config.init_map_data()
from Script.Core import get_text
from Script.Design import attr_calculation, game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, chara_life, facility, growth
from Script.Modules.domains import identity, relations, roster, status, wardrobe
from Script.Modules.gameplay_resolution import working
from Script.Modules.gameplay_resolution import course_select_service as svc
from Script.Modules.save_load import kernel_state
from Script.System.Education_System import education_constant as E
from Script.System.Education_System import schedule_handle as sh
from Script.System.Education_System import schedule_template_handle as th
from Script.System.Education_System import sex_class_handle as sc
core.reset_state(core.GameState(kernel_state.first_clock(), {}, {}))
out = payload
_ = get_text._
POOL, PILE = _("游泳池"), _("木桩房")
INTEREST, INTERN = E.COURSE_TYPE_INTEREST, E.COURSE_TYPE_INTERN
with working.based_on(core.state()):
    for cid in (0, 101, 102, 201, 202, 203):
        identity.put(identity.Identity(cid, name=f"n{cid}", sex=1))
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
    chara_life.work_type.set(102, 21)
    for open_cid in game_config.config_facility_open:
        facility.set_open(open_cid, True)
    for name in (POOL, "前卫街机厅", "铁匠铺"):
        facility.set_open(game_config.config_facility_open_name_to_cid[name], False)
    for cid in (58, 111):
        game_config.config_entertainment[cid].need = "W151|1"
    R1, R2 = sh.get_classroom_list()[:2]
    out["rooms"] = [R1, R2]
    sh.set_class_cell(R1, 0, 0, 45, 101)
    sh.set_class_cell(R1, 0, 1, 45, 102)
    sh.set_class_cell(R1, 0, 2, 70, -1)
    out["rows"] = [
        [[r.classroom, r.text, r.choice and list(r.choice), r.absent] for r in svc.classroom_rows(0, p)[:2]]
        for p in (0, 1, 2, 3)
    ]
    sh.set_class_cell(R1, 0, 4, 9999, 101)
    RP = sh.get_classroom_list(E.COURSE_TYPE_PRACTICE)[0]
    TODAY = game_time.now().weekday()
    sc.set_temp_class(game_time.now().date().toordinal(), 8, RP, 70, must_attend=[])
    sh.set_selected_course(202, TODAY, 8, E.COURSE_TYPE_PRACTICE, RP)
    temp_rows = [r for r in svc.classroom_rows(TODAY, 8) if r.classroom == RP]
    out["temp"] = [RP, temp_rows[0].text, temp_rows[0].choice, svc.cell_text(202, TODAY, 8)]
    options = {t: svc.target_options(201, t) for t in (E.COURSE_TYPE_PE, INTEREST, INTERN)}
    out["options"] = {
        str(t): [[o.target, o.text, o.enabled] for o in opts] for t, opts in options.items()
    }
    plan = [
        (0, 0, E.COURSE_TYPE_THEORY, R1),
        (0, 3, E.COURSE_TYPE_THEORY, R1),
        (0, 4, E.COURSE_TYPE_THEORY, R1),
        (1, 0, E.COURSE_TYPE_PE, POOL),
        (1, 1, E.COURSE_TYPE_PE, PILE),
        (1, 2, INTEREST, 58),
        (1, 3, INTEREST, 111),
        (1, 4, INTEREST, 51),
        (1, 5, INTERN, 11),
        (1, 6, INTERN, 22),
    ]
    for day, period, course_type, target in plan:
        sh.set_selected_course(201, day, period, course_type, target)
    out["cells"] = [svc.cell_text(201, d, p) for d, p, _t, _g in plan] + [svc.cell_text(201, 6, 8)]
    out["head"] = svc.course_head_text(201, 0, 3)
    out["targets"] = [list(t) for t in svc.copy_targets(201, [201, 202, 203])]
    sh.set_selected_course(202, 5, 5, E.COURSE_TYPE_PE, PILE)
    svc.copy_schedule(201, 202)
    grid = [(d, p) for d in range(7) for p in range(9)]
    same = [sh.get_selected_course(202, d, p) == sh.get_selected_course(201, d, p) for d, p in grid]
    out["copied"] = same.count(True)
    out["copied_extra"] = sh.get_selected_course(202, 5, 5)
    svc.apply_choice(203, 2, 2, (E.COURSE_TYPE_PE, PILE))
    out["chosen"] = sh.get_selected_course(203, 2, 2)
    svc.apply_choice(203, 2, 2, "CLEAR")
    out["unchosen"] = sh.get_selected_course(203, 2, 2)
    svc.clear_student(201)
    out["cleared"] = sum(sh.get_selected_course(201, d, p) is None for d, p in grid)
    out["slots_none"] = svc.slot_labels(203)
    th.apply_template(203, 1)
    th.set_child_override(203, 1, 155)
    out["slots"] = svc.slot_labels(203)
    fills = [svc.auto_fill_text(203), svc.auto_fill_text(203)]
    for d, p in grid:
        sh.set_class_cell(R2, d, p, 45, 101)
    fills += [svc.auto_fill_text(203), svc.auto_fill_text(203)]
    out["fills"] = fills
"""
""" 在无界面子进程中构造测试数据并调用个人课表服务各公开入口的脚本。 """


class CourseSelectServiceTest(FastTestCase):
    """个人课表服务的规则与无界面导入隔离测试。"""

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

    def test_cell_texts(self) -> None:
        """验证教室课、已停课、未知科目、个人式课未开放与条件不符及空格子的文本输出。"""
        room = self.out["rooms"][0]
        self.assertEqual(
            self.out["cells"],
            [
                f"{game_config.config_ability[45].name}/{room}",
                f"{room}/已停课",
                f"{room}/已停课",
                "[体]游泳池/未开放",
                "[体]木桩房",
                "[兴]下棋/条件不符",
                "[兴]玩街机游戏/未开放",
                "[兴]唱歌",
                "[实]供能调控员",
                "[实]铁匠/未开放",
                "--",
            ],
        )

    def test_classroom_rows(self) -> None:
        """验证在岗教师、离岗标灰、无教师自习与无课教室的选课行输出。"""
        r1, r2 = self.out["rooms"]
        subject = {i: game_config.config_ability[i].name for i in (45, 70)}
        empty = [r2, f" {r2}（本节没有课）", None, False]
        self.assertEqual(
            self.out["rows"],
            [
                [
                    [
                        r1,
                        f"[{r1}] {subject[45]}/n101（理论课）",
                        [0, r1],
                        False,
                    ],
                    empty,
                ],
                [
                    [
                        r1,
                        f"[{r1}] {subject[45]}/n102（已离岗）（理论课）",
                        [0, r1],
                        True,
                    ],
                    empty,
                ],
                [
                    [
                        r1,
                        f"[{r1}] {subject[70]}/无教师（自习）（理论课）",
                        [0, r1],
                        False,
                    ],
                    empty,
                ],
                [[r1, f" {r1}（本节没有课）", None, False], empty],
            ],
        )

    def test_temp_class(self) -> None:
        """验证当日临时实操课不列入教室选课行但会显示在个人课表单元格文本中。"""
        room, text, choice, cell = self.out["temp"]
        self.assertEqual((text, choice), (f" {room}（本节没有课）", None))
        self.assertEqual(cell, f"{game_config.config_ability[70].name}/{room}")

    def test_target_options(self) -> None:
        """验证体育、兴趣与实习课的候选项筛选规则及未开放与条件不符置灰状态。"""
        options = self.out["options"]
        self.assertEqual(
            options[str(E.COURSE_TYPE_PE)],
            [
                ["木桩房", "[木桩房]", True],
                ["射击房", "[射击房]", True],
                ["健身区", "[健身区]", True],
                ["游泳池", " 游泳池（未开放）", False],
            ],
        )
        interest = {
            row[0]: row[1:] for row in options[str(E.COURSE_TYPE_INTEREST)]
        }
        self.assertEqual(
            list(interest),
            [
                cid
                for cid, data in game_config.config_entertainment.items()
                if data.class_ok
            ],
        )
        self.assertEqual(interest[58], [" 下棋（条件不符）", False])
        self.assertEqual(interest[111], [" 玩街机游戏（未开放）", False])
        self.assertEqual(interest[51], ["[唱歌]", True])
        intern = {row[0]: row[1:] for row in options[str(E.COURSE_TYPE_INTERN)]}
        self.assertEqual(len(intern), 17)
        self.assertFalse(set(intern) & E.EXCLUDE_INTERN_WORK_TYPE)
        self.assertEqual(intern[22], [" 铁匠（未开放）", False])
        self.assertEqual(intern[11], ["[供能调控员]", True])

    def test_schedule_edits(self) -> None:
        """验证复制目标列表、复制与清空 63 格、单格写入清除以及选课页标题文本。"""
        out = self.out
        self.assertEqual(out["targets"], [["[n202]", 202], ["[n203]", 203]])
        self.assertEqual((out["copied"], out["copied_extra"]), (63, None))
        self.assertEqual(out["chosen"], [E.COURSE_TYPE_PE, "木桩房"])
        self.assertIsNone(out["unchosen"])
        self.assertEqual(out["cleared"], 63)
        self.assertEqual(out["head"], "  n201｜周一 第4节 11:15~12:00\n\n")

    def test_slot_labels(self) -> None:
        """验证无模板、套用模板及存在单槽覆盖时的三时段日程按钮标签。"""
        free = "自由选择娱乐活动"
        self.assertEqual(
            self.out["slots_none"],
            [f" [{slot}：{free}]" for slot in ("上午", "下午", "晚上")],
        )
        self.assertEqual(
            self.out["slots"],
            [
                " [上午：上课（无课时自习）]",
                " [下午：上课（无课时自习）（单独指定）]",
                " [晚上：读书]",
            ],
        )

    def test_auto_fill_texts(self) -> None:
        """验证一键选课在部分选上、全岛无课、补满与已选满四种情况下的提示文本。"""
        self.assertEqual(
            self.out["fills"],
            [
                "\n已为n203选上 4 节课；另有 59 节全岛都没有教室开课，留给日程模板\n",
                "\n没能选上任何一节课：全岛课表上还没排课，先去「全局课表」排好再来\n",
                "\n已为n203选上 59 节课\n",
                "\nn203的课表已经选满了\n",
            ],
        )
