"""按行动编号准备实际行为；准备操作不进入角色的 Behavior。

状态机可以在准备阶段为本角色提交强制后续；此时执行器放弃本次行动，由该待办结算一次。
"""


def _prepare_npc_action(runtime, actor: int, action):
    """输入执行器、角色编号和 Action，落实状态机；返回实际 Action。"""
    from Script.Core import cache_control, constant
    from Script.Modules.scheduler.action import Action, STATE

    if action.params.get("record_absence", False):
        from Script.System.Education_System import class_ai

        class_ai.settle_absent(actor)
    constant.handle_state_machine_data[action.params["state_machine_id"]](actor)
    character = cache_control.cache.character_data[actor]
    # 仅更新需求的状态机仍保持闲置，按原节奏等待后再选择。
    if character.behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
        return Action(constant.Behavior.WAIT, 5, actor, params={STATE: constant.CharacterStatus.STATUS_WAIT})
    return Action.from_character(character)


def _prepare_group_action(runtime, actor: int, action):
    """输入执行器、角色编号和 Action，落实群交操作；返回实际 Action。"""
    from Script.Core import cache_control
    from Script.Modules.scheduler.action import Action
    from Script.Design.handle_npc_ai_in_h import execute_group_action

    # 群交选择只在闲置时发生，操作落实后按安排的等待行为结算一次。
    execute_group_action(actor, action)
    return Action.from_character(cache_control.cache.character_data[actor])


# 准备动作按编号注册，调度器只传递统一的 Action。
_PREPARERS = {
    "prepare_npc_action": _prepare_npc_action,
    "group_join": _prepare_group_action,
    "group_fill": _prepare_group_action,
}


def prepare_action(runtime, actor: int, action):
    """输入执行器、角色编号和 Action，返回可结算的 Action。"""
    prepare = _PREPARERS.get(action.behavior_id)
    return action if prepare is None else prepare(runtime, actor, action)
