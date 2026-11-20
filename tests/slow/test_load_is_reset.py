# -*- coding: UTF-8 -*-
"""
读档是一次 Reset
================
存档写在临时目录里（index.SAVE_DIR 换成它），存档面板从第 0 页显示，经主界面的「读写存档」指令在玩家的选择里操作。
- 浏览：打开存档列表、点开存档、返回、退出列表：缓存（界面状态除外）、内核状态与存档目录都不变。
- 读档：等待一次后在存档面板里确认读取：内核状态等于存档时的 GameState；Reset 时 core.state() 与
  game_time.now() 已是存档的时钟；这次选择（从选择开始、经 Reset、到玩家再次选行动）没有行动开始；读档后回到主界面。
- 旧存档（没有文件 "2"）：读档后内核的时钟是存档头的游戏时间，角色是缓存里的名单，全局数据有 ticked 与 settled_day。
- 旧存档，系统设置 14 打开：读档时修复跑一次，跑时游戏时间已是存档的；读档后的静态检查没有时钟健全性（BEHAV-02）的失败。
"""

import importlib
import os
import sys
import tempfile
from types import ModuleType
from typing import TYPE_CHECKING
from unittest import mock

from tests.slow.base import SlowTestCase

if TYPE_CHECKING:
    from Script.Kernel import core

SAVE_ID = "0"
""" 存档面板第 0 页的第一个存档位 """


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


def listing(folder: str) -> list[tuple[str, int]]:
    """
    目录下每个文件的相对路径与大小
    Keyword arguments:
    folder -- 目录
    Return arguments:
    list -- (相对路径, 字节数)，按路径排序
    """
    return sorted(
        (
            os.path.relpath(os.path.join(root, name), folder),
            os.path.getsize(os.path.join(root, name)),
        )
        for root, _, names in os.walk(folder)
        for name in names
    )


