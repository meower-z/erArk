# -*- coding: UTF-8 -*-
"""
指令提示钩子测试
================
HandleInstructHooksTest 验证 handle_instruct 经 ui_hooks 发出提示。
"""

from unittest import mock

from Script.Core import constant, get_text
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import intent, ui_hooks
from Script.System.Instruct_System import handle_instruct
from Script.UI.Moudle import view
from tests.fast.base import FastTestCase

_ = get_text._

type Notice = tuple[str, bool, str | None, bool]
""" 一条提示的参数元组类型，依次为文本、是否等待确认、样式名与是否按文本宽度排版。 """


class HandleInstructHooksTest(FastTestCase):
    """handle_instruct 经 ui_hooks 发出提示的测试。"""

    def setUp(self) -> None:
        """
        调用父类准备，创建角色 0 与 1，临时替换 view.now_panel_id 与 view.show_non_h_in_hidden_sex，
        并在 ui_hooks._notices 末尾追加 self.record。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        for name, value in (
            ("now_panel_id", constant.Panel.IN_SCENE),
            ("show_non_h_in_hidden_sex", False),
        ):
            self.enterContext(mock.patch.object(view, name, value))
        self.notices: list[Notice] = []
        self.enterContext(
            mock.patch.object(
                ui_hooks, "_notices", [*ui_hooks._notices, self.record]
            )
        )

    def record(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        将一条提示的参数元组追加到 self.notices。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名
        use_text_width -- bool，是否按文本宽度排版
        Return arguments:
        None -- 无返回值
        """
        self.notices.append((text, wait, style, use_text_width))

    def test_class_without_student_notices(self) -> None:
        """
        验证无学生时执行 START_SEX_CLASS 指令会发出一条等待确认且按文本宽度排版的提示，且不切换面板。
        同时断言该提示写入 self.world.wait_texts。
        """
        handle_instruct.handle_instruct(constant.Instruct.START_SEX_CLASS)
        text = _("\n这里没有可以上课的学生。\n")
        self.assertEqual(self.notices, [(text, True, None, True)])
        self.assertEqual(self.world.wait_texts, [text])
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)

    def test_start_parts_notice(self) -> None:
        """
        验证 DO_H_FAIL、ASK_HIDDEN_SEX_FAIL 与 follow 三段开始代码各发出一条提示。
        同时断言每条提示的文本、等待标志、样式名与文本宽度选项均符合预期。
        """
        name = identity.of(1).name
        cases: tuple[tuple[str, int | None, Notice], ...] = (
            (
                constant.Behavior.DO_H_FAIL,
                None,
                (_("\n进入H模式失败\n\n"), True, "warning", True),
            ),
            (
                constant.Behavior.ASK_HIDDEN_SEX_FAIL,
                None,
                (_("\n邀请隐奸失败\n"), True, None, False),
            ),
            (
                "follow",
                1,
                (
                    _("\n{0}进入智能跟随模式\n").format(name),
                    False,
                    None,
                    False,
                ),
            ),
        )
        for part, target, notice in cases:
            with self.subTest(part=part):
                self.notices.clear()
                chosen = intent.Intent(
                    behavior_id=constant.Behavior.SHARE_BLANKLY,
                    minutes=1,
                    args={handle_instruct.START: part},
                )
                if target is not None:
                    chosen["target"] = target
                handle_instruct.start_instruct(0, chosen)
                self.assertEqual(self.notices, [notice])
