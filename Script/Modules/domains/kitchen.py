"""
食堂货架的全局键 base.dining_hall
=================================
值是 {食谱id的字符串: {食物uid的字符串: 食物记录}}，食物记录见 record。没有这个键时读空表。
货架与食物按放进的顺序排列。卖空的货架作为空表留在原位，因为干员随机挑食物时，货架的顺序决定挑到哪一份。
写入整值替换这个键。读出的食物是按记录新建的 Food 对象，改它不改货架。
"""

from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

KEY = "base.dining_hall"
""" 食堂货架在全局数据里的键 """

type Shelves = Mapping[str, Mapping[str, Mapping[str, core.JSON]]]
""" 存下的货架：食谱id的字符串到食物uid的字符串到食物记录 """

working.register(KEY, {})


def _stored(game: core.GameState | None = None) -> Shelves:
    return cast(Shelves, working.get(None, KEY, game))


def record(food: game_type.Food) -> dict[str, core.JSON]:
    """
    食物记录：Food 对象除 uid 外的全部属性，原样抄下
    Keyword arguments:
    food -- 食物
    Return arguments:
    dict -- 属性名到值
    """
    return {name: v for name, v in vars(food).items() if name != "uid"}


def food(uid: str, stored: Mapping[str, core.JSON]) -> game_type.Food:
    """
    按食物记录新建 Food 对象
    Keyword arguments:
    uid -- 食物uid的字符串
    stored -- 食物记录
    Return arguments:
    game_type.Food -- 属性与记录相同的食物，uid 为 UUID(uid)
    """
    # 不调 Food()，因为它会取一个用不上的 uuid4
    made = object.__new__(game_type.Food)
    vars(made).update(stored)
    made.uid = UUID(uid)
    return made


def shelves(
    game: core.GameState | None = None,
) -> dict[str, dict[UUID, game_type.Food]]:
    """
    食堂的全部货架
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 食谱id的字符串到 {食物uid: Food}，按放进的顺序，Food 都是新建的对象
    """
    return {
        recipe: {UUID(uid): food(uid, kept) for uid, kept in foods.items()}
        for recipe, foods in _stored(game).items()
    }


def shelf(
    recipe: str, game: core.GameState | None = None
) -> dict[UUID, game_type.Food]:
    """
    一种食谱的货架
    Keyword arguments:
    recipe -- 食谱id的字符串
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 食物uid到按记录新建的 Food，按放进的顺序，没有这个货架时为空表
    """
    foods = _stored(game).get(recipe, {})
    return {UUID(uid): food(uid, kept) for uid, kept in foods.items()}


def find(
    recipe: str, uid: str, game: core.GameState | None = None
) -> game_type.Food | None:
    """
    一种食谱的货架上的一份食物
    Keyword arguments:
    recipe -- 食谱id的字符串
    uid -- 食物uid的字符串
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    game_type.Food | None -- 按记录新建的食物，货架上没有这份食物时为 None
    """
    kept = _stored(game).get(recipe, {}).get(uid)
    return None if kept is None else food(uid, kept)


def stock(recipe: str, new_food: game_type.Food) -> None:
    """
    把食物的记录放上 recipe 的货架。没有这个货架时新货架排在最后
    Keyword arguments:
    recipe -- 食谱id的字符串
    new_food -- 食物
    """
    current = _stored()
    shelf = {**current.get(recipe, {}), str(new_food.uid): record(new_food)}
    working.put(None, KEY, cast(core.JSON, {**current, recipe: shelf}))


def take(recipe: str, uid: str) -> game_type.Food:
    """
    从货架上拿走一份食物。货架卖空时作为空表留在原位
    Keyword arguments:
    recipe -- 食谱id的字符串
    uid -- 食物uid的字符串
    Return arguments:
    game_type.Food -- 拿走的食物，按记录新建
    """
    current = _stored()
    shelf = dict(current[recipe])
    kept = shelf.pop(uid)
    working.put(None, KEY, cast(core.JSON, {**current, recipe: shelf}))
    return food(uid, kept)


def keep_shelf(recipe: str) -> None:
    """
    没有这种食谱的货架时，在最后放一个空货架
    Keyword arguments:
    recipe -- 食谱id的字符串
    """
    current = _stored()
    if recipe not in current:
        working.put(None, KEY, cast(core.JSON, {**current, recipe: {}}))


def clear() -> None:
    """撤掉全部货架，空货架也撤掉"""
    if _stored():
        working.put(None, KEY, {})


PICKLED = "dining_hall_data"
""" 版本 8 之前的存档里，罗德岛对象上的食堂货架属性名 """


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED 属性。它是不空的 dict 时，把其中的食物记录写进当前缓冲区的 base.dining_hall
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 版本 8 之前的存档里缺了这个属性或它不是 dict 时为 1，计法同 save_handle.update_dict_with_default，其余为 0
    """
    attrs = vars(loaded_dict["rhodes_island"])
    shelves = attrs.pop(PICKLED, None)
    if type(shelves) is not dict:
        return 1 if version < 8 else 0
    if shelves:
        hall = {
            str(recipe): {str(uid): record(f) for uid, f in foods.items()}
            for recipe, foods in shelves.items()
        }
        working.put(None, KEY, cast(core.JSON, hall))
    return 0
