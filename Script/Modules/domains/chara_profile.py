"""
角色的称呼、个人设置与口上作者变量：角色键 profile.*
====================================================
本模块存他人对角色的称呼、角色对玩家的称呼、角色的个人设置与口上作者的 int 变量。
每项一个角色键，KEYS 列出全部角色键。DROPPED 列出读档时从旧存档角色对象上直接删掉的属性。
"""

from typing import Any

from Script.Modules.domains import chara_key
from Script.Modules.domains.chara_key import CharaKey

DROPPED = ("collection_character",)
""" 读档时从旧存档角色对象上删掉、不搬进角色键的属性。没有代码读写这些属性 """

nick_name: CharaKey[str] = CharaKey("profile.nick_name", "", "nick_name")
""" 他人对角色的称呼 """
nick_name_to_pl: CharaKey[str] = CharaKey(
    "profile.nick_name_to_pl", "", "nick_name_to_pl"
)
""" 角色对玩家的称呼 """
chara_setting: CharaKey[dict[int, int]] = CharaKey(
    "profile.chara_setting",
    {},
    "chara_setting",
    chara_key.int_table,
    chara_key.int_table_of,
)
""" 角色的个人设置 设置id:选项 """
author_flag: CharaKey[dict[int, int]] = CharaKey(
    "profile.author_flag",
    {},
    "author_flag.chara_int_flag_dict",
    chara_key.int_table,
    chara_key.int_table_of,
)
""" 口上作者的 int 变量 变量id:值，没有的变量为 0 """

KEYS: tuple[CharaKey[Any], ...] = (
    nick_name,
    nick_name_to_pl,
    chara_setting,
    author_flag,
)
""" 本模块的角色键 """


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时把版本 21 之前存档的角色对象上本模块的数据导入角色键
    导入后从对象上删掉 nick_name、nick_name_to_pl、chara_setting 与 author_flag 属性，也删掉 DROPPED 里的属性。
    author_flag 上的 str、float 与 bool 变量表没有对应的键，随 author_flag 一起删掉
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    chara_key.adopt(loaded_dict, KEYS, DROPPED)
