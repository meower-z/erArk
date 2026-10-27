# -*- coding: UTF-8 -*-
"""
事件的综合数值结算改变宝珠（J）
==============================
开新游戏，以星熊为玩家的交互对象，经事件结算结算星熊的子事件，
其效果为交互对象的状态12加10、经验0加1、宝珠0加1；结算后宝珠0多1，状态12多10，经验0增加。
"""

from tests.slow.base import SlowTestCase

EVENT_ID = "108c4126-9c89-4fb5-9de3-b56a94de9d5e"
""" 星熊的子事件，效果含 CVE_A2_J|0_G_1 """
ADV_ID = 136
""" 星熊的干员编号 """


class JuelEventEffectTest(SlowTestCase):
  """事件效果里的宝珠增加改变交互对象的宝珠"""

  def test_event_adds_juel(self) -> None:
    """结算星熊的子事件：她的宝珠0多1，状态12多10，经验0增加"""
    from Script.Core import game_type
    from Script.Design import settle_behavior

    cache = self.cache
    npc_id = next(
        cid
        for cid, chara in cache.character_data.items()
        if chara.adv == ADV_ID
    )
    npc = cache.character_data[npc_id]
    cache.character_data[0].target_character_id = npc_id
    before = [
        npc.juel.get(0, 0),
        npc.status_data.get(12, 0),
        npc.experience.get(0, 0),
    ]
    change_data = game_type.CharacterStatusChange()
    settle_behavior.handle_event_data(
        EVENT_ID, 0, 1, change_data, cache.game_time
    )
    after = [
        npc.juel.get(0, 0),
        npc.status_data.get(12, 0),
        npc.experience.get(0, 0),
    ]
    self.assertEqual(
        after[0] - before[0], 1, f"宝珠0：{before[0]} -> {after[0]}"
    )
    self.assertEqual(
        after[1] - before[1], 10, f"状态12：{before[1]} -> {after[1]}"
    )
    self.assertGreater(after[2], before[2], "经验0")
