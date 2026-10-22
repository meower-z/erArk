# -*- coding: UTF-8 -*-
"""
异常位7（角色离线）只看自己是不是婴儿的回归测试
==============================================
异常位7 表示角色离线（装袋搬走、外勤、婴儿、他国外交访问、逃跑中），其中「婴儿」指她自己是婴儿。
保育员照料婴儿时交互对象是婴儿，她仍然在线；婴儿自己离线。
断言落在 handle_premise.handle_normal_7 的返回值上。
"""
from Script.Design import handle_premise
from tests.fast.base import FastTestCase

NURSERY = ["教", "育儿"]
BABY_TALENT = 101
""" 婴儿素质 """


class OfflineBitSelfIsBabyTest(FastTestCase):
    """handle_normal_7 的「婴儿」条件读自己的婴儿素质"""

    def test_carer_of_baby_stays_online(self):
        """保育员在育儿室照料婴儿：婴儿离线，交互对象是婴儿的保育员在线"""
        self.world.chara(0, "博士")
        baby = self.world.chara(1, "婴儿", position=NURSERY)
        carer = self.world.chara(2, "保育员", position=NURSERY)
        baby.talent[BABY_TALENT] = 1
        # 游戏初始化角色时把交互对象设为她自己（同 character_handle.init_character）
        baby.target_character_id = 1
        carer.target_character_id = 1
        self.assertEqual(handle_premise.handle_normal_7(1), 0, "婴儿离线")
        self.assertEqual(handle_premise.handle_normal_7(2), 1, "照料婴儿的保育员在线")
