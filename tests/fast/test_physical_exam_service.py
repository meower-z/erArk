"""
体检服务与报告测试
==================
验证身体检查行过滤与次数上限、检查与报告成就记录、体检结束结算、日程配置与候选名单。
验证体检报告各段文本生成且不写状态，并在隔离子进程中确认服务运行不导入界面与结算模块。
"""

from Script.Config import game_config
from Script.Design import attr_text, game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, achievement, action_info
from Script.Modules.domains import first_record, flags, hypnosis, physical_exam
from Script.Modules.gameplay_resolution import physical_exam_report as report
from Script.Modules.gameplay_resolution import physical_exam_service as svc
from Script.Modules.gameplay_resolution import working
from tests.chara_activity import aim
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free
from tests.world import DEFAULT_SCENE

NPC = 1
""" 测试用受检干员编号。 """
FOLDS = {"examine_vulva_and_shape", "examine_vagina_and_folds"}
""" 检查处女膜所需的前置检查集合。 """
CHAINS = {*FOLDS, "examine_anus", "examine_urethra"}
""" 解锁多条后续部位检查的前置检查集合。 """
UI_FREE_RUN = """
import contextlib, io
from Script.Config import map_config
with contextlib.redirect_stdout(io.StringIO()):
    map_config.init_map_data()
from Script.Design import attr_calculation, game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, first_record, identity
from Script.Modules.domains import inventory, physical_exam, roster, warehouse
from Script.Modules.gameplay_resolution import physical_exam_report as report
from Script.Modules.gameplay_resolution import physical_exam_service as svc
from Script.Modules.gameplay_resolution import working
from tests import kernel_data
from tests.world import DEFAULT_SCENE, start_time
from Script.Config import game_config
kernel_data.reset_clock(start_time(), {})
with working.based_on(core.state()):
    for cid, name in ((0, "doctor"), (1, "patient")):
        identity.put(identity.Identity(cid, name=name))
        abilities.talent(cid).replace(attr_calculation.get_talent_zero({}))
        abilities.ability(cid).replace(attr_calculation.get_ability_zero({}))
        abilities.experience(cid).replace(attr_calculation.get_experience_zero({}))
        inventory.replace_items(cid, attr_calculation.get_item_zero({}))
    roster.add(1)
    warehouse.set_all({rid: 0 for rid in game_config.config_resouce})
    activity.set_target(0, 1)
    talent = abilities.talent(1)
    for tid in (0, 1, 2, 4, 20, 72, 113, 151):
        talent[tid] = 1
    every = {b for b, d in game_config.config_behavior.items() if "检查" in d.tag}
    payload["rows"] = [
        [r.behavior_id, r.enabled] for r in svc.check_rows(1, every)
    ]
    talent[0] = 0
    talent[4] = 0
    hymen = [r for r in svc.check_rows(1, every) if r.behavior_id == "examine_hymen"]
    payload["hymen_row"] = [r.label for r in hymen]
    payload["record"] = svc.record_check(1, "examine_hair")
    with first_record.editing(1) as fr:
        fr.first_kiss_id = 0
        fr.first_kiss_time = game_time.now()
        fr.first_kiss_place = list(DEFAULT_SCENE)
        fr.first_kiss_body_part = 1
        fr.first_part_sex_dict[6] = {
            "id": 0, "time": game_time.now(), "place": list(DEFAULT_SCENE),
            "posture": "p", "item": -1,
        }
    payload["hymen"] = svc.record_check(1, "examine_hymen")
    payload["done"] = sorted(svc.done_checks(1))
    payload["report"] = report.report_text(1, every, "doctor")
    talent[20] = 0
    talent[72] = 0
    talent[151] = 0
    payload["plain"] = report.report_text(1, set(), "doctor")
    payload["report_ids"] = svc.record_report(1)
    svc.finish_exam(1, svc.done_checks(1))
    svc.finish_exam(1, set())
    payload["today"] = sorted(svc.done_checks(1))
    payload["closed"] = [r.setting_id for r in svc.setting_rows()]
    physical_exam.set_setting(2, 1)
    physical_exam.set_setting(4, 2)
    physical_exam.set_setting(7, 1)
    svc.toggle_chosen(1)
    payload["open"] = [
        [r.setting_id, r.roster_size, r.day_count] for r in svc.setting_rows()
    ]
    svc.toggle_chosen(1)
    svc.cycle_setting(3, 4)
    svc.cycle_setting(1, 2)
    svc.cycle_setting(1, 2)
    svc.set_daily_count("")
    svc.set_daily_count("12")
    payload["settings"] = physical_exam.settings()
    payload["candidates"] = svc.exam_candidates()
"""
""" 在无界面子进程中执行体检服务与体检报告各主要入口的测试脚本。 """


