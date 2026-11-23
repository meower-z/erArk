"""
Script/Design 提示文本出口测试
==============================
- 提示出口：验证四个 Script/Design 模块的七处提示按预期参数经 ui_hooks.emit_notice 发出并由 Tk 回调绘制。
- 导入边界：验证五个 Script/Design 模块的源码在各作用域中均不导入 Script.UI、tkinter 与 Script.Core.io_init。
"""

import pathlib

from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import game_type, get_text
from Script.Design import clothing, handle_ability, handle_npc_ai_in_h
from Script.Design import second_behavior
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, flags, h_state
from Script.Modules.domains import wardrobe
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.fast.test_ejaculation_services import imports_in
from tests.world import ROOT

TARGET = 1
""" 测试使用的目标角色编号（1）。 """
NAME = "测试干员"
""" 测试使用的目标角色名称。 """
PLAYER = "博士"
""" 测试使用的玩家角色名称。 """
INTIMACY = 32
""" 亲密能力编号（32），该能力由 0 级升至 1 级只需一种宝珠。 """
OBEDIENCE = 31
""" 顺从能力编号（31），该能力在 3 级升级时需屈服刻印达到 1 级。 """
SOCKS = 1002
""" 测试使用的袜子服装模板编号（1002）。 """
MODULES = (
    "clothing",
    "handle_ability",
    "handle_npc_ai",
    "handle_npc_ai_in_h",
    "second_behavior",
)
""" 需要检查导入边界的五个 Script/Design 模块名元组。 """
BANNED = ("Script.UI", "tkinter", "Script.Core.io_init")
""" 五个 Script/Design 模块不得导入的包与模块名元组。 """

type Notice = tuple[str, bool, str | None, bool]
""" 一条提示的参数元组类型，依次为文本、是否等待确认、样式名与是否按文本宽度排版。 """

_ = get_text._


class DesignNoticeTest(FastTestCase):
    """四个 Script/Design 模块七处提示的 ui_hooks 派发参数与 Tk 回调绘制测试。"""

    def setUp(self) -> None:
        """
        创建玩家与目标角色，打开工作集，在已登记的提示回调旁追加记录回调，
        并拦截 NormalDraw 与 WaitDraw 的 draw 方法。
        """
        super().setUp()
        self.world.chara(0, PLAYER)
        self.world.chara(TARGET, NAME)
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

    def assert_notice(self, *expected: Notice) -> None:
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

    def test_panties_notice(self) -> None:
        """验证 pl_get_chara_pan 获取目标内裤时，按文本宽度发出一条不等待确认的获得提示。"""
        cloth = wardrobe.of(TARGET).cloth_wear[9][-1]
        clothing.pl_get_chara_pan(TARGET)
        text = _("\n获得了{0}的{1}，可在藏品馆里纳入收藏\n").format(
            NAME, game_config.config_clothing_tem[cloth].name
        )
        self.assert_notice((text, False, None, True))

    def test_socks_notice(self) -> None:
        """验证 pl_get_chara_socks 获取目标袜子时，按文本宽度发出一条不等待确认的获得提示。"""
        wardrobe.set_part(TARGET, "cloth_wear", 10, [SOCKS])
        clothing.pl_get_chara_socks(TARGET)
        text = _("\n获得了{0}的{1}，可在藏品馆里纳入收藏\n").format(
            NAME, game_config.config_clothing_tem[SOCKS].name
        )
        self.assert_notice((text, False, None, True))

    def test_ability_upgrade_notice(self) -> None:
        """验证目标拥有亲密 0 级所需宝珠时，gain_ability 将该能力升至 1 级并发出一条不等待确认的提示。"""
        for need in game_config.config_ability_up_data[INTIMACY][0]:
            juel_key, amount = need.split("|")
            abilities.juel(TARGET)[int(juel_key[1:])] = int(amount)
        handle_ability.gain_ability(TARGET)
        self.assertEqual(abilities.ability(TARGET)[INTIMACY], 1)
        text = _("{0}的{1}提升到{2}级\n").format(
            NAME, game_config.config_ability[INTIMACY].name, "1"
        )
        self.assert_notice((text, False, None, False))

    def test_extra_condition_notice(self) -> None:
        """验证目标顺从达到 3 级且缺少屈服刻印时，extra_ability_check 返回 0 并发出一条不等待确认的额外条件提示。"""
        abilities.ability(TARGET)[OBEDIENCE] = 3
        judge = handle_ability.extra_ability_check(OBEDIENCE, TARGET)
        self.assertEqual(judge, 0)
        text = (
            _("\n○顺从能力的提升需要额外满足以下条件：\n")
            + _("  屈服刻印等级大于等于{0}级\n").format(1)
            + _("  当前屈服刻印等级为{0}级\n").format(0)
        )
        self.assert_notice((text, False, None, False))

    def test_mark_notice(self) -> None:
        """
        验证类型 0 状态的累计计数达到 20 时，mark_effect 将能力 13（快乐刻印）升至 2 级
        并发出一条等待确认的结算提示。
        """
        happy = next(
            sid
            for sid, state in game_config.config_character_state.items()
            if state.type == 0
        )
        with h_state.editing(TARGET) as hs:
            hs.orgasm_count[happy] = [0, 20]
        second_behavior.mark_effect(TARGET, game_type.CharacterStatusChange())
        self.assertEqual(abilities.ability(TARGET)[13], 2)
        text = _("在快乐刻印的影响下，{0}的欲望提升至3级\n").format(NAME)
        self.assert_notice((text + "\n", True, None, False))

    def test_recover_notice(self) -> None:
        """验证交互对象的 unconscious_h 为 1 时，recover_from_unconscious_h 按文本宽度发出一条等待确认的恢复提示。"""
        activity.set_target(0, TARGET)
        flags.set(TARGET, unconscious_h=1)
        handle_npc_ai_in_h.recover_from_unconscious_h(0)
        text = _("\n{0}从无意识状态中恢复过来\n").format(NAME)
        self.assert_notice((text, True, None, True))

    def test_noise_wake_notice(self) -> None:
        """验证目标角色的 unconscious_h 为 2 时，wake_by_noise 按文本宽度发出一条等待确认的唤醒提示。"""
        flags.set(TARGET, unconscious_h=2)
        handle_npc_ai_in_h.wake_by_noise(0, TARGET)
        text = _("\n{0}被{1}的动静吵醒了\n").format(NAME, PLAYER)
        self.assert_notice((text, True, None, True))


class ImportBoundaryTest(FastTestCase):
    """五个 Script/Design 模块的导入边界语法树测试。"""

    def test_modules_skip_ui(self) -> None:
        """验证 MODULES 中五个模块的源码在各作用域中均不导入 BANNED 所列的界面包、tkinter 与输入输出模块。"""
        for name in MODULES:
            path = pathlib.Path(ROOT, "Script", "Design", f"{name}.py")
            found = imports_in(
                path.read_text(encoding="utf-8"), "Script.Design"
            )
            with self.subTest(module=name):
                self.assertEqual(
                    {
                        module
                        for module in found
                        for banned in BANNED
                        if module == banned or module.startswith(banned + ".")
                    },
                    set(),
                )
