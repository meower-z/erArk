"""
隐奸结算服务（hidden_sex_service）
==================================
提供隐奸流程、隐蔽等级判定、同场景角色筛选、隐蔽值结算、被发现判定与结算、露出模式更新，
以及目睹H发现行动的排队与开始。
本模块不直接导入界面面板模块。
被发现结算与发现行动开始均调用 hidden_sex_discovered.resolve 结算「H中被发现」选择。
"""

import random

from Script.Config import game_config
from Script.Core import constant
from Script.Design import handle_ability, handle_premise, map_handle
from Script.Modules.domains import abilities, activity, flags, h_state
from Script.Modules.domains import identity, scene_state
from Script.Modules.gameplay_resolution import hidden_sex_discovered
from Script.Modules.gameplay_resolution import plan_queue, starts
from Script.Modules.gameplay_resolution.intent import Intent

DISCOVERY = "Discovery"
""" 目睹H发现行动的种类标识。 """


@starts.starter(DISCOVERY)
def start_discovery(who: int, intent: Intent) -> None:
    """
    作为 DISCOVERY 行动的开始函数，调用 hidden_sex_discovered.resolve(who, False) 结算发现选择。
    Keyword arguments:
    who -- int，发现者的角色编号
    intent -- Intent，内核传入的行动意图，本函数不读取该参数
    Return arguments:
    None -- 无返回值
    """
    hidden_sex_discovered.resolve(who, False)


def plan_discovery(character_id: int) -> None:
    """
    将 1 分钟的 DISCOVERY 等待行动排入发现者的计划队列，并请求打断其当前行动。
    排入的行动使用 constant.Behavior.WAIT 行为与 constant.CharacterStatus.STATUS_WAIT 状态。
    Keyword arguments:
    character_id -- int，发现者的角色编号
    Return arguments:
    None -- 无返回值
    """
    plan_queue.plan_next(
        character_id,
        constant.Behavior.WAIT,
        1,
        kind=DISCOVERY,
        state=constant.CharacterStatus.STATUS_WAIT,
        interrupt=True,
    )


def handle_hidden_sex_flow(
    character_id: int = 0,
    add_flag: bool | None = None,
    now_duration: int = 0,
    now_intensity: int = 0,
) -> None:
    """
    处理隐奸整体流程：先结算隐蔽值，再判断是否被发现
    参数:
        character_id (int): 角色id，默认为0（玩家）
        add_flag (bool): 是否增加隐蔽值，默认为None，表示根据行为类型判断
        now_duration (int): 行为持续时间，默认为0，表示使用当前行为的持续时间
        now_intensity (int): 行为强度，默认为0，表示使用当前行为的默认强度
    返回:
        None
    """
    if not handle_premise.handle_place_someone_not_in_hidden_and_conscious(
        character_id
    ):
        return
    settle_hidden_value_by_action(
        character_id, add_flag, now_duration, now_intensity
    )
    discovered = check_hidden_sex_discovery(
        h_state.get(character_id, "hidden_sex_discovery_dregree")
    )
    if discovered:
        settle_discovered(character_id)


def get_hidden_level(value: int) -> tuple[int, str]:
    """
    按当前隐蔽值返回当前隐蔽等级的str\n
    Keyword arguments:\n
    value -- 隐蔽值\n
    Return arguments:\n
    int -- 隐蔽等级,0-3\n
    str -- 隐蔽等级名
    """
    for now_cid in game_config.config_hidden_level:
        now_data = game_config.config_hidden_level[now_cid]
        if value > now_data.hidden_point:
            continue
        else:
            return now_cid, now_data.name
    return 3, game_config.config_hidden_level[3].name


def get_hidden_sex_targets(character_id: int) -> list[int]:
    """
    功能: 返回指定玩家的隐奸对象角色id列表
    参数:
        character_id (int): 玩家角色id
    返回:
        List[int]: 同场景中除玩家以外处于隐奸模式的角色id列表
    """
    position = activity.position(character_id)
    scene_path = map_handle.get_map_system_path_str_for_list(position)
    result: list[int] = []
    for chara_id in scene_state.occupants(scene_path):
        if chara_id == character_id:
            continue
        if handle_premise.handle_hidden_sex_mode_ge_1(chara_id):
            result.append(chara_id)
    return result


def get_nearby_conscious_unfallen_characters(character_id: int) -> list[int]:
    """
    功能: 返回指定角色所在地点中，不在隐奸中，有意识且未睡眠的其他角色列表
    参数:
        character_id (int): 角色id
    返回:
        List[int]: 符合条件的角色id列表
    """
    position = activity.position(character_id)
    scene_path = map_handle.get_map_system_path_str_for_list(position)
    result: list[int] = []
    for chara_cid in scene_state.occupants(scene_path):
        if chara_cid == character_id:
            continue
        if handle_premise.handle_hidden_sex_mode_ge_1(chara_cid):
            continue
        if handle_premise.handle_unconscious_flag_ge_1(chara_cid):
            continue
        if handle_premise.handle_action_sleep(chara_cid):
            continue
        result.append(chara_cid)
    return result