class ExamCase(FastTestCase):
    """体检服务与报告测试的公共基类。"""

    def setUp(self) -> None:
        """创建主角与测试干员、设定查看目标并开启状态写缓冲。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        aim(0, NPC)
        self.enterContext(working.based_on(core.state()))

    def rows(self, done: set[str]) -> dict[str, svc.CheckRow]:
        """
        将当前测试干员的检查行列表转为按行为编号索引的字典。
        Keyword arguments:
        done -- set[str]，已完成的检查行为编号集合
        Return arguments:
        dict[str, svc.CheckRow] -- 行为编号到检查行对象的映射
        """
        return {row.behavior_id: row for row in svc.check_rows(NPC, done)}

    def lose_virginity(self, when: object) -> None:
        """
        将测试干员设为非处女并在给定时间写入 V 处女失身记录。
        Keyword arguments:
        when -- object，失身时间对象
        Return arguments:
        None -- 无返回值
        """
        abilities.talent(NPC)[0] = 0
        with first_record.editing(NPC) as fr:
            fr.first_part_sex_dict[6] = {
                "id": 0,
                "time": when,
                "place": list(DEFAULT_SCENE),
                "posture": "体位",
                "item": -1,
            }


class CheckRowsTest(ExamCase):
    """身体检查项目列表过滤、编号、禁用与骚扰标记测试。"""

    def test_follow_up_waits_for_its_prerequisite(self) -> None:
        """验证后续检查在前置检查完成前不显示，完成后才出现。"""
        self.assertNotIn("examine_hymen", self.rows(set()))
        self.assertNotIn(
            "examine_hymen", self.rows({"examine_vulva_and_shape"})
        )
        self.assertIn("examine_hymen", self.rows(FOLDS))

    def test_numbers_count_hidden_rows(self) -> None:
        """验证检查行序号按全量配置顺序计数，包含隐藏项目。"""
        checks = [
            b for b, d in game_config.config_behavior.items() if "检查" in d.tag
        ]
        rows = self.rows(set())
        self.assertLess(len(rows), len(checks))
        for behavior_id, row in rows.items():
            with self.subTest(behavior_id):
                self.assertEqual(row.number, checks.index(behavior_id) + 1)
                name = game_config.config_behavior[behavior_id].name
                self.assertEqual(row.label, f"[{row.number:02}]：{name}")

    def test_organ_checks_need_the_organ(self) -> None:
        """验证特殊部位检查仅在目标具备对应素质时出现。"""
        self.assertNotIn("examine_tail", self.rows(set()))
        abilities.talent(NPC)[113] = 1
        self.assertIn("examine_tail", self.rows(set()))
        self.assertIn("examine_tail_flexibility", self.rows({"examine_tail"}))

    def test_done_and_virginity_notes_disable_rows(self) -> None:
        """验证已完成、未初吻与未破处提示会禁用对应检查项，素质清除后恢复可选。"""
        abilities.ability(0)[svc.MEDICINE] = 3
        talent = abilities.talent(NPC)
        done = {"examine_hair", "examine_oral", *CHAINS}
        hair = self.rows(done)["examine_hair"]
        self.assertTrue(hair.label.endswith("(已检查)"))
        self.assertFalse(hair.enabled)
        gated = {
            4: {"examine_sucking_and_swallowing": "(未初吻)"},
            0: {
                "examine_orifice": "(未破处)",
                "examine_vagina_firmness": "(未破处)",
            },
            1: {"examine_intestine_firmness": "(未破处)"},
            2: {"examine_urethra_firmness": "(未破处)"},
        }
        checks = {b for notes in gated.values() for b in notes}
        for talent_id, notes in gated.items():
            with self.subTest(talent_id):
                talent[talent_id] = 1
                rows = self.rows(done)
                talent[talent_id] = 0
                for behavior_id in checks:
                    row = rows[behavior_id]
                    note = notes.get(behavior_id)
                    self.assertEqual(row.enabled, note is None)
                    if note is not None:
                        self.assertTrue(row.label.endswith(note))
                self.assertTrue(rows["examine_breast"].enabled)

    def test_hymen_needs_virgin_or_first_sex_today(self) -> None:
        """验证处女膜检查在非当日破处时禁用，在当日破处时可选。"""
        abilities.ability(0)[svc.MEDICINE] = 3
        self.lose_virginity(game_time.now().replace(year=2000))
        hymen = self.rows(FOLDS)["examine_hymen"]
        self.assertTrue(hymen.label.endswith("(需要是处女或者今日刚破处)"))
        self.assertFalse(hymen.enabled)
        self.lose_virginity(game_time.now())
        self.assertTrue(self.rows(FOLDS)["examine_hymen"].enabled)

    def test_quota_disables_every_row(self) -> None:
        """验证达到医术等级决定的检查次数上限后所有检查项禁用，提升医术等级后恢复可选。"""
        done = {
            "examine_hair",
            "examine_oral",
            "examine_armpit",
            "examine_foot",
        }
        self.assertEqual(svc.check_quota(done), (4, 4))
        self.assertFalse(any(row.enabled for row in self.rows(done).values()))
        abilities.ability(0)[svc.MEDICINE] = 1
        self.assertEqual(svc.check_quota(done), (4, 8))
        self.assertTrue(self.rows(done)["examine_breast"].enabled)

    def test_test_checks_are_harassment(self) -> None:
        """验证标签含「测试」的检查项将 harassment 标记为 True。"""
        rows = self.rows({"examine_hair"})
        self.assertTrue(rows["examine_hair_smoothness"].harassment)
        self.assertFalse(rows["examine_hair"].harassment)


class ExamRecordTest(ExamCase):
    """检查记录、成就结算、体检结束与报告计数测试。"""

    def test_today_wins_over_the_running_exam(self) -> None:
        """验证 done_checks 在存在今日记录时优先返回今日记录。"""
        self.assertEqual(svc.done_checks(NPC), set())
        physical_exam.record_check(NPC, "examine_hair")
        self.assertEqual(svc.done_checks(NPC), {"examine_hair"})
        physical_exam.finish(NPC, {"examine_oral"})
        physical_exam.record_check(NPC, "examine_foot")
        self.assertEqual(svc.done_checks(NPC), {"examine_oral"})

    def test_record_check_counts_and_settles(self) -> None:
        """验证 record_check 写入进行中检查、累加计数并结算体检成就。"""
        self.assertEqual(svc.record_check(NPC, "examine_hair"), [1041])
        self.assertEqual(svc.record_check(NPC, "examine_oral"), [])
        self.assertEqual(achievement.get("health_check_count"), 2)
        self.assertEqual(
            physical_exam.checks(physical_exam.IN_PROGRESS),
            {NPC: {"examine_hair", "examine_oral"}},
        )

    def test_hymen_on_first_sex_day_settles_its_badge(self) -> None:
        """验证当日破处后执行 examine_hymen 会结算成就 1046。"""
        self.lose_virginity(game_time.now())
        self.assertEqual(svc.record_check(NPC, "examine_hair"), [1041])
        self.assertEqual(svc.record_check(NPC, "examine_hymen"), [1046])

    def test_finish_moves_the_exam_to_today(self) -> None:
        """验证 finish_exam 将进行中检查转入今日记录、更新名单并清零今日时段。"""
        action_info.set(NPC, "health_check_today", 30)
        physical_exam.add(physical_exam.WAITING, NPC)
        svc.finish_exam(NPC, {"examine_hair"})
        self.assertEqual(
            physical_exam.checks(physical_exam.TODAY), {NPC: {"examine_hair"}}
        )
        self.assertEqual(physical_exam.checks(physical_exam.IN_PROGRESS), {})
        self.assertTrue(physical_exam.has(physical_exam.EXAMINED, NPC))
        self.assertFalse(physical_exam.has(physical_exam.WAITING, NPC))
        self.assertEqual(action_info.get(NPC, "health_check_today"), 0)

    def test_finish_without_checks_writes_nothing(self) -> None:
        """验证 done 为空时调用 finish_exam 不产生任何状态写入。"""
        with working.based_on(core.state()) as buffer:
            svc.finish_exam(NPC, set())
            self.assertEqual(buffer.effects(), ())

    def test_report_view_counts_the_operator(self) -> None:
        """验证 record_report 追加受检角色编号并结算体检报告成就。"""
        self.assertEqual(svc.record_report(NPC), [1051])
        self.assertEqual(achievement.get("body_report_chara_count_list"), [NPC])


class ScheduleTest(ExamCase):
    """体检日程配置、选项切换、人数上限与候选名单测试。"""

    def test_rows_stop_while_regular_exams_are_off(self) -> None:
        """验证定期体检关闭时只返回前两项设置并补写默认值 0，开启后返回全部设置。"""
        rows = svc.setting_rows()
        self.assertEqual([row.setting_id for row in rows], [1, 2])
        self.assertEqual(physical_exam.settings(), {1: 0, 2: 0})
        self.assertEqual(rows[1].option_count, 2)
        physical_exam.set_setting(2, 1)
        ids = [row.setting_id for row in svc.setting_rows()]
        self.assertEqual(ids, sorted(game_config.config_physical_exam_setting))

    def test_roster_and_day_counts_follow_their_option(self) -> None:
        """验证手动名单人数与手动体检日天数仅在对应选项选中时非空。"""
        physical_exam.set_setting(2, 1)
        svc.toggle_chosen(NPC)
        physical_exam.toggle_week_day(3)
        rows = {row.setting_id: row for row in svc.setting_rows()}
        self.assertEqual((rows[4].roster_size, rows[7].day_count), (None, None))
        physical_exam.set_setting(4, 2)
        physical_exam.set_setting(7, 1)
        rows = {row.setting_id: row for row in svc.setting_rows()}
        self.assertEqual((rows[4].roster_size, rows[7].day_count), (1, 1))
        options = game_config.config_physical_exam_setting_option[4]
        self.assertEqual(rows[4].option, options[2])
        svc.toggle_chosen(NPC)
        self.assertEqual(physical_exam.ids(physical_exam.CHOSEN), set())

    def test_cycle_wraps_to_the_first_option(self) -> None:
        """验证 cycle_setting 递增选项并在超过末项后回绕到 0。"""
        physical_exam.set_setting(3, 2)
        svc.cycle_setting(3, 4)
        self.assertEqual(physical_exam.setting(3), 3)
        svc.cycle_setting(3, 4)
        self.assertEqual(physical_exam.setting(3), 0)

    def test_daily_count_takes_digits_and_clamps(self) -> None:
        """验证 set_daily_count 忽略非法文本并将数字减 1 后限制在 0 到 9。"""
        physical_exam.set_setting(svc.DAILY_COUNT, 4)
        for text, expected in (("", 4), ("abc", 4), ("-3", 4), ("0", 0)):
            with self.subTest(text):
                svc.set_daily_count(text)
                self.assertEqual(
                    physical_exam.setting(svc.DAILY_COUNT), expected
                )
        for text, expected in (("1", 0), ("7", 6), ("10", 9), ("25", 9)):
            with self.subTest(text):
                svc.set_daily_count(text)
                self.assertEqual(
                    physical_exam.setting(svc.DAILY_COUNT), expected
                )

    def test_candidates_skip_the_player(self) -> None:
        """验证 exam_candidates 排除主角及处于监禁等异常状态的干员。"""
        self.world.chara(2, "干员乙")
        self.assertEqual(svc.exam_candidates(), [NPC, 2])
        flags.set(2, imprisonment=1)
        self.assertEqual(svc.exam_candidates(), [NPC])


class ReportTest(ExamCase):
    """体检报告内容拼接与只读性测试。"""

    def test_report_lists_profile_checks_and_examiner(self) -> None:
        """验证体检报告包含基础档案、已完成检查评价、默认体质、感染状态与落款。"""
        abilities.ability(NPC)[0] = 8
        text = report.report_text(NPC, {"examine_breast"}, "博士")
        self.assertTrue(text.startswith("\n基础档案：\n 【代号】干员\n"))
        self.assertIn(" 【胸部敏感】卓越\n", text)
        self.assertNotIn("【阴蒂敏感】", text)
        self.assertIn(" 【特殊体质】无\n", text)
        self.assertIn(" 【催眠程度】0%\n", text)
        self.assertIn("\n  参照医学检测报告，确认为非感染者。\n", text)
        self.assertIn("\n检查人：Dr.博士\n", text)
        date = game_time.get_date_until_day()[3:]
        self.assertTrue(text.endswith(f"检查日期：{date}\n"))

    def test_report_tells_kept_and_lost_firsts(self) -> None:
        """验证体检报告正确区分保有与已失去的初吻及处女履历。"""
        talent = abilities.talent(NPC)
        talent[1] = talent[4] = 1
        self.lose_virginity(game_time.now())
        text = report.report_text(NPC, set(), "博士")
        self.assertIn(" 【初吻】保有初吻\n", text)
        self.assertIn(" 【肛门处女】保有后庭处女\n", text)
        date = game_time.get_date_until_day(game_time.now())[3:]
        place = attr_text.get_scene_path_text(DEFAULT_SCENE)
        lost = f"于{date}在{place}，被博士博士以体位夺走了处女\n"
        self.assertIn(f" 【处女】{lost}", text)

    def test_report_names_the_hypnosis_talent(self) -> None:
        """验证角色持有催眠素质时报告在催眠程度前显示对应素质名称。"""
        abilities.talent(NPC)[72] = 1
        hypnosis.set(NPC, hypnosis_degree=50)
        name = game_config.config_talent[72].name
        text = report.report_text(NPC, set(), "博士")
        self.assertIn(f" 【催眠程度】 {name} （50%）\n", text)

    def test_report_reads_no_state_it_writes(self) -> None:
        """验证生成体检报告期间不产生任何状态写入副作用。"""
        with working.based_on(core.state()) as buffer:
            report.report_text(NPC, {"examine_breast", "examine_anus"}, "博士")
            self.assertEqual(buffer.effects(), ())


class UiFreeRunTest(FastTestCase):
    """体检服务与体检报告的无界面子进程隔离测试。"""

    child: ChildRun
    out: dict
    error: str

    @classmethod
    def setUpClass(cls) -> None:
        """
        通过 run_ui_free 在隔离子进程运行体检与日程脚本并缓存结果。
        捕获 RuntimeError 时将错误文本存入 error 并置为空的 ChildRun。
        """
        cls.error = ""
        try:
            cls.child = run_ui_free(UI_FREE_RUN, boot=True)
        except RuntimeError as error:
            cls.error = str(error)
            cls.child = ChildRun({}, [], [])
        cls.out = cls.child.payload

    def test_no_ui_or_settle_loaded(self) -> None:
        """验证隔离子进程无错误退出，且运行期间未加载也未尝试导入受限界面或结算模块。"""
        self.assertEqual(self.error, "")
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_exam_flow_results(self) -> None:
        """验证隔离运行中的检查行、记录、报告文本与结束结算结果正确。"""
        out = self.out
        self.assertFalse(any(enabled for _, enabled in out["rows"]))
        self.assertEqual((out["record"], out["hymen"]), ([1041], [1046]))
        self.assertEqual(out["done"], ["examine_hair", "examine_hymen"])
        self.assertIn("的阴茎献上了初吻", out["report"])
        self.assertIn("夺走了处女", out["report"])
        self.assertNotIn("当前受精概率", out["report"])
        self.assertIn("当前受精概率", out["plain"])
        self.assertIn(" 【特殊体质】无\n", out["plain"])
        self.assertTrue(
            out["hymen_row"][0].endswith("(需要是处女或者今日刚破处)")
        )
        self.assertEqual(out["report_ids"], [1051])
        self.assertEqual(out["today"], ["examine_hair", "examine_hymen"])

    def test_schedule_results(self) -> None:
        """验证隔离运行中的日程设置行、设置存储值与候选名单结果正确。"""
        out = self.out
        self.assertEqual(out["closed"], [1, 2])
        open_rows = {row[0]: row[1:] for row in out["open"]}
        self.assertEqual((open_rows[4], open_rows[7]), ([1, None], [None, 0]))
        self.assertEqual(
            out["settings"],
            {"1": 0, "2": 1, "3": 1, "4": 2, "5": 0, "6": 9, "7": 1},
        )
        self.assertEqual(out["candidates"], [1])
