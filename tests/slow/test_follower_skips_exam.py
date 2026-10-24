# -*- coding: UTF-8 -*-
"""
智能跟随中的干员不去体检的回归测试
==================================
排了体检的干员处于智能跟随时，不应动身去体检科：否则她在博士身边时去体检科，离开一步后又被「移动到玩家位置」拉回，
逐分钟来回。跟随中她留在等待体检名单上，跟随结束后再去体检科。

开新游戏后，博士在「身体检查与管理」里给检修工程师可露希尔排每天的体检，博士睡觉期间进行午夜抽签（见 tests/slow/health_check.py）。
- 排了体检、还没登记：时段开始前一小时，博士在博士办公室邀请她同行，在办公室等待 90 分钟。
- 已登记在等待名单上：博士到体检科邀请她同行，带回博士办公室等待 90 分钟。
两种情形下，跟随中她都不去体检科；用「结束同行」结束跟随后，她去体检科。
"""

from tests.slow.health_check import DR_OFFICE, EXAM_ROOM, MOVE_TO_EXAM, SLOT_START, HealthCheckTestCase

FOLLOW_MINUTES = 90
""" 博士带着她在办公室里等待的分钟数 """


class FollowerSkipsExamTest(HealthCheckTestCase):
  """智能跟随中的干员不动身去体检科，跟随结束后再去"""

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
    self.sleep_through_midnight()
    self.start = SLOT_START[self.operator.action_info.health_check_today]

  def follow_doctor_in_office(self) -> None:
    """
    博士邀请身边的她同行，回到博士办公室等待 FOLLOW_MINUTES 分钟，等她回到身边，核对她一直跟随、没去体检科；然后结束同行
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Core import constant

    pl = self.cache.character_data[0]
    picks = self.record_picks(self.operator_id)
    # 在场景里点选她，再点「邀请同行」
    pl.target_character_id = self.operator_id
    self.instruct(constant.Instruct.FOLLOW)
    self.assertEqual(self.operator.sp_flag.is_follow, 1)
    if pl.position != DR_OFFICE:
      self.walk(DR_OFFICE)
    for _ in range(FOLLOW_MINUTES // 5):
      self.instruct(constant.Instruct.WAIT)
    # 吃饭、如厕等生理需求会让她暂时走开，跟随会把她带回博士身边
    self.assertTrue(
        self.wait_until(lambda: self.operator.position == DR_OFFICE, 60),
        f"她在 {self.operator.position}",
    )
    self.assertEqual(self.operator.sp_flag.is_follow, 1, "她一直在跟随")
    self.assertNotIn(
        MOVE_TO_EXAM,
        [state_machine for _, state_machine in picks],
        "跟随中她不去体检科",
    )
    pl.target_character_id = self.operator_id
    self.instruct(constant.Instruct.END_FOLLOW)
    self.assertEqual(self.operator.sp_flag.is_follow, 0)

  def test_booked_follower_waits_until_follow_ends(self) -> None:
    """排了体检、还没进等待名单（目标 210500）：时段前开始跟随，时段内不去体检科，结束同行后去"""
    self.wait_until_hour(self.start - 1)
    # 把她带到博士身边，再邀请同行
    self.world.move(self.operator_id, self.cache.character_data[0].position)
    self.follow_doctor_in_office()
    self.assertGreaterEqual(
        self.cache.game_time.hour, self.start, "跟随延续到时段内"
    )
    self.assertTrue(
        self.wait_until(lambda: self.operator.position == EXAM_ROOM, 60),
        f"她在 {self.operator.position}",
    )

  def test_waiting_follower_waits_until_follow_ends(self) -> None:
    """已在等待体检名单上（目标 220505）：博士在体检科邀请她同行带回办公室，她不回体检科，结束同行后回去"""
    waiting = self.cache.rhodes_island.waiting_for_exam_operator_ids
    self.assertTrue(
        self.wait_until(lambda: self.operator_id in waiting, 24 * 60),
        "她在时段内到体检科登记",
    )
    self.walk(EXAM_ROOM)
    self.follow_doctor_in_office()
    self.assertIn(self.operator_id, waiting, "跟随中她仍在等待体检名单上")
    self.assertTrue(
        self.wait_until(lambda: self.operator.position == EXAM_ROOM, 60),
        f"她在 {self.operator.position}",
    )
