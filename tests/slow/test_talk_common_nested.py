# -*- coding: UTF-8 -*-
"""
通用占位符嵌套替换的回归测试
==========================
通用口上（纸娃娃地文）的文本里会嵌套别的通用占位符（例如 m_orgasm_* 插入 {mouth}，{mouth} 再插入 {mouth_s}）。
占位符的处理顺序是 game_config.config_talk_common_cid_list_by_type 的顺序，它来自构建时列出 data/talk_common 下文件的顺序。
talk.talk_common_judge 不能依赖这个顺序：里层排在外层前面时，外层插入的里层占位符也必须被替换，
否则 code_text_to_draw_text 的 str.format 抛 KeyError。

开新游戏后，博士在会议室锁门时被杜宾逆推（与 test_ambush_event_keeps_door_locked 的开场相同），两人进入H。
布置：纸娃娃地文替换几率调到最大（玩家设置），通用口上的处理顺序整个倒过来（嵌套的里层全都排在外层前面），
杜宾的口喉快感到达一级高潮。博士用「H中等待五分钟」推进时间，主循环结算杜宾的口喉高潮，
渲染出的通用口上不留下任何通用占位符，渲染也不抛异常。
"""

from tests.slow.base import SlowTestCase

ROOM = ["中枢", "会议室"]
MOUTH = 21
""" 口喉快感的状态id """


class TalkCommonNestedTest(SlowTestCase):
  """处理顺序倒过来时，高潮的通用口上里嵌套的占位符都被替换"""

  def test_reversed_order_climax_line(self) -> None:
    """倒序时杜宾的口喉高潮渲染出通用口上，文本里不留通用占位符"""
    from Script.Config import game_config
    from Script.Core import constant
    from Script.Design import talk

    self.walk(ROOM)
    operator_id = self.npc("杜宾")
    operator = self.cache.character_data[operator_id]
    self.world.move(operator_id, ROOM)
    operator.sp_flag.npc_masturebate_for_player = True
    self.world.player.press("逆来顺受")
    self.instruct(constant.Instruct.DOOR_LOCK_INNER)
    self.assertTrue(operator.sp_flag.is_h)

    self.cache.all_system_setting.draw_setting[13] = 10
    game_config.config_talk_common_cid_list_by_type = dict(
        reversed(list(game_config.config_talk_common_cid_list_by_type.items()))
    )
    # 0 级的上限就是 1 级的下限
    operator.status_data[MOUTH] = next(
        iter(game_config.config_character_state_level.values())
    ).max_value
    rendered = []
    """ talk_common_judge 每次的输入与输出 """
    real_judge = talk.talk_common_judge

    def record_judge(now_talk: str, character_id: int) -> str:
      """
      记录型包装：照常替换，并把输入与输出收进 rendered
      Keyword arguments:
      now_talk -- 原文本
      character_id -- 角色id
      Return arguments:
      str -- 替换后的文本
      """
      result = real_judge(now_talk, character_id)
      rendered.append((now_talk, result))
      return result

    talk.talk_common_judge = record_judge
    self.instruct(constant.Instruct.WAIT_5_MIN_IN_H)

    climax = [
        result for text, result in rendered if text.startswith("{m_orgasm_")
    ]
    self.assertTrue(climax, "没有渲染口喉高潮的通用口上")
    keys = [
        "{" + key + "}"
        for key in game_config.config_talk_common_cid_list_by_type
    ]
    left = sorted(
        {key for _, result in rendered for key in keys if key in result}
    )
    self.assertEqual(left, [])
