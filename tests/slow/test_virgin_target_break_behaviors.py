# -*- coding: UTF-8 -*-
"""
群交与调教助手的行为列表按交互对象的处女素质跳过破处类行为
==========================================================
行为的标签同时含「破处」与部位 V/A/U/W/N，而交互对象有对应的素质 0/1/2/3/4（V/A/U/W 处女、无接吻经验）时，
这个行为不列出；对应素质没有了，就照常列出。
开新游戏，在博士办公室召集凯尔希与阿米娅，玩家持有震动棒与肛门拉珠（道具 125、129），邀请群交。
- 群交模板编辑面板：口与侍奉两栏指定凯尔希，打开该栏的行为列表，读面板画出的行为按钮。
- 调教助手：玩家的交互对象为阿米娅，助手选与玩家爱抚胸部不同部位的行为时（not_selet_part="B"）可用的行为。
"""

import re
from unittest import mock

from tests.slow.base import SlowTestCase

AMIYA_ID = 1
""" 阿米娅的角色id """
KALTSIT_ID = 3
""" 凯尔希的角色id """
PART_OF_TALENT = {0: "V", 1: "A", 2: "U", 3: "W", 4: "N"}
""" 素质id：破处类行为标签里对应的部位 """
TOOL_ITEM_LIST = (125, 129)
""" 调教助手的道具类行为要求玩家持有的道具：震动棒、肛门拉珠 """


class VirginTargetBreakBehaviorsTest(SlowTestCase):
  """交互对象为处时，群交模板与调教助手都不列出对应部位的破处类行为"""

  def setUp(self) -> None:
    """
    开新游戏后在博士办公室召集凯尔希与阿米娅，玩家持有两件道具，以阿米娅为交互对象邀请群交
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
    for item_id in TOOL_ITEM_LIST:
      self.pl.item[item_id] = 1
    self.pl.target_character_id = AMIYA_ID
    self.instruct(constant.Instruct.ASK_GROUP_SEX)
    self.assertTrue(handle_premise.handle_group_sex_mode_on(0), "进入了群交")

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

  def break_parts(self, behavior_id: str) -> set:
    """
    破处类行为的部位
    Keyword arguments:
    behavior_id -- 行为id
    Return arguments:
    set -- 标签含「破处」时，标签里的 V/A/U/W/N；否则为空集合
    """
    from Script.Config import game_config

    tag_list = game_config.config_behavior[behavior_id].tag.split("|")
    if "破处" not in tag_list:
      return set()
    return set(PART_OF_TALENT.values()) & set(tag_list)

  def virgin_parts(self, character_id: int) -> set:
    """
    角色还是处（含无接吻经验）的部位
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    set -- 素质 0~4 中有的那几个对应的部位
    """
    talent = self.cache.character_data[character_id].talent
    return {
        part for talent_id, part in PART_OF_TALENT.items() if talent[talent_id]
    }

  def break_ids(self, behavior_id_list: list, part: str) -> list:
    """
    列表里该部位的破处类行为
    Keyword arguments:
    behavior_id_list -- 行为id列表
    part -- 部位 V/A/U/W/N
    Return arguments:
    list -- 排好序的行为id
    """
    return sorted(
        behavior_id
        for behavior_id in set(behavior_id_list)
        if part in self.break_parts(behavior_id)
    )

  def panel_list(self, body_part: str) -> list:
    """
    群交模板编辑面板：该栏指定凯尔希，打开该栏的行为列表，看完按返回
    Keyword arguments:
    body_part -- 群交部位记号，如 mouth、侍奉
    Return arguments:
    list -- 面板画出的行为按钮的行为id
    """
    from Script.Config import game_config
    from Script.Core import flow_handle
    from Script.System.Sex_System import group_sex_panel

    panel = group_sex_panel.Edit_Group_Sex_Temple_Panel(120)
    panel.reset_template()
    self.world.player.press(f"[{KALTSIT_ID:04d}]")
    panel.show_target_chara_list("A", body_part)
    # 等输入前记下屏幕上的按钮：按下返回之后按钮表就清空了
    shown: list[str] = []
    order_deal = flow_handle.order_deal

    def record_buttons(*args, **kwargs):
      """记下按钮再照常等输入"""
      shown[:] = [text for text, __ in self.world.player.buttons]
      return order_deal(*args, **kwargs)

    self.world.player.press("[返回]")
    with mock.patch.object(flow_handle, "order_deal", record_buttons):
      panel.show_status_list("A", body_part)
    self.world.player.check_done()
    found = [re.match(r"\[([^\]]+)\]", text.strip()) for text in shown]
    return [
        match.group(1)
        for match in found
        if match and match.group(1) in game_config.config_behavior
    ]

  def test_group_sex_panel(self):
    """凯尔希无接吻经验时，口与侍奉两栏不列出 N 的破处类行为；有了接吻经验就列出"""
    kaltsit = self.cache.character_data[KALTSIT_ID]
    self.assertIn("N", self.virgin_parts(KALTSIT_ID), "开局时凯尔希无接吻经验")
    for body_part in ("mouth", "侍奉"):
      self.assertEqual(
          self.break_ids(self.panel_list(body_part), "N"),
          [],
          f"{body_part} 栏列出了 N 的破处类行为",
      )
    kaltsit.talent[4] = 0
    for body_part in ("mouth", "侍奉"):
      self.assertNotEqual(
          self.break_ids(self.panel_list(body_part), "N"),
          [],
          f"凯尔希有接吻经验后，{body_part} 栏应列出 N 的破处类行为",
      )

  def test_sex_assistant(self):
    """阿米娅为交互对象：她还是处的部位，调教助手不列出该部位的破处类行为；破处之后就列出"""
    from Script.UI.Panel import confinement_and_training

    amiya = self.cache.character_data[AMIYA_ID]

    find = (
        confinement_and_training.get_all_can_use_behavior_id_for_sex_assistant
    )

    def listing() -> list:
      """调教助手选与爱抚胸部不同部位时可用的行为"""
      return find(not_selet_part="B")

    self.assertEqual(self.virgin_parts(AMIYA_ID), {"V", "A", "U", "W", "N"})
    for part in ("V", "A", "N"):
      self.assertEqual(
          self.break_ids(listing(), part), [], f"列出了 {part} 的破处类行为"
      )
    # 只失去 V 处女：V 的列出，A 与 N 的仍不列出
    amiya.talent[0] = 0
    now_list = listing()
    self.assertNotEqual(self.break_ids(now_list, "V"), [], "V 破处后应列出")
    self.assertEqual(self.break_ids(now_list, "A"), [], "A 仍是处")
    self.assertEqual(self.break_ids(now_list, "N"), [], "仍无接吻经验")
    amiya.talent[1] = 0
    amiya.talent[4] = 0
    now_list = listing()
    for part in ("A", "N"):
      self.assertNotEqual(
          self.break_ids(now_list, part), [], f"{part} 也破处后应列出"
      )
