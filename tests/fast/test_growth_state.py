# -*- coding: UTF-8 -*-
"""
养成状态、版本 18 编解码、草稿回放、静态自检与缓冲区写保护
==========================================================
- 养成（growth.child）：惰性创建、全部 25 项字段存取、可重入 editing、边界与旧存档导入。
- 版本 18 与 kernel_state 编解码往返、选行动草稿回放、静态自检与缓冲区外写保护。
"""

from Script.Config import game_config
from Script.Core import game_type
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import growth, pregnancy, roster
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import kernel_state, upgrade
from Script.System.Education_System import growth_handle
from Script.Test.Static_Check.check_registry import get_all_checks
from tests.fast.base import FastTestCase


class GrowthStateTest(FastTestCase):
    """养成数据的惰性创建、全字段编解码、可重入 editing、边界与旧存档导入"""

    def setUp(self) -> None:
        """放入玩家与干员，打开基于当前状态的缓冲区"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.world.chara(2, "干员乙")
        self.enterContext(working.based_on(core.state()))

    def test_lazy_creation_and_legacy_apis_removed(self) -> None:
        """Character 不再持有 child_growth，growth_handle 不再有 get_child_growth，只读不写"""
        self.assertFalse(hasattr(game_type.Character(), "child_growth"))
        self.assertFalse(hasattr(growth_handle, "get_child_growth"))
        self.assertFalse(growth.has(1))
        self.assertIsNone(growth.of(1))
        self.assertFalse(growth.has(1))
        with growth.editing(1, create=False) as none_g:
            self.assertIsNone(none_g)
        self.assertFalse(growth.has(1))

    def test_full_fields_reentrant_editing_and_copy(self) -> None:
        """全部 25 项字段存取、可重入 editing、副本隔离与 copy_character"""
        now = game_time.now()
        with growth.editing(1) as outer:
            assert outer is not None
            outer.personality_point = {0: 2.5, 3: -1.0}
            outer.prenatal_point = 5.0
            outer.care_point = 12.5
            outer.selected_course = {0: {1: [0, "理论教室一"], 2: [4, 152]}}
            outer.attend_class_count = 10
            outer.absent_count = 2
            outer.last_absent_period = [now.toordinal(), 3]
            outer.last_attend_period = [now.toordinal(), 1]
            outer.skip_count = 1
            outer.skip_caught_day = now.toordinal()
            outer.sex_class_count = 1
            outer.event_history = {"通用1": {"time": now, "choice": 0}}
            outer.show_off_ability = {41: 3}
            outer.report_card_flag = True
            outer.skip_class_flag = True
            outer.skip_class_day = now.toordinal()
            outer.schedule_template_id = 2
            outer.schedule_override = {0: 152}
            outer.follow_mother_flag = True
            outer.semester_id = [2020, 12]
            outer.semester_base_attend = 4
            outer.semester_base_absent = 1
            outer.semester_base_ability = {41: 1, 42: 2}
            outer.semester_base_work_type = 152
            outer.report_card_history = [
                {
                    "year": 2020,
                    "month": 9,
                    "attend": 6,
                    "absent": 1,
                    "rate": 85,
                    "level_change": {41: [0, 1]},
                    "top_ability": 41,
                    "top_level": 1,
                    "grade": 2,
                    "reason": "",
                }
            ]
            with growth.editing(1) as inner:
                self.assertIs(inner, outer)
                assert inner is not None
                inner.attend_class_count = 11

        self.assertTrue(growth.has(1))
        got = growth.of(1)
        assert got is not None
        self.assertEqual(got.attend_class_count, 11)
        self.assertEqual(got.personality_point, {0: 2.5, 3: -1.0})
        self.assertEqual(got.selected_course[0][1], [0, "理论教室一"])
        self.assertEqual(got.event_history["通用1"]["time"], now)
        self.assertEqual(
            got.report_card_history[0]["level_change"], {41: [0, 1]}
        )

        got.selected_course[0][1][1] = "篡改"
        refetched = growth.of(1)
        assert refetched is not None
        self.assertEqual(refetched.selected_course[0][1][1], "理论教室一")

        growth.copy_character(1, 2)
        copied = growth.of(2)
        assert copied is not None
        self.assertEqual(copied.attend_class_count, 11)
        self.assertEqual(
            copied.report_card_history[0]["level_change"], {41: [0, 1]}
        )

    def test_invariants_and_adopt_old_save(self) -> None:
        """非法负数计数被拒绝；旧存档回填缺字段、并入旧成绩单、迁移事件 uid 并删掉属性"""
        for attr, val in (
            ("attend_class_count", -1),
            ("absent_count", -1),
            ("skip_count", -1),
            ("sex_class_count", -1),
            ("care_point", -1.0),
            ("prenatal_point", -0.5),
        ):
            bad = game_type.CHILD_GROWTH()
            setattr(bad, attr, val)
            with self.assertRaises(ValueError):
                growth.put(1, bad)

        legacy_g = game_type.CHILD_GROWTH()
        delattr(legacy_g, "sex_class_count")
        delattr(legacy_g, "skip_class_day")
        vars(legacy_g)["last_report_card"] = {
            "year": 2020,
            "month": 6,
            "grade": 1,
        }
        legacy_g.event_history = {
            "萝莉1": {"time": game_time.now(), "choice": 1}
        }
        npc = self.cache.character_data[1]
        vars(npc)["child_growth"] = legacy_g
        growth.adopt_old_save({"character_data": {1: npc}}, 15)
        self.assertFalse(hasattr(npc, "child_growth"))
        got = growth.of(1)
        assert got is not None
        self.assertEqual(got.sex_class_count, 0)
        self.assertEqual(got.skip_class_day, 0)
        self.assertEqual(
            got.report_card_history, [{"year": 2020, "month": 6, "grade": 1}]
        )
        self.assertIn("期末17", got.event_history)


class CodecPickAndChecksTest(FastTestCase):
    """版本 18、kernel_state 编解码、选行动草稿回放与静态自检"""

    def setUp(self) -> None:
        """放入玩家与干员"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")

    def flagged(self, check_id: str) -> bool:
        """运行一项静态自检"""
        _name, run = get_all_checks()[check_id]
        return bool(run())

    def test_version_18_and_codec_round_trip(self) -> None:
        """存档版本为 18，名册、妊娠与养成经 kernel_state 编解码往返一致"""
        self.assertEqual(upgrade.CURRENT, 18)
        self.assertIn(17, upgrade.STEPS)
        now = game_time.now()
        with working.based_on(core.state()) as buf:
            roster.set_active([1])
            roster.set_forbidden([99])
            roster.set_names(["干员甲"])
            pregnancy.set_milk_max(1, 240)
            with pregnancy.editing(1) as p:
                p.reproduction_period = 5
                p.fertilization_time = now
            with growth.editing(1) as g:
                assert g is not None
                g.attend_class_count = 5
                g.selected_course = {0: {0: [0, "理论教室一"]}}
            effects = buf.effects()
        state = core.preview(core.state(), effects)
        encoded = kernel_state.encode(state, "tok")
        self.assertEqual(encoded["version"], 18)
        decoded = kernel_state.decode(encoded, tagged=True)
        self.assertEqual(roster.active_sorted(decoded), (1,))
        self.assertEqual(roster.forbidden(decoded), {99})
        self.assertEqual(roster.names(decoded), {"干员甲"})
        self.assertEqual(pregnancy.milk_max(1, decoded), 240)
        self.assertEqual(pregnancy.of(1, decoded).reproduction_period, 5)
        self.assertEqual(pregnancy.of(1, decoded).fertilization_time, now)
        got_g = growth.of(1, decoded)
        assert got_g is not None
        self.assertEqual(got_g.attend_class_count, 5)
        self.assertEqual(got_g.selected_course, {0: {0: [0, "理论教室一"]}})

    def test_pick_buffer_carries_and_replays(self) -> None:
        """玩家选择缓冲区里的名册、妊娠与养成写入可随行动带出并回放"""
        buf = working.open_pick()
        roster.forbid(77)
        pregnancy.update(1, reproduction_period=3)
        with growth.editing(1) as g:
            assert g is not None
            g.care_point = 4.5
        carried = working.close_pick(buf)
        self.assertEqual(len(carried), 3)
        with working.based_on(core.state()) as replay_buf:
            working.replay(carried)
            effects = replay_buf.effects()
        after = core.preview(core.state(), effects)
        self.assertTrue(roster.is_forbidden(77, after))
        self.assertEqual(pregnancy.of(1, after).reproduction_period, 3)
        got_g = growth.of(1, after)
        assert got_g is not None
        self.assertEqual(got_g.care_point, 4.5)

    def test_static_checks_read_new_domains(self) -> None:
        """CORE-01、ROSTER-01、BODY-21/26/27 与 EDU-01/03/04/11 读新领域键"""
        with working.based_on(core.state()):
            roster.set_active([1])
            self.assertFalse(self.flagged("CORE-01"))
            self.assertFalse(self.flagged("ROSTER-01"))
            self.assertFalse(self.flagged("BODY-21"))
            self.assertFalse(self.flagged("BODY-26"))
            self.assertFalse(self.flagged("BODY-27"))
            self.assertFalse(self.flagged("EDU-01"))
            self.assertFalse(self.flagged("EDU-03"))
            self.assertFalse(self.flagged("EDU-04"))
            self.assertFalse(self.flagged("EDU-11"))

            roster.add(999999)
            self.assertTrue(self.flagged("CORE-01"))
            self.assertTrue(self.flagged("ROSTER-01"))
            roster.discard(999999)

            bad_period = max(game_config.config_reproduction_period) + 10
            pregnancy.update(
                1, reproduction_period=bad_period, lactation_flag=True
            )
            self.assertTrue(self.flagged("BODY-21"))
            self.assertTrue(self.flagged("BODY-27"))

            with growth.editing(1) as g:
                assert g is not None
                g.schedule_template_id = 999
                g.skip_count = 5
                g.absent_count = 2
            self.assertTrue(self.flagged("EDU-04"))
            self.assertTrue(self.flagged("EDU-11"))


class WriteOutsideBufferTest(FastTestCase):
    """缓冲区之外写入新领域键会报 RuntimeError"""

    def test_writes_outside_buffer_raise(self) -> None:
        """未打开 working 缓冲区时写名册、妊娠与养成均报 RuntimeError"""
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        with self.assertRaises(RuntimeError):
            roster.add(99)
        with self.assertRaises(RuntimeError):
            roster.discard(1)
        with self.assertRaises(RuntimeError):
            roster.forbid(1)
        with self.assertRaises(RuntimeError):
            roster.add_name("干员甲")
        with self.assertRaises(RuntimeError):
            pregnancy.update(1, reproduction_period=2)
        with self.assertRaises(RuntimeError):
            with growth.editing(1) as g:
                assert g is not None
                g.attend_class_count = 1
