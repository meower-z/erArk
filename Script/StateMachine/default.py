"""角色状态机函数（各自用 add_state_machine 按 id 注册），以及通用移动模块 general_movement_module 与放弃当天体检的
give_up_today_health_check"""

from __future__ import annotations

import os
import random
from types import FunctionType
from typing import TYPE_CHECKING
from Script.Config import game_config, normal_config
from Script.Design import (
    handle_state_machine,
    character_move,
    map_handle,
    handle_premise,
    handle_npc_ai,
    basement,
)
from Script.Core import get_text, cache_control, game_type, constant
from Script.Modules.domains import abilities, action_info, economy, h_state
from Script.Modules.domains import kitchen, maintenance, modes, production
from Script.UI.Moudle import draw
from Script.Modules.domains import body_manage, inventory

if TYPE_CHECKING:
    from Script.Modules.npc_action_choice import choice

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1


def general_movement_module(
    character_id: int, target_scene: list, show_info_flag: bool = True
) -> bool:
    """
    通用移动模块\n
    Keyword arguments:\n
    character_id -- 角色id\n
    target_scene -- 寻路目标场景(在地图系统下的绝对坐标)\n
    show_info_flag -- 是否显示移动信息，默认为True
    """
    character_data: game_type.Character = cache.character_data[character_id]
    character_data.target_character_id = character_id
    target_scene_str = map_handle.get_map_system_path_str_for_list(target_scene)
    move_path, move_time = _movement_leg(character_id, target_scene)
    # 寻路正常时
    if move_time > 0:
        character_data.behavior.move_final_target = target_scene
        character_data.behavior.behavior_id = constant.Behavior.MOVE
        character_data.behavior.move_target = move_path
        character_data.behavior.duration = move_time
        character_data.state = constant.CharacterStatus.STATUS_MOVE
        if show_info_flag:
            _draw_move_intent(character_id, target_scene_str)
        return True
    # 寻路失败时
    else:
        character_data.behavior.behavior_id = constant.Behavior.WAIT
        character_data.behavior.duration = 1
        character_data.state = constant.CharacterStatus.STATUS_WAIT
        return False


def _movement_leg(character_id: int, target_scene: list) -> tuple[list, int]:
    """
    寻路：本段移动到的位置与用时（非中文语言环境下先把目标坐标换回中文）
    Keyword arguments:
    character_id -- 角色id
    target_scene -- 寻路目标场景(在地图系统下的绝对坐标)，会被就地换成中文
    Return arguments:
    tuple -- 本段移动到的位置、用时（寻路失败时不大于0）
    """
    from Script.Config import normal_config

    target_scene_str = map_handle.get_map_system_path_str_for_list(target_scene)
    # 非中文语言环境下特殊处理
    if normal_config.config_normal.language != "zh_CN":
        if target_scene_str not in map_handle.scene_path_edge:
            for i in range(len(target_scene)):
                if target_scene[i] == _("中枢") or target_scene[i] == _(
                    "控制中枢"
                ):
                    target_scene[i] = "中枢"
                else:
                    target_scene[i] = _(
                        target_scene[i], revert_translation=True
                    )
    _move_type, _path, move_path, move_time = character_move.character_move(
        character_id, target_scene
    )
    return move_path, move_time


def _draw_move_intent(character_id: int, target_scene_str: str) -> None:
    """
    角色和玩家位于同一地点、NPC移动提示未屏蔽时，显示角色打算前往的地点
    Keyword arguments:
    character_id -- 角色id
    target_scene_str -- 目标场景的路径字符串
    """
    character_data: game_type.Character = cache.character_data[character_id]
    if (
        character_data.position == cache.character_data[0].position
        and normal_config.system_setting.draw_setting[8] == 1
    ):
        now_scene_data = cache.scene_data[target_scene_str]
        now_draw = draw.NormalDraw()
        now_draw.text = _("{0}打算前往{1}\n").format(
            character_data.name, now_scene_data.scene_name
        )
        now_draw.draw()


def plan_movement(character_id: int, target_scene: list) -> None:
    """
    结算途中用的通用移动：把第一段移动（寻路失败时等待1分钟）排进角色的计划队列，打断角色当前的行动
    Keyword arguments:
    character_id -- 角色id
    target_scene -- 寻路目标场景(在地图系统下的绝对坐标)
    """
    from Script.Modules.gameplay_resolution import plan_queue

    target_scene_str = map_handle.get_map_system_path_str_for_list(target_scene)
    move_path, move_time = _movement_leg(character_id, target_scene)
    if move_time <= 0:
        plan_queue.plan_next(
            character_id,
            constant.Behavior.WAIT,
            1,
            target=character_id,
            state=constant.CharacterStatus.STATUS_WAIT,
            interrupt=True,
        )
        return
    _draw_move_intent(character_id, target_scene_str)
    plan_queue.plan_next(
        character_id,
        constant.Behavior.MOVE,
        move_time,
        target=character_id,
        state=constant.CharacterStatus.STATUS_MOVE,
        interrupt=True,
        fields={
            "behavior.move_target": move_path,
            "behavior.move_final_target": target_scene,
        },
    )


@handle_state_machine.add_state_machine(constant.StateMachine.WAIT_5_MIN)
def character_wait_5_min(character_id: int) -> choice.Plan:
    """
    等待5分钟
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.WAIT)
    plan.set("behavior.duration", 5)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    plan.set("sp_flag.wait_flag", False)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.WAIT_10_MIN)
def character_wait_10_min(character_id: int) -> choice.Plan:
    """
    等待10分钟
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.WAIT)
    plan.set("behavior.duration", 10)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.WAIT_30_MIN)
def character_wait_30_min(character_id: int) -> choice.Plan:
    """
    等待30分钟，并取消跟随状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.WAIT)
    plan.set("behavior.duration", 30)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    plan.set("sp_flag.is_follow", 0)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_DORMITORY)
def character_move_to_dormitory(character_id: int) -> choice.Plan:
    """
    移动至所在宿舍
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    # 还没有宿舍时先原地等1分钟，开始时分配宿舍，下一次再走过去
    if character_data.dormitory == "无":
        plan.kind("assign_dormitory")
        plan.set("target_character_id", character_id)
        plan.set("behavior.behavior_id", constant.Behavior.WAIT)
        plan.set("behavior.duration", 1)
        plan.set("state", constant.CharacterStatus.STATUS_WAIT)
        return plan
    target_scene = map_handle.get_map_system_path_for_str(
        character_data.dormitory
    )
    plan.move(target_scene)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.SLEEP)
def character_sleep(character_id: int) -> choice.Plan:
    """
    睡觉
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SLEEP)
    plan.set("behavior.duration", 480)
    plan.set("state", constant.CharacterStatus.STATUS_SLEEP)
    plan.set("sp_flag.tired", False)

    # 如果是助理并开启了同居服务
    if handle_premise.handle_is_assistant(
        character_id
    ) and handle_premise.handle_assistant_live_together_on(character_id):
        min_to_wake_time = int(
            (
                action_info.get(0, "wake_time")
                - character_data.behavior.start_time
            ).seconds
            / 60
        )
        # 如果开启了早安服务，则睡到早安服务时间前十分钟醒来
        # 距离醒来时间过近时时长可能算出0或负数，钳制到至少1分钟，避免行为循环无法收敛
        if handle_premise.handle_assistant_morning_salutation_on(character_id):
            plan.set("behavior.duration", max(min_to_wake_time - 10, 1))
        # 否则睡到和玩家同时醒来
        else:
            plan.set("behavior.duration", max(min_to_wake_time, 1))
    return plan


# @handle_state_machine.add_state_machine(constant.StateMachine.FOLLOW)
# def character_follow(character_id: int):
#     """
#     跟随玩家
#     Keyword arguments:
#     character_id -- 角色id
#     """
#     character_data: game_type.Character = cache.character_data[character_id]
#     character_data.talent[400] = 1


@handle_state_machine.add_state_machine(constant.StateMachine.REST)
def character_rest(character_id: int) -> choice.Plan:
    """
    休息
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.REST)
    plan.set("behavior.duration", 30)
    plan.set("state", constant.CharacterStatus.STATUS_REST)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_RAND_SCENE
)
def character_move_to_rand_scene(character_id: int) -> choice.Plan:
    """
    移动至随机场景
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    scene_list = list(cache.scene_data.keys())
    now_scene_str = map_handle.get_map_system_path_str_for_list(
        character_data.position
    )
    scene_list.remove(now_scene_str)
    target_scene = map_handle.get_map_system_path_for_str(
        random.choice(scene_list)
    )
    plan.move(target_scene, show_info_flag=False)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_DR_OFFICE)
def character_move_to_dr_office(character_id: int) -> choice.Plan:
    """
    移动至博士办公室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_dr_office = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Dr_Office"])
    )
    plan.move(to_dr_office)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_DR_ROOM)
def character_move_to_dr_room(character_id: int) -> choice.Plan:
    """
    移动至博士房间
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_dr_room = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Dr_room"])
    )
    plan.move(to_dr_room)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_TOILET)
def character_move_to_toilet(character_id: int) -> choice.Plan:
    """
    移动至洗手间
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("target_character_id", character_id)
    # 当前大区块
    now_position = character_data.position[0]
    # 是否已找到目标地点
    find_flag = False
    # 是否已选择另一个厕所
    if plan.get("action_info.find_another_toilet") != []:
        to_toilet = plan.get("action_info.find_another_toilet")
        find_flag = True
    # 男性直接选择男厕所
    elif character_data.sex == 0:
        to_toilet = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data["Toilet_Male"])
        )
    else:
        # 如果是助理，且开启了同居服务
        # 如果当前在控制中枢
        if (
            handle_premise.handle_is_assistant(character_id)
            and handle_premise.handle_assistant_live_together_on(character_id)
            and now_position in {"中枢", "控制中枢"}
        ):
            # 优先去博士房间
            to_toilet = map_handle.get_map_system_path_for_str(
                random.choice(constant.place_data["Dr_room"])
            )
            find_flag = True
        # 其他正常情况
        else:
            # 遍历所有女厕所，寻找当前大场景内的厕所
            for place in constant.place_data["Toilet_Female"]:
                if place.split(os.sep)[0] == now_position:
                    to_toilet = map_handle.get_map_system_path_for_str(place)
                    find_flag = True
                    break
            # 如果是在宿舍区的话，则寻找自己的宿舍
            else:
                if handle_premise.handle_in_dormitory_zone(character_id):
                    to_toilet = map_handle.get_map_system_path_for_str(
                        character_data.dormitory
                    )
                    find_flag = True
                # 如果还是没找到的话就随机选择一个女厕所
                else:
                    to_toilet = map_handle.get_map_system_path_for_str(
                        random.choice(constant.place_data["Toilet_Female"])
                    )
    # print(f"debug constant.place_data[\"Toilet_Female\"] = ",constant.place_data["Toilet_Female"])
    move_success = plan.move(to_toilet)
    # 如果成功移动到了厕所，则将该厕所记录在角色数据里，方便下次优先选择
    if move_success and find_flag:
        plan.set("action_info.find_another_toilet", to_toilet)
    # 如果就近的厕所因某些原因无法进入，则随机找一个另外的厕所
    if find_flag and not move_success:
        to_toilet = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data["Toilet_Female"])
        )
        move_success = plan.move(to_toilet)
        plan.set("action_info.find_another_toilet", to_toilet)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_KITCHEN)
def character_move_to_kitchen(character_id: int) -> choice.Plan:
    """
    移动至厨房
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_kitchen = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Kitchen"])
    )
    plan.move(to_kitchen)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_FOODSHOP)
def character_move_to_foodshop(character_id: int) -> choice.Plan:
    """
    移动至食物商店
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    # 没有指定餐厅id的就去食堂，有指定餐厅id的就去指定的餐厅
    if plan.get("action_info.eat_food_restaurant") == -1:
        to_foodshop = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data["Take_Food_Area"])
        )
    else:
        restaurant_id = plan.get("action_info.eat_food_restaurant")
        place_tag = game_config.config_restaurant[restaurant_id].tag_name
        to_foodshop = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data[place_tag])
        )
    move_success = plan.move(to_foodshop)
    # 如果没有去食堂且移动失败了，则将移动目标重定向为食堂
    if plan.get("action_info.eat_food_restaurant") != -1 and not move_success:
        plan.set("action_info.eat_food_restaurant", -1)
        to_foodshop = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data["Take_Food_Area"])
        )
        move_success = plan.move(to_foodshop)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_DINING_HALL
)
def character_move_to_dining_hall(character_id: int) -> choice.Plan:
    """
    移动至食堂
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_dining_hall = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Dining_hall"])
    )
    plan.move(to_dining_hall, show_info_flag=False)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_CLINIC)
