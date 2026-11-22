"""
角色行为的开始与收尾
====================
内核里一个行动开始时（gameplay_resolution.starts.behave）由 settle_start 结算，
结束时（行为的结束函数 actions.wrap_up）由 end_action 收掉行为，
玩家另由 player_after_end 跑寻路的下一段、实时数据、睡觉的存档与成就。
"""

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
    handle_premise,
    event,
    handle_npc_ai,
    map_handle,
    handle_talent,
)
from Script.UI.Moudle import draw
from Script.Kernel import core
from Script.Modules.domains import h_state
from Script.Modules.save_load import autosave
from Script.Config import game_config, normal_config
from Script.Settle import sleep_settle, realtime_settle
from Script.Modules.domains import (
    achievement,
    action_info,
    activity,
    flags,
    history,
)
from Script.Modules.domains import modes, plan, roster

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


def settle_start(character_id: int, minutes: int) -> None:
    """
    行动开始时的结算（缓存里已换上新的行为）。
    干员：结算状态与事件；目睹H的反应已结算过时跳过一次（移动照样结算）。
    玩家：记下指令文本；发呆时不结算。否则移动时同场景的干员跟随、全员重置目击玩家H，行动前的前置结算，
    结算状态与事件，睡觉刷新，H状态、猥亵与无意识；时停中累计时停时长
    Keyword arguments:
    character_id -- 角色id
    minutes -- 行动在内核里的分钟数（时停中玩家的行动是 0）
    """
    behavior_id = activity.behavior(character_id).behavior_id
    if character_id:
        if (
            not flags.get(character_id, "see_h_reaction_settled")
            or behavior_id == constant.Behavior.MOVE
        ):
            judge_character_status(character_id)
        flags.set(character_id, see_h_reaction_settled=False)
        return
    history.note_instruction(character_instruct_record(0), behavior_id)
    if behavior_id == constant.Behavior.SHARE_BLANKLY:
        return
    if behavior_id in {constant.Behavior.MOVE, constant.Behavior.CARRY_MOVE}:
        # 同场景里的NPC的跟随与被携带角色的同步移动
        handle_npc_ai.judge_same_position_npc_follow()
        # 全角色重置目击玩玩家H
        for npc_id in roster.active():
            flags.set(npc_id, see_pl_h=False)
    judge_before_pl_behavior()
    judge_character_status(0)
    if activity.behavior(character_id).behavior_id == constant.Behavior.SLEEP:
        sleep_settle.update_sleep()
    from Script.Design import handle_npc_ai_in_h

    handle_npc_ai_in_h.judge_character_h_obscenity_unconscious(
        0, activity.behavior(character_id).start_time
    )
    if modes.time_stop() and minutes == 0:
        achievement.add(
            "time_stop_duration", activity.behavior(character_id).duration
        )


def end_action(character_id: int) -> None:
    """
    行动结束时收掉行为：行为记进旧行为列表，换成此刻开始的空行为（保留移动的来源；移动与带人移动时保留最终目标），
    状态回到空闲，清掉事件；随后结算自动获得的素质和能力
    Keyword arguments:
    character_id -- 角色id
    """
    old = activity.behavior(character_id)
    last = [*activity.last_behaviors(character_id), old.behavior_id]
    if len(last) > 5:
        last.pop(0)
    activity.set_last_behaviors(character_id, last)
    kept: dict[str, object] = {"move_src": old.move_src}
    if old.behavior_id in {
        constant.Behavior.MOVE,
        constant.Behavior.CARRY_MOVE,
    }:
        kept["move_final_target"] = old.move_final_target
    activity.set_behavior(
        character_id, start_time=game_time.at(core.state().clock), **kept
    )
    activity.set_state(character_id, constant.CharacterStatus.STATUS_ARDER)
    activity.update_event(character_id, event_id="", son_event_id="")
    handle_talent.gain_talent(character_id, now_gain_type=0)


