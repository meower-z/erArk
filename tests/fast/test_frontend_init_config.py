"""前端初始尺寸配置测试：验证小屏钳制、大屏保留配置以及应用钳制宽度后字号设置面板的计算结果。"""

from unittest import mock

from Script.Config import normal_config
from Script.Core import io_init
from Script.Frontend.Tk import screen
from Script.Protocol import ScriptedUiPort, script
from Script.UI.Panel import system_setting
from tests.fast.base import FastTestCase


class FrontendInitConfigTest(FastTestCase):
    """验证 `screen.init_config` 与 `io_init.apply_frontend_config` 对窗口配置与设置面板的影响。"""

    def setUp(self) -> None:
        """设置测试基准窗口与文本宽度配置，并在用例结束时还原 `io_init._port`。"""
        super().setUp()
        normal = normal_config.config_normal
        normal.window_width = 2000
        normal.window_hight = 930
        normal.text_width = 190
        self.enterContext(mock.patch.object(io_init, "_port", io_init._port))

    def test_small_screen_clamps_window_and_font(self) -> None:
        """断言 1280x720 屏幕将 2000x930 配置钳制为 1250x690，并算出字号 12 与输入框字号 10。"""
        config = screen.init_config(normal_config.config_normal, 1280, 720)
        io_init.apply_frontend_config(config)
        normal = normal_config.config_normal
        self.assertEqual(
            (
                normal.window_width,
                normal.window_hight,
                normal.text_width,
                normal.font_size,
                normal.order_font_size,
            ),
            (1250, 690, 190, 12, 10),
        )

    def test_large_screen_keeps_configured_window(self) -> None:
        """断言 3840x2160 屏幕保留 2000x930 配置窗口尺寸并算出字号 20。"""
        config = screen.init_config(normal_config.config_normal, 3840, 2160)
        self.assertEqual(
            (config.window_width, config.window_height, config.font_size),
            (2000, 930, 20),
        )

    def test_font_size_setting_uses_clamped_width(self) -> None:
        """断言应用小屏钳制配置后，在设置面板将字号设为 25 会按钳制宽度 1250 写入 `text_width` 100。"""
        io_init.apply_frontend_config(
            screen.init_config(normal_config.config_normal, 1280, 720)
        )
        self.world.chara(0, "博士")
        io_init.configure(ScriptedUiPort(script("25")))
        written: list[dict[str, str]] = []
        self.enterContext(
            mock.patch.object(
                normal_config, "write_local_config", written.append
            )
        )
        system_setting.System_Setting_Panel(80).change_font_size()
        self.assertEqual(written, [{"font_size": "25", "text_width": "100"}])
