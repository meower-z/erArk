"""
图书馆的全局键 base.book_holders 与 base.book_recommend
=======================================================
base.book_holders 是 {书id的字符串: 借书人}，借书人 -1 为没有借出，0 为博士，其余为角色id。没有这个键时读空表。
读出的借阅表先按存下的顺序列出存着的书，再按书籍配置的顺序列出配置里有、表里没存的书，记作没有借出。
所以新游戏不用写这个键，读档时也不用补上配置里新加的书。
base.book_recommend 是博士推荐阅读的书籍类型id，从小到大排列。没有这个键时读空表。
写入整值替换键。新值与旧值相同时不写。借阅表写入时连同补上的书一起写下。
"""

from collections.abc import Iterable, Mapping
from typing import Any, cast

from Script.Config import game_config
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working

HOLDERS = "base.book_holders"
""" 借阅表在全局数据里的键 """
RECOMMEND = "base.book_recommend"
""" 推荐阅读的书籍类型在全局数据里的键 """
FREE = -1
""" 借阅表里没有借出的书的借书人 """

working.register(HOLDERS, {})
working.register(RECOMMEND, ())


def holders(game: core.GameState | None = None) -> dict[int, int]:
    """
    借阅表。返回新建的 dict
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 书id 到借书人，存着的书按存下的顺序在前，配置里有、表里没存的书按配置的顺序在后，记作 FREE
    """
    stored = cast(Mapping[str, int], working.get(None, HOLDERS, game))
    out = {int(book): holder for book, holder in stored.items()}
    for book in game_config.config_book:
        out.setdefault(book, FREE)
    return out


def put_holders(new: Mapping[int, int]) -> None:
    """
    换掉借阅表
    Keyword arguments:
    new -- 书id 到借书人，按要存的顺序
    """
    stored = {str(book): holder for book, holder in new.items()}
    if stored != working.get(None, HOLDERS):
        working.put(None, HOLDERS, stored)


def set_holder(book_id: int, holder: int) -> None:
    """
    换一本书的借书人
    Keyword arguments:
    book_id -- 书id
    holder -- 借书人，FREE 为还回
    """
    current = holders()
    current[book_id] = holder
    put_holders(current)


def recommended(game: core.GameState | None = None) -> set[int]:
    """
    推荐阅读的书籍类型。返回新建的 set
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    set -- 书籍类型id
    """
    return set(cast(Iterable[int], working.get(None, RECOMMEND, game)))


def set_recommended(type_ids: Iterable[int]) -> None:
    """
    换掉推荐阅读的书籍类型
    Keyword arguments:
    type_ids -- 书籍类型id
    """
    new = tuple(sorted(set(type_ids)))
    if new != working.get(None, RECOMMEND):
        working.put(None, RECOMMEND, new)


def remap(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把借书人的旧id换成新id
    Keyword arguments:
    old_to_new -- 旧id到新id，表里没有的id不变
    """
    put_holders(
        {
            b: old_to_new.get(h, h) if h != FREE else h
            for b, h in holders().items()
        }
    )


PICKLED = {"book_borrow_dict": dict, "recommend_book_type_set": set}
""" 版本 11 之前的存档里，罗德岛对象上这两项的属性名与应有的类型。类型不是这一种的值不导入 """


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。从罗德岛对象上删掉 PICKLED 里的属性，把类型相符的值写进当前缓冲区
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 版本 11 之前的存档里缺了或类型不符的属性个数，计法同 save_handle.update_dict_with_default
    """
    attrs = vars(loaded_dict["rhodes_island"])
    found = {name: attrs.pop(name) for name in PICKLED if name in attrs}
    kept = {n: v for n, v in found.items() if type(v) is PICKLED[n]}
    if "book_borrow_dict" in kept:
        put_holders(kept["book_borrow_dict"])
    if "recommend_book_type_set" in kept:
        set_recommended(kept["recommend_book_type_set"])
    return len(PICKLED) - len(kept) if version < 11 else 0
