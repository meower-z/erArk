# -*- coding: UTF-8 -*-
"""
config.ini 默认值与 config.local.ini 玩家设置的读写
===================================================
每个测试在自己的临时目录写一份 config.ini，并把游戏根目录指向这个目录。
ReadConfig 检查 init_normal_config 怎样合并两份文件。
PanelWritesLocal 检查设置面板改字体大小、DPI 缩放和语言后写下的文件。
这两类测试继承 GameReadTestCase，按游戏的方式读两份文件。
HarnessReadsDefaults 检查复原小世界时只读 config.ini。
"""

import os
import tempfile
from unittest import mock

from Script.Config import normal_config
from Script.Core import flow_handle, game_path_config
from Script.UI.Panel import system_setting
from tests.fast.base import FastTestCase

DEFAULTS = """[game]
language = zh_CN
window_width = 2000
text_width = 190
font_size = 21
tk_dpi = 100
"""
""" 每个测试写进临时目录的 config.ini 内容 """


class ConfigLocalIniTestCase(FastTestCase):
    """
    配置文件读写测试的基类
    每个测试使用自己临时目录里的 config.ini。
    测试结束后，内存里的通用配置复原为测试前的内容。
    """

    def setUp(self) -> None:
        """复原小世界，把游戏根目录指向一个临时目录，并在那里写入 DEFAULTS 作为 config.ini"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(
            mock.patch.object(game_path_config, "game_path", folder)
        )
        snapshot = dict(vars(normal_config.config_normal))
        self.addCleanup(self.restore_config, snapshot)
        self.ini_path = os.path.join(folder, "config.ini")
        self.local_path = os.path.join(folder, "config.local.ini")
        with open(self.ini_path, "w", encoding="utf8") as ini_file:
            ini_file.write(DEFAULTS)
        with open(self.ini_path, "rb") as ini_file:
            self.ini_bytes = ini_file.read()

    @staticmethod
    def restore_config(snapshot: dict[str, object]) -> None:
        """
        把内存里的通用配置换回 snapshot 里的属性
        Keyword arguments:
        snapshot -- 测试前通用配置的属性字典
        Return arguments:
        无
        """
        vars(normal_config.config_normal).clear()
        vars(normal_config.config_normal).update(snapshot)

    def write_local(self, text: str) -> None:
        """
        用 text 覆盖临时目录里的 config.local.ini
        Keyword arguments:
        text -- 文件内容
        Return arguments:
        无
        """
        with open(self.local_path, "w", encoding="utf8") as local_file:
            local_file.write(text)

    def read_local(self) -> str:
        """
        读出临时目录里 config.local.ini 的全文
        Keyword arguments:
        无
        Return arguments:
        str -- 文件内容
        """
        with open(self.local_path, encoding="utf8") as local_file:
            return local_file.read()

    @staticmethod
    def reread() -> None:
        """
        清空内存里的通用配置，再用 init_normal_config 从文件重新读取
        Keyword arguments:
        无
        Return arguments:
        无
        """
        vars(normal_config.config_normal).clear()
        normal_config.init_normal_config()

    def assert_ini_untouched(self) -> None:
        """
        断言临时 config.ini 的字节与 setUp 写入后相同
        Keyword arguments:
        无
        Return arguments:
        无
        """
        with open(self.ini_path, "rb") as ini_file:
            self.assertEqual(ini_file.read(), self.ini_bytes)


class GameReadTestCase(ConfigLocalIniTestCase):
    """
    按游戏的方式读配置的测试基类
    每个测试期间删掉 DEFAULTS_ONLY_ENV 指定的环境变量，测试结束后复原。
    这期间 init_normal_config 读 config.ini 和 config.local.ini 两份文件。
    """

    def setUp(self) -> None:
        """
        做完基类的准备后，删掉 DEFAULTS_ONLY_ENV 指定的环境变量
        mock.patch.dict 在测试结束后复原 os.environ。
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.enterContext(mock.patch.dict(os.environ))
        os.environ.pop(normal_config.DEFAULTS_ONLY_ENV, None)


