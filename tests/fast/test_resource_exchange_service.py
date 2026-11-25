"""
资源交易规则服务测试。
覆盖报价、数量、交易、列表、交易员、自动交易写入及无界面边界。
"""

from Script.Kernel import core
from Script.Modules.domains import economy, location, warehouse, work
from Script.Modules.gameplay_resolution import resource_exchange_service as svc
from Script.Modules.gameplay_resolution import trade_service, working
from tests import chara_abilities as ca
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

PLAIN = 11
""" 可购买普通材料资源 11 的测试编号常量。 """
LOCKED = 12
""" 不可购买资源 12 的测试编号常量。 """
SPECIALTY = 101
""" 国家 1 对应特产资源 101 的测试编号常量。 """
HOME = 1
""" 测试用特产所属国家编号 1。 """
MONEY = 1
""" 龙门币对应的资源编号 1。 """
BACKEND_RUN = """
from Script.Config import normal_config
from Script.Kernel import core
from Script.Modules.domains import economy, identity, warehouse, work
from Script.Modules.gameplay_resolution import resource_exchange_service as svc
from Script.Modules.gameplay_resolution import working
from tests import chara_abilities, kernel_data
from tests.world import start_time
kernel_data.reset_clock(start_time(), {})
for cid in (0, 1, 2):
    kernel_data.put(identity.put, identity.Identity(cid, name="c" + str(cid), sex=1))
    chara_abilities.zero_tables(cid)
def scenario():
    out = {}
    with working.based_on(core.state()):
        warehouse.start({})
        warehouse.set_extra_modules(5)
        work.set_rosters({economy.TRADER_WORK: [1, 2, 9]})
        chara_abilities.ability(2)[40] = 7
        warehouse.set(1, 10 ** 7)
        warehouse.set(11, 40)
        svc.toggle_main_trader("材料", 1)
        quote = svc.quote(11, -40)
        out["quote"] = [quote.confirm, quote.main_name, list(quote.sub_names),
            quote.total == quote.sell_price * 40]
        out["steps"] = [svc.step(11, 0, 99999) + 40 == warehouse.capacity(),
            svc.step(11, 0, -99999), svc.max_sell(11), svc.max_buy(12, 3)]
        out["deal"] = [svc.trade(11, 0), svc.trade(11, -15).done,
            warehouse.amount(11)]
        out["listed"] = [item.resource_id for item in svc.listings("材料")]
        out["roster"] = [svc.roster().count, list(svc.roster().others),
            svc.candidates()]
        svc.toggle_auto_trade(11, "sell_on")
        svc.adjust_auto_trade_value(11, "sell_price_percent", 999, True)
        svc.adjust_auto_trade_value(11, "buy_stock", -5)
        svc.clear_main_trader("材料")
        out["auto"] = [economy.auto_trade(11), economy.main_trader("材料")]
    return out
payload["default"] = scenario()
normal_config.config_normal.language = "en_US"
normal_config.ai_setting.ai_chat_translator_setting = 2
normal_config.ai_setting.ai_chat_setting[1] = 1
payload["switched"] = scenario()
"""
""" 在拦截界面与结算模块的子进程中调用服务公开接口的测试脚本。 """


