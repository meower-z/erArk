# -*- coding: UTF-8 -*-
"""
幼年阶段（素质101婴儿、102幼女）的H闸测试
========================================
开新游戏后，把一名干员改成幼年阶段（年龄素质101~108清零后只留101或102），放到博士所在的场景。
博士以她为交互对象时，H类指令在Tk指令面板的过滤与Web的两处指令前提判断中都不成立，交给 handle_instruct 也不调用指令的处理函数。
NPC的状态机选出以她为对象的H类行为时，行为换成发呆；她自己的普通等待不变。
测试里没有任何H类指令或行为真正执行或结算：指令的处理函数换成只记下调用的替身，状态机只赋予行为。
"""
from unittest import mock

from tests.slow.base import SlowTestCase

AGE_TALENTS = range(101, 109)
""" 年龄素质 """
H_INSTRUCTS = ("kiss", "touch_head", "imprisonment_h")
""" 抽查的H类指令：两条只要求交互对象5、6正常或无意识（kiss、touch_head），一条走合作或监禁的或分支（imprisonment_h） """
MASSAGE_THERAPIST = 171
""" 工作：按摩师 """


class ChildStageHGateTest(SlowTestCase):
    """H类指令不对幼年阶段的交互对象列出或执行；NPC的状态机不以她为H类行为的对象"""

    def make_child(self, stage: int, name: str) -> int:
        """
        把一名干员改成幼年阶段并放到博士所在的场景
        Keyword arguments:
        stage -- 年龄素质，101或102
        name -- 干员名字
        Return arguments:
        int -- 角色id
        """
        child_id = self.npc(name)
        child = self.cache.character_data[child_id]
        for talent_id in AGE_TALENTS:
            child.talent[talent_id] = 0
        child.talent[stage] = 1
        self.world.move(child_id, self.cache.character_data[0].position)
        return child_id

    def assert_h_instructs_closed(self, stage: int):
        """
        博士以幼年阶段的干员为交互对象：抽查的H类指令在三处列表判断中都不成立，handle_instruct 也不调用它们的处理函数
        Keyword arguments:
        stage -- 年龄素质，101或102
        Return arguments:
        无
        """
        from Script.Core import constant
        from Script.Design import web_interaction_manager
        from Script.System.Instruct_System import handle_instruct, see_instruct_panel
        from Script.System.Web_Draw_System import tab_menu

        pl = self.cache.character_data[0]
        child_id = self.make_child(stage, "杜宾")
        # 监禁让 imprisonment_h 的「合作或监禁」或分支成立
        self.cache.character_data[child_id].sp_flag.imprisonment = 1
        pl.target_character_id = child_id
        listed = {
            "Tk面板": [i for i in H_INSTRUCTS if see_instruct_panel.judge_single_instruct_filter(i, {}, 0, use_type_filter_flag=False)[0]],
            "Web交互管理器": [i for i in H_INSTRUCTS if web_interaction_manager._check_single_instruct_premise(i, {})],
            "Web选项卡": [i for i in H_INSTRUCTS if tab_menu._check_single_instruct_premise(i, {})],
            "执行": [],
        }
        stubs = {i: (lambda instruct_id=i: listed["执行"].append(instruct_id)) for i in H_INSTRUCTS}
        with mock.patch.dict(constant.handle_instruct_data, stubs):
            for instruct_id in H_INSTRUCTS:
                handle_instruct.handle_instruct(instruct_id)
        self.assertEqual(listed, {"Tk面板": [], "Web交互管理器": [], "Web选项卡": [], "执行": []}, f"T|{stage}：各处列出或执行的H类指令")

    def test_h_instructs_closed_for_t102_target(self):
        """交互对象是102：抽查的H类指令不列出也不执行"""
        self.assert_h_instructs_closed(102)

    def test_h_instructs_closed_for_t101_target(self):
        """交互对象是101：抽查的H类指令不列出也不执行"""
        self.assert_h_instructs_closed(101)

    def test_h_instructs_closed_in_debug_mode(self):
        """debug模式下交互对象是102：抽查的H类指令在三处判断中仍不成立"""
        from Script.Design import web_interaction_manager
        from Script.System.Instruct_System import see_instruct_panel
        from Script.System.Web_Draw_System import tab_menu

        self.cache.debug_mode = True
        self.cache.character_data[0].target_character_id = self.make_child(102, "杜宾")
        listed = {
            "Tk面板": [i for i in H_INSTRUCTS if see_instruct_panel.judge_single_instruct_filter(i, {}, 0, use_type_filter_flag=False)[0]],
            "Web交互管理器": [i for i in H_INSTRUCTS if web_interaction_manager._check_single_instruct_premise(i, {})],
            "Web选项卡": [i for i in H_INSTRUCTS if tab_menu._check_single_instruct_premise(i, {})],
        }
        self.assertEqual(listed, {"Tk面板": [], "Web交互管理器": [], "Web选项卡": []}, "debug模式下各处列出的H类指令")

    def test_npc_state_machine_does_not_target_child(self):
        """按摩师状态机在场景里找到102为对象时，行为换成发呆，对象改回自己"""
        from Script.Core import constant

        child_id = self.make_child(102, "杜宾")
        self.cache.character_data[child_id].work.work_type = MASSAGE_THERAPIST
        npc_id = self.npc("阿米娅")
        npc = self.cache.character_data[npc_id]
        self.world.move(npc_id, self.cache.character_data[0].position)
        constant.handle_state_machine_data[constant.StateMachine.WORK_MASSAGE](npc_id)
        self.assertEqual((npc.behavior.behavior_id, npc.target_character_id), (constant.Behavior.SHARE_BLANKLY, npc_id), "按摩师状态机之后的（行为，对象）")

    def test_child_keeps_ordinary_wait(self):
        """102自己的等待30分钟不是H类行为：行为与时长不变"""
        from Script.Core import constant

        child_id = self.make_child(102, "杜宾")
        child = self.cache.character_data[child_id]
        constant.handle_state_machine_data[constant.StateMachine.WAIT_30_MIN](child_id)
        self.assertEqual((child.behavior.behavior_id, child.behavior.duration), (constant.Behavior.WAIT, 30), "102等待30分钟之后的（行为，时长）")
