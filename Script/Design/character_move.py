"""角色移动：主角寻路、通用角色移动控制、撤销移动计划与移动到私密房间的结算"""

from Script.Core import cache_control, constant, game_type, get_text
from Script.Design import map_handle, update
from Script.UI.Moudle import draw, view
from Script.Modules.domains import action_info, activity, flags, inventory, plan
from types import FunctionType
from Script.Modules.domains import chara_profile
from Script.Modules.domains import identity

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1

_: FunctionType = get_text._
""" 翻译api """


def cancel_movement_plan(character_id: int) -> None:
    """
    撤销角色尚未完成的移动计划，同时保留最后一次移动的起点和目标点
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    None -- 无返回值
    """
    activity.update_behavior(character_id, move_final_target=[])


def own_charcter_move(
    target_scene: list, follow: int = 0, open_map: bool = False
) -> None:
    """
    主角寻路至目标场景：走第一段，之后每段在玩家下一次选行动时由计划队列接着走（continue_player_route）。
    玩家选行动时，第一段能走就选定它（player_pick.choose，从那里退出本函数）；已在目标、被叫停或寻路断了时，清掉玩家的交互对象
    Keyword arguments:
    target_scene -- 寻路目标场景(在地图系统下的绝对坐标)
    follow -- 前往这名干员的位置：她走开了就跟过去，到达时设为玩家的交互对象；0 为不跟人
    open_map -- 每一段开始后仍打开地图面板（从大地图移动到另一个区块时）
    """
    from Script.Modules.tk_ui import player_pick

    with player_pick.drafting("move"):
        plan.set_route(None)
        move_now = _player_leg(target_scene, follow, open_map)
        if move_now == "end" or move_now in _BREAK_LIST:
            activity.set_target(0, 0)
        # 继续留在地图页面
        if move_now in ["Null", "wait_open", "door_lock"]:
            view.now_panel_id = constant.Panel.SEE_MAP
        # 回到主页面
        else:
            view.now_panel_id = constant.Panel.IN_SCENE


def continue_player_route() -> None:
    """
    玩家要选下一个行动时，若还在寻路途中且上一段已走完，把下一段排进玩家的计划队列；
    已抵达、被叫停、计划被撤销、上一段没走动或寻路断了时结束寻路，玩家不再有交互对象
    """
    route = plan.route()
    if route is None:
        return
    legs = (constant.Behavior.MOVE, constant.Behavior.CARRY_MOVE)
    # 这一段还没开始（界面刚定下）或还没走完
    if activity.behavior(0).behavior_id in legs:
        return
    # 事件把这一段排进了队列，还没开始
    from Script.Modules.gameplay_resolution import plan_queue

    if any(plan_queue.plan_has(0, leg) for leg in legs):
        return
    route_target, leg_start, *rest = route
    follow, open_map = (rest + [0, False])[:2]
    # 跟着干员走：目标是她此刻的位置
    target_scene = activity.position(follow) if follow else route_target
    if (
        activity.position(0) != leg_start
        and activity.position(0) != target_scene
        and activity.behavior(0).move_final_target == route_target
        and _player_leg(target_scene, follow, open_map)
        not in ["end", *_BREAK_LIST]
    ):
        return
    plan.set_route(None)
    # 跟到了干员身边时她是交互对象，否则不再有交互对象
    activity.set_target(
        0, follow if follow and activity.position(0) == target_scene else 0
    )


_BREAK_LIST = ["null", "wait_open", "door_lock"]
""" 寻路断掉的结果 """


