"""角色状态机：按状态机id取出选行动的计划，以及注册状态机的装饰器

状态机只读缓存，交回一个计划（npc_action_choice.choice.Plan），由 gameplay_resolution 在行动开始时写进缓存。
constant.handle_state_machine_data 里登记的是"选出并开始"的入口，给直接让角色执行某个状态机的面板用。
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING

from Script.Core import constant

if TYPE_CHECKING:
    from Script.Modules.npc_action_choice import choice

type StateMachine = Callable[[int], choice.Plan | None]
""" 状态机：角色id -> 计划（自己结算的状态机交回 None） """

plans: dict[int, StateMachine] = {}
""" 状态机id -> 状态机 """

starter: Callable[[int, choice.Plan | None], None] | None = None
""" 开始一个计划的函数，由 gameplay_resolution 的 npc_start 在导入时填上 """


def handle_state_machine(state_machine_id: int, character_id: int) -> None:
    """
    让角色按状态机选出行动并开始它
    Keyword arguments:
    state_machine_id -- 状态机id
    character_id -- 角色id
    """
    if state_machine_id in constant.handle_state_machine_data:
        constant.handle_state_machine_data[state_machine_id](character_id)


def new_plan(character_id: int) -> choice.Plan:
    """
    给状态机开一个空计划；Script.Modules 在用到时才导入，旧代码导入本模块时不会提前触发它的包初始化
    Keyword arguments:
    character_id -- 选行动的角色id
    Return arguments:
    Plan -- 空计划
    """
    from Script.Modules.npc_action_choice import choice as choice_module

    return choice_module.Plan(character_id)


def plan_of(state_machine_id: int, character_id: int) -> choice.Plan | None:
    """
    让角色按状态机选出行动
    Keyword arguments:
    state_machine_id -- 状态机id
    character_id -- 角色id
    Return arguments:
    Plan | None -- 选出的计划
    """
    return plans[state_machine_id](character_id)


def add_state_machine(
    state_machine_id: int,
) -> Callable[[StateMachine], StateMachine]:
    """
    添加角色状态机函数
    Keyword arguments:
    state_machine_id -- 状态机id
    """

    def decorator(func: StateMachine) -> StateMachine:
        @wraps(func)
        def choose_and_start(character_id: int) -> None:
            assert starter is not None, "npc_start 尚未导入"
            starter(character_id, func(character_id))

        plans[state_machine_id] = func
        constant.handle_state_machine_data[state_machine_id] = choose_and_start
        return func

    return decorator
