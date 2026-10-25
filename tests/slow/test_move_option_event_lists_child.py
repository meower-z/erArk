# -*- coding: UTF-8 -*-
"""
博士走进男士止步的地点时，选项父事件列出子事件，选中的子事件经结算生效
======================================================================
通用事件 da8a5d84（event.json，行为 move）是选项父事件（效果 10001），
子事件 5925c54e 带 option_son 前提，效果 761 让自己移动至前一场景。
开新游戏，一名干员有二级陷落素质，在中枢的女士洗手间里等待。博士从博士房间走过去，抵达时父事件触发；
它打开的选项面板里按下子事件 5925c54e 的选项，博士回到走进洗手间之前所在的场景。
"""

from typing import TYPE_CHECKING

from tests.slow.base import SlowTestCase
from tests.world import UnplannedInput

if TYPE_CHECKING:
  from Script.UI.Panel.draw_event_text_panel import DrawEventTextPanel

PARENT_ID = "da8a5d84-014c-41ef-a755-c65c765867e0"
""" 抵达男士止步地点、在场者都至少二级陷落时的选项父事件 """
CHILD_ID = "5925c54e-2385-4463-9b5e-230ada6dd632"
""" 父事件下的子事件，效果 761（自己移动至前一场景） """
START = ["中枢", "博士房间"]
""" 博士开局所在的场景 """
LADIES_ONLY = ["中枢", "女士洗手间"]
""" 带 Ladies_Only 标签的场景 """
FALL_2_TALENT = 202
""" 二级陷落素质的素质id """
WAIT_MINUTES = 240
""" 干员在洗手间里等待的分钟数：博士走过去的时间之内她不离开 """
TRIES = 3
""" 最多走进洗手间的次数：走到时还有别的事件可能被随机选中 """


class MoveOptionEventListsChildTest(SlowTestCase):
  """父事件 da8a5d84 的面板列出子事件 5925c54e，选中后博士回到前一场景"""

  def _prepare_npc(self) -> None:
    """
    让一名二级陷落的干员在女士洗手间里等待
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Core import constant

    npc_id = min(cid for cid in self.cache.npc_id_got if cid)
    npc = self.cache.character_data[npc_id]
    self.world.move(npc_id, LADIES_ONLY)
    npc.talent[FALL_2_TALENT] = 1
    npc.behavior.behavior_id = constant.Behavior.WAIT
    npc.state = constant.CharacterStatus.STATUS_WAIT
    npc.behavior.start_time = self.cache.game_time
    npc.behavior.duration = WAIT_MINUTES

  def _record(self) -> tuple[list[str], list[str], list[list[str]]]:
    """
    包装事件判定与子事件选项的绘制，照常执行并记下事件id
    Keyword arguments:
    无
    Return arguments:
    list -- 博士触发的事件id
    list -- 选项面板列出的子事件id
    list -- 父事件触发时博士移动记录里最近的、不同于所在地的场景（未触发时为空）
    """
    from Script.Design import event
    from Script.UI.Panel import event_option_panel

    fired: list[str] = []
    offered: list[str] = []
    previous: list[list[str]] = []
    real_handle_event = event.handle_event
    player = self.cache.character_data[0]

    def record_event(
        character_id: int, event_before_instrust_flag: bool = False
    ) -> "DrawEventTextPanel | None":
      """
      照常判定事件，把博士触发的事件id收进 fired；父事件触发时把前一场景收进 previous
      Keyword arguments:
      character_id -- 角色id
      event_before_instrust_flag -- 是否是事件在前，指令在后
      Return arguments:
      DrawEventTextPanel -- 事件绘制面板，没有触发事件时为None
      """
      result = real_handle_event(character_id, event_before_instrust_flag)
      if result is not None and character_id == 0:
        fired.append(result.event_id)
        if result.event_id == PARENT_ID:
          previous[:] = [
              path
              for path in player.action_info.past_move_position_list
              if path != player.position
          ][-1:]
      return result

    class RecordedSonEventDraw(event_option_panel.SonEventDraw):
      """照常绘制子事件选项，并把子事件id收进 offered"""

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
        """
        if value_list[0] not in offered:
          offered.append(value_list[0])
        super().__init__(value_list, width, is_button, num_button, button_id)

    event.handle_event = record_event
    setattr(event_option_panel, "SonEventDraw", RecordedSonEventDraw)
    return fired, offered, previous

  def test_child_offered_and_settled(self) -> None:
    """父事件触发时面板里有子事件的选项；按下后博士回到走进洗手间之前所在的场景"""
    from Script.Config import game_config
    from Script.Design import talk

    player = self.cache.character_data[0]
    self.assertEqual(player.position, START, "博士开局所在的场景")
    self._prepare_npc()
    label = talk.code_text_to_draw_text(
        game_config.config_event[CHILD_ID].text.split("|")[0], 0
    )
    fired, offered, previous = self._record()
    for _ in range(TRIES):
      fired.clear()
      offered.clear()
      self.world.player.planned.clear()
      self.world.player.press(label)
      try:
        self.walk(LADIES_ONLY)
      # 选项面板在等玩家选择，面板上却没有子事件的选项
      except UnplannedInput:
        break
      if PARENT_ID in fired:
        break
      self.walk(START)
    self.assertIn(PARENT_ID, fired, f"走进洗手间 {TRIES} 次，父事件都没有触发")
    self.assertIn(CHILD_ID, offered, "父事件的选项面板列出的子事件")
    self.world.player.check_done()
    self.assertEqual(len(previous), 1, "父事件触发时博士的移动记录里有前一场景")
    self.assertNotEqual(previous[0], LADIES_ONLY)
    self.assertEqual(player.position, previous[0], "博士回到了前一场景")
