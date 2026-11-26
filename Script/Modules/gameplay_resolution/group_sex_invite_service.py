"""
群交邀请服务（group_sex_invite_service）
========================================
提供群交可邀请干员名单筛选，以及发起或取消群交邀请的逻辑。
本模块不导入 Script.UI 与 Script.Settle。
"""

from collections.abc import Collection
from types import FunctionType

from Script.Core import constant, get_text
from Script.Design import handle_premise
from Script.Modules.domains import activity, flags, identity, modes, roster

_: FunctionType = get_text._
""" 翻译函数。 """


def invite_candidates(
    scene_ids: Collection[int],
) -> tuple[list[int], list[int]]:
    """
    筛选不在当前场景中且未疲劳的可邀请干员名单，并标出已受邀角色。
    课堂模式下按入课门槛筛选，必修学生跳过前置修习检查。
    普通群交以 settle_hypnosis=False 仅判实行值而不扣除催眠代价。
    Keyword arguments:
    scene_ids -- Collection[int]，玩家当前场景中的角色编号集合
    Return arguments:
    tuple[list[int], list[int]] -- (可邀请角色编号列表, 其中已受邀角色编号列表)
    """
    from Script.Design import instuct_judege
    from Script.System.Education_System import sex_class_handle

    npc_ids = list(roster.active_sorted())
    must_attend = (
        sex_class_handle.get_must_attend_set() if modes.sex_class() else set()
    )
    candidates = []
    invited = []
    for chara_id in npc_ids:
        if chara_id == 0 or chara_id in scene_ids:
            continue
        if modes.sex_class():
            if not sex_class_handle.judge_can_join_sex_class(
                chara_id, check_course=chara_id not in must_attend
            ):
                continue
        elif not instuct_judege.calculation_instuct_judege(
            0,
            chara_id,
            _("群交"),
            not_draw_flag=True,
            settle_hypnosis=False,
        )[0]:
            continue
        if handle_premise.handle_self_exhausted(chara_id):
            continue
        if handle_premise.handle_self_now_go_to_join_group_sex(chara_id):
            invited.append(chara_id)
        candidates.append(chara_id)
    return candidates, invited


def invite(character_id: int) -> str:
    """
    对指定角色执行群交邀请或取消已发出的邀请，并返回界面提示文本。
    依次检查状态异常、已受邀取消与过于疲劳，普通群交随后再判一次并结算催眠代价。
    通过后置受邀标志与二段行为，并打断当前行动排入前往玩家位置的移动或五分钟等待。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    str -- 供面板显示的邀请结果提示文本
    """
    from Script.Design import instuct_judege, second_behavior
    from Script.Modules.gameplay_resolution import plan_queue
    from Script.Modules.npc_action_choice import choice

    name = identity.of(character_id).name
    if not handle_premise.handle_normal_24567(character_id):
        return _("***{0}状态异常，无法召集***\n").format(name)
    if flags.get(character_id, "go_to_join_group_sex"):
        flags.set(character_id, go_to_join_group_sex=False)
        plan_queue.plan_next(
            character_id,
            constant.Behavior.WAIT,
            5,
            state=constant.CharacterStatus.STATUS_WAIT,
            fields={"sp_flag.wait_flag": False},
            interrupt=True,
        )
        return _("\n已取消对{0}的群交邀请，{0}不会来这里参加群交了\n").format(
            name
        )
    if handle_premise.handle_self_exhausted(character_id):
        return _("***{0}过于疲劳，无法参加群交***\n").format(name)
    if (
        not modes.sex_class()
        and not instuct_judege.calculation_instuct_judege(
            0, character_id, _("群交"), not_draw_flag=True
        )[0]
    ):
        return _("\n{0}拒绝了群交邀请\n").format(name)
    flags.set(character_id, go_to_join_group_sex=True)
    second_behavior.character_get_second_behavior(
        character_id, "be_invited_join_group_sex"
    )
    to_dr = activity.position(0)
    minutes = choice.route_minutes(character_id, to_dr)
    if minutes > 0:
        plan_queue.plan_next(
            character_id,
            constant.Behavior.MOVE,
            minutes,
            fields={"action_info.follow_wait_time": 0},
            move={"to": list(to_dr), "show": True},
            interrupt=True,
        )
    else:
        plan_queue.plan_next(
            character_id,
            constant.Behavior.WAIT,
            5,
            state=constant.CharacterStatus.STATUS_WAIT,
            interrupt=True,
        )
    return _("\n已邀请{0}来这里参加群交\n").format(name)
