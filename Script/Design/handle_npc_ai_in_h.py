"""H 中的 NPC AI：无意识 H 的判断与结算、NPC 逆推、群交中的行动与抢占"""

from __future__ import annotations

import datetime
import random
from types import FunctionType
from Script.Core import (
    cache_control,
    game_path_config,
    game_type,
    constant,
    get_text,
)
from Script.Design import (
    handle_premise,
    attr_calculation,
    map_handle,
    child_stage_gate,
    virgin_break_gate,
)
from Script.UI.Moudle import draw
from Script.Config import game_config, normal_config
from Script.Design import game_time

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

_settle_default = None
""" Script.Settle.default 模块的延迟导入缓存（规避循环导入，同时消除每角色每轮重复导入的开销） """


def judge_character_h_obscenity_unconscious(
    character_id: int, pl_start_time: datetime.datetime
) -> int:
    """
    判断H状态、猥亵与无意识\n
    Keyword arguments:
    character_id -- 角色id\n
    pl_start_time -- 玩家行动开始时间\n
    Return arguments:
    bool -- 本次update时间切片内活动是否已完成
    """
    # 延迟导入并缓存，避免循环导入且不在热路径反复执行导入机制
    global _settle_default
    if _settle_default is None:
        from Script.Settle import default as _settle_default_module

        _settle_default = _settle_default_module
    default = _settle_default
    character_data: game_type.Character = cache.character_data[character_id]
    pl_character_data: game_type.Character = cache.character_data[0]

    # 玩家部分
    if character_id == 0:
        # 清空空气催眠位置
        if (
            character_data.position
            != character_data.pl_ability.air_hypnosis_position
        ):
            character_data.pl_ability.air_hypnosis_position = ""
        # 如果前指令是口交类型则重置所有阴茎污浊状态
        if handle_premise.handle_last_cmd_blowjob_type(0):
            for dirty_key in character_data.dirty.penis_dirty_dict:
                character_data.dirty.penis_dirty_dict[dirty_key] = False
        # 当前有H体位下，如果进行手、口、胸类则清零H体位数据
        if handle_premise.handle_dr_have_sex_position(0):
            if (
                handle_premise.handle_last_cmd_handjob_type(0)
                or handle_premise.handle_last_cmd_blowjob_type(0)
                or handle_premise.handle_last_cmd_paizuri_type(0)
            ):
                character_data.h_state.current_sex_position = -1
        # 当前有子宫性交位置下，如果阴茎位置不是阴道或子宫，则清零子宫性交位置数据
        if handle_premise.handle_dr_have_sex_position(0):
            if character_data.h_state.insert_position not in [6, 7]:
                character_data.h_state.current_womb_sex_position = 0
        # 刚刚射精状态下，用计数的方式来判断是否重置
        if character_data.h_state.just_shoot == 1:
            character_data.h_state.just_shoot = 2
        else:
            character_data.h_state.just_shoot = 0
        # 二次确认H意外结束的归零结算
        special_end_list = constant.special_end_H_list
        if (
            len(cache.pl_pre_behavior_instruce)
            and cache.pl_pre_behavior_instruce[-1] in special_end_list
            and character_data.behavior.behavior_id not in special_end_list
        ):
            default.handle_both_h_state_reset(
                0,
                1,
                change_data=game_type.CharacterStatusChange(),
                now_time=datetime.datetime(1, 1, 1),
            )
        # 如果在搬运角色，则直接移动到玩家同一地点
        if handle_premise.handle_carry_somebody(0):
            now_carry_chara_id = pl_character_data.action_info.carry_chara_id
            now_carry_character_data = cache.character_data[now_carry_chara_id]
            map_handle.character_move_scene(
                now_carry_character_data.position,
                pl_character_data.position,
                now_carry_chara_id,
            )

    # 玩家部分终止，以下为NPC部分
    if character_id == 0:
        return 1

    # 将绝顶解放状态改为关闭绝顶寸止
    if handle_premise.handle_self_orgasm_edge_relase(character_id):
        default.handle_self_orgasm_edge_off(
            character_id,
            1,
            change_data=game_type.CharacterStatusChange(),
            now_time=datetime.datetime(1, 1, 1),
        )
    # 将时停解放状态改为False
    if handle_premise.handle_self_time_stop_orgasm_relase(character_id):
        character_data.h_state.time_stop_release = False

    # 群交中，仅自慰类型和补位类型的干员由群交AI判断处理（睡奸与6异常时例外）；
    # H中或木头人时做什么由她选行动时决定（handle_npc_ai.choose_state_machine）
    if (
        (character_data.sp_flag.is_h or character_data.hypnosis.blockhead)
        and character_data.behavior.behavior_id != constant.Behavior.SLEEP
        and handle_premise.handle_normal_6(character_id)
        and handle_premise.handle_group_sex_mode_on(character_id)
        and (
            handle_premise.handle_npc_ai_type_1_in_group_sex(character_id)
            or handle_premise.handle_npc_ai_type_2_in_group_sex(character_id)
        )
    ):
        npc_ai_in_group_sex(character_id)
    return 1


