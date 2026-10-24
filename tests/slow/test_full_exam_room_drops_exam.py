# -*- coding: UTF-8 -*-
"""
体检科满员时干员放弃今天体检的回归测试
======================================
体检科满员（Room_Area 0 上限 10 人）时，要去体检的干员在动身时就放弃今天的体检：清掉今日体检时间、退出等待名单，当天不回体检科，下一个体检日照常抽选；
否则她会在门口被拒，之后反复重选同一个体检目标、在走廊重试。

开新游戏后，博士在「身体检查与管理」里给检修工程师可露希尔排每天的体检，博士睡觉期间进行午夜抽签（见 tests/slow/health_check.py）。
她动身去体检科之前，或登记后离开、正走回体检科时，博士招募 10 名新干员并带进体检科：新干员原地等待 30 分钟，这段时间里体检科满员。
"""

from tests.slow.health_check import EXAM_ROOM, SLOT_START, HealthCheckTestCase

GIVE_UP_MINUTES = 30
""" 坐满体检科后，等她放弃的最长分钟数（新干员原地等待的时长） """


class FullExamRoomDropsExamTest(HealthCheckTestCase):
  """体检科满员时，要去体检的干员放弃今天的体检"""

  def setUp(self) -> None:
    """
    给可露希尔排体检，博士睡觉期间进行午夜抽签
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    self.operator_id = self.book_daily_exam("可露希尔")
    self.operator = self.cache.character_data[self.operator_id]
    self.waiting = self.cache.rhodes_island.waiting_for_exam_operator_ids
    self.sleep_through_midnight()
    self.start = SLOT_START[self.operator.action_info.health_check_today]

  def check_gives_up_for_today(self) -> None:
    """
    体检科已坐满：她在 GIVE_UP_MINUTES 分钟内放弃今天的体检（今日体检时间清零、不在等待名单上），之后到当天结束都不进体检科
    Keyword arguments:
    无
    Return arguments:
    无
    """
    operator = self.operator
    gave_up = self.wait_until(
        lambda: operator.action_info.health_check_today == 0
        and self.operator_id not in self.waiting,
        GIVE_UP_MINUTES,
    )
    self.assertTrue(
        gave_up,
        f"今日体检时间 {operator.action_info.health_check_today}，在等待名单上：{self.operator_id in self.waiting}",
    )
    today = self.cache.game_time.day
    self.assertTrue(
        self.wait_until(
            lambda: self.operator.position == EXAM_ROOM
            or self.cache.game_time.day != today,
            24 * 60,
        )
    )
    self.assertNotEqual(
        self.operator.position,
        EXAM_ROOM,
        f"{self.cache.game_time} 她又进了体检科",
    )

  def test_booked_operator_gives_up_when_full(self) -> None:
    """排了体检、还没进等待名单（目标 210500）：时段开始前体检科坐满，她放弃今天的体检；下一个体检日照常抽中她"""
    self.wait_until_hour(self.start - 1)
    self.assertTrue(
        self.wait_until(lambda: self.cache.game_time.minute >= 55, 60)
    )
    self.fill_exam_room()
    self.check_gives_up_for_today()
    self.assertIn(
        self.operator.action_info.health_check_today,
        SLOT_START,
        "下一个体检日的抽签抽中了她",
    )

  def test_waiting_operator_gives_up_when_full(self) -> None:
    """已在等待体检名单上（目标 220505）：她暂时离开体检科、正往回走时体检科坐满，她退出等待名单"""
    operator = self.operator
    self.assertTrue(
        self.wait_until(lambda: self.operator_id in self.waiting, 24 * 60),
        "她在时段内到体检科登记",
    )
    self.assertTrue(
        self.wait_until(
            lambda: operator.position != EXAM_ROOM
            and operator.behavior.move_final_target == EXAM_ROOM,
            24 * 60,
        ),
        "她离开体检科后往回走",
    )
    self.assertIn(self.operator_id, self.waiting)
    self.fill_exam_room()
    self.check_gives_up_for_today()
