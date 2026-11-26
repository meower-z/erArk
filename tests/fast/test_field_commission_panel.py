"""
外勤委托与编队载具面板交互测试
==============================
本测试复用 CommissionCase，导入 Script.UI.Panel 下的 field_commission_panel 与 commission_squad_panel。
测试以 bind 经 flow_handle.bind_cmd 注册按钮回调，并以 _answer 应答选项及执行对应命令。
列表用例绘制外勤委托主列表并选择「返回」。选人用例经 adjust_team 验证必需干员自动入选与工作筛选。
派遣用例从主列表进入委托 9101，依次选人、选载具、执行委托并返回，断言按钮列表变化、派遣状态与面板编号。
"""

from unittest import mock

from Script.Config import game_config
from Script.Core import constant, flow_handle
from Script.Modules.domains import commission, warehouse
from Script.UI.Moudle import draw, view
from Script.UI.Panel import commission_squad_panel, field_commission_panel
from tests import kernel_data
from tests.fast.test_field_commission_services import RES, CommissionCase

WIDTH = 100
""" 传给 Field_Commission_Panel 与 CommissionDraw 的面板宽度。 """


def bind(button: draw.CenterButton) -> None:
    """
    调用 flow_handle.bind_cmd，按 button.return_text 将 button.cmd_func 与 button.args 注册到 cmd_map。
    Keyword arguments:
    button -- draw.CenterButton，调用 draw 方法的按钮对象（含子类 draw.LeftButton）
    Return arguments:
    None -- 无返回值
    """
    flow_handle.bind_cmd(button.return_text, button.cmd_func, button.args)


class FieldCommissionPanelTest(CommissionCase):
    """外勤委托主列表、选人、载具与详情派遣面板的交互测试。"""

    def setUp(self) -> None:
        """
        调用父类 setUp，重命名编号大于 9000 的委托，添加 2 辆空闲 91 号载具并将 RES 库存设为 5。
        初始化 answers 与 seen，以 bind 替换两类按钮 draw、以 _answer 替换 askfor_all，设面板编号为 FIELD_COMMISSION。
        """
        super().setUp()
        for cid, data in game_config.config_commission.items():
            if cid > 9000:
                data.name = f"委托{cid}"
        with kernel_data.writing():
            commission.add_vehicle(91, 2, 0)
            warehouse.set(RES, 5)
        self.answers: list[str] = []
        """ 按消费顺序排列的预设按钮返回值文本列表。 """
        self.seen: list[list[str]] = []
        """ 记录 _answer 每次收到的按钮返回值列表副本。 """
        for button in (draw.CenterButton, draw.LeftButton):
            self.enterContext(mock.patch.object(button, "draw", bind))
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self._answer)
        )
        self.enterContext(
            mock.patch.object(
                view, "now_panel_id", constant.Panel.FIELD_COMMISSION
            )
        )

    def _answer(self, return_list: list[str], *args: object) -> str:
        """
        断言存在剩余预设应答并取出队首项，再断言该项在 return_list 中并记录 return_list 的副本。
        从 flow_handle.cmd_map 取出对应命令（未绑定时取 null_func），清空 cmd_map 后执行并返回应答。
        Keyword arguments:
        return_list -- list[str]，面板本次给出的按钮返回值列表
        args -- tuple[object, ...]，其余位置参数，本方法不使用
        Return arguments:
        str -- 当前取出的预设按钮返回值文本
        """
        self.assertTrue(self.answers, f"缺少针对 {return_list} 的预设应答")
        answer = self.answers.pop(0)
        self.assertIn(answer, return_list)
        self.seen.append(list(return_list))
        command = flow_handle.cmd_map.get(answer, flow_handle.null_func)
        flow_handle.cmd_map.clear()
        command()
        return answer

    def test_list_back_returns_to_scene(self) -> None:
        """绘制外勤委托主列表并选择「返回」，断言按钮返回值列表与返回后的面板编号 IN_SCENE。"""
        self.answers = ["返回"]
        with kernel_data.writing():
            field_commission_panel.Field_Commission_Panel(WIDTH).draw()
        self.assertEqual(
            self.seen,
            [["\n特殊外勤", "\n委托9202", "\n委托9105", "\n委托9101", "返回"]],
        )
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)

    def test_squad_page_auto_picks_required_operator(self) -> None:
        """打开委托 9105 的选人页并切换工作筛选，断言干员按钮列表变化及必需干员 3 自动入选并任队长。"""
        owner = field_commission_panel.CommissionDraw(
            9105, WIDTH, True, False, 0
        )
        self.answers = ["filter_work", "返回"]
        commission_squad_panel.adjust_team(owner, 9105)
        names = [[key for key in keys if key.isdigit()] for keys in self.seen]
        self.assertEqual(names, [["3", "1", "2"], []])
        self.assertEqual((owner.send_npc_list, owner.lead_chara_id), ([3], 3))

    def test_list_buttons_dispatch_chosen_team(self) -> None:
        """
        从外勤委托主列表进入委托 9101，依次选定干员 1、2 与载具 91 并执行委托，最后从主列表返回场景。
        断言应答耗尽，详情、载具与派遣后主列表的按钮正确，且进行中队伍、载具占用、资源与面板编号符合预期。
        """
        self.answers = [
            "\n委托9101",
            "调整派遣人员",
            "1",
            "2",
            "返回",
            "调整使用载具",
            "\n91+1",
            "返回",
            "执行委托",
            "返回",
        ]
        with kernel_data.writing():
            field_commission_panel.Field_Commission_Panel(WIDTH).draw()
        self.assertEqual(self.answers, [])
        self.assertNotIn("执行委托", self.seen[1])
        self.assertEqual(self.seen[6], ["\n91+1", "\n91-1", "返回"])
        self.assertIn("执行委托", self.seen[8])
        self.assertEqual(
            self.seen[9], ["\n特殊外勤", "\n委托9202", "\n委托9105", "", "返回"]
        )
        self.assertEqual(list(commission.ongoing()[9101].team), [1, 2])
        self.assertEqual(commission.vehicles()[91], (2, 1))
        self.assertEqual(warehouse.amount(RES), 0)
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
