"""
角色的住处、工作与娱乐：角色键 life.*
=====================================
本模块存每个角色的宿舍、登记宿舍与办公室，工作类型、正在处理的门诊与手术病人、宿舍管理员的行动阶段与目标宿舍，
以及娱乐类型、借的书、还书概率、阅读进度与借书历史。每项一个角色键，KEYS 列出全部角色键。
PATHS 列出存场景路径的三个键。WORK 列出来自旧存档角色对象 work 的五个键。
ENTERTAINMENT 列出来自旧存档角色对象 entertainment 的五个键。
借书历史里的借出与归还时间存为内核时钟的分钟数。读出时这两项换回游戏时间。
"""

import datetime
from collections.abc import Mapping
from typing import Any, cast

from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import chara_key
from Script.Modules.domains.chara_key import CharaKey

TIMES = ("borrow_time", "return_time")
""" 借书历史的一条记录里存游戏时间的项 """


def _history(records: list[dict[str, Any]]) -> core.JSON:
    return tuple(
        {
            k: game_time.minutes(v) if isinstance(v, datetime.datetime) else v
            for k, v in record.items()
        }
        for record in records
    )


def _history_of(stored: core.JSON) -> list[dict[str, Any]]:
    records = []
    for item in cast(tuple[Mapping[str, Any], ...], stored):
        record = dict(item)
        for k in TIMES:
            if record.get(k) is not None:
                record[k] = game_time.at(record[k])
        records.append(record)
    return records


dormitory: CharaKey[str] = CharaKey("life.dormitory", "", "dormitory")
""" 宿舍坐标 """
permanent_dormitory: CharaKey[str] = CharaKey(
    "life.permanent_dormitory", "", "permanent_dormitory"
)
""" 登记宿舍坐标：临时住进特殊房间期间记录原普通宿舍，住在普通宿舍时为空 """
officeroom: CharaKey[list[str]] = CharaKey(
    "life.officeroom",
    [],
    "officeroom",
    chara_key.sequence,
    chara_key.list_of,
)
""" 所属办公室坐标 """
work_type: CharaKey[int] = CharaKey("life.work_type", 0, "work.work_type")
""" 工作的类型 """
medical_patient_id: CharaKey[int] = CharaKey(
    "life.medical_patient_id", 0, "work.medical_patient_id"
)
""" 正在处理的门诊病人id """
surgery_patient_id: CharaKey[int] = CharaKey(
    "life.surgery_patient_id", 0, "work.surgery_patient_id"
)
""" 正在手术的病人id """
dormitory_admin_phase: CharaKey[int] = CharaKey(
    "life.dormitory_admin_phase", 0, "work.dormitory_admin_phase"
)
""" 宿舍管理员的行动阶段：0 到岗整理，1 移动处理 """
dormitory_admin_target_room: CharaKey[str] = CharaKey(
    "life.dormitory_admin_target_room", "", "work.dormitory_admin_target_room"
)
""" 宿舍管理员当前的目标宿舍 """
entertainment_type: CharaKey[list[int]] = CharaKey(
    "life.entertainment_type",
    [0, 0, 0],
    "entertainment.entertainment_type",
    chara_key.sequence,
    chara_key.list_of,
)
""" 三个娱乐时段的娱乐活动类型 """
borrow_book_id_set: CharaKey[set[int]] = CharaKey(
    "life.borrow_book_id_set",
    set(),
    "entertainment.borrow_book_id_set",
    chara_key.int_set,
    chara_key.set_of,
)
""" 借的书的id """
book_return_possibility: CharaKey[int] = CharaKey(
    "life.book_return_possibility", 0, "entertainment.book_return_possibility"
)
""" 归还当前阅读书籍的可能性比例 """
read_book_progress: CharaKey[dict[int, int]] = CharaKey(
    "life.read_book_progress",
    {},
    "entertainment.read_book_progress",
    chara_key.int_table,
    chara_key.int_table_of,
)
""" 阅读进度 书籍id:进度，100 为读完 """
borrow_book_history: CharaKey[list[dict[str, Any]]] = CharaKey(
    "life.borrow_book_history",
    [],
    "entertainment.borrow_book_history",
    _history,
    _history_of,
)
""" 借书历史，每条记录有 book_id、book_name、borrow_time、return_time、total_read_count """

WORK: tuple[CharaKey[Any], ...] = (
    work_type,
    medical_patient_id,
    surgery_patient_id,
    dormitory_admin_phase,
    dormitory_admin_target_room,
)
""" 旧存档里角色对象的 work 上的几项 """
ENTERTAINMENT: tuple[CharaKey[Any], ...] = (
    entertainment_type,
    borrow_book_id_set,
    book_return_possibility,
    read_book_progress,
    borrow_book_history,
)
""" 旧存档里角色对象的 entertainment 上的几项 """
KEYS: tuple[CharaKey[Any], ...] = (
    dormitory,
    permanent_dormitory,
    officeroom,
    *WORK,
    *ENTERTAINMENT,
)
""" 本模块的角色键 """
PATHS: tuple[CharaKey[str], ...] = (
    dormitory,
    permanent_dormitory,
    dormitory_admin_target_room,
)
""" 存场景路径的角色键 """


def adopt_old_save(loaded_dict: dict[str, Any]) -> None:
    """
    读档时把版本 21 之前存档的角色对象上本模块的数据导入角色键
    导入后从对象上删掉 dormitory、permanent_dormitory、officeroom、work 与 entertainment 属性。
    work.recruit_index 与 entertainment.board_game_settle_data 没有对应的键，随这两个属性一起删掉
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    chara_key.adopt(loaded_dict, KEYS)
