"""
角色信息头部文本服务（chara_head_service）
==========================================
本模块提供角色信息头部标题文本组装与快捷用药可用性判定。
本模块公开函数 head_message 与 quick_drugs。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

from types import FunctionType

from Script.Config import normal_config
from Script.Core import get_text
from Script.Design import attr_calculation
from Script.Modules.domains import chara_profile, h_meters, identity
from Script.Modules.domains import inventory, relations

_: FunctionType = get_text._
""" 翻译api """


def _favorability_trust_text(character_id: int) -> str:
    favorability = relations.favorability(character_id)[0]
    trust = relations.trust(character_id)
    favorability_lv, _fav_tem = attr_calculation.get_favorability_level(
        favorability
    )
    favorability_letter = attr_calculation.judge_grade(favorability_lv)
    trust_lv, _trust_tem = attr_calculation.get_trust_level(trust)
    trust_letter = attr_calculation.judge_grade(trust_lv)
    mode = normal_config.system_setting.draw_setting[3]
    if mode == 1:
        return _("好感度:{0}，信赖度:{1}").format(
            favorability_letter, trust_letter
        )
    if mode == 2:
        return _("好感度:{0}({1})，信赖度:{2}({3})").format(
            f"{int(favorability)}",
            favorability_letter,
            f"{round(trust, 1)}%",
            trust_letter,
        )
    return ""


def _eja_text() -> str:
    eja_val = h_meters.of(0)["eja"]
    if eja_val <= 0:
        return ""
    if eja_val <= 300:
        return _(" <射精欲:低>")
    if eja_val <= 600:
        return _(" <射精欲:中>")
    if eja_val <= 900:
        return _(" <射精欲:高>")
    return _(" <射精欲:极>")


def head_message(character_id: int) -> str:
    """
    生成角色信息头部的姓名与附加信息文本。
    非零编号角色返回姓名加空格与按 draw_setting[3] 格式化的好感度及信赖度文本。
    玩家角色（编号 0）返回姓名、昵称以及按射精欲数值分档的标识文本。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    str -- 角色信息头部标题文本
    """
    name = identity.of(character_id).name
    if character_id:
        return f"{name} {_favorability_trust_text(character_id)}"
    return f"{name}{chara_profile.nick_name(character_id)}{_eja_text()}"


def quick_drugs(character_id: int) -> tuple[bool, bool]:
    """
    检查角色是否持有可供快捷使用的理智恢复剂与精力恢复剂。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    tuple[bool, bool] -- 首项表示是否持有道具 0 至 3 中的任意一项，次项表示是否持有道具 11
    """
    items = inventory.items(character_id)
    return any(items[item_id] > 0 for item_id in (0, 1, 2, 3)), items[11] > 0