def player_after_end() -> None:
    """
    玩家的行动收尾之后：寻路途中排上下一段，寻路结束了（或不在寻路）才重定交互对象，玩家实时数据结算，
    睡觉留下了存档标记时向 save_load 提出自动存档，最后跑时停与群交的成就
    """
    from Script.Design import character_move
    from Script.UI.Panel import achievement_panel

    character_move.continue_player_route()
    if plan.route() is None:
        settle_player_target()
    realtime_settle.judge_pl_real_time_data()
    if plan.sleep_save():
        plan.set_sleep_save(False)
        autosave.update_save()
    achievement_panel.achievement_flow(_("时停"))
    achievement_panel.achievement_flow(_("群交"))


def scene_characters(scene_data: game_type.Scene) -> list[int]:
    """
    主界面列出的场景里的角色：除去玩家
    Keyword arguments:
    scene_data -- 玩家所在的场景
    Return arguments:
    list -- 角色id
    """
    character_set = scene_data.character_list.copy()
    character_set.discard(0)
    return list(character_set)


def settle_player_target() -> None:
    """
    玩家的行动结束时（寻路途中的各段之间除外，走到目标或寻路结束时照常）重定交互对象：
    交互对象不是自己也不在场景里，或刚移动到这里而交互对象不在场景里时，设为场景里的第一个角色；
    场景里没有别的角色时设为自己。
    主界面（in_scene_panel）只读不写，绘制时用的就是这里定下的交互对象
    """
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(0)
    )
    character_list = scene_characters(cache.scene_data[scene_path_str])
    target = activity.target(0)
    if not character_list:
        activity.set_target(0, 0)
    elif target not in character_list and (
        target != 0
        or (history.recent() and history.recent()[-1] == constant.Behavior.MOVE)
    ):
        activity.set_target(0, character_list[0])


def target_left(character_id: int, game: core.GameState) -> bool:
    """
    角色的交互对象不是自己，且已不在角色所在的场景（玩家正在搬运的对象除外）
    Keyword arguments:
    character_id -- 角色id
    game -- 事件触发函数收到的 GameState，交互对象与位置从它读
    Return arguments:
    bool -- 交互对象离开了时为真
    """
    target = activity.target(character_id, game)
    if target in (character_id, flags.get(character_id, "bagging_chara_id")):
        return False
    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id, game)
    )
    return target not in cache.scene_data[scene_path_str].character_list


