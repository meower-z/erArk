"""
gameplay_resolution 的行动前检查
================================
干员每次结算（character_behavior.character_behavior）开头跑行动前检查：无法自由移动、助理、跟随、H 状态与无意识。
这些检查写缓存，接着的选择要读检查的结果。
所以在内核里，本回合到期的干员选行动时，before_pick（PickNextAction 输入钩子）先跑检查，npc_action_choice 再选行动。
检查之后这名干员的第一次结算跳过这些检查。没经过 before_pick 的结算照旧在开头跑检查，
例如回合末 npc_passes.run_npc_passes 里的结算。
计划队列的输入钩子在外层，它答出队首时 before_pick 不跑。
疲劳与它引出的收场是事件（events），不在这里。
"""

import datetime

from Script.Core import cache_control, game_type
from Script.Design import instuct_judege
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_checked: set[int] = set()
""" 选行动时已跑过检查、下一次结算要跳过检查的干员 """


def forget() -> None:
    """读档、新周目或内核出错后，丢掉选行动时已跑过检查的干员记录"""
    _checked.clear()


@core.input_hook(core.pick_next_action)
def before_pick(who: str) -> tuple[str]:
    """
    PickNextAction 输入钩子：本回合到期的干员在选行动之前跑行动前检查，并记进 _checked。
    行为的开始时间还没设过（年份不大于 1）时，先设为玩家行动的开始。
    玩家、死亡的干员、回合外与没到期的干员原样放行。
    Keyword arguments:
    who -- 角色键
    Return arguments:
    tuple -- 原样交给内层的参数
    """
    if who == actions.PLAYER:
        return (who,)
    character_id = int(who)
    turn = actions._turn
    character_data = cache.character_data[character_id]
    if (
        turn is None
        or character_data.dead
        or not actions.needs_pass(character_id)
    ):
        return (who,)
    if character_data.behavior.start_time.year <= 1:
        instuct_judege.init_character_behavior_start_time(
            character_id, turn.pl_start
        )
    _run_checks(character_id, turn.pl_start)
    _checked.add(character_id)
    return (who,)


def run_npc_pre_behavior_checks(
    character_id: int, pl_start_time: datetime.datetime
) -> None:
    """
    干员结算开头的行动前检查，由 character_behavior.character_behavior 调用。干员在 _checked 里时跳过检查，
    并把它移出 _checked
    Keyword arguments:
    character_id -- 角色id
    pl_start_time -- 玩家当前行动的开始时间
    """
    if character_id in _checked:
        _checked.discard(character_id)
        return
    _run_checks(character_id, pl_start_time)


def _run_checks(character_id: int, pl_start_time: datetime.datetime) -> None:
    """
    跑行动前检查（handle_npc_ai.run_npc_pre_behavior_checks）：无法自由移动、助理、跟随、H 状态与无意识
    Keyword arguments:
    character_id -- 角色id
    pl_start_time -- 玩家当前行动的开始时间
    """
    from Script.Design import handle_npc_ai

    handle_npc_ai.run_npc_pre_behavior_checks(character_id, pl_start_time)
