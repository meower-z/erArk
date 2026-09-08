import datetime
from types import FunctionType
from Script.Core import (
    cache_control,
    game_path_config,
    game_type,
    constant,
    get_text,
)
from Script.Design import (
    settle_behavior,
    game_time,
    instuct_judege,
    handle_premise,
    event,
    handle_npc_ai,
    handle_npc_ai_in_h,
    map_handle,
    handle_talent,
)
from Script.UI.Moudle import draw
from Script.Config import game_config, normal_config
from Script.Settle import sleep_settle, past_day_settle, realtime_settle

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


def init_character_behavior():
    """提交玩家当前行动并推进到下次输入，无参数，返回 None。"""
    from Script.Modules import game_actions

    game_actions.get_runtime().advance(cache.character_data[0].behavior.duration)


def character_behavior(character_id: int, now_time: datetime.datetime, pl_start_time: datetime.datetime):
    """兼容旧角色入口，提交当前行动；参数为角色及旧时间区间，返回 None。"""
    from Script.Modules import game_actions

    game_actions.submit_current(character_id)


def judge_character_status(character_id: int) -> int:
    """
    校验并结算角色状态\n
    Keyword arguments:\n
    character_id -- 角色id\n
    Return arguments:\n
    int -- 结算是否成功
    """
    character_data: game_type.Character = cache.character_data[character_id]
    scene_path_str = map_handle.get_map_system_path_str_for_list(character_data.position)
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    start_time = character_data.behavior.start_time
    end_time = game_time.get_sub_date(minute=character_data.behavior.duration, old_date=start_time)
    if (
        character_data.target_character_id != character_id
        and character_data.target_character_id not in scene_data.character_list
    ):
        # 例外：玩家在搬运该角色
        if character_data.target_character_id != character_data.sp_flag.bagging_chara_id:
            # end_time = now_time # 这里本来是游戏实际时间，架构改了之后大概不需要了，姑且先保留着
            end_time = end_time
    # print(f"debug {character_data.name}的end_time = {end_time}")

    # 跳过指令和指令后置类型的事件触发
    # print(f"debug 跳过指令和指令后置类型的事件触发")
    start_event_draw = event.handle_event(character_id, event_before_instrust_flag = True)
    event_type_now = 1
    if start_event_draw != None:
        event_id = start_event_draw.event_id
        character_data.event.event_id = event_id
        event_config = game_config.config_event[event_id]
        event_type_now = event_config.type
        # 事件绘制
        start_event_draw.draw()

    # if not character_id:
    #     print(f"debug 1 move_src = {character_data.behavior.move_src},position = {character_data.position}")
    # 指令与指令前事件的数值结算
    first_settle_panel = settle_behavior.handle_settle_behavior(character_id, end_time, event_type_now)
    second_settle_panel = None
    # if not character_id:
    #     print(f"debug 2 move_src = {character_data.behavior.move_src},position = {character_data.position}")

    end_event_draw = event.handle_event(character_id)
    if end_event_draw != None and start_event_draw == None:
        end_event_id = end_event_draw.event_id
        end_event_type = end_event_draw.event_type
        event_config = game_config.config_event[end_event_id]
        # 指令前置类型的事件触发
        if end_event_type == 1:
            # print(f"debug 指令前置类型的事件触发")
            character_data.event.event_id = end_event_id
            # 事件绘制
            end_event_draw.draw()
            # 事件的数值结算
            second_settle_panel = settle_behavior.handle_settle_behavior(character_id, end_time, 0)

    # if not character_id:
    #     print(f"debug 3 move_src = {character_data.behavior.move_src},position = {character_data.position}")

    # 绘制数值变化
    if first_settle_panel != None and len(first_settle_panel.draw_list):
        # Web模式：不绘制结算面板，数值变化已通过collect_web_value_changes收集
        # 由前端以浮动文本形式在玩家信息栏和交互对象信息栏显示
        if cache.web_mode:
            pass
        else:
            # TK模式：正常绘制结算信息
            first_settle_panel.draw()
            if second_settle_panel != None:
                second_settle_panel.draw()
            # 进行一次暂停以便玩家看输出信息，非玩家的信息显示由设置控制
            if character_id == 0 or cache.all_system_setting.draw_setting[19]:
                wait_draw = draw.WaitDraw()
                wait_draw.text = "\n"
                wait_draw.width = window_width
                wait_draw.draw()

    return 1

