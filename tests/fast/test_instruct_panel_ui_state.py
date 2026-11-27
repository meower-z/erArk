# -*- coding: UTF-8 -*-
"""
操作菜单面板界面状态测试
========================
InstructPanelUiStateTest 验证 SeeInstructPanel.handle_instruct 在派发前维护的两项界面状态。
测试覆盖长等待开启跳过暂停、短等待与切换指令不调用跳过暂停、切换指令更新非H开关与幼年阶段拦截。
同时验证直接调用 handle_instruct.handle_instruct 不改写上述两项界面状态与 view.now_panel_id，并校验其面板返回值。
"""

from unittest import mock

from Script.Config import normal_config
from Script.Core import constant, flow_handle
from Script.Modules.gameplay_resolution import ui_hooks
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
from Script.UI.Moudle import view
from Script.UI.Panel import see_instruct_panel
from tests import chara_abilities as ca
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

TARGET = 1
""" 交互对象角色编号（阿米娅） """
CHILD = 102
""" 幼年阶段年龄素质编号（102 幼女） """
NON_H = constant.Instruct.SWITCH_TO_NON_H_INTERFACE
""" 切换到非H指令 id """
H = constant.Instruct.SWITCH_TO_H_INTERFACE
""" 切换到H指令 id """


class InstructPanelUiStateTest(FastTestCase):
    """SeeInstructPanel.handle_instruct 界面状态更新与后端直调不写界面状态的测试。"""

    def setUp(self) -> None:
        """
        调用父类准备，创建角色 0（博士）与角色 1（阿米娅），并将玩家交互对象设为角色 1。
        将 view.show_non_h_in_hidden_sex 临时设为 False，并以副本替换两项指令过滤字典。
        用模拟对象替换 flow_handle.set_skip_pauses，并以当前文本宽度创建 SeeInstructPanel 实例。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, "阿米娅")
        aim(0, TARGET)
        self.enterContext(
            mock.patch.object(view, "show_non_h_in_hidden_sex", False)
        )
        setting = normal_config.system_setting
        for name in ("instruct_type_filter", "instruct_sex_type_filter"):
            self.enterContext(
                mock.patch.object(setting, name, dict(getattr(setting, name)))
            )
        self.skip = self.enterContext(
            mock.patch.object(flow_handle, "set_skip_pauses")
        )
        self.panel = see_instruct_panel.SeeInstructPanel(
            normal_config.config_normal.text_width
        )

    def pick(self, instruct_id: str) -> int:
        """
        经操作菜单面板执行指定指令，断言其抛出 player_pick.Chosen，并返回选定行动的分钟时长。
        Keyword arguments:
        instruct_id -- str，待执行的指令 id
        Return arguments:
        int -- 抛出异常中选定行动的分钟时长
        """
        with self.assertRaises(player_pick.Chosen) as chosen:
            self.panel.handle_instruct(instruct_id)
        return chosen.exception.action.duration

    def test_long_waits_turn_on_skip_pauses(self) -> None:
        """验证经面板执行 WAIT_1_HOUR 与 WAIT_6_HOUR 返回 60 与 360 分钟，各以 True 调用 set_skip_pauses 一次。"""
        for instruct_id, minutes in (
            (constant.Instruct.WAIT_1_HOUR, 60),
            (constant.Instruct.WAIT_6_HOUR, 360),
        ):
            with self.subTest(instruct=instruct_id):
                self.skip.reset_mock()
                self.assertEqual(self.skip.call_args_list, [])
                self.assertEqual(self.pick(instruct_id), minutes)
                self.assertEqual(self.skip.call_args_list, [mock.call(True)])

    def test_other_instructs_leave_skip_pauses(self) -> None:
        """验证经面板执行 WAIT（5 分钟）与两条切换指令时不调用 set_skip_pauses。"""
        self.assertEqual(self.pick(constant.Instruct.WAIT), 5)
        for instruct_id in (NON_H, H):
            self.panel.handle_instruct(instruct_id)
        self.skip.assert_not_called()

    def test_switch_instructs_set_show_non_h(self) -> None:
        """验证 NON_H 与 H 经面板使 view.show_non_h_in_hidden_sex 与 hidden_sex_show_non_h() 依次为 True、False。"""
        for instruct_id, shown in ((NON_H, True), (H, False)):
            with self.subTest(instruct=instruct_id):
                self.assertIsNot(view.show_non_h_in_hidden_sex, shown)
                self.panel.handle_instruct(instruct_id)
                self.assertIs(view.show_non_h_in_hidden_sex, shown)
                self.assertIs(ui_hooks.hidden_sex_show_non_h(), shown)

    def test_child_stage_target_keeps_show_non_h(self) -> None:
        """验证交互对象带幼年素质 102 时，经面板执行 NON_H 与 H 均保持 view.show_non_h_in_hidden_sex 不变。"""
        ca.talent(TARGET)[CHILD] = 1
        for instruct_id, kept in ((NON_H, False), (H, True)):
            with self.subTest(instruct=instruct_id):
                view.show_non_h_in_hidden_sex = kept
                self.panel.handle_instruct(instruct_id)
                self.assertIs(view.show_non_h_in_hidden_sex, kept)

    def test_backend_dispatch_writes_no_ui_state(self) -> None:
        """验证直接调用 handle_instruct 处理 NON_H、H 与 WAIT_1_HOUR 不改非H开关，且不调用 set_skip_pauses。"""
        handle_instruct.handle_instruct(NON_H)
        self.assertIs(view.show_non_h_in_hidden_sex, False)
        view.show_non_h_in_hidden_sex = True
        handle_instruct.handle_instruct(H)
        self.assertIs(view.show_non_h_in_hidden_sex, True)
        with self.assertRaises(player_pick.Chosen):
            handle_instruct.handle_instruct(constant.Instruct.WAIT_1_HOUR)
        self.skip.assert_not_called()

    def test_backend_dispatch_returns_panel_untouched(self) -> None:
        """验证直调 handle_instruct 返回 SEE_ATTR 面板，对 NON_H 与幼年拦截的 UNDRESS 返回 None，不改当前面板。"""
        self.enterContext(
            mock.patch.object(view, "now_panel_id", constant.Panel.IN_SCENE)
        )
        self.assertEqual(
            handle_instruct.handle_instruct(constant.Instruct.SEE_ATTR),
            constant.Panel.SEE_ATTR,
        )
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        self.assertIsNone(handle_instruct.handle_instruct(NON_H))
        ca.talent(TARGET)[CHILD] = 1
        self.assertIsNone(
            handle_instruct.handle_instruct(constant.Instruct.UNDRESS)
        )
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
