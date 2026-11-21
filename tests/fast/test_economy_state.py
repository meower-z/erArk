# -*- coding: UTF-8 -*-
"""
基地经济与贸易的状态（domains.economy 的全局键）
=================================================
- 交易：买入 120 个后，供需系数从 1 升两次到 1.0199，今日买卖总量为 120。
  再卖出 60 个，系数按总量 120 下调一次，今日买卖总量为 180。
- 每天的供需波动之后，除龙门币外每种资源的今日买卖总量为 0，供需系数不低于 0.1。
- 收入：同一步里的两笔医疗收入相加。换成效果后，今日收入只有一个交给规则的 Change。
- 货架：3 名已招募干员时，新的一天每家餐馆进 3 份本店食谱的食物，品质 3 到 7。
  地摊小贩进 3 份零食或饮料，品质 1 到 8。
  拿走的食物带着货架上的 uid、食谱、品质与食谱名，没有制作者。货架上不再有它，再拿时为 None。
  货架上食谱与食物的先后经过存档文件 "2" 的编码与解码不变。
- 交易员：名单是职位为交易员的干员，按已招募干员集合的遍历顺序排列。
  刷新岗位后，不是交易员的主交易员与不存在的角色改为空缺。
- 读档：罗德岛对象带着旧经济属性时，值写进 GameState，属性从对象上删掉。之后角色换id，主交易员跟着换。
  对象上没有这些属性时什么也不写。
- 自检 ISLAND-15（主交易员）、ISLAND-24（自动交易设置）与 ISLAND-32（已开放商店）对合法值不报，对违规值报。
"""

import json
import uuid

from Script.Config import game_config
from Script.Core import game_type
from Script.Design import basement
from Script.Kernel import core
from Script.Modules.domains import economy, warehouse, work
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import kernel_state, upgrade
from Script.System.Cooking_System import cooking
from Script.System.Medical_System import medical_core
from Script.Test.Static_Check.check_registry import get_all_checks
from Script.UI.Panel import resource_exchange_panel as trade
from tests.fast.base import FastTestCase


def _tradable() -> int:
    """
    一种可以买卖的资源
    Return arguments:
    int -- 资源id：不是 0 号与龙门币，有价格，可以买入
    """
    for rid, data in game_config.config_resouce.items():
        if rid not in (0, 1) and data.price > 0 and data.cant_buy == 0:
            return rid
    raise AssertionError("配置里没有可以买卖的资源")


