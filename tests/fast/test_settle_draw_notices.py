"""
结算提示经 ui_hooks 发出的测试
==============================
- 提示发出（SettleNoticeTest）：验证 item_effect、realtime_settle 与 default_cloth 在六类结算场景中经 ui_hooks
  发出预期文本与显示参数。
- Tk 回调绘制（TkSettleNoticeTest）：沿用测试环境已登记的 Tk 提示回调，验证这六类结算场景以预期绘制类、文本、
  宽度与样式调用 NormalDraw.draw 或 WaitDraw.draw。
"""

import datetime
from collections.abc import Callable
from typing import NamedTuple
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import game_type, get_text
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import action_info, activity, dirty
from Script.Modules.domains import entertainment, flags, identity, wardrobe
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Settle import default_cloth, item_effect, realtime_settle
from Script.System.Education_System import sex_class_handle
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase

TARGET = 1
""" 测试使用的目标角色编号（1）。 """
PANTIES = 9
""" 测试使用的内裤服装类型编号（9）。 """
BLANK_WAITS = (
    default_cloth.handle_get_t_pan,
    default_cloth.handle_get_t_sock,
    default_cloth.handle_get_scene_t_pan,
    default_cloth.handle_get_scene_t_socks,
)
""" 获取内裤或袜子后发出空行等待提示的四个结算函数元组。 """


class Notice(NamedTuple):
    """一条预期提示的文本与显示参数记录，依次对应 ui_hooks.emit_notice 的 text、wait、style 与 use_text_width。"""

    text: str
    wait: bool
    style: str | None
    use_text_width: bool


