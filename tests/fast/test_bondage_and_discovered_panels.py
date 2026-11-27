"""
绳艺与H中被发现面板交互测试
===========================
本测试从 Script.UI.Panel 导入 bondage_panel 与 sex_be_discovered_panel。
测试替换 draw.CenterButton 与 draw.LeftButton 的 draw 方法，经 flow_handle.bind_cmd 注册按钮回调。
Clicks.answer 替换 flow_handle.askfor_all，按预设应答执行对应命令并记录各页按钮文本与返回值列表。
用例覆盖绳艺面板的[指技]与调教室限制及捆绑提交，也覆盖H中被发现面板各模式选项展示与结束H排程。
"""

import unittest
from collections.abc import Callable, Mapping
from unittest import mock

from Script.Core import constant, flow_handle
from Script.Modules.domains import (
    action_info,
    activity,
    flags,
    modes,
)
from Script.Modules.gameplay_resolution import plan_queue
from Script.Modules.tk_ui import player_pick
from Script.UI.Moudle import draw, view
from Script.UI.Panel import bondage_panel, sex_be_discovered_panel
from tests import chara_abilities as ca, kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

WIDTH = 100
""" 传给待测面板的绘制宽度。 """
PARTNER = 1
""" 与玩家交互的角色编号。 """
FINDER = 2
""" 发现玩家H的角色编号。 """
FINGER = 70
""" 能力项[指技]的编号 70。 """
DISCOVERED_TEXTS = {
    "1": "[1]用花言巧语支开对方",
    "2": "[2]迅速地隐藏起来，转为隐奸",
    "3": "[3]光明正大地展示，转为露出",
    "4": "[4]邀请对方加入群交",
    "5": "[5]尴尬地结束H",
}
""" 普通单独H被发现时，返回值 "1" 至 "5" 对应的按钮显示文本映射。 """


def queued(cid: int) -> list[str]:
    """
    按队首到队尾顺序返回指定角色计划队列中的行为编号列表。
    Keyword arguments:
    cid -- int，角色编号
    Return arguments:
    list[str] -- 角色计划队列中各计划项的 behavior_id 列表
    """
    return [item["behavior_id"] for item in plan_queue.planned(cid)]