class EconomyStateTest(FastTestCase):
    """交易、收入、货架、交易员、读档与自检"""

    def setUp(self) -> None:
        """博士一人。测试里对 GameState 的读写记在以当前状态为底的缓冲区里（working.based_on）"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        self.island = self.cache.rhodes_island

    def flagged(self, check_id: str) -> bool:
        """
        跑一项自检
        Keyword arguments:
        check_id -- 检查编号
        Return arguments:
        bool -- 这项检查报了问题时为 True
        """
        _name, run = get_all_checks()[check_id]
        return bool(run())

    def test_trade_moves_supply_and_counts(self) -> None:
        """
        买入 120 个：供需系数从 1 上调两次到 1.0199，今日总量 120。
        再卖出 60 个：系数按总量 120 下调一次，今日总量 180
        """
        rid = _tradable()
        warehouse.set(1, 10**9)
        self.island.warehouse_capacity = 10**6
        bought = trade.perform_trade(rid, 120, True)
        assert bought is not None
        self.assertEqual(bought["quantity"], 120)
        self.assertEqual(economy.supply_demand()[rid], 1.0199)
        self.assertEqual(economy.traded_today()[rid], 120)
        trade.perform_trade(rid, 60, False)
        expected = round(1.0199 - 0.01 * 1.0199 / (1 + 120 / 1000), 4)
        self.assertEqual(economy.supply_demand()[rid], expected)
        self.assertEqual(economy.traded_today()[rid], 180)

    def test_day_drift_resets_counts(self) -> None:
        """买入 50 个后跑每天的供需波动：除龙门币外每种资源的今日买卖总量为 0，供需系数都不低于 0.1"""
        rid = _tradable()
        warehouse.set(1, 10**9)
        self.island.warehouse_capacity = 10**6
        trade.perform_trade(rid, 50, True)
        trade.daily_supply_demand_fluctuation()
        others = set(game_config.config_resouce) - {1}
        self.assertEqual(economy.traded_today(), dict.fromkeys(others, 0))
        supply = economy.supply_demand()
        self.assertEqual(set(supply), others)
        self.assertGreaterEqual(min(supply.values()), 0.1)

    def test_income_of_one_step_adds_up(self) -> None:
        """同一步里两笔医疗收入 30 与 12：今日收入为 42，龙门币库存也为 42。换成效果后今日收入只有一个 Change"""
        with working.based_on(core.state()) as step:
            medical_core._apply_income_to_rhodes(self.island, 30)
            medical_core._apply_income_to_rhodes(self.island, 12)
            effects = step.effects()
        changes = [
            e for e in effects if getattr(e, "key", None) == economy.INCOME
        ]
        self.assertEqual(len(changes), 1)
        self.assertIsInstance(changes[0], core.Change)
        game = core.preview(core.state(), effects)
        self.assertEqual(economy.income(game), 42)
        self.assertEqual(warehouse.amount(1, game), 42)

    def restock(self) -> None:
        """载入菜谱，按 3 名已招募干员给新的一天进货"""
        cooking.init_recipes()
        self.cache.npc_id_got = {1, 2, 3}
        cooking.init_food_shop_data(new_day_flag=True)

    def test_new_day_restock(self) -> None:
        """每家餐馆进 3 份本店食谱的食物，品质 3 到 7。地摊小贩进 3 份零食或饮料，品质 1 到 8"""
        self.restock()
        for rid in game_config.config_restaurant:
            foods = economy.shelf(rid)
            qualities = [q for row in foods.values() for q in row.values()]
            self.assertEqual(len(qualities), 3, rid)
            self.assertTrue(all(3 <= q <= 7 for q in qualities), rid)
            for recipe in foods:
                self.assertEqual(
                    game_config.config_recipes[int(recipe)].restaurant, rid
                )
        stall = economy.shelf(economy.STALL)
        self.assertEqual(sum(len(row) for row in stall.values()), 3)
        for recipe, row in stall.items():
            self.assertIn(game_config.config_recipes[int(recipe)].type, (1, 2))
            self.assertTrue(all(1 <= q <= 8 for q in row.values()))

    def test_bought_food_leaves_shelf(self) -> None:
        """拿走的食物带着 uid、食谱、品质与食谱名，没有制作者。货架上不再有它，再拿时为 None"""
        self.restock()
        rid = next(iter(game_config.config_restaurant))
        recipe, row = next(iter(economy.shelf(rid).items()))
        uid, quality = next(iter(row.items()))
        food = economy.take(rid, recipe, uid)
        assert food is not None
        self.assertEqual(
            (food.uid, food.recipe, food.quality, food.maker),
            (uuid.UUID(uid), int(recipe), quality, ""),
        )
        self.assertEqual(food.name, self.cache.recipe_data[int(recipe)].name)
        self.assertNotIn(uid, economy.shelf(rid)[recipe])
        self.assertIsNone(economy.take(rid, recipe, uid))

    def test_shelf_order_survives_save_file(self) -> None:
        """进货后的货架写进存档文件 "2" 再读回，各商店里食谱与食物的先后不变"""
        with working.based_on(core.state()) as stocked:
            self.restock()
            game = core.preview(core.state(), stocked.effects())
        text = json.dumps(kernel_state.encode(game, "t"), ensure_ascii=False)
        loaded = kernel_state.decode(json.loads(text), True)
        shops: list[int | str] = [*game_config.config_restaurant, economy.STALL]
        for shop in shops:
            before = economy.shelf(shop, game)
            after = economy.shelf(shop, loaded)
            self.assertEqual(
                [(recipe, list(row.items())) for recipe, row in before.items()],
                [(recipe, list(row.items())) for recipe, row in after.items()],
            )

    def test_traders_follow_work(self) -> None:
        """干员甲是交易员，干员乙不是。刷新岗位后交易员名单是 [甲]，乙与不存在的角色 9999 的主交易员位置改为空缺"""
        self.world.chara(1, "干员甲").work.work_type = economy.TRADER_WORK
        self.world.chara(2, "干员乙")
        self.cache.npc_id_got = {1, 2}
        economy.set_main_trader("甲类", 1)
        economy.set_main_trader("乙类", 2)
        economy.set_main_trader("丙类", 9999)
        basement.update_work_people()
        self.assertEqual(economy.trade_operator_ids(), [1])
        self.assertEqual(
            economy.main_traders(), {"甲类": 1, "乙类": 0, "丙类": 0}
        )

    def test_trader_order_follows_recruits(self) -> None:
        """已招募干员是 1 到 39 与 1050，其中 3 与 1050 是交易员：交易员名单按已招募干员集合的遍历顺序排列"""
        self.cache.npc_id_got = {*range(1, 40), 1050}
        work.set_rosters({economy.TRADER_WORK: [1050, 3]})
        expected = [cid for cid in self.cache.npc_id_got if cid in (3, 1050)]
        self.assertEqual(economy.trade_operator_ids(), expected)

    def old_island(self) -> game_type.Rhodes_Island:
        """
        带着九个旧经济属性的罗德岛对象，餐馆 5 与地摊小贩的货架上各有一份食物
        Return arguments:
        Rhodes_Island -- 罗德岛对象
        """
        cooking.init_recipes()
        recipe = next(iter(self.cache.recipe_data))
        made = cooking.create_food("", recipe, 6, "")
        sold = cooking.create_food("", recipe, 2, "")
        island = game_type.Rhodes_Island()
        vars(island).update(
            all_income=88,
            shop_open_list=["店甲", "店乙"],
            restaurant_data={5: {str(recipe): {made.uid: made}}},
            stall_vendor_data={0: {str(recipe): {sold.uid: sold}}},
            supply_demand_dict={3: 1.25, 4: 1},
            today_trade_resource_count={3: 70},
            trade_operator_ids_list=[7],
            resource_type_main_trader={"甲类": 7, "乙类": 0},
            resource_type_auto_trade_setting={
                3: {"buy_on": True, "buy_stock": 40}
            },
        )
        return island

    def test_old_island_moves_into_state(self) -> None:
        """adopt_economy 把旧经济属性的值写进 GameState，并从对象上删掉这些属性。之后角色 7 换成 70，主交易员跟着换"""
        island = self.old_island()
        ((recipe, row),) = vars(island)["restaurant_data"][5].items()
        ((uid, _food),) = row.items()
        upgrade.adopt_economy({"rhodes_island": island})
        self.assertEqual(economy.income(), 88)
        self.assertEqual(economy.shops_open(), ("店甲", "店乙"))
        self.assertEqual(economy.shelf(5), {recipe: {str(uid): 6}})
        self.assertEqual(
            [
                list(row.values())
                for row in economy.shelf(economy.STALL).values()
            ],
            [[2]],
        )
        self.assertEqual(economy.supply_demand(), {3: 1.25, 4: 1})
        self.assertEqual(economy.traded_today(), {3: 70})
        self.assertEqual(economy.main_traders(), {"甲类": 7, "乙类": 0})
        self.assertEqual(
            economy.auto_trade(3),
            {
                **dict.fromkeys(economy.AUTO_TRADE_KEYS, 0),
                "buy_on": True,
                "buy_stock": 40,
            },
        )
        self.assertEqual(economy.auto_trade(4), economy.DEFAULT_AUTO_TRADE)
        self.assertEqual(set(upgrade.V4_ECONOMY) & set(vars(island)), set())
        economy.remap_traders({7: 70})
        self.assertEqual(economy.main_trader("甲类"), 70)

    def test_current_island_writes_nothing(self) -> None:
        """新建的罗德岛对象没有旧经济属性，adopt_economy 什么也不写"""
        with working.based_on(core.state()) as load:
            upgrade.adopt_economy({"rhodes_island": game_type.Rhodes_Island()})
            self.assertEqual(load.effects(), ())

    def test_island_checks(self) -> None:
        """ISLAND-15、ISLAND-24、ISLAND-32 各试一个合法值与一个违规值：合法值不报，违规值报"""
        self.world.chara(1, "干员甲").work.work_type = economy.TRADER_WORK
        economy.set_main_trader("甲类", 1)
        self.assertFalse(self.flagged("ISLAND-15"))
        economy.set_main_trader("甲类", 9999)
        self.assertTrue(self.flagged("ISLAND-15"))
        rid = _tradable()
        economy.set_auto_trade(rid, economy.DEFAULT_AUTO_TRADE)
        self.assertFalse(self.flagged("ISLAND-24"))
        economy.set_auto_trade(
            rid, {**economy.DEFAULT_AUTO_TRADE, "buy_price_percent": 400}
        )
        self.assertTrue(self.flagged("ISLAND-24"))
        self.assertFalse(self.flagged("ISLAND-32"))
        economy.open_shop("不存在的店")
        self.assertTrue(self.flagged("ISLAND-32"))
