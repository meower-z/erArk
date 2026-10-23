# -*- coding: UTF-8 -*-
"""
成年的学员（素质103）不走只给儿童的分支
======================================
「交互对象是儿童」的前提 t_child_or_loli_1 只在交互对象是幼女（素质102）时成立：
博士对饥饿的女儿聊天时，挂着这条前提的通用聊天口上只在女儿是幼女时整条前提成立，女儿是学员时不成立。
整条前提用口上选句时的同一个函数（handle_premise.get_weight_from_premise_dict）求值。
成长停滞药与成长继续药（道具 40、41）对幼女与学员女儿都有效。
"""

from Script.Config import game_config
from Script.Core import constant_promise
from Script.Design import handle_premise
from Script.UI.Panel import gift_panel
from tests.fast.base import FastTestCase

CHILD = 102
""" 幼女素质 """
TRAINEE = 103
""" 学员素质 """
GROWTH_STOP_TALENT = 28
""" 成长停滞素质 """
GROWTH_STOP_DRUG = 40
""" 成长停滞药 """
GROWTH_RESUME_DRUG = 41
""" 成长继续药 """
HUNGRY_POINT = 230
""" 饥饿值：满值 240 的 80% 以上 """
PANEL_WIDTH = 100
""" 礼物面板的绘制宽度 """


class TraineeNotChildTest(FastTestCase):
  """学员不满足只给幼女的聊天口上的前提，成长药对幼女与学员都有效"""

  def setUp(self):
    """
    博士（id 0）与女儿（id 1）在同一场景，博士的交互对象是女儿，女儿饥饿
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    self.pl = self.world.chara(0, "博士")
    self.daughter = self.world.chara(1, "女儿")
    self.daughter.relationship.father_id = 0
    self.daughter.hunger_point = HUNGRY_POINT
    self.pl.target_character_id = 1

  def set_stage(self, talent_id: int):
    """
    把女儿的成长阶段素质换成 talent_id
    Keyword arguments:
    talent_id -- CHILD 或 TRAINEE
    Return arguments:
    无
    """
    for stage_id in (CHILD, TRAINEE):
      self.daughter.talent[stage_id] = 1 if stage_id == talent_id else 0

  def child_chat_talk(self) -> set:
    """
    前提里有 t_child_or_loli_1、博士此刻满足整条前提的通用聊天口上
    Keyword arguments:
    无
    Return arguments:
    set -- 口上id
    """
    talk_id_list = []
    for talk_id_list_by_version in game_config.config_talk_data_by_chara_adv[
        "chat"
    ][0].values():
      talk_id_list += talk_id_list_by_version
    return {
        talk_id
        for talk_id in talk_id_list
        if constant_promise.Premise.T_CHILD_OR_LOLI_1
        in game_config.config_talk_premise_data[talk_id]
        and handle_premise.get_weight_from_premise_dict(
            game_config.config_talk_premise_data[talk_id],
            0,
            {},
            weight_all_to_1_flag=True,
        )[0]
    }

  def test_child_chat_talk_only_for_child(self):
    """挂着 t_child_or_loli_1 的聊天口上：女儿是幼女时整条前提成立，是学员时不成立"""
    self.set_stage(CHILD)
    self.assertTrue(
        self.child_chat_talk(), "女儿是幼女时，这类口上的整条前提成立"
    )
    self.set_stage(TRAINEE)
    self.assertEqual(
        self.child_chat_talk(), set(), "女儿是学员时，这类口上的整条前提不成立"
    )

  def test_growth_stop_drugs_for_child_and_trainee(self):
    """幼女与学员女儿：没停滞时成长停滞药有效，停滞时成长继续药有效"""
    for talent_id in (CHILD, TRAINEE):
      self.set_stage(talent_id)
      for drug_id, stopped in (
          (GROWTH_STOP_DRUG, 0),
          (GROWTH_RESUME_DRUG, 1),
      ):
        with self.subTest(stage=talent_id, drug=drug_id):
          self.daughter.talent[GROWTH_STOP_TALENT] = stopped
          self.assertTrue(
              gift_panel.Gift_Panel(PANEL_WIDTH).is_drug_effective(
                  drug_id, self.daughter
              )
          )
