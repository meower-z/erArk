"""
卵与无壳卵提示文本测试
======================
- 提示发出（EggNoticeTest）：验证 egg_handle 与 soft_egg_handle 的五个结算函数经 ui_hooks 发出提示并更新卵数据。
- Tk 回调绘制（TkEggNoticeTest）：验证小世界已登记的 Tk 提示回调以 WaitDraw 与配置文本宽度绘制提示。
- 模块边界（EggImportBoundaryTest）：验证两个模块的源码不导入 Script.UI、tkinter 或 Script.Core.io_init。
"""

import datetime
import itertools
import os
from unittest import mock

from Script.Config import normal_config
from Script.Core import get_text
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import player_collection, pregnancy
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.System.Pregnancy_System import egg_handle, pregnancy_constant
from Script.System.Pregnancy_System import soft_egg_handle
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.fast.test_ejaculation_services import imports_in
from tests.world import ROOT

_ = get_text._
""" get_text 提供的翻译函数。 """
MOTHER = 1
""" 测试用产卵角色编号（1）。 """
NURSE = 2
""" 测试用保育员角色编号（2）。 """
BANNER = "\n※※※※※※※※※\n"
""" 卵提示文本首尾使用的分隔行。 """
SOURCES = (
    "Script/System/Pregnancy_System/egg_handle.py",
    "Script/System/Pregnancy_System/soft_egg_handle.py",
)
""" 受导入边界检查的两个模块的仓库相对路径元组。 """
BANNED = ("Script.UI", "tkinter", "Script.Core.io_init")
""" 禁止两个卵模块导入的模块路径前缀元组。 """