def character_move_to_clinic(character_id: int) -> choice.Plan:
    """
    随机移动到门诊室（含急诊室）
    Keyword arguments:
    character_id -- 角色id
    """
    # 判断是否存在没有人的门诊室，存在的话优先去没有人的
    plan = handle_state_machine.new_plan(character_id)
    for Clinic_place in constant.place_data["Clinic"]:
        if list(cache.scene_data[Clinic_place].character_list) == []:
            to_clinic = map_handle.get_map_system_path_for_str(Clinic_place)
            break
    else:
        to_clinic = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data["Clinic"])
        )
    plan.move(to_clinic)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_PHYSICAL_EXAMINATION
)
def character_move_to_physical_examination(character_id: int) -> choice.Plan:
    """
    移动至体检科，体检科满员时放弃今天的体检
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_physical_examination_str = random.choice(
        constant.place_data["Physical_Examination"]
    )
    if map_handle.judge_scene_is_full(to_physical_examination_str):
        give_up_today_health_check(plan)
        return plan
    plan.move(
        map_handle.get_map_system_path_for_str(to_physical_examination_str)
    )
    return plan


def give_up_today_health_check(plan: choice.Plan) -> None:
    """
    放弃今天的体检：清空今天的体检安排并退出等待体检名单，原地发呆1分钟后回到日常行动，下一个体检日照常抽选
    Keyword arguments:
    plan -- 选行动的角色的计划
    """
    character_id = plan.character_id
    plan.set("action_info.health_check_today", 0)
    plan.kind("leave_exam_queue")
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_INPATIENT_DEPARTMENT
)
def character_move_to_inpatient_department(character_id: int) -> choice.Plan:
    """
    移动至住院部
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_inpatient_department = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Inpatient_Department"])
    )
    plan.move(to_inpatient_department)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_SURGERY_ROOM
)
def character_move_to_surgery_room(character_id: int) -> choice.Plan:
    """
    移动至手术室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_surgery_room = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Surgery_Room"])
    )
    plan.move(to_surgery_room)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_HR_OFFICE)
def character_move_to_hr_office(character_id: int) -> choice.Plan:
    """
    移动到人事部办公室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_hr_office = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["HR_Office"])
    )
    plan.move(to_hr_office)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_LIBRARY_OFFICE
)
def character_move_to_library_office(character_id: int) -> choice.Plan:
    """
    移动到图书馆办公室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_library_office = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Library_Office"])
    )
    plan.move(to_library_office)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_LIBRARY)
def character_move_to_library(character_id: int) -> choice.Plan:
    """
    移动到图书馆
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_library = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Library"])
    )
    plan.move(to_library)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_CLASS_ROOM
)
def character_move_to_class_room(character_id: int) -> choice.Plan:
    """
    移动到教室
    Plan 22 改造：目标教室改为由课表决定。现在的调用方有三个（Plan 24 并入工作链后）：
       教师的 210700 / 210705（去本节或马上那一节授课的教室）、学生的 210800（待赴实操课的教室）、
       娱乐 155「上课（无课时自习）」的自动 AI（学生没课时去自习，走下面的学生分支，多半落到随机回落）。
       课表查不到（没排课、非师生、旧存档）时回落"在已开放的理论教室里随机选一间"，不留死分支
       （Plan 27 §3.2：此前在全部 6 间里随机，开局只开理论教室一，挑中锁着的会走到门口一分钟一分钟地空转）
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Education_System import (
        class_ai,
        education_constant,
        schedule_handle,
    )

    target_room = ""
    # 预到岗：下一节是自己要上的性技实操课时，目标教室要查**下一节**而不是当前节次，
    # 否则学生会走去上一节课的教室（Plan 22 四期 §3.28.5）。
    #    只认学生岗（Plan 25 §3.6）：被任命为教师、课表还有残留的成年女儿不能被带去实操教室，和她自己的授课行来回拉扯
    next_classroom = class_ai.get_pending_sex_classroom(character_id)
    if next_classroom:
        target_room = next_classroom
    # 教师视角：反查全局课表；本节没课时看马上要开始的那一节（到岗时间与课间，第五轮）
    teaching = schedule_handle.get_now_teaching(character_id)
    if teaching is None:
        teaching = schedule_handle.get_upcoming_teaching(character_id)
    if target_room:
        pass
    elif teaching is not None:
        target_room = teaching["classroom"]
    else:
        # 学生视角：查个人课表，只有班级式课型才在教室里上；到岗时间看马上要开始的那一节（第五轮）
        now_course = schedule_handle.get_now_course(character_id)
        if now_course is None:
            now_course = schedule_handle.get_upcoming_course(character_id)
        if (
            now_course is not None
            and now_course["course_type"]
            in education_constant.CLASSROOM_COURSE_TYPE_SET
        ):
            target_room = now_course["classroom"]
    to_class_room = []
    if target_room:
        to_class_room = schedule_handle.get_classroom_position(target_room)
    if not to_class_room:
        open_room_list = schedule_handle.get_classroom_list(
            education_constant.COURSE_TYPE_THEORY
        )
        if open_room_list:
            to_class_room = schedule_handle.get_classroom_position(
                random.choice(open_room_list)
            )
    # 一间都没开时（理论教室一不在解锁表里、恒开放，实际不会发生）才退回在全部理论教室里随机
    if not to_class_room:
        to_class_room = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data["Class_Room"])
        )

    plan.move(to_class_room)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_TEACHER_OFFICE
)
def character_move_to_teacher_office(character_id: int) -> choice.Plan:
    """
    移动到教师办公室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Teacher_Office"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_GOLDEN_GAME_ROOM
)
def character_move_to_golden_game_room(character_id: int) -> choice.Plan:
    """
    移动至黄澄澄游戏室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Golden_Game_Room"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_NURSERY)
def character_move_to_nursery(character_id: int) -> choice.Plan:
    """
    移动至育儿室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Nursery"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_CLASSIC_MUSIC_ROOM
)
def character_move_to_classic_music_room(character_id: int) -> choice.Plan:
    """
    移动至夕照区音乐室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Classic_Musicroom"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_MODEN_MUSIC_ROOM
)
def character_move_to_moden_music_room(character_id: int) -> choice.Plan:
    """
    移动至现代音乐排练室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Modern_Musicroom"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_MULTIMEDIA_ROOM
)
def character_move_to_multimedia_room(character_id: int) -> choice.Plan:
    """
    移动至多媒体室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Multimedia_Room"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_PHOTOGRAPHY_STUDIO
)
def character_move_to_photography_studio(character_id: int) -> choice.Plan:
    """
    移动至摄影爱好者影棚
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Photography_Studio"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_AQUAPIT_EXPERIENTORIUM
)
def character_move_to_aquapit_experientorium(character_id: int) -> choice.Plan:
    """
    移动至大水坑快活体验屋
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Aquapit_Experientorium"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_BOARD_GAMES_ROOM
)
def character_move_to_board_games_room(character_id: int) -> choice.Plan:
    """
    移动至棋牌室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Board_Games_Room"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_FAIRY_BANQUET
)
def character_move_to_fairy_banquet(character_id: int) -> choice.Plan:
    """
    移动至糖果仙子宴会厅
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Fairy_Banquet"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_BAR)
def character_move_to_bar(character_id: int) -> choice.Plan:
    """
    移动至酒吧
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Bar"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_RESOURCE_EXCHANGE
)
def character_move_to_resource_exchange(character_id: int) -> choice.Plan:
    """
    移动至资源交易所
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Resource_Exchange"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_AVANT_GARDE_ARCADE
)
def character_move_to_avant_garde_arcade(character_id: int) -> choice.Plan:
    """
    移动至前卫街机厅
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Avant_Garde_Arcade"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_WALYRIA_CAKE_SHOP
)
def character_move_to_walyria_cake_shop(character_id: int) -> choice.Plan:
    """
    移动至瓦莱丽蛋糕店
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Walyria_Cake_Shop"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_STYLING_STUDIO
)
def character_move_to_styling_studio(character_id: int) -> choice.Plan:
    """
    移动至造型工作室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Styling_Studio"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_HAIR_SALON
)
def character_move_to_hair_salon(character_id: int) -> choice.Plan:
    """
    移动至理发店
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Hair_Salon"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_TEAHOUSE)
def character_move_to_teahouse(character_id: int) -> choice.Plan:
    """
    移动至山城茶馆
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Teahouse"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_CAFÉ)
def character_move_to_café(character_id: int) -> choice.Plan:
    """
    移动至哥伦比亚咖啡馆
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Café"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_LIGHT_STORE
)
def character_move_to_light_store(character_id: int) -> choice.Plan:
    """
    移动至花草灯艺屋
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Light_Store"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_PIZZERIA)
def character_move_to_pizzeria(character_id: int) -> choice.Plan:
    """
    移动至快捷连锁披萨店
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Pizzeria"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_SEVEN_CITIES_RESTAURANT
)
def character_move_to_seven_cities_restaurant(character_id: int) -> choice.Plan:
    """
    移动至七城风情餐厅
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Seven_Cities_Restaurant"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_BURGER)
def character_move_to_burger_joint(character_id: int) -> choice.Plan:
    """
    移动至约翰老妈汉堡店
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Burger"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_HEALTHY_DINER
)
def character_move_to_healthy_diner(character_id: int) -> choice.Plan:
    """
    移动至健康快餐店
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Healthy_Diner"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_LUNGMEN_EATERY
)
def character_move_to_lungmen_eatery(character_id: int) -> choice.Plan:
    """
    移动至龙门食坊
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_target = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Lungmen_Eatery"])
    )
    plan.move(to_target)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_SWIMMING_POOL
)
def character_move_to_swimming_pool(character_id: int) -> choice.Plan:
    """
    移动至游泳池
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_swimming_pool = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Swimming_Pool"])
    )
    plan.move(to_swimming_pool)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_GYM_ROOM)
def character_move_to_gym_room(character_id: int) -> choice.Plan:
    """
    移动至健身区
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_gym_room = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Gym"])
    )
    plan.move(to_gym_room)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_FOOT_BATH)
def character_move_to_foot_bath(character_id: int) -> choice.Plan:
    """
    移动至足浴区
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_foot_bath = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Foot_Bath"])
    )
    plan.move(to_foot_bath)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_SAUNA)
def character_move_to_sauna(character_id: int) -> choice.Plan:
    """
    移动至桑拿房
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_sauna = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Sauna"])
    )
    plan.move(to_sauna)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_SPA_ROOM)
def character_move_to_spa_room(character_id: int) -> choice.Plan:
    """
    移动至水疗房
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_spa_room = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Spa_Room"])
    )
    plan.move(to_spa_room)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_ONSEN)
