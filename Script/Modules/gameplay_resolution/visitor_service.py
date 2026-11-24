"""
访客服务（visitor_service）
===========================
提供空闲客房查询、客房排序键、邀请结算、访客抵达与离开、每日访客结算、去留判定与当日将离查询。
提示文本经 ui_hooks.emit_notice 发出，成就结算经 achievement_service.settle_and_notify 派发。
本模块不直接导入界面模块，供邀请访客面板、基地模块、行为结算与宿舍系统调用。
"""

import os
import random
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import character_handle, game_time, instuct_judege
from Script.Modules.domains import activity, chara_life, facility, flags
from Script.Modules.domains import identity, location, relations, roster
from Script.Modules.domains import visitor
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import recruit_service, ui_hooks

_: FunctionType = get_text._
""" 翻译api """


def get_empty_guest_room_id() -> int | bool:
    """
    查找首个已开放且无当前访客宿舍值与之同名的客房设施编号。
    按 facility.opens() 顺序检查编号 2001 至 2099 的客房设施。
    Return arguments:
    int | bool -- 首个匹配的空闲客房设施编号，无空闲客房时返回 False
    """
    guest_rooms = [
        room_id for room_id in facility.opens() if 2000 < room_id < 2100
    ]
    for room_id in guest_rooms:
        if not facility.is_open(room_id):
            continue
        room_name = game_config.config_facility_open[room_id].name
        have_visitor_flag = False
        for chara_id in visitor.visitors():
            if chara_life.dormitory(chara_id) == room_name:
                have_visitor_flag = True
                break
        if have_visitor_flag:
            continue
        return room_id
    return False


def sort_guest_room_key(room_path: str) -> int:
    """
    从客房路径末段提取客房序号作为排序键。
    路径按 os.sep 分隔后的末段不含“客房”或去掉“客房”后无法转为整数时返回 999。
    Keyword arguments:
    room_path -- str，客房路径字符串
    Return arguments:
    int -- 提取出的客房序号，解析失败时返回 999
    """
    room_name = room_path.split(os.sep)[-1]
    if "客房" in room_name:
        try:
            room_number = int(room_name.replace("客房", ""))
            return room_number
        except BaseException:
            return 999
    return 999


def update_invite_visitor() -> None:
    """
    检查访客邀请进度并在满 100 时触发目标访客抵达结算。
    无邀请目标或进度不足 100 时直接返回。
    调用 settle_visitor_arrivals 成功后调用 visitor.set_invite(0) 清空邀请。
    Return arguments:
    None -- 无返回值
    """

    target, progress = visitor.invite()
    if target == 0:
        return

    if progress >= 100:

        if settle_visitor_arrivals(visitor_id=target):
            visitor.set_invite(0)


def visitor_to_operator(character_id: int) -> None:
    """
    将指定临时访客转为正式干员。
    设置角色 vistor 标志为 2 并从访客列表移除，开放 NPC_id 与其模板号匹配的设施。
    最后调用 dormitory_common.new_character_get_dormitory 为其重新分配宿舍。
    Keyword arguments:
    character_id -- int，访客角色编号
    Return arguments:
    None -- 无返回值
    """
    from Script.System.Dormitory_System import common as dormitory_common

    character_data = identity.of(character_id)

    flags.set(character_id, vistor=2)

    visitor.leave(character_id)

    for open_cid in game_config.config_facility_open:
        if (
            game_config.config_facility_open[open_cid].NPC_id
            and game_config.config_facility_open[open_cid].NPC_id
            == character_data.adv
        ):
            facility.set_open(open_cid, True)

    dormitory_common.new_character_get_dormitory(character_id)


def settle_visitor_arrivals(visitor_id: int = 0) -> int:
    """
    结算一名新访客抵达罗德岛，经 ui_hooks.emit_notice 发等待确认、gold_enrod 与配置文本宽度提示。
    客房已满时发出无空房提示并返回 0，visitor_id 为 0 且当前所在地无候选时直接返回 0。
    有可接待访客时为其建档，发出抵达提示并结算访客类型成就，然后返回 1。
    Keyword arguments:
    visitor_id -- int，指定访客角色编号，默认 0 表示按当前所在地随机抽取
    Return arguments:
    int -- 成功接待访客返回 1，客房已满或无候选返回 0
    """

    if len(visitor.visitors()) >= visitor.capacity():
        notice_text = _(
            "\n ●由于没有空闲的客房，罗德岛没有接待到一名新抵达的访客\n"
        )
        ui_hooks.emit_notice(
            notice_text, wait=True, style="gold_enrod", use_text_width=True
        )
        return 0
    else:
        if visitor_id == 0:
            not_recruit_npc_id_list = recruit_service.find_recruitable_npc()
            now_country_id = location.country()
            now_country_npc_id_list = []
            for npc_id in not_recruit_npc_id_list:
                if relations.birthplace(npc_id) == now_country_id:
                    now_country_npc_id_list.append(npc_id)
            if len(now_country_npc_id_list):
                visitor_id = random.choice(now_country_npc_id_list)
            else:
                return 0
        character_handle.get_new_character(visitor_id, True)
        notice_text = _("\n ○【{0}】作为临时访客抵达了罗德岛\n").format(
            identity.of(visitor_id).name
        )
        ui_hooks.emit_notice(
            notice_text, wait=True, style="gold_enrod", use_text_width=True
        )
        achievement_service.settle_and_notify(_("访客"))
        return 1


