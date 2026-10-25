# -*- coding: UTF-8 -*-
"""
群交的行为列表对仍有素质0 的交互对象不列出带 W 的破处行为
==========================================================
带「破处」与 W 的行为结算时也夺走素质0（阴道处女），所以交互对象有素质0 时，即使没有素质3，群交各部位的行为列表也不列出它。
开新游戏，在博士办公室召集凯尔希与阿米娅，邀请群交，玩家的交互对象为阿米娅。
她的素质0~4 设为 (1,1,0,0,1)，insert_position 设为 6（V 插入中），博士的腰技（能力76）设为 4，
这样带 W 的破处行为 womb_os_caress 的指令前提成立；现有行为把 insert_position 设为 6 或 7 时都结算 1103、清掉素质0，所以这里直接设定。
读群交各部位的行为列表（群交模板编辑面板与群交中 NPC 的 AI 都从这里取行为）：
- 有素质0：各部位都不列出带 W 的破处行为；
- 再去掉素质0：会列出带 W 的破处行为。
"""

from tests.slow.base import SlowTestCase

AMIYA_ID = 1
""" 阿米娅的角色id """
KALTSIT_ID = 3
""" 凯尔希的角色id """
BODY_PARTS = ("mouth", "L_hand", "R_hand", "penis", "侍奉", "anal")
""" 群交模板的部位记号 """


class GroupSexWBreakKeepsVVirginTest(SlowTestCase):
  """交互对象有素质0 时，群交的行为列表不列出带 W 的破处行为"""

  def setUp(self) -> None:
    """
    开新游戏后在博士办公室召集凯尔希与阿米娅，以阿米娅为交互对象邀请群交，她的素质0~4 设为 (1,1,0,0,1)，insert_position 为 6（V 插入中），博士的腰技为 4
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    from Script.Core import constant
    from Script.Design import handle_premise

    self.pl = self.cache.character_data[0]
    self.walk(["中枢", "博士办公室"])
    # 干员位置一览记住上次选的召集方式，只在第一次按
    self.summon(KALTSIT_ID, ("召集到自己当前位置",))
    self.summon(AMIYA_ID, ())
    self.pl.target_character_id = AMIYA_ID
    self.instruct(constant.Instruct.ASK_GROUP_SEX)
    self.assertTrue(handle_premise.handle_group_sex_mode_on(0), "进入了群交")
    amiya = self.cache.character_data[AMIYA_ID]
    for talent_id, value in enumerate((1, 1, 0, 0, 1)):
      amiya.talent[talent_id] = value
    amiya.h_state.insert_position = 6
    self.pl.ability[76] = 4

  def summon(self, chara_id: int, mode: tuple) -> None:
    """
    在干员位置一览里召集干员到博士身边，等她走到
    Keyword arguments:
    chara_id -- 角色id
    mode -- 召集干员前先按下的召集方式按钮
    Return arguments:
    无
    """
    from Script.Core import constant

    chara = self.cache.character_data[chara_id]
    self.world.player.press(*mode, chara.name, "返回")
    self.instruct(constant.Instruct.ALL_NPC_POSITION)
    self.show_panel()
    self.world.player.check_done()
    arrived = self.wait_until(lambda: chara.position == self.pl.position, 120)
    self.assertTrue(arrived, f"{chara.name} 走到了博士身边")
    # 好感与信赖的上限，日常互动能攒到，够邀请群交的判定
    chara.favorability[0] = 100000
    chara.trust = 300

  def w_break_listed(self) -> dict[str, list[str]]:
    """
    群交各部位的行为列表里带「破处」与 W 的行为
    Keyword arguments:
    无
    Return arguments:
    dict[str, list[str]] -- 部位记号: 排好序的行为id
    """
    from Script.Config import game_config
    from Script.System.Sex_System import group_sex_panel

    find = group_sex_panel.get_status_id_list_from_group_sex_body_part
    listed = {}
    for body_part in BODY_PARTS:
      listed[body_part] = sorted(
          behavior_id
          for behavior_id in find(body_part)
          if {"破处", "W"}
          <= set(game_config.config_behavior[behavior_id].tag.split("|"))
      )
    return listed

  def test_v_virgin_lists_no_w_break(self) -> None:
    """有素质0、没有素质3：各部位都不列出带 W 的破处行为"""
    self.assertEqual(
        self.w_break_listed(), {body_part: [] for body_part in BODY_PARTS}
    )

  def test_without_v_virgin_lists_w_break(self) -> None:
    """素质0 与素质3 都没有：会列出带 W 的破处行为"""
    self.cache.character_data[AMIYA_ID].talent[0] = 0
    listed = self.w_break_listed()
    self.assertNotEqual(
        [behavior_id for ids in listed.values() for behavior_id in ids],
        [],
        f"各部位列出的带 W 的破处行为：{listed}",
    )
