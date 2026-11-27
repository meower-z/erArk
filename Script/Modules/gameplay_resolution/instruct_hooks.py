"""
指令界面钩子（instruct_hooks）
==============================
本模块提供三组指令界面入口与登记函数。本模块不导入界面模块。
on_instruct 登记 stash_filter 与 stashed_filter。
未登记时 stash_filter 无操作。未登记时 stashed_filter 返回新空字典。
on_prompts 登记 ask_close_door、ask_sex_class_ability、confirm_poor_music、select_condom、
ask_official_option 与 show_official_result。未登记时前五个抛出 RuntimeError。未登记时第六个无操作。
on_sex_position 登记 choose_sex_position。未登记时抛出 RuntimeError。
Script.Modules.tk_ui.instruct_callbacks 导入时调用上述三个登记函数填入三组槽位。
"""

from collections.abc import Callable, Sequence
from typing import Any, NoReturn

type FilterStash = Callable[[dict[int, bool]], None]
""" 接收指令类型过滤状态字典并暂存的函数类型别名。 """
type FilterStashed = Callable[[], dict[int, bool]]
""" 返回暂存的指令类型过滤状态字典的函数类型别名。 """
type AskDoor = Callable[[], bool | None]
""" 询问玩家是否关门的函数类型别名，返回布尔值或在当前地点已问过时返回 None。 """
type AskAbility = Callable[[Sequence[int]], int]
""" 询问性技实操课主修科目的函数类型别名，接收可选能力编号序列并返回选定编号或 -1。 """
type Confirm = Callable[[], bool]
""" 弹出确认询问并返回玩家是否同意的函数类型别名。 """
type AskCondom = Callable[[str], dict[str, object] | None]
""" 打开避孕套选择面板的函数类型别名，接收操作类型并返回选择字典或 None。 """
type AskOfficial = Callable[[dict[str, Any]], int]
""" 展示单条公务事件并询问选项的函数类型别名，接收队列项字典并返回选项序号或 0。 """
type ShowOfficial = Callable[[str, int, int, int], None]
""" 展示公务事件结算后果的函数类型别名，接收事件 uid、主体角色编号、互动对象编号与选项序号。 """
type ChooseSexPosition = Callable[[int, bool], None]
""" 打开性交体位选择面板的函数类型别名，接收性交类型编号与换体位标记且无返回值。 """


def _ignore(value: object) -> None:
    """
    未登记时的默认写入函数，不执行操作。
    Keyword arguments:
    value -- object，写入值，此默认实现不使用
    Return arguments:
    None -- 无返回值
    """


def _nothing_stashed() -> dict[int, bool]:
    """
    未登记时的默认暂存读取函数，返回新的空字典。
    Return arguments:
    dict[int, bool] -- 空字典
    """
    return {}


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


_stash_filter: FilterStash = _ignore
""" 当前生效的指令类型过滤状态暂存槽位，默认为 _ignore。 """
_stashed_filter: FilterStashed = _nothing_stashed
""" 当前生效的指令类型过滤状态读取槽位，默认为 _nothing_stashed。 """
_ask_close_door: AskDoor = _unregistered
""" 当前生效的关门询问槽位，默认为 _unregistered。 """
_ask_sex_class_ability: AskAbility = _unregistered
""" 当前生效的性技实操课主修科目询问槽位，默认为 _unregistered。 """
_confirm_poor_music: Confirm = _unregistered
""" 当前生效的低音乐能力继续确认槽位，默认为 _unregistered。 """
_select_condom: AskCondom = _unregistered
""" 当前生效的避孕套选择询问槽位，默认为 _unregistered。 """
_ask_official_option: AskOfficial = _unregistered
""" 当前生效的公务事件选项询问槽位，默认为 _unregistered。 """
_show_official_result: ShowOfficial = _ignore_result
""" 当前生效的公务事件后果显示槽位，默认为 _ignore_result。 """
_choose_sex_position: ChooseSexPosition = _unregistered
""" 当前生效的性交体位选择面板槽位，默认为未登记时抛出 RuntimeError 的 _unregistered。 """


def on_instruct(
    stash_filter: FilterStash, stashed_filter: FilterStashed
) -> None:
    """
    同时登记两个指令类型过滤状态槽位的处理函数。
    后续调用会替换先前登记的处理函数。
    Keyword arguments:
    stash_filter -- FilterStash，暂存指令类型过滤状态的函数
    stashed_filter -- FilterStashed，读取暂存的指令类型过滤状态的函数
    Return arguments:
    None -- 无返回值
    """
    global _stash_filter, _stashed_filter
    _stash_filter, _stashed_filter = stash_filter, stashed_filter


def stash_filter(filters: dict[int, bool]) -> None:
    """
    在调用时读取当前 _stash_filter 槽位，暂存指令类型过滤状态。
    Keyword arguments:
    filters -- dict[int, bool]，指令类型到是否展示的映射
    Return arguments:
    None -- 无返回值
    """
    _stash_filter(filters)


def stashed_filter() -> dict[int, bool]:
    """
    在调用时读取当前 _stashed_filter 槽位，返回暂存的指令类型过滤状态。
    Return arguments:
    dict[int, bool] -- 暂存的指令类型到是否展示的映射
    """
    return _stashed_filter()


def on_prompts(
    ask_close_door: AskDoor,
    ask_sex_class_ability: AskAbility,
    confirm_poor_music: Confirm,
    select_condom: AskCondom,
    ask_official_option: AskOfficial,
    show_official_result: ShowOfficial,
) -> None:
    """
    同时登记六个指令询问与结果显示槽位的处理函数。
    后续调用会替换先前登记的处理函数。
    Keyword arguments:
    ask_close_door -- AskDoor，询问玩家是否关门的函数
    ask_sex_class_ability -- AskAbility，询问性技实操课主修科目的函数
    confirm_poor_music -- Confirm，确认低音乐能力下是否继续的函数
    select_condom -- AskCondom，打开避孕套选择面板的函数
    ask_official_option -- AskOfficial，询问单条公务事件选项的函数
    show_official_result -- ShowOfficial，显示公务事件结算后果的函数
    Return arguments:
    None -- 无返回值
    """
    global _ask_close_door, _ask_sex_class_ability, _confirm_poor_music
    global _select_condom, _ask_official_option, _show_official_result
    _ask_close_door = ask_close_door
    _ask_sex_class_ability = ask_sex_class_ability
    _confirm_poor_music = confirm_poor_music
    _select_condom = select_condom
    _ask_official_option = ask_official_option
    _show_official_result = show_official_result


def ask_close_door() -> bool | None:
    """
    在调用时读取当前 _ask_close_door 槽位，询问玩家是否关门。
    未登记时抛出 RuntimeError。
    Return arguments:
    bool | None -- 关门为 True，不关为 False，当前地点已问过时为 None
    """
    return _ask_close_door()


def ask_sex_class_ability(ability_ids: Sequence[int]) -> int:
    """
    在调用时读取当前 _ask_sex_class_ability 槽位，询问性技实操课的主修科目。
    未登记时抛出 RuntimeError。
    Keyword arguments:
    ability_ids -- Sequence[int]，可供选择的能力编号序列
    Return arguments:
    int -- 选中的能力编号，选择返回时为 -1
    """
    return _ask_sex_class_ability(ability_ids)


def confirm_poor_music() -> bool:
    """
    在调用时读取当前 _confirm_poor_music 槽位，在音乐能力偏低时询问玩家是否继续。
    未登记时抛出 RuntimeError。
    Return arguments:
    bool -- 玩家确认继续时为 True，取消时为 False
    """
    return _confirm_poor_music()


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
