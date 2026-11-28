"""
公务事件提示文本（official_prompt）
===================================
本模块提供公务事件的口上代码转写函数 get_code_text、结算结果文本构造函数 result_text，
以及事件抬头、正文与选项列表构造函数 event_title、event_text 与 event_options。
本模块不导入界面模块。
"""

from collections.abc import Mapping
from typing import Any

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import talk
from Script.Modules.domains import activity, identity
from Script.Protocol.modal_prompts import ChoiceOption
from Script.System.Official_Event_System import official_event_handle

_ = get_text._
""" 文本翻译函数，指向 get_text._。 """


def get_code_text(raw_text: str, character_id: int, partner_id: int) -> str:
    """
    将公务事件文本中的口上代码转为可显示文本。
    raw_text 为空时返回空字符串。
    character_id 不存在于 identity 时原样返回 raw_text。
    其余情况下在 activity.target_as(character_id, partner_id) 上下文内调用 talk.code_text_to_draw_text 完成转换。
    activity.target_as 在转换期间将主体的交互对象临时读作 partner_id，不写入状态。
    Keyword arguments:
    raw_text -- str，待转换的原始文本
    character_id -- int，主体角色编号
    partner_id -- int，互动对象角色编号
    Return arguments:
    str -- 转换后的可显示文本
    """
    if not raw_text:
        return ""
    if not identity.exists(character_id):
        return raw_text
    with activity.target_as(character_id, partner_id):
        return talk.code_text_to_draw_text(raw_text, character_id)


def result_text(
    uid: str, character_id: int, partner_id: int, option_index: int
) -> str | None:
    """
    构造公务事件选项结算后的结果提示文本。
    本函数在 official_event_handle.get_option_list 返回的选项列表中查找 index 等于 option_index 的选项。
    未找到匹配选项时返回 None。
    找到匹配选项后先以 get_code_text 转换该选项的 tip。
    转换后的 tip 为空时返回 None。
    转换后的 tip 非空时再以 get_code_text 转换该选项的 text，并经翻译模板拼装选项文本与结果提示后返回。
    Keyword arguments:
    uid -- str，公务事件 uid
    character_id -- int，主体角色编号
    partner_id -- int，互动对象角色编号
    option_index -- int，已结算的选项配置序号
    Return arguments:
    str | None -- 结果提示文本，无匹配选项或转换后的 tip 为空时返回 None
    """
    for option in official_event_handle.get_option_list(
        uid, character_id, partner_id
    ):
        if option["index"] != option_index:
            continue
        tip_text = get_code_text(option["tip"], character_id, partner_id)
        if not tip_text:
            return None
        option_text = get_code_text(option["text"], character_id, partner_id)
        return _("\n  你选择了「{0}」\n  结果：{1}\n").format(
            option_text, tip_text
        )
    return None


def event_title(queue_data: Mapping[str, Any]) -> str:
    """
    获取单条公务事件的抬头文本。
    部门编号优先取 queue_data 中的 "department"，缺省时调用 official_event_handle.get_event_department 获取。
    该部门在 official_event_handle.EVENT_TITLE 中有抬头提供者时，调用提供者并返回其结果。
    提供者抛出 Exception 时，向标准输出打印含部门编号与错误信息的调试行并回退。
    未登记提供者或调用回退时，返回 official_event_handle.get_department_name(department)。
    Keyword arguments:
    queue_data -- Mapping[str, Any]，公务事件队列项，包含 uid，可选 department
    Return arguments:
    str -- 公务事件抬头文本
    """
    department = queue_data.get(
        "department",
        official_event_handle.get_event_department(queue_data["uid"]),
    )
    if department in official_event_handle.EVENT_TITLE:
        try:
            return official_event_handle.EVENT_TITLE[department](queue_data)
        except Exception as now_error:
            print(
                f"\ndebug 公务事件的部门{department}抬头提供者报错：{now_error}\n"
            )
    return official_event_handle.get_department_name(department)


def event_text(queue_data: Mapping[str, Any]) -> str:
    """
    构造单条公务事件的正文显示文本。
    按 queue_data["uid"] 读取 game_config.config_official_event 中的事件配置，缺少该 uid 时抛出 KeyError。
    读取配置的 text 字段后调用 get_code_text 转换口上代码，chara_id 与 partner_id 缺省时均为 0。
    转换结果按 "\n  {}\n\n" 格式拼装后返回。
    Keyword arguments:
    queue_data -- Mapping[str, Any]，公务事件队列项，包含 uid，可选 chara_id 与 partner_id
    Return arguments:
    str -- 带前后空行与两格缩进的事件正文文本
    """
    event_data = game_config.config_official_event[queue_data["uid"]]
    return "\n  {}\n\n".format(
        get_code_text(
            event_data.get("text", ""),
            queue_data.get("chara_id", 0),
            queue_data.get("partner_id", 0),
        )
    )


def event_options(queue_data: Mapping[str, Any]) -> tuple[ChoiceOption, ...]:
    """
    按配置表原序构造单条公务事件的 ChoiceOption 元组。
    调用 official_event_handle.get_option_list 读取事件选项，chara_id 与 partner_id 缺省时均为 0。
    每项以配置序号字符串作为 option_id，以转换后的选项文本作为 label。
    can_use 为真时 availability 为 "open" 且 note 为空字符串。
    can_use 为假时 availability 为 "blocked"，note 为转换后的 reason 文本。
    Keyword arguments:
    queue_data -- Mapping[str, Any]，公务事件队列项，包含 uid，可选 chara_id 与 partner_id
    Return arguments:
    tuple[ChoiceOption, ...] -- 按配置表原序排列的选项元组，事件无选项时为空元组
    """
    character_id = queue_data.get("chara_id", 0)
    partner_id = queue_data.get("partner_id", 0)
    return tuple(
        ChoiceOption(
            str(option["index"]),
            get_code_text(option["text"], character_id, partner_id),
            "open" if option["can_use"] else "blocked",
            (
                ""
                if option["can_use"]
                else get_code_text(option["reason"], character_id, partner_id)
            ),
        )
        for option in official_event_handle.get_option_list(
            queue_data["uid"], character_id, partner_id
        )
    )
