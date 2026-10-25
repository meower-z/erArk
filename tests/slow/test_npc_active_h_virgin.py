# -*- coding: UTF-8 -*-
"""
NPC 主动H（逆推）时，仍有处女素质的她不选会夺走该素质的破处行为，与抽到哪个部位无关
================================================================================
素质0 配 V 与 W（带 W 的破处行为结算时也夺走阴道处女），素质1 配 A，素质2 配 U，素质3 配 W，素质4 配 N：
她有某个素质时，同时带「破处」与对应标签的行为就会夺走它。
开新游戏，博士与阿米娅进一间能锁门的空房间；博士下「邀请H」进入H，再下「交给对方」让她主动H。
之后把她的部位喜好固定为某个部位，用每个种子各调一次 npc_active_h，记下它赋给博士的行为。
npc_active_h 选完行为后调的主循环换成只记录行为的替身，每次调完复原博士的行为，她的状态不前进。
部位取 0（标签过滤只留 N 行为）与 22（不过滤标签）：
- 她有素质0~4：选出的行为里没有会夺走其中任一素质的破处行为；
- 她素质0~4 都没有：仍会选出破处行为。
她只有素质0、1、4（没有素质2、3）时，部位取 0、21、22（21 与 22 都不过滤标签），选出的行为里没有会夺走其中任一素质的破处行为，
包括带 W 的破处行为。
"""

import collections
import random
from unittest import mock

from tests.slow.base import SlowTestCase

NPC_NAME = "阿米娅"
""" 主动H的干员，开局时有素质0~4 """
FAVORABILITY = 10000
""" 她对博士的好感，与信赖一起让「邀请H」成功 """
TRUST = 200
""" 她对博士的信赖 """
PARTS = (0, 22)
""" 固定的部位喜好：0 只留带 N 标签的行为，22 不过滤标签 """
PARTS_WITHOUT_WOMB_VIRGIN = (0, 21, 22)
""" 她没有素质2、3 时固定的部位喜好：21 与 22 都不过滤标签 """
SEEDS = range(300)
""" 每个部位调 npc_active_h 用的种子 """
VIRGIN_TALENT_TAGS = {
    0: {"V", "W"},
    1: {"A"},
    2: {"U"},
    3: {"W"},
    4: {"N"},
}
""" 处女素质id: 会夺走它的破处行为所带的部位标签，带其中任一个就会夺走 """


