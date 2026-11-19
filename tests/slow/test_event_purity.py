# -*- coding: UTF-8 -*-
"""
事件是可以反复求值的纯粹检查
============================
新游戏里博士一次次等待五分钟。内核每一步找事件之前（_fire_event），
挑出至少有一个事件条件成立的前 6 个状态，在每个上检查：
- P1：每个事件的条件对每个角色连求两次，两次答案相同；求值前后缓存（界面状态与全局设置除外）、内核状态、
  随机数状态、待交给内核的打断与自动存档的请求都不变。
- P2：内核照常触发第一个成立的事件之后，再跑一次它的处理函数并套用效果：缓存、内核状态、待交的打断与存档请求不变
  （处理函数可以抽随机数决定结果的大小，随机数状态不比）。
- P3：触发的那一次里没有为写打开文件、没有请求自动存档、没有让玩家选择，套用效果后计划队列里没有留下打断。
"""

import importlib
from collections.abc import Callable
from types import ModuleType
from unittest import mock

from tests.slow.base import SlowTestCase

STATES = 6
""" 检查的状态数 """
WAITS = 60
""" 最多等待的次数 """


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


class EventPurityTest(SlowTestCase):
    """事件的条件与处理函数在真实的游戏状态上是纯的"""

    def test_events_are_pure(self) -> None:
        """6 个有事件成立的状态上 P1、P2、P3 都成立"""
        core = game("Script.Kernel.core")
        constant = game("Script.Core.constant")
        pick_guard = game("tests.pick_guard")
        plan_queue = game("Script.Modules.gameplay_resolution.plan_queue")
        autosave = game("Script.Modules.save_load.autosave")
        player_pick = game("Script.Modules.tk_ui.player_pick")
        snapshot_states = game("tests.snapshot_states")
        problems: list[str] = []
        checked: list[str] = []
        original = core._fire_event

        def stable(fp: tuple) -> tuple:
            return (fp[0], fp[1], fp[3], fp[4])

        def check_conditions() -> bool:
            game_state = core._context.state
            before = pick_guard.fingerprint()
            held = False
            for name in core._events:
                first = core._trigger(name, game_state)
                if core._trigger(name, game_state) != first:
                    problems.append(f"P1 {name}: 两次答案不同")
                held = held or first is not None
            if pick_guard.fingerprint() != before:
                problems.append(f"P1 条件求值改了状态，时钟 {game_state.clock}")
            return held

        def fire_and_check() -> bool:
            if len(checked) >= STATES or not check_conditions():
                return original()
            fired: list[tuple[str, object]] = []
            game_state = core._context.state
            for name in core._events:
                data = core._trigger(name, game_state)
                if data is not None:
                    fired.append((name, data))
                    break
            asked: list[int] = []
            requested = autosave._requested
            chooser: Callable[[], None] = player_pick.chooser

            def counted() -> None:
                asked.append(1)
                chooser()

            with (
                pick_guard.file_writes() as wrote,
                mock.patch.object(player_pick, "chooser", counted),
            ):
                result = original()
            name, data = fired[0]
            label = f"{name} {data} 时钟 {game_state.clock}"
            if wrote or asked or plan_queue._pending:
                problems.append(
                    f"P3 {label}: 写文件 {wrote} 选择 {len(asked)} 打断 {len(plan_queue._pending)}"
                )
            if autosave._requested and not requested:
                problems.append(f"P3 {label}: 请求了自动存档")
            core._context.boundary = core._context.state
            after = stable(pick_guard.fingerprint())
            try:
                core._loop_calls(
                    core.apply_effects, core._resolve(core.Event(name), data)
                )
            except Exception as exc:
                problems.append(
                    f"P2 {label}: 再跑一次抛出 {type(exc).__name__}: {exc}"
                )
            else:
                if stable(pick_guard.fingerprint()) != after:
                    problems.append(f"P2 {label}: 再跑一次改了状态")
            checked.append(label)
            return result

        with mock.patch.object(core, "_fire_event", fire_and_check):
            for _ in range(WAITS):
                if len(checked) >= STATES:
                    break
                snapshot_states.instruct(self.world, constant.Instruct.WAIT)
        self.assertEqual(len(checked), STATES, checked)
        self.assertEqual(problems, [], checked)