class ReadConfig(GameReadTestCase):
    """init_normal_config 合并 config.ini 与 config.local.ini 的测试"""

    def test_defaults_only(self) -> None:
        """没有 config.local.ini 时，init_normal_config 读到 config.ini 的值，并把数字读成 int"""
        self.reread()
        self.assertEqual(normal_config.config_normal.font_size, 21)
        self.assertEqual(normal_config.config_normal.language, "zh_CN")

    def test_local_overrides(self) -> None:
        """config.local.ini 只写 font_size 时，读到 config.local.ini 的 font_size 和 config.ini 的 tk_dpi"""
        self.write_local("[game]\nfont_size = 30\n")
        self.reread()
        self.assertEqual(normal_config.config_normal.font_size, 30)
        self.assertEqual(normal_config.config_normal.tk_dpi, 100)


class PanelWritesLocal(GameReadTestCase):
    """
    设置面板改字体大小、DPI 缩放和语言的测试
    每个测试都检查 config.ini 一字不变。
    """

    def setUp(self) -> None:
        """
        造玩家角色 0，读入临时配置，再建系统设置面板与游戏基础设置面板
        System_Setting_Panel 构造时读取玩家角色 0 的数据。
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.world.chara(0)
        normal_config.init_normal_config()
        self.system_panel = system_setting.System_Setting_Panel(100)
        self.basic_panel = system_setting.Game_Basic_Settings_Panel(100)

    def test_font_size_creates_local(self) -> None:
        """没有 config.local.ini 时，改字体大小新建这个文件并写入 font_size 与按 window_width 算出的 text_width"""
        with mock.patch.object(flow_handle, "askfor_str", return_value="30"):
            self.system_panel.change_font_size()
        self.assert_ini_untouched()
        self.assertTrue(self.read_local().startswith("[game]\n"))
        self.reread()
        self.assertEqual(normal_config.config_normal.font_size, 30)
        self.assertEqual(
            normal_config.config_normal.text_width, int(2000 / 30 * 2)
        )

    def test_dpi(self) -> None:
        """改 DPI 缩放后，重新读取得到新的 tk_dpi"""
        with mock.patch.object(flow_handle, "askfor_str", return_value="150"):
            self.system_panel.change_dpi_size()
        self.assert_ini_untouched()
        self.reread()
        self.assertEqual(normal_config.config_normal.tk_dpi, 150)

    def test_language(self) -> None:
        """改语言后，重新读取得到新的 language"""
        self.basic_panel.change_language_cmd("en_US")
        self.assert_ini_untouched()
        self.reread()
        self.assertEqual(normal_config.config_normal.language, "en_US")

    def test_other_local_keys_survive(self) -> None:
        """先改 DPI 缩放再改语言后，config.local.ini 原有的 extra_key 和第一次写入的 tk_dpi 都还在"""
        self.write_local("[game]\nextra_key = 7\n")
        with mock.patch.object(flow_handle, "askfor_str", return_value="150"):
            self.system_panel.change_dpi_size()
        self.basic_panel.change_language_cmd("en_US")
        self.assert_ini_untouched()
        self.reread()
        self.assertEqual(vars(normal_config.config_normal)["extra_key"], 7)
        self.assertEqual(normal_config.config_normal.tk_dpi, 150)
        self.assertEqual(normal_config.config_normal.language, "en_US")


class HarnessReadsDefaults(ConfigLocalIniTestCase):
    """
    复原小世界时读配置的测试
    这个类的测试沿用导入 tests 包时设好的环境变量。
    """

    def test_reset_ignores_local(self) -> None:
        """config.local.ini 改了 font_size 和 language 时，复原小世界后读到的仍是 config.ini 的值"""
        self.write_local("[game]\nfont_size = 30\nlanguage = en_US\n")
        self.world.reset()
        self.assertEqual(normal_config.config_normal.font_size, 21)
        self.assertEqual(normal_config.config_normal.language, "zh_CN")
