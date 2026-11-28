"""
忍耐射精判定与选择渲染测试
==========================
- EndureDecisionTest：emit_endure_panel 在各系统设置 11 分支、几率档位、掷骰阈值与未登记处理函数时的
  判定、状态写入与结果输出。
- TkEndureChoiceTest：draw_endure_choice 经 choice_prompts 与 ui_hooks 完成忍耐选择及结果绘制的顺序与参数。
"""

from unittest import mock

from Script.Config import normal_config
from Script.Core import flow_handle, get_text
from Script.Kernel import core
from Script.Modules.domains import abilities, h_meters, h_state
from Script.Modules.gameplay_resolution import ejaculation_service, modal_hooks
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Modules.tk_ui import callbacks, choice_prompts
from Script.Protocol.modal_prompts import ChoiceOption, ChoicePrompt
from Script.Protocol.modal_prompts import ChoiceResult
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase

_ = get_text._
ASK_TEXT = "要射精了，是否要忍住射精，忍耐次数越多则射精量越多（当前已忍住{0}次，忍耐几率 {1}）\n"
""" 忍耐射精询问的未翻译正文模板字符串。 """


class EndureCase(FastTestCase):
    """初始化玩家角色并替身化 modal_hooks 与 ui_hooks 回调的忍耐测试基类。"""

    def setUp(self) -> None:
        """创建玩家角色并打开工作集，替身化 modal_hooks._ask 与 ui_hooks 提示及分隔线回调，并将系统设置 11 设为 2。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        self.prompts: list[ChoicePrompt] = []
        self.answer = "endure"
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.dividers: list[str] = []
        self.enterContext(mock.patch.object(modal_hooks, "_ask", self.ask))
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.notice])
        )
        self.enterContext(
            mock.patch.object(ui_hooks, "_dividers", [self.dividers.append])
        )
        self.setting(2)

    def ask(self, prompt: ChoicePrompt) -> ChoiceResult:
        """
        记录收到的选项提示，并返回选中 self.answer 的 ChoiceResult。
        Keyword arguments:
        prompt -- ChoicePrompt，本次派发的选项提示
        Return arguments:
        ChoiceResult -- 包含 prompt.prompt_id 与 self.answer 的选择结果
        """
        self.prompts.append(prompt)
        return ChoiceResult(prompt.prompt_id, self.answer)

    def notice(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        将一次经 ui_hooks.emit_notice 派发的提示参数元组追加到 self.notices。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名
        use_text_width -- bool，是否按配置文本宽度排版
        Return arguments:
        None -- 无返回值
        """
        self.notices.append((text, wait, style, use_text_width))

    def setting(self, value: int | None) -> None:
        """
        将系统设置字典中的键 11 临时替换为指定值，并在用例结束后恢复。
        Keyword arguments:
        value -- int | None，写入键 11 的整数值，为 None 时不设键 11
        Return arguments:
        None -- 无返回值
        """
        settings = dict(normal_config.system_setting.base_setting)
        settings.pop(11, None)
        if value is not None:
            settings[11] = value
        self.enterContext(
            mock.patch.dict(
                normal_config.system_setting.base_setting, settings, clear=True
            )
        )

    def endure(self, level: int, count: int, roll: int) -> bool:
        """
        设置玩家能力 30 等级、忍耐次数与满值射精槽，固定 randint 返回值后调用 emit_endure_panel 并断言掷骰参数。
        Keyword arguments:
        level -- int，玩家能力 30 的等级
        count -- int，当前已忍耐次数
        roll -- int，固定给 random.randint 的返回值
        Return arguments:
        bool -- emit_endure_panel 的判定结果
        """
        abilities.ability(0)[30] = level
        h_state.set(0, endure_not_shot_count=count)
        h_meters.set(0, eja=1000, eja_max=1000)
        with mock.patch.object(
            ejaculation_service.random, "randint", return_value=roll
        ) as randint:
            endured = ejaculation_service.emit_endure_panel()
        randint.assert_called_once_with(1, 100)
        return endured

    def assert_endured(self, count: int) -> None:
        """
        断言忍耐次数加 1、射精槽清零，且记录到一次按文本宽度排版的忍耐提示与一条 "-" 分隔线。
        Keyword arguments:
        count -- int，调用 emit_endure_panel 前的已忍耐次数
        Return arguments:
        None -- 无返回值
        """
        self.assertEqual(h_state.get(0, "endure_not_shot_count"), count + 1)
        self.assertEqual(h_meters.of(0)["eja"], 0)
        text = _("\n{0}忍住了射精\n").format("博士")
        self.assertEqual(self.notices, [(text, False, None, True)])
        self.assertEqual(self.dividers, ["-"])

    def assert_untouched(self, count: int) -> None:
        """
        断言忍耐次数与射精槽均保持不变，且未发出提示与分隔线。
        Keyword arguments:
        count -- int，期望保持不变的已忍耐次数
        Return arguments:
        None -- 无返回值
        """
        self.assertEqual(h_state.get(0, "endure_not_shot_count"), count)
        self.assertEqual(h_meters.of(0)["eja"], 1000)
        self.assertEqual((self.notices, self.dividers), ([], []))


