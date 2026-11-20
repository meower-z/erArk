# -*- coding: UTF-8 -*-
"""
存档与读档带着内核的 GameState，读档后从玩家的选择接着跑
========================================================
- 读档：新游戏里等待三次后经 save_handle 写盘存档，再等待一次后读档。
  读档后内核的时钟与游戏时间是存档时的。各干员的内核行动（行动id、行动数据、结束时刻）与角色数据和存档时相同。玩家的行动结束在当前时钟。
- 读带 open 键的内核状态：等待三次后存档，给文件 "2" 里每个角色加上 open（玩家为 None，干员的行为还在进行时为真，
  否则为 None）。读档后没有 open，open 为真的干员保留行为，其余角色是同样起止的 kernel.Idle；
  之后等待一次，每个行动至多收尾一次，读档前已收尾的行动不会第二次收尾，读档时还在进行的干员行为各在结束时收尾。
- 读旧存档：等待一次后，从缓存里删掉计划队列与玩家的寻路，再写盘存档。存档后给一名干员排一个睡觉，给博士留一段寻路。
  读档后，这名干员没有排着的行动，博士没有寻路。
- 新周目：等待 12 次后，给一名干员排一个睡觉，给博士留一段寻路，再开新周目。
  新周目开局时，这名干员没有排着的行动，博士没有寻路，面板回到场景主面板。
  新周目的游戏时间早于开新周目之前的时钟。之后等待一次，每个角色的内核行动都开始在新周目开局的时钟与当前时钟之间。
"""

