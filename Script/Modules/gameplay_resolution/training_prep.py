"""
调教前准备（training_prep）
===========================
提供监禁调教道具表、道具序号到物品编号的映射，以及调教前准备的执行流程。
不依赖界面模块，供面板行动开始函数与监禁调教管理面板调用。
"""

import random
from types import FunctionType

from Script.Core import constant, game_type, get_text
from Script.Design import game_time, handle_premise, map_handle
from Script.Modules.domains import activity, dirty, h_state, inventory
from Script.Modules.domains import identity, prison, work
from Script.Modules.gameplay_resolution import plan_queue

_: FunctionType = get_text._
""" 翻译api """

body_item_list = [
    _("乳头夹"),
    _("阴蒂夹"),
    _("V震动棒"),
    _("A震动棒"),
    _("搾乳机"),
    _("采尿器"),
    _("眼罩"),
    _("肛门拉珠"),
    _("持续性利尿剂"),
    _("安眠药"),
    _("排卵促进药"),
    _("事前避孕药"),
    _("事后避孕药"),
    _("避孕套"),
]
""" 14 项调教道具的翻译显示名称列表，下标对应监禁调教道具序号 0 至 13 """


def get_item_id_from_body_item_list(body_item_id: int) -> int:
    """
    根据调教道具序号返回对应的物品配置编号。
    支持序号 0 至 13，其中序号 2 与 3 均映射到物品编号 125，其余序号返回 -1。
    Keyword arguments:
    body_item_id -- int，调教道具在 body_item_list 中的序号
    Return arguments:
    int -- 对应的物品编号，序号无效时返回 -1
    """
    item_id_dict = {
        0: 122,
        1: 123,
        2: 125,
        3: 125,
        4: 133,
        5: 134,
        6: 132,
        7: 129,
        8: 106,
        9: 107,
        10: 108,
        11: 101,
        12: 102,
        13: 120,
    }
    if body_item_id in item_id_dict:
        return item_id_dict[body_item_id]
    return -1


def start_training_preparation(target_character_id: int) -> None:
    """
    执行目标角色的调教前准备流程。
    随机选取 Humiliation_Room 场景，将目标、监狱长与玩家移入该场景。
    按监禁设置依次执行目标清洁、物品 100 润滑结算，以及玩家有库存的已启用道具。
    道具序号 13 扣减玩家库存并对玩家调用 handle_wear_condom，其余序号开启目标对应身体道具标记。
    序号 8 至 12 额外扣减库存并经监狱长触发对应 Settle 效果，最后为目标与监狱长各排入 10 分钟打断等待。
    Keyword arguments:
    target_character_id -- int，目标角色编号
    Return arguments:
    None -- 直接更新场景、物品、状态与行动队列
    """
    from Script.Settle import default

    target_character_data = identity.of(target_character_id)
    warden_id = work.warden()
    humiliation_room_list = map_handle.get_map_system_path_for_str(
        random.choice(constant.place_data["Humiliation_Room"])
    )
    map_handle.character_move_scene(
        activity.position(target_character_id),
        humiliation_room_list,
        target_character_id,
    )
    map_handle.character_move_scene(
        activity.position(warden_id), humiliation_room_list, warden_id
    )
    map_handle.character_move_scene(
        activity.position(0), humiliation_room_list, 0
    )
    if prison.cleaning():
        dirty.reset(target_character_data.cid)
    if prison.lubrication() and handle_premise.handle_have_body_lubricant(0):
        default.handle_use_body_lubricant(
            0,
            add_time=1,
            change_data=game_type.CharacterStatusChange(),
            now_time=game_time.now(),
        )
        default.handle_target_add_huge_lubrication(
            warden_id,
            add_time=1,
            change_data=game_type.CharacterStatusChange(),
            now_time=game_time.now(),
        )
    for i in range(len(body_item_list)):
        if prison.tool(i):
            item_id = get_item_id_from_body_item_list(i)
            item_num = inventory.items(0)[item_id]
            if item_num <= 0:
                continue
            if i == 13:
                default.handle_wear_condom(
                    0,
                    add_time=1,
                    change_data=game_type.CharacterStatusChange(),
                    now_time=game_time.now(),
                )
                inventory.add_item(0, item_id, -1)
            else:
                h_state.set_body_item(target_character_data.cid, i, True)
                if i in {8, 9, 10, 11, 12}:
                    inventory.add_item(0, item_id, -1)
                    if i == 8:
                        default.handle_target_diuretics_on(
                            warden_id,
                            add_time=1,
                            change_data=game_type.CharacterStatusChange(),
                            now_time=game_time.now(),
                        )
                    elif i == 9:
                        default.handle_target_add_tired_tosleep(
                            warden_id,
                            add_time=1,
                            change_data=game_type.CharacterStatusChange(),
                            now_time=game_time.now(),
                        )
                    elif i == 10:
                        default.handle_target_add_pregnancy_chance(
                            warden_id,
                            add_time=1,
                            change_data=game_type.CharacterStatusChange(),
                            now_time=game_time.now(),
                        )
                    elif i == 11:
                        default.handle_target_no_pregnancy_next_day(
                            warden_id,
                            add_time=1,
                            change_data=game_type.CharacterStatusChange(),
                            now_time=game_time.now(),
                        )
                    elif i == 12:
                        default.handle_target_no_pregnancy_from_last_h(
                            warden_id,
                            add_time=1,
                            change_data=game_type.CharacterStatusChange(),
                            now_time=game_time.now(),
                        )
    for waiting_id in (target_character_id, warden_id):
        plan_queue.plan_next(
            waiting_id,
            constant.Behavior.WAIT,
            10,
            target=target_character_id,
            state=constant.CharacterStatus.STATUS_WAIT,
            interrupt=True,
        )