class EndureDecisionTest(EndureCase):
    """emit_endure_panel 在各系统设置分支、几率档位、掷骰阈值与未登记处理函数时的行为测试。"""

    def test_manual_endure_offers_both_choices(self) -> None:
        """
        验证系统设置 11 为 2、掷骰通过且选「忍住」时返回 True、写回状态并输出提示，
        同时发出含「忍住」与「射出」选项及必定忍住标签的 ChoicePrompt。
        """
        self.assertIs(self.endure(2, 1, 100), True)
        self.assert_endured(1)
        self.assertEqual(
            self.prompts,
            [
                ChoicePrompt(
                    ejaculation_service.ENDURE_PROMPT_ID,
                    (
                        ChoiceOption("endure", _("忍住")),
                        ChoiceOption("release", _("射出")),
                    ),
                    _(ASK_TEXT).format(1, _("必定忍住")),
                )
            ],
        )

    def test_manual_release_skips_endure(self) -> None:
        """验证系统设置 11 为 2 且选「射出」时即使掷骰通过也返回 False、不改动状态与输出，并已发起一次询问。"""
        self.answer = "release"
        self.assertIs(self.endure(2, 1, 1), False)
        self.assert_untouched(1)
        self.assertEqual(len(self.prompts), 1)

    def test_failed_roll_ignores_endure_answer(self) -> None:
        """验证忍耐几率为 0 且掷骰失败时，即便选「忍住」也返回 False 且不改动状态，询问文本显示「无」几率标签。"""
        self.assertIs(self.endure(0, 3, 1), False)
        self.assert_untouched(3)
        self.assertEqual(self.prompts[0].text, _(ASK_TEXT).format(3, _("无")))

    def test_missing_setting_asks(self) -> None:
        """验证系统设置缺少键 11 时默认按 2 发起询问，并在掷骰通过且选「忍住」时返回 True 与写回状态。"""
        self.setting(None)
        self.assertIs(self.endure(0, 0, 100), True)
        self.assertEqual(len(self.prompts), 1)
        self.assert_endured(0)

    def test_auto_endure_follows_roll(self) -> None:
        """验证系统设置 11 为 1 时不发起询问，掷骰不超过几率时忍住并写回状态，超过几率时返回 False 且不改动状态。"""
        self.setting(1)
        self.assertIs(self.endure(5, 7, 50), True)
        self.assert_endured(7)
        self.notices.clear()
        self.dividers.clear()
        self.assertIs(self.endure(5, 7, 51), False)
        self.assert_untouched(7)
        self.assertEqual(self.prompts, [])

    def test_never_endure_still_rolls(self) -> None:
        """验证系统设置 11 为 0 时仍执行一次掷骰但不发起询问，直接返回 False 且不改动状态。"""
        self.setting(0)
        self.assertIs(self.endure(3, 0, 1), False)
        self.assert_untouched(0)
        self.assertEqual(self.prompts, [])

    def test_rate_labels_and_thresholds(self) -> None:
        """验证各能力等级与忍耐次数组合下的几率标签（高、中、低、无）以及临界掷骰值的通过与失败边界。"""
        cases = (
            (5, 6, 75, "高"),
            (2, 3, 60, "中"),
            (0, 1, 50, "中"),
            (5, 8, 25, "低"),
            (2, 4, 20, "无"),
            (1, 3, 10, "无"),
            (0, 9, 0, "无"),
        )
        self.answer = "release"
        for level, count, rate, label in cases:
            with self.subTest(level=level, count=count):
                self.prompts.clear()
                self.endure(level, count, rate)
                self.assertEqual(
                    self.prompts[0].text, _(ASK_TEXT).format(count, _(label))
                )
        self.setting(1)
        for level, count, rate, _label in cases:
            with self.subTest(level=level, count=count, roll=rate + 1):
                self.assertIs(self.endure(level, count, rate + 1), False)
                if rate:
                    self.assertIs(self.endure(level, count, rate), True)

    def test_unregistered_manual_choice_raises(self) -> None:
        """验证系统设置 11 为 2 且未登记 modal_hooks 处理函数时抛出 RuntimeError，且不改动状态与输出。"""
        self.enterContext(mock.patch.object(modal_hooks, "_ask", None))
        with self.assertRaises(RuntimeError):
            self.endure(2, 1, 1)
        self.assert_untouched(1)


