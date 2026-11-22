# -*- coding: UTF-8 -*-
"""
食堂货架的状态（base.dining_hall）
==================================
- 新的一天刷新食堂：每名干员三份预制食物，前一天的食物不留。
- 干员买食堂的食物：食物从货架进背包，成为行为的目标食物，货架作为空表留下。
- 卖空的货架留在原位，之后放上的同种食物回到这个货架。
- 读档：罗德岛对象带着旧的食堂货架时，食物写进 GameState，空货架也留下，属性从对象上删掉。拿出的食物属性与原来相同。
  kitchen.adopt_old_save 交回 0，因为这个属性在且是 dict。
"""

import uuid
from types import SimpleNamespace

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.domains import inventory, kitchen, roster
from Script.Modules.gameplay_resolution import intent, npc_starters, working
from Script.System.Cooking_System import cooking
from tests.fast.base import FastTestCase


def _food(name: str, recipe: int) -> game_type.Food:
    """
    一份测试用的食物，品质 3
    Keyword arguments:
    name -- 食物名
    recipe -- 食谱id
    Return arguments:
    Food -- 食物
    """
    food = game_type.Food()
    food.name = name
    food.recipe = recipe
    food.quality = 3
    return food


class DiningHallStateTest(FastTestCase):
    """食堂的刷新、购买、货架顺序与读档"""

    def setUp(self) -> None:
        """放进博士，再以 core.state() 为底开一个缓冲区，测试里对 GameState 的读写都记在里面"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))

    def test_new_day_restock(self) -> None:
        """有两名干员时，新的一天食堂有六份食物，都是预制食物，前一天的食物不留"""
        self.world.chara(1, "干员1")
        self.world.chara(2, "干员2")
        roster.set_active({1, 2})
        cooking.init_recipes()
        kitchen.stock("1", _food("昨天的", 1))
        cooking.init_food_shop_data(new_day_flag=True)
        foods = [
            f for shelf in kitchen.shelves().values() for f in shelf.values()
        ]
        self.assertEqual(len(foods), 6)
        self.assertEqual(
            {self.cache.recipe_data[f.recipe].type for f in foods}, {5}
        )

    def test_npc_buys_food(self) -> None:
        """干员买走食堂的食物：食物进背包并成为目标食物，货架作为空表留下"""
        self.world.chara(1, "干员1")
        food = _food("便当", 7)
        kitchen.stock("7", food)
        args: dict[str, core.JSON] = {"shop": -1, "recipe_id": "7"}
        args["food_uid"] = str(food.uid)
        data: intent.Intent = {"behavior_id": "buy", "minutes": 1, "args": args}
        npc_starters.buy_food(1, data)
        bag = inventory.foods(1)
        self.assertEqual(vars(bag[food.uid]), vars(food))
        target = self.cache.character_data[1].behavior.target_food
        self.assertEqual(vars(target), vars(bag[food.uid]))
        self.assertEqual(kitchen.shelves(), {"7": {}})

    def test_sold_out_shelf_keeps_place(self) -> None:
        """货架 7 卖空后仍排在货架 8 前面，再放上的食物回到货架 7"""
        first = _food("便当", 7)
        kitchen.stock("7", first)
        kitchen.stock("8", _food("面包", 8))
        kitchen.take("7", str(first.uid))
        kitchen.stock("7", _food("便当", 7))
        self.assertEqual(list(kitchen.shelves()), ["7", "8"])
        self.assertEqual(len(kitchen.shelves()["7"]), 1)

    def test_old_hall_moves_into_state(self) -> None:
        """
        旧存档的食堂货架写进 GameState，空货架也留下，属性从对象上删掉。拿出的食物属性与原来相同。
        属性在且是 dict，交回 0
        """
        food = _food("便当", 7)
        food.maker = "干员1"
        key = uuid.uuid4()
        food.uid = key
        island = SimpleNamespace(dining_hall_data={"7": {key: food}, "8": {}})
        missing = kitchen.adopt_old_save({"rhodes_island": island}, 0)
        self.assertEqual(missing, 0)
        self.assertEqual(vars(island), {})
        self.assertEqual(list(kitchen.shelves()), ["7", "8"])
        self.assertEqual(vars(kitchen.take("7", str(key))), vars(food))
