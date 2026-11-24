"""
素质与妊娠结算提示出口测试
==========================
- 素质提示：验证酒量素质结算提示经 ui_hooks.emit_notice 发出并由 Tk 回调绘制。
- 妊娠提示：验证受精判定提示与 body_part_grow 的提示经 ui_hooks.emit_notice 发出并由 Tk 回调绘制。
- 导入边界：验证 handle_talent.py 与 pregnancy_handle.py 通过后端界面边界守卫的 banned_imports 检查。
"""

from unittest import mock

from Script.Config import normal_config
from Script.Core import get_text
from Script.Design import handle_talent
from Script.Kernel import core
from Script.Modules.domains import abilities, pregnancy, relations
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.System.Pregnancy_System import pregnancy_handle
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports

TARGET = 1
""" 测试使用的目标角色编号（1）。 """
NAME = "测试干员"
""" 测试使用的目标角色名称。 """
MOTHER = 2
""" body_part_grow 测试中作为 TARGET 母亲关系的角色编号（2）。 """
MACHINE = 2
""" 机械种族编号（2）。 """
DRINK_EXP = 94
""" 饮酒经验编号（94）。 """
BODY_PART_TALENTS = range(126, 133)
""" body_part_grow 读取的素质编号范围（126~132）。 """
SOURCES = (
    "Script/Design/handle_talent.py",
    "Script/System/Pregnancy_System/pregnancy_handle.py",
)
""" 受导入边界检查的两个模块的仓库相对路径元组。 """

type Notice = tuple[str, bool, str | None, bool]
""" 一条提示的参数元组类型，依次为文本、是否等待确认、样式名与是否按文本宽度排版。 """

_ = get_text._


class NoticeCase(FastTestCase):
    """提示出口测试基类，记录 ui_hooks 派发参数与 Tk 回调绘制对象并提供核对方法。"""

    def setUp(self) -> None:
        """
        创建玩家角色，打开工作集，在已登记的提示回调之后追加记录回调，
        并拦截 NormalDraw.draw 与 WaitDraw.draw。
        """
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
        依次核对 Tk 回调绘出的绘制对象列表与 ui_hooks 记录的提示参数列表。
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


class TalentNoticeTest(NoticeCase):
    """handle_talent 提示的 ui_hooks 派发参数与 Tk 回调绘制测试。"""

    def test_drink_talent_notices(self) -> None:
        """验证 chara_settle_drink_talent 在满足三档酒量条件时依次发出三条等待确认的酒量素质结算提示。"""
        self.world.chara(TARGET, NAME)
        abilities.talent(TARGET)[360] = 1
        abilities.talent(TARGET)[353] = 0
        abilities.talent(TARGET)[354] = 0
        abilities.experience(TARGET)[DRINK_EXP] = 300
        handle_talent.chara_settle_drink_talent(TARGET)
        texts = (
            _(
                "\n{0}因为稍微习惯了酒精（饮酒经验>=30），因此对酒精的耐受力稍微提高了\n"
            ).format(NAME)
            + _("{0}失去了[酒量差]\n").format(NAME)
            + _("{0}获得了[酒量差]\n").format(NAME),
            _(
                "\n{0}因为经常饮酒（饮酒经验>=100），因此对酒精的耐受力提高了\n"
            ).format(NAME)
            + _("{0}失去了[酒量差]\n").format(NAME),
            _(
                "\n{0}因为长期性地饮酒（饮酒经验>=300），因此对酒精的耐受力大大提高了\n"
            ).format(NAME)
            + _("{0}获得了[好酒量]\n").format(NAME),
        )
        self.assert_notices(*((text, True, None, False) for text in texts))


class PregnancyNoticeTest(NoticeCase):
    """pregnancy_handle 提示的 ui_hooks 派发参数与 Tk 回调绘制测试。"""

    def test_machine_fertilization_notice(self) -> None:
        """验证 check_fertilization 在机械体无素质 171 分支中返回 None 并按文本宽度发出等待确认的受精判定提示。"""
        self.world.chara(TARGET, NAME, race=MACHINE)
        abilities.talent(TARGET)[171] = 0
        with pregnancy.editing(TARGET) as preg:
            preg.ovulation_flag = True
            preg.fertilization_rate = 50
        self.assertEqual(pregnancy_handle.check_fertilization(TARGET), None)
        text = _("\n{0}是机械体，且未安装生育模组，无法受精\n").format(NAME)
        self.assert_notices((text, True, None, True))

    def test_body_part_grow_print_flag(self) -> None:
        """验证素质 126~132 为 0 时，body_part_grow 的提示在 print_flag 为假时不发出，为真时按文本宽度等待发出。"""
        self.world.chara(MOTHER, "母亲")
        self.world.chara(TARGET, NAME)
        relations.mother_id.set(TARGET, MOTHER)
        for cid in (TARGET, MOTHER):
            for talent_id in BODY_PART_TALENTS:
                abilities.talent(cid)[talent_id] = 0
        self.assertEqual(pregnancy_handle.body_part_grow(TARGET), "")
        self.assert_notices()
        self.assertEqual(pregnancy_handle.body_part_grow(TARGET, True), "")
        self.assert_notices(("", True, None, True))


class ImportBoundaryTest(FastTestCase):
    """handle_talent.py 与 pregnancy_handle.py 的导入边界语法树测试。"""

    def test_sources_pass_backend_guard(self) -> None:
        """验证 SOURCES 中两个模块源码经后端界面边界守卫 banned_imports 检查均返回空列表。"""
        for path in SOURCES:
            with self.subTest(path=path):
                self.assertEqual(
                    banned_imports((ROOT / path).read_bytes(), path), []
                )