def end_h_left_behind(character_id: int) -> None:
    """
    玩家离开场景后，留下的干员结束H、睡眠猥亵、空气催眠、隐奸与露出（事件 HLeftBehind）\n
    H中的干员排上1分钟的结束H，当前的行动被打断\n
    Keyword arguments:
    character_id -- 角色id\n
    """
    from Script.Modules.gameplay_resolution import plan_queue

    character_data: game_type.Character = cache.character_data[character_id]
    pl_character_data: game_type.Character = cache.character_data[0]
    # 结束H状态
    if handle_premise.handle_self_is_h(character_id):
        character_data.sp_flag.is_h = False
        character_data.sp_flag.unconscious_h = 0
        plan_queue.plan_next(
            character_id,
            constant.Behavior.END_H,
            1,
            state=constant.CharacterStatus.STATUS_END_H,
            interrupt=True,
        )
    # 结束睡眠猥亵状态
    if handle_premise.handle_unconscious_flag_1(character_id):
        character_data.sp_flag.unconscious_h = 0
    # 结束空气催眠
    if (
        handle_premise.handle_unconscious_flag_5(character_id)
        and character_data.position
        != pl_character_data.pl_ability.air_hypnosis_position
    ):
        character_data.sp_flag.unconscious_h = 0
    # 结束隐奸状态
    if handle_premise.handle_hidden_sex_mode_ge_1(character_id):
        character_data.sp_flag.hidden_sex_mode = 0
    # 结束露出状态
    if handle_premise.handle_exhibitionism_sex_mode_ge_1(character_id):
        character_data.sp_flag.exhibitionism_sex_mode = 0


