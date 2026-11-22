# -*- coding: UTF-8 -*-
"""
指令的子菜单在选择里只读，回答在行动开始时生效
==============================================
每一族子菜单（判定的询问、避孕套、关门、捆绑、体位、角色特殊指令）在 tests.world.act 的一轮选择里跑：
- 在任一层取消：没有 Chosen，这一轮里指纹（pick_guard）不变；act 之后内核状态、时钟、开始门的调用次数都不变，
  所以没有行动、也没有 1 分钟的发呆。
- 确定：Chosen 抛出之前指纹不变；行动开始后效果才在。
- 判定没过（捆绑）：开始的是失败的行为，不换上捆绑。
玩家的输入由打桩的 flow_handle.askfor_all 按安排给出：整数是返回列表里的下标，字符串是返回值。
"""

import json
from collections.abc import Callable
from typing import cast
from unittest import mock

from Script.Config import game_config
from Script.Core import constant, flow_handle
from Script.Kernel import core
from Script.Modules.gameplay_resolution import intent, start_gate
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
from Script.System.Sex_System import bondage_panel, sex_position_panel
from tests import chara_abilities as ca, kernel_data, pick_guard
from tests import world as world_module
from tests.chara_activity import aim
from tests.fast.base import FastTestCase
from Script.UI.Moudle import view
from Script.Modules.domains import (
    action_info,
    activity,
    dirty,
    h_state,
    history,
)
from Script.Modules.domains import scene_state

NPC = 1
""" 玩家的交互对象 """
FIRST_KISS = 4
""" 初吻素质 """
YES, NO = 0, 1
""" 是否两个按钮在返回列表里的下标（判定的询问、关门面板） """

type Answer = int | str