import importlib
import json
import os
import shutil
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
    各干员在内核里的行动与角色数据（行动只比结束时刻）
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
        """读档后内核的时钟、游戏时间与各干员的行动都是存档时的，玩家的行动结束在此刻"""
        from Script.Design import game_time

        core = game("Script.Kernel.core")
        save_handle = game("Script.Core.save_handle")
        self.wait(3)
        saved = core.state()
        saved_time = game_time.now()
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
        resumed = core.state()
        self.assertEqual(resumed.clock, saved.clock)
        self.assertEqual(game_time.now(), saved_time)
        self.assertEqual(npc_view(resumed), npc_view(saved))
        player = resumed.characters[PLAYER].action
        self.assertEqual(player.start + player.duration, resumed.clock)

    def test_open_keys_load_and_each_end_runs_once(self) -> None:
        """
        存档的内核状态带 open 键：读档后按 open 换掉行动、去掉 open，角色的其余数据留着。
        等待一次，每个行动至多收尾一次。收尾的行动是读档时还在进行的干员行为或读档后开始的，前者此后结束的都收尾了
        """
        kernel = game("Script.Kernel.core")
        actions = game("Script.Modules.gameplay_resolution.actions")
        save_handle = game("Script.Core.save_handle")
        index = game("Script.Modules.save_load.index")
        kernel_state = game("Script.Modules.save_load.kernel_state")
        self.wait(3)
        clock = kernel.state().clock
        save_handle.establish_save(SAVE_ID)
        try:
            path = os.path.join(index.path(SAVE_ID), kernel_state.SAVE_FILE)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            running = set()
            kept = {
                who: set(c["data"]) for who, c in data["characters"].items()
            }
            for who, c in data["characters"].items():
                act = c["action"]
                opened = (
                    who != PLAYER
                    and act["action_id"] == actions.behave.name
                    and act["start"] + act["duration"] > clock
                )
                c["data"]["open"] = True if opened else None
                if opened:
                    running.add(who)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            self.wait()
            save_handle.input_load_save(SAVE_ID)
        finally:
            shutil.rmtree(
                save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True
            )
        loaded = kernel.state()
        self.assertTrue(running, "存档时有行为还在进行的干员")
        self.assertEqual(
            {who: set(c.data) for who, c in loaded.characters.items()},
            {who: kept[who] for who in loaded.characters},
        )
        self.assertEqual(
            {
                who
                for who, c in loaded.characters.items()
                if c.action.action_id == actions.behave.name
            },
            running,
        )
        ends: list[tuple[str, int, int]] = []
        name = actions.behave.name + ".end"
        saved = kernel._bodies[name]

        def spy(act: "core.Action") -> "core.Effects":
            ends.append((act.who, act.start, act.duration))
            return saved(act)

        with mock.patch.dict(kernel._bodies, {name: spy}):
            self.wait()
        now = kernel.state().clock
        self.assertEqual(len(ends), len(set(ends)), "每个行动至多收尾一次")
        held = {
            who: (c.action.start, c.action.duration)
            for who, c in loaded.characters.items()
            if who in running
        }
        self.assertEqual(
            [
                end
                for end in ends
                if held.get(end[0]) != end[1:] and end[1] < loaded.clock
            ],
            [],
            "收尾的是读档时还在进行的行为或读档后开始的行动",
        )
        due = {
            who
            for who, (start, length) in held.items()
            if start + length <= now
        }
        self.assertLessEqual(
            due, {end[0] for end in ends if held.get(end[0]) == end[1:]}
        )

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
        self.assertEqual(plan_queue.planned(npc), [])
        self.assertIsNone(vars(self.cache).get("player_route"))

    def test_old_save_load_drops_queue_and_route(self) -> None:
        """读一个没有计划队列与寻路的存档后，读档前排下的行动与寻路都不留下"""
        save_handle = game("Script.Core.save_handle")
        self.wait()
        for key in ("plan_queue", "player_route"):
            vars(self.cache).pop(key, None)
        save_handle.establish_save(SAVE_ID)
        vars(self.cache)["plan_queue"] = {}
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
        world = game("tests.world")
        saves: list[tuple[str, str, int, int]] = []

        def record(save_id: str) -> None:
            """记下存档id，与那一刻玩家的内核行动的行动id、时长和时钟"""
            game_state = core.state()
            act = game_state.characters[PLAYER].action
            saves.append(
                (save_id, act.action_id, act.duration, game_state.clock)
            )

        slept_at = core.state().clock
        with mock.patch.object(save_handle, "establish_save", record):
            self.world.player.press("1小时", "确定")
            world.act(
                lambda: handle_instruct.handle_instruct(constant.Instruct.SLEEP)
            )
            self.show_panel()
            self.world.player.check_done()
            self.assertEqual(len(saves), 1, saves)
            self.assertEqual(
                saves[0],
                ("auto", core.idle.name, 0, slept_at + 60),
                "睡觉收尾之后、玩家选行动时存档：玩家的行动已换成 0 分钟的 kernel.Idle",
            )
            self.assertEqual(slept_at + 60, core.state().clock, "存档时已睡醒")
            self.wait()
            self.assertEqual(len(saves), 1, saves)

    def test_new_round_restarts_kernel_from_cache(self) -> None:
        """新周目开局时没有上一周目排下的行动与寻路。等待一次后，每个角色的内核行动都开始在新周目里"""
        from Script.Design import game_time

        core = game("Script.Kernel.core")
        constant = game("Script.Core.constant")
        new_round = game("Script.UI.Panel.new_round")
        self.wait(12)
        before = core.state().clock
        npc = self.queue_and_route()
        self.world.player.press("醒来")
        new_round.New_Round_Handle().start_new_round()
        self.world.player.check_done()
        self.assert_no_queue_or_route(npc)
        self.assertEqual(self.cache.now_panel_id, constant.Panel.IN_SCENE)
        round_start = game_time.minutes(game_time.now())
        self.assertLess(round_start, before, "新周目的游戏时间回到开局")
        self.wait()
        resumed = core.state()
        for who, character in resumed.characters.items():
            start = character.action.start
            self.assertTrue(
                round_start <= start <= resumed.clock,
                f"{who} 的行动开始于 {start}，新周目 {round_start}，此刻 {resumed.clock}",
            )
