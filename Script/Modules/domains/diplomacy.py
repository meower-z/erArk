"""
外交的全局键 base.diplomats
===========================
值是 {势力id的字符串: Post}，按第一次任命或定方针的先后排列。没有这个键时读空表，没有登记的势力读 VACANT。
写入整值替换这个键。新值与旧值相同时不写。
"""

from collections.abc import Mapping
from typing import Any, TypedDict, cast

from Script.Kernel import core
from Script.Modules.domains import recruit
from Script.Modules.gameplay_resolution import working

KEY = "base.diplomats"
""" 各势力的外交官与外交方针在全局数据里的键 """


class Post(TypedDict):
    """一个势力的外交"""

    diplomat: int
    """ 外交官的角色id，0 为空缺 """
    policy: int
    """ 外交方针id，0 为未定 """


VACANT: Post = {"diplomat": 0, "policy": 0}
""" 没有登记的势力 """

working.register(KEY, {})


def table(game: core.GameState | None = None) -> dict[int, Post]:
    """
    登记过的势力的外交。返回新建的 dict
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 势力id 到外交，按登记的顺序
    """
    stored = cast(Mapping[str, Post], working.get(None, KEY, game))
    return {int(c): cast(Post, dict(post)) for c, post in stored.items()}


def of(country_id: int) -> Post:
    """
    一个势力的外交，没有登记时为 VACANT
    Keyword arguments:
    country_id -- 势力id
    Return arguments:
    Post -- 新建的 dict
    """
    return table().get(country_id, {**VACANT})


def _put_table(new: Mapping[int, Post]) -> None:
    stored = {str(c): dict(post) for c, post in new.items()}
    if stored != working.get(None, KEY):
        working.put(None, KEY, cast(core.JSON, stored))


def set_post(country_id: int, **fields: int) -> None:
    """
    改一个势力外交的几项，其余项不变。没有登记的势力从 VACANT 起登记，排在最后
    Keyword arguments:
    country_id -- 势力id
    fields -- Post 的项名到新值
    """
    current = table()
    current[country_id] = cast(Post, {**of(country_id), **fields})
    _put_table(current)


def remap(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把外交官的旧id换成新id，空缺的不换
    Keyword arguments:
    old_to_new -- 旧id到新id，表里没有的id不变
    """
    current = table()
    for post in current.values():
        if post["diplomat"]:
            post["diplomat"] = old_to_new.get(
                post["diplomat"], post["diplomat"]
            )
    _put_table(current)


PICKLED = "diplomat_of_country"
""" 版本 11 之前的存档里，罗德岛对象上 {势力id: [外交官id, 外交方针id]} 的属性名 """


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED，是 dict 时写进当前缓冲区。
    每项不足两项的补 0，外交官由 recruit.chara_id 换成 int
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 版本 11 之前的存档里缺了或类型不符时为 1，否则为 0，计法同 save_handle.update_dict_with_default
    """
    raw = vars(loaded_dict["rhodes_island"]).pop(PICKLED, None)
    if type(raw) is not dict:
        return 1 if version < 11 else 0
    posts = {}
    for country_id, data in raw.items():
        items = list(data) + [0, 0]
        posts[country_id] = Post(
            diplomat=recruit.chara_id(items[0]), policy=items[1]
        )
    _put_table(posts)
    return 0