def character_move_to_onsen(character_id: int) -> choice.Plan:
    """
    移动至温泉
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_onsen = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Onsen"])
    )
    plan.move(to_onsen)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_MAINTENANCE_DEPARTMENT
)
def character_move_to_maintenance_department(character_id: int) -> choice.Plan:
    """
    移动至运维部
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_maintenance_department = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Maintenance_Department"])
    )
    plan.move(to_maintenance_department)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_BLACKSMITH_SHOP
)
def character_move_to_blacksmith_shop(character_id: int) -> choice.Plan:
    """
    移动至铁匠铺
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_blacksmith_shop = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Blacksmith_Shop"])
    )
    plan.move(to_blacksmith_shop)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_POWER_DISPATCH
)
def character_move_to_power_dispatch(character_id: int) -> choice.Plan:
    """
    移动至动力控制室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_power_dispatch = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Power_Dispatch"])
    )
    plan.move(to_power_dispatch)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_DIPLOMATIC_OFFICE
)
def character_move_to_diplomatic_office(character_id: int) -> choice.Plan:
    """
    移动至外交官办公室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_diplomatic_office = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Diplomatic_Office"])
    )
    plan.move(to_diplomatic_office)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_HERB_GARDEN
)
def character_move_to_herb_garden(character_id: int) -> choice.Plan:
    """
    移动至药田
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_herb_garden = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Herb_Garden"])
    )
    plan.move(to_herb_garden)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_GREENHOUSE
)
def character_move_to_greenhouse(character_id: int) -> choice.Plan:
    """
    移动至温室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_greenhouse = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Greenhouse"])
    )
    plan.move(to_greenhouse)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_HUMILIATION_ROOM
)
def character_move_to_humiliation_room(character_id: int) -> choice.Plan:
    """
    移动至调教室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_humiliation_room = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Humiliation_Room"])
    )
    plan.move(to_humiliation_room)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_WARDEN_OFFICE
)
def character_move_to_warden_office(character_id: int) -> choice.Plan:
    """
    移动至监狱长办公室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    to_warden_office = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Warden_Office"])
    )
    plan.move(to_warden_office)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_REST_ROOM)
def character_move_to_rest_room(character_id: int) -> choice.Plan:
    """
    移动至休息室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    special_rest_room_list = []
    # 首先检测角色所属的势力与出身地是否有专属休息室
    chara_nation = character_data.relationship.nation
    nation_rest_room_tag = "Nation_" + str(chara_nation)
    if nation_rest_room_tag in constant.place_data:
        special_rest_room_list.extend(constant.place_data[nation_rest_room_tag])
    chara_birthplace = character_data.relationship.birthplace
    birthplace_rest_room_tag = "Birthplace_" + str(chara_birthplace)
    if birthplace_rest_room_tag in constant.place_data:
        special_rest_room_list.extend(
            constant.place_data[birthplace_rest_room_tag]
        )
    # 如果有专属休息室的话，有一半几率使用该休息室
    if len(special_rest_room_list) and random.randint(1, 2) == 1:
        to_rest_room = map_handle.get_map_system_path_for_str(
            random.choice(special_rest_room_list)
        )
    # 不使用专属休息室的话，检索当前角色所在的大场景里有没有休息室
    else:
        now_position = character_data.position[0]
        for place in constant.place_data["Rest_Room"]:
            if place.split(os.sep)[0] == now_position:
                if (
                    map_handle.judge_scene_accessible(place, character_id)
                    == "open"
                ):
                    to_rest_room = map_handle.get_map_system_path_for_str(place)
                    break
        # 没有的话再随机选择其他区块
        else:
            to_rest_room = map_handle.get_map_system_path_for_str(
                random.choice(constant.place_data["Rest_Room"])
            )

    plan.move(to_rest_room)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_RESTAURANT
)
def character_move_to_restaurant(character_id: int) -> choice.Plan:
    """
    移动至餐馆（随机某个正餐餐馆）
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]

    # 检索当前角色所在的大场景里有没有餐馆，没有的话再随机选择其他区块
    now_position = character_data.position[0]
    for place in constant.place_data["Restaurant"]:
        if place.split(os.sep)[0] == now_position:
            to_rest_room = map_handle.get_map_system_path_for_str(place)
            break
    else:
        to_rest_room = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data["Restaurant"])
        )

    plan.move(to_rest_room)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_MAINTENANCE_PLACE
)
def character_move_to_maintenance_place(character_id: int) -> choice.Plan:
    """
    移动至检修地点
    Keyword arguments:
    character_id -- 角色id
    """
    # 正常情况下
    plan = handle_state_machine.new_plan(character_id)
    place = maintenance.place_of(character_id)
    if place is not None:
        plan.move(map_handle.get_map_system_path_for_str(place))
    # 如果检修地点已不存在则取消检修状态
    else:
        plan.set("sp_flag.work_maintenance", False)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_PRODUCTION_WORKSHOP
)
def character_move_to_production_workshop(character_id: int) -> choice.Plan:
    """
    移动至生产车间
    Keyword arguments:
    character_id -- 角色id
    """

    # 如果已经属于某个车间，则直接选择该车间
    plan = handle_state_machine.new_plan(character_id)
    target_scene_str = ""
    for assembly_line_id, line in production.lines("assembly").items():
        if character_id == line["main"]:
            target_scene_name = f"assembly_line_{(str(assembly_line_id))}"
            target_scene_str = random.choice(
                constant.place_data[target_scene_name]
            )

    # 如果没有被分配到某个生产车间，则优先去没有人的，如果没有，则随机选择一个
    if not target_scene_str:
        empty_flag = False
        for target_scene_str in constant.place_data["Production_Workshop"]:
            close_type = map_handle.judge_scene_accessible(
                target_scene_str, character_id
            )
            if (
                list(cache.scene_data[target_scene_str].character_list) == []
                and close_type == "open"
            ):
                empty_flag = True
                break
        if not empty_flag:
            while 1:
                target_scene_str = random.choice(
                    constant.place_data["Production_Workshop"]
                )
                close_type = map_handle.judge_scene_accessible(
                    target_scene_str, character_id
                )
                if close_type == "open":
                    break
        assembly_line_id = int(target_scene_str[-1]) - 1

    to_production_workshop = map_handle.get_map_system_path_for_str(
        target_scene_str
    )
    plan.move(to_production_workshop)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_BATHZONE_LOCKER_ROOM
)
def character_move_to_bathzone_locker_room(character_id: int) -> choice.Plan:
    """
    移动至大浴场的更衣室
    Keyword arguments:
    character_id -- 角色id
    """

    plan = handle_state_machine.new_plan(character_id)
    to_locker_room = []
    # 直接检索大浴场的更衣室
    for place in constant.place_data["Locker_Room"]:
        if place.split(os.sep)[0] == "大浴场":
            to_locker_room = map_handle.get_map_system_path_for_str(place)
            break

    # 以防没有找到更衣室
    if to_locker_room != []:
        plan.move(to_locker_room)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_BATHZONE_REST_ROOM
)
def character_move_to_bathzone_rest_room(character_id: int) -> choice.Plan:
    """
    移动至大浴场的休息室
    Keyword arguments:
    character_id -- 角色id
    """

    plan = handle_state_machine.new_plan(character_id)
    to_rest_room = []
    # 直接检索大浴场的休息室
    for place in constant.place_data["Rest_Room"]:
        if place.split(os.sep)[0] == "大浴场":
            to_rest_room = map_handle.get_map_system_path_for_str(place)
            break

    # 以防没有找到休息室
    if to_rest_room != []:
        plan.move(to_rest_room, show_info_flag=False)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_TRAINING_LOCKER_ROOM
)
def character_move_to_training_locker_room(character_id: int) -> choice.Plan:
    """
    移动至训练场的更衣室
    Keyword arguments:
    character_id -- 角色id
    """

    plan = handle_state_machine.new_plan(character_id)
    to_locker_room = []
    # 直接检索训练场的更衣室
    for place in constant.place_data["Locker_Room"]:
        if place.split(os.sep)[0] == "训练":
            to_locker_room = map_handle.get_map_system_path_for_str(place)
            break

    # 以防没有找到更衣室
    if to_locker_room != []:
        plan.move(to_locker_room)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_BATH_ROOM)
def character_move_to_bath_room(character_id: int) -> choice.Plan:
    """
    移动至淋浴室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]

    # 检索当前角色所在的大场景里有没有淋浴室，没有的话再随机选择其他区块
    now_position = character_data.position[0]
    for place in constant.place_data["Bathroom"]:
        if place.split(os.sep)[0] == now_position:
            to_bath_room = map_handle.get_map_system_path_for_str(place)
            break
    else:
        to_bath_room = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data["Bathroom"])
        )

    plan.move(to_bath_room)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MOVE_TO_TRAINING_ROOM
)
def character_move_to_training_room(character_id: int) -> choice.Plan:
    """
    根据职业自动移动至对应训练室
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    if character_data.profession in {1, 5, 6, 8}:
        room_name = "Fight_Room"
    else:
        room_name = "Shoot_Room"

    to_training_room = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data[room_name])
    )

    plan.move(to_training_room)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MOVE_TO_PLAYER)
def character_move_to_player(character_id: int) -> choice.Plan:
    """
    移动至玩家位置
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    to_dr = cache.character_data[0].position
    _move_type, _path, move_path, _move_time = character_move.character_move(
        character_id, to_dr
    )
    move_flag = True  # flase的话就是等待
    if move_path == []:
        move_flag = False
    else:
        move_flag, _wait_flag, outcome = character_move.private_move_outcome(
            character_id, move_path
        )
        _settle_private_move(plan, outcome)
    # 最后决定是移动还是继续等待
    if move_flag:
        plan.set("action_info.follow_wait_time", 0)
        plan.move(to_dr)
    else:
        plan.set("state", constant.CharacterStatus.STATUS_WAIT)
        plan.set("behavior.behavior_id", constant.Behavior.WAIT)
        plan.set("behavior.duration", 5)
        plan.set(
            "action_info.follow_wait_time",
            plan.get("action_info.follow_wait_time") + (5),
        )
    return plan
    # if character_data.sp_flag.is_follow:
    #     print(f"debug {character_data.name}向玩家移动，当前跟随={character_data.sp_flag.is_follow}")


@handle_state_machine.add_state_machine(constant.StateMachine.CONTINUE_MOVE)
def character_continue_move(character_id: int) -> choice.Plan:
    """
    继续移动
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    # print(f"\n\ndebug 判断 {character_data.name} 继续移动")
    # 仅在有最终目标的情况下进行判断
    if character_data.behavior.move_final_target != []:

        # 如果还没有抵达最终目标地点
        if character_data.position != character_data.behavior.move_final_target:
            # print(f"debug {character_data.name} 还没有抵达最终目标地点:{character_data.behavior.move_final_target}")

            # 基础数据计算
            to_dr = cache.character_data[0].position
            _move_type, _path, move_path, move_time = (
                character_move.character_move(
                    character_id, character_data.behavior.move_final_target
                )
            )
            move_flag = True  # true的话就是移动
            wait_flag = False  # true的话就是等待

            if len(move_path) == 0:
                move_flag = False
                wait_flag = True

            # 如果是向玩家移动的话
            if move_flag and character_data.behavior.move_final_target == to_dr:
                # 进行私密跟随判断
                move_flag, wait_flag, outcome = (
                    character_move.private_move_outcome(character_id, move_path)
                )
                _settle_private_move(plan, outcome)
                # print(f"debug {character_data.name} 向玩家移动，move_flag = {move_flag}, wait_flag = {wait_flag}")

            if move_flag:
                plan.set("state", constant.CharacterStatus.STATUS_MOVE)
                plan.set("behavior.behavior_id", constant.Behavior.MOVE)
                plan.set("behavior.move_target", move_path)
                plan.set("behavior.duration", move_time)
                plan.set("action_info.follow_wait_time", 0)
            elif wait_flag:
                plan.set("state", constant.CharacterStatus.STATUS_WAIT)
                plan.set("behavior.behavior_id", constant.Behavior.WAIT)
                plan.set("behavior.duration", 5)
                plan.set(
                    "action_info.follow_wait_time",
                    plan.get("action_info.follow_wait_time") + (5),
                )
    return plan


def _settle_private_move(plan: choice.Plan, outcome: str) -> None:
    """
    私密房间前有要结算的结果时，开始时结算它（character_move.settle_private_move）
    Keyword arguments:
    plan -- 计划
    outcome -- character_move.private_move_outcome 交回的结果
    """
    if outcome:
        plan.kind("private_move")
        plan.arg("outcome", outcome)


@handle_state_machine.add_state_machine(
    constant.StateMachine.CHAT_RAND_CHARACTER
)
def character_chat_rand_character(character_id: int) -> choice.Plan:
    """
    角色和场景内玩家以外的随机角色聊天
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    target_id = handle_npc_ai.select_random_free_character(character_id)
    if target_id != -1:
        plan.set("behavior.behavior_id", constant.Behavior.CHAT)
        plan.set("behavior.duration", 10)
        plan.set("target_character_id", target_id)
        plan.set("state", constant.CharacterStatus.STATUS_CHAT)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.STROKE_RAND_CHARACTER
)
def character_stroke_rand_character(character_id: int) -> choice.Plan:
    """
    角色和场景内随机角色身体接触
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    target_id = handle_npc_ai.select_random_free_character(character_id)
    if target_id != -1:
        plan.set("behavior.behavior_id", constant.Behavior.STROKE)
        plan.set("behavior.duration", 10)
        plan.set("target_character_id", target_id)
        plan.set("state", constant.CharacterStatus.STATUS_STROKE)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.CHAT_TO_DR)
def character_chat_to_dr(character_id: int) -> choice.Plan:
    """
    角色和玩家聊天
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    target_id = 0
    plan.set("behavior.behavior_id", constant.Behavior.CHAT)
    plan.set("behavior.duration", 5)
    plan.set("target_character_id", target_id)
    plan.set("state", constant.CharacterStatus.STATUS_CHAT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.STROKE_TO_DR)
def character_stroke_to_dr(character_id: int) -> choice.Plan:
    """
    角色和玩家身体接触
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    target_id = 0
    plan.set("behavior.behavior_id", constant.Behavior.STROKE)
    plan.set("behavior.duration", 10)
    plan.set("target_character_id", target_id)
    plan.set("state", constant.CharacterStatus.STATUS_STROKE)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MAKE_COFFEE_TO_DR)
def character_make_coffee_to_dr(character_id: int) -> choice.Plan:
    """
    角色给玩家泡咖啡
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    target_id = 0
    plan.set("behavior.behavior_id", constant.Behavior.MAKE_COFFEE)
    plan.set("behavior.duration", 15)
    plan.set("target_character_id", target_id)
    plan.set("state", constant.CharacterStatus.STATUS_MAKE_COFFEE)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MAKE_COFFEE_ADD_TO_DR
)
def character_make_coffee_Add_to_dr(character_id: int) -> choice.Plan:
    """
    角色给玩家泡咖啡（加料）
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    target_id = 0
    plan.set("behavior.behavior_id", constant.Behavior.MAKE_COFFEE_ADD)
    plan.set("behavior.duration", 15)
    plan.set("target_character_id", target_id)
    plan.set("state", constant.CharacterStatus.STATUS_MAKE_COFFEE_ADD)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.SEE_H_AND_MOVE_TO_DORMITORY
)
def character_see_h_and_move_to_dormitory(character_id: int) -> choice.Plan:
    """
    目睹玩家和其他角色H：这一分钟先愣住，开始时把发现的结算（被发现面板与各方的后续行动）排进自己的计划队列
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    # 如果是关闭了隔间门的房间的话，则不会被看到
    if handle_premise.handle_place_inside_door_close(character_id):
        return plan
    plan.kind("see_h")
    plan.set("behavior.behavior_id", constant.Behavior.WAIT)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    plan.set("sp_flag.see_h_reaction_settled", True)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.SINGING)
