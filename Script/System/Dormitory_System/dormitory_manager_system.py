"""宿舍管理员的状态机与相关函数：前往舍管房、整理宿舍意见、选择并移动至目标宿舍、处理宿舍问题，以及要求复制钥匙时给予玩家对应层的钥匙"""

from __future__ import annotations

import re
import random
from types import FunctionType
from typing import TYPE_CHECKING

from Script.Core import cache_control, game_type, get_text, constant
from Script.Design import handle_state_machine, map_handle, handle_premise
from Script.Modules.domains import abilities, dormitory, inventory
from Script.System.Dormitory_System import common
from Script.Modules.domains import chara_life

if TYPE_CHECKING:
    from Script.Modules.npc_action_choice import choice

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """


def get_dormitory_layer_by_character(character_id: int) -> int:
    """
    获取角色当前宿舍层号
    输入类型: character_id(int)
    输出类型: int
    功能: 从角色 dormitory 对应场景名中解析层号，失败时返回0
    """
    if character_id not in cache.character_data:
        return 0
    dormitory_path = chara_life.dormitory(character_id)
    dormitory_layer = common.get_layer_by_dormitory_path(dormitory_path)
    return dormitory_layer


def get_dormitory_manager_knowledge(character_id: int) -> int:
    """
    获取角色所在层宿舍管理员学识等级
    输入类型: character_id(int)
    输出类型: int
    功能: 查询角色所在宿舍层的管理员，并返回其学识能力等级；无管理员时返回0
    """
    layer = get_dormitory_layer_by_character(character_id)
    if layer <= 0:
        return 0

    manager_id = dormitory.managers().get(layer, 0)
    if not manager_id or manager_id not in cache.character_data:
        return 0

    return int(abilities.ability(manager_id).get(45, 0))


def _get_manager_layer_by_character(character_id: int) -> int:
    """
    获取角色作为宿舍管理员时负责的层号
    输入类型: character_id(int)
    输出类型: int
    功能: 从 dormitory.managers() 中反查角色负责层号
    """
    for layer, manager_id in dormitory.managers().items():
        if manager_id == character_id:
            return int(layer)
    return 0


def _get_target_room(character_id: int) -> str:
    """
    读取宿舍管理员当前目标宿舍
    输入类型: character_id(int)
    输出类型: str
    功能: 读角色键 life.dormitory_admin_target_room，没有时为空字符串
    """
    return chara_life.dormitory_admin_target_room(character_id)


def _plan_target_room(plan: choice.Plan, room_path: str) -> None:
    """
    在计划里记下宿舍管理员的目标宿舍
    输入类型: plan(Plan), room_path(str)
    输出类型: 无
    功能: 行动开始时在角色键 life.dormitory_admin_target_room 里记录目标宿舍路径
    """
    plan.set(chara_life.dormitory_admin_target_room.key, room_path)


def _plan_wait(plan: choice.Plan, minute: int) -> None:
    """
    在计划里记下原地等待
    输入类型: plan(Plan), minute(int)
    输出类型: 无
    功能: 行动开始时设置角色等待状态和持续时间
    """
    plan.set("target_character_id", plan.character_id)
    plan.set("behavior.behavior_id", constant.Behavior.WAIT)
    plan.set("behavior.duration", max(int(minute), 1))
    plan.set("state", constant.CharacterStatus.STATUS_WAIT)


def _get_office_path_by_layer(layer: int) -> list:
    """
    根据层号获取舍管房路径
    输入类型: layer(int)
    输出类型: list
    功能: 从 Dormitory_Manager_Room 场景列表中选出对应层级舍管房路径
    """
    office_candidates = constant.place_data.get("Dormitory_Manager_Room", [])
    for office_path in office_candidates:
        match = re.search(r"[\\/](\d)区[\\/]", office_path)
        if match and int(match.group(1)) == layer:
            return map_handle.get_map_system_path_for_str(office_path)
    if len(office_candidates):
        return map_handle.get_map_system_path_for_str(
            random.choice(office_candidates)
        )
    return []


def _get_open_room_paths_by_layer(layer: int) -> list:
    """
    获取指定层可巡查的开放宿舍路径列表
    输入类型: layer(int)
    输出类型: list
    功能: 从 facility_open 中筛选已开放且属于该层的宿舍房间
    """
    return common.get_open_dormitory_room_paths_by_layer(layer)


@handle_state_machine.add_state_machine(
    constant.StateMachine.DORMITORY_ADMIN_TO_OFFICE
)
def dormitory_admin_to_office(character_id: int) -> choice.Plan:
    """
    宿舍管理员状态机入口：前往所属层舍管房
    输入类型: character_id(int)
    输出类型: 无
    功能: 根据角色负责层号获取舍管房路径，前往途中不显示移动信息；异常情况时原地等待后重试
    """
    plan = handle_state_machine.new_plan(character_id)
    # 阶段0：初始前往舍管房，或因异常返回后的重试
    layer = _get_manager_layer_by_character(character_id)
    if layer <= 0:
        _plan_wait(plan, 5)
        return plan

    # 获取目标舍管房路径，优先匹配对应层级，未找到时随机分配一个舍管房
    target_scene = _get_office_path_by_layer(layer)
    if target_scene == []:
        _plan_wait(plan, 5)
        return plan

    # 前往舍管房，途中不显示移动信息
    plan.move(target_scene, show_info_flag=False)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.DORMITORY_ADMIN_ORGANIZE
)
def dormitory_admin_organize(character_id: int) -> choice.Plan:
    """
    整理宿舍意见
    输入类型: character_id(int)
    输出类型: Plan
    功能: 原地工作，并切换到选房阶段
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set(
        "behavior.behavior_id", constant.Behavior.ORGANIZE_DORMITORY_OPINION
    )
    plan.set("behavior.duration", 10)
    plan.set(
        "state", constant.CharacterStatus.STATUS_ORGANIZE_DORMITORY_OPINION
    )
    return plan


