"""
公务事件提示文本（official_prompt）
===================================
本模块提供公务事件的口上代码转写函数 get_code_text 与选项结算结果文本构造函数 result_text。
本模块不导入界面模块。
"""

from Script.Core import get_text
from Script.Design import talk
from Script.Modules.domains import activity, identity
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
