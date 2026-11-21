# -*- coding: UTF-8 -*-
"""
基地教育区状态（base.class_schedule、base.temp_sex_class、base.child_schedule_template）
=======================================================================================
- 读写：课表格子增删并清理空表、临时课程存取与批量清理、日程模板读写与时段清理。
- 模板只读不写：未写入模板时读预设不改状态，写入操作才落盘。
- 读档：旧存档三项属性导入内核状态并从对象上删掉；当前版本无属性时状态不变；类型不符按缺项计数。
- 编解码：三个键经 kernel_state 往返后不变。
- 自检：EDU-08、EDU-10、EDU-11 在合法与违规状态下的结果。
"""

from types import SimpleNamespace

from Script.Config import game_config
from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.domains import education
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import kernel_state, upgrade
from Script.System.Education_System import schedule_template_handle
from Script.Test.Static_Check.check_registry import get_all_checks
from tests.fast.base import FastTestCase


class EducationStateTest(FastTestCase):
    """教育区三项数据在内核状态里的读写、旧存档导入、编解码与自检"""

    def setUp(self) -> None:
        """放入玩家并打开基于当前状态的缓冲区"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员1")
        self.enterContext(working.based_on(core.state()))

    def flagged(self, check_id: str) -> bool:
        """
        运行一项静态自检
        Keyword arguments:
        check_id -- 检查编号
        Return arguments:
        bool -- 检出问题时为 True
        """
        _name, run = get_all_checks()[check_id]
        return bool(run())

    def test_class_schedule_crud_and_prune(self) -> None:
        """写入、读取与清空课表格子，空星期与空教室自动裁掉"""
        self.assertEqual(education.class_schedule(), {})
        self.assertIsNone(education.class_cell("理论教室一", 0, 1))
        education.set_class_cell("理论教室一", 0, 1, 45, 1)
        self.assertEqual(education.class_cell("理论教室一", 0, 1), [45, 1])
        self.assertEqual(
            education.class_schedule(),
            {"理论教室一": {0: {1: [45, 1]}}},
        )
        education.clear_class_cell("理论教室一", 0, 1)
        self.assertIsNone(education.class_cell("理论教室一", 0, 1))
        self.assertEqual(education.class_schedule(), {})

    def test_temp_class_crud_and_drop(self) -> None:
        """临时课程的写入、读取副本、移除成员与批量删键"""
        record = {
            "classroom": "实践教室一",
            "ability_id": 42,
            "must_attend": [1, 2],
            "notified": [False, False, False],
            "running": False,
            "reserved": False,
        }
        stored = education.put_temp_class("739510-2", record)
        self.assertEqual(stored["classroom"], "实践教室一")
        self.assertEqual(education.temp_class("739510-2"), record)
        removed = education.drop_must_attend({2})
        self.assertEqual(removed, 1)
        got = education.temp_class("739510-2")
        assert got is not None
        self.assertEqual(got["must_attend"], [1])
        self.assertEqual(
            education.delete_temp_classes(["739510-2", "missing"]), 1
        )
        self.assertEqual(education.temp_classes(), {})

    def test_templates_read_does_not_write_and_cleanup(self) -> None:
        """模板为空时读取预设不写内核状态，写入后可读且清理失效活动编号"""
        self.assertEqual(working.get(None, education.TEMPLATES), {})
        ids = schedule_template_handle.get_all_template_id()
        self.assertEqual(ids, [1, 2, 3, 4])
        self.assertEqual(working.get(None, education.TEMPLATES), {})

        invalid_ent = max(game_config.config_entertainment) + 100
        valid_ent = next(iter(game_config.config_entertainment))
        education.put_template(
            9,
            {"name": "测试模板", "slot": {0: valid_ent, 1: invalid_ent, 2: 0}},
        )
        cleared = education.clear_missing_template_slots(
            game_config.config_entertainment
        )
        self.assertEqual(cleared, 1)
        tpl = education.template(9)
        assert tpl is not None
        self.assertEqual(tpl["slot"], {0: valid_ent, 1: 0, 2: 0})
        self.assertTrue(education.delete_template(9))
        self.assertIsNone(education.template(9))

    def test_adopt_old_save_v0_and_current(self) -> None:
        """旧存档的三项属性导入内核状态并删掉，当前版本无属性时不变"""
        island = SimpleNamespace(
            class_schedule={"理论教室一": {1: {2: [45, 1]}}},
            temp_sex_class={
                "739510-1": {
                    "classroom": "实践教室一",
                    "ability_id": 42,
                    "must_attend": [1],
                    "notified": [True, False, False],
                    "running": False,
                    "reserved": True,
                }
            },
            child_schedule_template={
                1: {"name": "模板甲", "slot": {0: 0, 1: 0, 2: 0}}
            },
            other_field="keep",
        )
        missing = education.adopt_old_save({"rhodes_island": island}, 0)
        self.assertEqual(missing, 0)
        self.assertEqual(vars(island), {"other_field": "keep"})
        self.assertEqual(education.class_cell("理论教室一", 1, 2), [45, 1])
        got_temp = education.temp_class("739510-1")
        assert got_temp is not None
        self.assertEqual(got_temp["must_attend"], [1])
        self.assertEqual(
            education.template(1),
            {"name": "模板甲", "slot": {0: 0, 1: 0, 2: 0}},
        )

        before = tuple(working.get(None, k) for k in education.KEYS)
        current_missing = education.adopt_old_save(
            {"rhodes_island": SimpleNamespace()}, upgrade.CURRENT
        )
        self.assertEqual(current_missing, 0)
        self.assertEqual(
            tuple(working.get(None, k) for k in education.KEYS), before
        )

    def test_adopt_wrong_type_counts_missing(self) -> None:
        """旧存档属性类型不符时删掉并计入缺项"""
        island = SimpleNamespace(class_schedule=[], temp_sex_class=None)
        missing = education.adopt_old_save({"rhodes_island": island}, 0)
        self.assertEqual(missing, len(education.PICKLED_TYPES))
        self.assertEqual(vars(island), {})
        self.assertEqual(education.class_schedule(), {})

    def test_codec_round_trip(self) -> None:
        """三个键经存档编解码往返后一致"""
        with working.based_on(core.state()) as buf:
            education.set_class_cell("理论教室一", 2, 3, 45, -1)
            education.put_temp_class(
                "739510-4",
                {
                    "classroom": "实践教室一",
                    "ability_id": 42,
                    "must_attend": [1],
                    "notified": [False, True, False],
                    "running": False,
                    "reserved": False,
                },
            )
            education.put_template(
                5, {"name": "方案五", "slot": {0: 0, 1: 0, 2: 0}}
            )
            effects = buf.effects()
        state = core.preview(core.state(), effects)
        encoded = kernel_state.encode(state, "tok")
        decoded, _token = kernel_state.decode(encoded, upgrade.CURRENT)
        self.assertEqual(
            education.class_cell("理论教室一", 2, 3, decoded), [45, -1]
        )
        self.assertEqual(
            education.temp_class("739510-4", decoded),
            {
                "classroom": "实践教室一",
                "ability_id": 42,
                "must_attend": [1],
                "notified": [False, True, False],
                "running": False,
                "reserved": False,
            },
        )
        self.assertEqual(
            education.template(5, decoded),
            {"name": "方案五", "slot": {0: 0, 1: 0, 2: 0}},
        )

    def test_static_checks(self) -> None:
        """合法时三项自检通过，违规时各报对应检查"""
        valid_ability = next(iter(game_config.config_ability))
        valid_ent = next(iter(game_config.config_entertainment))
        education.set_class_cell("理论教室一", 0, 0, valid_ability, 1)
        education.put_template(
            1, {"name": "方案一", "slot": {0: valid_ent, 1: 0, 2: 0}}
        )
        self.assertFalse(self.flagged("EDU-08"))
        self.assertFalse(self.flagged("EDU-10"))
        self.assertFalse(self.flagged("EDU-11"))

        bad_ability = max(game_config.config_ability) + 100
        education.set_class_cell("理论教室一", 0, 0, bad_ability, 1)
        self.assertTrue(self.flagged("EDU-08"))
        education.set_class_cell("理论教室一", 0, 0, valid_ability, 1)

        bad_ent = max(game_config.config_entertainment) + 100
        education.put_template(1, {"name": "方案一", "slot": {0: bad_ent}})
        self.assertTrue(self.flagged("EDU-10"))
        education.put_template(1, {"name": "方案一", "slot": {0: valid_ent}})

        growth = game_type.CHILD_GROWTH()
        growth.schedule_template_id = 99
        self.cache.character_data[1].child_growth = growth
        self.assertTrue(self.flagged("EDU-11"))
