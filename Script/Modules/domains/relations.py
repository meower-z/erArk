"""
角色的社会关系：角色键 social.*
===============================
本模块存每个角色的 trust、对其他角色的 favorability、助理id、作为助理的服务选项、父母、孩子、朋友、出生地与势力。
每项一个角色键，KEYS 列出全部角色键。
"""

from typing import Any

from Script.Modules.domains import chara_key
from Script.Modules.domains.chara_key import CharaKey

favorability: CharaKey[dict[int, int]] = CharaKey(
    "social.favorability",
    {},
    "favorability",
    chara_key.int_table,
    chara_key.int_table_of,
)
""" 好感度 角色id:好感度 """
trust: CharaKey[float] = CharaKey("social.trust", 0, "trust")
""" 信赖度 """
assistant_character_id: CharaKey[int] = CharaKey(
    "social.assistant_character_id", 0, "assistant_character_id"
)
""" 助理角色id """
assistant_services: CharaKey[dict[int, int]] = CharaKey(
    "social.assistant_services",
    {},
    "assistant_services",
    chara_key.int_table,
    chara_key.int_table_of,
)
""" 作为助理的服务 服务id:选项 """
father_id: CharaKey[int] = CharaKey(
    "social.father_id", -1, "relationship.father_id"
)
""" 父亲id """
mother_id: CharaKey[int] = CharaKey(
    "social.mother_id", -1, "relationship.mother_id"
)
""" 母亲id """
child_id_list: CharaKey[list[int]] = CharaKey(
    "social.child_id_list",
    [],
    "relationship.child_id_list",
    chara_key.sequence,
    chara_key.list_of,
)
""" 孩子id列表 """
firend_id_list: CharaKey[list[int]] = CharaKey(
    "social.firend_id_list",
    [],
    "relationship.firend_id_list",
    chara_key.sequence,
    chara_key.list_of,
)
""" 朋友id列表 """
birthplace: CharaKey[int] = CharaKey(
    "social.birthplace", 0, "relationship.birthplace"
)
""" 出生地 """
nation: CharaKey[int] = CharaKey("social.nation", 0, "relationship.nation")
""" 势力 """

KEYS: tuple[CharaKey[Any], ...] = (
    favorability,
    trust,
    assistant_character_id,
    assistant_services,
    father_id,
    mother_id,
    child_id_list,
    firend_id_list,
    birthplace,
    nation,
)
""" 本模块的角色键 """


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时把版本 21 之前存档的角色对象上本模块的数据导入角色键
    导入后从对象上删掉 favorability、trust、assistant_character_id、assistant_services 与 relationship 属性
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    chara_key.adopt(loaded_dict, KEYS)
