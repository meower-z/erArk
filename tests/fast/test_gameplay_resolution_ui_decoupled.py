"""
gameplay_resolution 界面回调与成就结算测试
==========================================
- 界面回调（ui_hooks）：无已登记回调时不触发绘制也不改动当前面板，有回调时按参数转发提示与目标面板编号。
- 成就结算服务（achievement_service）：验证提示文本拼装、按数值阈值判定、按类型结算，
  以及逐条经 ui_hooks 发出新达成提示。
- Tk 界面回调（tk_ui.callbacks）：验证经 load_order 登记后的提示绘制、面板切换、成就单次绘制以及与成就面板绘制一致。
"""

from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant, get_text
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import achievement
from Script.Modules.gameplay_resolution import achievement_service, ui_hooks
from Script.Modules.gameplay_resolution import working
from Script.UI.Moudle import draw, view
from Script.UI.Panel import achievement_panel
from tests.fast.base import FastTestCase

POWER_ID = 821
""" 测试用的能源类成就编号（821） """
AROMA_IDS = (1061, 1062)
""" 测试用的调香类成就编号元组（1061 与 1062） """


def unlocked_notice(achievement_id: int) -> tuple[str, bool, str, bool]:
    """
    构造指定成就编号对应的预期 ui_hooks 提示参数四元组。
    Keyword arguments:
    achievement_id -- int，成就编号
    Return arguments:
    tuple[str, bool, str, bool] -- 依次为成就获得提示文本、wait（True）、style（"gold_enrod"）与 use_text_width（False）
    """
    return (
        achievement_service.unlocked_text(achievement_id),
        True,
        "gold_enrod",
        False,
    )


class UiHooksTest(FastTestCase):
    """界面回调模块（ui_hooks）在无回调与有回调时的转发测试"""

    def setUp(self) -> None:
        """清空已登记回调、打桩文本绘制方法并将当前面板设为场景主面板"""
        super().setUp()
        self.enterContext(mock.patch.object(ui_hooks, "_notices", []))
        self.enterContext(mock.patch.object(ui_hooks, "_panel_switches", []))
        self.drawn = self.enterContext(
            mock.patch.object(draw.NormalDraw, "draw", autospec=True)
        )
        self.waited = self.enterContext(
            mock.patch.object(draw.WaitDraw, "draw", autospec=True)
        )
        self.addCleanup(setattr, view, "now_panel_id", view.now_panel_id)
        view.now_panel_id = constant.Panel.IN_SCENE

    def test_without_handlers_nothing_happens(self) -> None:
        """验证未登记回调时发出提示与切换面板不触发绘制且不改变当前面板"""
        ui_hooks.emit_notice("text", wait=True, use_text_width=True)
        ui_hooks.switch_panel(constant.Panel.SEE_MAP)
        self.drawn.assert_not_called()
        self.waited.assert_not_called()
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)

    def test_handlers_receive_notice_and_panel(self) -> None:
        """验证登记函数返回原回调，且提示参数（含默认值）与面板编号正确转发而不触发界面绘制"""
        notice = mock.Mock()
        switch = mock.Mock()
        self.assertIs(ui_hooks.on_notice(notice), notice)
        self.assertIs(ui_hooks.on_panel_switch(switch), switch)
        ui_hooks.emit_notice("plain")
        ui_hooks.emit_notice("styled", wait=True, style="gold_enrod")
        ui_hooks.switch_panel(constant.Panel.SEE_MAP)
        self.assertEqual(
            notice.call_args_list,
            [
                mock.call(
                    "plain", wait=False, style=None, use_text_width=False
                ),
                mock.call(
                    "styled",
                    wait=True,
                    style="gold_enrod",
                    use_text_width=False,
                ),
            ],
        )
        switch.assert_called_once_with(constant.Panel.SEE_MAP)
        self.drawn.assert_not_called()
        self.waited.assert_not_called()
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)


class AchievementServiceTest(FastTestCase):
    """成就结算服务（achievement_service）的提示文本、阈值判定、按类型结算与提示发送测试"""

    def setUp(self) -> None:
        """创建玩家角色、打开工作集上下文并将 ui_hooks._notices 替换为记录方法 self.note"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.enterContext(mock.patch.object(ui_hooks, "_notices", [self.note]))

    def note(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        记录一次提示回调收到的参数四元组。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名
        use_text_width -- bool，是否按配置文本宽度排版
        Return arguments:
        None -- 无返回值，将四元组追加到 self.notices
        """
        self.notices.append((text, wait, style, use_text_width))

    def test_unlocked_text_shows_name_and_description(self) -> None:
        """验证 unlocked_text 返回的成就获得提示文本按固定格式包含配置中的名称与说明"""
        data = game_config.config_achievement[POWER_ID]
        self.assertEqual(
            achievement_service.unlocked_text(POWER_ID),
            f"\n\n   ○ 获得蚀刻章：{data.name} ○\n"
            f"      （{data.description}）\n\n\n",
        )

    def test_judge_by_value_settles_at_threshold(self) -> None:
        """验证按数值判定在低于阈值时不结算，达到阈值时结算并仅通知一次"""
        need = game_config.config_achievement[POWER_ID].value
        judge = achievement_service.get_achievement_judge_by_value
        self.assertFalse(judge(POWER_ID, need - 1))
        self.assertFalse(achievement.done(POWER_ID))
        self.assertEqual(self.notices, [])
        self.assertTrue(judge(POWER_ID, need))
        self.assertTrue(achievement.done(POWER_ID))
        self.assertFalse(judge(POWER_ID, need))
        self.assertEqual(self.notices, [unlocked_notice(POWER_ID)])

    def test_settle_by_type_uses_type_value(self) -> None:
        """验证按类型结算按调香计数返回达标成就编号，重复调用返回空列表且不触发通知"""
        first, second = AROMA_IDS
        count = game_config.config_achievement[first].value
        achievement.put("aromatherapy_count", count)
        expected = [
            cid
            for cid in AROMA_IDS
            if count >= game_config.config_achievement[cid].value
        ]
        self.assertIn(first, expected)
        self.assertNotIn(second, expected)
        aroma = get_text._("调香")
        self.assertEqual(achievement_service.settle_by_type(aroma), expected)
        self.assertEqual(achievement_service.settle_by_type(aroma), [])
        self.assertEqual(self.notices, [])

    def test_settle_and_notify_only_reports_new_ids(self) -> None:
        """验证 settle_and_notify 仅在存在新达成成就编号时经 ui_hooks 发出金色等待提示，重复或无新达成时不发出提示"""
        kind = game_config.config_achievement[POWER_ID].type
        settle = achievement_service.settle_and_notify
        self.assertEqual(settle(kind, POWER_ID), [POWER_ID])
        self.assertEqual(settle(kind, POWER_ID), [])
        self.assertEqual(settle(get_text._("调香")), [])
        self.assertEqual(self.notices, [unlocked_notice(POWER_ID)])

    def test_each_new_id_gets_one_notice(self) -> None:
        """验证一次 settle_and_notify 同时达成多个成就时返回全部编号，并按顺序逐条发出对应的金色等待提示"""
        count = max(
            game_config.config_achievement[cid].value for cid in AROMA_IDS
        )
        achievement.put("aromatherapy_count", count)
        settled = achievement_service.settle_and_notify(get_text._("调香"))
        self.assertEqual(settled, list(AROMA_IDS))
        self.assertEqual(
            self.notices, [unlocked_notice(cid) for cid in AROMA_IDS]
        )


