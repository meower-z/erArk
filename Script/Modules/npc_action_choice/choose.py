"""
npc_action_choice 的选择：干员选下一个行动
==========================================
choose 由 handle_npc_ai.choose_state_machine 按目标与前提选出状态机，再让状态机交回计划（choice.Plan）。
开始行动的是 gameplay_resolution 的 npc_start，它在行动开始时把计划写进缓存。
选择代码里还有少数写缓存的地方，例如目睹 H 的状态机（character_see_h_and_move_to_dormitory）。
干员到期且空闲时，npc_hook 在它的 PickNextAction 里调用 choose。
"""

from Script.Design import handle_npc_ai, handle_state_machine
from Script.Modules.npc_action_choice import choice


def choose(character_id: int) -> "choice.Choice | None":
    """
    干员选下一个行动，只读缓存
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    Choice | None -- 选出的状态机与计划；角色在H中、不选新行动时为 None
    """
    state_machine_id = handle_npc_ai.choose_state_machine(character_id)
    if state_machine_id is None:
        return None
    if not state_machine_id:
        return choice.Choice(0, None)
    return choice.Choice(
        state_machine_id,
        handle_state_machine.plan_of(state_machine_id, character_id),
    )
