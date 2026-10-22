# -*- coding: UTF-8 -*-
"""
干员袭击事件选「逆来顺受」后门仍锁着的回归测试
==============================================
干员处在要找博士逆推的状态（npc_masturebate_for_player，游戏里由状态机「进入要自慰或要逆推状态」按攻略等级随机设定，这里直接布置），
与博士单独在一间房里时，触发「{Name}最近有些欲求不满……向{PlayerName}扑了过来」事件。事件按干员当时的行为分 move 与 wait 两个，
各有一个「逆来顺受」选项。博士锁门后选「逆来顺受」，选项结算完门必须仍然锁着（谁锁的门谁来开），
选项的其他结算也生效：干员开启主动H，两人进入H。

开新游戏后，博士走进会议室：
- wait：杜宾已在屋里，博士用「锁上门内侧锁」锁门，这条指令经主循环结算时触发事件。
- move：博士先锁门，再在「干员位置一览」里把杜宾召集到自己当前位置，杜宾走进锁着的会议室时触发事件。
"""
from tests.slow.base import SlowTestCase

ROOM = ["中枢", "会议室"]


class AmbushEventKeepsDoorLockedTest(SlowTestCase):
    """「逆来顺受」选项不解开博士锁上的门"""

    def setUp(self):
        """
        博士走进会议室；杜宾要找博士逆推；记录结算过的事件
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        from Script.Design import settle_behavior

        self.walk(ROOM)
        self.operator_id = self.npc("杜宾")
        self.operator = self.cache.character_data[self.operator_id]
        self.operator.sp_flag.npc_masturebate_for_player = True
        self.settled_events = []
        """ handle_event_data 结算过的事件id """
        real_handle = settle_behavior.handle_event_data

        def record_handle(event_id, *args, **kwargs):
            """
            记录型包装：记下事件id，照常结算
            Keyword arguments:
            event_id -- 事件id
            Return arguments:
            与 handle_event_data 相同
            """
            self.settled_events.append(event_id)
            return real_handle(event_id, *args, **kwargs)

        settle_behavior.handle_event_data = record_handle

    def check_ambush(self, behavior_id: str):
        """
        核对：结算了该行为的「逆来顺受」选项，门仍锁着，杜宾开启主动H
        Keyword arguments:
        behavior_id -- 事件所属的行为id（move 或 wait）
        Return arguments:
        无
        """
        from Script.Config import game_config

        self.world.player.check_done()
        options = [event_id for event_id in self.settled_events if game_config.config_event[event_id].text.startswith("逆来顺受|")]
        self.assertEqual([game_config.config_event[event_id].behavior_id for event_id in options], [behavior_id])
        self.assertEqual(self.world.scene(ROOM).close_flag, 1)
        self.assertTrue(self.operator.h_state.npc_active_h)
        self.assertTrue(self.operator.sp_flag.is_h)
        self.assertEqual(self.cache.character_data[0].target_character_id, self.operator_id)

    def test_wait_option_keeps_door_locked(self):
        """杜宾在屋里，锁门指令里触发 wait 事件，选「逆来顺受」后门仍锁着"""
        from Script.Core import constant

        self.world.move(self.operator_id, ROOM)
        self.world.player.press("逆来顺受")
        self.instruct(constant.Instruct.DOOR_LOCK_INNER)
        self.check_ambush("wait")

    def test_move_option_keeps_door_locked(self):
        """博士锁门后召集杜宾，她走进来时触发 move 事件，选「逆来顺受」后门仍锁着"""
        from Script.Core import constant

        self.instruct(constant.Instruct.DOOR_LOCK_INNER)
        self.world.player.press("召集到自己当前位置", "杜宾", "返回")
        self.instruct(constant.Instruct.ALL_NPC_POSITION)
        self.show_panel()
        self.world.player.press("逆来顺受")
        self.assertTrue(self.wait_until(lambda: self.operator.sp_flag.is_h, 60), f"杜宾在 {self.operator.position}")
        self.check_ambush("move")
