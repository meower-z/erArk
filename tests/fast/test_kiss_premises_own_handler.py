# -*- coding: UTF-8 -*-
"""
亲吻经验前提和初吻前提的判定
============================
Premise.KISS_0 判定角色自身的亲吻经验（experience[40]）是否为0。
Premise.TARGET_KISS_0 判定交互对象的亲吻经验是否为0。
Premise.NO_FIRST_KISS 判定玩家是否未保有初吻（玩家的 talent[4] 为0）。
Premise.TARGET_NO_FIRST_KISS 判定交互对象是否未保有初吻（交互对象的 talent[4] 为0）。
口上和事件数据里的前提id kiss_0、t_kiss_0 分别按 NO_FIRST_KISS、TARGET_NO_FIRST_KISS 判定。
玩家和一名NPC互为交互对象。
两人的亲吻经验各取0或3，两人的 talent[4] 各取0或1，共16种组合。
每种组合下两人各作一次判定角色。
测试经 get_weight_from_premise_dict 求权重，权重是否非零须等于定义函数的结果。
"""

import itertools

from Script.Core import constant_promise
from Script.Design import handle_premise
from tests.fast.base import FastTestCase

Premise = constant_promise.Premise

KISS_EXPERIENCE = 40
""" Experience.csv 里接吻经验的id """
FIRST_KISS = 4
""" Talent.csv 里无接吻经验素质的id，值为0表示未保有初吻 """


def self_kiss_experience_0(self_data, target_data, player_data) -> bool:
  """
  Premise.KISS_0 的定义函数
  Keyword arguments:
  self_data -- 判定角色的数据（game_type.Character）
  target_data -- 交互对象的数据（game_type.Character）
  player_data -- 玩家的数据（game_type.Character）
  Return arguments:
  bool -- 判定角色的亲吻经验为0时为 True
  """
  return self_data.experience[KISS_EXPERIENCE] == 0


def target_kiss_experience_0(self_data, target_data, player_data) -> bool:
  """
  Premise.TARGET_KISS_0 的定义函数
  Keyword arguments:
  self_data -- 判定角色的数据（game_type.Character）
  target_data -- 交互对象的数据（game_type.Character）
  player_data -- 玩家的数据（game_type.Character）
  Return arguments:
  bool -- 交互对象的亲吻经验为0时为 True
  """
  return target_data.experience[KISS_EXPERIENCE] == 0


def player_no_first_kiss(self_data, target_data, player_data) -> bool:
  """
  Premise.NO_FIRST_KISS 和数据里 kiss_0 的定义函数
  Keyword arguments:
  self_data -- 判定角色的数据（game_type.Character）
  target_data -- 交互对象的数据（game_type.Character）
  player_data -- 玩家的数据（game_type.Character）
  Return arguments:
  bool -- 玩家未保有初吻时为 True
  """
  return player_data.talent[FIRST_KISS] == 0


def target_no_first_kiss(self_data, target_data, player_data) -> bool:
  """
  Premise.TARGET_NO_FIRST_KISS 和数据里 t_kiss_0 的定义函数
  Keyword arguments:
  self_data -- 判定角色的数据（game_type.Character）
  target_data -- 交互对象的数据（game_type.Character）
  player_data -- 玩家的数据（game_type.Character）
  Return arguments:
  bool -- 交互对象未保有初吻时为 True
  """
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
""" 每一项依次是子测试名、前提id、定义函数 """


class KissPremisesOwnHandlerTest(FastTestCase):
  """亲吻经验前提、初吻前提和数据里的 kiss_0、t_kiss_0 按各自定义判定的测试"""

  def test_every_state_matches_definition(self):
    """
    遍历16种组合和两名判定角色，比较每个前提的权重是否非零与定义函数的结果
    Keyword arguments:
    无
    Return arguments:
    无
    """
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