def character_singing(character_id: int) -> choice.Plan:
    """
    唱歌
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SINGING)
    plan.set("behavior.duration", 10)
    plan.set("state", constant.CharacterStatus.STATUS_SINGING)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.PLAY_INSTRUMENT)
def character_play_instrument(character_id: int) -> choice.Plan:
    """
    角色演奏乐器
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.PLAY_INSTRUMENT)
    plan.set("behavior.duration", 30)
    plan.set("state", constant.CharacterStatus.STATUS_PLAY_INSTRUMENT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.ENTERTAIN_READ)
def character_entertain_read(character_id: int) -> choice.Plan:
    """
    角色娱乐：读书
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.UI.Panel import borrow_book_panel

    # 没借书就先借一本，并把借着的那本写进 behavior（与兴趣课读书共用，Plan 29 §3.2）；借不到就等 1 分钟
    if not borrow_book_panel.judge_can_get_read_book(character_id):
        plan.set("behavior.behavior_id", constant.Behavior.WAIT)
        plan.set("behavior.duration", 1)
        plan.set("state", constant.CharacterStatus.STATUS_WAIT)
        return plan
    plan.kind("read_book")
    plan.set("behavior.behavior_id", constant.Behavior.READ_BOOK)
    plan.set("state", constant.CharacterStatus.STATUS_READ_BOOK)
    plan.set("behavior.duration", 30)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.ENTERTAIN_SINGING)
def character_entertain_singing(character_id: int) -> choice.Plan:
    """
    娱乐：唱歌
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SINGING)
    plan.set("behavior.duration", 10)
    plan.set("state", constant.CharacterStatus.STATUS_SINGING)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_PLAY_CLASSIC_INSTRUMENT
)
def character_play_classic_instrument(character_id: int) -> choice.Plan:
    """
    娱乐：演奏传统乐器
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.PLAY_INSTRUMENT)
    plan.set("behavior.duration", 10)
    plan.set("state", constant.CharacterStatus.STATUS_PLAY_INSTRUMENT)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_PLAY_MODEN_INSTRUMENT
)
def character_play_moden_instrument(character_id: int) -> choice.Plan:
    """
    娱乐：演奏现代乐器
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.PLAY_INSTRUMENT)
    plan.set("behavior.duration", 10)
    plan.set("state", constant.CharacterStatus.STATUS_PLAY_INSTRUMENT)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_WATCH_MOVIE
)
def character_watch_movie(character_id: int) -> choice.Plan:
    """
    娱乐：看电影
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 120)
    plan.set("behavior.behavior_id", constant.Behavior.WATCH_MOVIE)
    plan.set("state", constant.CharacterStatus.STATUS_WATCH_MOVIE)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_PHOTOGRAPHY
)
def character_photography(character_id: int) -> choice.Plan:
    """
    娱乐：摄影
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.PHOTOGRAPHY)
    plan.set("state", constant.CharacterStatus.STATUS_PHOTOGRAPHY)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_PLAY_WATER
)
def character_play_water(character_id: int) -> choice.Plan:
    """
    娱乐：玩水
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.PLAY_WATER)
    plan.set("state", constant.CharacterStatus.STATUS_PLAY_WATER)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_PLAY_CHESS
)
def character_play_chess(character_id: int) -> choice.Plan:
    """
    娱乐：下棋
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 30)
    plan.set("behavior.behavior_id", constant.Behavior.PLAY_CHESS)
    plan.set("state", constant.CharacterStatus.STATUS_PLAY_CHESS)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_PLAY_MAHJONG
)
def character_play_mahjong(character_id: int) -> choice.Plan:
    """
    娱乐：打麻将
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.PLAY_MAHJONG)
    plan.set("state", constant.CharacterStatus.STATUS_PLAY_MAHJONG)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_PLAY_CARDS
)
def character_play_cards(character_id: int) -> choice.Plan:
    """
    娱乐：打牌
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.PLAY_CARDS)
    plan.set("state", constant.CharacterStatus.STATUS_PLAY_CARDS)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_REHEARSE_DANCE
)
def character_rehearse_dance(character_id: int) -> choice.Plan:
    """
    娱乐：排演舞剧
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 120)
    plan.set("behavior.behavior_id", constant.Behavior.REHEARSE_DANCE)
    plan.set("state", constant.CharacterStatus.STATUS_REHEARSE_DANCE)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_PLAY_ARCADE_GAME
)
def character_play_arcade_game(character_id: int) -> choice.Plan:
    """
    娱乐：玩街机游戏
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.PLAY_ARCADE_GAME)
    plan.set("state", constant.CharacterStatus.STATUS_PLAY_ARCADE_GAME)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_SWIMMING
)
def character_swimming(character_id: int) -> choice.Plan:
    """
    娱乐：游泳
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.SWIMMING)
    plan.set("state", constant.CharacterStatus.STATUS_SWIMMING)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_TASTE_WINE
)
def character_taste_wine(character_id: int) -> choice.Plan:
    """
    娱乐：品酒
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 30)
    plan.set("behavior.behavior_id", constant.Behavior.TASTE_WINE)
    plan.set("state", constant.CharacterStatus.STATUS_TASTE_WINE)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_TASTE_TEA
)
def character_taste_tea(character_id: int) -> choice.Plan:
    """
    娱乐：品茶
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 30)
    plan.set("behavior.behavior_id", constant.Behavior.TASTE_TEA)
    plan.set("state", constant.CharacterStatus.STATUS_TASTE_TEA)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_TASTE_COFFEE
)
def character_taste_coffee(character_id: int) -> choice.Plan:
    """
    娱乐：品咖啡
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 30)
    plan.set("behavior.behavior_id", constant.Behavior.TASTE_COFFEE)
    plan.set("state", constant.CharacterStatus.STATUS_TASTE_COFFEE)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_TASTE_DESSERT
)
def character_taste_dessert(character_id: int) -> choice.Plan:
    """
    娱乐：品尝点心
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 30)
    plan.set("behavior.behavior_id", constant.Behavior.TASTE_DESSERT)
    plan.set("state", constant.CharacterStatus.STATUS_TASTE_DESSERT)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_TASTE_FOOD
)
def character_taste_food(character_id: int) -> choice.Plan:
    """
    娱乐：品尝美食
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 30)
    plan.set("behavior.behavior_id", constant.Behavior.TASTE_FOOD)
    plan.set("state", constant.CharacterStatus.STATUS_TASTE_FOOD)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_TEND_EGGS
)
def character_tend_eggs(character_id: int) -> choice.Plan:
    """
    娱乐：照料卵（有可鉴定卵时：自己是保育员或无在班保育员在场则自己鉴定，有在班保育员在场则等待其鉴定；否则进行孵化）
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Pregnancy_System import egg_handle
    from Script.System.Pregnancy_System import pregnancy_constant

    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("target_character_id", character_id)
    # 鉴定优先级高于孵化，鉴定完成后同一时段的后续行动自然落入孵化行为
    if len(egg_handle.get_identifiable_eggs(character_id)):
        # 自己就是保育员时直接自己鉴定
        if (
            character_data.work.work_type
            == pregnancy_constant.NURSERY_WORKER_WORK_ID
        ):
            plan.set("behavior.duration", 30)
            plan.set("behavior.behavior_id", constant.Behavior.IDENTIFY_EGGS)
            plan.set("state", constant.CharacterStatus.STATUS_IDENTIFY_EGGS)
            _identify_eggs(plan, character_id)
        # 有处于工作时间内的保育员在场时，等待保育员前来鉴定（保育员的工作状态机会以最高优先级鉴定在场角色的卵）
        elif egg_handle.nursery_worker_on_duty_in_scene(character_id):
            plan.set("behavior.duration", 10)
            plan.set("behavior.behavior_id", constant.Behavior.WAIT)
            plan.set("state", constant.CharacterStatus.STATUS_WAIT)
        # 兜底：无在职保育员或保育员不在场时自己鉴定，保证卵不会永久滞留
        else:
            plan.set("behavior.duration", 30)
            plan.set("behavior.behavior_id", constant.Behavior.IDENTIFY_EGGS)
            plan.set("state", constant.CharacterStatus.STATUS_IDENTIFY_EGGS)
            _identify_eggs(plan, character_id)
    else:
        plan.set("behavior.duration", 60)
        plan.set("behavior.behavior_id", constant.Behavior.HATCH_EGGS)
        plan.set("state", constant.CharacterStatus.STATUS_HATCH_EGGS)
    return plan


def _identify_eggs(plan: choice.Plan, owner_id: int) -> None:
    """
    开始时由选行动的角色鉴定 owner_id 的卵（egg_handle.npc_identify_eggs_settle）
    Keyword arguments:
    plan -- 鉴定者的计划
    owner_id -- 持卵角色id
    """
    plan.kind("identify_eggs")
    plan.arg("owner_id", owner_id)


@handle_state_machine.add_state_machine(constant.StateMachine.WORK_NURSERY_CARE)
def character_work_nursery_care(character_id: int) -> choice.Plan:
    """
    工作：保育员照料育儿室——优先为在场角色（含自己）鉴定卵；无卵可鉴定时等权重照料孵化中的卵/照料婴儿
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Pregnancy_System import egg_handle

    character_data: game_type.Character = cache.character_data[character_id]
    # 优先级1：为在场角色（含自己）鉴定卵
    owner_id = egg_handle.find_identifiable_egg_owner_in_scene(character_id)
    if owner_id != -1:
        plan.set("target_character_id", owner_id)
        plan.set("behavior.duration", 30)
        plan.set("behavior.behavior_id", constant.Behavior.IDENTIFY_EGGS)
        plan.set("state", constant.CharacterStatus.STATUS_IDENTIFY_EGGS)
        # 鉴定的数据在开始时结算（未受精卵静默删除，受精卵进入孵化并通知玩家）
        _identify_eggs(plan, owner_id)
        return plan
    # 等权重行为池：照料孵化中的卵 / 照料婴儿
    action_list = []
    if egg_handle.any_hatching_eggs_exist():
        action_list.append("hatch")
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        character_data.position
    )
    scene_data = cache.scene_data[scene_path_str]
    baby_id_list = [
        i for i in scene_data.character_list if i and abilities.talent(i)[101]
    ]
    if len(baby_id_list):
        action_list.append("baby")
    if len(action_list):
        now_action = random.choice(action_list)
        if now_action == "hatch":
            plan.set("target_character_id", character_id)
            plan.set("behavior.duration", 60)
            plan.set("behavior.behavior_id", constant.Behavior.HATCH_EGGS)
            plan.set("state", constant.CharacterStatus.STATUS_HATCH_EGGS)
        else:
            baby_care_list = [
                (
                    constant.Behavior.HOLD_CHILD,
                    constant.CharacterStatus.STATUS_HOLD_CHILD,
                ),
                (
                    constant.Behavior.SING_CHILDREN_SONG,
                    constant.CharacterStatus.STATUS_SING_CHILDREN_SONG,
                ),
                (
                    constant.Behavior.NUIRSE_CHILD,
                    constant.CharacterStatus.STATUS_NUIRSE_CHILD,
                ),
                (
                    constant.Behavior.CHANGE_DIAPERS,
                    constant.CharacterStatus.STATUS_CHANGE_DIAPERS,
                ),
                (
                    constant.Behavior.TEACH_TALK,
                    constant.CharacterStatus.STATUS_TEACH_TALK,
                ),
                (
                    constant.Behavior.GIVE_TOY,
                    constant.CharacterStatus.STATUS_GIVE_TOY,
                ),
            ]
            now_behavior_id, now_state_id = random.choice(baby_care_list)
            plan.set("target_character_id", random.choice(baby_id_list))
            plan.set("behavior.duration", 30)
            plan.set("behavior.behavior_id", now_behavior_id)
            plan.set("state", now_state_id)
        return plan
    # 兜底：无事可做时短暂等待（前提门控下一般不会走到）
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 1)
    plan.set("behavior.behavior_id", constant.Behavior.WAIT)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_STYLE_HAIR
)
def character_style_hair(character_id: int) -> choice.Plan:
    """
    娱乐：修整发型
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.STYLE_HAIR)
    plan.set("state", constant.CharacterStatus.STATUS_STYLE_HAIR)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_FULL_BODY_STYLING
)
def character_full_body_styling(character_id: int) -> choice.Plan:
    """
    娱乐：全身造型服务
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 120)
    plan.set("behavior.behavior_id", constant.Behavior.FULL_BODY_STYLING)
    plan.set("state", constant.CharacterStatus.STATUS_FULL_BODY_STYLING)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_SOAK_FEET
)
def character_soak_feet(character_id: int) -> choice.Plan:
    """
    娱乐：泡脚
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 30)
    plan.set("behavior.behavior_id", constant.Behavior.SOAK_FEET)
    plan.set("state", constant.CharacterStatus.STATUS_SOAK_FEET)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_STEAM_SAUNA
)
def character_steam_sauna(character_id: int) -> choice.Plan:
    """
    娱乐：蒸桑拿
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 30)
    plan.set("behavior.behavior_id", constant.Behavior.STEAM_SAUNA)
    plan.set("state", constant.CharacterStatus.STATUS_STEAM_SAUNA)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_HYDROTHERAPY_TREATMENT
)
def character_hydrotherapy_treatment(character_id: int) -> choice.Plan:
    """
    娱乐：水疗护理
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.HYDROTHERAPY_TREATMENT)
    plan.set("state", constant.CharacterStatus.STATUS_HYDROTHERAPY_TREATMENT)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ENTERTAIN_ONSEN_BATH
)
def character_onsen_bath(character_id: int) -> choice.Plan:
    """
    娱乐：泡温泉
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.ONSEN_BATH)
    plan.set("state", constant.CharacterStatus.STATUS_ONSEN_BATH)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.SINGING_RAND_CHARACTER
)
def character_singing_to_rand_character(character_id: int) -> choice.Plan:
    """
    唱歌给房间里随机角色听
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    target_id = handle_npc_ai.select_random_free_character(character_id)
    if target_id != -1:
        plan.set("behavior.behavior_id", constant.Behavior.SINGING)
        plan.set("behavior.duration", 10)
        plan.set("target_character_id", target_id)
        plan.set("state", constant.CharacterStatus.STATUS_SINGING)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.PLAY_INSTRUMENT_RAND_CHARACTER
)
def character_play_instrument_to_rand_character(
    character_id: int,
) -> choice.Plan:
    """
    演奏乐器给房间里随机角色听
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    target_id = handle_npc_ai.select_random_free_character(character_id)
    if target_id != -1:
        plan.set("behavior.behavior_id", constant.Behavior.PLAY_INSTRUMENT)
        plan.set("behavior.duration", 30)
        plan.set("target_character_id", target_id)
        plan.set("state", constant.CharacterStatus.STATUS_PLAY_INSTRUMENT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.PEE)
