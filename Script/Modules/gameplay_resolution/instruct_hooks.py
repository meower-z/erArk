"""
指令界面钩子（instruct_hooks）
==============================
本模块提供指令界面入口与两组槽位登记函数，不导入界面模块。
on_prompts 登记 select_condom、ask_official_option 与 show_official_result。
未登记时前两者抛出 RuntimeError。未登记时第三者无操作。
on_sex_position 登记 choose_sex_position。未登记时抛出 RuntimeError。
confirm_poor_music、ask_sex_class_ability 与需要询问时的 ask_close_door 经 modal_hooks.ask 发送 ChoicePrompt。
未登记选择处理函数时，modal_hooks.ask 抛出 RuntimeError。
Script.Modules.tk_ui.instruct_callbacks 导入时调用上述两个登记函数填入槽位。
"""

from collections.abc import Callable, Sequence
from typing import Any, NoReturn

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.gameplay_resolution import modal_hooks, pick_hooks
from Script.Modules.gameplay_resolution import normal_panel_service
from Script.Protocol.modal_prompts import ChoiceOption, ChoicePrompt

_ = get_text._
""" 文本翻译函数，指向 get_text._。 """
CLOSE_DOOR_PROMPT_ID = "close_door"
""" 关门询问使用的 ChoicePrompt 标识（"close_door"）。 """
POOR_MUSIC_PROMPT_ID = "poor_music"
""" 音乐能力偏低确认提问使用的 ChoicePrompt 标识（"poor_music"）。 """
SEX_CLASS_ABILITY_PROMPT_ID = "sex_class_ability"
""" 实操课主修科目提问使用的 ChoicePrompt 标识（"sex_class_ability"）。 """
type AskCondom = Callable[[str], dict[str, object] | None]
""" 打开避孕套选择面板的函数类型别名，接收操作类型并返回选择字典或 None。 """
type AskOfficial = Callable[[dict[str, Any]], int]
""" 展示单条公务事件并询问选项的函数类型别名，接收队列项字典并返回选项序号或 0。 """
type ShowOfficial = Callable[[str, int, int, int], None]
""" 展示公务事件结算后果的函数类型别名，接收事件 uid、主体角色编号、互动对象编号与选项序号。 """
type ChooseSexPosition = Callable[[int, bool], None]
""" 打开性交体位选择面板的函数类型别名，接收性交类型编号与换体位标记且无返回值。 """


def _ignore_result(
    uid: str, character_id: int, partner_id: int, option_index: int
) -> None:
    """
    未登记公务结果显示实现时的默认槽位函数，不执行操作。
    Keyword arguments:
    uid -- str，公务事件 uid，此默认实现不使用
    character_id -- int，主体角色编号，此默认实现不使用
    partner_id -- int，互动对象角色编号，此默认实现不使用
    option_index -- int，选定的选项序号，此默认实现不使用
    Return arguments:
    None -- 无返回值
    """


def _unregistered(*args: Any, **kwargs: Any) -> NoReturn:
    """
    未登记指令询问实现时的默认槽位函数，直接抛出 RuntimeError。
    Keyword arguments:
    args -- Any，位置参数，此默认实现不使用
    kwargs -- Any，关键字参数，此默认实现不使用
    Return arguments:
    NoReturn -- 不正常返回，直接抛出 RuntimeError
    """
    raise RuntimeError(
        "no instruct prompt handler registered in instruct_hooks"
    )


_select_condom: AskCondom = _unregistered
""" 当前生效的避孕套选择询问槽位，默认为 _unregistered。 """
_ask_official_option: AskOfficial = _unregistered
""" 当前生效的公务事件选项询问槽位，默认为 _unregistered。 """
_show_official_result: ShowOfficial = _ignore_result
""" 当前生效的公务事件后果显示槽位，默认为 _ignore_result。 """
_choose_sex_position: ChooseSexPosition = _unregistered
""" 当前生效的性交体位选择面板槽位，默认为未登记时抛出 RuntimeError 的 _unregistered。 """


def on_prompts(
    select_condom: AskCondom,
    ask_official_option: AskOfficial,
    show_official_result: ShowOfficial,
) -> None:
    """
    同时登记三个指令询问与结果显示槽位的处理函数。
    后续调用会替换先前登记的处理函数。
    Keyword arguments:
    select_condom -- AskCondom，打开避孕套选择面板的函数
    ask_official_option -- AskOfficial，询问单条公务事件选项的函数
    show_official_result -- ShowOfficial，显示公务事件结算后果的函数
    Return arguments:
    None -- 无返回值
    """
    global _select_condom, _ask_official_option, _show_official_result
    _select_condom = select_condom
    _ask_official_option = ask_official_option
    _show_official_result = show_official_result


