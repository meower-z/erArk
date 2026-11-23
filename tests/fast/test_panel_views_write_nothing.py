"""
动力系统管理面板与体检报告的绘制不写游戏状态
============================================
- 动力系统管理的概览、发电设施管理与蓄电池管理绘制到按下「返回」，缓冲区里没有写入。
  储能超限且动力区 1 级配 5 台副源石反应炉时同样没有写入。
- 体检报告绘制到按下「返回」，缓冲区里没有写入。
- 玩家查看体检报告时，交互对象记入出具过体检报告的干员名单。
"""

from unittest import mock

from Script.Core import flow_handle
from Script.Kernel import core
from Script.Modules.domains import achievement, power
from Script.Modules.gameplay_resolution import working
from Script.UI.Panel import manage_power_system_panel
from Script.UI.Panel import physical_check_and_manage
from tests import kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

NPC = 1
""" 玩家的交互对象编号 """
WIDTH = 100
""" 面板宽度 """


def _back(return_list: list[str], *args: object) -> str:
    """
    模拟玩家按下「返回」按钮
    Keyword arguments:
    return_list -- 面板按钮的返回值列表，必须包含「返回」
    Return arguments:
    str -- 字符串「返回」
    """
    if "返回" not in return_list:
        raise AssertionError(f"按钮里没有「返回」：{return_list}")
    return "返回"


class PanelViewsWriteNothing(FastTestCase):
    """动力系统管理面板与体检报告绘制不写游戏状态的测试"""

    def setUp(self) -> None:
        """建立博士与一名作为交互对象的干员，并将面板选项输入固定为按下「返回」"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        aim(0, NPC)
        self.enterContext(mock.patch.object(flow_handle, "askfor_all", _back))

    def test_power_panels(self) -> None:
        """储能超限且动力区 1 级配 5 台副源石反应炉时，动力系统三个界面绘制结束均无缓冲区写入"""
        kernel_data.set_facility_level(1, 1)
        kernel_data.put(power.set_plant, aux_reactors=5, batteries=(1, 0, 0))
        top = power.storage_levels("电池容量", int, 0)[0]
        kernel_data.put(power.set_storage, top + 7)
        panel = manage_power_system_panel.Manage_Power_System_Panel(WIDTH)
        for view in (panel.draw, panel._panel_facilities, panel._panel_battery):
            with self.subTest(view.__name__):
                with working.based_on(core.state()) as buffer:
                    view()
                    self.assertEqual(buffer.effects(), ())

    def test_physical_report(self) -> None:
        """draw_report 绘制体检报告不产生缓冲区写入。check_physcial_report 将交互对象记入体检报告干员名单"""
        panel = physical_check_and_manage.Physical_Check_And_Manage_Panel(WIDTH)
        with working.based_on(core.state()) as buffer:
            panel.draw_report(NPC)
            self.assertEqual(buffer.effects(), ())
        with working.based_on(core.state()):
            panel.check_physcial_report()
            self.assertIn(NPC, achievement.get("body_report_chara_count_list"))