class Clicks:
    """按预设应答驱动面板按钮交互并记录各页按钮文本与返回值列表的测试辅助类。"""

    def __init__(self, case: unittest.TestCase) -> None:
        """
        绑定测试用例实例，并初始化应答队列、当前页按钮列表、历史页面列表与返回值记录列表。
        Keyword arguments:
        case -- unittest.TestCase，用于执行断言的测试用例实例
        Return arguments:
        None -- 无返回值
        """
        self.case = case
        """ 用于执行断言的测试用例实例。 """
        self.answers: list[str] = []
        """ 按消费顺序排列的预设按钮返回值队列。 """
        self.drawn: list[str] = []
        """ 当前页面已绘制、尚未归档的按钮文本列表。 """
        self.pages: list[list[str]] = []
        """ 每次应答前已绘制的各页按钮文本列表。 """
        self.offers: list[list[str]] = []
        """ 每次应答时面板给出的按钮返回值列表副本。 """

    def bind(self, button: draw.CenterButton) -> None:
        """
        记录按钮显示文本，并按 button.return_text 经 flow_handle.bind_cmd 注册按钮回调与参数。
        Keyword arguments:
        button -- draw.CenterButton，调用 draw 方法的按钮对象（含子类 draw.LeftButton）
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append(button.text)
        flow_handle.bind_cmd(button.return_text, button.cmd_func, button.args)

    def answer(self, return_list: list[str], *args: object) -> str:
        """
        断言存在预设应答并取出队首项，再断言该项在 return_list 中并归档当前页按钮文本与返回值列表。
        从 flow_handle.cmd_map 取出对应命令（未绑定时取 null_func），清空映射并执行命令后返回该应答。
        Keyword arguments:
        return_list -- list[str]，面板本次给出的按钮返回值列表
        args -- tuple[object, ...]，其余位置参数，本方法不使用
        Return arguments:
        str -- 本次消费的预设按钮返回值
        """
        self.case.assertTrue(
            self.answers, f"缺少预设应答，当前可选返回值为 {return_list}"
        )
        wanted = self.answers.pop(0)
        self.case.assertIn(wanted, return_list)
        self.pages.append(self.drawn)
        self.offers.append(list(return_list))
        self.drawn = []
        command = flow_handle.cmd_map.get(wanted, flow_handle.null_func)
        flow_handle.cmd_map.clear()
        command()
        return wanted


class PanelCase(FastTestCase):
    """为面板交互测试提供角色、界面状态与按钮拦截夹具的公共基类。"""

    def setUp(self) -> None:
        """
        注册计划队列与命令映射清理，创建博士、对方与发现者，并将博士的交互目标设为对方。
        将 view.now_panel_id 暂设为 constant.Panel.BONDAGE，并创建 Clicks 辅助对象。
        拦截 draw.CenterButton 与 draw.LeftButton 的 draw 方法，并替换 flow_handle.askfor_all。
        """
        super().setUp()
        self.addCleanup(plan_queue.forget)
        self.addCleanup(flow_handle.cmd_map.clear)
        self.world.chara(0, "博士")
        self.world.chara(PARTNER, "对方")
        self.world.chara(FINDER, "发现者")
        aim(0, PARTNER)
        self.enterContext(
            mock.patch.object(view, "now_panel_id", constant.Panel.BONDAGE)
        )
        self.clicks = Clicks(self)
        """ 驱动面板按钮交互并记录页面的 Clicks 辅助对象。 """
        bind = self.clicks.bind
        for button in (draw.CenterButton, draw.LeftButton):
            self.enterContext(
                mock.patch.object(
                    button, "draw", autospec=True, side_effect=bind
                )
            )
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self.clicks.answer)
        )

    def run_panel(self, show: Callable[[], None], *answers: str) -> None:
        """
        先断言当前面板非 IN_SCENE，再写入预设应答并在 kernel_data.written 内运行 show。
        运行结束后断言预设应答已耗尽且面板处于 IN_SCENE。
        Keyword arguments:
        show -- Callable[[], None]，打开并绘制待测面板的可调用对象
        answers -- tuple[str, ...]，按顺序执行的预设按钮返回值
        Return arguments:
        None -- 无返回值
        """
        self.assertNotEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        self.clicks.answers = list(answers)
        kernel_data.written(show)
        self.assertEqual(self.clicks.answers, [])
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)


class BondagePanelTest(PanelCase):
    """绳艺面板（Bondage_Panel）的按钮展示与提交交互测试。"""

    def test_finger_skill_and_room_limit_choices(self) -> None:
        """
        在[指技]为 0、2、4 且不在调教室时，每轮先将面板设为 BONDAGE 后打开绳艺面板并点选「[返回]」。
        断言各档可选返回值列表，验证低[指技]截断更高等级且需要设施的编号 8 至 10 不出现在列表中。
        """
        expected = {
            0: ["0"],
            2: ["0", "1", "2", "3"],
            4: ["0", "1", "2", "3", "4", "5", "6", "7"],
        }
        for skill, ids in expected.items():
            with self.subTest(skill=skill):
                ca.ability(0)[FINGER] = skill
                view.now_panel_id = constant.Panel.BONDAGE
                self.clicks.offers = []
                self.run_panel(bondage_panel.Bondage_Panel(WIDTH).draw, "返回")
                self.assertEqual(self.clicks.offers, [[*ids, "返回"]])

    def test_button_commits_bind_or_unbind(self) -> None:
        """
        在[指技]为 2 时分别点击编号 1 与 0 的捆绑按钮，断言抛出 player_pick.Chosen 且面板切回 IN_SCENE。
        测试验证选定行为分别为 BIND 与 UNBIND，并核对行为参数中的 bondage_id 与 start。
        """
        ca.ability(0)[FINGER] = 2
        for bondage_id, behavior_id in (
            (1, constant.Behavior.BIND),
            (0, constant.Behavior.UNBIND),
        ):
            with self.subTest(bondage_id=bondage_id):
                view.now_panel_id = constant.Panel.BONDAGE
                self.clicks.answers = [str(bondage_id)]
                with self.assertRaises(player_pick.Chosen) as raised:
                    bondage_panel.Bondage_Panel(WIDTH).draw()
                self.assertEqual(self.clicks.answers, [])
                data = raised.exception.action.action_data
                assert isinstance(data, Mapping)
                self.assertEqual(data["behavior_id"], behavior_id)
                args = data["args"]
                assert isinstance(args, Mapping)
                self.assertEqual(
                    (args["bondage_id"], args["start"]),
                    (bondage_id, "bondage"),
                )
                self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)


class SexBeDiscoveredPanelTest(PanelCase):
    """H中被发现面板（Sex_Be_Discovered_Panel）的选项展示与结束H排程测试。"""

    def setUp(self) -> None:
        """在基类夹具基础上将对方角色的 is_h 标记设为 True。"""
        super().setUp()
        kernel_data.put(flags.set, PARTNER, is_h=True)

    def panel(
        self, **kwargs: bool
    ) -> sex_be_discovered_panel.Sex_Be_Discovered_Panel:
        """
        以 WIDTH 宽度与 FINDER 发现者编号构造 Sex_Be_Discovered_Panel 实例。
        Keyword arguments:
        kwargs -- dict[str, bool]，透传给面板构造函数的布尔关键字参数
        Return arguments:
        Sex_Be_Discovered_Panel -- 新建的H中被发现面板实例
        """
        return sex_be_discovered_panel.Sex_Be_Discovered_Panel(
            WIDTH, FINDER, **kwargs
        )

    def first_page(self, **kwargs: bool) -> list[str]:
        """
        绘制H中被发现面板并以返回值 "5" 退出，断言首页各按钮文本第二位字符与可选返回值列表一致。
        Keyword arguments:
        kwargs -- dict[str, bool]，透传给 panel 方法的布尔关键字参数
        Return arguments:
        list[str] -- 首页绘制的按钮文本列表
        """
        self.run_panel(self.panel(**kwargs).draw, "5")
        page = self.clicks.pages[0]
        self.assertEqual([text[1] for text in page], self.clicks.offers[0])
        return page

    def test_plain_h_offers_all_choices(self) -> None:
        """验证普通单独H被发现时，首页依次列出 DISCOVERED_TEXTS 中的五个选项按钮。"""
        self.assertEqual(self.first_page(), list(DISCOVERED_TEXTS.values()))

    def test_hidden_context_drops_hidden_switch(self) -> None:
        """验证传入 from_hidden_sex_flag=True 时，首页不列出「[2]迅速地隐藏起来，转为隐奸」。"""
        self.assertEqual(
            self.first_page(from_hidden_sex_flag=True),
            [DISCOVERED_TEXTS[key] for key in "1345"],
        )

    def test_exhibitionism_mode_keeps_going(self) -> None:
        """验证玩家处于 exhibitionism_sex_mode 时，首页将选项 3 显示为「[3]无视对方，正常继续」并保持其余四项不变。"""
        kernel_data.put(flags.set, 0, exhibitionism_sex_mode=1)
        texts = list(DISCOVERED_TEXTS.values())
        texts[2] = "[3]无视对方，正常继续"
        self.assertEqual(self.first_page(), texts)

    def test_group_sex_drops_both_switches(self) -> None:
        """验证群交模式下，首页仅列出编号 1、4、5 对应的三个选项按钮。"""
        kernel_data.put(modes.set_group_sex, True)
        self.assertEqual(
            self.first_page(), [DISCOVERED_TEXTS[key] for key in "145"]
        )

    def test_end_h_plans_interrupts(self) -> None:
        """
        先将发现者目标设为对方并断言打开前目标为对方，see_pl_h、h_interrupt、记录名、双方队列与结算标记均为初值。
        普通H下选择「[5]尴尬地结束H」，断言结算标记、发现者目标 0、see_pl_h、对方 h_interrupt 与记录名已写入。
        测试同时断言发现者队列为 [SEE_H_AND_INTERRUPT]，并断言玩家队列为 [H_INTERRUPT]。
        """
        aim(FINDER, PARTNER)
        self.assertEqual(
            (
                activity.target(FINDER),
                flags.get(FINDER, "see_pl_h"),
                action_info.get(PARTNER, "h_interrupt"),
                activity.behavior(0).h_interrupt_chara_name,
                queued(FINDER),
                queued(0),
            ),
            (PARTNER, False, 0, "", [], []),
        )
        panel = self.panel()
        self.assertFalse(panel.discoverer_reaction_settled)
        self.run_panel(panel.draw, "5")
        self.assertTrue(panel.discoverer_reaction_settled)
        self.assertEqual(activity.target(FINDER), 0)
        self.assertTrue(flags.get(FINDER, "see_pl_h"))
        self.assertEqual(action_info.get(PARTNER, "h_interrupt"), 1)
        self.assertEqual(activity.behavior(0).h_interrupt_chara_name, "发现者")
        self.assertEqual(
            queued(FINDER), [constant.Behavior.SEE_H_AND_INTERRUPT]
        )
        self.assertEqual(queued(0), [constant.Behavior.H_INTERRUPT])

    def test_end_group_sex_plans_group_end(self) -> None:
        """
        群交模式下先断言双方计划队列为空，再选择「[5]尴尬地结束H」。
        断言玩家完整计划队列为 [GROUP_SEX_END]，并断言发现者完整计划队列为 [SEE_H_AND_INTERRUPT]。
        """
        kernel_data.put(modes.set_group_sex, True)
        self.assertEqual((queued(FINDER), queued(0)), ([], []))
        self.run_panel(self.panel().draw, "5")
        self.assertEqual(queued(0), [constant.Behavior.GROUP_SEX_END])
        self.assertEqual(
            queued(FINDER), [constant.Behavior.SEE_H_AND_INTERRUPT]
        )
