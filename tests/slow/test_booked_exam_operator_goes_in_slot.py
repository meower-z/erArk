# -*- coding: UTF-8 -*-
"""
排了体检的干员到了体检时段去体检科的回归测试
============================================
异常位3（高优先级AI：助理、跟随、体检）看读取时是否在她的体检时段内：午夜排体检时在时段外，位3为正常；
到了时段内位3必须读成异常。位3异常时，要求 normal_all 的工作行与要求 normal_123467 的「继续移动」都不成立，AI 选去体检科。

开新游戏后，博士在「身体检查与管理」里给检修工程师可露希尔排每天的体检，博士睡觉期间进行午夜抽签（见 tests/slow/health_check.py）。
时段前她不去体检科；进入时段后她选的第一个行动就是去体检科，并走进体检科。
"""
from tests.slow.health_check import EXAM_ROOM, MOVE_TO_EXAM, SLOT_START, HealthCheckTestCase


class BookedExamOperatorGoesInSlotTest(HealthCheckTestCase):
    """排了体检的干员在自己的时段去体检科"""

    def test_goes_to_exam_room_in_her_slot(self):
        """可露希尔时段前不去体检科，进入时段后先去体检科"""
        operator_id = self.book_daily_exam("可露希尔")
        operator = self.cache.character_data[operator_id]
        picks = self.record_picks(operator_id)
        self.sleep_through_midnight()
        slot = operator.action_info.health_check_today
        self.assertIn(slot, SLOT_START, "午夜抽签给她排了上午或下午体检")
        slot_time = self.cache.game_time.replace(hour=SLOT_START[slot], minute=0)
        self.wait_until_hour(slot_time.hour)
        self.assertNotIn(MOVE_TO_EXAM, [state_machine for time, state_machine in picks if time < slot_time], f"{slot_time} 前她不去体检科")

        def in_slot():
            """
            时段开始之后她执行的状态机
            Keyword arguments:
            无
            Return arguments:
            list -- 状态机id，按执行顺序
            """
            return [state_machine for time, state_machine in picks if time >= slot_time]

        self.assertTrue(self.wait_until(lambda: bool(in_slot()), 60), "进入时段后她选了行动")
        self.assertEqual(in_slot()[0], MOVE_TO_EXAM, f"进入时段后她依次执行的状态机：{in_slot()[:5]}")
        self.assertTrue(self.wait_until(lambda: operator.position == EXAM_ROOM, 60), f"她在 {operator.position}")