def recover_from_unconscious_h(character_id: int, info_text: str = "") -> None:
    """
    交互对象从无意识H中恢复意识的结算\n
    接着的等待排进对方的计划队列并打断对方当前的行动；玩家的反应（继续H时等待5分钟，否则裁决出的行为与结束无意识H）
    排进玩家的计划队列并打断玩家当前的行动；群交中的其他角色只结束自己的行动\n
    Keyword arguments:\n
    character_id -- 角色id\n
    info_text -- 提示文本，为空时用默认的恢复意识提示\n
    """
    from Script.Modules.gameplay_resolution import plan_queue
    from Script.Settle import default

    character_data: game_type.Character = cache.character_data[character_id]
    target_data: game_type.Character = cache.character_data[
        character_data.target_character_id
    ]
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        character_data.position
    )
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]

    # 如果角色不在无意识H状态，则直接返回
    if target_data.sp_flag.unconscious_h == 0:
        return

    # 输出提示信息
    now_draw = draw.WaitDraw()
    now_draw.width = window_width
    if info_text == "":
        name_text = target_data.name
        # 如果在群交中
        if handle_premise.handle_group_sex_mode_on(character_id):
            name_text += _("等人")
        now_draw.text = _("\n{0}从无意识状态中恢复过来\n").format(name_text)
    else:
        now_draw.text = info_text
    now_draw.draw()

    # 睡眠中，则对方获得睡奸醒来状态
    if handle_premise.handle_action_sleep(character_data.target_character_id):
        target_data.sp_flag.sleep_h_awake = True

    # 结算恢复无意识的二段行为
    settle_unconscious_semen_and_cloth(target_data.cid)

    # 如果在群交中
    if handle_premise.handle_group_sex_mode_on(character_id):
        # 清空玩家的群交模板数据
        default.handle_clear_group_sex_template(
            character_id,
            1,
            game_type.CharacterStatusChange(),
            datetime.datetime(1, 1, 1),
        )
        # 关闭群交状态
        default.handle_group_sex_mode_off(
            character_id,
            1,
            game_type.CharacterStatusChange(),
            datetime.datetime(1, 1, 1),
        )
        # 结算交互对象以外的其他角色，遍历在角色列表的副本上进行，结算中囚犯干员会被移回监牢而改动该列表
        for chara_id in scene_data.character_list.copy():
            # 如果是玩家，则跳过
            if chara_id == character_id:
                continue
            # 如果是交互对象，则跳过
            if chara_id == target_data.cid:
                continue
            # 结算其他角色，这些角色一律不继续H
            handle_unconscious_h_response(
                character_id, chara_id, can_continue=False
            )

    # 结算交互对象的响应
    response = handle_unconscious_h_response(
        character_id, character_data.target_character_id
    )

    # 如果继续H，对方等待10分钟
    wait_minutes = 10
    if response == UnconsciousHResponse.CONTINUE_H:
        default.handle_h_flag_to_1(
            target_data.cid,
            1,
            game_type.CharacterStatusChange(),
            game_time.now(),
        )
        plan_queue.plan_next(
            character_id,
            constant.Behavior.WAIT,
            5,
            state=constant.CharacterStatus.STATUS_WAIT,
            interrupt=True,
        )
        # 睡眠中，则对方获得装睡状态，仍继续无意识H
        if handle_premise.handle_action_sleep(
            character_data.target_character_id
        ):
            target_data.h_state.pretend_sleep = True
            target_data.sp_flag.unconscious_h = 1
            # 成就刷新
            cache.achievement.sleep_sex_record[1] = 1
    # 否则对象只等1分钟，地点开门；双方H结构体由排上的结束无意识H在补体力气力上限之后重置
    else:
        wait_minutes = 1
        scene_data.close_flag = 0
    plan_queue.plan_next(
        target_data.cid,
        constant.Behavior.WAIT,
        wait_minutes,
        state=constant.CharacterStatus.STATUS_WAIT,
        interrupt=True,
    )


class UnconsciousHResponse:
    """无意识H被打断后的裁决结果"""

    CONTINUE_H = 1
    """ 继续H """
    LOW_OBSCENITY = 2
    """ 玩家转为轻度性骚扰 """
    HIGH_OBSCENITY = 3
    """ 玩家转为高级性骚扰 """
    ANGRY = 4
    """ 目标角色对玩家愤怒 """
    H_FAIL = 5
    """ 玩家H失败 """


UNCONSCIOUS_H_REACTION: dict[int, tuple[str, int]] = {
    UnconsciousHResponse.LOW_OBSCENITY: (
        constant.Behavior.LOW_OBSCENITY_ANUS,
        constant.CharacterStatus.STATUS_LOW_OBSCENITY_ANUS,
    ),
    UnconsciousHResponse.HIGH_OBSCENITY: (
        constant.Behavior.HIGH_OBSCENITY_ANUS,
        constant.CharacterStatus.STATUS_HIGH_OBSCENITY_ANUS,
    ),
    UnconsciousHResponse.H_FAIL: (
        constant.Behavior.DO_H_FAIL,
        constant.CharacterStatus.STATUS_DO_H_FAIL,
    ),
}
""" 裁决结果到玩家反应的行为与状态；愤怒时玩家没有反应行为 """