class TkUiCallbacksTest(FastTestCase):
    """经 load_order 登记的 Tk 界面回调（tk_ui.callbacks）行为测试"""

    def setUp(self) -> None:
        """加载 LOAD_ORDER 登记回调，创建玩家与工作集并打桩文本绘制方法，结束后恢复当前面板"""
        super().setUp()
        core.load(load_order.LOAD_ORDER)
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        self.normal = self.enterContext(
            mock.patch.object(draw.NormalDraw, "draw", autospec=True)
        )
        self.wait = self.enterContext(
            mock.patch.object(draw.WaitDraw, "draw", autospec=True)
        )
        self.addCleanup(setattr, view, "now_panel_id", view.now_panel_id)

    @staticmethod
    def shown(drawn: mock.MagicMock) -> list[tuple[str, float, str, str]]:
        """
        从打桩后的绘制调用记录中提取每次绘制的类名、宽度、样式与文本。
        Keyword arguments:
        drawn -- mock.MagicMock，绘制方法的打桩对象
        Return arguments:
        list[tuple[str, float, str, str]] -- 每次绘制的 (类名, 宽度, 样式, 文本) 元组列表
        """
        return [
            (type(now).__name__, now.width, now.style, now.text)
            for (now,), _kwargs in drawn.call_args_list
        ]

    def test_notice_draws_like_the_backend_sites(self) -> None:
        """验证 emit_notice 的三类参数组合分别对应 WaitDraw 按配置宽度、WaitDraw 自定义样式与 NormalDraw 默认样式绘制"""
        width = normal_config.config_normal.text_width
        ui_hooks.emit_notice("tired", wait=True, use_text_width=True)
        ui_hooks.emit_notice("say", wait=True, style="gold_enrod")
        ui_hooks.emit_notice("short")
        self.assertEqual(
            self.shown(self.wait),
            [
                ("WaitDraw", width, "standard", "tired"),
                ("WaitDraw", 0, "gold_enrod", "say"),
            ],
        )
        self.assertEqual(
            self.shown(self.normal), [("NormalDraw", 0, "standard", "short")]
        )

    def test_panel_switch_sets_current_panel(self) -> None:
        """验证 switch_panel 将当前面板依次更新为地图面板与场景主面板"""
        for panel_id in (constant.Panel.SEE_MAP, constant.Panel.IN_SCENE):
            ui_hooks.switch_panel(panel_id)
            self.assertEqual(view.now_panel_id, panel_id)

    def test_new_achievement_draws_one_notice(self) -> None:
        """
        验证同一成就连续调用两次 settle_and_notify 时仅绘制一次宽度为 0、gold_enrod 样式
        且文本为 unlocked_text 的 WaitDraw，不触发 NormalDraw
        """
        kind = game_config.config_achievement[POWER_ID].type
        achievement_service.settle_and_notify(kind, POWER_ID)
        achievement_service.settle_and_notify(kind, POWER_ID)
        self.assertEqual(
            self.shown(self.wait),
            [
                (
                    "WaitDraw",
                    0,
                    "gold_enrod",
                    achievement_service.unlocked_text(POWER_ID),
                )
            ],
        )
        self.normal.assert_not_called()

    def test_panel_notice_draws_like_the_service(self) -> None:
        """
        验证 settle_and_notify 与 achievement_panel.draw_achievement_notice
        对相同成就列表绘出一致的 WaitDraw 记录且不触发 NormalDraw
        """
        ids = [POWER_ID, AROMA_IDS[0]]
        for achievement_id in ids:
            kind = game_config.config_achievement[achievement_id].type
            achievement_service.settle_and_notify(kind, achievement_id)
        backend = self.shown(self.wait)
        self.wait.reset_mock()
        achievement_panel.draw_achievement_notice(ids)
        self.assertEqual(self.shown(self.wait), backend)
        self.assertEqual(
            [text for _name, _w, _style, text in backend],
            [achievement_service.unlocked_text(cid) for cid in ids],
        )
        self.normal.assert_not_called()
