"""
公务事件决断面板交互测试
========================
本测试验证 Script.UI.Panel.official_event_panel 的选项决断、结算与事件抬头获取。
测试替换事件配置、抬头注册表与洗牌函数，并拦截 LeftButton.draw、NormalDraw.draw 与 askfor_all 来驱动选择。
用例覆盖洗牌选项与原序号返回、不可决断事件跳过、空队列返回、结算效果与提示、抬头提供者回退。
"""

from types import SimpleNamespace
from unittest import mock

from Script.Config import game_config
from Script.Core import flow_handle, text_handle
from Script.Modules.domains import official
from Script.Modules.tk_ui import player_pick
from Script.System.Official_Event_System import official_event_handle, ri_value
from Script.UI.Moudle import draw
from Script.UI.Panel import official_event_panel
from tests import kernel_data
from tests.fast.base import FastTestCase

WIDTH = 100
""" 传给 choose_official_event_option 的测试绘制宽度。 """
DEPARTMENT = 15
""" 假公务事件使用的测试部门编号。 """
LOCKED = "CVP_RI_R|1_G_100"
""" 要求罗德岛资源 1 大于 100 的前提条件，在初始测试世界中不满足。 """
EVENTS = {
    "测试甲": {
        "cid": "测试甲",
        "department": DEPARTMENT,
        "text": "甲正文",
        "option_1": "甲选项一",
        "option_1_premise": LOCKED,
        "option_1_tip": "甲提示一",
    },
    "测试乙": {
        "cid": "测试乙",
        "department": DEPARTMENT,
        "text": "乙正文",
        "option_1": "乙选项一",
        "option_1_tip": "乙提示一",
        "option_1_effect": "CVE_RI_R|1_G_100",
        "option_2": "乙选项二",
        "option_2_premise": LOCKED,
        "option_2_reason": "乙原因",
        "option_2_tip": "乙提示二",
        "option_3": "乙选项三",
        "option_3_effect": "CVE_RI_R|1_G_7",
    },
}
"""
测试用假公务事件配置表，包含测试甲与测试乙。
测试甲仅设前提为 LOCKED 的选项 1。测试乙设带提示的选项 1、前提为 LOCKED 的选项 2 与无提示的选项 3。
"""
SKIPPED = "  （这件事已经不需要你来决定了）\n"
""" 无可选选项时面板以 deep_gray 样式绘制的跳过提示文本。 """


def queued(uid: str) -> dict[str, object]:
    """返回指定 uid、chara_id 为 0 且 partner_id 为 0 的公务事件队列项字典。"""
    return {"uid": uid, "chara_id": 0, "partner_id": 0}