def handle_unconscious_h_response(
    character_id: int, target_character_id: int, can_continue: bool = True
) -> int:
    """
    结算目标角色从无意识H中被打断后的响应

    参数:
        character_id: int -- 自己角色的ID
        target_character_id: int -- 本次结算的目标角色的ID
        can_continue: bool -- 本次结算是否允许目标角色继续H，默认为True

    返回:
        int -- UnconsciousHResponse中的裁决结果

    功能描述:
        先解除目标角色的无意识H状态，再按目标角色自身的监禁状态与陷落状态得出裁决结果。
        can_continue为True时：裁决为继续H以外的结果时，玩家对她的反应行为（5分钟，愤怒时没有）与结束无意识H
        依次排进玩家的计划队列，并打断玩家当前的行动。
        can_continue为False时只结算目标角色这一边：不论裁决，都对她本人做退出结算（退出奖励、H状态归位、穿回衣物），
        然后打断她当前的行动。
    """
    from Script.Modules.gameplay_resolution import plan_queue
    from Script.Settle import default, default_cloth

    # 从缓存中获取自己角色数据与目标角色数据
    character_data: game_type.Character = cache.character_data[character_id]
    target_data: game_type.Character = cache.character_data[target_character_id]

    # 停止对方的无意识状态与H状态
    target_data.sp_flag.unconscious_h = 0
    target_data.sp_flag.is_h = False

    # 如果目标对象处于监禁状态，则直接满足条件
    if handle_premise.handle_imprisonment_1(target_character_id):
        # 目标对象处于监禁状态，裁决为继续H
        response = UnconsciousHResponse.CONTINUE_H
    # 如果满足高级性骚扰的实行值需求，则根据目标对象的陷落状态判断
    elif handle_premise.handle_instruct_judge_high_obscenity(
        target_character_id
    ):
        # 获取目标对象的陷落状态，minus_flag为True表示计算减值
        character_fall_level = attr_calculation.get_character_fall_level(
            target_character_id, minus_flag=True
        )
        # 如果陷落状态等级大于等于3，则允许继续H
        if character_fall_level >= 3:
            response = UnconsciousHResponse.CONTINUE_H
        # 如果陷落状态大于0，则设置为轻度性骚扰状态
        elif character_fall_level > 0:
            response = UnconsciousHResponse.LOW_OBSCENITY
        # 如果陷落状态小于0，则目标角色愤怒并增加愤怒值
        elif character_fall_level < 0:
            response = UnconsciousHResponse.ANGRY
            target_data.angry_point += 100
            target_data.sp_flag.angry_with_player = True
        # 如果没有陷落状态，则设置为高级性骚扰状态
        else:
            response = UnconsciousHResponse.HIGH_OBSCENITY
    # 如果上述条件都不满足，则设置为H失败状态
    else:
        response = UnconsciousHResponse.H_FAIL

    # 群交中的其他角色：只结算她这一边，结束她当前的行动；不论她继续与否，她这一边的H都在这里结束
    if not can_continue:
        # 退出结算：退出奖励、H状态归位与穿回衣物。
        # 寸止解放按玩家的交互对象结算，结算时把玩家的交互对象暂时指向她，结算完复原；
        # 退出奖励会连同角色的交互对象一起结算，而她身上的交互对象可能是没有清理过的旧值，因此先把她的目标指向自己
        old_target_character_id = character_data.target_character_id
        character_data.target_character_id = target_character_id
        default.handle_orgasm_edge_release(
            character_id,
            1,
            game_type.CharacterStatusChange(),
            game_time.now(),
        )
        character_data.target_character_id = old_target_character_id
        target_data.target_character_id = target_character_id
        default.handle_end_h_add_hpmp_max(
            target_character_id,
            1,
            game_type.CharacterStatusChange(),
            game_time.now(),
        )
        default.handle_self_h_state_reset(
            target_character_id,
            1,
            game_type.CharacterStatusChange(),
            game_time.now(),
        )
        default_cloth.handle_self_cloth_back(
            target_character_id,
            1,
            game_type.CharacterStatusChange(),
            game_time.now(),
        )
        plan_queue.interrupt(target_character_id)
    # 不继续H：玩家的反应与结束无意识H排进玩家的计划队列
    elif response != UnconsciousHResponse.CONTINUE_H:
        reaction = UNCONSCIOUS_H_REACTION.get(response)
        if reaction is not None:
            plan_queue.plan_next(
                character_id,
                reaction[0],
                5,
                target=target_character_id,
                state=reaction[1],
                interrupt=True,
            )
        plan_queue.plan_next(
            character_id,
            constant.Behavior.NO_CONSCIOUS_H_END,
            0,
            target=target_character_id,
            state=constant.CharacterStatus.STATUS_NO_CONSCIOUS_H_END,
            interrupt=True,
        )

    # 返回裁决结果
    return response


