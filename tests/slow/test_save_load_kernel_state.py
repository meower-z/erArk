# -*- coding: UTF-8 -*-
"""
存档与读档带着内核的 GameState，读档后从玩家的选择接着跑
========================================================
- 读档：新游戏里等待三次后经 save_handle 写盘存档，再等待一次后读档，跑内核到玩家下一次选行动。
  这时时钟与游戏时间是存档时的。各干员的内核行动（行动id、行动数据、结束时刻）与角色数据和存档时相同。玩家的行动结束在当前时钟。
- 读旧存档：等待一次后，从缓存里删掉计划队列与玩家的寻路，再写盘存档。存档后给一名干员排一个睡觉，给博士留一段寻路。
  读档后，这名干员没有排着的行动，博士没有寻路。
- 新周目：等待 12 次后，给一名干员排一个睡觉，给博士留一段寻路，再开新周目。
  新周目开局时，这名干员没有排着的行动，博士没有寻路。
  新周目的游戏时间早于开新周目之前的时钟。之后等待一次，每个角色的内核行动都开始在新周目开局的时钟与当前时钟之间。
"""

import importlib
import shutil
from collections.abc import Mapping
from types import ModuleType
from typing import TYPE_CHECKING
from unittest import mock

from tests.slow.base import SlowTestCase

if TYPE_CHECKING:
    from Script.Kernel import core

SAVE_ID = "test_save_load_kernel_state"
""" 本测试写入 save/ 的存档id，测试结束时删掉 """
PLAYER = "0"
""" 玩家在 GameState.characters 里的键 """


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


def npc_view(game_state: "core.GameState") -> dict:
    """
    各干员在内核里的行动与角色数据。读档后跑内核时，行动按缓存重建，开始时刻是跑内核时的时钟，所以只比结束时刻
    Keyword arguments:
    game_state -- 内核的 GameState
    Return arguments:
    dict -- 角色键 -> (行动id, 行动数据, 结束时刻, 角色数据)，不含玩家
    """
    return {
        who: (
            c.action.action_id,
            c.action.action_data,
            c.action.start + c.action.duration,
            c.data,
        )
        for who, c in game_state.characters.items()
        if who != PLAYER
    }