class NpcActiveHVirginTest(SlowTestCase):
  """NPC 主动H时，会夺走她处女素质的破处行为只在她没有该素质时选得出"""

  def start_npc_active_h(self) -> int:
    """
    博士与阿米娅进一间能锁门的空房间，经「邀请H」与「交给对方」让她主动H
    Keyword arguments:
    无
    Return arguments:
    int -- 她的角色id
    """
    from Script.Core import constant
    from Script.Design import map_handle

    player = self.cache.character_data[0]
    npc_id = self.npc(NPC_NAME)
    npc = self.cache.character_data[npc_id]
    room_key = next(
        key
        for key, scene in sorted(self.cache.scene_data.items())
        if scene.close_type in (1, 2) and not scene.character_list
    )
    room = map_handle.get_map_system_path_for_str(room_key)
    self.world.move(0, room)
    self.world.move(npc_id, room)
    npc.favorability[0] = FAVORABILITY
    npc.trust = TRUST
    player.target_character_id = npc_id
    self.instruct(constant.Instruct.DO_H)
    self.instruct(constant.Instruct.CHANGE_TOP_AND_BOTTOM)
    self.assertTrue(npc.h_state.npc_active_h, f"{NPC_NAME}在主动H")
    return npc_id

  def picks_at_part(self, part_id: int) -> collections.Counter[str]:
    """
    部位喜好固定为 part_id，每个种子调一次 npc_active_h，数它赋给博士的各个行为
    Keyword arguments:
    part_id -- 固定的部位id
    Return arguments:
    collections.Counter[str] -- 行为id: 选中的次数
    """
    from Script.Design import handle_npc_ai_in_h, update

    player = self.cache.character_data[0]
    saved = (
        player.behavior.behavior_id,
        player.state,
        player.behavior.duration,
        player.behavior.start_time,
    )
    picks: collections.Counter[str] = collections.Counter()

    def record(add_time: int) -> None:
      """
      主循环的替身：记下赋给博士的行为
      Keyword arguments:
      add_time -- 推进的分钟数，不使用
      Return arguments:
      无
      """
      picks[player.behavior.behavior_id] += 1

    with mock.patch.object(
        handle_npc_ai_in_h, "evaluate_npc_body_part_prefs", return_value=part_id
    ), mock.patch.object(update, "game_update_flow", side_effect=record):
      for seed in SEEDS:
        random.seed(seed)
        handle_npc_ai_in_h.npc_active_h()
        (
            player.behavior.behavior_id,
            player.state,
            player.behavior.duration,
            player.behavior.start_time,
        ) = saved
    self.assertEqual(
        sum(picks.values()),
        len(SEEDS),
        f"部位{part_id}下每个种子都选出了一个行为",
    )
    return picks

  def break_behaviors(self, npc_id: int) -> set[str]:
    """
    会夺走她现有处女素质的破处行为：带「破处」，且带她仍有的某个素质对应的部位标签
    Keyword arguments:
    npc_id -- 她的角色id
    Return arguments:
    set[str] -- 行为id
    """
    from Script.Config import game_config

    talent = self.cache.character_data[npc_id].talent
    tags = {
        tag
        for talent_id, talent_tags in VIRGIN_TALENT_TAGS.items()
        if talent[talent_id]
        for tag in talent_tags
    }
    return {
        behavior_id
        for behavior_id, behavior_data in game_config.config_behavior.items()
        if "破处" in behavior_data.tag.split("|")
        and tags & set(behavior_data.tag.split("|"))
    }

  def test_virgin_npc_picks_no_break_behavior(self) -> None:
    """她有素质0~4：部位 0 与 22 下选出的行为都不会夺走其中任一素质"""
    npc_id = self.start_npc_active_h()
    talent = self.cache.character_data[npc_id].talent
    self.assertEqual(
        [talent[talent_id] for talent_id in VIRGIN_TALENT_TAGS],
        [1] * len(VIRGIN_TALENT_TAGS),
        f"{NPC_NAME}有素质0~4",
    )
    break_behaviors = self.break_behaviors(npc_id)
    picks = {part_id: self.picks_at_part(part_id) for part_id in PARTS}
    self.assertEqual(
        {
            part_id: sorted(set(part_picks) & break_behaviors)
            for part_id, part_picks in picks.items()
        },
        {part_id: [] for part_id in PARTS},
        f"各部位选出的破处行为，全部选择：{picks}",
    )

  def test_npc_without_womb_virgin_picks_no_break_behavior(self) -> None:
    """她只有素质0、1、4：部位 0、21、22 下选出的行为都不会夺走其中任一素质，包括带 W 的破处行为"""
    npc_id = self.start_npc_active_h()
    talent = self.cache.character_data[npc_id].talent
    talent[2] = 0
    talent[3] = 0
    break_behaviors = self.break_behaviors(npc_id)
    picks = {
        part_id: self.picks_at_part(part_id)
        for part_id in PARTS_WITHOUT_WOMB_VIRGIN
    }
    self.assertEqual(
        {
            part_id: sorted(set(part_picks) & break_behaviors)
            for part_id, part_picks in picks.items()
        },
        {part_id: [] for part_id in PARTS_WITHOUT_WOMB_VIRGIN},
        f"各部位选出的破处行为，全部选择：{picks}",
    )

  def test_npc_without_virgin_talents_picks_break_behavior(self) -> None:
    """她素质0~4 都没有：部位 0 与 22 下仍会选出破处行为"""
    from Script.Config import game_config

    npc_id = self.start_npc_active_h()
    for talent_id in VIRGIN_TALENT_TAGS:
      self.cache.character_data[npc_id].talent[talent_id] = 0
    break_tagged = {
        behavior_id
        for behavior_id, behavior_data in game_config.config_behavior.items()
        if "破处" in behavior_data.tag.split("|")
    }
    picks = {part_id: self.picks_at_part(part_id) for part_id in PARTS}
    self.assertEqual(
        [
            part_id
            for part_id, part_picks in picks.items()
            if not set(part_picks) & break_tagged
        ],
        [],
        f"没有选出破处行为的部位，全部选择：{picks}",
    )