def judge_weak_up_in_sleep_h(
    character_id: int, target_character_id: int
) -> None:
    """
    判断睡眠中是否被吵醒：掷骰，吵醒时记进 cache.noise_woken，掷骰的这一步里由 time_hooks 结算（wake_by_noise）\n
    每个睡着的人各掷一次；她已被吵醒而还没结算时不再掷骰\n
    Keyword arguments:\n
    character_id -- 产生动作的角色id\n
    target_character_id -- 需要判定是否醒来的睡眠角色id\n
    """
    if target_character_id in cache.noise_woken:
        return
    target_data: game_type.Character = cache.character_data[target_character_id]

    # 浅睡和半梦半醒时递增苏醒概率
    weak_rate = (
        game_config.config_sleep_level[1].sleep_point - target_data.sleep_point
    )
    if target_data.sleep_point <= game_config.config_sleep_level[0].sleep_point:
        weak_rate += (
            game_config.config_sleep_level[0].sleep_point
            - target_data.sleep_point
        )
    # 判定是否吵醒
    if weak_rate >= random.randint(1, 100):
        cache.noise_woken[target_character_id] = character_id


def wake_by_noise(character_id: int, target_character_id: int) -> None:
    """
    睡着的角色被动静吵醒（掷骰的这一步里由 time_hooks 调用）：她当前的行动被打断，在这一步结束\n
    Keyword arguments:\n
    character_id -- 产生动作的角色id\n
    target_character_id -- 被吵醒的角色id\n
    """
    from Script.Modules.gameplay_resolution import plan_queue

    now_character_data: game_type.Character = cache.character_data[character_id]
    target_data: game_type.Character = cache.character_data[target_character_id]
    # 清空疲劳和睡眠程度
    target_data.tired_point = 0
    target_data.sleep_point = 0
    if target_data.sp_flag.unconscious_h == 1:
        # 睡奸目标：走现有无意识H恢复流程
        info_text = _("\n因为{0}的动作，{1}从梦中惊醒过来\n").format(
            now_character_data.name, target_data.name
        )
        recover_from_unconscious_h(character_id, info_text)
        return
    if target_data.sp_flag.unconscious_h == 0:
        # 普通睡眠角色：睡眠行为当场结束，“睡觉中被吵醒”排进它的计划队列。
        # 交互对象设为产生动静的角色（玩家），供效果762把对方推回前一场景使用
        plan_queue.plan_next(
            target_character_id,
            constant.Behavior.WAKE_UP_BY_NOISE,
            1,
            target=character_id,
            state=constant.CharacterStatus.STATUS_WAKE_UP_BY_NOISE,
            interrupt=True,
        )
        return
    # 醉酒、时停、平然、空气、体控、心控等其他无意识状态：提示，并结束当前的行动
    info_text = _("\n{0}被{1}的动静吵醒了\n").format(
        target_data.name, now_character_data.name
    )
    now_draw = draw.WaitDraw()
    now_draw.width = window_width
    now_draw.text = info_text
    now_draw.draw()
    plan_queue.interrupt(target_character_id)


def settle_unconscious_semen_and_cloth(character_id: int) -> None:
    """
    结算角色在无意识期间的部位精液与服装偷窃的二段行为
    参数:
        character_id: int -- 角色ID
    返回:
        None -- 该函数只更新角色脏污数据，无返回值
    功能描述:
        当角色在恢复意识时触发的二段行为。
    """
    from Script.Design import second_behavior

    # 从缓存中获取角色数据
    character_data: game_type.Character = cache.character_data[character_id]
    # 对数据进行去重
    character_data.dirty.body_semen_in_unconscious = list(
        set(character_data.dirty.body_semen_in_unconscious)
    )
    character_data.dirty.cloth_semen_in_unconscious = list(
        set(character_data.dirty.cloth_semen_in_unconscious)
    )
    # 触发角色的部位精液二段行为
    for body_part in character_data.dirty.body_semen_in_unconscious:
        second_behavior_id = "in_unconscious_cum_on_body_" + str(body_part)
        second_behavior.character_get_second_behavior(
            character_id, second_behavior_id
        )
    for cloth_part in character_data.dirty.cloth_semen_in_unconscious:
        # 如果自己身上没穿着该部位的衣服，则跳过
        if len(character_data.cloth.cloth_wear[cloth_part]) == 0:
            continue
        second_behavior_id = "in_unconscious_cum_on_cloth_" + str(cloth_part)
        second_behavior.character_get_second_behavior(
            character_id, second_behavior_id
        )
    # 触发角色的服装失窃行为
    if character_data.cloth.stolen_panties_in_unconscious:
        second_behavior.character_get_second_behavior(
            character_id, "in_unconscious_stolen_panty"
        )
    if character_data.cloth.stolen_socks_in_unconscious:
        second_behavior.character_get_second_behavior(
            character_id, "in_unconscious_stolen_socks"
        )
    # 数据清零
    character_data.dirty.body_semen_in_unconscious = []
    character_data.dirty.cloth_semen_in_unconscious = []
    character_data.cloth.stolen_panties_in_unconscious = False
    character_data.cloth.stolen_socks_in_unconscious = False


