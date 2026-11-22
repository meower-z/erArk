# -*- coding: UTF-8 -*-
"""
角色的催眠状态（mind.hypnosis）
==============================
- 默认零拷贝返回 DEFAULT；set 只存非默认项，roleplay 存成元组。
- reset 清空为默认并返回是否发生变动。
- adopt_old_save 搬走旧角色对象上的 hypnosis，并把旧版 int 型的 roleplay 修复为空并计 1 条更新。
"""

from unittest import mock

from Script.Core import game_type
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import hypnosis
from Script.Modules.gameplay_resolution import working
from Script.Settle import default as settle_default
from Script.UI.Panel import hypnosis_panel
from tests.fast.base import FastTestCase


class HypnosisTest(FastTestCase):
    """mind.hypnosis 领域的读写、重置与旧档导入"""

    def setUp(self) -> None:
        """载入内核模块并建出测试角色"""
        super().setUp()
        core.load(load_order.LOAD_ORDER)
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")

    def test_defaults_set_and_reset(self) -> None:
        """默认返回 DEFAULT；set 写入后 view 与 of 一致，reset 恢复默认"""
        self.assertIs(hypnosis.of(1), hypnosis.DEFAULT)
        with working.based_on(core.state()) as buf:
            hypnosis.set(
                1,
                hypnosis_degree=75,
                blockhead=True,
                roleplay=[2, 5],
                pain_as_pleasure=True,
            )
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        got = hypnosis.of(1, next_state)
        self.assertEqual(got["hypnosis_degree"], 75)
        self.assertTrue(got["blockhead"])
        self.assertEqual(got["roleplay"], (2, 5))
        self.assertTrue(got["pain_as_pleasure"])
        v = hypnosis.view(1, next_state)
        self.assertEqual(v.roleplay, [2, 5])
        self.assertEqual(v.hypnosis_degree, 75)
        with working.based_on(next_state) as buf2:
            self.assertTrue(hypnosis.reset(1))
            self.assertFalse(hypnosis.reset(1))
            effects2 = buf2.effects()
        cleared = core.preview(next_state, effects2)
        self.assertIs(hypnosis.of(1, cleared), hypnosis.DEFAULT)

    def test_adopt_old_save_fixes_int_roleplay(self) -> None:
        """旧档 roleplay 为 int 时归空并计 1 条更新，属性从对象上删除"""
        chara = game_type.Character()
        old = game_type.HYPNOSIS()
        old.hypnosis_degree = 50
        old.force_ovulation = True
        vars(old)["roleplay"] = 0
        vars(chara)["hypnosis"] = old
        with working.based_on(core.state()) as buf:
            count = hypnosis.adopt_old_save({"character_data": {1: chara}})
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertFalse(hasattr(chara, "hypnosis"))
        self.assertEqual(count, 1)
        got = hypnosis.of(1, next_state)
        self.assertEqual(got["hypnosis_degree"], 50)
        self.assertTrue(got["force_ovulation"])
        self.assertEqual(got["roleplay"], ())

    def test_degree_keeps_float_across_consecutive_settle_gains(self) -> None:
        """degree 保留小数催眠度，连续两次小数结算累加不丢小数"""
        self.world.cache.character_data[0].target_character_id = 1
        now = game_time.now()
        with (
            working.based_on(core.state()) as buf,
            mock.patch.object(
                hypnosis_panel, "calculate_hypnosis_sanity_cost", return_value=0
            ),
            mock.patch.object(
                hypnosis_panel,
                "hypnosis_degree_calculation",
                side_effect=[3.7, 2.4],
            ),
            mock.patch.object(
                hypnosis_panel,
                "hypnosis_degree_limit_calculation",
                return_value=100,
            ),
            mock.patch.object(hypnosis_panel, "evaluate_hypnosis_completion"),
        ):
            settle_default.handle_hypnosis_one(
                0, 5, game_type.CharacterStatusChange(), now
            )
            self.assertAlmostEqual(hypnosis.degree(1), 3.7)
            settle_default.handle_hypnosis_one(
                0, 5, game_type.CharacterStatusChange(), now
            )
            self.assertAlmostEqual(hypnosis.degree(1), 6.1)
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertAlmostEqual(hypnosis.degree(1, next_state), 6.1)