def _player_leg(
    target_scene: list, follow: int = 0, open_map: bool = False
) -> str:
    """
    玩家走寻路的一段：玩家选行动时选定它（player_pick.choose，从那里退出本函数），结算途中排进玩家的计划队列
    Keyword arguments:
    target_scene -- 寻路目标场景
    follow -- 跟着走的干员id，0 为不跟人
    open_map -- 这一段开始后仍打开地图面板
    Return arguments:
    str -- 寻路结果，"end" 为已在目标或被叫停
    """
    if flags.get(0, "move_stop"):
        flags.set(0, move_stop=False)
        plan.set_route(None)
        return "end"
    if activity.position(0) == target_scene:
        return "end"
    move_now, __, now_target_position, now_need_time = character_move(
        0, target_scene
    )
    if move_now in _BREAK_LIST:
        return move_now
    # 隐奸携带模式中使用携带H中移动行为，消耗大幅增加
    if flags.get(0, "hidden_sex_mode") == 5:
        behavior_id = constant.Behavior.CARRY_MOVE
        state = constant.CharacterStatus.STATUS_CARRY_MOVE
    else:
        behavior_id = constant.Behavior.MOVE
        state = constant.CharacterStatus.STATUS_MOVE
    plan.set_route((target_scene, activity.position(0), follow, open_map))
    fields = {
        "behavior.move_target": now_target_position,
        "behavior.move_src": activity.position(0),
        "behavior.move_final_target": target_scene,
        "action_info.ask_close_door_flag": False,
    }
    from Script.Modules.gameplay_resolution import starts

    args = {starts.OPEN_MAP: True} if open_map else None
    if update.in_resolution():
        from Script.Modules.gameplay_resolution import plan_queue

        plan_queue.plan_next(
            0,
            behavior_id,
            now_need_time,
            state=state,
            fields=fields,
            args=args,
        )
        return move_now
    from Script.Modules.tk_ui import player_pick

    view.now_panel_id = constant.Panel.IN_SCENE
    player_pick.choose(
        behavior_id, now_need_time, state=state, fields=fields, args=args
    )


def character_move(
    character_id: int, target_scene: list
) -> tuple[str, list, list, int]:
    """
    通用角色移动控制 \n
    Keyword arguments: \n
    character_id -- 角色id \n
    target_scene -- 寻路目标场景(在地图系统下的 绝对坐标) \n
    Return arguments: \n
    str:null -- 未找到路径 \n
    str:end -- 当前位置已是路径终点 \n
    list -- 路径 \n
    list -- 本次移动到的位置 \n
    int -- 本次移动花费的时间 \n
    """

    now_position = activity.position(character_id)
    # if not character_id:
    #     print(f"debug now_position = {now_position},target_scene = {target_scene}")
    if now_position == target_scene:
        return "end", [], [], 0
    now_position_str = map_handle.get_map_system_path_str_for_list(now_position)
    target_scene_str = map_handle.get_map_system_path_str_for_list(target_scene)
    # target_scene_data = cache.scene_data[target_scene_str]
    # if character_data.name == "阿米娅":
    #     print(f"debug 阿米娅，now_position_str = {now_position_str},target_scene_str = {target_scene_str}")
    if (
        now_position_str not in map_handle.scene_path_edge
        or target_scene_str not in map_handle.scene_path_edge[now_position_str]
    ):
        return "null", [], [], 0
    now_path_data = map_handle.scene_path_edge[now_position_str][
        target_scene_str
    ]
    access_type = "open"
    # 如果已经到门前了，则判断目标场景是否可进入，不可进入则输出原因
    if now_path_data[0] == target_scene:
        access_type = map_handle.judge_scene_accessible(
            target_scene_str, character_id
        )
        # 玩家移动，且目标地点锁门时
        if character_id == 0 and access_type == "door_lock":
            now_scene_data = cache.scene_data[target_scene_str]
            from Script.System.Dormitory_System.common import (
                check_have_move_target_room_key,
            )

            # 如果这里是宿舍，且玩家持有该楼层的钥匙，则解锁
            if (
                "Dormitory" in now_scene_data.scene_tag
                and check_have_move_target_room_key(0, target_scene_str)
            ):
                info_draw = draw.WaitDraw()
                info_draw.text = _(
                    "\n  ●你拿出了该楼层的复制钥匙，悄悄打开了门\n\n"
                )
                info_draw.draw()
                now_scene_data.close_flag = 0
                access_type = "open"
            # 如果这是宿舍或客房，且玩家持有一次性钥匙则消耗钥匙并解锁
            elif (
                "Dormitory" in now_scene_data.scene_tag
                or "Guest_Room" in now_scene_data.scene_tag
            ) and inventory.items(character_id)[152] >= 1:
                info_draw = draw.WaitDraw()
                info_draw.text = _(
                    "\n  ●你拿出了一次性万能钥匙，悄悄打开了门\n\n"
                )
                info_draw.draw()
                inventory.add_item(character_id, 152, -1)
                now_scene_data.close_flag = 0
                access_type = "open"
        # 其他不可进入情况
        if access_type not in ["open", "private"]:
            return access_type, [], [], 0
    return access_type, [], now_path_data[0], now_path_data[1]


