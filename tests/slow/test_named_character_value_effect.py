# -*- coding: UTF-8 -*-
"""
综合数值结算按干员编号指定角色（A3）时，与按交互对象（A2）结算同一角色的结果相同
==============================================================================
开新游戏，取一名已拥有的干员作玩家的交互对象，对她依次结算状态、能力与经验的增加，
主体先写 A2（交互对象），再写 A3|<她的干员编号>；两次都记下她的数值变化与结算记录里记给她的变化，逐项比较。
"""

from tests.slow.base import SlowTestCase


class NamedCharacterValueEffectTest(SlowTestCase):
  """A3 主体的综合数值结算改变该角色的数值，并记进结算记录里她的一栏"""

  def test_a3_same_as_a2(self) -> None:
    """A3|<干员编号> 与 A2 结算同一角色：数值变化与记录都相同，且确实有变化"""
    from Script.Config import game_config
    from Script.Core import game_type
    from Script.Design import settle_behavior

    cache = self.cache
    npc_id = min(
        cid for cid in cache.npc_id_got if cache.character_data[cid].adv == cid
    )
    npc = cache.character_data[npc_id]
    cache.character_data[0].target_character_id = npc_id
    status_id = min(game_config.config_character_state)
    ability_id = min(game_config.config_ability)
    experience_id = min(game_config.config_experience)
    effect_list = [
        [f"S|{status_id}", "G", "300"],
        [f"A|{ability_id}", "G", "1"],
        [f"E|{experience_id}", "G", "2"],
    ]

    def settle(subject: str) -> tuple[list[float], dict]:
      """
      以 subject 为主体结算 effect_list
      Keyword arguments:
      subject -- 主体，A2 或 A3|<干员编号>
      Return arguments:
      list -- 状态、能力、经验三项各自的增加量
      dict -- 结算记录里记给该角色的状态、能力与经验变化
      """
      before = [
          npc.status_data.get(status_id, 0),
          npc.ability.get(ability_id, 0),
          npc.experience.get(experience_id, 0),
      ]
      change_data = game_type.CharacterStatusChange()
      for effect in effect_list:
        settle_behavior.handle_comprehensive_value_effect(
            0, [subject] + effect, change_data
        )
      after = [
          npc.status_data.get(status_id, 0),
          npc.ability.get(ability_id, 0),
          npc.experience.get(experience_id, 0),
      ]
      record = change_data.target_change[npc_id]
      return [new - old for old, new in zip(before, after)], {
          "status_data": dict(record.status_data),
          "ability": dict(record.ability),
          "experience": dict(record.experience),
      }

    by_target = settle("A2")
    by_number = settle(f"A3|{npc.adv}")
    self.assertTrue(all(by_target[0]), f"A2 结算让三项都有变化：{by_target}")
    self.assertEqual(by_number, by_target)
