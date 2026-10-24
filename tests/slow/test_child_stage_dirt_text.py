# -*- coding: UTF-8 -*-
"""
身体面板的精液污浊文本不按幼女、学员阶段换差分
==============================================
脸部、口腔、腋部、手部的精液污浊在开启完整污浊文本时，按年龄素质的名称去差分文本表里找；找不到就用通用文本。
幼女（素质 102）与学员（素质 103）这四个部位的面板文字，每个污浊等级都与婴儿（素质 101，差分表里没有她的行）相同；
少女（素质 104）有差分文本，面板文字与婴儿不同，说明这四个部位的污浊确实画了出来。
开新游戏后取本局 id 最小的干员（不含博士）当博士的交互对象，脱光她的衣服，换她的年龄素质与污浊等级。
断言只报成立与否，不把面板文字带进测试输出。
"""

from tests.slow.base import SlowTestCase

BABY = 101
""" 婴儿素质：差分文本表里没有她的行 """
CHILD = 102
""" 幼女素质 """
TRAINEE = 103
""" 学员素质 """
GIRL = 104
""" 少女素质：差分文本表里有她的行 """
AGE_TALENT_LIST = (101, 102, 103, 104, 105, 106, 107)
""" 年龄素质，handle_talent.have_age_talent 按这个顺序取第一个 """
AGE_PART_LIST = (1, 2, 4, 5)
""" 按年龄素质找差分文本的部位：脸部、口腔、腋部、手部 """
FULL_DIRTY_SETTING = 10
""" 显示设置里「完整污浊文本」的编号 """
PANEL_WIDTH = 100
""" 面板的绘制宽度 """


class ChildStageDirtTextTest(SlowTestCase):
  """幼女与学员的精液污浊文字与没有差分文本的婴儿相同"""

  def setUp(self) -> None:
    """
    开新游戏，博士的交互对象是 id 最小的干员，脱光她的衣服，开启完整污浊文本
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    self.target_id = min(cid for cid in self.cache.npc_id_got if cid != 0)
    self.target = self.cache.character_data[self.target_id]
    for clothing_type in self.target.cloth.cloth_wear:
      self.target.cloth.cloth_wear[clothing_type] = []
    self.cache.character_data[0].target_character_id = self.target_id
    self.cache.all_system_setting.draw_setting[FULL_DIRTY_SETTING] = 1

  def panel_text(self, talent_id: int, semen_level: int) -> str:
    """
    把干员的年龄素质换成 talent_id、四个部位的精液污浊等级设为 semen_level，返回身体面板画出的文字
    Keyword arguments:
    talent_id -- 年龄素质
    semen_level -- 精液污浊等级
    Return arguments:
    str -- 面板文字
    """
    from Script.UI.Panel import dirty_panel

    for age_talent in AGE_TALENT_LIST:
      self.target.talent[age_talent] = 1 if age_talent == talent_id else 0
    for part_id in AGE_PART_LIST:
      self.target.dirty.body_semen[part_id][2] = semen_level
    panel = dirty_panel.SeeCharacterBodyPanel(self.target_id, PANEL_WIDTH, 9, 0)
    text_list = []
    for label in panel.draw_list:
      for value in label if isinstance(label, list) else [label]:
        text_list.append(getattr(value, "text", ""))
    return "".join(text_list)

  def test_child_and_trainee_use_common_text(self) -> None:
    """每个污浊等级下，幼女与学员的面板文字都与婴儿相同，少女的不同"""
    from Script.Config import game_config

    face_name = game_config.config_body_part[1].name
    level_list = [
        level
        for level in range(1, 100)
        if f"{face_name}精液污浊{level}"
        in game_config.ui_text_data["dirty_full"]
    ]
    self.assertTrue(level_list, "通用文本里有脸部的精液污浊等级")
    for semen_level in level_list:
      baby_text = self.panel_text(BABY, semen_level)
      self.assertTrue(
          self.panel_text(GIRL, semen_level) != baby_text,
          f"等级 {semen_level}：少女用差分文本，与婴儿不同",
      )
      self.assertTrue(
          self.panel_text(CHILD, semen_level) == baby_text,
          f"等级 {semen_level}：幼女与婴儿相同",
      )
      self.assertTrue(
          self.panel_text(TRAINEE, semen_level) == baby_text,
          f"等级 {semen_level}：学员与婴儿相同",
      )