class InstructSubMenuTest(FastTestCase):
    """指令子菜单的取消与确定"""

    def setUp(self) -> None:
        """玩家与当交互对象的干员在场景里，内核停在玩家选行动的时候"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.npc = self.world.chara(NPC, "干员")
        aim(self.player.cid, NPC)
        view.now_panel_id = constant.Panel.IN_SCENE
        world_module.act(player_pick.back)

    def play(
        self, fn: Callable[[], None], *answers: Answer
    ) -> pick_guard.Round:
        """
        玩家跑一轮选择，按安排回答每一次等输入，记下这一轮
        Keyword arguments:
        fn -- 一轮选择
        answers -- 依次的回答
        Return arguments:
        Round -- 这一轮的记录
        """
        planned = list(answers)

        def askfor_all(
            return_list: list[str], *args: object, **kwargs: object
        ) -> str:
            self.assertTrue(planned, f"没有安排的输入：{return_list}")
            want = planned.pop(0)
            if isinstance(want, int):
                return return_list[want]
            self.assertIn(want, return_list)
            return want

        guard = pick_guard.watch()
        with mock.patch.object(flow_handle, "askfor_all", askfor_all):
            world_module.act(guard(fn))
        self.assertEqual(planned, [], "安排的输入没有用掉")
        self.assertEqual(len(guard.rounds), 1)
        return guard.rounds[0]

    def assert_backs_out(
        self, fn: Callable[[], None], *answers: Answer
    ) -> None:
        """
        取消的一轮：没有 Chosen、指纹不变，内核状态与开始门的调用次数不变
        Keyword arguments:
        fn -- 一轮选择
        answers -- 依次的回答，最后一个是取消
        """
        before = (core.state(), start_gate.calls)
        got = self.play(fn, *answers)
        self.assertEqual((got.chosen, got.changed), (False, False))
        self.assertEqual((core.state(), start_gate.calls), before)

    def assert_commits(self, fn: Callable[[], None], *answers: Answer) -> None:
        """
        确定的一轮：Chosen 抛出之前指纹不变
        Keyword arguments:
        fn -- 一轮选择
        answers -- 依次的回答
        """
        got = self.play(fn, *answers)
        self.assertEqual((got.chosen, got.changed), (True, False))

    def instruct(self, instruct_id: str) -> Callable[[], None]:
        """
        一条指令的处理函数
        Keyword arguments:
        instruct_id -- 指令id
        Return arguments:
        Callable -- 处理函数
        """

        def run() -> None:
            constant.handle_instruct_data[instruct_id]()

        return run

    def test_judge_question(self) -> None:
        """夺走初吻的询问：[返回]没有行动也没有发呆；[确定]定下亲吻，开始时不再问"""
        ca.talent(self.npc)[FIRST_KISS] = 1
        world_module.act(player_pick.back)
        self.cache.debug_mode = True
        kiss = self.instruct(constant.Instruct.KISS)
        self.assert_backs_out(kiss, NO)
        self.assert_commits(kiss, YES)
        self.assertEqual(history.recent()[-1], constant.Behavior.KISS)

    def test_condom_decoration(self) -> None:
        """挂上避孕套装饰：选套、选部位两层都能取消；确定后避孕套在行动开始时才挂上"""
        from Script.Modules.domains import player_collection
        from tests import kernel_data

        self.cache.debug_mode = True
        kernel_data.put(player_collection.put, "used_condoms", [10, 20])
        world_module.act(player_pick.back)
        hang = self.instruct(constant.Instruct.HANG_CONDOM_DECORATION)
        self.assert_backs_out(hang, "cancel")
        self.assert_backs_out(hang, "condom_0", "confirm", "cancel")
        self.assert_commits(hang, "condom_0", "confirm", "part_0")
        self.assertEqual(player_collection.get("used_condoms"), [20])
        self.assertEqual(dirty.view(NPC).condom_decoration, {(0, 0): [10]})

    def test_close_door(self) -> None:
        """关门：关不上的地方回答否时取消；回答关门时门在行动开始时关上，记下问过"""
        scene = self.world.scene(activity.position(self.player.cid))
        kernel_data.put(scene_state.set_close_flag, scene.scene_path, 0)
        hypnosis = self.instruct(constant.Instruct.HYPNOSIS_ONE)
        scene.close_type = 0
        self.assert_backs_out(hypnosis, NO)
        self.assertFalse(
            action_info.get(self.player.cid, "ask_close_door_flag")
        )
        scene.close_type = 1
        self.assert_commits(hypnosis, YES)
        self.assertEqual(scene_state.close_flag(scene.scene_path), 1)
        self.assertTrue(action_info.get(self.player.cid, "ask_close_door_flag"))

    def test_bondage(self) -> None:
        """捆绑：判定通过时捆绑在行动开始时换上；判定没过时开始的是失败的行为，不换上捆绑"""
        bondage_id = next(i for i in game_config.config_bondage if i)
        panel = bondage_panel.Bondage_Panel(width=1)
        self.assert_commits(lambda: panel.select_bondage(bondage_id))
        self.assertEqual(
            history.recent()[-1],
            constant.Behavior.HIGH_OBSCENITY_ANUS,
        )
        self.assertEqual(h_state.get(NPC, "bondage"), 0)
        self.cache.debug_mode = True
        self.assert_commits(lambda: panel.select_bondage(bondage_id))
        self.assertEqual(h_state.get(NPC, "bondage"), bondage_id)

    def test_sex_position(self) -> None:
        """换体位：处女的询问能取消；确定后换之前的体位在行动开始时才记下"""
        self.cache.debug_mode = True
        ca.talent(self.npc)[0] = 1
        kernel_data.put(
            h_state.set, 0, current_sex_position=3, pre_sex_position=-1
        )
        world_module.act(player_pick.back)
        position_id = next(
            key
            for key, data in game_config.config_sex_position_data.items()
            if getattr(data, "vaginal_sex_behavior_id", "")
        )
        panel = sex_position_panel.Sex_Position_Panel(
            width=1, change_position=True
        )
        self.assert_backs_out(
            lambda: panel.select_sex_position(position_id), NO
        )
        self.assertEqual(h_state.get(0, "pre_sex_position"), -1)
        self.assert_commits(lambda: panel.select_sex_position(position_id), YES)
        self.assertEqual(h_state.get(0, "pre_sex_position"), 3)

    def test_diy_event(self) -> None:
        """角色特殊指令：选择时玩家的事件不变，行动开始时才记下"""
        event_id = next(
            key
            for key, event in game_config.config_event.items()
            if event.text.count("|") and event.text.split("|")[1].isdigit()
        )
        kernel_data.put(activity.update_event, self.player.cid, event_id="")
        before = pick_guard.fingerprint()
        with self.assertRaises(player_pick.Chosen) as chosen:
            handle_instruct.handle_chara_diy_instruct(event_id)
        self.assertEqual(pick_guard.fingerprint(), before)
        data = json.loads(json.dumps(chosen.exception.action.action_data))
        kernel_data.written(
            handle_instruct.start_instruct, 0, cast(intent.Intent, data)
        )
        self.assertEqual(
            (
                activity.event(self.player.cid).event_id,
                activity.event(self.player.cid).chara_diy_event_flag,
            ),
            (event_id, True),
        )