def settle_hidden_value_by_action(
    character_id: int = 0,
    add_flag: bool | None = None,
    now_duration: int = 0,
    now_intensity: int = 0,
) -> None:
    """
    根据玩家当前的行为和其他因素来结算角色的隐蔽值
    参数:
        character_id (int): 角色id，默认为0，表示玩家角色
        add_flag (bool): 是否增加隐蔽值，默认为None，表示根据行为类型判断
        now_duration (int): 行为持续时间，默认为0，表示使用当前行为的持续时间
        now_intensity (int): 行为强度，默认为0，表示使用当前行为的默认强度
    返回:
        None
    """
    now_behavior_id = activity.behavior(character_id).behavior_id
    behavior_data = game_config.config_behavior[now_behavior_id]
    if add_flag is None:
        add_flag = False
        for tag in {"猥亵", "性爱"}:
            if tag in behavior_data.tag:
                add_flag = True
                break
        if now_behavior_id == constant.Behavior.WAIT:
            add_flag = False
        if now_behavior_id == constant.Behavior.CARRY_MOVE:
            add_flag = True
    if now_duration == 0:
        now_duration = activity.behavior(character_id).duration
    mode_adjust: float = 1
    if handle_premise.handle_hidden_sex_mode_1(character_id):
        mode_adjust = 2
    elif handle_premise.handle_hidden_sex_mode_4(character_id):
        mode_adjust = 0.5
    if now_intensity == 0:
        now_intensity = 1
        tag_list = behavior_data.tag.split("|")
        for tag in tag_list:
            if tag == "道具":
                now_intensity = max(4, now_intensity)
            elif tag == "插入":
                now_intensity = max(3, now_intensity)
            elif tag == "侍奉":
                now_intensity = max(2, now_intensity)
    now_ability_lv = abilities.ability(character_id)[90]
    abi_adjust = handle_ability.get_ability_adjust(now_ability_lv)
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )
    other_chara_adjust = max(len(scene_state.occupants(scene_path_str)) - 2, 1)
    if add_flag:
        adjust = now_intensity * mode_adjust / abi_adjust * other_chara_adjust
    else:
        adjust = -2 / mode_adjust * abi_adjust
    delta = int(now_duration * adjust)
    new_degree = (
        h_state.get(character_id, "hidden_sex_discovery_dregree") + delta
    )
    h_state.set(
        character_id,
        hidden_sex_discovery_dregree=max(min(new_degree, 100), 0),
    )


def check_hidden_sex_discovery(now_degree: int) -> bool:
    """
    判断隐奸行为是否被发现
    参数:
        now_degree (int): 当前隐蔽值
    返回:
        bool: True-已被发现, False-未被发现
    """
    hidden_lv, _ = get_hidden_level(now_degree)
    if hidden_lv < 2:
        return False
    discover_rate = (
        now_degree - game_config.config_hidden_level[1].hidden_point
    ) * 3
    random_value = random.randint(0, 100)
    if discover_rate >= random_value:
        return True
    return False


def settle_discovered(character_id: int) -> None:
    """
    结算角色隐奸被发现后的状态并在有旁观者时发起发现选择结算。
    先记录该角色 hidden_sex_mode 是否大于 0，并获取隐奸对象，
    以及同场景中不在隐奸中、有意识、未睡眠且 see_pl_h 为假的旁观者。
    随后清零该角色与各隐奸对象的 hidden_sex_mode。
    存在隐奸对象时将角色交互目标设为首位隐奸对象，否则打印调试信息并返回。
    若存在剩余旁观者，以首位旁观者编号与前述标志调用 hidden_sex_discovered.resolve。
    Keyword arguments:
    character_id -- int，被发现的角色编号
    Return arguments:
    None -- 无返回值
    """
    from_hidden_sex_flag = flags.get(character_id, "hidden_sex_mode") > 0
    hidden_sex_target_id_list = get_hidden_sex_targets(character_id)
    interrupt_chara_list = get_nearby_conscious_unfallen_characters(
        character_id
    )
    interrupt_chara_list = [
        chara_id
        for chara_id in interrupt_chara_list
        if not flags.get(chara_id, "see_pl_h")
    ]
    flags.set(character_id, hidden_sex_mode=0)
    for hidden_target_id in hidden_sex_target_id_list:
        flags.set(hidden_target_id, hidden_sex_mode=0)
    if len(hidden_sex_target_id_list):
        activity.set_target(character_id, hidden_sex_target_id_list[0])
    else:
        print(f"debug : 隐奸被发现时未找到隐奸对象，角色id:{character_id}")
        return
    if len(interrupt_chara_list):
        hidden_sex_discovered.resolve(
            interrupt_chara_list[0], from_hidden_sex_flag
        )


def update_exhibiionism_sex_mode() -> None:
    """
    按主角当前场景更新主角与同场景露出对象的露出模式。
    主角的 exhibitionism_sex_mode 为 0 时直接返回。
    场景超过两人且除主角与其交互对象外另有清醒未睡眠角色时设为 3，
    超过两人且无此类角色时设为 4，不超过两人且室外时设为 2，否则设为 1。
    写入主角后，将该模式同步给同场景首位 exhibitionism_sex_mode 非 0 的其他角色。
    Return arguments:
    None -- 无返回值
    """
    if flags.get(0, "exhibitionism_sex_mode") == 0:
        return
    if handle_premise.handle_scene_over_two(0):
        if handle_premise.handle_scene_others_conscious(0):
            new_mode = 3
        else:
            new_mode = 4
    else:
        if handle_premise.handle_place_outdoor(0):
            new_mode = 2
        else:
            new_mode = 1
    flags.set(0, exhibitionism_sex_mode=new_mode)
    now_scene_character_list = map_handle.get_chara_now_scene_all_chara_id_list(
        0, remove_own_character=True
    )
    for chara_id in now_scene_character_list:
        target_character_data: identity.Identity = identity.of(chara_id)
        if flags.get(target_character_data.cid, "exhibitionism_sex_mode") != 0:
            flags.set(
                target_character_data.cid, exhibitionism_sex_mode=new_mode
            )
            break
