# -*- coding: UTF-8 -*-
"""
被吵醒、不肯继续的无意识H对象，H照样整套结束
============================================
玩家对睡着的干员A进行睡眠H，她被动静吵醒（needs.sleep_noise），陷落为负、愤怒，不继续H：
- 排上的结束无意识H是 0 分钟的行动，它的结束结算照样整套运行：之后A不在H里，H状态归位（插入位置 -1），
  脱下的衣服穿回去了。
- 群交中：同一场景里一起H的干员B也被叫醒，同样不肯继续。她这一边照样做退出结算：H状态归位，衣服穿回去。
"""

import importlib
from unittest import mock

from tests import kernel_data
from tests.slow.base import SlowTestCase

INSERTED = 3
""" H中的插入位置；归位后是 -1 """


class UnconsciousHRefusalEndsHTest(SlowTestCase):
    """吵醒后不肯继续的结束结算"""

    def setUp(self) -> None:
        """开新游戏，玩家与两名干员在同一场景，玩家以A为交互对象"""
        super().setUp()
        npcs = sorted(i for i in self.cache.npc_id_got if i)
        self.a_id, self.b_id = npcs[0], npcs[1]
        player = self.cache.character_data[0]
        for cid in (self.a_id, self.b_id):
            self.world.move(cid, player.position)
        player.target_character_id = self.a_id

    def in_h(self, cid: int, unconscious: int) -> None:
        """
        角色在H中：插入位置有值；干员脱下一件衣服
        Keyword arguments:
        cid -- 角色id
        unconscious -- sp_flag.unconscious_h 的值
        """
        data = self.cache.character_data[cid]
        kernel_data.put(kernel_data.domain("flags").set, cid, is_h=True)
        kernel_data.put(
            kernel_data.domain("flags").set, cid, unconscious_h=unconscious
        )
        data.h_state.insert_position = INSERTED
        if cid == 0:
            return
        kind = next(k for k, worn in data.cloth.cloth_wear.items() if worn)
        data.cloth.cloth_off[kind] = data.cloth.cloth_wear[kind]
        data.cloth.cloth_wear[kind] = []

    def ended(self, cid: int) -> tuple[bool, int, bool]:
        """
        角色H结束后的样子
        Return arguments:
        tuple -- (仍在H中, 插入位置, 还有脱下的衣服)
        """
        data = self.cache.character_data[cid]
        return (
            kernel_data.domain("flags").get(cid, "is_h"),
            data.h_state.insert_position,
            any(data.cloth.cloth_off.values()),
        )

    def wake_a(self) -> None:
        """A被玩家的动静吵醒，玩家等待 5 分钟；吵醒的人愤怒（陷落为负），推进到玩家下一次选行动"""
        from Script.Core import constant
        from Script.Design import attr_calculation, handle_premise
        from Script.System.Instruct_System import handle_instruct
        from tests import world

        needs = importlib.import_module("Script.Modules.domains.needs")
        self.in_h(0, 0)
        self.in_h(self.a_id, 1)
        kernel_data.set_world(needs.note_woken, self.a_id, 0)
        with (
            mock.patch.object(
                handle_premise,
                "handle_instruct_judge_high_obscenity",
                return_value=True,
            ),
            mock.patch.object(
                attr_calculation, "get_character_fall_level", return_value=-1
            ),
        ):
            world.act(
                lambda: handle_instruct.handle_instruct(constant.Instruct.WAIT)
            )

    def test_refused_partner_ends_h(self) -> None:
        """A不肯继续：0 分钟的结束无意识H结算之后，A不在H里，H状态归位，衣服穿回去"""
        self.wake_a()
        self.assertEqual(self.ended(self.a_id), (False, -1, False))

    def test_refused_group_member_ends_h(self) -> None:
        """群交中B也不肯继续：她这一边做退出结算，H状态归位，衣服穿回去"""
        modes = importlib.import_module("Script.Modules.domains.modes")
        kernel_data.set_world(modes.set_group_sex, True)
        self.in_h(self.b_id, 1)
        self.wake_a()
        self.assertEqual(self.ended(self.b_id), (False, -1, False))
