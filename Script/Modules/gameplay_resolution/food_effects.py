"""
进食效果计算（food_effects）
============================
本模块提供进食效果计算函数 calculate_food_effects，按角色当前目标食物与菜谱配置计算状态值与体力气力增量。
本模块不导入界面模块。
"""

import random

from Script.Config import game_config
from Script.Modules.domains import activity


def calculate_food_effects(
    character_id: int,
    add_time: int,
) -> tuple[int, int]:
    """
    按角色当前目标食物与菜谱配置，计算本次进食的状态值增量与体力气力增量。
    品质大于 8、小于 1 或目标食物为空时均按 1 计。
    品质系数取 (品质 / 2)²，手制时（maker 非空）再乘 1.5。
    菜谱命中配置时，难度取 max(difficulty, 1)。
    菜谱命中配置时，时间系数取 min(time / 60, 1.5)（time 为 999 时按 15 计）。
    目标食物为空或菜谱未命中配置时，难度与时间系数均取 1。
    函数依次调用两次 random.uniform(0.8, 1.2)，先后用于 state_add 与 hpmp_add 并经 int 取整。
    Keyword arguments:
    character_id -- int，角色编号
    add_time -- int，本次结算时间
    Return arguments:
    tuple[int, int] -- (state_add, hpmp_add)，依次为状态值增量与体力气力增量
    """
    now_food = activity.behavior(character_id).target_food
    food_quality = now_food.quality if now_food is not None else 1
    if food_quality > 8:
        food_quality = 1
    food_quality = max(food_quality, 1)
    quality_adjust = (food_quality / 2) ** 2
    cook_difficulty = 1
    if now_food is not None and now_food.recipe in game_config.config_recipes:
        cook_difficulty = max(
            game_config.config_recipes[now_food.recipe].difficulty, 1
        )
    add_time_adjust: float = 1

    if now_food is not None:
        if len(now_food.maker):
            quality_adjust *= 1.5
        food_recipe_id = now_food.recipe
        if food_recipe_id in game_config.config_recipes:
            food_recipe_data = game_config.config_recipes[food_recipe_id]
            food_recipe_time = food_recipe_data.time
            if food_recipe_time == 999:
                food_recipe_time = 15
            add_time_adjust = food_recipe_time / 60
            add_time_adjust = min(add_time_adjust, 1.5)

    state_add = int(
        add_time
        * quality_adjust
        * cook_difficulty
        * add_time_adjust
        * random.uniform(0.8, 1.2)
    )

    hpmp_add = int(
        25 * cook_difficulty * add_time_adjust * random.uniform(0.8, 1.2)
    )

    return state_add, hpmp_add
