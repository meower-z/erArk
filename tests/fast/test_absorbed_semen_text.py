# -*- coding: UTF-8 -*-
"""
被吸收后的精液量带零头时，文字里只写整数
========================================
肠胃每分钟吸收 1/5 ml 起，腹部各处的精液量与累计吸收量都会带分数零头。
获得精液膨腹时记进特殊履历的腹部精液总量、履历面板里「肠胃一共吸收了」的量，都按向下取整写成整数 ml。
"""

from fractions import Fraction

from Script.Design import handle_talent
from Script.System.First_Record_System import first_record_panel
from tests.fast.base import FastTestCase
from tests import chara_abilities as ca, kernel_data

TALENT_CUMFLATION = 32
""" 素质：精液膨腹 """
SPECIAL_CUMFLATION = 6
""" 特殊履历：第一次获得精液膨腹 """


class AbsorbedSemenTextTest(FastTestCase):
    """带零头的精液量在文字里写成整数"""

    def setUp(self) -> None:
        """
        造玩家与一名干员，干员子宫里有 6000 又 2/5 ml 精液，肠胃累计吸收了 23 又 2/5 ml
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.chara = self.world.chara(1, "干员")
        self.chara.dirty.body_semen[7][1] = 6000 + Fraction(2, 5)
        self.chara.dirty.body_semen[15][3] = 10
        self.chara.dirty.absorbed_total_semen = Fraction(117, 5)

    def test_cumflation_record_is_whole(self) -> None:
        """获得精液膨腹时，特殊履历里记的是 6000ml"""
        ca.talent(self.chara)[TALENT_CUMFLATION] = 0
        kernel_data.written(handle_talent.npc_gain_and_lost_cumflation, 1)
        record = self.chara.first_record.first_special_record_dict.get(
            SPECIAL_CUMFLATION
        )
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record[2], "6000ml")

    def test_absorbed_amount_is_whole(self) -> None:
        """履历面板写「肠胃一共吸收了23ml精液」"""
        text = first_record_panel._build_fluid_text(1)
        self.assertIn("肠胃一共吸收了23ml精液", text)
        self.assertNotIn("/", text)