def judge_character_status(character_id: int) -> int:
    """
    校验并结算角色状态\n
    Keyword arguments:\n
    character_id -- 角色id\n
    Return arguments:\n
    int -- 结算是否成功
    """
    start_time = activity.behavior(character_id).start_time
    end_time = game_time.get_sub_date(
        minute=activity.behavior(character_id).duration, old_date=start_time
    )
    # print(f"debug {character_data.name}的end_time = {end_time}")

    # 跳过指令和指令后置类型的事件触发
    # print(f"debug 跳过指令和指令后置类型的事件触发")
    start_event_draw = event.handle_event(
        character_id, event_before_instrust_flag=True
    )
    event_type_now = 1
    if start_event_draw is not None:
        event_id = start_event_draw.event_id
        activity.update_event(character_id, event_id=event_id)
        event_config = game_config.config_event[event_id]
        event_type_now = event_config.type
        # 事件绘制
        start_event_draw.draw()

    # if not character_id:
    #     print(f"debug 1 move_src = {character_data.behavior.move_src},position = {character_data.position}")
    # 指令与指令前事件的数值结算
    first_settle_panel = settle_behavior.handle_settle_behavior(
        character_id, end_time, event_type_now
    )
    second_settle_panel = None
    # if not character_id:
    #     print(f"debug 2 move_src = {character_data.behavior.move_src},position = {character_data.position}")

    end_event_draw = event.handle_event(character_id)
    if end_event_draw is not None and start_event_draw is None:
        end_event_id = end_event_draw.event_id
        end_event_type = end_event_draw.event_type
        event_config = game_config.config_event[end_event_id]
        # 指令前置类型的事件触发
        if end_event_type == 1:
            # print(f"debug 指令前置类型的事件触发")
            activity.update_event(character_id, event_id=end_event_id)
            # 事件绘制
            end_event_draw.draw()
            # 事件的数值结算
            second_settle_panel = settle_behavior.handle_settle_behavior(
                character_id, end_time, 0
            )

    # if not character_id:
    #     print(f"debug 3 move_src = {character_data.behavior.move_src},position = {character_data.position}")

    # 绘制数值变化
    if first_settle_panel is not None and len(first_settle_panel.draw_list):
        first_settle_panel.draw()
        if second_settle_panel is not None:
            second_settle_panel.draw()
        # 暂停一次让玩家看输出信息，非玩家角色是否暂停由 draw_setting[19] 决定
        if character_id == 0 or normal_config.system_setting.draw_setting[19]:
            wait_draw = draw.WaitDraw()
            wait_draw.text = "\n"
            wait_draw.width = window_width
            wait_draw.draw()

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
    now_time = activity.behavior(character_id).start_time.strftime("%H:%M")
    instruct_text += _("{0}在{1}，").format(name, now_time)
    # 移动指令则记录移动路径
    if activity.behavior(character_id).behavior_id == constant.Behavior.MOVE:
        move_src = activity.behavior(character_id).move_src[-1]
        if move_src == "0":
            move_src = activity.behavior(character_id).move_src[-2] + "出口"
        move_target = activity.behavior(character_id).move_target[-1]
        if move_target == "0":
            move_target = (
                activity.behavior(character_id).move_target[-2] + "出口"
            )
        if move_target:
            instruct_text += _("从{0}移动至{1}\n").format(move_src, move_target)
    # 其他指令则记录状态
    else:
        now_chara_behavior_name = game_config.config_behavior[
            activity.behavior(character_id).behavior_id
        ].name
        # 如果是交互指令则记录交互对象
        if activity.target(character_id) != character_id:
            target_character_data: game_type.Character = cache.character_data[
                activity.target(character_id)
            ]
            target_name = target_character_data.name
            instruct_text += _("对{0}进行了{1}\n").format(
                target_name, now_chara_behavior_name
            )
        else:
            instruct_text += _("进行了{0}\n").format(now_chara_behavior_name)
    return instruct_text


def judge_before_pl_behavior() -> None:
    """
    玩家角色行动前的判断\n
    Keyword arguments:
    无\n
    Return arguments:
    无
    """
    if activity.target(0) != 0:
        target_character_data: game_type.Character = cache.character_data[
            activity.target(0)
        ]
        # 重置交互对象的射精部位
        h_state.set(
            target_character_data.cid,
            shoot_position_body=-1,
            shoot_position_cloth=-1,
        )

    # 睡眠时间在6h及以上的额外恢复
    if (
        activity.behavior(0).behavior_id == constant.Behavior.SLEEP
        and activity.behavior(0).duration >= 360
    ):
        sleep_settle.refresh_temp_semen_max()  # 刷新玩家临时精液上限

    # 结算上次进行聊天的时间，以重置聊天计数器#
    settle_behavior.change_character_talkcount_for_time(
        0, activity.behavior(0).start_time
    )

    # 全获得角色刷新等待文本标记
    for character_id in roster.active():
        if character_id == 0:
            continue
        character_data: game_type.Character = cache.character_data[character_id]
        action_info.set(
            character_data.cid, "have_shown_waiting_in_now_instruct", False
        )

    # 隐奸的被察觉情况结算，需要玩家的行为不是结束H
    if (
        handle_premise.handle_hidden_sex_mode_ge_1(0)
        and activity.behavior(0).behavior_id != constant.Behavior.END_H
    ):
        from Script.System.Sex_System import hidden_sex_panel

        hidden_sex_panel.handle_hidden_sex_flow()
    # 露出的模式更新
    if handle_premise.handle_exhibitionism_sex_mode_ge_1(0):
        from Script.System.Sex_System import exhibitionism_sex_panel

        exhibitionism_sex_panel.update_exhibiionism_sex_mode()
