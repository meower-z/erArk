"""角色状态机：按状态机id取出选行动的计划，以及注册状态机的装饰器

状态机只读缓存，交回一个计划（npc_action_choice.choice.Plan）。
计划变成内核行动，由 gameplay_resolution 在行动开始时写进缓存。
constant.handle_state_machine_data 里登记的入口给直接让角色执行某个状态机的面板用：它把选出的行动排进角色的计划队列，
并打断角色当前的行动。
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING

from Script.Core import constant

if TYPE_CHECKING:
    from Script.Modules.npc_action_choice import choice

type StateMachine = Callable[[int], choice.Plan]
""" 状态机：角色id -> 计划 """

plans: dict[int, StateMachine] = {}
""" 状态机id -> 状态机 """


def handle_state_machine(state_machine_id: int, character_id: int) -> None:
    """
    让角色按状态机选出行动，排进它的计划队列并打断它当前的行动
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


def plan_of(state_machine_id: int, character_id: int) -> choice.Plan:
    """
    让角色按状态机选出行动
    Keyword arguments:
    state_machine_id -- 状态机id
    character_id -- 角色id
    Return arguments:
    Plan -- 选出的计划
    """
    return plans[state_machine_id](character_id)


def queue_plan(plan: choice.Plan) -> None:
    """
    把计划排进角色的计划队列，并打断角色当前的行动
    Keyword arguments:
    plan -- 计划
    """
    from Script.Modules.gameplay_resolution import plan_queue

    intent = plan.intent
    plan_queue.plan_next(
        plan.character_id,
        intent["behavior_id"],
        intent["minutes"],
        kind=plan.action_kind,
        target=intent.get("target"),
        state=intent.get("state"),
        interrupt=True,
        fields=intent.get("fields"),
        args=intent.get("args"),
        move=intent.get("move"),
        say=intent.get("say"),
    )


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
        def choose_and_queue(character_id: int) -> None:
            queue_plan(func(character_id))

        plans[state_machine_id] = func
        constant.handle_state_machine_data[state_machine_id] = choose_and_queue
        return func

    return decorator
