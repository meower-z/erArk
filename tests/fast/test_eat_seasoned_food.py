# -*- coding: UTF-8 -*-
"""
给交互对象吃特殊调味的食物：开始时的食用判定读的是选中的那份食物
================================================================
博士背包里有一份按食谱做的、不含酒、精液巧妙混合的饭，交互对象有精爱味觉（一定接受）。博士选「食用」这份饭：
选择不出错，定下的是食用；选择时博士自己的行为（target_food）不被改写。
"""

from collections.abc import Mapping
from unittest import mock

from Script.Config import game_config
from Script.Core import constant
from Script.System.Cooking_System import cooking
from Script.UI.Panel import food_bag_panel
from Script.Modules.tk_ui import player_pick
from Script.Modules.domains import inventory
from tests import kernel_data
from tests.fast.base import FastTestCase
from Script.UI.Moudle import view
from tests import chara_abilities as ca
from tests.chara_activity import aim
from Script.Modules.domains import activity, kitchen

NPC = 1
""" 交互对象 """
SEMEN_HIDDEN = 11
""" 特殊调味：精液_巧妙混合 """
SEMEN_TASTE = 31
""" 素质：精爱味觉 """


class EatSeasonedFoodTest(FastTestCase):
    """食用特殊调味的食物：判定读选中的食物，选择不改写行为"""

    def setUp(self) -> None:
        """
        博士背包里一份精液巧妙混合的饭，交互对象有精爱味觉
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.npc = self.world.chara(NPC, "干员")
        ca.talent(self.npc)[SEMEN_TASTE] = 1
        aim(self.player.cid, NPC)
        recipe_id = next(
            rid
            for rid, recipe in game_config.config_recipes.items()
            if rid != -1
            and game_config.config_recipes.get(rid) is not None
            and game_config.config_recipes[rid].alcohol == 0
        )
        self.food = cooking.create_food("0", recipe_id)
        self.food.special_seasoning = SEMEN_HIDDEN
        kernel_data.put(inventory.put_food, self.player.cid, self.food)
        view.now_panel_id = constant.Panel.IN_SCENE

    def test_eating_seasoned_food_picks_eat(self) -> None:
        """选择不出错，定下的是食用，选择时博士的 target_food 没被改写"""
        before = activity.behavior(self.player.cid).target_food
        panel = food_bag_panel.FoodGroupDraw.__new__(
            food_bag_panel.FoodGroupDraw
        )
        with (
            mock.patch("Script.Settle.default.base_chara_climix_common_settle"),
            self.assertRaises(player_pick.Chosen) as caught,
        ):
            panel.eat_food(self.food.uid)
        chosen = caught.exception.action.action_data
        assert isinstance(chosen, Mapping)
        self.assertEqual(chosen["behavior_id"], constant.Behavior.EAT)
        after = activity.behavior(self.player.cid).target_food
        self.assertEqual(
            (after.uid, kitchen.record(after)),
            (before.uid, kitchen.record(before)),
        )