def visitor_leave(character_id: int) -> None:
    """
    处理指定访客离开罗德岛的状态清理。
    将角色 vistor 标志设为 2，从访客列表与在编名册移除，并将位置重置为 ["0", "0"]。
    Keyword arguments:
    character_id -- int，离开访客的角色编号
    Return arguments:
    None -- 无返回值
    """

    flags.set(character_id, vistor=2)

    visitor.leave(character_id)

    roster.discard(character_id)

    activity.set_position(character_id, ["0", "0"])


def settle_visitor_arrivals_and_departures() -> None:
    """
    执行每日访客抵达与到期去留结算。
    基地移动标志为真时清标志并触发抵达，另按距上次随机来访天数乘以 3% 概率触发抵达并更新时间。
    随后遍历当前访客，对已到达或超过离开时刻的访客调用 judge_visitor_if_leave。
    Return arguments:
    None -- 无返回值
    """

    if visitor.moved():
        visitor.set_moved(False)
        settle_visitor_arrivals()

    add_day = game_time.count_day_for_datetime(
        visitor.last_arrival(), game_time.now()
    )
    visitor_come_possibility = add_day * 3
    if random.randint(1, 100) <= visitor_come_possibility:
        visitor.set_last_arrival(game_time.now())
        settle_visitor_arrivals()

    for visitor_id, leave_time in visitor.visitors().items():
        if game_time.judge_date_big_or_small(game_time.now(), leave_time):
            judge_visitor_if_leave(visitor_id)


def judge_visitor_if_leave(visitor_id: int) -> None:
    """
    判定指定访客停留期满后留下转正或离开罗德岛。
    按“访客留下”指令判定概率与随机抽签执行 visitor_to_operator 或 visitor_leave。
    状态更新后经 ui_hooks.emit_notice 以等待确认、gold_enrod 样式与配置文本宽度发出含意愿与结果的提示。
    Keyword arguments:
    visitor_id -- int，待判定的访客角色编号
    Return arguments:
    None -- 无返回值
    """
    character_data: identity.Identity = identity.of(visitor_id)
    _tem_1, _tem_2, stay_posibility = instuct_judege.calculation_instuct_judege(
        0, visitor_id, _("访客留下")
    )
    stay_text = next(
        attitude_data.name
        for attitude_data in game_config.config_visitor_stay_attitude.values()
        if stay_posibility < attitude_data.rate
    )
    notice_text = _(
        "\n 访客【{0}】预定的停留期限到了，她当前的留下意愿为：【{1}】"
    ).format(character_data.name, stay_text)
    if random.random() < stay_posibility:
        visitor_to_operator(visitor_id)
        notice_text += _(
            "\n ○【{0}】决定放弃离开，留在罗德岛成为一名正式干员\n"
        ).format(character_data.name)
        ui_hooks.emit_notice(
            notice_text, wait=True, style="gold_enrod", use_text_width=True
        )
    else:
        visitor_leave(visitor_id)
        notice_text += _("\n ●【{0}】打包好行李，离开了罗德岛\n").format(
            character_data.name
        )
        ui_hooks.emit_notice(
            notice_text, wait=True, style="gold_enrod", use_text_width=True
        )


def get_today_departing_visitors() -> list[int]:
    """
    查询离开时刻不晚于次日零点且留下意愿概率低于 0.5 的访客编号列表。
    以次日零点对比各访客离开时刻，并通过“访客留下”指令判定筛选留下概率低于 0.5 的访客。
    Return arguments:
    list[int] -- 当日将离开且留下概率低于 0.5 的访客角色编号列表
    """
    departing_visitors = []
    for visitor_id, leave_time in visitor.visitors().items():
        judge_time = game_time.get_sub_date(day=1)
        judge_time = judge_time.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        if game_time.judge_date_big_or_small(judge_time, leave_time):
            _tem_1, _tem_2, stay_posibility = (
                instuct_judege.calculation_instuct_judege(
                    0, visitor_id, _("访客留下")
                )
            )
            if stay_posibility < 0.5:
                departing_visitors.append(visitor_id)
    return departing_visitors