class TkEndureChoiceTest(EndureCase):
    """经 choice_prompts 与 callbacks 完成忍耐选择及结果绘制的 Tk 路径测试。"""

    def setUp(self) -> None:
        """
        拦截 NormalDraw、LineDraw 与 CenterButton 的 draw 方法及 flow_handle.askfor_all，
        并接入真实 Tk 渲染与输出回调。
        """
        super().setUp()
        self.drawn: list[tuple[object, ...]] = []
        for cls in (draw.NormalDraw, draw.LineDraw, draw.CenterButton):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.keep
                )
            )
        self.offered: list[list[str]] = []
        self.picked = _("射出")
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", side_effect=self.pick)
        )
        self.enterContext(
            mock.patch.object(modal_hooks, "_ask", choice_prompts.ask_choice)
        )
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [callbacks.draw_notice])
        )
        self.enterContext(
            mock.patch.object(ui_hooks, "_dividers", [callbacks.draw_divider])
        )

    def keep(self, now: object) -> None:
        """
        记录被拦截绘制对象的类名、文本、响应文本、宽度与样式到 self.drawn。
        Keyword arguments:
        now -- object，被调用 draw 方法的绘制对象实例
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append(
            (
                type(now).__name__,
                getattr(now, "text", None),
                getattr(now, "return_text", None),
                getattr(now, "width", None),
                getattr(now, "style", None),
            )
        )

    def pick(self, options: list[str]) -> str:
        """
        记录传给 flow_handle.askfor_all 的候选列表并返回 self.picked。
        Keyword arguments:
        options -- list[str]，本次提供的候选响应文本列表
        Return arguments:
        str -- 预设的模拟选择文本 self.picked
        """
        self.offered.append(list(options))
        return self.picked

    def expected(self, count: int, label: str) -> list[tuple[object, ...]]:
        """
        构造 draw_endure_choice 在给定忍耐次数与几率标签下预期的七步绘制记录。
        Keyword arguments:
        count -- int，当前已忍耐次数
        label -- str，忍耐几率档位标签
        Return arguments:
        list[tuple[object, ...]] -- 分隔线、换行、询问文本、换行、两枚居中按钮与换行的绘制记录列表
        """
        width = normal_config.config_normal.text_width
        feed = ("NormalDraw", "\n", None, 1, "standard")
        return [
            ("LineDraw", "-", None, width, "standard"),
            feed,
            (
                "NormalDraw",
                _(ASK_TEXT).format(count, _(label)),
                None,
                width,
                "standard",
            ),
            feed,
            (
                "CenterButton",
                "[" + _("忍住") + "]",
                _("忍住"),
                int(width / 3),
                None,
            ),
            (
                "CenterButton",
                "[" + _("射出") + "]",
                _("射出"),
                int(width / 3),
                None,
            ),
            feed,
        ]

    def test_release_draws_choice_only(self) -> None:
        """验证玩家在 Tk 路径选「射出」时返回 False、提供「忍住」与「射出」候选，且只绘制七步询问界面。"""
        self.assertIs(self.endure(0, 0, 1), False)
        self.assertEqual(self.drawn, self.expected(0, "必定忍住"))
        self.assertEqual(self.offered, [[_("忍住"), _("射出")]])

    def test_endure_draws_result_after_choice(self) -> None:
        """验证玩家在 Tk 路径选「忍住」并成功时返回 True，在七步询问界面后追加按文本宽度排版的忍耐提示与同宽分隔线。"""
        self.picked = _("忍住")
        self.assertIs(self.endure(0, 0, 1), True)
        width = normal_config.config_normal.text_width
        self.assertEqual(
            self.drawn,
            self.expected(0, "必定忍住")
            + [
                (
                    "NormalDraw",
                    _("\n{0}忍住了射精\n").format("博士"),
                    None,
                    width,
                    "standard",
                ),
                ("LineDraw", "-", None, width, "standard"),
            ],
        )
