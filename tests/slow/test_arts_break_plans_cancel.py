# -*- coding: UTF-8 -*-
"""
理智耗尽时源石技艺中断的回归测试
================================
博士开着技艺做事，理智随时间耗尽：技艺中断的提示出现一次，透视关掉，
催眠中的交互对象与开着的时停由排上的「解除催眠」「解除时停」在博士接下来的行动里解除。

开新游戏后，直接给博士初级催眠与初级时停素质。催眠一例：把杜宾召集到会议室，用「切换催眠模式」选平然，
再开透视、把理智设为 1/3（透视每分钟耗 1/12，五分钟耗 5/12），等待五分钟。时停一例：开时停、把理智设为 1，等待五分钟。
"""

from fractions import Fraction
import importlib
from unittest import mock

from tests import kernel_data
from tests.slow.base import SlowTestCase

ROOM = ["中枢", "会议室"]
PRIMARY_HYPNOSIS = 331
""" 素质：初级催眠 """
PRIMARY_TIME_STOP = 316
""" 素质：初级时停 """
CALM = 1
""" 催眠类型：平然 """
BREAK_TEXT = "理智值不足，开启的源石技艺已全部中断"
""" 技艺中断的提示 """


class ArtsBreakPlansCancelTest(SlowTestCase):
    """理智耗尽：技艺中断提示一次，解除行动在博士接下来的行动里开始"""

    def _count_breaks(self) -> list[str]:
        """
        从此刻起记下画出的技艺中断提示
        Return arguments:
        list -- 画出的提示，按画出的顺序追加
        """
        from Script.UI.Moudle import draw

        shown: list[str] = []
        original = draw.WaitDraw.draw

        def record(self: draw.WaitDraw) -> None:
            """
            画出 WaitDraw 时记下技艺中断的提示，再照常画
            Keyword arguments:
            self -- 绘制对象
            """
            if BREAK_TEXT in str(getattr(self, "text", "")):
                shown.append(str(self.text))
            original(self)

        patcher = mock.patch.object(draw.WaitDraw, "draw", record)
        patcher.start()
        self.addCleanup(patcher.stop)
        return shown

    def _hypnotize(self, name: str) -> int:
        """
        把干员召集到会议室，选作交互对象，让她进入平然催眠
        Keyword arguments:
        name -- 干员名
        Return arguments:
        int -- 干员的角色id
        """
        from Script.Config import game_config
        from Script.Core import constant

        pl = self.cache.character_data[0]
        operator_id = self.npc(name)
        operator = self.cache.character_data[operator_id]
        operator.hypnosis.hypnosis_degree = game_config.config_hypnosis_type[
            CALM
        ].hypnosis_degree
        self.walk(ROOM)
        self.world.player.press("召集到自己当前位置", name, "返回")
        self.instruct(constant.Instruct.ALL_NPC_POSITION)
        self.show_panel()
        self.assertTrue(
            self.wait_until(lambda: operator.position == ROOM, 60),
            f"{name} 在 {operator.position}",
        )
        pl.target_character_id = operator_id
        self.world.player.press("平然")
        self.instruct(constant.Instruct.CHANGE_HYPNOSIS_MODE)
        self.show_panel()
        self.world.player.check_done()
        self.assertEqual(operator.sp_flag.unconscious_h, 4, "平然")
        return operator_id

    def test_hypnosis_cancel_starts_next(self) -> None:
        """透视与催眠开着时理智耗尽：透视关掉，博士下一个行动是解除催眠，她清醒过来"""
        from Script.Core import constant

        pl = self.cache.character_data[0]
        pl.talent[PRIMARY_HYPNOSIS] = 1
        operator = self.cache.character_data[self._hypnotize("杜宾")]
        pl.pl_ability.visual = True
        kernel_data.set_needs(pl.cid, sanity=Fraction(1, 3))
        breaks = self._count_breaks()
        self.instruct(constant.Instruct.WAIT)
        self.assertEqual(len(breaks), 1, "技艺中断的提示出现一次")
        self.assertEqual(kernel_data.needs_of(pl.cid)["sanity"], 0)
        self.assertFalse(pl.pl_ability.visual, "透视关掉")
        history = importlib.import_module("Script.Modules.domains.history")
        self.assertEqual(
            history.recent()[-2:],
            [constant.Behavior.WAIT, constant.Behavior.HYPNOSIS_CANCEL],
            "等待之后接着解除催眠",
        )
        self.assertEqual(operator.sp_flag.unconscious_h, 0, "她清醒过来")

    def test_time_stop_off_starts_next(self) -> None:
        """时停中理智耗尽：博士下一个行动是解除时停，时间重新流动"""
        from Script.Core import constant

        history = importlib.import_module("Script.Modules.domains.history")
        modes = importlib.import_module("Script.Modules.domains.modes")
        pl = self.cache.character_data[0]
        pl.talent[PRIMARY_TIME_STOP] = 1
        self.instruct(constant.Instruct.TIME_STOP_ON)
        self.assertTrue(modes.time_stop(), "时停开着")
        kernel_data.set_needs(pl.cid, sanity=1)
        breaks = self._count_breaks()
        self.instruct(constant.Instruct.WAIT)
        self.assertEqual(len(breaks), 1, "技艺中断的提示出现一次")
        self.assertEqual(
            history.recent()[-2:],
            [constant.Behavior.WAIT, constant.Behavior.TIME_STOP_OFF],
            "等待之后接着解除时停",
        )
        self.assertFalse(modes.time_stop(), "时间重新流动")
