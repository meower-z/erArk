# -*- coding: UTF-8 -*-
"""
指令界面钩子测试
================
InstructHooksUiFreeTest 在无界面子进程中验证 instruct_hooks 的默认行为、槽位登记与界面模块隔离。
InstructCallbacksTest 验证 stash_filter 与 stashed_filter 经 instruct_callbacks 读写 view.instruct_type_filter_cache。
HandleInstructHooksTest 验证 handle_instruct 经 ui_hooks 切换面板与发出提示，并经 instruct_hooks 调用界面回调。
"""

from unittest import mock

from Script.Config import normal_config
from Script.Core import constant, get_text
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import instruct_hooks, intent, ui_hooks
from Script.System.Instruct_System import handle_instruct
from Script.UI.Moudle import view
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

_ = get_text._

type Notice = tuple[str, bool, str | None, bool]
""" 一条提示的参数元组类型，依次为文本、是否等待确认、样式名与是否按文本宽度排版。 """
RUNS = """
payload["error"] = None
try:
    from Script.Modules.gameplay_resolution import instruct_hooks

    instruct_hooks.stash_filter({6: True})
    payload["plain"] = sorted(instruct_hooks.stashed_filter().items())
    calls = []
    instruct_hooks.on_instruct(
        lambda filters: calls.append(["stash", sorted(filters.items())]),
        lambda: {1: False},
    )
    instruct_hooks.stash_filter({6: True})
    payload["stashed"] = sorted(instruct_hooks.stashed_filter().items())
    payload["calls"] = calls
except ImportError as error:
    payload["error"] = repr(error)
"""
""" 无界面子进程脚本，调用 instruct_hooks 的默认与登记后入口并向 payload 记录结果。 """


class InstructHooksUiFreeTest(FastTestCase):
    """无界面子进程中的 instruct_hooks 默认行为、槽位登记与界面模块隔离测试。"""

    child: ChildRun

    @classmethod
    def setUpClass(cls) -> None:
        """调用父类类级准备并经 run_ui_free 执行 RUNS，将结果保存到 cls.child。"""
        super().setUpClass()
        cls.child = run_ui_free(RUNS)

    def test_defaults_without_ui(self) -> None:
        """
        验证无界面子进程未记录导入错误，且未登记时 stash_filter 调用正常。
        同时断言未登记时 stashed_filter 的键值对列表为空。
        """
        self.assertIsNone(self.child.payload["error"])
        self.assertEqual(self.child.payload["plain"], [])

    def test_registered_handlers_get_calls(self) -> None:
        """
        验证经 on_instruct 登记后，stash_filter 将参数传给登记函数。
        同时断言 stashed_filter 返回登记函数提供的映射。
        """
        payload = self.child.payload
        self.assertEqual(payload["calls"], [["stash", [[6, True]]]])
        self.assertEqual(payload["stashed"], [[1, False]])

    def test_hooks_touch_no_ui_module(self) -> None:
        """验证无界面子进程未尝试导入也未加载任何受拦截模块。"""
        self.assertEqual(self.child.attempted, [])
        self.assertEqual(self.child.loaded, [])


class InstructCallbacksTest(FastTestCase):
    """本进程中 stash_filter 与 stashed_filter 经 instruct_callbacks 读写 view.instruct_type_filter_cache 的测试。"""

    def setUp(self) -> None:
        """
        调用父类准备，并用 mock.patch.object 临时替换 view.instruct_type_filter_cache。
        """
        super().setUp()
        self.enterContext(
            mock.patch.object(view, "instruct_type_filter_cache", {})
        )

    def test_filter_stash_reaches_view(self) -> None:
        """
        验证 stash_filter 将传入字典直接存入 view.instruct_type_filter_cache。
        同时断言 stashed_filter 返回同一字典对象。
        """
        filters = {1: True, 6: False}
        instruct_hooks.stash_filter(filters)
        self.assertIs(view.instruct_type_filter_cache, filters)
        self.assertIs(instruct_hooks.stashed_filter(), filters)


class HandleInstructHooksTest(FastTestCase):
    """handle_instruct 经 ui_hooks 切换面板与发出提示，并经 instruct_hooks 调用界面回调的测试。"""

    def setUp(self) -> None:
        """
        调用父类准备，创建角色 0 与角色 1，并临时替换 view 的面板编号与两个指令界面状态。
        随后在 ui_hooks 已登记的提示与面板切换回调末尾追加记录回调，同时保留原有 Tk 回调。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        for name, value in (
            ("now_panel_id", constant.Panel.IN_SCENE),
            ("show_non_h_in_hidden_sex", False),
            ("instruct_type_filter_cache", {}),
        ):
            self.enterContext(mock.patch.object(view, name, value))
        self.notices: list[Notice] = []
        self.panels: list[int] = []
        self.enterContext(
            mock.patch.object(
                ui_hooks, "_notices", [*ui_hooks._notices, self.record]
            )
        )
        self.enterContext(
            mock.patch.object(
                ui_hooks,
                "_panel_switches",
                [*ui_hooks._panel_switches, self.panels.append],
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

    def test_panel_instruct_switches_panel(self) -> None:
        """
        验证执行 EDIT_GROUP_SEX_TEMPLE 指令会经 ui_hooks.switch_panel 切换到对应面板。
        同时断言 view.now_panel_id 更新为 Panel.EDIT_GROUP_SEX_TEMPLE。
        """
        handle_instruct.handle_instruct(constant.Instruct.EDIT_GROUP_SEX_TEMPLE)
        self.assertEqual(self.panels, [constant.Panel.EDIT_GROUP_SEX_TEMPLE])
        self.assertEqual(
            view.now_panel_id, constant.Panel.EDIT_GROUP_SEX_TEMPLE
        )

    def test_class_without_student_notices(self) -> None:
        """
        验证无学生时执行 START_SEX_CLASS 指令会发出一条等待确认且按文本宽度排版的提示，且不切换面板。
        同时断言该提示写入 self.world.wait_texts。
        """
        handle_instruct.handle_instruct(constant.Instruct.START_SEX_CLASS)
        text = _("\n这里没有可以上课的学生。\n")
        self.assertEqual(self.notices, [(text, True, None, True)])
        self.assertEqual(self.world.wait_texts, [text])
        self.assertEqual(self.panels, [])

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

    def test_h_filter_stash_and_restore(self) -> None:
        """
        验证 instruct_filter_H_change(True) 暂存当前指令类型过滤状态，并仅保留类型 6 为 True。
        同时断言 instruct_filter_H_change(False) 恢复暂存的过滤状态。
        """
        before = {i: True for i in range(1, 7)}
        setting = normal_config.system_setting
        self.enterContext(
            mock.patch.object(setting, "instruct_type_filter", dict(before))
        )
        handle_instruct.instruct_filter_H_change(True)
        self.assertEqual(instruct_hooks.stashed_filter(), before)
        self.assertEqual(
            setting.instruct_type_filter,
            {1: False, 2: False, 3: False, 4: False, 5: False, 6: True},
        )
        handle_instruct.instruct_filter_H_change(False)
        self.assertEqual(setting.instruct_type_filter, before)
