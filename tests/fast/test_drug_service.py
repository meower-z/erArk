"""
药物使用效果服务测试
====================
- 身体部位与未知药物：验证 21~28 号药物委派给 body_part_talent_update，以及未知编号 99 发出空正文提示。
- 素质开关药物：验证 33/34、37/38 与 40/41 号药物切换对应素质并发出等待提示。
- 妊娠、孵化与成长加速：验证 35、36 与 39 号药物的天数累加、无效果分支、选择编号重置与季节日期格式。
- 送礼结算调用：验证 handle_give_gift_add_adjust 扣除 33 号药物道具、调用药物服务并生效。
- 面板边界：验证 gift_panel 模块不含 handle_drug_use_effect 属性。
"""

import datetime
from unittest import mock

from Script.Core import game_type, get_text
from Script.Design import game_time, handle_talent
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, inventory, pregnancy
from Script.Modules.gameplay_resolution import drug_service, ui_hooks, working
from Script.System.Pregnancy_System import egg_handle, pregnancy_constant
from Script.System.Pregnancy_System import pregnancy_handle
from Script.Settle import default as settle_default
from Script.UI.Moudle import draw
from Script.UI.Panel import gift_panel, pregnancy_panel
from tests.fast.base import FastTestCase

TARGET = 1
""" 测试使用的目标角色编号（1）。 """
NAME = "测试干员"
""" 测试目标角色名称。 """
CHILD = 2
""" 成长加速测试使用的婴儿角色编号（2）。 """
CHILD_NAME = "测试孩子"
""" 成长加速测试使用的婴儿角色名称。 """
GIFT_DRUG = 33
""" 送礼结算测试使用的 11 类药物礼物编号（33）。 """
EGG = 7
""" 孵化加速测试使用的卵编号（7）。 """
START = datetime.datetime(2025, 2, 14, 8, 30)
""" 日期与加速计算测试使用的非四季月基准时间 datetime(2025, 2, 14, 8, 30)。 """
BODY_PART_DRUGS = {
    21: ([121, 122, 123, 124, 125], True, "胸部"),
    22: ([121, 122, 123, 124, 125], False, "胸部"),
    23: ([126, 127, 128], True, "臀部"),
    24: ([126, 127, 128], False, "臀部"),
    25: ([129, 130], True, "腿部"),
    26: ([129, 130], False, "腿部"),
    27: ([131, 132], True, "足部"),
    28: ([131, 132], False, "足部"),
}
""" 21~28 号身体部位药物的映射表，值为素质编号列表、增减方向与部位名。 """
TALENT_DRUGS = (
    (33, 34, 27, "{0}获得了【泌乳】\n", "{0}失去了【泌乳】\n"),
    (
        37,
        38,
        25,
        "{0}获得了【假孕孕肚】，肚子像真正的孕妇一样隆起来了\n",
        "{0}失去了【假孕孕肚】，隆起的肚子恢复了原状\n",
    ),
    (
        40,
        41,
        28,
        "{0}获得了【成长停滞】，在使用成长继续药之前她会一直保持在当前的阶段\n",
        "{0}失去了【成长停滞】，她会继续正常成长\n",
    ),
)
""" 素质开关类药物的测试配置元组，每项含开启药号、关闭药号、素质编号与对应提示模板。 """

_ = get_text._


