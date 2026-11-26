"""
Script.Settle.default 事件选项无界面与回调测试
==============================================
OptionFatherUiFreeTest 在独立无界面子进程中测试 BehaviorEffect.OPTION_FATER 结算效果。
该子进程放行 Script.Settle 并拦截其余默认受禁模块。子进程失败时，setUpClass 抛出 RuntimeError。
测试核对无受禁模块加载或尝试导入记录，以及 add_time 为 0 与 5 时的事件选项回调结果。
EventOptionsTkAdapterTest 在本进程验证 tk_ui/callbacks.py 向 settle_hooks 登记的事件选项绘制回调。
"""

from typing import Any, cast
from unittest import mock

from Script.Config import normal_config
from Script.Modules.gameplay_resolution import settle_hooks
from Script.UI.Panel import event_option_panel
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
settle_hooks.on_event_options(opened.append)
with mock.patch.dict(game_config.config_event, {{{EVENT!r}: event}}):
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
        """
        断言 add_time 为 0 时未触发事件选项回调（opened_0 为 []）。
        断言 add_time 为 5 时以角色编号 3 触发一次事件选项回调（opened_5 为 [3]）。
        """
        self.assertEqual(self.payload["opened_0"], [])
        self.assertEqual(self.payload["opened_5"], [3])


class EventOptionsTkAdapterTest(FastTestCase):
    """tk_ui/callbacks.py 向 settle_hooks 登记的事件选项 Tk 绘制适配回调测试。"""

    def test_event_options_draw_line_then_panel(self) -> None:
        """
        断言 emit_event_options(3) 按序调用 line_feed.draw()、Event_option_Panel(3, width) 及其 draw()。
        其中 width 取自 normal_config.config_normal.text_width。
        """
        calls = mock.Mock()
        with (
            mock.patch.object(event_option_panel, "line_feed") as line_feed,
            mock.patch.object(
                event_option_panel, "Event_option_Panel"
            ) as panel,
        ):
            calls.attach_mock(line_feed, "line_feed")
            calls.attach_mock(panel, "panel")
            settle_hooks.emit_event_options(3)
        width = normal_config.config_normal.text_width
        self.assertEqual(
            calls.mock_calls,
            [
                mock.call.line_feed.draw(),
                mock.call.panel(3, width),
                mock.call.panel().draw(),
            ],
        )
