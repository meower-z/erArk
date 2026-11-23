"""
新周目换态后执行唤醒输出与周目成就提示的测试
============================================
本测试在慢速层新游戏环境中通过 world.act 执行 New_Round_Handle.start_new_round。测试监控
core.reset_state 期间的文本打印、按钮绘制与输入等待，验证换态过程不触发界面交互。测试同时断言
编号 2 的周目成就已记录，且其获得提示出现在 [醒来] 按钮之后。
"""

import importlib
from collections.abc import Callable
from types import ModuleType
from unittest import mock

from tests import world
from tests.slow.base import SlowTestCase

ROUND_TWO = 2
""" 周目类成就中编号 2 的成就 ID（二周目达成）。 """


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


class NewRoundWakesAfterResetTest(SlowTestCase):
    """验证新周目换态期间不打印、不绘按钮也不等输入，且编号 2 周目成就提示出现在 [醒来] 之后。"""

    def test_wake_runs_after_reset(self) -> None:
        """
        预设按下 [醒来] 并以玩家选择方式运行 start_new_round，拦截打印、按钮与输入调用。
        断言 core.reset_state 期间无界面交互、编号 2 周目成就已达成，且其提示文本晚于 [醒来] 出现。
        """
        core = game("Script.Kernel.core")
        flow_handle = game("Script.Core.flow_handle")
        io_init = game("Script.Core.io_init")
        achievement = game("Script.Modules.domains.achievement")
        game_config = game("Script.Config.game_config")
        new_round = game("Script.UI.Panel.new_round")
        events: list[tuple[str, str, bool]] = []
        inside = False
        reset_state = core.reset_state

        def resetting(*args: object) -> None:
            nonlocal inside
            inside = True
            try:
                reset_state(*args)
            finally:
                inside = False

        def recording(
            kind: str, real: Callable[..., object]
        ) -> Callable[..., object]:
            def call(*args: object, **kwargs: object) -> object:
                events.append((kind, str(args[0]) if args else "", inside))
                return real(*args, **kwargs)

            return call

        self.assertFalse(achievement.done(ROUND_TWO))
        handle = new_round.New_Round_Handle()
        self.world.player.press("[醒来]")
        with (
            mock.patch.object(core, "reset_state", resetting),
            mock.patch.object(
                io_init, "era_print", recording("print", io_init.era_print)
            ),
            mock.patch.object(
                io_init,
                "io_print_cmd",
                recording("button", io_init.io_print_cmd),
            ),
            mock.patch.object(
                flow_handle,
                "order_deal",
                recording("input", flow_handle.order_deal),
            ),
        ):
            world.act(handle.start_new_round)
        self.world.player.check_done()
        self.assertEqual([e for e in events if e[2]], [])
        self.assertTrue(achievement.done(ROUND_TWO))
        name = game_config.config_achievement[ROUND_TWO].name
        texts = [text for _, text, _ in events]
        wake = next(i for i, t in enumerate(texts) if "[醒来]" in t)
        pressed = next(
            i for i in range(wake, len(events)) if events[i][0] == "input"
        )
        notice = next(i for i, t in enumerate(texts) if name in t)
        self.assertLess(pressed, notice)
