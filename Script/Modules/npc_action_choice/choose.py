"""
npc_action_choice 的选择：干员选下一个行动
==========================================
choose 由 handle_npc_ai.choose_state_machine 按目标与前提选出状态机，再让状态机交回计划（choice.Plan），
交回计划给出的内核行动。选择只读缓存；行动开始时 gameplay_resolution 才把它写进缓存。
没有可选的行动（角色在H中，或没有目标成立）时，干员发呆到下一次 Tick。
"""

from Script.Core import constant
from Script.Design import handle_npc_ai, handle_state_machine
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, intent
from Script.StateMachine import default as state_machines

MACHINES = state_machines
""" 状态机模块：导入本模块时一并导入，它的装饰器 add_state_machine 把各状态机登记进 handle_state_machine.plans """

TICK_MINUTES = 5
""" Tick 的间隔分钟数 """


def choose(character_id: int) -> core.Action:
    """
    干员选下一个行动，只读缓存
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    Action -- 选出的行动；没有可选的行动时为发呆到下一次 Tick
    """
    state_machine_id = handle_npc_ai.choose_state_machine(character_id)
    if state_machine_id is None:
        return blank(character_id)
    return handle_state_machine.plan_of(state_machine_id, character_id).action()


def blank(character_id: int) -> core.Action:
    """
    发呆到下一次 Tick（上一次 Tick 之后 5 分钟），至少 1 分钟
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    Action -- 发呆的行动
    """
    game = core.state()
    ticked = game.data.get(actions.TICKED)
    if not isinstance(ticked, int):
        ticked = game.clock
    return intent.behavior_action(
        character_id,
        {
            "behavior_id": constant.Behavior.SHARE_BLANKLY,
            "minutes": max(1, ticked + TICK_MINUTES - game.clock),
            "target": character_id,
            "state": constant.CharacterStatus.STATUS_ARDER,
        },
    )