def evaluate_npc_body_part_prefs(character_id: int) -> int:
    """
    判断NPC的部位喜好\n
    Return arguments:
    int -- 选择的部位
    """

    character_data = cache.character_data[character_id]

    # 如果自己不是NPC，则返回
    if character_id == 0:
        return 0

    # 按照部位统计权重，初始权重为1
    part_weight = {}
    for state_id in game_config.config_character_state:
        if game_config.config_character_state[state_id].type == 0:
            part_weight[state_id] = 1

    # 部位经验权重为1
    for experience_id in game_config.config_experience:
        # 去掉非部位的经验
        if 20 <= experience_id <= 60 or experience_id >= 78:
            continue

        # 取除以10的余数
        part_id = experience_id % 10
        if experience_id in {61, 65}:
            part_id = 4
        elif experience_id in {62, 66}:
            part_id = 5
        elif experience_id in {63, 67}:
            part_id = 6
        elif experience_id in {64, 68}:
            part_id = 7
        now_exp = character_data.experience[experience_id]
        part_weight[part_id] += now_exp

    # 能力等级权重为10
    for ability_id in game_config.config_ability:
        # 去掉非部位的能力
        if game_config.config_ability[ability_id].ability_type not in [0, 1]:
            continue
        if ability_id <= 8:
            part_id = ability_id
        # 将扩张的序号转换为部位序号
        elif game_config.config_ability[ability_id].ability_type == 1:
            part_id = ability_id - 5
        else:
            part_id = ability_id - 79
        now_ability = character_data.ability[ability_id]
        part_weight[part_id] += now_ability * 10

    # 在最后将阴茎的权重置为0
    part_weight[3] = 0

    # 根据权重，随机选择一个部位
    part_id = random.choices(
        list(part_weight.keys()), weights=list(part_weight.values()), k=1
    )[0]

    # 以防万一，如果因为BUG选中了阴茎，则返回
    if part_id == 3:
        return 0

    # 返回选择的部位
    return part_id


def npc_active_h() -> int:
    """
    判断NPC的逆推ai：在玩家选行动时调用，选出的行为经 player_pick.choose 定为玩家这次的行动（抛出 Chosen）\n
    Return arguments:
    int -- 0为对方没有逆推或没有可选的行为
    """
    from Script.Modules.tk_ui import player_pick
    from Script.System.Instruct_System import see_instruct_panel

    pl_character_data: game_type.Character = cache.character_data[0]
    target_character_id = pl_character_data.target_character_id
    target_character_data = cache.character_data[target_character_id]

    # 如果对方不是主动H状态，则返回
    if (
        not target_character_data.hypnosis.active_h
        and not target_character_data.h_state.npc_active_h
    ):
        return 0
    # 对方处于幼年阶段时不逆推
    if child_stage_gate.is_child_stage(target_character_id):
        return 0

    # 根据NPC的部位喜好，选择一个部位
    part_id = evaluate_npc_body_part_prefs(target_character_id)

    # 遍历全状态
    all_stastus_list = []
    now_premise_data: dict[str, float] = {}
    for behavior_id in game_config.config_behavior:
        behavior_data = game_config.config_behavior[behavior_id]
        # 跳过只能玩家使用的状态
        if behavior_data.trigger == "pl":
            continue
        # 获得各状态的tag
        behavior_tag_list = behavior_data.tag.split("|")
        # 跳过其中非性爱类，道具类、药物类、SM类、非逆推类
        if (
            "性爱" not in behavior_tag_list
            or "道具" in behavior_tag_list
            or "药物" in behavior_tag_list
            or "SM" in behavior_tag_list
            or "非逆推" in behavior_tag_list
        ):
            continue
        # 如果NPC为处，则跳过破处类
        if virgin_break_gate.takes_kept_virginity(
            behavior_tag_list, target_character_data.talent
        ):
            continue

        # 跳过非当前部位
        if part_id == 0 and "N" not in behavior_tag_list:
            continue
        elif part_id == 1 and "B" not in behavior_tag_list:
            continue
        elif part_id == 2 and "C" not in behavior_tag_list:
            continue
        elif part_id == 4 and "V" not in behavior_tag_list:
            continue
        elif part_id == 5 and "A" not in behavior_tag_list:
            continue
        elif part_id == 6 and "U" not in behavior_tag_list:
            continue
        elif part_id == 7 and "W" not in behavior_tag_list:
            continue

        # 跳过不满足前提的
        if behavior_id in constant.behavior_id_to_instruct_id:
            # 获取指令id
            instruct_id = constant.behavior_id_to_instruct_id[behavior_id]
            # 检查指令是否可用
            filter_judge, now_premise_data = (
                see_instruct_panel.judge_single_instruct_filter(
                    instruct_id,
                    now_premise_data,
                    constant.InstructType.SEX,
                    use_type_filter_flag=False,
                )
            )
            # 跳过
            if not filter_judge:
                continue

        # 开始加入列表中
        all_stastus_list.append(behavior_id)

    # 如果没有符合条件的状态，则返回
    if len(all_stastus_list) == 0:
        return 0

    # print(f"debug 全列表为{all_stastus_list}")

    # 随机选择一个状态
    behavior_id = random.choice(all_stastus_list)

    # 定为玩家这次选的行动
    player_pick.choose(behavior_id, 10, state=behavior_id)