def ask_close_door() -> bool | None:
    """
    调用 normal_panel_service.door_ask 读取当前地点的关门询问结果。
    读取结果为 None 时直接返回 None，不调用 modal_hooks.ask。
    否则构造标识为 CLOSE_DOOR_PROMPT_ID、正文为该结果 prompt、选项依次为 "yes"（是）与 "no"（否）的 ChoicePrompt，
    并经 modal_hooks.ask 发起提问。
    未在 modal_hooks 登记选择处理函数时，modal_hooks.ask 抛出 RuntimeError。
    所选选项标识为 "yes" 时返回 True。
    所选选项标识为 "no" 且该结果 cancel_on_no 为真时调用 pick_hooks.back 取消选择。
    所选选项标识为 "no" 且该结果 cancel_on_no 为假时返回 False。
    Return arguments:
    bool | None -- 无需询问时返回 None，选 "yes" 返回 True，选 "no" 且不取消时返回 False
    """
    ask = normal_panel_service.door_ask()
    if ask is None:
        return None
    prompt = ChoicePrompt(
        CLOSE_DOOR_PROMPT_ID,
        (ChoiceOption("yes", _("是")), ChoiceOption("no", _("否"))),
        ask.prompt,
    )
    if modal_hooks.ask(prompt).selected_option_id == "yes":
        return True
    if ask.cancel_on_no:
        pick_hooks.back()
    return False


def ask_sex_class_ability(ability_ids: Sequence[int]) -> int:
    """
    构造标识为 SEX_CLASS_ABILITY_PROMPT_ID 的 ChoicePrompt，并经 modal_hooks.ask 询问实操课主修科目。
    提示选项依次包含 ability_ids 各能力编号对应的科目项与末尾的 back（返回）项。
    未在 modal_hooks 登记选择处理函数时抛出 RuntimeError。
    Keyword arguments:
    ability_ids -- Sequence[int]，可供选择的主修科目能力编号序列
    Return arguments:
    int -- 所选选项标识为 "back" 时返回 -1，否则返回该选项标识转换后的能力编号
    """
    subjects = tuple(
        ChoiceOption(
            str(ability_id), game_config.config_ability[ability_id].name
        )
        for ability_id in ability_ids
    )
    prompt = ChoicePrompt(
        SEX_CLASS_ABILITY_PROMPT_ID,
        (*subjects, ChoiceOption("back", _("返回"))),
        _(
            "\n这节实操课主要练哪一门？\n（其他动作照样可以做，只是不会有本门的加成）\n\n"
        ),
    )
    answer = modal_hooks.ask(prompt).selected_option_id
    return -1 if answer == "back" else int(answer)


def confirm_poor_music() -> bool:
    """
    构造标识为 POOR_MUSIC_PROMPT_ID、包含 cancel（取消）与 confirm（确定）两项的 ChoicePrompt，
    并经 modal_hooks.ask 发起音乐能力偏低时的继续确认提问。
    未在 modal_hooks 登记选择处理函数时抛出 RuntimeError。
    Return arguments:
    bool -- 所选选项标识为 "confirm" 时返回 True，否则返回 False
    """
    prompt = ChoicePrompt(
        POOR_MUSIC_PROMPT_ID,
        (ChoiceOption("cancel", _("取消")), ChoiceOption("confirm", _("确定"))),
        _("\n当前音乐能力小于等于2，可能会让对方感觉不适，确认要继续吗\n\n"),
    )
    return modal_hooks.ask(prompt).selected_option_id == "confirm"


def select_condom(mode: str) -> dict[str, object] | None:
    """
    在调用时读取当前 _select_condom 槽位，打开避孕套选择面板。
    未登记时抛出 RuntimeError。
    Keyword arguments:
    mode -- str，面板操作类型，可选 hang、take_back、drink 或 squeeze
    Return arguments:
    dict[str, object] | None -- 玩家确认的选择字典，取消时为 None
    """
    return _select_condom(mode)


def ask_official_option(queue_data: dict[str, Any]) -> int:
    """
    在调用时读取当前 _ask_official_option 槽位，为单条公务事件询问玩家选定的选项。
    未登记时抛出 RuntimeError。
    Keyword arguments:
    queue_data -- dict[str, Any]，待决断队列中弹出的单条公务事件字典
    Return arguments:
    int -- 选定的选项配置序号，无可用选项时为 0
    """
    return _ask_official_option(queue_data)


def show_official_result(
    uid: str, character_id: int, partner_id: int, option_index: int
) -> None:
    """
    在调用时读取当前 _show_official_result 槽位，显示公务事件选项的结算后果。
    未登记时不执行操作。
    Keyword arguments:
    uid -- str，公务事件 uid
    character_id -- int，主体角色编号
    partner_id -- int，互动对象角色编号
    option_index -- int，已结算的选项配置序号
    Return arguments:
    None -- 无返回值
    """
    _show_official_result(uid, character_id, partner_id, option_index)


def on_sex_position(choose_sex_position: ChooseSexPosition) -> None:
    """
    登记性交体位选择面板槽位的处理函数。
    后续调用会替换先前登记的处理函数。
    Keyword arguments:
    choose_sex_position -- ChooseSexPosition，打开性交体位选择面板的函数
    Return arguments:
    None -- 无返回值
    """
    global _choose_sex_position
    _choose_sex_position = choose_sex_position


def choose_sex_position(sex_type: int, change_position: bool) -> None:
    """
    在调用时读取当前 _choose_sex_position 槽位，打开性交体位选择面板。
    未登记时抛出 RuntimeError。
    Keyword arguments:
    sex_type -- int，性交类型编号（1 阴道、2 子宫口、3 子宫、4 肛门、5 尿道）
    change_position -- bool，是否为切换体位
    Return arguments:
    None -- 无返回值
    """
    _choose_sex_position(sex_type, change_position)
