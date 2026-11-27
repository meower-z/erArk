"""
tk_ui 的指令界面回调
====================
导入时调用 instruct_hooks.on_instruct 与 on_prompts 登记十个槽位。
show_non_h 写 view.show_non_h_in_hidden_sex。stash_filter 与 stashed_filter 读写 view.instruct_type_filter_cache。
skip_pauses 调用时查找 flow_handle.set_skip_pauses。
ask_sex_class_ability 与 confirm_poor_music 用 draw 画提示与按钮，经 flow_handle.askfor_all 读回答。
ask_close_door 与 select_condom 调用时分别导入 normal_panel 与 condom_panel。
ask_official_option 与 show_official_result 调用时导入 official_event_panel。
"""

from collections.abc import Sequence
from types import FunctionType
from typing import Any

from Script.Config import game_config, normal_config
from Script.Core import flow_handle, get_text
from Script.Modules.gameplay_resolution import instruct_hooks
from Script.UI.Moudle import draw, view

_: FunctionType = get_text._
""" 翻译api """
width: int = normal_config.config_normal.text_width
""" 屏幕宽度 """


def show_non_h(shown: bool) -> None:
    """
    将 view.show_non_h_in_hidden_sex 设为 shown。
    Keyword arguments:
    shown -- bool，隐奸中显示非H指令开关的新值
    Return arguments:
    None -- 无返回值
    """
    view.show_non_h_in_hidden_sex = shown


def skip_pauses(enabled: bool) -> None:
    """
    在调用时查找 flow_handle.set_skip_pauses 并以 enabled 调用它。
    Keyword arguments:
    enabled -- bool，为真时开启跳过暂停模式
    Return arguments:
    None -- 无返回值
    """
    flow_handle.set_skip_pauses(enabled)


def stash_filter(filters: dict[int, bool]) -> None:
    """
    将 view.instruct_type_filter_cache 设为 filters。
    Keyword arguments:
    filters -- dict[int, bool]，指令类型到是否展示的映射
    Return arguments:
    None -- 无返回值
    """
    view.instruct_type_filter_cache = filters


def stashed_filter() -> dict[int, bool]:
    """
    返回 view.instruct_type_filter_cache 当前引用的字典。
    Return arguments:
    dict[int, bool] -- view.instruct_type_filter_cache 当前引用的字典
    """
    return view.instruct_type_filter_cache


def ask_close_door() -> bool | None:
    """
    在调用时导入 normal_panel，以当前文本宽度创建 Close_Door_Panel 并调用其 draw 询问玩家是否关门。
    Return arguments:
    bool | None -- 关门为 True，不关为 False，当前地点已问过时为 None
    """
    from Script.UI.Panel import normal_panel

    return normal_panel.Close_Door_Panel(width).draw()


def ask_sex_class_ability(ability_ids: Sequence[int]) -> int:
    """
    绘制性技实操课主修科目提示、各科目按钮与返回按钮，并经 flow_handle.askfor_all 等待选择。
    按钮宽度均为 int(width / 4)。
    Keyword arguments:
    ability_ids -- Sequence[int]，可供选择的能力编号序列
    Return arguments:
    int -- 选中按钮对应的能力编号，选择返回按钮时为 -1
    """
    now_draw = draw.NormalDraw()
    now_draw.width = width
    now_draw.text = _(
        "\n这节实操课主要练哪一门？\n（其他动作照样可以做，只是不会有本门的加成）\n\n"
    )
    now_draw.draw()
    return_list = []
    id_to_return = {}
    for ability_id in ability_ids:
        ability_name = game_config.config_ability[ability_id].name
        now_button = draw.CenterButton(
            _("[{0}]").format(ability_name), ability_name, int(width / 4)
        )
        now_button.draw()
        return_list.append(now_button.return_text)
        id_to_return[now_button.return_text] = ability_id
    line_draw = draw.NormalDraw()
    line_draw.text = "\n"
    line_draw.draw()
    back_draw = draw.CenterButton(_("[返回]"), _("返回"), int(width / 4))
    back_draw.draw()
    return_list.append(back_draw.return_text)
    yrn = flow_handle.askfor_all(return_list)
    return id_to_return.get(yrn, -1)


def confirm_poor_music() -> bool:
    """
    使用 draw.WaitDraw 显示低音乐能力提示，并绘制宽度为 int(width / 3) 的取消与确定按钮等待确认。
    Return arguments:
    bool -- 玩家选择确定按钮时为 True，选择取消按钮时为 False
    """
    now_draw = draw.WaitDraw()
    now_draw.width = width
    now_draw.text = _(
        "\n当前音乐能力小于等于2，可能会让对方感觉不适，确认要继续吗\n\n"
    )
    now_draw.draw()
    back_draw = draw.CenterButton(_("[取消]"), _("\n取消"), int(width / 3))
    back_draw.draw()
    yes_draw = draw.CenterButton(_("[确定]"), _("\n确定"), int(width / 3))
    yes_draw.draw()
    yrn = flow_handle.askfor_all([back_draw.return_text, yes_draw.return_text])
    return yrn == yes_draw.return_text


def select_condom(mode: str) -> dict[str, object] | None:
    """
    在调用时导入 condom_panel，并以当前文本宽度和 mode 调用 Condom_Select_Panel.draw。
    Keyword arguments:
    mode -- str，避孕套面板操作类型，可选 hang、take_back、drink 或 squeeze
    Return arguments:
    dict[str, object] | None -- 玩家确认的选择字典，取消时为 None
    """
    from Script.UI.Panel import condom_panel

    return condom_panel.Condom_Select_Panel(width, mode).draw()


def ask_official_option(queue_data: dict[str, Any]) -> int:
    """
    在调用时导入 official_event_panel，并以 queue_data 和当前文本宽度调用 Official_Event_Draw.draw。
    Keyword arguments:
    queue_data -- dict[str, Any]，待决断队列中的单条公务事件字典
    Return arguments:
    int -- 玩家选定的选项配置序号，无可用选项时为 0
    """
    from Script.UI.Panel import official_event_panel

    return official_event_panel.Official_Event_Draw(queue_data, width).draw()


def show_official_result(
    uid: str, character_id: int, partner_id: int, option_index: int
) -> None:
    """
    在调用时导入 official_event_panel，构造事件字典并调用 Official_Event_Draw.draw_result 显示结算后果。
    Keyword arguments:
    uid -- str，公务事件 uid
    character_id -- int，主体角色编号
    partner_id -- int，互动对象角色编号
    option_index -- int，已结算的选项配置序号
    Return arguments:
    None -- 无返回值
    """
    from Script.UI.Panel import official_event_panel

    queue_data = {
        "uid": uid,
        "chara_id": character_id,
        "partner_id": partner_id,
    }
    official_event_panel.Official_Event_Draw(queue_data, width).draw_result(
        option_index
    )


instruct_hooks.on_instruct(
    show_non_h, skip_pauses, stash_filter, stashed_filter
)
instruct_hooks.on_prompts(
    ask_close_door,
    ask_sex_class_ability,
    confirm_poor_music,
    select_condom,
    ask_official_option,
    show_official_result,
)