class EggCase(FastTestCase):
    """卵提示测试基类，准备测试角色、工作集与造卵辅助方法。"""

    def setUp(self) -> None:
        """创建玩家、产卵角色与保育员，并在当前内核状态上打开工作集。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.mother = self.world.chara(MOTHER, "产卵干员")
        self.nurse = self.world.chara(NURSE, "保育员")
        self.enterContext(working.based_on(core.state()))

    def lay(self, fertilized: bool, days_ago: int = 1) -> int:
        """
        给产卵角色新增一枚卵，并将其排出时间前移 days_ago 天。
        Keyword arguments:
        fertilized -- bool，卵是否受精
        days_ago -- int，排出时间早于当前游戏时间的天数，默认为 1
        Return arguments:
        int -- 新卵的编号
        """
        egg_id = egg_handle.add_egg(MOTHER, fertilized)
        with pregnancy.editing(MOTHER) as preg:
            preg.eggs[egg_id]["lay_time"] -= datetime.timedelta(days=days_ago)
        return egg_id

    def eggs(self) -> dict:
        """
        读取产卵角色当前的卵字典。
        Keyword arguments:
        无
        Return arguments:
        dict -- {卵编号: 卵数据字典}
        """
        return pregnancy.of(MOTHER).eggs

    def soft_egg(self, semen_count: float) -> int:
        """
        在玩家收藏品中登记一枚已超过受精等待时长的体外无壳卵。
        Keyword arguments:
        semen_count -- float，卵上的精液量（毫升）
        Return arguments:
        int -- 新登记的体外无壳卵编号
        """
        lay_time = game_time.now() - datetime.timedelta(
            hours=pregnancy_constant.SOFT_EGG_FERTILIZATION_DELAY_HOUR + 1
        )
        return player_collection.add_soft_egg(
            MOTHER, lay_time, ["中枢", "0"], semen_count
        )


class EggNoticeTest(EggCase):
    """验证五个卵结算函数经 ui_hooks 发出的提示参数与状态变化。"""

    def setUp(self) -> None:
        """将 ui_hooks._notices 替换为单个记录用模拟对象。"""
        super().setUp()
        self.notices = mock.Mock()
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.notices])
        )

    def assert_notice(self, text: str) -> None:
        """
        断言提示回调仅以 wait=True、style=None、use_text_width=True 收到一次 text。
        Keyword arguments:
        text -- str，预期的提示文本
        Return arguments:
        None -- 无返回值
        """
        self.notices.assert_called_once_with(
            text, wait=True, style=None, use_text_width=True
        )

    def test_nurse_identify_keeps_fertilized_eggs(self) -> None:
        """验证保育员代为鉴定时删除未受精卵、将受精卵标为已鉴定并发出保育员鉴定提示。"""
        kept = self.lay(True)
        dropped = self.lay(False)
        egg_handle.npc_identify_eggs_settle(MOTHER, NURSE)
        self.assertNotIn(dropped, self.eggs())
        self.assertTrue(self.eggs()[kept]["identified"])
        self.assertEqual(self.eggs()[kept]["identify_time"], game_time.now())
        self.assert_notice(
            BANNER
            + _(
                "\n保育员{0}在育儿室为{1}鉴定了产下的卵，发现其中{2}枚已经受精\n"
            ).format(self.nurse.name, self.mother.name, 1)
            + _("\n受精卵将一直放在育儿室中照料孵化\n")
            + BANNER
        )

    def test_take_eggs_marks_them_held(self) -> None:
        """验证 take_eggs_from_chara 返回拿走数量、标记玩家持有并登记索引且发出拿走提示。"""
        laid = [self.lay(True), self.lay(False)]
        self.assertEqual(egg_handle.take_eggs_from_chara(MOTHER), 2)
        for egg_id in laid:
            self.assertTrue(self.eggs()[egg_id]["held_by_player"])
        self.assertEqual(
            sorted(player_collection.get("held_eggs").values()),
            [(MOTHER, egg_id) for egg_id in laid],
        )
        self.assert_notice(
            _("\n从{0}处拿走了{1}枚未鉴定的卵\n").format(self.mother.name, 2)
        )

    def test_identify_held_eggs_returns_fertilized(self) -> None:
        """验证鉴定玩家持有的卵时清空持有索引、删除未受精卵、将受精卵标为已鉴定并取消持有且发出鉴定提示。"""
        kept = self.lay(True)
        dropped = self.lay(False)
        for egg_id in (kept, dropped):
            with pregnancy.editing(MOTHER) as preg:
                preg.eggs[egg_id]["held_by_player"] = True
            player_collection.add_held_egg(MOTHER, egg_id)
        egg_handle.identify_held_eggs_settle()
        self.assertEqual(player_collection.get("held_eggs"), {})
        self.assertNotIn(dropped, self.eggs())
        self.assertTrue(self.eggs()[kept]["identified"])
        self.assertFalse(self.eggs()[kept]["held_by_player"])
        self.assert_notice(
            BANNER
            + _("\n经过鉴定，{0}产下的卵中有{1}枚已经受精\n").format(
                self.mother.name, 1
            )
            + _("\n受精卵将一直放在育儿室中进行孵化\n")
            + BANNER
        )

    def test_lay_soft_egg_without_semen(self) -> None:
        """验证体内无精液时 lay_soft_egg 登记精液量为 0 的体外无壳卵并发出排卵提示。"""
        egg_id = soft_egg_handle.lay_soft_egg(MOTHER)
        egg = player_collection.get("soft_eggs")[egg_id]
        self.assertEqual((egg["mother_id"], egg["semen_count"]), (MOTHER, 0.0))
        self.assert_notice(
            BANNER
            + _(
                "\n{0}的体内排出了一大团裹在黏稠凝胶里的无壳卵块，"
                "成百上千颗细小的卵粒在半透明的胶质中若隐若现，凝胶里还没有任何精液\n"
            ).format(self.mother.name)
            + _(
                "\n请在{0}小时内尽量多地把精液射在这团卵块上，"
                "精液需要穿过凝胶层才能与卵粒结合，精液越多，受精的概率与受精卵粒的数量就越高\n"
            ).format(pregnancy_constant.SOFT_EGG_FERTILIZATION_DELAY_HOUR)
            + BANNER
        )

    def test_soft_egg_fertilizes_one_grain(self) -> None:
        """验证首轮判定成功且其余失败时，移出体外卵、为母亲新增一枚已鉴定无壳受精卵并发出受精提示。"""
        egg_id = self.soft_egg(1500.0)
        lay_time = player_collection.get("soft_eggs")[egg_id]["lay_time"]
        name = soft_egg_handle.get_soft_egg_name(egg_id)
        rolls = itertools.chain([1], itertools.repeat(101))
        with mock.patch.object(
            soft_egg_handle.random, "randint", side_effect=rolls
        ):
            soft_egg_handle.check_soft_eggs_fertilization()
        self.assertNotIn(egg_id, player_collection.get("soft_eggs"))
        (egg,) = self.eggs().values()
        self.assertEqual(
            (egg["fertilized"], egg["identified"], egg["soft"]),
            (True, True, True),
        )
        self.assertEqual(egg["lay_time"], lay_time)
        self.assert_notice(
            BANNER
            + _(
                "\n{1}ml精液渗过了{0}的凝胶层，与其中的卵粒完成了结合，"
                "共有{2}颗卵粒受精，已送往育儿室孵化\n"
            ).format(name, 1500, 1)
            + BANNER
        )


class TkEggNoticeTest(EggCase):
    """验证小世界已登记的 Tk 提示回调以 WaitDraw 绘制卵提示的行为。"""

    def setUp(self) -> None:
        """拦截 WaitDraw.draw 并用 self.drawn 记录被绘制对象的类名、文本与宽度。"""
        super().setUp()
        self.drawn: list[tuple[str, str, float]] = []
        self.enterContext(
            mock.patch.object(
                draw.WaitDraw, "draw", autospec=True, side_effect=self.keep
            )
        )

    def keep(self, now: draw.WaitDraw) -> None:
        """
        记录被拦截绘制对象的类名、文本与宽度到 self.drawn。
        Keyword arguments:
        now -- draw.WaitDraw，被调用 draw 的绘制对象
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append((type(now).__name__, now.text, now.width))

    def test_take_eggs_draws_wait_text(self) -> None:
        """验证 take_eggs_from_chara 经 Tk 回调以 WaitDraw 与配置文本宽度绘制一次拿走提示。"""
        self.lay(True)
        egg_handle.take_eggs_from_chara(MOTHER)
        self.assertEqual(
            self.drawn,
            [
                (
                    "WaitDraw",
                    _("\n从{0}处拿走了{1}枚未鉴定的卵\n").format(
                        self.mother.name, 1
                    ),
                    normal_config.config_normal.text_width,
                )
            ],
        )

    def test_failed_soft_egg_draws_wait_text(self) -> None:
        """验证精液量为 0 的体外卵结算时，Tk 回调以 WaitDraw 与配置文本宽度绘制一次未受精提示。"""
        egg_id = self.soft_egg(0.0)
        name = soft_egg_handle.get_soft_egg_name(egg_id)
        soft_egg_handle.check_soft_eggs_fertilization()
        text = (
            BANNER
            + _(
                "\n{1}ml精液没能穿透{0}的凝胶层与卵粒结合，"
                "没有一颗卵粒受精，整团卵块失去了活性\n"
            ).format(name, 0)
            + BANNER
        )
        self.assertEqual(
            self.drawn,
            [("WaitDraw", text, normal_config.config_normal.text_width)],
        )


class EggImportBoundaryTest(FastTestCase):
    """验证两个卵模块不导入界面与输入输出模块的语法树边界测试。"""

    def test_sources_import_no_ui(self) -> None:
        """验证 SOURCES 中两个模块源码的任意作用域均不导入 BANNED 中的模块或其子模块。"""
        for path in SOURCES:
            with open(os.path.join(ROOT, path), encoding="utf-8") as source:
                imports = imports_in(
                    source.read(), "Script.System.Pregnancy_System"
                )
            hits = sorted(
                name
                for name in imports
                for root in BANNED
                if name == root or name.startswith(root + ".")
            )
            self.assertEqual(hits, [], path)
