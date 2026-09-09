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
    from Script.Core import cache_control
    from Script.Modules.action import Action
    from Script.Modules.group_intent import execute_group_action

    execute_group_action(actor, action)
    return Action.from_character(cache_control.cache.character_data[actor])


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
    from Script.Modules.action import Action

    prepare = _PREPARERS.get(action.behavior_id)
    if prepare is None:
        return action
    prepared = prepare(runtime, actor, action)
    if prepared is not None:
        prepared.followups = action.followups + prepared.followups
        if action.after is not None:
            prepared.after = action.after
    else:
        pending = runtime.scheduler.pending(actor)
        if pending is not None and isinstance(pending.item, Action):
            # 响应先执行，再执行准备请求附带的后续；回调交给响应负责。
            pending.item.followups += action.followups
            if action.after is not None:
                pending.item.after = action.after
        else:
            # 无响应时准备操作已经完成，后续进入队列，收尾回调执行一次。
            for following in action.followups:
                runtime.enqueue(actor, following)
            if action.after is not None:
                runtime.finish_action(actor, action.after)
    return prepared
