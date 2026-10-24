# -*- coding: UTF-8 -*-
"""
失去泌乳后涨奶罩杯缩回的回归测试
================================
干员涨奶（奶量超过上限的 80%）时罩杯变大一级并记下涨奶标记。
失去泌乳素质（停乳药、育儿结束）后的第一次结算把罩杯缩小一级、清除涨奶标记，之后罩杯保持不变。
断言都落在 handle_talent.npc_b_talent_change_for_lactation_flag（行为循环每轮经 gain_talent 调用它）结算后的罩杯素质与涨奶标记上。
"""

from Script.Design import handle_talent
from Script.UI.Panel import gift_panel
from tests.fast.base import FastTestCase

CUPS = [121, 122, 123, 124, 125]
""" 罩杯素质：绝壁、贫乳、普乳、巨乳、爆乳 """
LACTATION_DRUG, STOP_LACTATION_DRUG, SHRINK_CHEST_DRUG = 33, 34, 22
""" 泌乳药、停乳药、缩胸药的药物id """


class CupShrinksAfterLactationEndsTest(FastTestCase):
  """失去泌乳素质后，涨奶时变大的罩杯缩回一次并清除涨奶标记"""

  def setUp(self) -> None:
    """
    造博士
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    self.world.chara(0, "博士")

  def make(self, cid, cup):
    """
    造一个指定罩杯、没有泌乳的干员
    Keyword arguments:
    cid -- 角色id
    cup -- 罩杯素质id
    Return arguments:
    game_type.Character -- 角色对象
    """
    cd = self.world.chara(cid, f"干员{cid}")
    for talent_id in CUPS:
      cd.talent[talent_id] = 0
    cd.talent[cup] = 1
    cd.pregnancy.milk_max = 190
    return cd

  def engorge(self, cid, cup):
    """
    造一个指定罩杯的干员，用泌乳药并把奶量加满，跑一次结算使她涨奶
    Keyword arguments:
    cid -- 角色id
    cup -- 罩杯素质id
    Return arguments:
    game_type.Character -- 角色对象
    """
    cd = self.make(cid, cup)
    gift_panel.handle_drug_use_effect(cid, LACTATION_DRUG)
    cd.pregnancy.milk = 190
    self.settle(cid)
    return cd

  def settle(self, cid):
    """
    跑一次涨奶罩杯结算，返回结算后的罩杯与涨奶标记
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    tuple -- (罩杯素质id列表, 涨奶标记)
    """
    handle_talent.npc_b_talent_change_for_lactation_flag(cid)
    cd = self.cache.character_data[cid]
    return [t for t in CUPS if cd.talent[t]], cd.pregnancy.lactation_flag

  def test_stop_lactation_shrinks_cup_once(self) -> None:
    """涨奶后用停乳药：罩杯缩回涨奶前的大小，只缩一次"""
    cd = self.make(1, 122)
    gift_panel.handle_drug_use_effect(1, LACTATION_DRUG)
    cd.pregnancy.milk = 190
    self.assertEqual(self.settle(1), ([123], True))
    gift_panel.handle_drug_use_effect(1, STOP_LACTATION_DRUG)
    self.assertEqual(cd.talent[27], 0)
    self.assertEqual(self.settle(1), ([122], False))
    self.assertEqual(self.settle(1), ([122], False))

  def test_stuck_old_save_repaired_once(self) -> None:
    """旧存档里卡住的状态（没有泌乳素质、涨奶标记还在、奶量为 0）：第一次结算修复，只修一次"""
    cd = self.make(2, 123)
    cd.pregnancy.lactation_flag = True
    cd.pregnancy.milk = 0
    self.assertEqual(self.settle(2), ([122], False))
    self.assertEqual(self.settle(2), ([122], False))

  def test_largest_cup_unchanged(self) -> None:
    """罩杯已是爆乳时涨奶：没有变大也没有涨奶标记，停乳后保持爆乳"""
    cd = self.make(3, 125)
    gift_panel.handle_drug_use_effect(3, LACTATION_DRUG)
    cd.pregnancy.milk = 190
    self.assertEqual(self.settle(3), ([125], False))
    gift_panel.handle_drug_use_effect(3, STOP_LACTATION_DRUG)
    self.assertEqual(self.settle(3), ([125], False))

  def test_shrink_drug_during_engorgement(self) -> None:
    """涨奶期间用过缩胸药：停乳或奶量降到 79% 及以下后比涨奶前小一级，最小到绝壁"""
    self.engorge(4, 122)
    gift_panel.handle_drug_use_effect(4, SHRINK_CHEST_DRUG)
    self.assertEqual(self.settle(4), ([122], True))
    gift_panel.handle_drug_use_effect(4, STOP_LACTATION_DRUG)
    self.assertEqual(self.settle(4), ([121], False))

    cd = self.engorge(7, 122)
    gift_panel.handle_drug_use_effect(7, SHRINK_CHEST_DRUG)
    cd.pregnancy.milk = 100
    self.assertEqual(self.settle(7), ([121], False))

    self.engorge(8, 121)
    gift_panel.handle_drug_use_effect(8, SHRINK_CHEST_DRUG)
    gift_panel.handle_drug_use_effect(8, STOP_LACTATION_DRUG)
    self.assertEqual(self.settle(8), ([121], False))

  def test_unaffected_cases(self) -> None:
    """从没泌乳过的干员罩杯不变；还在涨奶的干员保持涨奶，奶量降到 79% 及以下时照旧缩回"""
    self.make(5, 122)
    self.assertEqual(self.settle(5), ([122], False))
    cd = self.engorge(6, 122)
    self.assertEqual(self.settle(6), ([123], True))
    cd.pregnancy.milk = 100
    self.assertEqual(self.settle(6), ([122], False))
