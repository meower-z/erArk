# -*- coding: UTF-8 -*-
"""
面板定下玩家的行动时缓存不变
============================
选择路径上的面板经 player_pick.choose 抛出 Chosen：行动的数据经得起 JSON 往返，
抛出前后游戏缓存逐字节相同（按 pickle 比较），只有面板id（界面状态）可以变。
要改的数据（食物进背包、脱衣、睡觉时间）留到行动开始时由 panel_starters 写入。
"""

import json
import pickle
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

from Script.Config import game_config
from Script.Core import constant, game_type
from Script.Modules.tk_ui import player_pick
from Script.System.Cooking_System import food_bag_panel
from Script.UI.Panel import (
    check_locker_panel,
    cloth_panel,
    food_shop_panel,
    normal_panel,
    read_book_panel,
)
from tests.fast.base import FastTestCase


def pickled(cache: Any) -> dict[str, bytes]:
    """
    缓存的每个属性（character_data 拆成每个角色）的 pickle
    Keyword arguments:
    cache -- 游戏缓存
    Return arguments:
    dict -- 属性名 -> pickle
    """
    out = {
        k: pickle.dumps(v)
        for k, v in vars(cache).items()
        if k != "character_data"
    }
    for cid, data in cache.character_data.items():
        out[f"character_data[{cid}]"] = pickle.dumps(data)
    return out


def _food(name: str) -> game_type.Food:
    """
    一份测试用的食物
    Keyword arguments:
    name -- 食物名
    Return arguments:
    Food -- 食物
    """
    food = game_type.Food()
    food.name = name
    return food


def _panel(**attrs: object) -> Any:
    """
    面板对象的替身：只带选择要读的属性
    Keyword arguments:
    attrs -- 属性
    Return arguments:
    Any -- 替身
    """
    return SimpleNamespace(**attrs)


class PanelPicksLeaveCache(FastTestCase):
    """每个面板的选择：抛出 Chosen，数据是 JSON，缓存不变"""

    def chosen(self, pick: Callable[[], object]) -> dict[str, Any]:
        """
        跑一次面板的选择
        Keyword arguments:
        pick -- 面板的选择
        Return arguments:
        dict -- 定下的行动：kind 与 JSON 往返后的 action_data
        """
        before = pickled(self.cache)
        with self.assertRaises(player_pick.Chosen) as raised:
            pick()
        act = raised.exception.action
        data = json.loads(json.dumps(act.action_data))
        now = pickled(self.cache)
        changed = sorted(
            k for k in before.keys() | now.keys() if before.get(k) != now.get(k)
        )
        self.assertEqual(changed, [], "选择里缓存不变")
        self.assertEqual(act.who, "0")
        return {"kind": act.action_id.split(".", 1)[1], **data}

    def test_each_panel_pick(self) -> None:
        """每个面板定下的行动：种类、行为、分钟与参数"""
        self.world.chara(0, "博士")
        self.world.chara(1, "干员")
        book_id = next(iter(game_config.config_book))
        shop_food = _food("shop")
        self.cache.rhodes_island.dining_hall_data["1"] = {
            shop_food.uid: shop_food
        }
        bag_food = _food("bag")
        self.cache.character_data[0].food_bag[bag_food.uid] = bag_food
        self.cache.character_data[0].target_character_id = 1
        cases: list[tuple[str, Callable[[], object], dict[str, Any]]] = [
            (
                "照顾孩子",
                lambda: normal_panel.Take_Care_Baby_Panel.settle_take_care(
                    _panel(target_chara_id=1), 0
                ),
                {"kind": "Behavior", "target": 1, "minutes": 30},
            ),
            (
                "读书",
                lambda: read_book_panel.Read_Book_Panel.read(_panel(), book_id),
                {"kind": "player_read_book", "args": {"book_id": book_id}},
            ),
            (
                "闻内裤",
                lambda: check_locker_panel.FindDraw.smell(_panel(npc_id=1)),
                {"behavior_id": constant.Behavior.SMELL_UNDERWEAR, "target": 1},
            ),
            (
                "买食物",
                lambda: food_shop_panel.SeeFoodListByFoodNameDraw.buy_food(
                    _panel(), "1", shop_food.uid
                ),
                {
                    "kind": "player_buy_food",
                    "args": {
                        "food_cid": "1",
                        "food_uid": str(shop_food.uid),
                        "restaurant": None,
                    },
                },
            ),
            (
                "吃背包里的食物",
                lambda: food_bag_panel.FoodGroupDraw.eat_food(
                    _panel(), bag_food.uid
                ),
                {"kind": "eat_food", "minutes": 5},
            ),
            (
                "脱衣",
                lambda: cloth_panel.SeeUndressButtonList.chose_button(
                    _panel(button_id=2)
                ),
                {"kind": "undress", "args": {"choice": 2}},
            ),
        ]
        for name, pick, expected in cases:
            with self.subTest(name):
                got = self.chosen(pick)
                self.assertEqual(
                    {k: got.get(k) for k in expected}, expected, got
                )
        self.assertIn(
            shop_food.uid, self.cache.rhodes_island.dining_hall_data["1"]
        )
