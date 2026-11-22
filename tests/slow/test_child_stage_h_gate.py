# -*- coding: UTF-8 -*-
"""
幼年阶段（素质101婴儿、102幼女）的H闸测试
========================================
开新游戏后，把一名干员改成幼年阶段（年龄素质101~108清零后只留101或102），放到博士所在的场景。
博士以她为交互对象时，H类指令在指令面板的过滤中不成立，
交给 handle_instruct 也不调用指令的处理函数。
NPC的状态机选出以她为对象的H类行为时，行为换成发呆；她自己的普通等待在行动开始时不变。
测试里没有任何H类指令或行为真正执行或结算：指令的处理函数换成只记下调用的替身，状态机只赋予行为。
"""

from collections.abc import Mapping
from unittest import mock

from tests import chara_abilities as ca, kernel_data
from tests.chara_activity import aim
from tests.slow.base import SlowTestCase
from tests.kernel_project import activity

AGE_TALENTS = range(101, 109)
""" 年龄素质 """
H_INSTRUCTS = ("kiss", "touch_head", "imprisonment_h")
""" 抽查的H类指令：两条只要求交互对象5、6正常或无意识（kiss、touch_head），
一条走合作或监禁的或分支（imprisonment_h） """
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
        for talent_id in AGE_TALENTS:
            ca.talent(child_id)[talent_id] = 0
        ca.talent(child_id)[stage] = 1
        kernel_data.put(kernel_data.domain("roster").discard, child_id)
        self.world.move(child_id, activity.position(0))
        return child_id

    def assert_h_instructs_closed(self, stage: int) -> None:
        """
        博士以幼年阶段的干员为交互对象：抽查的H类指令在指令面板的过滤中不成立，handle_instruct 也不调用它们的处理函数
        Keyword arguments:
        stage -- 年龄素质，101或102
        Return arguments:
        无
        """
        from Script.Core import constant
        from Script.System.Instruct_System import (
            handle_instruct,
            see_instruct_panel,
        )

        child_id = self.make_child(stage, "杜宾")
        # 监禁让 imprisonment_h 的「合作或监禁」或分支成立
        kernel_data.put(
            kernel_data.domain("flags").set, child_id, imprisonment=True
        )
        aim(0, child_id)
        listed = {
            "Tk面板": [
                i
                for i in H_INSTRUCTS
                if see_instruct_panel.judge_single_instruct_filter(
                    i, {}, 0, use_type_filter_flag=False
                )[0]
            ],
            "执行": [],
        }
        stubs = {
            i: (lambda instruct_id=i: listed["执行"].append(instruct_id))
            for i in H_INSTRUCTS
        }
        with mock.patch.dict(constant.handle_instruct_data, stubs):
            for instruct_id in H_INSTRUCTS:
                handle_instruct.handle_instruct(instruct_id)
        self.assertEqual(
            listed,
            {"Tk面板": [], "执行": []},
            f"T|{stage}：各处列出或执行的H类指令",
        )

    def test_h_instructs_closed_for_t102_target(self) -> None:
        """交互对象是102：抽查的H类指令不列出也不执行"""
        self.assert_h_instructs_closed(102)

    def test_h_instructs_closed_for_t101_target(self) -> None:
        """交互对象是101：抽查的H类指令不列出也不执行"""
        self.assert_h_instructs_closed(101)

    def test_h_instructs_closed_in_debug_mode(self) -> None:
        """debug模式下交互对象是102：抽查的H类指令在指令面板的过滤中仍不成立"""
        from Script.System.Instruct_System import see_instruct_panel

        self.cache.debug_mode = True
        aim(0, self.make_child(102, "杜宾"))
        listed = {
            "Tk面板": [
                i
                for i in H_INSTRUCTS
                if see_instruct_panel.judge_single_instruct_filter(
                    i, {}, 0, use_type_filter_flag=False
                )[0]
            ],
        }
        self.assertEqual(
            listed,
            {"Tk面板": []},
            "debug模式下各处列出的H类指令",
        )

    def test_npc_state_machine_does_not_target_child(self) -> None:
        """按摩师状态机在场景里找到102为对象时，行为换成发呆，对象改回自己"""
        from Script.Modules.domains import chara_life
        from Script.Core import constant

        child_id = self.make_child(102, "杜宾")
        kernel_data.put(chara_life.work_type.set, child_id, MASSAGE_THERAPIST)
        npc_id = self.npc("阿米娅")
        self.world.move(npc_id, activity.position(0))
        kernel_data.written(
            constant.handle_state_machine_data[
                constant.StateMachine.WORK_MASSAGE
            ],
            npc_id,
        )
        self.assertEqual(
            (activity.behavior(npc_id).behavior_id, activity.target(npc_id)),
            (constant.Behavior.SHARE_BLANKLY, npc_id),
            "按摩师状态机之后的（行为，对象）",
        )

    def test_child_keeps_ordinary_wait(self) -> None:
        """102自己的等待30分钟不是H类行为：离线不进在编名册与内核角色表，排定意图经开始门不变"""
        from Script.Core import constant
        from Script.Kernel import core
        from Script.Modules.gameplay_resolution import (
            intent,
            plan_queue,
            start_gate,
        )

        child_id = self.make_child(102, "杜宾")
        kernel_data.written(
            constant.handle_state_machine_data[
                constant.StateMachine.WAIT_30_MIN
            ],
            child_id,
        )
        queued = plan_queue.planned(child_id)
        self.assertEqual(len(queued), 1)
        direct = queued[0].copy()
        direct.pop("queued", None)
        act = intent.behavior_action(child_id, direct)
        assert isinstance(act.action_data, Mapping)
        self.assertFalse(
            start_gate.child_stage_h(
                child_id, constant.Behavior.WAIT, act.action_data
            ),
            "幼年阶段H闸不拦普通等待",
        )
        result = start_gate.gate(act)
        assert isinstance(result, tuple)
        (gated,) = result
        assert isinstance(gated.action_data, Mapping)
        self.assertEqual(
            (gated.action_data["behavior_id"], gated.duration),
            (constant.Behavior.WAIT, 30),
            "102等待30分钟经开始门之后的（行为，时长）",
        )
        self.instruct(constant.Instruct.WAIT)
        self.assertNotIn(str(child_id), core.state().characters)