def dormitory_admin_select_room(plan: choice.Plan) -> str:
    """
    选择目标宿舍
    输入类型: plan(Plan)
    输出类型: str
    功能: 从同层已开放宿舍中随机选定一个可巡查房间，记进计划；层号无效时记下原地等待，返回原有的目标宿舍
    """
    character_id = plan.character_id
    layer = _get_manager_layer_by_character(character_id)
    if layer <= 0:
        _plan_wait(plan, 5)
        return _get_target_room(character_id)

    # 获取同层已开放宿舍列表，若无可选房间则进入返回舍管房阶段
    room_paths = _get_open_room_paths_by_layer(layer)
    room = random.choice(room_paths) if room_paths else ""
    # 无可选房间时为空，进入返回舍管房阶段；否则进入前往宿舍阶段
    _plan_target_room(plan, room)
    return room


@handle_state_machine.add_state_machine(
    constant.StateMachine.DORMITORY_ADMIN_MOVE_TO_DORM
)
def dormitory_admin_move_to_dorm(character_id: int) -> choice.Plan:
    """
    移动至目标宿舍
    输入类型: character_id(int)
    输出类型: Plan
    功能: 向已选目标宿舍移动，到达后切换到处理问题阶段
    """
    plan = handle_state_machine.new_plan(character_id)
    # 先选定目标宿舍，若无有效目标则进入返回舍管房阶段
    target_room = dormitory_admin_select_room(plan)
    if target_room == "":
        return plan

    target_scene = map_handle.get_map_system_path_for_str(target_room)

    # 前往目标宿舍，途中不显示移动信息
    plan.move(target_scene, show_info_flag=False)
    return plan


@handle_state_machine.add_state_machine(
    constant.StateMachine.DORMITORY_ADMIN_HANDLE_PROBLEM
)
def dormitory_admin_handle_problem(character_id: int) -> choice.Plan:
    """
    处理宿舍问题
    输入类型: character_id(int)
    输出类型: Plan
    功能: 在宿舍处理问题，之后进入返回舍管房阶段
    """
    plan = handle_state_machine.new_plan(character_id)
    plan.set("target_character_id", character_id)
    plan.set("behavior.behavior_id", constant.Behavior.HANDLE_DORMITORY_PROBLEM)
    plan.set("behavior.duration", 30)
    plan.set("state", constant.CharacterStatus.STATUS_HANDLE_DORMITORY_PROBLEM)
    # 清零目标宿舍，进入返回舍管房阶段
    _plan_target_room(plan, "")
    return plan


def ask_copy_key(character_id: int) -> int:
    """
    （要求复制钥匙用）获取交互对象的所在楼层的钥匙
    输入类型: character_id(int)
    输出类型: 无
    功能: 判断交互对象是否为宿舍管理员，若是则获取其负责层号并给予玩家对应层号的钥匙
    """
    character_data: game_type.Character = cache.character_data[character_id]
    target_id = character_data.target_character_id
    # 判断交互对象是否为宿舍管理员，如果不是则不执行
    if not handle_premise.handle_work_is_dormitory_manager(target_id):
        return 0
    # 获取交互对象负责的层号
    layer = _get_manager_layer_by_character(target_id)
    if layer <= 0:
        return 0
    # 给予玩家对应层号的钥匙
    key_item_id = 300 + layer
    inventory.set_item(character_id, key_item_id, 1)
    # 返回钥匙id
    return key_item_id