def character_pee(character_id: int) -> choice.Plan:
    """
    角色解手
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.PEE)
    plan.set("state", constant.CharacterStatus.STATUS_PEE)
    plan.set("behavior.duration", 5)
    if (
        handle_premise.handle_urinate_ge_125(character_id)
        and handle_premise.handle_not_in_toilet(character_id)
        and character_data.position == cache.character_data[0].position
    ):
        plan.draw(
            _(
                "尿意达到了极限的{0}实在无法继续憋下去，被迫当场尿了出来\n"
            ).format(character_data.name),
            wait=True,
        )
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.START_SHOWER)
def character_start_shower(character_id: int) -> choice.Plan:
    """
    进入要脱衣服（洗澡）状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.shower", 1)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.SIWM_1)
def character_swim_1(character_id: int) -> choice.Plan:
    """
    进入要换泳衣状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.swim", 1)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.SIWM_2)
def character_swim_2(character_id: int) -> choice.Plan:
    """
    脱掉衣服并换上泳衣并进入要游泳状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.READY_TO_SWIM)
    plan.set("state", constant.CharacterStatus.STATUS_READY_TO_SWIM)
    plan.set("behavior.duration", 10)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.START_BATHHOUSE_ENTERTAINMENT
)
def character_start_bathhouse_entertainment(character_id: int) -> choice.Plan:
    """
    进入要去大浴场娱乐_要更衣状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.bathhouse_entertainment", 1)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.FOOT_CLOTH_TO_LOCKER
)
def character_foot_cloth_to_locker(character_id: int) -> choice.Plan:
    """
    袜子和鞋子转移到衣柜里
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.FOOT_CLOTH_TO_LOCKER)
    plan.set("state", constant.CharacterStatus.STATUS_FOOT_CLOTH_TO_LOCKER)
    plan.set("behavior.duration", 5)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WEAR_TO_LOCKER_AND_GET_SHOWER_CLOTH
)
def character_wear_to_locker_and_get_shower_cloth(
    character_id: int,
) -> choice.Plan:
    """
    当前身上衣服转移到衣柜里，并换上浴帽和浴巾
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set(
        "behavior.behavior_id",
        constant.Behavior.WEAR_TO_LOCKER_AND_GET_SHOWER_CLOTH,
    )
    plan.set(
        "state",
        constant.CharacterStatus.STATUS_WEAR_TO_LOCKER_AND_GET_SHOWER_CLOTH,
    )
    plan.set("behavior.duration", 10)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.CLEAN_WEAR_AND_LOCKER_TO_WEAR
)
def character_clean_wear_and_locker_to_wear(character_id: int) -> choice.Plan:
    """
    清空身上的衣服然后穿回衣柜的衣服，如果有浴场或游泳娱乐flag则置0
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set(
        "behavior.behavior_id", constant.Behavior.CLEAN_WEAR_AND_LOCKER_TO_WEAR
    )
    plan.set(
        "state", constant.CharacterStatus.STATUS_CLEAN_WEAR_AND_LOCKER_TO_WEAR
    )
    plan.set("behavior.duration", 10)

    # 如果有浴场或游泳娱乐flag则置0
    if plan.get("sp_flag.bathhouse_entertainment"):
        plan.set("sp_flag.bathhouse_entertainment", 0)
    if plan.get("sp_flag.swim"):
        plan.set("sp_flag.swim", 0)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.HELP_BUY_FOOD_1)
def character_help_buy_food(character_id: int) -> choice.Plan:
    """
    进入要买饭状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("sp_flag.help_buy_food", 1)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)

    # 如果和玩家位于同一地点，则输出提示信息
    if character_data.position == cache.character_data[0].position:
        plan.draw(_("{0}打算去买饭\n").format(character_data.name), wait=False)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.HELP_MAKE_FOOD_1)
def character_help_make_food(character_id: int) -> choice.Plan:
    """
    进入要做饭状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("sp_flag.help_make_food", 1)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)

    # 如果和玩家位于同一地点，则输出提示信息
    if character_data.position == cache.character_data[0].position:
        plan.draw(_("{0}打算去做饭\n").format(character_data.name), wait=False)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MORNING_SALUTATION_FLAG_1
)
def character_morning_salutation_flag_1(character_id: int) -> choice.Plan:
    """
    进入要早安问候状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.morning_salutation", 1)
    # 如果此时还没有完成晚安问候，则清除晚安问候flag
    plan.set("sp_flag.night_salutation", 0)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan
    # print(f"{character_data.name}进入要早安问候状态")


@handle_state_machine.add_state_machine(
    constant.StateMachine.NIGHT_SALUTATION_FLAG_1
)
def character_night_salutation_flag_1(character_id: int) -> choice.Plan:
    """
    进入要晚安问候状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.night_salutation", 1)
    # 如果此时还没有完成早安问候，则清除早安问候flag
    plan.set("sp_flag.morning_salutation", 0)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan
    # print(f"debug {character_data.name} 进入要晚安问候状态，time = {cache.game_time}")


@handle_state_machine.add_state_machine(constant.StateMachine.START_MILK)
def character_start_milk(character_id: int) -> choice.Plan:
    """
    进入要挤奶状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.milk", True)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MAKE_MILK)
def character_make_milk(character_id: int) -> choice.Plan:
    """
    角色挤奶
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.MILK)
    plan.set("state", constant.CharacterStatus.STATUS_MILK)
    plan.set("behavior.duration", 30)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.START_MASTUREBATE)
def character_start_masturebate(character_id: int) -> choice.Plan:
    """
    进入要自慰或要逆推状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.Design import attr_calculation

    # 获取攻略等级
    character_fall_level = attr_calculation.get_character_fall_level(
        character_id
    )
    # 根据攻略等级决定是自慰还是逆推
    if character_fall_level >= 4:
        activate_rate = 50
    elif character_fall_level == 3:
        activate_rate = 20
    elif character_fall_level == 2:
        activate_rate = 5
    else:
        activate_rate = 0
    # 是否逆推，需要没有被禁止且随机成功
    if (
        handle_premise.handle_not_ask_not_active_h_for_player(character_id)
        and random.randint(1, 100) <= activate_rate
    ):
        plan.set("sp_flag.npc_masturebate_for_player", True)
    else:
        # 随机等于1或2来决定自慰地点
        plan.set("sp_flag.masturebate", random.randint(1, 2))
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.MASTUREBATE)
def character_masturebate(character_id: int) -> choice.Plan:
    """
    角色自慰
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.MASTUREBATE)
    plan.set("state", constant.CharacterStatus.STATUS_MASTUREBATE)
    plan.set("behavior.duration", 10)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.GET_CHARA_NORMAL_CLOTH_AND_DAY_EQIP
)
def character_get_chara_normal_cloth_and_day_equip(
    character_id: int,
) -> choice.Plan:
    """
    起床（换上正常服装+调整管理白天道具）
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.GET_UP)
    plan.set("behavior.duration", 3)
    plan.set("state", constant.CharacterStatus.STATUS_GET_UP)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.RESET_SHOWER_STATUS_AND_GET_NORMAL_CLOTH
)
def character_reset_shower_status_and_get_normal_cloth(
    character_id: int,
) -> choice.Plan:
    """
    清零洗澡状态并换上标准衣服
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.shower", 0)
    plan.set("sp_flag.sleep_h_awake", False)
    plan.kind("npc_cloth")
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.START_MASTUREBATE_BEFORE_SLEEP
)
def character_start_masturebate_before_sleep(character_id: int) -> choice.Plan:
    """
    进入要睡前自慰状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.masturebate_before_sleep", 1)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.JOIN_GROUP_SEX)
def character_join_group_sex(character_id: int) -> choice.Plan:
    """
    加入群交
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", 0)
    plan.set("behavior.behavior_id", constant.Behavior.JOIN_GROUP_SEX)
    plan.set("behavior.duration", 5)
    plan.set("state", constant.CharacterStatus.STATUS_JOIN_GROUP_SEX)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.STOP_JOIN_GROUP_SEX
)
def character_stop_join_group_sex(character_id: int) -> choice.Plan:
    """
    停止加入群交
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.go_to_join_group_sex", False)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WAIT_FOR_HEALTH_CHECK
)
def character_wait_for_health_check(character_id: int) -> choice.Plan:
    """
    等待体检
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    # 开始时加入等待序列
    plan.kind("join_exam_queue")
    # 重置今日体检时间
    plan.set("action_info.health_check_today", 0)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan
    # print(f"{character_data.name}进入等待体检状态")


@handle_state_machine.add_state_machine(constant.StateMachine.WEAR_TO_LOCKER)
def character_wear_to_locker(character_id: int) -> choice.Plan:
    """
    当前身上衣服转移到衣柜里
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.WEAR_TO_LOCKER)
    plan.set("state", constant.CharacterStatus.STATUS_WEAR_TO_LOCKER)
    plan.set("behavior.duration", 10)
    if character_data.position == cache.character_data[0].position:
        plan.draw(_("{0}脱成全裸了\n").format(character_data.name), wait=False)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.LOCKER_TO_WEAR)
def character_locker_to_wear(character_id: int) -> choice.Plan:
    """
    当前衣柜里衣服转移到身上，如果有浴场flag则置0
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.LOCKER_TO_WEAR)
    plan.set("state", constant.CharacterStatus.STATUS_LOCKER_TO_WEAR)
    plan.set("behavior.duration", 10)
    if character_data.position == cache.character_data[0].position:
        plan.draw(_("{0}穿上了衣服\n").format(character_data.name), wait=False)
    # 如果有浴场或游泳娱乐flag则置0
    if plan.get("sp_flag.bathhouse_entertainment"):
        plan.set("sp_flag.bathhouse_entertainment", 0)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.TAKE_SHOWER)
