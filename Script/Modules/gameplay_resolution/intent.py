"""
gameplay_resolution 的行动意图（Intent）
=======================================
一个角色选出的行动在内核里是 core.Action：action_id 是行动的种类 gameplay_resolution.<kind>，
duration 是流逝的分钟数，action_data 是这里的 Intent，只含 JSON 值。
选行动只读不写；Intent 记下开始时要做的事，行动开始时（starts.behave）照着写进缓存。
behavior_action 是造这种 Action 的唯一入口。
"""

from typing import NotRequired, TypedDict, cast

from Script.Kernel import core

KIND_PREFIX = "gameplay_resolution."
""" 行动种类的 action_id 前缀 """


class Move(TypedDict):
    """开始时的移动"""

    to: list[str]
    """ 目的地的场景路径 """
    show: bool
    """ 是否绘制移动的文本 """


class Intent(TypedDict):
    """一个行动的意图：选行动时定下，行动开始时照着做"""

    behavior_id: str
    """ constant.Behavior 里的行为id；开始门与结算按它分派 """
    minutes: int
    """ 名义分钟数；时停中玩家的 duration 是 0，这里仍是名义值 """
    target: NotRequired[int]
    """ 交互对象的角色id，默认自己 """
    state: NotRequired[int | str]
    """ 开始时的角色状态（Character.state：CharacterStatus id，或行为id） """
    fields: NotRequired[dict[str, core.JSON]]
    """ 开始时写在行动者自己身上的值：路径到 JSON 值，路径的根是 behavior、sp_flag、action_info 或 work，
    例如 "behavior.move_target" """
    move: NotRequired[Move]
    """ 开始时的移动 """
    say: NotRequired[str]
    """ 开始时绘制的文本 """
    args: NotRequired[dict[str, core.JSON]]
    """ 本种类自己的参数：选行动时定下的id与随机值 """
    premises: NotRequired[list[str]]
    """ 选中的前提id，开始时由开始门再查一次 """
    queued: NotRequired[bool]
    """ 来自计划队列：开始时弹出队首 """
    judge: NotRequired[str]
    """ 玩家指令的判定名（instuct_judege.calculation_instuct_judege 的 instruct_name），开始门检查 """
    draft: NotRequired[list[core.JSON]]
    """ 选择时写下的草稿（draft.Change 的列表），开始时在 begin 之前写入；判定没过时不写 """
    interrupts: NotRequired[list[str]]
    """ 选择时排下打断的角色键，开始时在 begin 之前重新排上；判定没过时不排 """


def behavior_action(
    who: int, intent: Intent, kind: str = "Behavior"
) -> core.Action:
    """
    造一个从此刻开始的行动
    Keyword arguments:
    who -- 角色id
    intent -- 行动的意图
    kind -- 行动的种类，action_id 为 gameplay_resolution.<kind>
    Return arguments:
    Action -- 时长为 intent 的分钟数；干员至少 1 分钟
    """
    minutes = intent["minutes"]
    if who != 0:
        minutes = max(1, minutes)
    # TypedDict 的值在 mypy 里是 object；Intent 的每个键都是 JSON 值，内核开始行动时还会冻结并检查一遍
    data = cast(core.JSON, dict(intent))
    return core.Action(
        str(who), KIND_PREFIX + kind, data, core.state().clock, minutes
    )