def judge_character_move_to_private(
    character_id: int, move_path: list
) -> tuple[bool, bool]:
    """
    结算角色是否移动到私密房间：判定（private_move_outcome）之后当场结算（settle_private_move）\n
    Keyword arguments:\n
    character_id -- 角色id\n
    move_path -- 移动路径\n
    Return arguments:\n
    move_flag -- true的话就是移动\n
    wait_flag -- true的话就是等待\n
    """
    move_flag, wait_flag, outcome = private_move_outcome(
        character_id, move_path
    )
    settle_private_move(character_id, outcome)
    return move_flag, wait_flag


PRIVATE_MOVE_OUTCOMES = (
    "stop_follow",
    "give_up",
    "waiting_long",
    "barge_in",
    "wait_outside",
)
""" 私密房间前要结算的结果 """


def _private_move_text(outcome: str) -> str:
    """
    私密房间前的结果的提示文字
    Keyword arguments:
    outcome -- 结果
    Return arguments:
    str -- 带 {0}（角色名）的文字
    """
    return {
        "stop_follow": _("因为等待时间过长，所以{0}不再继续跟随\n"),
        "give_up": _("因为等待时间过长，所以{0}放弃了有些私密的打算\n"),
        "waiting_long": _("{0}有些私密的事想要找你，已经在门外等候多时了\n"),
        "barge_in": _("{0}等不下去了，决定直接进来\n"),
        "wait_outside": _("因为不方便进来，所以{0}正在外面等待\n"),
    }[outcome]


def private_move_outcome(
    character_id: int, move_path: list
) -> tuple[bool, bool, str]:
    """
    判定角色能否移动到私密房间，只读缓存\n
    Keyword arguments:\n
    character_id -- 角色id\n
    move_path -- 移动路径\n
    Return arguments:\n
    move_flag -- true的话就是移动\n
    wait_flag -- true的话就是等待\n
    outcome -- 要结算的结果：PRIVATE_MOVE_OUTCOMES 之一，没有要结算的时为空字符串\n
    """
    # 移动路径为空，直接返回
    if move_path == []:
        return False, True, ""
    # 进行私密跟随判断
    target_scene_str = map_handle.get_map_system_path_str_for_list(move_path)
    access_type = map_handle.judge_scene_accessible(
        target_scene_str, character_id
    )
    if access_type != "private":
        return True, False, ""
    wait_time = action_info.get(character_id, "follow_wait_time")
    setting = chara_profile.chara_setting(character_id)[0]
    # 超时后取消跟随
    if setting == 0:
        if wait_time < 30:
            return False, True, "wait_outside"
        # 如果是因为等待
        if flags.get(character_id, "is_follow") > 0:
            return False, False, "stop_follow"
        # 如果是因为想逆推
        if flags.get(character_id, "npc_masturebate_for_player"):
            # 如果门没关的话，就依然进去
            if cache.scene_data[target_scene_str].close_flag == 0:
                return True, False, ""
            # 超过一个小时就放弃逆推，否则门外等待
            if wait_time >= 60:
                return False, False, "give_up"
            return False, False, "waiting_long"
        return False, False, ""
    # 超时后仍继续等待
    if setting == 1:
        return False, True, "wait_outside"
    # 超时后直接闯入
    if setting == 2:
        if wait_time < 30:
            return False, True, "wait_outside"
        return True, False, "barge_in"
    # 一直跟随，无视私密地点
    return True, False, ""


def settle_private_move(character_id: int, outcome: str) -> None:
    """
    结算私密房间前的结果：取消跟随或放弃逆推，并显示提示\n
    Keyword arguments:\n
    character_id -- 角色id\n
    outcome -- private_move_outcome 交回的结果\n
    """
    if outcome not in PRIVATE_MOVE_OUTCOMES:
        return
    character_data: identity.Identity = identity.of(character_id)
    if outcome == "stop_follow":
        flags.set(character_id, is_follow=0)
    elif outcome == "give_up":
        flags.set(character_id, npc_masturebate_for_player=False)
    now_draw = draw.NormalDraw()
    now_draw.text = _private_move_text(outcome).format(character_data.name)
    now_draw.draw()
