# -*- coding: UTF-8 -*-
"""
选择隐奸模式的面板不列出携带模式
================================
开新游戏后打开 debug 模式（列出的模式都可以选），打开选择隐奸模式的面板，按「返回」退出：
从邀请隐奸打开、从被发现面板打开两种情况下，面板都列出 [1]~[4] 四个模式按钮，按钮与文字里都没有携带模式。
"""
from unittest import mock

from tests.slow.base import SlowTestCase

PANEL_WIDTH = 100
""" 面板的绘制宽度 """
MODE_BUTTON_LIST = ("[1]不隐藏", "[2]干员隐藏", "[3]博士隐藏", "[4]双方隐藏")
""" 面板列出的四个模式按钮的开头 """
CARRY_MODE_TEXT = "携带"
""" 携带模式按钮与说明里的字样 """


class HiddenSexNoCarryModeTest(SlowTestCase):
    """选择隐奸模式的面板只列出四个模式，不列出携带模式"""

    def mode_panel_buttons(self, sex_be_discovered_flag: bool) -> tuple:
        """
        打开选择隐奸模式的面板，记下它画出的按钮与文字，按「返回」退出
        Keyword arguments:
        sex_be_discovered_flag -- 是否从被发现面板打开
        Return arguments:
        tuple -- (按钮文字的列表, 面板画出的文字)
        """
        from Script.Core import io_init
        from Script.System.Sex_System import hidden_sex_panel

        player_input = self.world.player
        player_input.screen.clear()
        button_text_list = []
        real_print_cmd = io_init.io_print_cmd

        def record_print_cmd(cmd_str, *args, **kwargs):
            """
            记下按钮文字后照常交给 PlayerInput
            Keyword arguments:
            cmd_str -- 按钮文字
            Return arguments:
            无
            """
            button_text_list.append(str(cmd_str))
            return real_print_cmd(cmd_str, *args, **kwargs)

        player_input.press("返回")
        with mock.patch.object(io_init, "io_print_cmd", side_effect=record_print_cmd):
            hidden_sex_panel.Select_Hidden_Sex_Mode_Panel(PANEL_WIDTH, sex_be_discovered_flag=sex_be_discovered_flag).draw()
        player_input.check_done()
        return button_text_list, "".join(player_input.screen)

    def test_no_carry_mode(self):
        """两种打开方式下都只列出四个模式按钮，没有携带模式"""
        self.cache.debug_mode = True
        for sex_be_discovered_flag in (False, True):
            label = "从被发现面板打开" if sex_be_discovered_flag else "从邀请隐奸打开"
            button_text_list, screen_text = self.mode_panel_buttons(sex_be_discovered_flag)
            for mode_button in MODE_BUTTON_LIST:
                self.assertTrue(any(text.startswith(mode_button) for text in button_text_list), f"{label}：列出了 {mode_button}")
            self.assertFalse([text for text in button_text_list if CARRY_MODE_TEXT in text], f"{label}：没有携带模式的按钮")
            self.assertNotIn(CARRY_MODE_TEXT, screen_text, f"{label}：面板文字里没有携带模式")
