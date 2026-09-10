"""按行动编号准备实际行为；准备操作不进入角色的 Behavior。"""


def _prepare_npc_action(runtime, actor: int, action):
    """输入执行器、角色编号和 Action，落实状态机；返回实际 Action 或已消费的 None。"""
    from Script.Core import cache_control, constant
    from Script.Modules.action import Action

    if action.params.get("record_absence", False):
        from Script.System.Education_System import class_ai

        class_ai.settle_absent(actor)
    constant.handle_state_machine_data[action.params["state_machine_id"]](actor)
    # 状态机已提交响应行动时，由该待办负责结算一次。
    if runtime.scheduler.contains(actor):
        return None
    character = cache_control.cache.character_data[actor]
    # 仅更新需求的状态机仍保持闲置，按原节奏等待后再选择。
    if character.behavior.behavior_id == constant.Behavior.SHARE_BLANKLY:
        return Action(constant.Behavior.WAIT, 5, actor, state=constant.CharacterStatus.STATUS_WAIT)
    return Action.from_character(character)


def _prepare_group_action(runtime, actor: int, action):
    """输入执行器、角色编号和 Action，落实群交操作；返回实际 Action。"""
    from Script.Core import cache_control, constant
    from Script.Modules.action import Action
    from Script.Design.handle_npc_ai_in_h import execute_group_action

    character = cache_control.cache.character_data[actor]
    continued = character.behavior.behavior_id == constant.Behavior.WAIT
    execute_group_action(actor, action)
    # 已有等待沿用原先的继续语义，跳过一次性的行为结算。
    if continued:
        return Action(constant.Behavior.WAIT, 5, character.target_character_id, state=constant.CharacterStatus.STATUS_WAIT, continued=True)
    return Action.from_character(character)


def _finish_current(runtime, actor: int, action):
    """输入执行器、角色编号和 Action，收尾当前行为；返回已消费的 None。"""
    runtime.finish_current(actor, runtime.scheduler.now)
    return None


# 准备动作按编号注册，调度器只传递统一的 Action。
_PREPARERS = {
    "prepare_npc_action": _prepare_npc_action,
    "group_join": _prepare_group_action,
    "group_fill": _prepare_group_action,
    "finish_current": _finish_current,
}


def prepare_action(runtime, actor: int, action):
    """输入执行器、角色编号和 Action，返回可结算的 Action；操作已完成时返回 None。"""
    prepare = _PREPARERS.get(action.behavior_id)
    return action if prepare is None else prepare(runtime, actor, action)
