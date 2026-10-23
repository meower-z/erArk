# -*- coding: UTF-8 -*-
"""
能力面板对被监禁干员负面刻印的降级标记的回归测试
==============================================
能力面板（Characterabi_show_Text）的刻印按钮里，反发刻印等级不低于1、宝珠足以降级时，按钮文字带「(-)」。
被监禁的干员降级所需宝珠按关押区等级打折，面板按打折后的需求判断。
本测试让开局的阿米娅反发刻印1级、关押区5级（监禁干员的降级消耗减半：1级反发刻印需 20000 宝珠值，打折后 10000），
只给她苦痛珠（反发刻印降级按 1:1 计入），按游戏的屏幕宽度画出能力面板，看反发刻印按钮的文字。
"""

import importlib

from tests.slow.base import SlowTestCase

HATE_MARK = 18
""" 反发刻印的能力id """
PRISON_FACILITY = 19
""" 关押区的设施id """
PAIN_JUEL = 17
""" 苦痛珠的宝珠id """


class PrisonerMarkDownMarkerTest(SlowTestCase):
  """被监禁的干员，宝珠够打折后的降级需求时，反发刻印按钮带「(-)」"""

  def hate_mark_button(self, imprisoned: bool, pain_juel: int) -> str:
    """
    设好阿米娅的反发刻印、监禁状态与苦痛珠，画出她的能力面板，返回反发刻印按钮的文字
    Keyword arguments:
    imprisoned -- 是否被监禁
    pain_juel -- 苦痛珠数量
    Return arguments:
    str -- 反发刻印按钮的文字
    """
    # 游戏模块要在启动游戏之后才能导入（见 tests/slow/__init__.py）
    game_config = importlib.import_module("Script.Config.game_config")
    normal_config = importlib.import_module("Script.Config.normal_config")
    ability_up_panel = importlib.import_module(
        "Script.UI.Panel.ability_up_panel"
    )

    cid = self.npc("阿米娅")
    cd = self.cache.character_data[cid]
    cd.ability[HATE_MARK] = 1
    cd.sp_flag.imprisonment = imprisoned
    cd.juel[PAIN_JUEL] = pain_juel
    self.cache.rhodes_island.facility_level[PRISON_FACILITY] = 5
    self.world.player.buttons.clear()
    ability_up_panel.Characterabi_show_Text(
        cid, normal_config.config_normal.text_width
    ).draw()
    mark_name = game_config.config_ability[HATE_MARK].name
    found = [text for text, _ in self.world.player.buttons if mark_name in text]
    self.assertEqual(len(found), 1, f"能力面板上的{mark_name}按钮：{found}")
    return str(found[0])

  def test_prisoner_with_discounted_juel_can_lower(self) -> None:
    """被监禁、宝珠够打折后的需求（不够原价）时，按钮带「(-)」"""
    self.assertIn("(-)", self.hate_mark_button(True, 15000))

  def test_free_operator_needs_full_juel(self) -> None:
    """未被监禁时按原价判断，同样的宝珠不够降级，按钮不带「(-)」"""
    self.assertNotIn("(-)", self.hate_mark_button(False, 15000))

  def test_prisoner_short_of_discounted_juel_cannot_lower(self) -> None:
    """被监禁但宝珠不够打折后的需求时，按钮不带「(-)」"""
    self.assertNotIn("(-)", self.hate_mark_button(True, 9000))
