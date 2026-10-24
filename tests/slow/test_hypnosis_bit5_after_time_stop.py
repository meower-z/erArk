# -*- coding: UTF-8 -*-
"""
平然催眠的干员在时停结束后按清醒判定的回归测试
==============================================
平然催眠（unconscious_h=4）使异常位5（意识模糊）为异常。开时停把她的 unconscious_h 改成 3，关时停再改成 0。
关时停后她已经清醒，异常位5必须读成正常；否则玩家对她用的、要求交互对象5、6正常的指令都不可用。

开新游戏后，直接给博士初级催眠与初级时停素质，把杜宾的催眠深度设为平然所需的 50%。
博士走进会议室，在「干员位置一览」里把杜宾召集过来，用「切换催眠模式」选平然让她进入平然状态，再用「时间停止流动」与「时间重新流动」开关时停。
"""

from tests.slow.base import SlowTestCase

ROOM = ["中枢", "会议室"]
PRIMARY_HYPNOSIS = 331
""" 素质：初级催眠 """
PRIMARY_TIME_STOP = 316
""" 素质：初级时停 """
CALM = 1
""" 催眠类型：平然 """


class HypnosisBit5AfterTimeStopTest(SlowTestCase):
  """关时停后，平然催眠过的干员异常位5为正常"""

  def test_calm_operator_is_lucid_after_time_stop(self) -> None:
    """杜宾进入平然后开、关时停：关时停后她清醒，异常位5正常，「交互对象5、6正常」成立"""
    from Script.Config import game_config
    from Script.Core import constant
    from Script.Design import handle_premise

    pl = self.cache.character_data[0]
    pl.talent[PRIMARY_HYPNOSIS] = 1
    pl.talent[PRIMARY_TIME_STOP] = 1
    operator_id = self.npc("杜宾")
    operator = self.cache.character_data[operator_id]
    operator.hypnosis.hypnosis_degree = game_config.config_hypnosis_type[
        CALM
    ].hypnosis_degree
    self.walk(ROOM)
    self.world.player.press("召集到自己当前位置", "杜宾", "返回")
    self.instruct(constant.Instruct.ALL_NPC_POSITION)
    self.show_panel()
    self.assertTrue(
        self.wait_until(lambda: operator.position == ROOM, 60),
        f"杜宾在 {operator.position}",
    )
    # 在场景里点选杜宾
    pl.target_character_id = operator_id
    self.world.player.press("平然")
    self.instruct(constant.Instruct.CHANGE_HYPNOSIS_MODE)
    self.show_panel()
    self.world.player.check_done()
    self.assertEqual(operator.sp_flag.unconscious_h, 4, "平然")
    self.assertEqual(
        handle_premise.handle_normal_5(operator_id), 0, "平然中异常位5为异常"
    )
    self.instruct(constant.Instruct.TIME_STOP_ON)
    self.assertEqual(
        handle_premise.handle_normal_6(operator_id), 0, "时停中异常位6为异常"
    )
    self.instruct(constant.Instruct.TIME_STOP_OFF)
    self.assertEqual(operator.sp_flag.unconscious_h, 0, "关时停后她清醒")
    self.assertEqual(
        handle_premise.handle_normal_5(operator_id), 1, "关时停后异常位5为正常"
    )
    self.assertEqual(
        handle_premise.handle_t_normal_5_6(0),
        1,
        "关时停后「交互对象5、6正常」成立",
    )
