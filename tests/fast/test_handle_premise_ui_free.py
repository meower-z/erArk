"""
隐奸非H开关查询与前提测试
=========================
- 界面回调（ui_hooks）：验证未登记查询回调时开关查询与 SHOW 前提返回 False 且 HIDE 前提返回 True。
- 界面回调（ui_hooks）：验证登记查询回调后，查询函数返回该回调给出的布尔值。
- Tk 界面回调（tk_ui.callbacks）：验证经 load_order 登记后，对应前提与处理函数随 view 开关值变化。
"""

from unittest import mock

from Script.Core import constant_promise
from Script.Design import handle_premise
from Script.Design.handle_premise import handle_premise_other
from Script.Modules.gameplay_resolution import ui_hooks
from Script.UI.Moudle import view
from tests.fast.base import FastTestCase

SHOW = constant_promise.Premise.SHOW_NON_H_IN_HIDDEN_SEX
""" 测试用的“隐奸中显示非H指令”前提枚举项 """
HIDE = constant_promise.Premise.NOT_SHOW_NON_H_IN_HIDDEN_SEX
""" 测试用的“不在隐奸中显示非H指令”前提枚举项 """


class HiddenSexToggleHookTest(FastTestCase):
    """界面回调模块（ui_hooks）隐奸非H开关查询在无回调与有回调时的测试"""

    def setUp(self) -> None:
        """将 ui_hooks._show_non_h_queries 暂时替换为空列表以便隔离测试"""
        super().setUp()
        self.enterContext(
            mock.patch.object(ui_hooks, "_show_non_h_queries", [])
        )

    def test_unregistered_query_is_false(self) -> None:
        """验证未登记查询回调时，开关查询与 SHOW 前提返回 False、HIDE 前提返回 True"""
        self.assertIs(ui_hooks.hidden_sex_show_non_h(), False)
        self.assertIs(handle_premise.handle_premise(SHOW, 0), False)
        self.assertIs(handle_premise.handle_premise(HIDE, 0), True)

    def test_registered_query_value_is_returned(self) -> None:
        """验证登记函数返回原回调对象，且开关查询返回该回调给出的布尔值"""
        query = mock.Mock(return_value=True)
        self.assertIs(ui_hooks.on_hidden_sex_show_non_h(query), query)
        self.assertIs(ui_hooks.hidden_sex_show_non_h(), True)
        query.return_value = False
        self.assertIs(ui_hooks.hidden_sex_show_non_h(), False)


class TkHiddenSexToggleTest(FastTestCase):
    """经 load_order 登记的 Tk 隐奸非H开关查询回调行为测试"""

    def setUp(self) -> None:
        """记录 view.show_non_h_in_hidden_sex 的初值并在测试结束后恢复"""
        super().setUp()
        self.addCleanup(
            setattr,
            view,
            "show_non_h_in_hidden_sex",
            view.show_non_h_in_hidden_sex,
        )

    def test_premises_follow_view_toggle(self) -> None:
        """
        验证 view.show_non_h_in_hidden_sex 依次取 False、True、False 时，SHOW 前提与处理函数返回同值而 HIDE
        前提返回取反值
        """
        for shown in (False, True, False):
            view.show_non_h_in_hidden_sex = shown
            self.assertIs(handle_premise.handle_premise(SHOW, 0), shown)
            self.assertIs(handle_premise.handle_premise(HIDE, 0), not shown)
            self.assertIs(
                handle_premise_other.handle_show_non_h_in_hidden_sex(0), shown
            )
