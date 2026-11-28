"""
Script.Settle.default 事件选项无界面测试
========================================
OptionFatherUiFreeTest 在独立无界面子进程中测试 BehaviorEffect.OPTION_FATER 结算效果。
该子进程放行 Script.Settle 并拦截其余默认受禁模块，校验未加载受禁模块及时间推进后才调用 emit_event_options。
子进程失败时，setUpClass 抛出 RuntimeError。
"""

from typing import Any, cast

from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import BLOCKED, run_ui_free

EVENT = "settle-option-father"
""" 测试用合成事件的事件编号。 """
CHILD_RUN = f"""
import datetime
from unittest import mock
import Script.Settle.default
from Script.Config import game_config
from Script.Core import constant_effect, game_type
from Script.Design import settle_behavior
from Script.Modules.gameplay_resolution import settle_hooks

event = game_type.Event()
event.uid = {EVENT!r}
event.effect = [str(constant_effect.BehaviorEffect.OPTION_FATER)]
opened = []
with (
    mock.patch.dict(game_config.config_event, {{{EVENT!r}: event}}),
    mock.patch.object(settle_hooks, "emit_event_options", opened.append),
):
    for add_time in (0, 5):
        opened.clear()
        settle_behavior.handle_event_data(
            {EVENT!r},
            3,
            add_time,
            game_type.CharacterStatusChange(),
            datetime.datetime(2025, 1, 1),
        )
        payload[f"opened_{{add_time}}"] = list(opened)
"""
""" 在无界面子进程中导入 Script.Settle.default 并运行 OPTION_FATER 结算用例的代码片段。 """


class OptionFatherUiFreeTest(FastTestCase):
    """Script.Settle.default 中 OPTION_FATER 结算效果的无界面子进程测试。"""

    @classmethod
    def setUpClass(cls) -> None:
        """放行 Script.Settle 并在无界面子进程中执行 CHILD_RUN。子进程失败时抛出 RuntimeError。"""
        super().setUpClass()
        cls.child = run_ui_free(
            CHILD_RUN, boot=True, blocked=BLOCKED - {"Script.Settle"}
        )
        cls.payload = cast(dict[str, Any], cls.child.payload)

    def test_no_blocked_module_loaded(self) -> None:
        """断言子进程未加载也未尝试导入任何受拦截模块。"""
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_option_effect_asks_options_once_time_passes(self) -> None:
        """断言 add_time 为 0 时不调用 settle_hooks.emit_event_options，为 5 时以角色编号 3 调用一次。"""
        self.assertEqual(self.payload["opened_0"], [])
        self.assertEqual(self.payload["opened_5"], [3])
