"""NPC行为AI：行动前的检查、查找并选择目标活动、自动工作或娱乐、打断当前行动的判断"""

import random
import datetime
from types import FunctionType
from Script.Core import (
    cache_control,
    game_path_config,
    game_type,
    constant,
    value_handle,
    get_text,
)
from Script.Design import attr_calculation, character_move, game_time
from Script.Design import handle_premise, map_handle
from Script.UI.Moudle import draw
from Script.Config import game_config, normal_config
from Script.Modules.domains import abilities, action_info, entertainment
from Script.Modules.domains import facility, flags, hypnosis, needs, roster
from Script.Modules.domains import chara_life

game_path = game_path_config.game_path
cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """
_: FunctionType = get_text._
""" 翻译api """
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1

_handle_npc_ai_in_h = None
""" handle_npc_ai_in_h 模块的延迟导入缓存（规避循环导入，同时消除每角色每轮重复导入的开销） """


def run_npc_pre_behavior_checks(
    character_id: int, pl_start_time: datetime.datetime
) -> None:
    """
    依次执行NPC的行动前检查序列：无法自由移动、助理、跟随、H状态与无意识\n
    疲劳与它引出的收场是事件（gameplay_resolution.events），不在这里\n
    Keyword arguments:\n
    character_id -- 角色id\n
    pl_start_time -- 玩家行动开始时间\n
    """
    # 延迟导入并缓存，避免循环导入且不在热路径反复执行导入机制
    global _handle_npc_ai_in_h
    if _handle_npc_ai_in_h is None:
        from Script.Design import handle_npc_ai_in_h as _in_h_module

        _handle_npc_ai_in_h = _in_h_module
    handle_npc_ai_in_h = _handle_npc_ai_in_h

    judge_character_cant_move(character_id)  # 无法自由移动的角色
    judge_assistant_character(character_id)  # 助理
    judge_character_follow(character_id)  # 跟随模式
    handle_npc_ai_in_h.judge_character_h_obscenity_unconscious(
        character_id, pl_start_time
    )  # H状态、猥亵与无意识


def before_pick(character_id: int) -> None:
    """
    干员选行动之前的行动前检查（run_npc_pre_behavior_checks），以此刻为玩家行动的开始
    Keyword arguments:
    character_id -- 角色id
    """
    run_npc_pre_behavior_checks(character_id, game_time.now())


def early_end(character_id: int) -> bool:
    """
    行动是否提前结束：学生岗赶去上课（judge_student_leave_truncate），
    再是休息、睡觉与工作 / 娱乐中到了淋浴时间（judge_interrupt_character_behavior）；结束时打断角色的行动
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 结束了当前行为时为真
    """
    truncated = judge_student_leave_truncate(character_id)
    return bool(judge_interrupt_character_behavior(character_id)) or truncated


def end_now(character_id: int) -> None:
    """
    立即结束角色当前的行动：打断它在内核里的行动，由它的行为结束（actions.wrap_up）结算
    Keyword arguments:
    character_id -- 角色id
    """
    from Script.Modules.gameplay_resolution import plan_queue

    plan_queue.interrupt(character_id)


def commit_group_sex_tired_exit(character_id: int) -> None:
    """
    力竭的干员退出群交（事件 GroupExit）\n
    退出行为排进它的计划队列，开始时结算退出效果链（1503欲望清零/528补HPMP上限/403重置H状态/635穿回衣服）。\n
    再按玩家所在场景里除它以外仍在H、且还没排上退出的群交成员数收尾：仅剩1人时玩家转为与她的普通H，\n
    无人时结束群交，2人及以上则保持群交模式不变；玩家的收尾行动也排进队列。\n
    排给别人的打断由计划队列交回内核。\n
    Keyword arguments:\n
    character_id -- 力竭退出的NPC角色id\n
    """
    from Script.Modules.gameplay_resolution import plan_queue
    from Script.System.Instruct_System import handle_instruct

    character_data: game_type.Character = cache.character_data[character_id]
    # 目标指向自己并排上退出行为
    character_data.target_character_id = character_id
    handle_instruct.plan_instruct_common_settle(
        constant.Behavior.GROUP_SEX_NPC_HP_0_END, character_id, character_id
    )
    pl_character_data: game_type.Character = cache.character_data[0]
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        pl_character_data.position
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    remaining_ids = [
        chara_id
        for chara_id in scene_data.character_list
        if chara_id
        and chara_id != character_id
        and flags.get(chara_id, "is_h")
        and not plan_queue.plan_has(
            chara_id, constant.Behavior.GROUP_SEX_NPC_HP_0_END
        )
    ]
    # 仅剩1人转为普通H
    if len(remaining_ids) == 1:
        plan_queue.plan_next(
            0,
            constant.Behavior.GROUP_SEX_TO_H,
            0,
            target=remaining_ids[0],
            state=constant.CharacterStatus.STATUS_GROUP_SEX_TO_H,
        )
    # 已无仍在H的成员，结束群交
    elif len(remaining_ids) == 0:
        handle_instruct.plan_group_sex_end()


def judge_assistant_character(character_id: int) -> int:
    """
    处理助理角色的行为\n
    Keyword arguments:
    character_id -- 角色id\n
    Return arguments:
    bool -- 本次update时间切片内活动是否已完成
    """
    # 如果自己不是助理，则返回
    if handle_premise.handle_not_assistant(character_id):
        return 0

    character_data: game_type.Character = cache.character_data[character_id]
    start_time_hour = character_data.behavior.start_time.hour
    now_time_hour = game_time.now().hour
    # 如果超过了12点，则将早安问候设为已问候
    if start_time_hour >= 12 and now_time_hour >= 12:
        flags.set(character_id, morning_salutation=2)
    # 如果早于18点且不是睡觉时间，则清零晚安问候
    if (
        start_time_hour < 18
        and not handle_premise.handle_game_time_is_sleep_time(character_id)
    ):
        flags.set(character_id, night_salutation=0)
    return 1


def judge_character_follow(character_id: int) -> int:
    """
    处理跟随模式
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 本次update时间切片内活动是否已完成
    """
    from Script.Settle import default

    character_data: game_type.Character = cache.character_data[character_id]

    # 智能跟随
    if flags.get(character_id, "is_follow") == 1:
        # 取消所有工作和娱乐状态
        default.handle_cancel_all_work_and_entertainment_flag(
            character_id,
            1,
            game_type.CharacterStatusChange(),
            datetime.datetime(1, 1, 1),
        )
        return 1

    # 维持强制跟随的状态：跟随，不在玩家身边时先走向玩家
    if flags.get(character_id, "is_follow") == 2:
        from Script.Modules.gameplay_resolution import plan_queue

        if character_data.position == cache.character_data[0].position:
            plan_queue.plan_next(
                character_id,
                constant.Behavior.FOLLOW,
                1,
                target=character_id,
                state=constant.CharacterStatus.STATUS_FOLLOW,
            )
            return 1
        _move_type, _path, move_path, move_time = character_move.character_move(
            character_id, cache.character_data[0].position
        )
        plan_queue.plan_next(
            character_id,
            constant.Behavior.MOVE,
            move_time,
            target=character_id,
            state=constant.CharacterStatus.STATUS_FOLLOW,
            fields={"behavior.move_target": move_path},
        )
        return 1
    return 0


def judge_character_cant_move(character_id: int) -> int:
    """
    无法自由移动的角色\n
    Keyword arguments:
    character_id -- 角色id\n
    Return arguments:
    bool -- 本次update时间切片内活动是否已完成
    """
    talent = abilities.talent(character_id)
    character_data: game_type.Character = cache.character_data[character_id]

    cant_move_flag = False

    # 被囚禁
    if flags.get(character_id, "imprisonment"):
        cant_move_flag = True
        # 如果不在自己的监狱，且玩家不在关押区，不在H中，则瞬移回自己的监狱
        if (
            not handle_premise.handle_in_detention_area(0)
            and handle_premise.handle_not_in_dormitory(character_id)
            and not flags.get(character_id, "is_h")
        ):
            dormitory_list = map_handle.get_map_system_path_for_str(
                chara_life.dormitory(character_id)
            )
            map_handle.character_move_scene(
                character_data.position, dormitory_list, character_id
            )

    # 临盆和产后
    if talent[22] == 1 or talent[23] == 1:
        cant_move_flag = True
        needs.set(character_id, desire=0)  # 欲望锁0
        # character.init_character_behavior_start_time(character_id, cache.game_time)
        # character_data.behavior.behavior_id = constant.Behavior.WAIT
        # character_data.state = constant.CharacterStatus.STATUS_WAIT

        # 检测当前位置是否在医疗部的住院部，如果不在的话则移动至住院部
        now_position = character_data.position
        now_scene_str = map_handle.get_map_system_path_str_for_list(
            now_position
        )
        now_scene_data = cache.scene_data[now_scene_str]
        if "Inpatient_Department" not in now_scene_data.scene_tag:
            to_Inpatient_Department = map_handle.get_map_system_path_for_str(
                random.choice(constant.place_data["Inpatient_Department"])
            )
            map_handle.character_move_scene(
                character_data.position, to_Inpatient_Department, character_id
            )
    return cant_move_flag


def choose_state_machine(character_id: int) -> int | None:
    """
    查询角色可用目标活动，选出状态机
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int | None -- 状态机id；角色在H中、是木头人或没有可做的行动时为 None
    """
    all_target_list = list(game_config.config_target.keys())
    premise_data: dict[str, float] = {}
    target_weight_data: dict[str, float] = {}
    null_target_set: set[str] = set()

    # 体控催眠的木头人不赋予新活动，原地等着（睡眠、时停等6异常时例外）
    if hypnosis.of(character_id)[
        "blockhead"
    ] and handle_premise.handle_normal_6(character_id):
        return None
    # 如果该NPC在H模式
    if flags.get(character_id, "is_h"):
        # 群交中+要群交自慰时，才能继续下去
        if handle_premise.handle_group_sex_mode_on(
            character_id
        ) and handle_premise.handle_masturebate_flag_3(character_id):
            pass
        # 否则不赋予新活动，等玩家的下一个行动
        else:
            return None

    # 首先判定是否有高优先级的行动
    type_0_target_list = game_config.config_target_type_index[0]
    target, __, judge, new_premise_data = search_target(
        character_id,
        type_0_target_list,
        null_target_set,
        premise_data,
        target_weight_data,
    )
    # 将行动列表加到null_target中，将新的前提数据加到premise_data中
    null_target_set.update(type_0_target_list)
    premise_data = new_premise_data
    # 然后判断需求，先判断需求链中的需求，再判断非链中的需求，最后判断是否需要进入需求链
    if judge == 0 and not handle_premise.handle_normal_1(character_id):
        now_target_list = game_config.config_target_type_index[12]
        target, __, judge, new_premise_data = search_target(
            character_id,
            now_target_list,
            null_target_set,
            premise_data,
            target_weight_data,
            get_first_only=True,
        )
        null_target_set.update(now_target_list)
        premise_data = new_premise_data
    # 非链中的需求
    if judge == 0 and handle_premise.handle_unnormal_27(character_id):
        now_target_list = game_config.config_target_type_index[13]
        target, __, judge, new_premise_data = search_target(
            character_id,
            now_target_list,
            null_target_set,
            premise_data,
            target_weight_data,
            get_first_only=True,
        )
        null_target_set.update(now_target_list)
        premise_data = new_premise_data
    # 进入需求链
    if judge == 0:
        now_target_list = game_config.config_target_type_index[11]
        target, __, judge, new_premise_data = search_target(
            character_id,
            now_target_list,
            null_target_set,
            premise_data,
            target_weight_data,
            get_first_only=True,
        )
        null_target_set.update(now_target_list)
        premise_data = new_premise_data
    # 然后判断助理，先判断助理服务链，再判断非链中的助理服务，最后判断是否要进入助理服务链
    if judge == 0 and handle_premise.handle_is_assistant(character_id):
        # 是否正在助理服务链中
        if (
            judge == 0
            and handle_premise.handle_assistant_salutation_of_ai_disable(
                character_id
            )
        ):
            now_target_list = game_config.config_target_type_index[42]
            target, __, judge, new_premise_data = search_target(
                character_id,
                now_target_list,
                null_target_set,
                premise_data,
                target_weight_data,
            )
            null_target_set.update(now_target_list)
            premise_data = new_premise_data
        # 是否进行非链的助理服务
        if judge == 0:
            now_target_list = game_config.config_target_type_index[43]
            target, __, judge, new_premise_data = search_target(
                character_id,
                now_target_list,
                null_target_set,
                premise_data,
                target_weight_data,
            )
            null_target_set.update(now_target_list)
            premise_data = new_premise_data
        # 是否进入助理服务链
        if judge == 0:
            now_target_list = game_config.config_target_type_index[41]
            target, __, judge, new_premise_data = search_target(
                character_id,
                now_target_list,
                null_target_set,
                premise_data,
                target_weight_data,
            )
            null_target_set.update(now_target_list)
            premise_data = new_premise_data
    if judge == 0 and handle_premise.handle_have_work(character_id):
        # 当前工作数据
        work_type_id = chara_life.work_type(character_id)
        work_type_data = game_config.config_work_type[work_type_id]
        # 进行工作
        if judge == 0:
            # 判断是否存在自动ai工作流程
            if work_type_data.auto_ai and (
                handle_premise.common_place_judge_by_SceneName(
                    character_id, work_type_data.place
                )
                or handle_premise.common_place_judge_by_SceneTag(
                    character_id, work_type_data.place_tag
                )
            ):
                state_machine_id, new_premise_data = (
                    npc_auto_work_or_entertainment(
                        character_id,
                        premise_data,
                        move_flag=False,
                        work_flag=True,
                    )
                )
                premise_data = new_premise_data
                if state_machine_id:
                    judge = state_machine_id
            # 没有的话则正常寻找
            else:
                now_target_list = game_config.config_target_type_index[22]
                target, __, judge, new_premise_data = search_target(
                    character_id,
                    now_target_list,
                    null_target_set,
                    premise_data,
                    target_weight_data,
                )
                null_target_set.update(now_target_list)
                premise_data = new_premise_data
        # 工作准备
        if judge == 0:
            # 判断是否存在自动ai工作流程
            if work_type_data.auto_ai:
                state_machine_id, new_premise_data = (
                    npc_auto_work_or_entertainment(
                        character_id,
                        premise_data,
                        move_flag=True,
                        work_flag=True,
                    )
                )
                premise_data = new_premise_data
                if state_machine_id:
                    judge = state_machine_id
            # 没有的话则正常寻找
            else:
                now_target_list = game_config.config_target_type_index[21]
                target, __, judge, new_premise_data = search_target(
                    character_id,
                    now_target_list,
                    null_target_set,
                    premise_data,
                    target_weight_data,
                )
                null_target_set.update(now_target_list)
                premise_data = new_premise_data
    # 然后判断娱乐，需要在娱乐时间
    if judge == 0 and handle_premise.handle_all_entertainment_time(
        character_id
    ):
        # 当前娱乐数据
        enter_time = game_time.judge_entertainment_time(character_id) - 1
        entertainment_type_id = chara_life.entertainment_type(character_id)[
            enter_time
        ]
        entertainment_type_data = game_config.config_entertainment[
            entertainment_type_id
        ]
        # 进行娱乐
        if judge == 0:
            # 判断是否存在自动ai娱乐流程
            if entertainment_type_data.auto_ai and (
                handle_premise.common_place_judge_by_SceneName(
                    character_id, entertainment_type_data.place
                )
                or handle_premise.common_place_judge_by_SceneTag(
                    character_id, entertainment_type_data.place_tag
                )
            ):
                state_machine_id, new_premise_data = (
                    npc_auto_work_or_entertainment(
                        character_id,
                        premise_data,
                        move_flag=False,
                        work_flag=False,
                    )
                )
                premise_data = new_premise_data
                if state_machine_id:
                    judge = state_machine_id
            # 没有的话则正常寻找
            else:
                now_target_list = game_config.config_target_type_index[32]
                target, __, judge, new_premise_data = search_target(
                    character_id,
                    now_target_list,
                    null_target_set,
                    premise_data,
                    target_weight_data,
                )
                null_target_set.update(now_target_list)
                premise_data = new_premise_data
        # 娱乐后处理
        if judge == 0:
            now_target_list = game_config.config_target_type_index[33]
            target, __, judge, new_premise_data = search_target(
                character_id,
                now_target_list,
                null_target_set,
                premise_data,
                target_weight_data,
            )
            null_target_set.update(now_target_list)
            premise_data = new_premise_data
        # 娱乐准备
        if judge == 0:
            # 判断是否存在自动ai娱乐流程
            if entertainment_type_data.auto_ai:
                state_machine_id, new_premise_data = (
                    npc_auto_work_or_entertainment(
                        character_id,
                        premise_data,
                        move_flag=True,
                        work_flag=False,
                    )
                )
                premise_data = new_premise_data
                if state_machine_id:
                    judge = state_machine_id
            # 没有的话则正常寻找
            else:
                now_target_list = game_config.config_target_type_index[31]
                target, __, judge, new_premise_data = search_target(
                    character_id,
                    now_target_list,
                    null_target_set,
                    premise_data,
                    target_weight_data,
                )
                null_target_set.update(now_target_list)
                premise_data = new_premise_data

    # 如果以上都没有，则遍历所有大类的目标行动
    if judge == 0:
        target, __, judge, new_premise_data = search_target(
            character_id,
            all_target_list,
            null_target_set,
            premise_data,
            target_weight_data,
        )
    if not judge:
        return None
    # judge 为 1 时选中的是目标，否则是ai自动补完的工作或娱乐行动的状态机
    if judge == 1:
        return game_config.config_target[target].state_machine_id
    return judge


def search_target(
    character_id: int,
    target_list: list,
    null_target: set,
    premise_data: dict[str, float],
    target_weight_data: dict[str, float],
    get_first_only: bool = False,
) -> tuple[str, float, int, dict[str, float]]:
    """
    查找可用目标\n
    Keyword arguments:\n
    character_id -- 角色id\n
    target_list -- 检索的目标列表\n
    null_target -- 被排除的目标\n
    premise_data -- 已算出的前提权重\n
    target_weight_data -- 已算出权重的目标列表\n
    get_first_only -- 是否只获取第一个符合条件的目标，默认False\n
    Return arguments:\n
    int -- 目标id\n
    float -- 目标权重\n
    bool -- 前提是否能够被满足\n
    Dict[str, float] -- 新的前提数据\n
    """
    target_data: dict[float, set[str]] = {}
    for target in target_list:
        if target in null_target:
            continue
        if target in target_weight_data:
            target_data.setdefault(target_weight_data[target], set())
            target_data[target_weight_data[target]].add(target)
            continue
        if target not in game_config.config_target_premise_data:
            target_weight_data[target] = 1
            target_data.setdefault(1, set())
            target_data[1].add(target)
            continue
        target_premise_list = game_config.config_target_premise_data[target]
        now_weight: float = 0
        now_target_pass_judge = 0
        now_target_data: dict[float, set[str]] = {}
        premise_judge: float = 1
        # 按前提id排序后判断，使判断前提时抽的随机数不随集合的遍历顺序变化。
        for premise in sorted(target_premise_list):
            premise_judge = 0
            if premise in premise_data:
                premise_judge = premise_data[premise]
            else:
                premise_judge = handle_premise.handle_premise(
                    premise, character_id
                )
                premise_judge = max(premise_judge, 0)
                premise_data[premise] = premise_judge
            if premise_judge:
                now_weight += premise_judge
            else:
                if (
                    premise in game_config.config_effect_target_data
                    and premise not in premise_data
                ):
                    pass
                    # 暂时不用该功能
                    """
                    now_target_list = game_config.config_effect_target_data[premise] - null_target
                    now_target, now_target_weight, now_judge = search_target(
                        character_id,
                        now_target_list,
                        null_target,
                        premise_data,
                        target_weight_data,
                    )
                    if now_judge:
                        now_target_data.setdefault(now_target_weight, set())
                        now_target_data[now_target_weight].add(now_target)
                        now_weight += now_target_weight
                    else:
                        now_target_pass_judge = 1
                        break
                    """
                else:
                    now_target_pass_judge = 1
                    break
        if now_target_pass_judge:
            null_target.add(target)
            target_weight_data[target] = 0
            continue
        if premise_judge:
            target_data.setdefault(now_weight, set())
            target_data[now_weight].add(target)
            target_weight_data[target] = now_weight
            # 如果只获取第一个符合条件的目标，则直接返回
            if get_first_only:
                return target, now_weight, 1, premise_data
            # 如果权重已经大于100，则直接返回
            if now_weight >= 100:
                return target, now_weight, 1, premise_data
        else:
            now_value_weight = value_handle.get_rand_value_for_value_region(
                list(now_target_data.keys())
            )
            target_data.setdefault(now_weight, set())
            # 集合的遍历顺序随字符串哈希变化。排序后，同一随机状态总挑中同一个目标。
            target_data[now_weight].add(
                random.choice(sorted(now_target_data[now_value_weight]))
            )
    if len(target_data):
        value_weight = value_handle.get_rand_value_for_value_region(
            list(target_data.keys())
        )
        # 集合的遍历顺序随字符串哈希变化。排序后，同一随机状态总挑中同一个目标。
        final_target = random.choice(sorted(target_data[value_weight]))
        return final_target, value_weight, 1, premise_data
    return "", 0, 0, premise_data


def npc_auto_work_or_entertainment(
    character_id: int,
    premise_data: dict[str, float],
    move_flag: bool,
    work_flag: bool,
) -> tuple[int, dict[str, float]]:
    """
    NPC自动工作或娱乐\n
    Keyword arguments:\n
    character_id -- 角色id\n
    premise_data -- 前提数据\n
    move_flag -- 是否移动\n
    work_flag -- 是否工作\n
    Return arguments:\n
    int -- 状态机id\n
    Dict[str, float] -- 新的前提数据\n
    """

    # 工作
    if work_flag:
        # 当前工作数据
        work_type_id = chara_life.work_type(character_id)
        work_type_data = game_config.config_work_type[work_type_id]
        tem_premise_data = {"work_time"}
        # 进行工作
        if move_flag:
            tem_premise_data.add("normal_all")
            target_data = work_type_data.auto_ai_move
        else:
            tem_premise_data.add("normal_all_except_special_hypnosis")
            target_data = work_type_data.auto_ai_work
    # 娱乐
    else:
        enter_time = game_time.judge_entertainment_time(character_id) - 1
        entertainment_type_id = chara_life.entertainment_type(character_id)[
            enter_time
        ]
        entermainment_type_data = game_config.config_entertainment[
            entertainment_type_id
        ]
        tem_premise_data = {"all_entertainment_time"}
        # 进行娱乐
        if move_flag:
            tem_premise_data.add("normal_all")
            target_data = entermainment_type_data.auto_ai_move
        else:
            tem_premise_data.add("normal_all_except_special_hypnosis")
            target_data = entermainment_type_data.auto_ai_entertainment
    # 进行判断
    if "|" in target_data:
        state_machine_id = int(target_data.split("|")[0])
        extra_premise = target_data.split("|")[1]
        tem_premise_data.add(extra_premise)
    else:
        state_machine_id = int(target_data)
    judge = True
    # 开始遍历前提。按前提id排序后判断，使判断前提时抽的随机数不随集合的遍历顺序变化。
    for premise in sorted(tem_premise_data):
        premise_judge: float = 0
        if premise in premise_data:
            premise_judge = premise_data[premise]
        else:
            premise_judge = handle_premise.handle_premise(premise, character_id)
            premise_judge = max(premise_judge, 0)
            premise_data[premise] = premise_judge
        if not premise_judge:
            judge = False
            break
    # 如果前提都满足，则返回状态机id
    if judge:
        return state_machine_id, premise_data
    return 0, premise_data


def judge_student_leave_truncate(character_id: int) -> bool:
    """
    学生岗赶去上课：到了应离开的时刻（class_ai.get_student_leave_time）就结束当前的工作 / 娱乐行为
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 是否结束了当前行为
    功能: 待赴实操课提前退场（口径 62），没课的节次到了下一节开课前收手，人已在上课地点或今天已翘课的到开课那一刻收手。
          由每 5 分钟的 Tick 判，最多晚 4 分钟
    """
    character_data: game_type.Character = cache.character_data[character_id]
    # 这一分钟刚开始的行为不判，否则"结束→AI重选同一行为→再结束"会使NPC行为循环永不收敛
    if (
        game_time.judge_date_big_or_small(
            game_time.now(), character_data.behavior.start_time
        )
        != 1
    ):
        return False
    from Script.System.Education_System import class_ai

    leave_time = class_ai.get_student_leave_time(character_id)
    if leave_time is None or game_time.now() < leave_time:
        return False
    end_now(character_id)
    return True


def get_salutation_wake_time(character_id: int) -> datetime.datetime | None:
    """
    早安问候的助理睡觉时该醒的时刻：玩家计划起床的时刻\n
    Keyword arguments:
    character_id -- 角色id\n
    Return arguments:
    datetime | None -- 睡觉中、早安问候服务开启、今日未问候、没吃安眠药，
        行动结束时间晚于游戏时间且晚于玩家起床时刻、行动还是 480 分钟（未截过）时为玩家起床的时刻，否则为 None
    """
    character_data: game_type.Character = cache.character_data[character_id]
    if not (
        handle_premise.handle_action_sleep(character_id)
        and handle_premise.handle_self_not_sleep_pills(character_id)
        and handle_premise.handle_assistant_morning_salutation_on(character_id)
        and handle_premise.handle_morning_salutation_flag_0(character_id)
        and handle_premise.handle_chara_behavior_end_time_lateer_than_game_time(
            character_id
        )
        and character_data.behavior.duration == 480
    ):
        return None
    end_time = game_time.get_sub_date(
        minute=character_data.behavior.duration,
        old_date=character_data.behavior.start_time,
    )
    wake_hour, wake_minute = action_info.get(0, "plan_to_wake_time")[:2]
    wake_up_time = end_time.replace(hour=wake_hour, minute=wake_minute)
    if not game_time.judge_date_big_or_small(end_time, wake_up_time):
        return None
    return wake_up_time


def judge_interrupt_character_behavior(character_id: int) -> int:
    """
    判断是否需要打断角色的当前行动\n
    Keyword arguments:
    character_id -- 角色id\n
    Return arguments:
    int -- 是否打断，1为打断
    功能: 休息、睡觉与工作 / 娱乐中到了淋浴时间，以及早安问候的助理到了玩家起床的时刻，都立即结束当前行动（end_now）。
          学生岗赶去上课在 judge_student_leave_truncate
    """
    character_data: game_type.Character = cache.character_data[character_id]

    # 本轮内刚赋予的行为（开始时间不早于当前游戏时间）不做打断判定，
    # 否则"打断→AI重选同一行为→再打断"会使NPC行为循环永不收敛
    if (
        game_time.judge_date_big_or_small(
            game_time.now(), character_data.behavior.start_time
        )
        != 1
    ):
        return 0

    # 休息中的相关判断
    if handle_premise.handle_action_rest(character_id):
        # 疲劳归零，且HP、MP满值时，则立刻结束休息
        if (
            handle_premise.handle_tired_le_0(character_id)
            and handle_premise.handle_hp_max(character_id)
            and handle_premise.handle_mp_max(character_id)
        ):
            end_now(character_id)
            return 1

    # 睡觉中的相关判断，需要没有被安眠药
    elif handle_premise.handle_action_sleep(
        character_id
    ) and handle_premise.handle_self_not_sleep_pills(character_id):
        # ①睡觉中，早安问候服务开启中，今日未问候：到了玩家起床的时刻就醒
        wake_up_time = get_salutation_wake_time(character_id)
        if wake_up_time is not None:
            if game_time.now() >= wake_up_time:
                end_now(character_id)
                return 1

        # ②睡觉中，疲劳归零，且HP、MP满值时，当前非睡觉时间，未醉酒，角色行动结束时间晚于游戏时间，则立刻结束睡觉
        # 醉酒豁免与settle_sleep自然醒的豁免保持一致，否则烂醉爆睡的角色会被立刻叫醒后又立刻重新爆睡，形成死循环
        if (
            handle_premise.handle_tired_le_0(character_id)
            and handle_premise.handle_hp_max(character_id)
            and handle_premise.handle_mp_max(character_id)
            and not handle_premise.handle_game_time_is_sleep_time(character_id)
            and handle_premise.handle_drunk_level_0(character_id)
            and handle_premise.handle_chara_behavior_end_time_lateer_than_game_time(
                character_id
            )
        ):
            end_now(character_id)
            return 1

    # 工作或娱乐中的相关判断
    elif handle_premise.handle_action_work_or_entertainment(character_id):
        # 今日未洗澡，到了淋浴时间，距离行动结束时间还有至少30分钟，正常状态下，则立刻结束工作或娱乐
        if (
            handle_premise.handle_shower_flag_0(character_id)
            and handle_premise.handle_shower_time(character_id)
            and handle_premise.handle_still_30_minutes_before_end(character_id)
            and handle_premise.handle_normal_all(character_id)
        ):
            end_now(character_id)
            # print(f"debug {character_data.name}立刻结束工作或娱乐，当前时间={cache.game_time}")
            return 1

    return 0


def judge_same_position_npc_follow() -> None:
    """
    玩家移动时，同位置智能跟随的NPC跟着走：移动（或在门外等待）排进它的计划队列并打断它当前的行动；\n
    隐奸携带模式中被携带的角色直接随玩家换场景\n
    Keyword arguments:\n
    无
    """
    from Script.Modules.gameplay_resolution import plan_queue

    pl_character_data: game_type.Character = cache.character_data[0]
    for character_id in roster.active():
        character_data: game_type.Character = cache.character_data[character_id]
        # 跳过不在同一位置的NPC
        if character_data.position != pl_character_data.position:
            continue
        # 智能跟随、异常状态267正常
        if flags.get(
            character_data.cid, "is_follow"
        ) == 1 and handle_premise.handle_normal_267(character_id):

            # 变成移动状态，目标为玩家位置
            _move_type, _path, move_path, move_time = (
                character_move.character_move(
                    character_id, pl_character_data.behavior.move_final_target
                )
            )
            move_flag, wait_flag = (
                character_move.judge_character_move_to_private(
                    character_id, move_path
                )
            )
            if move_flag:
                plan_queue.plan_next(
                    character_id,
                    constant.Behavior.MOVE,
                    move_time,
                    target=character_id,
                    state=constant.CharacterStatus.STATUS_MOVE,
                    interrupt=True,
                    fields={
                        "behavior.move_target": move_path,
                        "behavior.move_final_target": (
                            pl_character_data.behavior.move_final_target
                        ),
                    },
                )
                action_info.set(character_data.cid, "follow_wait_time", 0)
            elif wait_flag:
                plan_queue.plan_next(
                    character_id,
                    constant.Behavior.WAIT,
                    5,
                    state=constant.CharacterStatus.STATUS_WAIT,
                    interrupt=True,
                )
                action_info.add(character_data.cid, "follow_wait_time", 5)
        elif flags.get(character_data.cid, "hidden_sex_mode") == 5:
            if (
                len(pl_character_data.behavior.move_target)
                and character_data.position
                != pl_character_data.behavior.move_target
            ):
                map_handle.character_move_scene(
                    character_data.position,
                    pl_character_data.behavior.move_target,
                    character_id,
                )


def get_chara_entertainment(character_id: int) -> None:
    """
    刷新角色的娱乐活动\n
    Keyword arguments:\n
    character_id -- 角色id
    """
    week_day = game_time.now().weekday()
    if character_id:
        # 重置基础数据
        flags.set(character_id, swim=0)

        # 如果当天有派对的话，则全员当天娱乐为该娱乐
        if entertainment.party_day(week_day):
            for i in range(3):
                chara_life.entertainment_type.set_item(
                    character_id, i, entertainment.party_day(week_day)
                )

        # 否则随机当天的娱乐活动
        else:
            # 教育系统的常量从配置现算，必须在函数内延迟 import（与本文件里 class_ai 的延迟 import 同款）
            from Script.System.Education_System import education_constant
            from Script.System.Pregnancy_System import pregnancy_constant

            entertainment_list = [i for i in game_config.config_entertainment]
            entertainment_list.remove(0)
            # 照料卵娱乐不进入随机池，仅由每日替换钩子分配给持卵的卵生角色
            if (
                pregnancy_constant.TEND_EGGS_ENTERTAINMENT_ID
                in entertainment_list
            ):
                entertainment_list.remove(
                    pregnancy_constant.TEND_EGGS_ENTERTAINMENT_ID
                )
            # 上课（无课时自习）是孩子的日程专用活动，
            # 只由日程模板指派，随机抽给成年干员没有意义；编号统一取 education_constant.SCHEDULE_ONLY_ENTERTAINMENT_SET
            for (
                schedule_only_id
            ) in education_constant.SCHEDULE_ONLY_ENTERTAINMENT_SET:
                if schedule_only_id in entertainment_list:
                    entertainment_list.remove(schedule_only_id)
            # 循环获得上午、下午、晚上的三个娱乐活动
            for i in range(3):

                # 进入主循环
                while 1:
                    # 开始随机
                    choice_entertainment_id = random.choice(entertainment_list)
                    entertainment_data = game_config.config_entertainment[
                        choice_entertainment_id
                    ]
                    # if choice_entertainment_id in {92, 151}:
                    #     print(f"debug {character_data.name}: {choice_entertainment_id}")
                    # 首先检查娱乐地点的场所是否开放
                    if (
                        entertainment_data.place
                        in game_config.config_facility_open_name_set
                    ):
                        facility_open_cid = (
                            game_config.config_facility_open_name_to_cid[
                                entertainment_data.place
                            ]
                        )
                        # 如果该娱乐活动的场所未开放，则去掉该id后重新随机
                        if facility.is_open(facility_open_cid) == 0:
                            entertainment_list.remove(choice_entertainment_id)
                            continue
                    # 品酒只能在晚上进行
                    if choice_entertainment_id == 62 and i != 2:
                        continue
                    # 检查该娱乐活动是否需要特定的条件
                    if entertainment_data.need == "无":
                        break
                    else:
                        need_data_all = entertainment_data.need
                        # 整理需要的条件
                        if "&" not in need_data_all:
                            need_data_list = [need_data_all]
                        else:
                            need_data_list = need_data_all.split("&")
                        judge, __ = attr_calculation.judge_require(
                            need_data_list, character_id
                        )
                        # 如果满足条件则选择该娱乐活动，否则去掉该id后重新随机
                        if judge:
                            break
                        else:
                            entertainment_list.remove(choice_entertainment_id)
                            continue

                # 跳出循环后，将该娱乐活动赋值给角色
                chara_life.entertainment_type.set_item(
                    character_id, i, choice_entertainment_id
                )
                entertainment_list.remove(
                    choice_entertainment_id
                )  # 从列表中去掉该娱乐活动，防止重复


def select_random_free_character(character_id: int) -> int:
    """
    选择在场的一位空闲的随机角色
    Keyword arguments:
    character_id -- 自己的角色id
    Return arguments:
    int -- 对方的角色id
    """
    character_data: game_type.Character = cache.character_data[character_id]
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        character_data.position
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    available_characters = []
    # 遍历所有角色
    for chara_id in scene_data.character_list:
        # 跳过自己
        if chara_id == character_id:
            continue
        now_character_data = cache.character_data[chara_id]
        # 跳过H状态
        if flags.get(now_character_data.cid, "is_h"):
            continue
        # 跳过正在移动的
        if handle_premise.handle_action_move(chara_id):
            continue
        # 跳过正在睡觉的
        if handle_premise.handle_action_sleep(chara_id):
            continue
        # 跳过双隐
        if handle_premise.handle_hidden_sex_mode_4(chara_id):
            continue
        # 跳过玩家的男隐
        if chara_id == 0 and handle_premise.handle_hidden_sex_mode_3(chara_id):
            continue
        # 跳过非玩家的女隐
        if chara_id != 0 and handle_premise.handle_hidden_sex_mode_2(chara_id):
            continue
        # 检查是否有人正在对其互动
        interacting_character_end_info = action_info.get(
            now_character_data.cid, "interacting_character_end_info"
        )
        # 如果有人正在对其互动，且不是自己的话
        if (
            interacting_character_end_info[0] != -1
            and interacting_character_end_info[0] != character_id
        ):
            # 检查互动结束时间
            interacting_character_end_time = interacting_character_end_info[1]
            # 如果自己的行动开始时间晚于对方的互动结束时间，则跳过
            if (
                game_time.judge_date_big_or_small(
                    character_data.behavior.start_time,
                    interacting_character_end_time,
                )
                < 0
            ):
                continue
        available_characters.append(chara_id)
    if not available_characters:
        return -1  # 无空闲角色
    return random.choice(available_characters)