def judge_character_status_time_over(character_id: int, now_time: datetime.datetime, end_now = 0) -> int:
    """
    结算角色状态是否本次行动已经结束
    Keyword arguments:
    character_id -- 角色id
    end_now -- 是否要强制结算，1为当前时间大于行动结束时间，2为当前时间等于行动结束时间
    Return arguments:
    bool -- 本次update时间切片内活动是否已完成
    """
    character_data: game_type.Character = cache.character_data[character_id]
    pl_character_data = cache.character_data[0]
    scene_path_str = map_handle.get_map_system_path_str_for_list(character_data.position)
    scene_data: game_type.Scene = cache.scene_data[scene_path_str]
    # 如果行动起始时间大于当前时间，则初始化行动起始时间为当前时间
    if game_time.judge_date_big_or_small(character_data.behavior.start_time, now_time):
        character_data.behavior.start_time = now_time
    start_time = character_data.behavior.start_time
    end_time = game_time.get_sub_date(minute=character_data.behavior.duration, old_date=start_time)
    if (
        character_data.target_character_id != character_id
        and character_data.target_character_id not in scene_data.character_list
    ):
        # 例外：玩家在搬运该角色
        if character_data.target_character_id != character_data.sp_flag.bagging_chara_id:
            end_time = now_time
    # print(f"debug {character_data.name}的end_time = {end_time}")
    time_judge = game_time.judge_date_big_or_small(now_time, end_time)
    add_time = (end_time.timestamp() - start_time.timestamp()) / 60
    # if character_data.name == "阿米娅":
    #     print(f"debug {character_data.name}的time_judge = {time_judge}，add_time = {add_time}")
    # 如果本次行动的持续时间为0或负数（负数见于状态机算出的异常时长，需在此拦截以保证时间前进）
    if add_time <= 0:
        # 如果是H状态，则直接可以跳出
        if handle_premise.handle_self_is_h(character_id):
            character_data.behavior.start_time = now_time
            return 1
        character_data.behavior = game_type.Behavior()
        character_data.behavior.start_time = now_time
        character_data.behavior.duration = 1
        character_data.state = constant.CharacterStatus.STATUS_ARDER
        # print(f"debug {character_data.name}的add_time = 0，已重置为当前时间：start_time = {character_data.behavior.start_time}")
        return 0
    if end_now:
        time_judge = end_now
    if time_judge:
        # 记录并刷新旧行为列表
        character_data.last_behavior_id_list.append(character_data.behavior.behavior_id)
        if len(character_data.last_behavior_id_list) > 5:
            character_data.last_behavior_id_list.pop(0)
        # 保留移动的来源位置
        tem_move_src = character_data.behavior.move_src
        # 移动状态下则不完全重置行动数据，保留最终目标数据
        if character_data.behavior.behavior_id == constant.Behavior.MOVE:
            tem_move_final_target = character_data.behavior.move_final_target
            character_data.behavior = game_type.Behavior()
            character_data.behavior.move_final_target = tem_move_final_target
        else:
            character_data.behavior = game_type.Behavior()
        # 赋予移动来源
        character_data.behavior.move_src = tem_move_src
        character_data.state = constant.CharacterStatus.STATUS_ARDER
        character_data.event.event_id = ""
        character_data.event.son_event_id = ""
        # 睡醒时刷新异常位掩码5/6：睡眠中位6被结算为异常，若醒来后不经过起床状态机
        # （仅宿舍内可触发），无其他修改点负责刷新，会导致角色因过期异常位卡死在原地
        if character_data.last_behavior_id_list[-1] == constant.Behavior.SLEEP:
            handle_premise.settle_chara_unnormal_flag(character_id, 5)
            handle_premise.settle_chara_unnormal_flag(character_id, 6)
        # 当前时间大于行动结束时间
        if time_judge == 1:
            character_data.behavior.start_time = end_time
            return 0
        # 当前时间等于行动结束时间
        elif time_judge == 2:
            instuct_judege.init_character_behavior_start_time(character_id, now_time)
            return 1
    return 1