class OfficialEventPanelTest(FastTestCase):
    """公务事件决断面板的选项决断、结算与事件抬头测试。"""

    def setUp(self) -> None:
        """
        调用父类 setUp，创建角色 0 并初始化记录属性。替换事件配置并将洗牌替换为反序。
        在清空 EVENT_TITLE 前先调用 official_event_handle.init_provider，以便拆卸恢复时保留已注册的抬头提供者。
        以 _bind、_text 与 _answer 分别拦截 LeftButton.draw、NormalDraw.draw 与 askfor_all。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.choices: list[str] = []
        """ 按消费顺序排列的预设选项文本列表，每次决断消费一项。 """
        self.drawn: list[draw.LeftButton] = []
        """ 当前事件已绘制、尚未被 _answer 消费的选项按钮列表。 """
        self.pages: list[list[str]] = []
        """ 每次决断页记录的选项按钮文本列表，保留按钮上的序号前缀。 """
        self.texts: list[tuple[str, str]] = []
        """ 按绘制顺序记录的 NormalDraw 文本与样式二元组列表。 """
        self.enterContext(
            mock.patch.object(game_config, "config_official_event", EVENTS)
        )
        official_event_handle.init_provider()
        self.enterContext(
            mock.patch.dict(official_event_handle.EVENT_TITLE, clear=True)
        )
        self.enterContext(
            mock.patch.object(
                player_pick,
                "ui_random",
                SimpleNamespace(shuffle=lambda items: items.reverse()),
            )
        )
        self.enterContext(
            mock.patch.object(
                draw.LeftButton, "draw", autospec=True, side_effect=self._bind
            )
        )
        self.enterContext(
            mock.patch.object(
                draw.NormalDraw, "draw", autospec=True, side_effect=self._text
            )
        )
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self._answer)
        )

    def _bind(self, button: draw.LeftButton) -> None:
        """
        按 button.return_text 经 flow_handle.bind_cmd 注册按钮回调，再将按钮追加到 self.drawn。
        Keyword arguments:
        button -- draw.LeftButton，调用 draw 方法的选项按钮对象
        Return arguments:
        None -- 无返回值
        """
        flow_handle.bind_cmd(button.return_text, button.cmd_func, button.args)
        self.drawn.append(button)

    def _text(self, text_draw: draw.NormalDraw) -> None:
        """
        将普通文本绘制对象的文本与样式二元组追加到 self.texts。
        Keyword arguments:
        text_draw -- draw.NormalDraw，调用 draw 方法的普通文本绘制对象
        Return arguments:
        None -- 无返回值
        """
        self.texts.append((text_draw.text, text_draw.style))

    def _answer(self, return_list: list[str], *args: object) -> str:
        """
        断言 self.choices 非空并取出队首预设选项，取出并清空 self.drawn，断言按钮返回值与 return_list 一致。
        将本页按钮文本列表记入 self.pages，并按从 1 起的序号前缀加预设选项定位唯一按钮。
        从 flow_handle.cmd_map 取该按钮命令（未绑定时取 null_func），清空 cmd_map 后执行并返回其 return_text。
        Keyword arguments:
        return_list -- list[str]，面板本次给出的选项按钮返回值列表
        args -- tuple[object, ...]，其余位置参数，本方法不使用
        Return arguments:
        str -- 命中选项按钮的 return_text
        """
        self.assertTrue(self.choices, f"缺少针对 {return_list} 的预设选项")
        choice = self.choices.pop(0)
        buttons, self.drawn = self.drawn, []
        self.assertEqual([b.return_text for b in buttons], return_list)
        self.pages.append([b.text for b in buttons])
        (button,) = [
            b
            for i, b in enumerate(buttons, 1)
            if b.text == text_handle.id_index(i) + choice
        ]
        command = flow_handle.cmd_map.get(
            button.return_text, flow_handle.null_func
        )
        flow_handle.cmd_map.clear()
        command()
        return button.return_text

    def choose(
        self, queue: list[dict[str, object]], choices: list[str]
    ) -> dict | None:
        """
        写入公务事件队列与 self.choices，在 kernel_data.writing() 中以 WIDTH 调用 choose_official_event_option。
        调用结束后断言 self.choices 耗尽，并返回选定结果字典或 None。
        Keyword arguments:
        queue -- list[dict[str, object]]，写入内核状态的待决断公务事件队列
        choices -- list[str]，按决断顺序排列的预设选项文本列表
        Return arguments:
        dict | None -- 选定的公务事件选项字典，无可用选项或队列为空时返回 None
        """
        kernel_data.put(official.set_queue, queue)
        self.choices = list(choices)
        with kernel_data.writing():
            option = official_event_panel.choose_official_event_option(WIDTH)
        self.assertEqual(self.choices, [])
        return option

    def settle(self, option_index: int) -> None:
        """
        在 kernel_data.writing() 中以测试乙和指定选项序号调用 official_event_panel.settle_chosen_option。
        Keyword arguments:
        option_index -- int，传给测试乙结算调用的选项序号
        Return arguments:
        None -- 无返回值
        """
        with kernel_data.writing():
            official_event_panel.settle_chosen_option(
                {**queued("测试乙"), "option": option_index}
            )

    def test_choose_offers_shuffled_buttons_and_returns_csv_index(self) -> None:
        """
        以子测试选择测试乙的乙选项一与乙选项三，验证按钮按反序显示且返回对应配置序号 1 与 3。
        断言正文与置灰的乙选项二及原因被绘制、提示文本未显示，且队列已空、履历为空、资源 1 仍为 0。
        """
        for choice, index in (("乙选项一", 1), ("乙选项三", 3)):
            with self.subTest(choice=choice):
                self.pages.clear()
                self.texts.clear()
                option = self.choose([queued("测试乙")], [choice])
                self.assertEqual(option, {**queued("测试乙"), "option": index})
                self.assertEqual(
                    self.pages,
                    [
                        [
                            text_handle.id_index(1) + "乙选项三",
                            text_handle.id_index(2) + "乙选项一",
                        ]
                    ],
                )
                self.assertIn(("\n  乙正文\n\n", "standard"), self.texts)
                self.assertIn(
                    ("   ○ 乙选项二（乙原因）\n", "deep_gray"), self.texts
                )
                shown = "".join(text for text, _style in self.texts)
                for tip in ("乙提示一", "乙提示二"):
                    self.assertNotIn(tip, shown)
                self.assertEqual(official.queue(), [])
                self.assertEqual(official.history(), {})
                self.assertEqual(ri_value.get_ri_value("R|1"), 0)

    def test_undecidable_event_is_recorded_and_skipped(self) -> None:
        """
        队列依次放入测试甲与测试乙后选择乙选项一，验证测试甲被跳过且返回测试乙的选项 1。
        断言记录 1 页选项按钮、deep_gray 文本依次为 SKIPPED 与乙选项二置灰行，且测试甲以选项 0 记入履历、队列为空。
        """
        option = self.choose([queued("测试甲"), queued("测试乙")], ["乙选项一"])
        self.assertEqual(option, {**queued("测试乙"), "option": 1})
        self.assertEqual(len(self.pages), 1)
        self.assertEqual(
            [text for text, style in self.texts if style == "deep_gray"],
            [SKIPPED, "   ○ 乙选项二（乙原因）\n"],
        )
        self.assertEqual(list(official.history()), ["测试甲"])
        self.assertEqual(official.history()["测试甲"]["choice"], 0)
        self.assertEqual(official.queue(), [])

    def test_no_decidable_event_returns_none(self) -> None:
        """验证空队列与仅含测试甲的队列均返回 None、未记录选项页，且测试甲以选项 0 记入履历、队列为空。"""
        self.assertIsNone(self.choose([], []))
        self.assertIsNone(self.choose([queued("测试甲")], []))
        self.assertEqual(self.pages, [])
        self.assertEqual(official.history()["测试甲"]["choice"], 0)
        self.assertEqual(official.queue(), [])

    def test_settle_applies_effect_and_shows_tip(self) -> None:
        """
        结算测试乙选项 1，验证罗德岛资源 1 增至 100、履历记选项 1，且 wait_texts 含乙选项一与乙提示一的结果提示。
        清空 wait_texts 后结算选项 3，验证资源 1 增至 107、履历记选项 3 且 wait_texts 保持为空。
        """
        self.settle(1)
        self.assertEqual(ri_value.get_ri_value("R|1"), 100)
        self.assertEqual(official.history()["测试乙"]["choice"], 1)
        self.assertEqual(
            self.world.wait_texts,
            ["\n  你选择了「乙选项一」\n  结果：乙提示一\n"],
        )
        self.world.wait_texts.clear()
        self.settle(3)
        self.assertEqual(ri_value.get_ri_value("R|1"), 107)
        self.assertEqual(official.history()["测试乙"]["choice"], 3)
        self.assertEqual(self.world.wait_texts, [])

    def test_event_title(self) -> None:
        """验证未注册抬头提供者时返回部门名，注册提供者时使用其返回值，提供者异常时回退部门名。"""
        name = official_event_handle.get_department_name(DEPARTMENT)
        self.assertNotEqual(name, "")
        self.assertEqual(
            official_event_panel.get_event_title(queued("测试乙")), name
        )
        titles = official_event_handle.EVENT_TITLE
        titles[DEPARTMENT] = lambda queue_data: f"抬头{queue_data['uid']}"
        self.assertEqual(
            official_event_panel.get_event_title(queued("测试乙")), "抬头测试乙"
        )
        titles[DEPARTMENT] = lambda queue_data: queue_data["title"]
        self.assertEqual(
            official_event_panel.get_event_title(queued("测试乙")), name
        )