def character_take_shower(character_id: int) -> choice.Plan:
    """
    角色淋浴
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.TAKE_SHOWER)
    plan.set("state", constant.CharacterStatus.STATUS_TAKE_SHOWER)
    plan.set("behavior.duration", 30)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.SIMPLE_SHOWER)
def character_simple_shower(character_id: int) -> choice.Plan:
    """
    角色简易洗澡
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SIMPLE_SHOWER)
    plan.set("behavior.duration", 10)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.GET_SHOWER_CLOTH_AND_CLEAN_LOCKER
)
def character_get_shower_cloth_and_clean_locker(
    character_id: int,
) -> choice.Plan:
    """
    角色换上浴帽和浴巾并清空衣柜
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.PUT_SHOWER_CLOTH)
    plan.set("state", constant.CharacterStatus.STATUS_PUT_SHOWER_CLOTH)
    plan.set("behavior.duration", 10)
    if character_data.position == cache.character_data[0].position:
        plan.draw(
            _("{0}换上了浴帽和浴巾\n").format(character_data.name), wait=False
        )
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.START_EAT_FOOD)
def character_start_eat_food(character_id: int) -> choice.Plan:
    """
    进入要取餐状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Cooking_System import cooking

    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    plan.set("sp_flag.eat_food", 1)
    # 随机三分之一的几率去食堂，其他几率去美食街
    if random.randint(1, 3) == 1:
        plan.set("action_info.eat_food_restaurant", -1)
    else:
        # 首先获取所有开放的餐厅id
        all_restaurant_id_list = []
        if len(economy.shops_open()):
            for shop_name in economy.shops_open():
                for restaurant_id in game_config.config_restaurant:
                    if (
                        game_config.config_restaurant[restaurant_id].name
                        == shop_name
                    ):
                        all_restaurant_id_list.append(restaurant_id)
                        break
        # 如果没有开放的餐厅则去食堂
        if not len(all_restaurant_id_list):
            plan.set("action_info.eat_food_restaurant", -1)
        else:
            plan.set(
                "action_info.eat_food_restaurant",
                random.choice(all_restaurant_id_list),
            )
            # 一半几率去自己出身地的餐厅
            if random.randint(1, 2) == 1:
                restaurant_id = cooking.find_character_birthplace_restaurant(
                    character_id
                )
                if (
                    restaurant_id != -1
                    and restaurant_id in all_restaurant_id_list
                ):
                    plan.set("action_info.eat_food_restaurant", restaurant_id)
                else:
                    # 随机选一个餐厅
                    restaurant_id = random.choice(all_restaurant_id_list)
                    plan.set("action_info.eat_food_restaurant", restaurant_id)
            else:
                # 随机选一个餐厅
                restaurant_id = random.choice(all_restaurant_id_list)
                plan.set("action_info.eat_food_restaurant", restaurant_id)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.BUY_RAND_FOOD_AT_FOODSHOP
)
def character_buy_rand_food_at_foodshop(character_id: int) -> choice.Plan:
    """
    在食物商店购买随机食物
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    all_food_list = []
    make_food_list = []
    # 在食堂购买
    if action_info.get(character_id, "eat_food_restaurant") == -1:
        # 收集还有食物的货架的食谱id
        shelves = kitchen.shelves()
        for recipes_id, foods in shelves.items():
            # 跳过卖空的货架
            if not len(foods):
                continue
            # 获取食谱
            food_recipe = cache.recipe_data[int(recipes_id)]
            all_food_list.append(recipes_id)
            # 菜谱类型不是预制食物（5）的算自制食物
            if food_recipe.type != 5:
                make_food_list.append(recipes_id)
        # 如果没有食物则开始时刷新食物，等待下次购买
        if not len(all_food_list):
            plan.kind("restock_shop")
            plan.arg("shop", -1)
            return plan
        # 如果有自制食物则优先购买自制食物
        if len(make_food_list):
            all_food_list = make_food_list
        # 随机选一个食物id
        now_food_id = random.choice(all_food_list)
        now_food = shelves[now_food_id][
            random.choice(list(shelves[now_food_id].keys()))
        ]
        # 开始时从食堂拿进背包
        _buy_food(plan, -1, now_food_id, now_food.uid)
    # 在指定餐厅购买
    else:
        restaurant_id = action_info.get(character_id, "eat_food_restaurant")
        shelf = economy.shelf(restaurant_id)
        all_food_list = [recipe for recipe, foods in shelf.items() if foods]
        if not len(all_food_list):
            plan.kind("restock_shop")
            plan.arg("shop", restaurant_id)
            return plan
        now_food_id = random.choice(all_food_list)
        now_food_uid = random.choice(list(shelf[now_food_id]))
        _buy_food(plan, restaurant_id, now_food_id, now_food_uid)

    plan.set("behavior.behavior_id", constant.Behavior.BUY_FOOD)
    plan.set("state", constant.CharacterStatus.STATUS_BUY_FOOD)
    plan.set("behavior.duration", 5)

    # 特殊flag进行对应更改
    # 帮忙买饭
    if plan.get("sp_flag.help_buy_food") == 1:
        plan.set("sp_flag.help_buy_food", 2)
    # 帮忙买第二次饭
    elif plan.get("sp_flag.help_buy_food") == 2:
        plan.set("sp_flag.help_buy_food", 3)
    # AI正常吃饭
    elif plan.get("sp_flag.eat_food") == 1:
        plan.set("sp_flag.eat_food", 2)
    return plan


def _buy_food(
    plan: choice.Plan, shop: int, recipe_id: object, food_uid: object
) -> None:
    """
    开始时把选中的食物从食堂或餐厅拿进背包，并作为行为的目标食物
    Keyword arguments:
    plan -- 计划
    shop -- -1 为食堂，否则为餐厅id
    recipe_id -- 食谱id（食堂或餐厅的数据里的键）
    food_uid -- 食物的uid（记成字符串）
    """
    plan.kind("buy_food")
    plan.arg("shop", shop)
    plan.arg("recipe_id", recipe_id)
    plan.arg("food_uid", str(food_uid))


@handle_state_machine.add_state_machine(constant.StateMachine.EAT_BAG_RAND_FOOD)
def character_eat_rand_food(character_id: int) -> choice.Plan:
    """
    角色随机食用背包中的食物
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.EAT)
    now_food_list = []
    for food_id in inventory.foods(character_id):
        now_food_list.append(food_id)
    # 如果没有食物则直接清空饥饿值和进食状态，然后切换至无行动状态并返回，以防止进食失败的死循环
    if not len(now_food_list):
        plan.kind("hunger_zero")
        plan.set("target_character_id", character_id)
        plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
        plan.set("behavior.duration", 1)
        plan.set("state", constant.CharacterStatus.STATUS_WAIT)
        return plan
    choice_food_id = random.choice(now_food_list)
    plan.kind("eat_bag_food")
    plan.arg("food_uid", str(choice_food_id))
    plan.set("state", constant.CharacterStatus.STATUS_EAT)
    plan.set("action_info.eat_food_restaurant", -1)

    plan.set("behavior.duration", 30)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.START_SLEEP)
def character_start_sleep(character_id: int) -> choice.Plan:
    """
    进入要睡眠状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.sleep", True)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.START_REST)
def character_start_rest(character_id: int) -> choice.Plan:
    """
    进入要休息状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.rest", True)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.START_PEE)
def character_start_pee(character_id: int) -> choice.Plan:
    """
    进入要撒尿状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.pee", True)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.WORK_CURE_PATIENT)
def character_work_cure_patient(character_id: int) -> choice.Plan:
    """
    角色工作：治疗病人
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.CURE_PATIENT)
    # 设施加成
    adjust = basement.calc_facility_efficiency(6)
    new_time = int(30 / adjust)
    plan.set("behavior.duration", new_time)
    plan.set("state", constant.CharacterStatus.STATUS_CURE_PATIENT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.WORK_WARD_ROUND)
def character_work_ward_round(character_id: int) -> choice.Plan:
    """角色工作：病房查房"""

    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.WARD_ROUND)
    adjust = max(basement.calc_facility_efficiency(6), 0.1)
    new_time = max(int(45 / adjust), 10)
    plan.set("behavior.duration", new_time)
    plan.set("state", constant.CharacterStatus.STATUS_WARD_ROUND)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_START_SURGERY
)
def character_work_start_surgery(character_id: int) -> choice.Plan:
    """
    工作：进入要手术状态，并指定一个对象病人
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Medical_System import medical_service

    character_data: game_type.Character = cache.character_data[character_id]

    # 获取所有可进行手术的患者列表
    available_patients_list = medical_service.get_surgery_candidate_patient_ids(
        doctor_character=character_data,
        target_base=cache.rhodes_island,
    )

    # 赋予角色行为数据
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)

    # 如果没有可手术的患者，则直接进入等待状态并返回
    if len(available_patients_list) == 0:
        return plan

    # 随机选择一个患者
    selected_patient = random.choice(available_patients_list)

    # 开始时扣除手术资源并安排手术，资源不足时不安排
    plan.kind("schedule_surgery")
    plan.arg("patient_id", selected_patient.patient_id)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_PERFORM_SURGERY
)
def character_work_perform_surgery(character_id: int) -> choice.Plan:
    """角色工作：执行手术治疗"""

    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.PERFORM_SURGERY)
    adjust = max(basement.calc_facility_efficiency(6), 0.1)
    new_time = max(int(60 / adjust), 15)
    plan.set("behavior.duration", new_time)
    plan.set("state", constant.CharacterStatus.STATUS_PERFORM_SURGERY)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.WORK_RECRUIT)
def character_work_recruit(character_id: int) -> choice.Plan:
    """
    角色工作：招募干员
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.RECRUIT)
    plan.set("behavior.duration", 60)
    plan.set("state", constant.CharacterStatus.STATUS_RECRUIT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.WORK_TEACH)