class LoadIsResetTest(SlowTestCase):
    """存档面板读档：浏览只读，确认读取换掉整个 GameState"""

    def setUp(self) -> None:
        """开新游戏，存档目录换成临时目录，存档面板从第 0 页显示，Reset 时记下内核时钟的探针登记进 LOAD_ORDER"""
        super().setUp()
        index = game("Script.Modules.save_load.index")
        save_handle = game("Script.Core.save_handle")
        load_order = game("Script.Modules.load_order")
        kernel = game("Script.Kernel.core")
        game_time = game("Script.Design.game_time")
        start_gate = game("Script.Modules.gameplay_resolution.start_gate")
        self.folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", self.folder))
        self.enterContext(
            mock.patch.object(save_handle, "get_last_save_page", return_value=0)
        )
        self.resets: list[tuple[int, int, int]] = []
        """ 每次 Reset 时的 (core.state().clock, game_time.now() 的分钟, start_gate.calls) """
        spy = ModuleType("tests.slow.load_is_reset_spy")
        sys.modules[spy.__name__] = spy

        def seen(new: "core.GameState") -> "core.GameState":
            """Reset 的输出钩子：记下此刻的时钟与开始门的计数"""
            self.resets.append(
                (
                    kernel.state().clock,
                    game_time.minutes(game_time.now()),
                    start_gate.calls,
                )
            )
            return new

        seen.__module__ = spy.__name__
        kernel.output_hook(kernel.reset)(seen)
        self.enterContext(
            mock.patch.object(
                load_order, "LOAD_ORDER", (*load_order.LOAD_ORDER, spy)
            )
        )

    def instruct(self, instruct_name: str, *presses: str) -> None:
        """
        像玩家在主界面点下指令一样执行它，之后依次按下 presses
        Keyword arguments:
        instruct_name -- constant.Instruct 的成员名
        presses -- 按钮文字的一部分
        """
        from tests.snapshot_states import instruct

        constant = game("Script.Core.constant")
        instruct(self.world, getattr(constant.Instruct, instruct_name), presses)

    def save(self, old: bool = False) -> "core.GameState":
        """
        等待一次后存档，old 为真时删掉存档里的文件 "2" 与存档头里的标记，做成旧存档。再等待一次，忘掉此前的 Reset 记录
        Keyword arguments:
        old -- 是否做成旧存档
        Return arguments:
        GameState -- 存档时的内核状态
        """
        core = game("Script.Kernel.core")
        save_handle = game("Script.Core.save_handle")
        index = game("Script.Modules.save_load.index")
        kernel_state = game("Script.Modules.save_load.kernel_state")
        self.instruct("WAIT")
        saved = core.state()
        save_handle.establish_save(SAVE_ID)
        if old:
            os.remove(
                os.path.join(self.folder, SAVE_ID, kernel_state.SAVE_FILE)
            )
            head = index.head(SAVE_ID)
            del head[kernel_state.TOKEN]
            index.write_head(SAVE_ID, head)
        self.instruct("WAIT")
        self.assertNotEqual(core.state().clock, saved.clock)
        self.resets.clear()
        return saved

    def load(self) -> None:
        """在存档面板里读取存档 SAVE_ID"""
        self.instruct("SAVE", f"No.{SAVE_ID} ", "读取", "确认读取存档")

    def test_browse_writes_nothing(self) -> None:
        """打开存档列表、点开存档、返回、退出：缓存、内核状态与存档目录都不变"""
        from tests import pick_guard

        core = game("Script.Kernel.core")
        self.save()
        before = (pick_guard.fingerprint(), listing(self.folder))
        self.instruct("SAVE", f"No.{SAVE_ID} ", "返回", "[返回]")
        self.assertEqual(
            (pick_guard.fingerprint(), listing(self.folder)), before
        )
        self.assertEqual(self.resets, [])
        self.assertIs(core.state(), before[0][1])

    def test_load_swaps_whole_state(self) -> None:
        """确认读取：内核状态是存档时的，Reset 看到的时钟是存档的，选择里没有行动开始，回到主界面"""
        core = game("Script.Kernel.core")
        start_gate = game("Script.Modules.gameplay_resolution.start_gate")
        constant = game("Script.Core.constant")
        saved = self.save()
        calls = start_gate.calls
        self.load()
        self.assertEqual(core.state(), saved)
        self.assertEqual(self.resets, [(saved.clock, saved.clock, calls)])
        self.assertEqual(start_gate.calls, calls)
        self.assertEqual(self.cache.now_panel_id, constant.Panel.IN_SCENE)

    def test_old_save_projects_characters(self) -> None:
        """旧存档：内核时钟是存档头的游戏时间，角色是缓存里的名单，全局数据有 ticked 与 settled_day"""
        core = game("Script.Kernel.core")
        actions = game("Script.Modules.gameplay_resolution.actions")
        saved = self.save(old=True)
        self.load()
        loaded = core.state()
        self.assertEqual(loaded.clock, saved.clock)
        self.assertEqual(tuple(loaded.characters), actions.roster())
        self.assertEqual(tuple(loaded.characters), tuple(saved.characters))
        self.assertIsInstance(loaded.data.get(actions.TICKED), int)
        self.assertIsInstance(loaded.data.get(actions.SETTLED_DAY), int)
        self.assertEqual(self.resets[0][:2], (saved.clock, saved.clock))

    def test_old_save_with_self_check(self) -> None:
        """
        系统设置 14 打开时读旧存档：修复跑一次，跑时游戏时间已是存档的；之后的静态检查没有 BEHAV-02 的失败
        """
        static_check = game("Script.Test.Static_Check")
        game_time = game("Script.Design.game_time")
        run_load_repair = static_check.run_load_repair
        repair_clocks: list[int] = []

        def repair() -> list[dict]:
            repair_clocks.append(game_time.minutes(game_time.now()))
            return run_load_repair()

        self.cache.all_system_setting.base_setting[14] = 1
        saved = self.save(old=True)
        with mock.patch.object(static_check, "run_load_repair", repair):
            self.load()
        self.assertEqual(repair_clocks, [saved.clock])
        failed = [
            f for f in static_check.run_all_checks() if f.check_id == "BEHAV-02"
        ]
        self.assertEqual(failed, [])
