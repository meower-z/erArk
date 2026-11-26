"""
核外进程状态复原测试
====================
本测试验证 tests.outside_cache.fresh 将进程输入历史 input_cache.input_cache、
未结算输入 orders._unsettled 与界面临时状态 view.now_panel_id 复原为初始值。
"""

from Script.Core import input_cache
from Script.Modules.tk_ui import orders
from Script.UI.Moudle import view
from tests import outside_cache
from tests.fast.base import FastTestCase


class OutsideCacheTest(FastTestCase):
    """outside_cache.fresh 复原核外进程状态的测试。"""

    def test_fresh_clears_process_input_state(self) -> None:
        """写入 input_cache.input_cache、orders._unsettled 与 view.now_panel_id 后调用 fresh，断言三者恢复初始值。"""
        input_cache.input_cache.extend(["1", "2"])
        orders._unsettled.append("3")
        view.now_panel_id = 99
        outside_cache.fresh()
        self.assertEqual(input_cache.input_cache, [])
        self.assertEqual(orders._unsettled, [])
        self.assertEqual(view.now_panel_id, 0)
