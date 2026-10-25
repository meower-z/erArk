# -*- coding: UTF-8 -*-
"""
婴儿与幼女两个阶段离线的回归测试（前提部分）
============================================
婴儿（素质101）与幼女（素质102）都是离线阶段：异常位7（角色离线）为异常，学员（素质103）正常。
交互对象为玩家女儿的乱伦H指令（5204 邀请乱伦H、6003 结束乱伦H）对离线的女儿不可用。
指令 3004 一起玩耍、娱乐 151 过家家与 154 自由玩耍连同它们独有的行为都不存在。
幼女穿的胸衣与内裤只从童装里挑，攻略等级与情趣内衣收藏加成都满足时也不会挑到情趣内衣。
幼女不上学、不跟随母亲见学的部分在 tests/slow/test_child_no_class_no_follow_mother.py。
"""

from typing import TYPE_CHECKING
from unittest import mock

from Script.Config import game_config
from Script.Core import constant_promise
from Script.Design import attr_calculation, clothing, handle_premise
from tests.fast.base import FastTestCase

if TYPE_CHECKING:
  from Script.Core import game_type

BABY = 101
""" 婴儿素质 """
CHILD = 102
""" 幼女素质 """
TRAINEE = 103
""" 学员素质 """
DELETED_INSTRUCT_CID = 3004
""" 一起玩耍指令在 InstructConfig.csv 的 cid """
DELETED_ENTERTAINMENT_CID_LIST = (151, 154)
""" 过家家、自由玩耍两项娱乐在 Entertainment.csv 的 cid """
DELETED_BEHAVIOR_LIST = ("play_with_child", "free_play")
""" 只给一起玩耍指令与自由玩耍娱乐用的两个行为 """
UNDERWEAR_TYPE_LIST = (6, 9)
""" 胸衣与内裤的服装类型 """
H_UNDERWEAR_TAG = 2
""" 情趣内衣在服装表里的 tag """
H_UNDERWEAR_BONUS_ID = 102
""" 解锁情趣内衣的收藏加成编号 """
DAUGHTER_INSTRUCT_CID_LIST = (5204, 6003)
""" 交互对象为玩家女儿的乱伦H指令在 InstructConfig.csv 的 cid：5204 邀请乱伦H、6003 结束乱伦H """


def set_stage(character: "game_type.Character", talent_id: int) -> None:
  """
  把角色的成长阶段素质换成 talent_id
  Keyword arguments:
  character -- 角色对象
  talent_id -- 101 / 102 / 103 之一
  Return arguments:
  无
  """
  for stage_id in (BABY, CHILD, TRAINEE):
    character.talent[stage_id] = 1 if stage_id == talent_id else 0


class ChildStagesOfflineTest(FastTestCase):
  """婴儿与幼女离线，乱伦H指令对她们不可用"""

  def setUp(self) -> None:
    """
    博士（id 0）与女儿（id 1）在同一场景，博士的交互对象是女儿
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    self.pl = self.world.chara(0, "博士")
    self.daughter = self.world.chara(1, "女儿")
    self.daughter.relationship.father_id = 0
    self.daughter.target_character_id = 1
    self.pl.target_character_id = 1

  def test_child_stage_is_offline(self) -> None:
    """婴儿与幼女的异常位7为异常（离线），学员正常"""
    for talent_id, expected in ((BABY, 0), (CHILD, 0), (TRAINEE, 1)):
      with self.subTest(talent_id=talent_id):
        set_stage(self.daughter, talent_id)
        self.assertEqual(handle_premise.handle_normal_7(1), expected)

  def test_daughter_h_instruct_gated_offline(self) -> None:
    """
    两条乱伦H指令的前提里，都有一条在交互对象是婴儿或幼女时不成立、同一女儿换成学员时成立：
    这条前提挡住了离线的女儿，指令对她不可用
    """
    for cid in DAUGHTER_INSTRUCT_CID_LIST:
      premise_list = [
          getattr(constant_promise.Premise, name)
          for name in game_config.config_instruct[cid].premise_set.split("|")
      ]
      for talent_id in (BABY, CHILD):
        with self.subTest(cid=cid, talent_id=talent_id):
          set_stage(self.daughter, talent_id)
          offline_result = {
              premise: handle_premise.handle_premise(premise, 0)
              for premise in premise_list
          }
          set_stage(self.daughter, TRAINEE)
          online_result = {
              premise: handle_premise.handle_premise(premise, 0)
              for premise in premise_list
          }
          gate_list = [
              premise
              for premise in premise_list
              if not offline_result[premise] and online_result[premise]
          ]
          self.assertTrue(
              gate_list, f"指令 {cid} 没有挡住离线女儿的前提：{offline_result}"
          )

  def test_play_with_child_and_child_entertainments_deleted(self) -> None:
    """指令 3004、娱乐 151 与 154、行为 play_with_child 与 free_play 在配置里都不存在"""
    self.assertNotIn(DELETED_INSTRUCT_CID, game_config.config_instruct)
    self.assertNotIn("play_with_child", game_config.config_instruct_by_id)
    for cid in DELETED_ENTERTAINMENT_CID_LIST:
      with self.subTest(entertainment=cid):
        self.assertNotIn(cid, game_config.config_entertainment)
    for behavior in DELETED_BEHAVIOR_LIST:
      with self.subTest(behavior=behavior):
        self.assertNotIn(behavior, game_config.config_behavior)
        self.assertNotIn(behavior, game_config.config_behavior_effect_data)

  def test_child_underwear_never_h(self) -> None:
    """幼女攻略等级 2 以上、博士有情趣内衣收藏加成时，换 60 次胸衣与内裤都不挑到情趣内衣"""
    set_stage(self.daughter, CHILD)
    h_id_set = {
        cid
        for cid, cloth in game_config.config_clothing_tem.items()
        if cloth.clothing_type in UNDERWEAR_TYPE_LIST
        and cloth.tag == H_UNDERWEAR_TAG
        and cloth.npc in (0, self.daughter.adv)
    }
    self.assertTrue(h_id_set, "服装表里有情趣内衣")
    self.pl.pl_collection = attr_calculation.get_collection_zero()
    self.pl.pl_collection.collection_bonus[H_UNDERWEAR_BONUS_ID] = True
    picked = set()
    with mock.patch.object(
        attr_calculation, "get_character_fall_level", return_value=2
    ):
      for _ in range(60):
        for clothing_type in UNDERWEAR_TYPE_LIST:
          self.daughter.cloth.cloth_wear[clothing_type] = []
        clothing.get_underwear(1)
        for clothing_type in UNDERWEAR_TYPE_LIST:
          picked.update(self.daughter.cloth.cloth_wear[clothing_type])
    self.assertTrue(picked, "挑到了胸衣或内裤")
    self.assertFalse(picked & h_id_set, sorted(picked & h_id_set))