def character_instruct_record(character_id: int) -> str:
    """
    角色的指令记录\n
    Keyword arguments:
    character_id -- 角色id\n
    Return arguments:
    str -- 指令记录文本
    """
    character_data: game_type.Character = cache.character_data[character_id]
    name = character_data.name
    instruct_text = ""
    # 记录时间的小时数和分钟数
    now_time = character_data.behavior.start_time.strftime("%H:%M")
    instruct_text += _("{0}在{1}，").format(name, now_time)
    # 移动指令则记录移动路径
    if character_data.behavior.behavior_id == constant.Behavior.MOVE:
        move_src = character_data.behavior.move_src[-1]
        if move_src == "0":
            move_src =  character_data.behavior.move_src[-2] + "出口"
        move_target = character_data.behavior.move_target[-1]
        if move_target == "0":
            move_target =  character_data.behavior.move_target[-2] + "出口"
        if move_target:
            instruct_text += _("从{0}移动至{1}\n").format(move_src, move_target)
    # 其他指令则记录状态
    else:
        now_chara_behavior_name = game_config.config_behavior[character_data.behavior.behavior_id].name
        # 如果是交互指令则记录交互对象
        if character_data.target_character_id != character_id:
            target_character_data: game_type.Character = cache.character_data[character_data.target_character_id]
            target_name = target_character_data.name
            instruct_text += _("对{0}进行了{1}\n").format(target_name, now_chara_behavior_name)
        else:
            instruct_text += _("进行了{0}\n").format(now_chara_behavior_name)
    return instruct_text


def judge_before_pl_behavior():
    """
    玩家角色行动前的判断\n
    Keyword arguments:
    无\n
    Return arguments:
    无
    """
    pl_character_data: game_type.Character = cache.character_data[0]
    if pl_character_data.target_character_id != 0:
        target_character_data: game_type.Character = cache.character_data[pl_character_data.target_character_id]
        # 重置交互对象的射精部位
        if target_character_data.h_state.shoot_position_body != -1:
            target_character_data.h_state.shoot_position_body = -1
        if target_character_data.h_state.shoot_position_cloth != -1:
            target_character_data.h_state.shoot_position_cloth = -1

    # 睡眠时间在6h及以上的额外恢复
    if pl_character_data.behavior.behavior_id == constant.Behavior.SLEEP and pl_character_data.behavior.duration >= 360:
        sleep_settle.refresh_temp_semen_max() # 刷新玩家临时精液上限

    # 结算上次进行聊天的时间，以重置聊天计数器#
    settle_behavior.change_character_talkcount_for_time(0, pl_character_data.behavior.start_time)

    # 全获得角色刷新等待文本标记
    for character_id in cache.npc_id_got:
        if character_id == 0:
            continue
        character_data: game_type.Character = cache.character_data[character_id]
        character_data.action_info.have_shown_waiting_in_now_instruct = False

    # 隐奸的被察觉情况结算，需要玩家的行为不是结束H
    if handle_premise.handle_hidden_sex_mode_ge_1(0) and pl_character_data.behavior.behavior_id != constant.Behavior.END_H:
        from Script.System.Sex_System import hidden_sex_panel
        hidden_sex_panel.handle_hidden_sex_flow()
    # 露出的模式更新
    if handle_premise.handle_exhibitionism_sex_mode_ge_1(0):
        from Script.System.Sex_System import exhibitionism_sex_panel
        exhibitionism_sex_panel.update_exhibiionism_sex_mode()
