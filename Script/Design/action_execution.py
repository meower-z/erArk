"""执行行动之前的准备步骤。

有些行动在执行前要先跑一段游戏逻辑才知道实际要做什么：NPC AI 选中的不是行动本身，而是一个"状态机"编号
（一段会替 NPC 决定并写入行动的原有代码）；要先运行它，实际行动才会写在角色的 Behavior（记录"正在做什么"的对象，见 Script/Modules/action.py）上。
加入群交（多人 H）的操作同样要先执行，才知道该角色实际做什么。

本模块两端各提供一个函数：state_machine_action 把状态机编号装进行动编号为 prepare_npc_action 的 Action，供 NPC AI 返回给调度器；
prepare_action 在执行时按行动编号找到对应的准备函数，运行后把角色 Behavior 上的实际行动读回来，作为要执行的 Action。没有准备步骤的行动原样返回。

准备过程中游戏逻辑可能为该角色提交一条立即执行的新待办（game_actions.py 称之为"强制后续"）。
此时 game_actions.Runtime.execute 放弃本次行动（返回 0 分钟），改为执行那条待办。
"""

from Script.Modules.action import Action


def state_machine_action(actor: int, state_machine_id: int, record_absence: bool = False) -> Action:
    """输入角色、状态机编号及缺课记录要求，返回交给执行侧准备的 Action。"""
    return Action("prepare_npc_action", 0, actor, params={"state_machine_id": state_machine_id, "record_absence": record_absence})


def _prepare_npc_action(runtime, actor: int, action):
    """输入执行器、角色编号和 Action，落实状态机；返回实际 Action。"""
    from Script.Core import cache_control, constant
    from Script.Modules.action import STATE

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
