# -*- coding: UTF-8 -*-
"""
存档里的内核状态
================
- kernel_state.write 把 core.state() 写成 JSON，read 读回同一个 GameState。
- 玩家选行动时读档（kernel_state.load）中止这次选择，越过插件的 except Exception：行动不开始，
  step() 照常返回，下一步在读回的 GameState 上选行动。
- save_handle 存档再读档：难度取存档里的，系统设置是全局的，读档不换它；内核换成存档时的 GameState。
存档都写在临时目录里（index.SAVE_DIR 换成它）。
"""

import itertools
import sys
import tempfile
from collections.abc import Callable
from types import MappingProxyType, ModuleType
from typing import Any
from unittest import mock

from Script.Core import save_handle
from Script.Design import attr_calculation
from Script.Kernel import core
from Script.Modules.save_load import index, kernel_state
from tests.fast.base import FastTestCase

SAVE_ID = "kernel_state_test"
""" 测试用的存档id """
_serial = itertools.count()


def game(clock: int, ends: dict[str, int]) -> core.GameState:
    """
    一个 GameState：每个角色一个带行动数据的 Idle，在 ends 给出的分钟结束；角色与全局数据里有各种 JSON 值
    Keyword arguments:
    clock -- 时钟
    ends -- 角色键到他的行动结束的分钟
    Return arguments:
    GameState -- 冻结的 GameState
    """
    characters = {
        who: core.Character(
            core.Action(
                who,
                core.idle.name,
                {"behavior_id": "share_blankly", "args": {"ids": (1, 2)}},
                clock,
                end - clock,
            ),
            {"open": True, "note": "博士", "ratio": 0.5, "none": None},
        )
        for who, end in ends.items()
    }
    data: dict[str, core.JSON] = {
        "ticked": clock,
        "settled_day": clock // 1440,
        "nested": ((1,), ()),
    }
    core.reset_state(core.GameState(clock, MappingProxyType(characters), data))
    return core.state()


class KernelStateTest(FastTestCase):
    """存档里的内核状态：写、读、读档"""

    def setUp(self) -> None:
        """复原小世界，存档写进临时目录，换上空的事件表"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.enterContext(mock.patch.object(core, "_events", []))

    def test_write_then_read_gives_equal_state(self) -> None:
        """写下的 GameState 读回来相等，角色的先后不变"""
        saved = game(100, {"0": 100, "2": 130, "1": 160})
        kernel_state.write(SAVE_ID)
        kernel_state.reset_clock(0)
        loaded = kernel_state.read(SAVE_ID)
        self.assertEqual(loaded, saved)
        assert loaded is not None
        self.assertEqual(tuple(loaded.characters), ("0", "2", "1"))

    def test_read_without_kernel_state_is_none(self) -> None:
        """没有文件 "2" 的存档（旧存档）读回 None"""
        self.assertIsNone(kernel_state.read(SAVE_ID))

    def test_load_inside_pick_restarts_step(self) -> None:
        """
        选行动的钩子在 except Exception 里读档：这次选择中止，Work 不开始，step() 返回；
        下一步在读回的 GameState 上选行动，Work 开始
        """
        saved = game(500, {"0": 500})
        kernel_state.write(SAVE_ID)
        game(10, {"0": 10})
        trace: list[tuple[str, int]] = []
        toy = ModuleType(f"tests.fast.kernel_state_toy_{next(_serial)}")
        sys.modules[toy.__name__] = toy

        def own[F: Callable[..., Any]](fn: F) -> F:
            fn.__module__ = toy.__name__
            return fn

        @core.action(f"{toy.__name__}.Work")
        @own
        def work(_act: core.Action) -> core.Effects:
            trace.append(("start", core.state().clock))
            return ()

        @core.input_hook(core.pick_next_action)
        @own
        def pick(who: str) -> core.Intercept[core.Action]:
            trace.append(("pick", core.state().clock))
            if len(trace) == 1:
                try:
                    kernel_state.load(SAVE_ID)
                except Exception:
                    trace.append(("swallowed", 0))
            return core.Intercept(core.new_action(work, who, 5))

        core.load((toy,))
        core.step()
        self.assertEqual(trace, [("pick", 10)])
        self.assertEqual(core.state(), saved)
        core.step()
        self.assertEqual(trace, [("pick", 10), ("pick", 500), ("start", 500)])

    def test_load_takes_difficulty_from_save(self) -> None:
        """
        存档时难度 1 为 3、系统设置 1 号为 0；之后难度改成 1、系统设置改成 1，再读档：
        难度回到 3，系统设置还是 1、还是同一个对象；内核回到存档时的 GameState
        """
        self.world.chara(0, "博士")
        cache = self.cache
        cache.npc_id_got = {0}
        cache.country = attr_calculation.get_country_reset(cache.country)
        cache.difficulty_setting[1] = 3
        cache.all_system_setting.base_setting[1] = 0
        start = core.state().clock
        saved = game(start + 800, {"0": start + 800})
        save_handle.establish_save(SAVE_ID)
        cache.difficulty_setting[1] = 1
        settings = cache.all_system_setting
        settings.base_setting[1] = 1
        game(start + 20, {"0": start + 20})
        save_handle.input_load_save(SAVE_ID)
        self.assertEqual(cache.difficulty_setting[1], 3)
        self.assertIs(cache.all_system_setting, settings)
        self.assertEqual(settings.base_setting[1], 1)
        self.assertEqual(core.state(), saved)
