"""
gameplay_resolution 的干员行动开始：把 npc_action_choice 选出的计划写进缓存
============================================================================
状态机交回计划（npc_action_choice.choice.Plan）。run_plan 按计划记下的顺序写入角色数据、寻路移动、显示文字、
调用结算函数。
start_plan 执行计划，再套用幼年阶段的门。start_choice 开始选出的状态机，并让开始的行为至少 1 分钟。
干员在内核的 PickNextAction 里选出的行动由 hold 留下，到它的结算行动开始时由 start_choice 取用。
导入本模块时，start_plan 登记为 handle_state_machine.starter。
"""

import datetime

from Script.Core import cache_control, constant, game_type
from Script.Design import child_stage_gate, game_time, handle_state_machine
from Script.Modules.npc_action_choice import choice
from Script.StateMachine import default as state_machine_default
from Script.UI.Moudle import draw

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_held: "dict[int, choice.Choice]" = {}
""" 干员在 PickNextAction 里选出、还没开始的行动：角色id -> 选择 """


def forget() -> None:
    """读档、新周目或内核出错后，丢掉干员在 PickNextAction 里选出、还没开始的行动"""
    _held.clear()


def hold(character_id: int, chosen: "choice.Choice") -> None:
    """
    留下干员在 PickNextAction 里选出的行动，到它的结算开始时取用
    Keyword arguments:
    character_id -- 角色id
    chosen -- 选出的状态机与计划
    """
    _held[character_id] = chosen


def held_state_machine(character_id: int) -> int | None:
    """
    干员留下的选择里的状态机id
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int | None -- 状态机id，0 为没有可做的行动，没有留下选择时为 None
    """
    chosen = _held.get(character_id)
    return None if chosen is None else chosen.state_machine_id


def drop(character_id: int) -> None:
    """
    丢掉干员留下的选择。干员的一次结算之后调用，结算没取用的选择不留到下一次结算
    Keyword arguments:
    character_id -- 角色id
    """
    _held.pop(character_id, None)


def start_plan(character_id: int, plan: "choice.Plan | None") -> None:
    """
    按计划的顺序执行，然后套用幼年阶段的门
    Keyword arguments:
    character_id -- 角色id
    plan -- 状态机交回的计划；没有计划的状态机自己结算过了
    """
    if plan is not None:
        run_plan(plan)
    # 状态机选出的H类行为若涉及幼年阶段角色，则换成发呆
    if child_stage_gate.blocks_behavior(character_id):
        child_stage_gate.reset_to_idle(character_id)


def run_plan(plan: "choice.Plan") -> None:
    """
    按计划记下的顺序写入角色数据、寻路移动、显示文字、调用结算函数
    Keyword arguments:
    plan -- 计划
    """
    character_id = plan.character_id
    for op in plan.ops:
        match op:
            case ("set", int(who), str(path), value):
                *parents, last = path.split(".")
                node: object = cache.character_data[who]
                for name in parents:
                    node = getattr(node, name)
                setattr(node, last, value)
            case ("move", list(scene), bool(show_info_flag)):
                state_machine_default.general_movement_module(
                    character_id, scene, show_info_flag=show_info_flag
                )
            case ("draw", str(text), bool(wait), str() | None as style):
                now_draw = draw.WaitDraw() if wait else draw.NormalDraw()
                now_draw.text = text
                if style is not None:
                    now_draw.style = style
                now_draw.draw()
            case ("effect", settle, tuple(args), dict(kwargs)) if callable(
                settle
            ):
                settle(*args, **kwargs)
            case _:
                raise ValueError(f"计划里有不认识的一步：{op!r}")


def schedule_surgery(doctor_id: int, patient: object) -> None:
    """
    扣除手术资源并给患者安排这位医生的手术；资源不足时什么都不改
    Keyword arguments:
    doctor_id -- 医生的角色id
    patient -- 患者（MedicalPatient）
    """
    from Script.System.Medical_System import medical_constant, medical_service

    assert isinstance(patient, medical_constant.MedicalPatient)
    if not medical_service.consume_surgery_resources(
        patient, cache.rhodes_island
    ):
        return
    patient.assigned_hospital_doctor_id = doctor_id
    patient.last_surgery_result = "scheduled"
    patient.surgery_blocked_resource = None
    patient.surgery_blocked = False
    cache.character_data[doctor_id].work.surgery_patient_id = patient.patient_id


def start_choice(
    character_id: int,
    state_machine_id: int | None,
    now_time: datetime.datetime,
) -> None:
    """
    开始干员选出的状态机。
    state_machine_id 为 None 时，干员加进本回合已结算完的角色（cache.over_behavior_character）。
    为 0 时，行为的开始时间不早于 now_time 则干员本回合结算完，否则行为的开始时间推后 1 分钟。
    其余情况下，留下的选择是同一个状态机时开始留下的计划，否则调用 constant.handle_state_machine_data 里登记的入口。
    开始之后，时长不到 1 分钟的行为改成 1 分钟。
    Keyword arguments:
    character_id -- 角色id
    state_machine_id -- 选出的状态机id，0 为没有可做的行动，None 为干员在H中、不选新行动
    now_time -- 当前时间
    """
    if state_machine_id is None:
        cache.over_behavior_character.add(character_id)
        return
    character_data = cache.character_data[character_id]
    if not state_machine_id:
        start_time = character_data.behavior.start_time
        if game_time.judge_date_big_or_small(start_time, now_time):
            cache.over_behavior_character.add(character_id)
        else:
            character_data.behavior.start_time = game_time.get_sub_date(
                minute=1, old_date=start_time
            )
        return
    chosen = _held.pop(character_id, None)
    if chosen is not None and chosen.state_machine_id == state_machine_id:
        start_plan(character_id, chosen.plan)
    else:
        constant.handle_state_machine_data[state_machine_id](character_id)
    # 保证AI选出的行动至少消耗1分钟：时长为0或负数的行动会在时间结算中被直接抹除且效果全部跳过，
    # 若前提未变化则AI下一轮会重复选择同一行动，导致NPC行为循环永不收敛（死循环）
    if character_data.behavior.duration <= 0:
        character_data.behavior.duration = 1


handle_state_machine.starter = start_plan