def character_work_teach(character_id: int) -> choice.Plan:
    """
    角色工作：授课
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Education_System import schedule_handle

    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.TEACH)
    # 时长截到本节结束：迟到的教师照满45分钟讲，会压进她下一节在别的教室的课（Plan 22 第五轮）
    plan.set(
        "behavior.duration",
        schedule_handle.get_period_left_minute(character_id),
    )
    plan.set("state", constant.CharacterStatus.STATUS_TEACH)
    plan.kind("teach")
    return plan


def pull_students(character_id: int) -> None:
    """
    教师开始授课时，把本节来上这间教室的学生排进听课，并打断她们当前的行动；听课与教师的授课同时长
    Keyword arguments:
    character_id -- 教师的角色id
    """
    from Script.Modules.gameplay_resolution import plan_queue

    character_data: game_type.Character = cache.character_data[character_id]
    # 把本节来上这间教室的学生变为听课状态
    # 只拉自己的学生（本节个人课表指向这间教室的人），不再把场景里所有学生岗都拉过来：
    #    路过的孩子不该被顺手记一节课。
    #    判据与学生自己决策时同口径：只认学生岗，过体力闸与心情闸（必修生豁免）——开课前已在教室里等候的学生，
    #    本节该体力缺课或掷中翘课的，不能因为教师先被处理就被拉进来（Plan 25 §3.5）
    from Script.System.Education_System import class_ai

    scene_path_str = map_handle.get_map_system_path_str_for_list(
        character_data.position
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    for chara_id in scene_data.character_list:
        # 跳过自己
        if chara_id == character_id:
            continue
        if not class_ai.judge_student_join_class(
            chara_id, scene_data.scene_name, character_data.behavior.start_time
        ):
            continue
        # 让对方变成听课状态：打断后她在同一分钟开始听课，开始时刻与教师对齐，节次判定才对得上
        plan_queue.plan_next(
            chara_id,
            constant.Behavior.ATTENT_CLASS,
            character_data.behavior.duration,
            state=constant.CharacterStatus.STATUS_ATTENT_CLASS,
            interrupt=True,
        )


@handle_state_machine.add_state_machine(constant.StateMachine.WORK_ATTENT_CLASS)
def character_attend_class(character_id: int) -> choice.Plan:
    """
    角色工作：上学
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Education_System import schedule_handle

    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.ATTENT_CLASS)
    # 时长截到本节结束，晚到的学生下一节才能按时换教室（Plan 22 第五轮）
    plan.set(
        "behavior.duration",
        schedule_handle.get_period_left_minute(character_id),
    )
    plan.set("state", constant.CharacterStatus.STATUS_ATTENT_CLASS)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.EDUCATION_SELF_STUDY
)
def character_education_self_study(character_id: int) -> choice.Plan:
    """
    上课：本节无可用教师，降级为自习（Plan 22 §3.5）
    与听课的区别只在结算：自习走 548 效果，基础值降档且不吃师生等级差
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Education_System import schedule_handle

    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SELF_STUDY)
    # 节次内截到本节结束；日程活动「上课（无课时自习）」在节次外照旧45分钟（Plan 22 第五轮）
    plan.set(
        "behavior.duration",
        schedule_handle.get_period_left_minute(character_id),
    )
    plan.set("state", constant.CharacterStatus.STATUS_SELF_STUDY)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.EDUCATION_SKIP_CLASS
)
def character_education_skip_class(character_id: int) -> choice.Plan:
    """
    上课：翘课（Plan 22 §3.19）
    还在教室里就先溜回自己宿舍，人已经不在教室了才开始摸鱼——
    翘课的可见表现就是"该在教室的人不在教室"，这一步不能省
    开始摸鱼时记一节缺课（Plan 30）：翘掉的课原先不进出勤率，常翘课的孩子照评良好。
       与 721 同理，前提不能有副作用，所以记在状态机里；settle_absent 与体力缺课共用同一节的去重标记，
       翘课 flag 挂着时之后每一节派到这里各记一节。先离开教室的那一步不记，到了外面开始摸鱼时才记
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Education_System import education_constant

    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("target_character_id", character_id)
    now_scene_str = map_handle.get_map_system_path_str_for_list(
        character_data.position
    )
    now_scene_tag: str | list[str] = ""
    if now_scene_str in cache.scene_data:
        now_scene_tag = cache.scene_data[now_scene_str].scene_tag
    # 还在教室（含实践教室与大礼堂）里，先离开
    if any(
        tag in now_scene_tag
        for tag in education_constant.CLASSROOM_TAG_BY_COURSE_TYPE.values()
    ):
        to_dormitory = map_handle.get_map_system_path_for_str(
            character_data.dormitory
        )
        plan.move(to_dormitory)
        return plan
    plan.kind("skip_class")
    plan.set("behavior.behavior_id", constant.Behavior.SKIP_CLASS)
    plan.set("behavior.duration", 45)
    plan.set("state", constant.CharacterStatus.STATUS_SKIP_CLASS)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.EDUCATION_MOVE_TO_COURSE_PLACE
)
def character_education_move_to_course_place(character_id: int) -> choice.Plan:
    """
    上课：移动到个人式课型（体育/兴趣/实习）的上课地点（Plan 22 §3.21）
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Education_System import schedule_handle

    now_course = schedule_handle.get_now_course(character_id)
    # 到岗时间：本节还没开始，去马上要上的那一节的地点（第五轮）
    if now_course is None:
        now_course = schedule_handle.get_upcoming_course(character_id)
    if now_course is None:
        return plan
    to_place = schedule_handle.get_course_place(now_course)
    if not to_place:
        return plan
    plan.move(to_place)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.EDUCATION_DO_COURSE
)
def character_education_do_course(character_id: int) -> choice.Plan:
    """
    上课：在个人式课型的地点执行该课对应的既有行为（Plan 22 §3.21）
    体育课与兴趣课执行的是自带效果串的既有行为，学生侧的学习收益无需另加结算；
       但这些行为全岛共用（成年干员娱乐时也走它们），效果串里加不了出勤，所以出勤在这里派出行为时记一节
       （growth_handle.settle_course_attend，同一节只记一次，Plan 29 §3.1）；
       实习课走新增的 intern_class，它的效果串里带一次学徒侧结算（552），出勤也由那里记，这里不另记
    兴趣课「读书」要先借书：读书结算按 behavior.book_id 取书、口上按 behavior.book_name 写书名，
       与娱乐读书（401）共用 prepare_npc_read_book 装配；借不到书（判定与执行之间被别人借走）就等 1 分钟、不记出勤，
       下一次决策时 get_now_course 会按「借不到书视为没课」交回娱乐链（Plan 29 §3.2）
    时长一律截到45分钟（一节课）：战斗训练本是120分钟、锻炼与游泳是60分钟，
       照原时长会让一节体育课吃掉整个上午。既有结算按 add_time 线性计算，截断天然成立
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Education_System import (
        education_constant,
        schedule_handle,
    )

    plan.set("target_character_id", character_id)
    now_course = schedule_handle.get_now_course(character_id)
    if now_course is None:
        return plan
    course_type = now_course["course_type"]
    behavior_name = ""
    state_id = 0
    # 体育课：四处地点各自对应不同的既有行为
    if course_type == education_constant.COURSE_TYPE_PE:
        place_data = education_constant.PE_PLACE_DATA.get(now_course["target"])
        if place_data is not None:
            behavior_name, state_id = place_data[1], place_data[2]
    # 兴趣课：行为直接读 Entertainment.csv 的 behavior_id 列（该列的值即状态cid）
    elif course_type == education_constant.COURSE_TYPE_INTEREST:
        if now_course["target"] in game_config.config_entertainment:
            state_id = game_config.config_entertainment[
                now_course["target"]
            ].behavior_id
            behavior_name = schedule_handle.get_behavior_name_by_cid(state_id)
            # 读书先借书并装配 behavior.book_id / book_name
            if behavior_name == constant.Behavior.READ_BOOK:
                from Script.UI.Panel import borrow_book_panel

                if not borrow_book_panel.judge_can_get_read_book(character_id):
                    plan.set("behavior.behavior_id", constant.Behavior.WAIT)
                    plan.set("behavior.duration", 1)
                    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
                    return plan
                plan.arg("read_book", True)
    # 实习课：本计划新增的行为
    elif course_type == education_constant.COURSE_TYPE_INTERN:
        behavior_name = constant.Behavior.INTERN_CLASS
        state_id = constant.CharacterStatus.STATUS_INTERN_CLASS
    if not behavior_name or not state_id:
        return plan
    plan.set("behavior.behavior_id", behavior_name)
    # 截到本节结束（Plan 22 第五轮），最多一节课45分钟
    plan.set(
        "behavior.duration",
        schedule_handle.get_period_left_minute(character_id),
    )
    plan.set("state", state_id)
    # 体育课与兴趣课在派出行为时记一节出勤（实习课由 552 记）
    if course_type in (
        education_constant.COURSE_TYPE_PE,
        education_constant.COURSE_TYPE_INTEREST,
    ):
        plan.arg("attend", True)
    plan.kind("do_course")
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.EDUCATION_WAIT_NEXT_PERIOD
)
def character_education_wait_next_period(character_id: int) -> choice.Plan:
    """
    等到下一节开始（Plan 22 第五轮）：教师本节没课时在教师办公室待命，提前到了教室的师生原地等开课
    时长截到下一节开始，最少1分钟、最多30分钟——不截会一分钟一分钟地空转，截太长又会误了下一节
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    import datetime

    from Script.Design import game_time

    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("target_character_id", character_id)
    now_time = character_data.behavior.start_time or game_time.now()
    duration = 30
    for hour, minute in game_time.CLASS_PERIOD_START:
        start_time = now_time.replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        if start_time > now_time:
            duration = int(
                (start_time - now_time) / datetime.timedelta(minutes=1)
            )
            break
    plan.set("behavior.behavior_id", constant.Behavior.WAIT)
    plan.set("behavior.duration", max(1, min(30, duration)))
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.EDUCATION_ABSENT_REST
)
def character_education_absent_rest(character_id: int) -> choice.Plan:
    """
    上课：体力不足缺这一节课，记一节缺课后原地休息（Plan 24）
    记缺课原先写在 AI 判定里，前提不能有副作用，所以挪进状态机；settle_absent 自带同一节只记一次的去重
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.follow(character_rest(character_id))
    plan.kind("absent_rest")
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.EDUCATION_JOIN_SEX_CLASS
)
def character_education_join_sex_class(character_id: int) -> choice.Plan:
    """
    上课：走进正在上性技实操课的教室，直接加入课堂 H 并记一节出勤（Plan 25 §3.2，Plan 26 §3.3 泛化）
    两个调用方：
        target 220835 —— 本节（或提前开讲的下一节）的课所在教室正在上实操课、自己可以参加
        target 515    —— 课堂模式下受玩家「邀请」、已经走到玩家身边的人
    与开课时拉人（效果 10014）走同一个 pull_student_into_class：进 H、看见玩家的 H、到场二段口上。
       开课时拉进来的人出勤已由 start_sex_class 记过，晚到的人由这里补记；进了 H 之后她不再进 AI 链，不会重复记。
    到场那一刻再判一次参加门槛：受邀的人走在路上时课可能已经下了、她可能换了岗，不满足就照状态机 97 的写法收场
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.System.Education_System import sex_class_handle

    # 受邀前往的标记在这里一并清掉：不管进不进课堂，这趟邀请都已经走完了
    plan.set("sp_flag.go_to_join_group_sex", False)
    plan.set("target_character_id", character_id)
    must_attend = character_id in sex_class_handle.get_must_attend_set()
    if not modes.sex_class() or not sex_class_handle.judge_can_join_sex_class(
        character_id, check_course=not must_attend
    ):
        plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
        plan.set("behavior.duration", 1)
        plan.set("state", constant.CharacterStatus.STATUS_WAIT)
        return plan
    plan.kind("join_sex_class")
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.WORK_LIBRARY_1)
def character_work_library_1(character_id: int) -> choice.Plan:
    """
    工作：三成去图书馆，七成原地等待30分钟
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    rand_num = random.randint(0, 99)
    if rand_num < 30:
        to_library = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data["Library"])
        )
        plan.move(to_library)
    else:
        plan.set("behavior.behavior_id", constant.Behavior.WAIT)
        plan.set("behavior.duration", 30)
        plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.WORK_LIBRARY_2)
def character_work_library_2(character_id: int) -> choice.Plan:
    """
    工作：三成去图书馆办公室，七成看书
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.UI.Panel import borrow_book_panel

    plan.set("target_character_id", character_id)
    rand_num = random.randint(0, 99)
    if rand_num < 30:
        to_library = map_handle.get_map_system_path_for_str(
            random.choice(constant.place_data["Library_Office"])
        )
        plan.move(to_library)
    else:
        # 借不到书就等 1 分钟；借得到时开始时借书，并把借着的那本写进 behavior
        if not borrow_book_panel.judge_can_get_read_book(character_id):
            plan.set("behavior.behavior_id", constant.Behavior.WAIT)
            plan.set("behavior.duration", 1)
            plan.set("state", constant.CharacterStatus.STATUS_WAIT)
            return plan
        plan.kind("read_book")
        plan.set("behavior.behavior_id", constant.Behavior.READ_BOOK)
        plan.set("state", constant.CharacterStatus.STATUS_READ_BOOK)
        plan.set("behavior.duration", 30)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_MAINTENANCE_1
)
def character_work_maintenance_1(character_id: int) -> choice.Plan:
    """
    工作：进入要检修状态，并随机指定一个检修地点
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    from Script.Design import basement

    plan.set("sp_flag.work_maintenance", True)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)

    # 获得维修地点
    target_scene_str = basement.find_facility_damage()
    # 开始时记录检修地点
    plan.kind("maintenance")
    plan.arg("place", target_scene_str)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_MAINTENANCE_2
)
def character_work_maintenance_2(character_id: int) -> choice.Plan:
    """
    角色工作：维护设施，并清零检修状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.MAINTENANCE_FACILITIES)
    need_time = 5
    plan.set("state", constant.CharacterStatus.STATUS_MAINTENANCE_FACILITIES)
    # 获取当前位置
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        character_data.position
    )
    # 检查是否在损坏设施数据中
    damage = maintenance.damage()
    if scene_path_str in damage:
        need_time = 60
        # 1级损坏，10分钟修复
        if damage[scene_path_str] == 1:
            need_time = 10
        # 2级损坏，30分钟修复
        elif damage[scene_path_str] == 2:
            need_time = 30
    # 根据制造能力等级减少维修时间
    ability_level = abilities.ability(character_id)[48]
    ability_adjust = 0.05 * ability_level
    ability_adjust = max(ability_adjust, 0.5)
    need_time = int(need_time * (1 - ability_adjust))
    need_time = max(need_time, 1)
    # 记录维修时间
    plan.set("behavior.duration", need_time)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_REPAIR_EQUIPMENT
)
def character_work_repair_equipment(character_id: int) -> choice.Plan:
    """
    角色工作：修理装备
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)

    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.REPAIR_EQUIPMENT)
    plan.set("behavior.duration", 60)
    plan.set("state", constant.CharacterStatus.STATUS_REPAIR_EQUIPMENT)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.WORK_COOK)
