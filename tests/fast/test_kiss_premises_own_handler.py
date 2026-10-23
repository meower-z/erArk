# -*- coding: UTF-8 -*-
"""
亲吻经验前提与初吻前提各按自己的定义判定
========================================
四个前提的定义：
    Premise.KISS_0                -- 自身亲吻经验（experience[40]）==0
    Premise.TARGET_KISS_0         -- 交互对象亲吻经验==0
    Premise.NO_FIRST_KISS         -- 玩家未保有初吻（玩家 talent[4]==0）
    Premise.TARGET_NO_FIRST_KISS  -- 交互对象未保有初吻（交互对象 talent[4]==0）
口上与事件的前提列写的是前提id字符串 kiss_0 / t_kiss_0，它们按初吻前提判定。
本测试遍历玩家与一名NPC的亲吻经验、初吻的全部组合，分别以玩家（交互对象为NPC）和NPC（交互对象为玩家）为判定角色，
经口上判定用的 get_weight_from_premise_dict 求值，结果必须处处等于定义。
"""

import itertools

from Script.Core import constant_promise
from Script.Design import handle_premise
from tests.fast.base import FastTestCase

Premise = constant_promise.Premise

KISS_EXPERIENCE = 40
""" 亲吻经验的经验id """
FIRST_KISS = 4
""" 「保有初吻」的素质id """


def self_kiss_experience_0(self_data, target_data, player_data) -> bool:
  """自身亲吻经验==0"""
  return self_data.experience[KISS_EXPERIENCE] == 0


def target_kiss_experience_0(self_data, target_data, player_data) -> bool:
  """交互对象亲吻经验==0"""
  return target_data.experience[KISS_EXPERIENCE] == 0


def player_no_first_kiss(self_data, target_data, player_data) -> bool:
  """玩家未保有初吻"""
  return player_data.talent[FIRST_KISS] == 0


def target_no_first_kiss(self_data, target_data, player_data) -> bool:
  """交互对象未保有初吻"""
  return target_data.talent[FIRST_KISS] == 0


CASES = [
    ("Premise.KISS_0", Premise.KISS_0, self_kiss_experience_0),
    ("Premise.TARGET_KISS_0", Premise.TARGET_KISS_0, target_kiss_experience_0),
    ("Premise.NO_FIRST_KISS", Premise.NO_FIRST_KISS, player_no_first_kiss),
    (
        "Premise.TARGET_NO_FIRST_KISS",
        Premise.TARGET_NO_FIRST_KISS,
        target_no_first_kiss,
    ),
    ("数据里的 kiss_0", "kiss_0", player_no_first_kiss),
    ("数据里的 t_kiss_0", "t_kiss_0", target_no_first_kiss),
]
""" (名称, 前提id, 定义) 列表：定义的参数为判定角色、其交互对象、玩家的角色数据 """


class KissPremisesOwnHandlerTest(FastTestCase):
  """四个亲吻相关前提及数据里的 kiss_0 / t_kiss_0 在亲吻经验与初吻的全部组合下都等于定义"""

  def test_every_state_matches_definition(self):
    """玩家与NPC的亲吻经验各取0、3，初吻各取保有、未保有，两名角色各判定一次"""
    player = self.world.chara(0, "玩家")
    npc = self.world.chara(1)
    player.target_character_id = 1
    npc.target_character_id = 0
    for p_exp, n_exp, p_kiss, n_kiss in itertools.product(
        (0, 3), (0, 3), (0, 1), (0, 1)
    ):
      player.experience[KISS_EXPERIENCE] = p_exp
      npc.experience[KISS_EXPERIENCE] = n_exp
      player.talent[FIRST_KISS] = p_kiss
      npc.talent[FIRST_KISS] = n_kiss
      for character_id, (name, premise, expect) in itertools.product(
          (0, 1), CASES
      ):
        self_data = self.cache.character_data[character_id]
        target_data = self.cache.character_data[self_data.target_character_id]
        with self.subTest(
            player_exp=p_exp,
            npc_exp=n_exp,
            player_first_kiss=p_kiss,
            npc_first_kiss=n_kiss,
            character_id=character_id,
            premise=name,
        ):
          weight, _ = handle_premise.get_weight_from_premise_dict(
              {premise}, character_id, {}
          )
          self.assertEqual(bool(weight), expect(self_data, target_data, player))
