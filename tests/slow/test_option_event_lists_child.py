# -*- coding: UTF-8 -*-
"""
星熊的选项面板列出子事件 108c4126
================================
星熊的事件 110b756a 属于聊天行为。
这个事件的效果是打开选项面板。
测试让玩家与星熊聊天，直到 110b756a 触发。
测试检查面板列出了子事件 108c4126。
测试再选中 108c4126，检查星熊的皮肤快感珠与皮肤经验各加 1。
"""

from typing import TYPE_CHECKING

from tests.slow.base import SlowTestCase
from tests.world import UnplannedInput

if TYPE_CHECKING:
  from Script.Core import game_type
  from Script.UI.Panel.draw_event_text_panel import DrawEventTextPanel

PARENT_ID = "110b756a-bd81-4fb8-b86a-4e749a2b34fa"
""" 星熊的选项父事件：行为是聊天，效果 10001 打开选项面板 """
CHILD_ID = "108c4126-9c89-4fb5-9de3-b56a94de9d5e"
""" 星熊的子事件：效果含皮肤快感珠加 1 与皮肤经验加 1 """
ADV_ID = 136
""" 星熊的干员编号 """
FALL_3_TALENT = 203
""" 素质「恋人」，对应攻略程度 3（父事件的前提之一） """
FAVORABILITY = 10000
""" 星熊对玩家的好感度，它计入严重骚扰判定的实行值 """
TRUST = 300
""" 星熊的信赖度，它计入严重骚扰判定的实行值 """
TRIES = 20
""" 等父事件触发时最多聊天的次数 """


class OptionEventListsChildTest(SlowTestCase):
  """玩家与星熊聊天时打开的选项面板"""

  def _prepare_target(self) -> "game_type.Character":
    """
    把星熊设为玩家的交互对象，并让父事件的前提成立
    Keyword arguments:
    无
    Return arguments:
    game_type.Character -- 星熊的角色数据
    """
    from Script.Design import handle_premise

    player = self.cache.character_data[0]
    npc_id = next(
        cid
        for cid, chara in self.cache.character_data.items()
        if chara.adv == ADV_ID
    )
    npc = self.cache.character_data[npc_id]
    self.cache.npc_id_got.add(npc_id)
    self.world.move(npc_id, player.position)
    npc.talent[FALL_3_TALENT] = 1
    npc.favorability[0] = FAVORABILITY
    npc.trust = TRUST
    player.target_character_id = npc_id
    self.assertTrue(
        handle_premise.handle_premise(
            "target_instruct_judge_high_obscenity", 0
        ),
        "严重骚扰的实行判定应成立",
    )
    return npc

  def _record(self) -> tuple[list[str], list[str]]:
    """
    记下游戏里触发的事件，也记下选项面板列出的子事件
    Keyword arguments:
    无
    Return arguments:
    list[str] -- 触发过的事件 id
    list[str] -- 选项面板列出过的子事件 id，每个只记一次
    """
    from Script.Design import event
    from Script.UI.Panel import event_option_panel

    fired: list[str] = []
    offered: list[str] = []
    real_handle_event = event.handle_event

    def record_event(
        character_id: int, event_before_instrust_flag: bool = False
    ) -> "DrawEventTextPanel | None":
      """
      执行真实的 handle_event，并记下它选出的事件
      Keyword arguments:
      character_id -- 角色id
      event_before_instrust_flag -- 是否是事件在前，指令在后
      Return arguments:
      DrawEventTextPanel -- 事件绘制面板，没有触发事件时为None
      """
      result = real_handle_event(character_id, event_before_instrust_flag)
      if result is not None:
        fired.append(result.event_id)
      return result

    class RecordedSonEventDraw(event_option_panel.SonEventDraw):
      """选项按钮：画按钮之前记下它的子事件 id"""

      def __init__(
          self,
          value_list: list,
          width: int,
          is_button: bool,
          num_button: bool,
          button_id: int,
      ) -> None:
        """
        Keyword arguments:
        value_list -- 事件id,人物id
        width -- 最大宽度
        is_button -- 绘制按钮
        num_button -- 绘制数字按钮
        button_id -- 数字按钮id
        Return arguments:
        无
        """
        if value_list[0] not in offered:
          offered.append(value_list[0])
        super().__init__(value_list, width, is_button, num_button, button_id)

    event.handle_event = record_event
    setattr(event_option_panel, "SonEventDraw", RecordedSonEventDraw)
    return fired, offered

  def test_child_offered_and_settled(self) -> None:
    """玩家选中选项面板列出的子事件后，星熊的皮肤快感珠与皮肤经验各加 1"""
    from Script.Config import game_config
    from Script.Core import constant
    from Script.Design import talk

    npc = self._prepare_target()
    # 选项按钮上的文字取自事件文本里「|」之前的部分
    label = talk.code_text_to_draw_text(
        game_config.config_event[CHILD_ID].text.split("|")[0], 0
    )
    fired, offered = self._record()
    for _ in range(TRIES):
      # 聊天次数超过上限时，聊天指令走聊天失败行为
      npc.action_info.talk_count = 0
      fired.clear()
      offered.clear()
      self.world.player.planned.clear()
      self.world.player.press(label)
      before = (npc.juel.get(0, 0), npc.experience.get(0, 0))
      try:
        self.instruct(constant.Instruct.CHAT)
      except UnplannedInput:
        # 游戏在等一个选择，屏幕上没有子事件的按钮
        break
      if PARENT_ID in fired:
        break
    self.assertIn(PARENT_ID, fired, f"聊天 {TRIES} 次，父事件都没有触发")
    self.assertIn(CHILD_ID, offered, "父事件的选项面板列出的子事件")
    self.world.player.check_done()
    after = (npc.juel.get(0, 0), npc.experience.get(0, 0))
    self.assertEqual(
        after[0] - before[0], 1, f"皮肤快感珠：{before} -> {after}"
    )
    self.assertEqual(after[1] - before[1], 1, f"皮肤经验：{before} -> {after}")
