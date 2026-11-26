"""
文本生成AI界面面板测试
======================
验证直接对话面板收集输入、构造效果表并经由通用指令结算选中 AI_CHAT_INSTRUCT。
验证模块级 OUTPUT 实例按预期调用 NormalDraw 与 LineFeedWaitDraw 绘制文本。
"""

from types import SimpleNamespace
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant
from Script.Design import handle_chat_ai
from Script.Modules.tk_ui import player_pick
from Script.System.Instruct_System import handle_instruct
from Script.UI.Moudle import draw, panel
from Script.UI.Panel import chat_ai_panel
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

OPENAI_KEY = "OPENAI_API_KEY"
""" 测试使用的 OPENAI_API_KEY 密钥名 """


class Picked(Exception):
    """用于拦截 player_pick.choose 并中止面板循环的替身异常。"""


class DirectChatPanelTest(FastTestCase):
    """直接对话面板与 Tk 输出实现单元测试。"""

    def test_direct_chat_picks_ai_chat_instruct(self) -> None:
        """验证直接对话写入临时指令效果表并以等待目标标记选中 AI_CHAT_INSTRUCT。"""
        self.world.chara(0, "c0")
        self.world.chara(1, "c1")
        aim(0, 1)
        behavior = constant.Behavior.AI_CHAT_INSTRUCT
        self.enterContext(
            mock.patch.dict(game_config.config_behavior_effect_data, {})
        )
        ai = normal_config.ai_setting
        settings = dict.fromkeys(range(1, 15), 0) | {1: 1, 5: "m-test", 8: 1}
        self.enterContext(mock.patch.object(ai, "ai_chat_setting", settings))
        self.enterContext(
            mock.patch.object(ai, "ai_chat_api_key", {OPENAI_KEY: "k"})
        )
        text = "time:7\ntired:3\nrelationship:4\ncharacter_state:9,20,21\n"
        message = SimpleNamespace(content=text + "experience:81,82\ntext:好")
        client = mock.Mock()
        client.chat.completions.create.return_value.choices = [
            SimpleNamespace(message=message)
        ]
        self.enterContext(
            mock.patch.object(
                handle_chat_ai.openai, "OpenAI", return_value=client
            )
        )
        self.enterContext(
            mock.patch.object(
                panel.AskForOneMessage, "draw", return_value="摸头"
            )
        )
        with mock.patch.object(
            player_pick, "choose", side_effect=Picked
        ) as choose, self.assertRaises(Picked):
            chat_ai_panel.direct_chat_with_ai()
        sent = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertIn("摸头", sent[1]["content"])
        self.assertEqual(
            game_config.config_behavior_effect_data[behavior],
            [13, 14, 21, 22, 51, 62, "CVE_A2_E|81_G_1", "CVE_A2_E|82_G_1"],
        )
        self.assertEqual(choose.call_args.args, (behavior, 7))
        self.assertEqual(
            choose.call_args.kwargs["args"], {handle_instruct.TARGET_WAIT: True}
        )

    def test_output_draws(self) -> None:
        """验证 OUTPUT.show 与 line_break 按预期宽度和文本调用绘制对象。"""
        drawn: list[tuple[str, str, float]] = []

        def record(drawer: draw.NormalDraw) -> None:
            drawn.append((type(drawer).__name__, drawer.text, drawer.width))

        for cls in (draw.NormalDraw, draw.LineFeedWaitDraw):
            self.enterContext(mock.patch.object(cls, "draw", record))
        chat_ai_panel.OUTPUT.show("a")
        chat_ai_panel.OUTPUT.show("b", full_width=True)
        chat_ai_panel.OUTPUT.line_break()
        self.assertEqual(
            drawn,
            [
                ("NormalDraw", "a", 0),
                ("NormalDraw", "b", chat_ai_panel.window_width),
                ("LineFeedWaitDraw", " \n", 0),
            ],
        )