class DrugCase(FastTestCase):
    """药物使用效果测试基类，初始化测试角色、工作集以及提示与绘制拦截。"""

    def setUp(self) -> None:
        """创建玩家与目标角色、打开工作集，追加提示记录回调并拦截绘制方法。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, NAME)
        self.enterContext(working.based_on(core.state()))
        self.notices: list[tuple[str, bool, str | None, bool]] = []
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

    def use(self, drug_id: int, body: str) -> None:
        """
        对目标角色调用 handle_drug_use_effect，并核对单条 WaitDraw 绘制结果与提示记录。
        Keyword arguments:
        drug_id -- int，要测试的药物编号
        body -- str，不含前缀换行与空格的预期提示正文
        Return arguments:
        None -- 无返回值
        """
        self.notices.clear()
        self.drawn.clear()
        drug_service.handle_drug_use_effect(TARGET, drug_id)
        text = "\n  " + body
        self.assertEqual(self.drawn, [("WaitDraw", 0, "gold_enrod", text)])
        self.assertEqual(self.notices, [(text, True, "gold_enrod", False)])


class BodyPartDrugTest(DrugCase):
    """身体部位药物委派与未知药物编号提示测试。"""

    def test_body_part_drugs_delegate(self) -> None:
        """验证 21~28 号药物按映射参数调用 body_part_talent_update 并输出其返回值。"""
        for drug_id, (talents, increase, part) in BODY_PART_DRUGS.items():
            with self.subTest(drug_id=drug_id):
                with mock.patch.object(
                    handle_talent,
                    "body_part_talent_update",
                    return_value=f"{drug_id}\n",
                ) as update:
                    self.use(drug_id, f"{drug_id}\n")
                update.assert_called_once_with(
                    TARGET, talents, increase, _(part)
                )

    def test_unknown_drug_emits_blank_notice(self) -> None:
        """验证未知药物编号 99 发出正文为空字符串的等待提示。"""
        self.use(99, "")


class TalentDrugTest(DrugCase):
    """33/34、37/38 与 40/41 号素质开关药物测试。"""

    def test_talent_drugs_toggle(self) -> None:
        """验证三组素质开关药物分别将对应素质设为 1 或 0 并发出对应提示。"""
        for give, stop, talent_id, gained, lost in TALENT_DRUGS:
            with self.subTest(give=give, stop=stop):
                self.use(give, _(gained).format(NAME))
                self.assertEqual(abilities.talent(TARGET)[talent_id], 1)
                self.use(stop, _(lost).format(NAME))
                self.assertEqual(abilities.talent(TARGET)[talent_id], 0)


class PregnancyAccelerationTest(DrugCase):
    """35 号妊娠加速药的状态更新与提示测试。"""

    def setUp(self) -> None:
        """调用基类准备步骤，并为目标角色写入初始妊娠加速天数与受精时间。"""
        super().setUp()
        pregnancy.update(
            TARGET, acceleration_days=5.0, fertilization_time=START
        )

    def test_acceleration_adds_days(self) -> None:
        """验证 35 号药物在可加速量为正时累加 acceleration_days 并输出一致的预计临盆日期。"""
        with mock.patch.object(
            pregnancy_handle,
            "get_pregnancy_acceleration_amount",
            return_value=10.5,
        ):
            predict = game_time.get_predict_date(
                pregnancy_constant.PARTURIENT_DAY - 15, START
            )
            self.use(
                35,
                _(
                    "本次加速{0}，累计加速{1}，{2}的预计临盆日期提前到了{3}\n"
                ).format(
                    game_time.get_duration_text(10.5),
                    game_time.get_duration_text(15),
                    NAME,
                    pregnancy_panel.get_date_text(predict),
                ),
            )
        self.assertEqual(pregnancy.of(TARGET).acceleration_days, 15.5)

    def test_capped_acceleration_has_no_effect(self) -> None:
        """验证 35 号药物在可加速量为 0 时保持 acceleration_days 不变并输出无效果提示。"""
        with mock.patch.object(
            pregnancy_handle,
            "get_pregnancy_acceleration_amount",
            return_value=0,
        ):
            self.use(
                35,
                _("{0}的孕期已经加速到极限，药物没有产生效果\n").format(NAME),
            )
        self.assertEqual(pregnancy.of(TARGET).acceleration_days, 5.0)


class EggAccelerationTest(DrugCase):
    """36 号孵化加速药的状态更新、选择重置与提示测试。"""

    def setUp(self) -> None:
        """调用基类准备步骤，写入已鉴定已受精测试卵并设置玩家的 gift_egg_id。"""
        super().setUp()
        egg = {
            "identified": True,
            "fertilized": True,
            "lay_time": START,
            "acceleration_days": 2.0,
        }
        pregnancy.update(TARGET, eggs={EGG: egg})
        activity.update_behavior(0, gift_egg_id=EGG)

    def egg_days(self) -> float:
        """
        读取目标角色测试卵当前的加速天数。
        Return arguments:
        float -- 测试卵字典中的 acceleration_days 数值
        """
        return pregnancy.of(TARGET).eggs[EGG]["acceleration_days"]

    def test_acceleration_adds_days(self) -> None:
        """验证 36 号药物在可加速量为正时累加卵加速天数、输出预计破壳日期并重置 gift_egg_id。"""
        with mock.patch.object(
            egg_handle, "get_egg_acceleration_amount", return_value=3.0
        ):
            predict = game_time.get_predict_date(
                pregnancy_constant.HATCH_TOTAL_DAY - 5, START
            )
            self.use(
                36,
                _(
                    "本次加速{0}，累计加速{1}，这枚卵的预计破壳日期提前到了{2}\n"
                ).format(
                    game_time.get_duration_text(3.0),
                    game_time.get_duration_text(5),
                    pregnancy_panel.get_date_text(predict),
                ),
            )
        self.assertEqual(self.egg_days(), 5.0)
        self.assertEqual(activity.behavior(0).gift_egg_id, -1)

    def test_missing_egg_has_no_effect(self) -> None:
        """验证选中的卵编号不存在时 36 号药物不修改卵数据、输出无效果提示并重置 gift_egg_id。"""
        activity.update_behavior(0, gift_egg_id=EGG + 1)
        self.use(36, _("选中的卵已经不存在，药物没有产生效果\n"))
        self.assertEqual(self.egg_days(), 2.0)
        self.assertEqual(activity.behavior(0).gift_egg_id, -1)

    def test_capped_egg_has_no_effect(self) -> None:
        """验证可加速量为 0 时 36 号药物不修改卵数据、输出无效果提示并重置 gift_egg_id。"""
        with mock.patch.object(
            egg_handle, "get_egg_acceleration_amount", return_value=0
        ):
            self.use(36, _("这枚卵已经加速到极限，药物没有产生效果\n"))
        self.assertEqual(self.egg_days(), 2.0)
        self.assertEqual(activity.behavior(0).gift_egg_id, -1)


class ChildGrowthTest(DrugCase):
    """39 号成长加速药的婴儿与自身目标分支测试。"""

    def setUp(self) -> None:
        """调用基类准备步骤，创建婴儿角色、写入成长加速初始值并打桩妊娠辅助函数。"""
        super().setUp()
        self.world.chara(CHILD, CHILD_NAME)
        pregnancy.update(CHILD, growth_acceleration_days=4.0, born_time=START)
        activity.update_behavior(0, gift_child_id=CHILD)
        for name, value in (
            ("is_growth_drug_self_target", False),
            ("get_baby_id_list", [CHILD]),
            ("get_child_next_stage_name", "下一阶段"),
            ("get_child_growth_stage_total_day", 60),
        ):
            self.enterContext(
                mock.patch.object(pregnancy_handle, name, return_value=value)
            )

    def grow(self, amount: float) -> mock.MagicMock:
        """
        打桩 get_child_growth_acceleration_amount 使其返回指定成长加速天数。
        Keyword arguments:
        amount -- float，模拟返回的本次成长加速天数
        Return arguments:
        mock.MagicMock -- 替换后的模拟对象
        """
        return self.enterContext(
            mock.patch.object(
                pregnancy_handle,
                "get_child_growth_acceleration_amount",
                return_value=amount,
            )
        )

    def added_text(self, name: str, add_day: float, total: int) -> str:
        """
        构造 39 号药物生效后的预期提示正文，并用 pregnancy_panel.get_date_text 核对日期格式。
        Keyword arguments:
        name -- str，成长目标角色名称
        add_day -- float，本次加速天数
        total -- int，取整后的累计加速天数
        Return arguments:
        str -- 预期的提示正文文本
        """
        predict = game_time.get_predict_date(60 - total, START)
        return _("本次加速{0}，累计加速{1}，{2}预计将在{3}成长为{4}\n").format(
            game_time.get_duration_text(add_day),
            game_time.get_duration_text(total),
            name,
            pregnancy_panel.get_date_text(predict),
            "下一阶段",
        )

    def test_selected_baby_grows(self) -> None:
        """验证 39 号药物对选中婴儿累加 growth_acceleration_days、输出成长阶段日期并重置 gift_child_id。"""
        amount = self.grow(6.0)
        self.use(39, self.added_text(CHILD_NAME, 6.0, 10))
        amount.assert_called_once_with(CHILD)
        self.assertEqual(pregnancy.of(CHILD).growth_acceleration_days, 10.0)
        self.assertEqual(activity.behavior(0).gift_child_id, -1)

    def test_self_target_grows(self) -> None:
        """验证目标角色为自身成长目标时累加自身 growth_acceleration_days 且保留 gift_child_id。"""
        self.enterContext(
            mock.patch.object(
                pregnancy_handle,
                "is_growth_drug_self_target",
                return_value=True,
            )
        )
        pregnancy.update(TARGET, growth_acceleration_days=4.0, born_time=START)
        amount = self.grow(6.0)
        self.use(39, self.added_text(NAME, 6.0, 10))
        amount.assert_called_once_with(TARGET)
        self.assertEqual(pregnancy.of(TARGET).growth_acceleration_days, 10.0)
        self.assertEqual(activity.behavior(0).gift_child_id, CHILD)

    def test_missing_baby_has_no_effect(self) -> None:
        """验证选中婴儿不在婴儿列表时跳过加速量计算、保持数值不变并重置 gift_child_id。"""
        self.enterContext(
            mock.patch.object(
                pregnancy_handle, "get_baby_id_list", return_value=[]
            )
        )
        amount = self.grow(6.0)
        self.use(39, _("选中的婴儿已经不在婴儿期，药物没有产生效果\n"))
        amount.assert_not_called()
        self.assertEqual(pregnancy.of(CHILD).growth_acceleration_days, 4.0)
        self.assertEqual(activity.behavior(0).gift_child_id, -1)

    def test_capped_growth_has_no_effect(self) -> None:
        """验证成长加速量为 0 时保持婴儿 growth_acceleration_days 不变并输出无效果提示。"""
        self.grow(0)
        self.use(
            39,
            _("{0}已经快要成长为{1}了，药物没有产生效果\n").format(
                CHILD_NAME, "下一阶段"
            ),
        )
        self.assertEqual(pregnancy.of(CHILD).growth_acceleration_days, 4.0)


class GiftSettlementTest(DrugCase):
    """送礼行为结算经 handle_give_gift_add_adjust 调用药物服务的测试。"""

    def test_drug_gift_calls_service(self) -> None:
        """验证送礼结算扣除 33 号道具、调用 handle_drug_use_effect、开启素质 27 并发出等待提示。"""
        activity.set_target(0, TARGET)
        activity.update_behavior(0, gift_id=GIFT_DRUG)
        inventory.set_item(0, GIFT_DRUG, 1)
        with mock.patch.object(
            drug_service,
            "handle_drug_use_effect",
            wraps=drug_service.handle_drug_use_effect,
        ) as handle:
            settle_default.handle_give_gift_add_adjust(
                0, 5, game_type.CharacterStatusChange(), game_time.now()
            )
        handle.assert_called_once_with(TARGET, GIFT_DRUG)
        self.assertEqual(abilities.talent(TARGET)[27], 1)
        self.assertEqual(inventory.items(0)[GIFT_DRUG], 0)
        text = "\n  " + _("{0}获得了【泌乳】\n").format(NAME)
        self.assertEqual(self.notices, [(text, True, "gold_enrod", False)])


class ImportBoundaryTest(FastTestCase):
    """礼物面板不含 handle_drug_use_effect 属性的边界测试。"""

    def test_gift_panel_lacks_drug_effect(self) -> None:
        """验证 gift_panel 模块不含 handle_drug_use_effect 属性。"""
        self.assertFalse(hasattr(gift_panel, "handle_drug_use_effect"))
