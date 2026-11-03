# -*- coding: UTF-8 -*-
"""
「周目点数结算」面板的经验列表按博士的性别跳过经验
==================================================
开新游戏后改博士的性别，再建「[1]博士的能力与经验」一节的经验列表（new_round.CharacterExperienceText）。
博士性别为 1 时，列表列出女性器官的经验 2、4，不列男性器官的经验 3、13、21、73。博士性别为 0 时，列表列出 3、13、21、73，不列 2、4。
"""

import importlib

from tests.slow.base import SlowTestCase

MALE_ONLY_EXPERIENCE = (3, 13, 21, 73)
""" 男性器官的经验id """
FEMALE_ONLY_EXPERIENCE = (2, 4)
""" 女性器官的经验id """
PANEL_WIDTH = 100
""" 传给面板的绘制宽度 """
INHERIT_RATE = 50
""" 传给面板的继承比例（百分比） """


class NewRoundExperienceBySexTest(SlowTestCase):
  """博士的经验列表按性别跳过经验的回归测试"""

  def listed_experience_names(self, sex: int) -> set[str]:
    """
    把博士设成给定性别，返回面板经验列表列出的经验名。列表只列数值大于 0 的经验。所以先给两组经验各记 10 点。
    Keyword arguments:
    sex -- 博士的性别id（0 有男性器官，1 有女性器官）
    Return arguments:
    set[str] -- 列出的经验名
    """
    new_round = importlib.import_module("Script.UI.Panel.new_round")
    player = self.cache.character_data[0]
    player.sex = sex
    for experience_id in MALE_ONLY_EXPERIENCE + FEMALE_ONLY_EXPERIENCE:
      player.experience[experience_id] = 10
    experience_panel = new_round.CharacterExperienceText(
        0, PANEL_WIDTH, 8, INHERIT_RATE
    )
    return {
        label.text.strip().split(":")[0]
        for row in experience_panel.draw_list
        if isinstance(row, list)
        for label in row
    }

  def experience_names(self, experience_ids: tuple[int, ...]) -> set[str]:
    """
    返回经验id对应的经验名
    Keyword arguments:
    experience_ids -- 经验id
    Return arguments:
    set[str] -- 经验名
    """
    game_config = importlib.import_module("Script.Config.game_config")
    return {
        game_config.config_experience[experience_id].name
        for experience_id in experience_ids
    }

  def test_female_lists_no_male_only_experience(self) -> None:
    """博士性别为 1 时，列表列出经验 2、4，不列 3、13、21、73"""
    listed = self.listed_experience_names(1)
    self.assertLessEqual(self.experience_names(FEMALE_ONLY_EXPERIENCE), listed)
    self.assertEqual(
        self.experience_names(MALE_ONLY_EXPERIENCE) & listed, set()
    )

  def test_male_lists_no_female_only_experience(self) -> None:
    """博士性别为 0 时，列表列出经验 3、13、21、73，不列 2、4"""
    listed = self.listed_experience_names(0)
    self.assertLessEqual(self.experience_names(MALE_ONLY_EXPERIENCE), listed)
    self.assertEqual(
        self.experience_names(FEMALE_ONLY_EXPERIENCE) & listed, set()
    )
