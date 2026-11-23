"""
后端界面回调登记测试
====================
验证设定表补齐提示与 Reset 前端步骤通过登记函数接入界面。
"""

from types import MappingProxyType
from unittest import mock

from Script.Core import get_text, save_handle
from Script.Design import attr_calculation
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import playthrough
from Script.Modules.save_load import reset
from Script.UI.Moudle import draw
from tests import kernel_data
from tests.fast.base import FastTestCase


class BackendUiCallbacksTest(FastTestCase):
    """验证 playthrough 提示回调与 reset 前端步骤的登记行为"""

    def setUp(self) -> None:
        """载入游戏模块，写满生殖方式表，并将 draw.NormalDraw 替换为记录器"""
        super().setUp()
        core.load(load_order.LOAD_ORDER)
        self.default = attr_calculation.get_difficulty_setting_zero()
        self.missing = min(self.default)
        with kernel_data.writing():
            playthrough.set_settings(
                playthrough.BIRTH_TYPE,
                attr_calculation.get_birth_type_setting_zero(),
            )
        self.drawn: list[tuple[str, str]] = []
        drawn = self.drawn

        class Recorder:
            """记录每次绘制的样式与文本的替身类"""

            def __init__(self) -> None:
                self.style = ""
                self.text = ""

            def draw(self) -> None:
                drawn.append((self.style, self.text))

        self.enterContext(mock.patch.object(draw, "NormalDraw", Recorder))
        self.text = get_text._("\n难度设置已更新，如有需要请手动修改\n")

    def adopt(self) -> int:
        """
        写入缺少一项的难度表，并以版本 12 的空存档字典调用 adopt_old_save
        Return arguments:
        int -- adopt_old_save 返回的项数
        """
        partial = dict(self.default)
        del partial[self.missing]
        with kernel_data.writing():
            playthrough.set_settings(playthrough.DIFFICULTY, partial)
        with kernel_data.writing():
            count = playthrough.adopt_old_save({}, 12)
        return count

    def test_fill_draws_gold_notice(self) -> None:
        """验证补齐难度表时以 gold_enrod 样式绘制提示，且齐全的生殖方式表不触发提示"""
        self.assertEqual(self.adopt(), 1)
        self.assertEqual(self.drawn, [("gold_enrod", self.text)])
        self.assertEqual(
            playthrough.settings(playthrough.DIFFICULTY), self.default
        )

    def test_fill_without_ui_and_with_handler(self) -> None:
        """
        验证未登记回调时能补齐设定表且不触发绘制。
        随后验证通过 on_filled 登记的函数会收到提示文本且不触发界面绘制。
        """
        with mock.patch.object(playthrough, "_notices", []):
            self.assertEqual(self.adopt(), 1)
            self.assertEqual(
                playthrough.settings(playthrough.DIFFICULTY), self.default
            )
            self.assertEqual(self.drawn, [])
            seen: list[str] = []
            playthrough.on_filled(seen.append)
            self.assertEqual(self.adopt(), 1)
            self.assertEqual(seen, [self.text])
            self.assertEqual(self.drawn, [])

    def test_frontend_step_missing_raises(self) -> None:
        """验证未登记前端步骤时，new_round 原因的 Reset 会抛出含 new_round 的 RuntimeError"""
        empty = core.GameState(
            core.state().clock, MappingProxyType({}), MappingProxyType({})
        )
        with (
            mock.patch.object(reset, "_frontend", {}),
            self.assertRaisesRegex(RuntimeError, "new_round"),
        ):
            core.reset_state(empty, {"cause": "new_round", "inherit": {}})

    def test_missing_panel_stops_load_before_install(self) -> None:
        """验证读档 Reset 缺 panel 登记时在 install_save 前报 RuntimeError 且不改变内核状态"""
        before = core.state()
        empty = core.GameState(
            before.clock, MappingProxyType({}), MappingProxyType({})
        )
        install = mock.MagicMock()
        with (
            mock.patch.object(save_handle, "install_save", install),
            mock.patch.object(reset, "_frontend", {"new_round": mock.Mock()}),
            self.assertRaisesRegex(RuntimeError, "panel"),
        ):
            core.reset_state(empty, {"cause": "load", "save": "1"})
        install.assert_not_called()
        self.assertIs(core.state(), before)
