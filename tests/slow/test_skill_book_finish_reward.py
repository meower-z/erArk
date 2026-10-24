# -*- coding: UTF-8 -*-
"""
读完技能书时加的经验按书的难度给：难度 1 加 10，难度 2 加 20，难度 3 加 40
==========================================================================
开新游戏，取一名干员独自读书（交互对象是她自己）。
书籍配置里每本技能书（书籍类型对应的经验 id 不为 0）都经读书结算 handle_read_add_adjust 读两次：
- 阅读进度从 0 读一次，读不完：这本书对应经验的增加量，是每次读书都加的那一份；
- 阅读进度从 99 读一次，读完：对应经验的增加量减去上一份，就是读完时加的经验。
"""

from tests.slow.base import SlowTestCase

FINISH_REWARD = {0: 5, 1: 10, 2: 20, 3: 40}
""" 书的难度 -> 读完技能书时加的对应经验 """
READ_MINUTES = 30
""" 读一次书的分钟数 """


class SkillBookFinishRewardTest(SlowTestCase):
  """读完技能书时，对应经验按书的难度增加"""

  def read_once(self, character_id: int, book_id: int, progress: int) -> int:
    """
    让干员从给定的阅读进度读一次这本书，结算读书效果 handle_read_add_adjust
    Keyword arguments:
    character_id -- 角色id
    book_id -- 书本id
    progress -- 读之前的阅读进度
    Return arguments:
    int -- 这本书对应经验的增加量
    """
    from Script.Config import game_config
    from Script.Core import game_type
    from Script.Settle import default

    character_data = self.cache.character_data[character_id]
    exp_id = game_config.config_book_type[
        game_config.config_book[book_id].type
    ].exp_id
    character_data.behavior.book_id = book_id
    character_data.entertainment.read_book_progress[book_id] = progress
    before = character_data.experience.get(exp_id, 0)
    default.handle_read_add_adjust(
        character_id,
        READ_MINUTES,
        game_type.CharacterStatusChange(),
        self.cache.game_time,
    )
    return character_data.experience.get(exp_id, 0) - before

  def test_finish_reward_by_difficulty(self) -> None:
    """每本技能书读完时加的对应经验，等于它的难度在 FINISH_REWARD 里的值"""
    from Script.Config import game_config

    character_id = min(cid for cid in self.cache.npc_id_got if cid != 0)
    character_data = self.cache.character_data[character_id]
    character_data.target_character_id = character_id
    progress_dict = character_data.entertainment.read_book_progress
    reward_dict: dict[int, set[int]] = {}
    for book_id, book_data in sorted(game_config.config_book.items()):
      if not game_config.config_book_type[book_data.type].exp_id:
        continue
      read_gain = self.read_once(character_id, book_id, 0)
      self.assertLess(
          progress_dict[book_id], 100, f"书 {book_id} 从进度 0 读一次没读完"
      )
      finish_gain = self.read_once(character_id, book_id, 99)
      self.assertEqual(
          progress_dict[book_id], 100, f"书 {book_id} 从进度 99 读一次读完了"
      )
      reward_dict.setdefault(book_data.difficulty, set()).add(
          finish_gain - read_gain
      )
    self.assertTrue(
        {1, 2, 3} <= set(reward_dict), "书籍配置里有难度 1、2、3 的技能书"
    )
    self.assertEqual(
        reward_dict,
        {difficulty: {FINISH_REWARD[difficulty]} for difficulty in reward_dict},
        "各难度的技能书读完时加的对应经验",
    )