class SaveLoadKernelStateTest(SlowTestCase):
    """存档带着 GameState，读档与新周目后内核从玩家的选择接着跑"""

    def wait(self, times: int = 1) -> None:
        """
        像玩家在主界面点「等待五分钟」一样等待
        Keyword arguments:
        times -- 次数
        """
        from tests.snapshot_states import instruct

        constant = game("Script.Core.constant")
        for _ in range(times):
            instruct(self.world, constant.Instruct.WAIT)

    def test_load_resumes_at_player_pick(self) -> None:
        """读档后跑内核：时钟、游戏时间与各干员的行动都是存档时的，先轮到玩家选行动"""
        core = game("Script.Kernel.core")
        save_handle = game("Script.Core.save_handle")
        update = game("Script.Design.update")
        self.wait(3)
        saved = core.state()
        saved_time = self.cache.game_time
        self.assertGreater(len(saved.characters), 1, "开局后已有干员")
        save_handle.establish_save(SAVE_ID)
        try:
            self.wait()
            self.assertNotEqual(core.state().clock, saved.clock)
            save_handle.input_load_save(SAVE_ID)
        finally:
            shutil.rmtree(
                save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True
            )
        update.run_kernel("script")
        resumed = core.state()
        self.assertEqual(resumed.clock, saved.clock)
        self.assertEqual(self.cache.game_time, saved_time)
        self.assertEqual(npc_view(resumed), npc_view(saved))
        player = resumed.characters[PLAYER].action
        self.assertEqual(player.start + player.duration, resumed.clock)

    def queue_and_route(self) -> int:
        """
        给 npc_id_got 里除博士外编号最小的干员排一个 60 分钟的睡觉，给博士留一段寻路
        Return arguments:
        int -- 排着睡觉的干员id
        """
        constant = game("Script.Core.constant")
        plan_queue = game("Script.Modules.gameplay_resolution.plan_queue")
        npc = min(i for i in self.cache.npc_id_got if i)
        plan_queue.plan_next(npc, constant.Behavior.SLEEP, 60)
        position = self.cache.character_data[0].position
        vars(self.cache)["player_route"] = (position, position)
        return npc

    def assert_no_queue_or_route(self, npc: int) -> None:
        """
        断言干员 npc 没有排着的行动，博士没有寻路
        Keyword arguments:
        npc -- 干员id
        """
        plan_queue = game("Script.Modules.gameplay_resolution.plan_queue")
        self.assertEqual(plan_queue.planned(npc), ())
        self.assertIsNone(vars(self.cache).get("player_route"))

    def test_old_save_load_drops_queue_and_route(self) -> None:
        """读一个没有计划队列与寻路的存档后，读档前排下的行动与寻路都不留下"""
        save_handle = game("Script.Core.save_handle")
        self.wait()
        for key in ("plan_queue", "player_route"):
            vars(self.cache).pop(key, None)
        save_handle.establish_save(SAVE_ID)
        try:
            npc = self.queue_and_route()
            save_handle.input_load_save(SAVE_ID)
        finally:
            shutil.rmtree(
                save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True
            )
        self.assert_no_queue_or_route(npc)

    def test_autosave_at_player_pick_after_sleep(self) -> None:
        """睡觉结束后，玩家选下一个行动时自动存档一次，存的是睡觉刚结束的 GameState"""
        core = game("Script.Kernel.core")
        constant = game("Script.Core.constant")
        save_handle = game("Script.Core.save_handle")
        handle_instruct = game("Script.System.Instruct_System.handle_instruct")
        saves: list[tuple[str, object, int, int, int]] = []

        def record(save_id: str) -> None:
            """记下存档id，与那一刻玩家的内核行动的行为id、时长、结束时刻和时钟"""
            game_state = core.state()
            act = game_state.characters[PLAYER].action
            data = act.action_data
            assert isinstance(data, Mapping)
            saves.append(
                (
                    save_id,
                    data.get("behavior_id"),
                    act.duration,
                    act.start + act.duration,
                    game_state.clock,
                )
            )

        with mock.patch.object(save_handle, "establish_save", record):
            self.world.player.press("1小时", "确定")
            handle_instruct.handle_instruct(constant.Instruct.SLEEP)
            constant.panel_data[self.cache.now_panel_id]()
            self.world.player.check_done()
            self.assertEqual(len(saves), 1, saves)
            save_id, behavior_id, duration, end, clock = saves[0]
            self.assertEqual(save_id, "auto")
            self.assertEqual(behavior_id, constant.Behavior.SLEEP)
            self.assertEqual(duration, 60)
            self.assertEqual(end, clock, "存档时睡觉已经结束")
            self.assertEqual(clock, core.state().clock, "存档时已睡醒")
            self.wait()
            self.assertEqual(len(saves), 1, saves)

    def test_new_round_restarts_kernel_from_cache(self) -> None:
        """新周目开局时没有上一周目排下的行动与寻路。等待一次后，每个角色的内核行动都开始在新周目里"""
        core = game("Script.Kernel.core")
        constant = game("Script.Core.constant")
        new_round = game("Script.UI.Panel.new_round")
        actions = game("Script.Modules.gameplay_resolution.actions")
        self.wait(12)
        before = core.state().clock
        npc = self.queue_and_route()
        self.world.player.press("醒来")
        new_round.New_Round_Handle().start_new_round()
        self.world.player.check_done()
        self.assert_no_queue_or_route(npc)
        self.cache.now_panel_id = constant.Panel.IN_SCENE
        round_start = actions.minutes(self.cache.game_time)
        self.assertLess(round_start, before, "新周目的游戏时间回到开局")
        self.wait()
        resumed = core.state()
        for who, character in resumed.characters.items():
            start = character.action.start
            self.assertTrue(
                round_start <= start <= resumed.clock,
                f"{who} 的行动开始于 {start}，新周目 {round_start}，此刻 {resumed.clock}",
            )
