"""
外勤委托与角色行为提示出口测试
==============================
- 外勤委托提示：验证新载具奖励提示与委托完成汇总提示经 ui_hooks 发出并由 Tk 回调绘制。
- 结算后的停顿：验证角色状态结算后的停顿提示按玩家身份与干员停顿设置经 ui_hooks 发出并绘制。
"""

import datetime
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import get_text
from Script.Design import character_behavior, event, game_time, settle_behavior
from Script.Kernel import core
from Script.Modules.domains import commission
from Script.Modules.gameplay_resolution import achievement_service, ui_hooks
from Script.Modules.gameplay_resolution import settle_hooks
from Script.Modules.gameplay_resolution import working
from Script.System.Field_Commission_System import field_commission_function
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase

VEHICLE_COMMISSION = 1104
""" 发放 51 号新载具奖励的委托编号（1104）。 """
NEW_VEHICLE = 51
""" 1104 号委托作为奖励发放的新载具编号（51）。 """
COMMISSION = 2
""" 奖励为 10 个 11 号资源的测试委托编号（2）。 """
REWARD_RESOURCE = 11
""" 2 号测试委托所发放奖励的资源编号（11）。 """
NPC = 1
""" 停顿测试使用的非玩家角色编号（1）。 """
PAUSE_SETTING = 19
""" 控制干员显示文本与结算数据时是否停顿的绘制设置索引（19）。 """

type Notice = tuple[str, bool, str | None, bool]
""" 一条提示的参数元组类型，依次为文本、是否等待确认、样式名与是否按文本宽度排版。 """

_ = get_text._