class ExchangeCase(FastTestCase):
    """资源交易服务测试基类，准备测试角色、仓储扩展模块与临时写缓冲。"""

    def setUp(self) -> None:
        """初始化角色 0 至 2、开启状态写缓冲并设置 5 个仓储扩展模块。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "主交易员")
        self.world.chara(2, "副交易员")
        self.enterContext(working.based_on(core.state()))
        warehouse.set_extra_modules(5)

    def hire(self) -> None:
        """配置 1、2 号干员为交易员，任命 1 号为材料主交易员并设话术。"""
        work.set_rosters({economy.TRADER_WORK: [1, 2]})
        economy.set_main_trader("材料", 1)
        ca.ability(1)[40] = 10
        ca.ability(2)[40] = 20

    def home(self, country: int) -> None:
        """将罗德岛当前所在国家写入临时写缓冲。"""
        working.put(None, location.KEY, {"country": country, "move": None})


class QuoteTest(ExchangeCase):
    """报价快照的买卖确认条件、零数量与交易员加成测试。"""

    def test_buy_needs_money_and_a_buyable_resource(self) -> None:
        """验证买入确认需资金充足且资源未禁买，并核对总价与余额。"""
        price = trade_service.get_resouce_price(PLAIN, True)[0]
        warehouse.set(MONEY, price * 5)
        quote = svc.quote(PLAIN, 5)
        self.assertTrue(quote.confirm)
        self.assertEqual(quote.total, price * 5)
        self.assertEqual(quote.money_left, 0)
        warehouse.set(MONEY, price * 5 - 1)
        self.assertFalse(svc.quote(PLAIN, 5).confirm)
        warehouse.set(MONEY, 10**9)
        locked = svc.quote(LOCKED, 1)
        self.assertTrue(locked.cant_buy)
        self.assertFalse(locked.confirm)

    def test_sell_needs_stock_and_a_home_specialty(self) -> None:
        """验证卖出确认需库存充足，且特产需在所属国家才允许卖出。"""
        warehouse.set(MONEY, 100)
        warehouse.set(PLAIN, 3)
        price = trade_service.get_resouce_price(PLAIN, False)[0]
        quote = svc.quote(PLAIN, -3)
        self.assertTrue(quote.confirm)
        self.assertEqual(quote.total, price * 3)
        self.assertEqual(quote.money_left, 100 + price * 3)
        self.assertFalse(svc.quote(PLAIN, -4).confirm)
        warehouse.set(SPECIALTY, 5)
        self.assertFalse(svc.quote(SPECIALTY, -5).confirm)
        self.home(HOME)
        self.assertTrue(svc.quote(SPECIALTY, -5).confirm)

    def test_zero_quantity_never_confirms(self) -> None:
        """验证交易数量为 0 时确认标志为假、总价为 0 且余额不变。"""
        warehouse.set(MONEY, 700)
        quote = svc.quote(PLAIN, 0)
        self.assertEqual((quote.confirm, quote.total), (False, 0))
        self.assertEqual(quote.money_left, 700)

    def test_traders_and_bonuses(self) -> None:
        """验证空缺及有主副交易员时的名单、加成计算与缺失角色跳过。"""
        empty = svc.quote(PLAIN, 0)
        self.assertEqual((empty.main_id, empty.main_name), (0, None))
        self.assertEqual((empty.main_bonus, empty.sub_names), (0.0, ()))
        self.hire()
        work.set_rosters({economy.TRADER_WORK: [1, 2, 9]})
        quote = svc.quote(PLAIN, 0)
        self.assertEqual((quote.main_id, quote.main_name), (1, "主交易员"))
        self.assertEqual(quote.sub_names, ("副交易员",))
        self.assertAlmostEqual(quote.main_bonus, 0.05)
        self.assertAlmostEqual(quote.sub_bonus, 0.02)


class QuantityTest(ExchangeCase):
    """交易数量步进夹紧、最大买入与最大卖出计算测试。"""

    def test_step_stays_between_stock_and_free_room(self) -> None:
        """验证 step 将数量夹紧在负库存与剩余仓容之间，并核对最大卖出。"""
        warehouse.set(PLAIN, 30)
        room = warehouse.capacity() - 30
        self.assertEqual(svc.step(PLAIN, 3, 2), 5)
        self.assertEqual(svc.step(PLAIN, 0, 10**6), room)
        self.assertEqual(svc.step(PLAIN, 0, -1000), -30)
        self.assertEqual(svc.max_sell(PLAIN), -30)

    def test_max_buy_by_money_room_and_lock(self) -> None:
        """验证 max_buy 受资金、剩余仓容与禁买标志约束。"""
        price = trade_service.get_resouce_price(PLAIN, True)[0]
        warehouse.set(MONEY, price * 7 + 1)
        self.assertEqual(svc.max_buy(PLAIN, -4), 7)
        warehouse.set(MONEY, 10**12)
        self.assertEqual(svc.max_buy(PLAIN, 0), warehouse.capacity())
        warehouse.set(MONEY, 0)
        self.assertEqual(svc.max_buy(PLAIN, 9), 0)
        self.assertEqual(svc.max_buy(LOCKED, 9), 9)


class TradeTest(ExchangeCase):
    """交易执行成交提示、部分成交与失败保态测试。"""

    def test_trade_reports_the_deal(self) -> None:
        """验证零数量返回 None、部分买入带实际成交提示及全额卖出结果。"""
        self.assertIsNone(svc.trade(PLAIN, 0))
        price = trade_service.get_resouce_price(PLAIN, True)[0]
        warehouse.set(MONEY, price * 4)
        deal = svc.trade(PLAIN, 10)
        assert deal is not None
        self.assertTrue(deal.done)
        self.assertEqual(warehouse.amount(PLAIN), 4)
        self.assertIn(f"(-{price * 4})", deal.text)
        self.assertIn("(+4)\n(本次实际成交4单位)\n", deal.text)
        sold = svc.trade(PLAIN, -4)
        assert sold is not None
        self.assertTrue(sold.done)
        self.assertNotIn("本次实际成交", sold.text)
        self.assertTrue(sold.text.endswith("(-4)\n"))

    def test_trade_failure_keeps_state(self) -> None:
        """验证卖出失败时返回失败提示、成交标志为假且资金不变。"""
        warehouse.set(MONEY, 50)
        deal = svc.trade(PLAIN, -3)
        assert deal is not None
        self.assertFalse(deal.done)
        self.assertEqual(
            deal.text, "\n交易未能执行，请检查资金、仓库或库存限制。\n"
        )
        self.assertEqual(warehouse.amount(MONEY), 50)


class ListingTest(ExchangeCase):
    """资源选择列表价格与特产可见性过滤测试。"""

    def test_listing_prices_and_specialty_filter(self) -> None:
        """验证禁买资源无买价及零库存非本地特产隐藏、有库存或在产地显示。"""
        items = {item.resource_id: item for item in svc.listings("材料")}
        self.assertIn(PLAIN, items)
        plain, locked = items[PLAIN], items[LOCKED]
        buy = trade_service.get_resouce_price(PLAIN, True)
        self.assertEqual(plain.buy, buy)
        self.assertIsNone(locked.buy)
        self.assertEqual(
            locked.sell, trade_service.get_resouce_price(LOCKED, False)
        )
        specialty = svc.listings("特产")
        self.assertNotIn(SPECIALTY, [item.resource_id for item in specialty])
        warehouse.set(SPECIALTY, 2)
        listed = {item.resource_id: item for item in svc.listings("特产")}
        self.assertEqual(listed[SPECIALTY].stock, 2)
        warehouse.set(SPECIALTY, 0)
        self.home(HOME)
        self.assertIn(SPECIALTY, [i.resource_id for i in svc.listings("特产")])


class RosterTest(ExchangeCase):
    """交易员名册汇总、候选列表与主交易员切换清空测试。"""

    def test_rows_and_other_traders(self) -> None:
        """验证名册跳过无与货币、标出空缺与副交易员话术并跳过缺失角色。"""
        self.hire()
        work.set_rosters({economy.TRADER_WORK: [1, 2, 9]})
        roster = svc.roster()
        rows = dict(roster.rows)
        self.assertEqual(roster.count, 3)
        self.assertNotIn("无", rows)
        self.assertNotIn("货币", rows)
        self.assertEqual(rows["材料"], "主交易员")
        self.assertEqual(rows["药剂"], "空缺")
        self.assertEqual(roster.others, (("副交易员", 20),))
        self.assertEqual(svc.candidates(), [1, 2, 9])

    def test_main_trader_toggles_and_clears(self) -> None:
        """验证主交易员忽略非交易员、支持任命撤销清空，候选排除角色 0。"""
        work.set_rosters({economy.TRADER_WORK: [1]})
        svc.toggle_main_trader("药剂", 2)
        self.assertEqual(economy.main_trader("药剂"), 0)
        svc.toggle_main_trader("药剂", 1)
        self.assertEqual(economy.main_trader("药剂"), 1)
        svc.toggle_main_trader("药剂", 1)
        self.assertEqual(economy.main_trader("药剂"), 0)
        economy.set_main_trader("香水", 1)
        svc.clear_main_trader("香水")
        self.assertEqual(economy.main_trader("香水"), 0)
        work.set_rosters({economy.TRADER_WORK: [0, 1]})
        self.assertEqual(svc.candidates(), [1])


class AutoTradeTest(ExchangeCase):
    """自动交易开关翻转与数值边界调整测试。"""

    def test_toggle_and_bounded_values(self) -> None:
        """验证自动交易开关翻转、库存与百分比上下限夹紧及重置置零。"""
        svc.toggle_auto_trade(PLAIN, "buy_on")
        self.assertIs(economy.auto_trade(PLAIN)["buy_on"], True)
        svc.toggle_auto_trade(PLAIN, "buy_on")
        self.assertIs(economy.auto_trade(PLAIN)["buy_on"], False)
        cases = (
            ("buy_stock", -50, False, False, 0),
            ("buy_stock", 10**6, False, False, warehouse.capacity()),
            ("buy_price_percent", 250, True, False, 300),
            ("buy_price_percent", -400, True, False, 0),
            ("sell_price_percent", 5, True, False, 105),
            ("sell_stock", 77, False, True, 0),
        )
        for key, delta, percent, reset, value in cases:
            with self.subTest(key=key, delta=delta, reset=reset):
                svc.adjust_auto_trade_value(PLAIN, key, delta, percent, reset)
                self.assertEqual(economy.auto_trade(PLAIN)[key], value)


class BackendIsolationTest(FastTestCase):
    """资源交易服务的无界面与无结算导入边界独立子进程测试。"""

    def test_service_runs_without_ui_or_settle(self) -> None:
        """验证默认与切换设置下服务全部公开接口结果一致且无受限导入。"""
        run = run_ui_free(BACKEND_RUN, boot=True)
        self.assertEqual((run.loaded, run.attempted), ([], []))
        out: dict = run.payload
        self.assertEqual(out["switched"], out["default"])
        default = out["default"]
        self.assertEqual(default["quote"], [True, "c1", ["c2"], True])
        self.assertEqual(default["steps"], [True, -40, -40, 3])
        self.assertEqual(default["deal"], [None, True, 25])
        self.assertIn(11, default["listed"])
        self.assertEqual(default["roster"], [3, [["c2", 7]], [1, 2, 9]])
        auto, main = default["auto"]
        self.assertEqual(auto["sell_on"], True)
        self.assertEqual(auto["sell_price_percent"], 300)
        self.assertEqual((auto["buy_stock"], main), (0, 0))