def character_work_cook(character_id: int) -> choice.Plan:
    """
    角色工作：做饭
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)

    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.NPC_WORK_COOK)
    plan.set("behavior.duration", 30)
    plan.set("behavior.make_food_time", plan.get("behavior.duration"))
    plan.set("state", constant.CharacterStatus.STATUS_NPC_WORK_COOK)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.ASSISTANT_MAKE_FOOD
)
def character_assistant_work_cook(character_id: int) -> choice.Plan:
    """
    角色助理：做饭
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)

    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.NPC_ASSISTANT_COOK)
    plan.set("behavior.duration", 30)
    plan.set("behavior.make_food_time", plan.get("behavior.duration"))
    plan.set("state", constant.CharacterStatus.STATUS_NPC_ASSISTANT_COOK)
    # 特殊flag进行对应更改
    if plan.get("sp_flag.help_make_food") == 1:
        plan.set("sp_flag.help_make_food", 2)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MORNING_SALUTATION_1
)
def character_morning_salutation_1(character_id: int) -> choice.Plan:
    """
    早安问候：叫起床
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]

    plan.set("target_character_id", 0)
    plan.set("behavior.behavior_id", constant.Behavior.MORNING_SALUTATION_1)
    plan.set("behavior.duration", 5)
    plan.set("state", constant.CharacterStatus.STATUS_MORNING_SALUTATION_1)
    # 特殊flag进行对应更改
    if plan.get("sp_flag.morning_salutation") == 1:
        plan.set("sp_flag.morning_salutation", 2)
    plan.draw(
        _("\n{0}来进行早安问候了\n").format(character_data.name),
        wait=True,
        style="gold_enrod",
    )
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MORNING_SALUTATION_2
)
def character_morning_salutation_2(character_id: int) -> choice.Plan:
    """
    早安问候：早安吻
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]

    plan.set("target_character_id", 0)
    plan.set("behavior.behavior_id", constant.Behavior.MORNING_SALUTATION_2)
    plan.set("behavior.duration", 5)
    plan.set("state", constant.CharacterStatus.STATUS_MORNING_SALUTATION_2)
    # 特殊flag进行对应更改
    if plan.get("sp_flag.morning_salutation") == 1:
        plan.set("sp_flag.morning_salutation", 2)
    plan.draw(
        _("\n{0}来进行早安问候了\n").format(character_data.name),
        wait=True,
        style="gold_enrod",
    )
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.MORNING_SALUTATION_3
)
def character_morning_salutation_3(character_id: int) -> choice.Plan:
    """
    早安问候：早安咬
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]

    plan.set("target_character_id", 0)
    plan.set("behavior.behavior_id", constant.Behavior.MORNING_SALUTATION_3)
    plan.set("behavior.duration", 10)
    plan.set("state", constant.CharacterStatus.STATUS_MORNING_SALUTATION_3)
    # 特殊flag进行对应更改
    if plan.get("sp_flag.morning_salutation") == 1:
        plan.set("sp_flag.morning_salutation", 2)
    plan.draw(
        _("\n{0}来进行早安问候了\n").format(character_data.name),
        wait=True,
        style="gold_enrod",
    )
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.NIGHT_SALUTATION_1
)
def character_night_salutation_1(character_id: int) -> choice.Plan:
    """
    晚安问候：催睡觉
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]

    plan.set("target_character_id", 0)
    plan.set("behavior.behavior_id", constant.Behavior.NIGHT_SALUTATION_1)
    plan.set("behavior.duration", 30)
    plan.set("state", constant.CharacterStatus.STATUS_NIGHT_SALUTATION_1)
    # 仅在催睡觉的服务下，晚安问候flag才会变为2
    if handle_premise.handle_assistant_night_salutation_1(character_id):
        plan.set("sp_flag.night_salutation", 2)
        # 如果此时还没有完成早安问候，则设为已早安问候
        plan.set("sp_flag.morning_salutation", 2)
    plan.draw(
        _("\n{0}来进行晚安问候了\n").format(character_data.name),
        wait=True,
        style="gold_enrod",
    )
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.NIGHT_SALUTATION_2
)
def character_night_salutation_2(character_id: int) -> choice.Plan:
    """
    晚安问候：晚安吻
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]

    plan.set("target_character_id", 0)
    plan.set("behavior.behavior_id", constant.Behavior.NIGHT_SALUTATION_2)
    plan.set("behavior.duration", 5)
    plan.set("state", constant.CharacterStatus.STATUS_NIGHT_SALUTATION_2)
    # 特殊flag进行对应更改
    plan.set("sp_flag.night_salutation", 2)
    # 如果此时还没有完成早安问候，则设为已早安问候
    plan.set("sp_flag.morning_salutation", 2)
    plan.draw(
        _("\n{0}来进行晚安问候了\n").format(character_data.name),
        wait=True,
        style="gold_enrod",
    )
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.NIGHT_SALUTATION_3
)
def character_night_salutation_3(character_id: int) -> choice.Plan:
    """
    晚安问候：晚安咬
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]

    plan.set("target_character_id", 0)
    plan.set("behavior.behavior_id", constant.Behavior.NIGHT_SALUTATION_3)
    plan.set("behavior.duration", 10)
    plan.set("state", constant.CharacterStatus.STATUS_NIGHT_SALUTATION_3)
    # 特殊flag进行对应更改
    plan.set("sp_flag.night_salutation", 2)
    # 如果此时还没有完成早安问候，则设为已早安问候
    plan.set("sp_flag.morning_salutation", 2)
    plan.draw(
        _("\n{0}来进行晚安问候了\n").format(character_data.name),
        wait=True,
        style="gold_enrod",
    )
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.NIGHT_SALUTATION_FLAG_2
)
def character_night_salutation_flag_2(character_id: int) -> choice.Plan:
    """
    进入已晚安问候状态
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("sp_flag.night_salutation", 2)
    # 如果此时还没有完成早安问候，则设为已早安问候
    plan.set("sp_flag.morning_salutation", 2)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.SHARE_BLANKLY)
    plan.set("behavior.duration", 1)
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)
    return plan
    # print(f"debug {character_data.name} 进入要晚安问候状态，time = {cache.game_time}")


@handle_state_machine.add_state_machine(
    constant.StateMachine.SELF_NIPPLE_CLAMP_SWITCH_CHANEG
)
def character_self_nipple_clamp_switch_chaneg(character_id: int) -> choice.Plan:
    """
    切换自己是否装备道具_乳头夹
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    if h_state.body_item_on(character_id, 0):
        plan.set("behavior.behavior_id", constant.Behavior.NIPPLE_CLAMP_OFF)
        plan.set("state", constant.CharacterStatus.STATUS_NIPPLE_CLAMP_OFF)
    else:
        plan.set("behavior.behavior_id", constant.Behavior.NIPPLE_CLAMP_ON)
        plan.set("state", constant.CharacterStatus.STATUS_NIPPLE_CLAMP_ON)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 5)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.SELF_CLIT_CLAMP_SWITCH_CHANEG
)
def character_self_clit_clamp_switch_chaneg(character_id: int) -> choice.Plan:
    """
    切换自己是否装备道具_阴蒂夹
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    if h_state.body_item_on(character_id, 1):
        plan.set("behavior.behavior_id", constant.Behavior.CLIT_CLAMP_OFF)
        plan.set("state", constant.CharacterStatus.STATUS_CLIT_CLAMP_OFF)
    else:
        plan.set("behavior.behavior_id", constant.Behavior.CLIT_CLAMP_ON)
        plan.set("state", constant.CharacterStatus.STATUS_CLIT_CLAMP_ON)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 5)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.SELF_V_VIBRATOR_SWITCH_CHANEG
)
def character_self_v_vibrator_switch_chaneg(character_id: int) -> choice.Plan:
    """
    切换自己是否装备道具_V振动棒
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    if h_state.body_item_on(character_id, 2):
        plan.set(
            "behavior.behavior_id", constant.Behavior.VIBRATOR_INSERTION_OFF
        )
        plan.set(
            "state", constant.CharacterStatus.STATUS_VIBRATOR_INSERTION_OFF
        )
    else:
        plan.set("behavior.behavior_id", constant.Behavior.VIBRATOR_INSERTION)
        plan.set("state", constant.CharacterStatus.STATUS_VIBRATOR_INSERTION)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 5)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.SELF_A_VIBRATOR_SWITCH_CHANEG
)
def character_self_a_vibrator_switch_chaneg(character_id: int) -> choice.Plan:
    """
    切换自己是否装备道具_A振动棒
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    if h_state.body_item_on(character_id, 3):
        plan.set(
            "behavior.behavior_id",
            constant.Behavior.VIBRATOR_INSERTION_ANAL_OFF,
        )
        plan.set(
            "state", constant.CharacterStatus.STATUS_VIBRATOR_INSERTION_ANAL_OFF
        )
    else:
        plan.set(
            "behavior.behavior_id", constant.Behavior.VIBRATOR_INSERTION_ANAL
        )
        plan.set(
            "state", constant.CharacterStatus.STATUS_VIBRATOR_INSERTION_ANAL
        )
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 5)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.WORK_PRODUCE)
def character_work_produce(character_id: int) -> choice.Plan:
    """
    角色工作：制造产品
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.PRODUCE)
    plan.set("state", constant.CharacterStatus.STATUS_PRODUCE)
    plan.set("behavior.duration", 30)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_OFFICIAL_WORK
)
def character_work_official_work(character_id: int) -> choice.Plan:
    """
    工作：处理公务
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.OFFICIAL_WORK)
    plan.set("state", constant.CharacterStatus.STATUS_OFFICIAL_WORK)
    return plan


@handle_state_machine.add_state_machine(constant.StateMachine.WORK_MASSAGE)
def character_work_massage(character_id: int) -> choice.Plan:
    """
    工作：按摩（自动寻找对象）
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    plan.set("behavior.duration", 30)
    plan.set("behavior.behavior_id", constant.Behavior.MASSAGE)
    plan.set("state", constant.CharacterStatus.STATUS_MASSAGE)

    scene_path_str = map_handle.get_map_system_path_str_for_list(
        character_data.position
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    # 场景角色数大于等于2时进行检测
    if len(scene_data.character_list) >= 2:
        # 遍历当前角色列表
        for chara_id in scene_data.character_list:
            # 跳过自己
            if chara_id == character_id:
                continue
            other_character_data: game_type.Character = cache.character_data[
                chara_id
            ]
            # 跳过也是按摩师的角色
            if other_character_data.work.work_type != 171:
                continue
            plan.set("target_character_id", chara_id)
            break
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_INVITE_VISITOR
)
def character_work_invite_visitor(character_id: int) -> choice.Plan:
    """
    工作：邀请访客
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.INVITE_VISITOR)
    plan.set("state", constant.CharacterStatus.STATUS_INVITE_VISITOR)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_PLANT_MANAGE_CROP
)
def character_work_plant_manage_crop(character_id: int) -> choice.Plan:
    """
    工作：种植与养护作物
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.PLANT_MANAGE_CROP)
    plan.set("state", constant.CharacterStatus.STATUS_PLANT_MANAGE_CROP)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_DEAL_WITH_DIPLOMACY
)
def character_work_deal_with_diplomacy(character_id: int) -> choice.Plan:
    """
    工作：处理外交事宜
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.duration", 60)
    plan.set("behavior.behavior_id", constant.Behavior.DEAL_WITH_DIPLOMACY)
    plan.set("state", constant.CharacterStatus.STATUS_DEAL_WITH_DIPLOMACY)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_SEX_EXERCISES
)
def character_work_sex_exercises(character_id: int) -> choice.Plan:
    """
    工作：性爱练习
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    # 从目前的性爱练习列表中随机选一个
    exercises_list = []
    for i in body_manage.of(character_id):
        if body_manage.of(character_id)[i]:
            body_manage_data = game_config.config_body_manage_requirement[i]
            if body_manage_data.behavior_id == "0":
                continue
            exercises_list.append(body_manage_data.behavior_id)
    # 赋予行为
    if len(exercises_list):
        now_exercises = random.choice(exercises_list)
        plan.set("behavior.duration", 30)
        plan.set("behavior.behavior_id", now_exercises)
        plan.set("state", now_exercises)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_COMBAT_TRAINING
)
def character_combat_training(character_id: int) -> choice.Plan:
    """
    角色战斗训练
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.TRAINING)
    plan.set("behavior.duration", 120)
    plan.set("state", constant.CharacterStatus.STATUS_TRAINING)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_FITNESS_TRAINING
)
def character_fitness_training(character_id: int) -> choice.Plan:
    """
    角色健身锻炼
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.EXERCISE)
    plan.set("behavior.duration", 60)
    plan.set("state", constant.CharacterStatus.STATUS_EXERCISE)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_TRAIN_PRISONER
)
def character_train_prisoner(character_id: int) -> choice.Plan:
    """
    工作：对囚犯进行日常训练
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.TRAIN_PRISONER)
    plan.set("behavior.duration", 60)
    plan.set("state", constant.CharacterStatus.STATUS_TRAIN_PRISONER)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_MANAGE_FACILITY_POWER
)
def character_manage_facility_power(character_id: int) -> choice.Plan:
    """
    工作：调控设施供能
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.MANAGE_FACILITY_POWER)
    plan.set("behavior.duration", 30)
    plan.set("state", constant.CharacterStatus.STATUS_MANAGE_FACILITY_POWER)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.WORK_INVESTIGATE_RESOURCE_MARKET
)
def character_investigate_resource_market(character_id: int) -> choice.Plan:
    """
    工作：研判资源市场
    Keyword arguments:
    character_id -- 角色id
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set(
        "behavior.behavior_id", constant.Behavior.INVESTIGATE_RESOURCE_MARKET
    )
    plan.set("behavior.duration", 60)
    return plan