class NoticeCase(FastTestCase):
    """提示出口测试基类，初始化玩家与工作集，记录提示参数并拦截绘制方法。"""

    def setUp(self) -> None:
        """创建玩家角色、打开工作集，追加提示记录回调并拦截 NormalDraw 与 WaitDraw 的 draw 方法。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        self.notices: list[Notice] = []
        self.enterContext(
            mock.patch.object(
                ui_hooks, "_notices", [*ui_hooks._notices, self.record]
            )
        )
        self.drawn: list[tuple[str, float, str, str]] = []
        for cls in (draw.NormalDraw, draw.WaitDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.keep
                )
            )

    def record(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        记录一条经 ui_hooks.emit_notice 派发的提示参数。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名，为 None 时使用默认样式
        use_text_width -- bool，是否按配置文本宽度排版
        Return arguments:
        None -- 无返回值
        """
        self.notices.append((text, wait, style, use_text_width))

    def keep(self, now: draw.NormalDraw) -> None:
        """
        记录被拦截绘制对象的类名、宽度、样式与文本。
        Keyword arguments:
        now -- draw.NormalDraw，调用 draw 方法的绘制对象实例
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append((type(now).__name__, now.width, now.style, now.text))

    def assert_notices(self, *expected: Notice) -> None:
        """
        依次核对 Tk 回调绘出的绘制对象列表与 ui_hooks 记录的提示列表。
        Keyword arguments:
        expected -- Notice，按顺序预期的提示参数元组
        Return arguments:
        None -- 无返回值
        """
        width = normal_config.config_normal.text_width
        self.assertEqual(
            self.drawn,
            [
                (
                    "WaitDraw" if wait else "NormalDraw",
                    width if use_text_width else 0,
                    style or draw.NormalDraw.style,
                    text,
                )
                for text, wait, style, use_text_width in expected
            ],
        )
        self.assertEqual(self.notices, list(expected))


class CommissionNoticeTest(NoticeCase):
    """外勤委托的新载具奖励提示与委托完成汇总提示测试。"""

    def setUp(self) -> None:
        """调用基类准备步骤，并将 achievement_service.settle_by_type 替换为返回空列表的模拟函数。"""
        super().setUp()
        self.enterContext(
            mock.patch.object(
                achievement_service, "settle_by_type", return_value=[]
            )
        )

    def test_vehicle_reward_notice(self) -> None:
        """验证 1104 号委托未发放时不授予载具且无提示，发放时授予 51 号载具并发出新载具奖励提示。"""
        field_commission_function.get_commission_demand_and_reward(
            VEHICLE_COMMISSION, [], True, False
        )
        self.assert_notices()
        self.assertEqual(commission.vehicles()[NEW_VEHICLE][0], 0)
        field_commission_function.get_commission_demand_and_reward(
            VEHICLE_COMMISSION, [], True, True
        )
        text = _("\n获得了一辆新的载具：{0}\n").format(
            game_config.config_vehicle[NEW_VEHICLE].name
        )
        self.assert_notices((text, True, "gold_enrod", True))
        self.assertEqual(commission.vehicles()[NEW_VEHICLE][0], 1)

    def test_finish_summary_notice(self) -> None:
        """验证 judge_field_commission_finish 在委托未到期时无提示，到期后登记完成并发出委托完成汇总提示。"""
        later = game_time.now() + datetime.timedelta(hours=1)
        commission.start(COMMISSION, [], later, [])
        field_commission_function.judge_field_commission_finish()
        self.assert_notices()
        commission.finish(COMMISSION)
        due = game_time.now() - datetime.timedelta(minutes=1)
        commission.start(COMMISSION, [], due, [])
        field_commission_function.judge_field_commission_finish()
        text = "\n" + _("完成了委托：{0}，获得奖励：{1}\n\n").format(
            game_config.config_commission[COMMISSION].name,
            f"{game_config.config_resouce[REWARD_RESOURCE].name}:10 ",
        )
        self.assert_notices((text, True, "gold_enrod", True))
        self.assertIn(COMMISSION, commission.finished())


class BehaviorPauseTest(NoticeCase):
    """验证 judge_character_status 结算后的停顿提示在玩家、干员与空结算下的行为。"""

    def setUp(self) -> None:
        """创建非玩家角色并记录结算文本回调输出。同时打桩事件处理返回 None 与行为结算返回预设文本。"""
        super().setUp()
        self.world.chara(NPC, "干员")
        self.settle_text = "数值变化"
        self.drawn_texts: list[str] = []
        self.enterContext(
            mock.patch.object(event, "handle_event", return_value=None)
        )
        self.enterContext(
            mock.patch.object(
                settle_hooks, "_settle_texts", [self.drawn_texts.append]
            )
        )
        self.enterContext(
            mock.patch.object(
                settle_behavior,
                "handle_settle_behavior",
                side_effect=lambda *args: self.settle_text,
            )
        )

    def settle(self, character_id: int, pause: int) -> None:
        """
        临时将绘制设置 19 设为 pause 后调用 judge_character_status，并断言其返回 1。
        Keyword arguments:
        character_id -- int，要结算的角色编号
        pause -- int，写入绘制设置 19 的停顿开关值（0 关闭，1 开启）
        Return arguments:
        None -- 无返回值
        """
        with mock.patch.dict(
            normal_config.system_setting.draw_setting, {PAUSE_SETTING: pause}
        ):
            self.assertEqual(
                character_behavior.judge_character_status(character_id), 1
            )

    def test_player_always_pauses(self) -> None:
        """验证绘制设置 19 关闭时，玩家结算仍派发一次结算文本并发出一次停顿提示。"""
        self.settle(0, 0)
        self.assertEqual(self.drawn_texts, ["数值变化"])
        self.assert_notices(("\n", True, None, True))

    def test_npc_pause_follows_setting(self) -> None:
        """验证非玩家角色在绘制设置 19 关闭时无停顿、开启时停顿一次。两次结算均派发结算文本。"""
        self.settle(NPC, 0)
        self.assert_notices()
        self.settle(NPC, 1)
        self.assertEqual(self.drawn_texts, ["数值变化"] * 2)
        self.assert_notices(("\n", True, None, True))

    def test_empty_settlement_skips_pause(self) -> None:
        """验证结算文本为空字符串时，即使玩家开启绘制设置 19 也不派发文本且不发出停顿提示。"""
        self.settle_text = ""
        self.settle(0, 1)
        self.assertEqual(self.drawn_texts, [])
        self.assert_notices()
