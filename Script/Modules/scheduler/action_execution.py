"""按行动编号准备实际行为；准备操作不进入角色的 Behavior。"""


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
    from Script.Core import cache_control, constant
    from Script.Design import game_time
    from Script.Modules.scheduler.action import Action
    from Script.Design.handle_npc_ai_in_h import execute_group_action

    character = cache_control.cache.character_data[actor]
    # 闲置角色由群交操作安排等待；已有行为的角色延续剩余时间，不重复结算。
    idle = character.behavior.behavior_id == constant.Behavior.SHARE_BLANKLY
    execute_group_action(actor, action)
    if idle:
        return Action.from_character(character)
    result = Action.from_character(character, continued=True)
    end = game_time.get_sub_date(minute=character.behavior.duration, old_date=character.behavior.start_time)
    result.duration = max(game_time.elapsed_minutes(runtime.scheduler.now, end), 1)
    return result


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