class SettleNoticeTest(FastTestCase):
    """验证三个结算模块经 ui_hooks 发出提示参数的单元测试。"""

    def setUp(self) -> None:
        """
        创建玩家角色与全裸目标角色、打开工作集上下文、将玩家交互对象设为 TARGET，
        并选取最小的内裤服装模板编号存入 self.panties。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, "测试干员", naked=True)
        self.enterContext(working.based_on(core.state()))
        activity.set_target(0, TARGET)
        self.panties = min(
            cid
            for cid, tem in game_config.config_clothing_tem.items()
            if tem.clothing_type == PANTIES
        )

    def expect(self, run: Callable[[], object], notices: list[Notice]) -> None:
        """
        将 ui_hooks._notices 临时替换为单个模拟回调并执行 run，断言回调按顺序收到与 notices 一致的调用参数。
        Keyword arguments:
        run -- Callable[[], object]，触发结算提示的无参可调用对象
        notices -- list[Notice]，预期按顺序收到的提示参数列表
        Return arguments:
        None -- 无返回值
        """
        handler = mock.Mock()
        with mock.patch.object(ui_hooks, "_notices", [handler]):
            run()
        self.assertEqual(
            handler.call_args_list,
            [
                mock.call(
                    n.text,
                    wait=n.wait,
                    style=n.style,
                    use_text_width=n.use_text_width,
                )
                for n in notices
            ],
        )

    def settle(self, effect: Callable[..., None], cid: int) -> None:
        """
        以角色编号 cid、时间增量 1、空状态变更对象与当前游戏时间调用结算效果函数 effect。
        Keyword arguments:
        effect -- Callable[..., None]，待调用的结算效果函数
        cid -- int，执行结算的角色编号
        Return arguments:
        None -- 无返回值
        """
        effect(cid, 1, game_type.CharacterStatusChange(), game_time.now())

    def test_enema_end_reports_expelled_semen(self) -> None:
        """
        验证目标 a_clean 为 3 且角色 0 的部位 8 精液量为 100 时，
        handle_target_enema_end 发出一条 90ml 排出提示（wait=False、style=None、use_text_width=True）。
        """
        dirty.set(TARGET, a_clean=3)
        with dirty.editing(0) as d:
            d.body_semen[8][1] = 100
        text = get_text._("{0}的后穴喷出了{1}ml的精液\n").format(
            identity.of(TARGET).name, 90
        )
        self.expect(
            lambda: self.settle(item_effect.handle_target_enema_end, 0),
            [Notice(text, False, None, True)],
        )

    def test_hotel_checkout_notice(self) -> None:
        """
        验证酒店房型编号为 1 且退房时间已过 1 小时时，judge_pl_real_time_data 发出一条自动退房提示（wait=False、
        style=None、use_text_width=False）。
        """
        entertainment.set_hotel_room(1)
        action_info.set(
            0, "check_out_time", game_time.now() - datetime.timedelta(hours=1)
        )
        text = get_text._("\n您入住的{0}到退房时间了，已自动退房\n").format(
            get_text._("标间")
        )
        self.expect(
            realtime_settle.judge_pl_real_time_data,
            [Notice(text, False, None, False)],
        )

    def test_sex_class_reminders(self) -> None:
        """
        验证 sex_class_handle.check_and_send_notify 返回两条提醒文本且行为编号为空串时，
        settle_sex_class_notify 按序发出两条提示（wait=False、style=None、use_text_width=True）。
        """
        texts = ["提醒一\n", "提醒二\n"]
        self.enterContext(
            mock.patch.object(
                sex_class_handle, "check_and_send_notify", return_value=texts
            )
        )
        now = game_time.now()
        self.expect(
            lambda: realtime_settle.settle_sex_class_notify(
                identity.of(0), "", now, now - datetime.timedelta(minutes=5)
            ),
            [Notice(text, False, None, True) for text in texts],
        )

    def test_sanity_out_breaks_arts(self) -> None:
        """验证 break_arts 发出一条源石技艺中断提示（wait=True、style="red"、use_text_width=True）。"""
        text = get_text._("\n理智值不足，开启的源石技艺已全部中断\n")
        self.expect(
            realtime_settle.break_arts, [Notice(text, True, "red", True)]
        )

    def test_taking_clothes_waits_on_blank_line(self) -> None:
        """
        验证依次调用 BLANK_WAITS 中的四个结算函数后，各发出一条换行符等待提示（wait=True、style=None、
        use_text_width=True）。
        """
        self.expect(
            lambda: [self.settle(effect, 0) for effect in BLANK_WAITS],
            [Notice("\n", True, None, True)] * len(BLANK_WAITS),
        )

    def test_cloth_back_notice(self) -> None:
        """
        验证目标 cloth_off[PANTIES] 含内裤且 unconscious_h 分别为 0 与 1 时，
        handle_self_cloth_back 各发出一条对应分支的穿回提示（wait=True、style=None、use_text_width=True）。
        """
        for unconscious, template in (
            (0, "\n{0}穿回了脱下的衣服\n"),
            (1, "\n给{0}穿上了脱下的衣服，并尽量整理成H前的样子\n"),
        ):
            with self.subTest(unconscious_h=unconscious):
                flags.set(TARGET, unconscious_h=unconscious)
                cloth = wardrobe.clone_mutable_snapshot(TARGET)
                cloth.cloth_off[PANTIES] = [self.panties]
                wardrobe.put(TARGET, cloth)
                text = get_text._(template).format(identity.of(TARGET).name)
                self.expect(
                    lambda: self.settle(
                        default_cloth.handle_self_cloth_back, TARGET
                    ),
                    [Notice(text, True, None, True)],
                )


class TkSettleNoticeTest(SettleNoticeTest):
    """沿用小世界已登记的 Tk 提示回调重跑 SettleNoticeTest 用例，验证各结算提示的绘制类、文本、宽度与样式。"""

    def expect(self, run: Callable[[], object], notices: list[Notice]) -> None:
        """
        保留已登记的 Tk 提示回调并拦截 NormalDraw.draw 与 WaitDraw.draw，执行 run 后断言记录到的绘制类名、文本、
        宽度与样式与 notices 对应。
        Keyword arguments:
        run -- Callable[[], object]，触发结算提示的无参可调用对象
        notices -- list[Notice]，预期按顺序绘制的提示参数列表
        Return arguments:
        None -- 无返回值
        """
        drawn: list[tuple[str, str, float, str]] = []

        def keep(now: draw.NormalDraw) -> None:
            """
            记录被拦截绘制对象的类名、文本、宽度与样式。
            Keyword arguments:
            now -- draw.NormalDraw，被调用 draw 的绘制对象
            Return arguments:
            None -- 无返回值
            """
            drawn.append((type(now).__name__, now.text, now.width, now.style))

        with (
            mock.patch.object(
                draw.NormalDraw, "draw", autospec=True, side_effect=keep
            ),
            mock.patch.object(
                draw.WaitDraw, "draw", autospec=True, side_effect=keep
            ),
        ):
            run()
        width = normal_config.config_normal.text_width
        self.assertEqual(
            drawn,
            [
                (
                    "WaitDraw" if n.wait else "NormalDraw",
                    n.text,
                    width if n.use_text_width else 0,
                    n.style or draw.NormalDraw.style,
                )
                for n in notices
            ],
        )