def npc_ai_in_group_sex(character_id: int) -> None:
    """
    NPC在群交中的AI，不含抢占：在她自己的行为结束时（actions.wrap_up）选模板里的部位与状态加入，或进入要自慰状态\n
    Keyword arguments:\n
    character_id -- 角色id\n
    """
    from Script.System.Sex_System import group_sex_panel

    # 玩家或幼年阶段角色则返回
    if character_id == 0 or child_stage_gate.is_child_stage(character_id):
        return
    # 如果自己已在群交模板中，则返回
    group_sex_chara_id_list = group_sex_panel.count_group_sex_character_list()
    if character_id in group_sex_chara_id_list:
        return

    character_data: game_type.Character = cache.character_data[character_id]
    pl_character_data: game_type.Character = cache.character_data[0]
    A_template_data = pl_character_data.h_state.group_sex_body_template_dict[
        "A"
    ]

    # 如果不是H状态+群交，则返回
    if (
        not character_data.sp_flag.is_h
        or handle_premise.handle_group_sex_mode_off(character_id)
    ):
        return

    # 被绳子捆绑则返回
    if handle_premise.handle_self_now_bondage(character_id):
        return

    # 如果设定NPC为仅自慰，则进入要自慰后返回
    if handle_premise.handle_npc_ai_type_1_in_group_sex(character_id):
        character_data.sp_flag.masturebate = 3
        return

    # 获取当前模板的空缺部位和非空缺部位
    now_template_empty_part_list, __ = (
        group_sex_panel.get_now_template_part_list()
    )

    # 没有空缺时，自己进入要自慰状态
    if not now_template_empty_part_list:
        character_data.sp_flag.masturebate = 3
        return
    # 随机选择一个部位；如果是加入侍奉，则直接加入
    body_part = random.choice(now_template_empty_part_list)
    if body_part == _("加入侍奉"):
        A_template_data[1][0].append(character_id)
        return
    # 获取该部位的状态id列表：查询按玩家的交互对象判断前提，查完复原
    old_target_character_id = pl_character_data.target_character_id
    pl_character_data.target_character_id = character_id
    try:
        new_status_id_list = (
            group_sex_panel.get_status_id_list_from_group_sex_body_part(
                body_part
            )
        )
    finally:
        pl_character_data.target_character_id = old_target_character_id
    # 如果没有可用的状态，则返回
    if len(new_status_id_list) == 0:
        return
    # 随机选择一个状态；侍奉时替换侍奉位，对单时占这个部位
    status_id = random.choice(new_status_id_list)
    if body_part == "侍奉":
        A_template_data[1] = [[character_id], status_id]
    else:
        A_template_data[0][body_part] = [character_id, status_id]
