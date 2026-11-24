"""随行为时间推进的实时结算：玩家实时数据、角色随时间自动变化的数值、精液流动与吸收、疲劳、休息与睡眠等"""

import random
import datetime
import functools
from fractions import Fraction
from types import FunctionType
from typing import TYPE_CHECKING
from Script.Core import game_path_config, constant, get_text, num
from Script.Design import (
    basement,
    game_time,
    handle_premise,
    handle_npc_ai_in_h,
    attr_calculation,
)
from Script.Modules.gameplay_resolution import semen_dirty_service, ui_hooks
from Script.Config import game_config
from Script.Modules.domains import abilities, action_info, activity, dirty
from Script.Modules.domains import entertainment, facility, flags, h_meters
from Script.Modules.domains import h_state, modes, needs, player_ability
from Script.Modules.domains import playthrough, pregnancy, prison, identity
from Script.Modules.domains import scene_state

if TYPE_CHECKING:
    from Script.Kernel import core

game_path = game_path_config.game_path
_: FunctionType = get_text._
""" 翻译api """

_drunk_sex_common = None
""" drunk_sex_common 模块的延迟导入缓存（规避循环导入，同时消除每角色每轮重复导入的开销） """
_common_default = None
""" common_default 模块的延迟导入缓存（同上） """
_map_handle = None
""" map_handle 模块的延迟导入缓存（同上） """

# 随时间增长的数值每分钟的基础量，取按段取整的结算在行为快照场景里的实际增长率：按段取整时干员 1~5 分钟的短段
# 平均只得到公式的一部分，玩家的 5 分钟等待则因每段至少 1 点疲劳而多得
TIRED_PER_MINUTE_PLAYER = Fraction(11, 60)
""" 玩家醒着时每分钟的疲劳 """
TIRED_PER_MINUTE_NPC = Fraction(7, 72)
""" 干员醒着时每分钟的疲劳 """
URINE_PER_MINUTE = Fraction(4, 5)
""" 每分钟的尿意（尿意增长难度为「中」时；难度按 设置值/2 缩放） """
HUNGER_PER_MINUTE = Fraction(3, 4)
""" 体力气力全满时每分钟的饥饿 """
MILK_PER_MINUTE = Fraction(3, 8)
""" 有泌乳素质的干员每分钟的乳汁 """


def judge_pl_real_time_data() -> None:
    """
    玩家实时数据结算\n
    Keyword arguments:
    无\n
    Return arguments:
    无
    """

    love_hotel_room_lv = entertainment.hotel_room()

    # 酒店退房时间到了则退房
    if love_hotel_room_lv > 0:
        if (
            game_time.judge_date_big_or_small(
                game_time.now(), action_info.get(0, "check_out_time")
            )
            > 0
        ):
            # 输出提示信息
            room_name = [_("标间"), _("情趣主题房"), _("顶级套房")]
            ui_hooks.emit_notice(
                _("\n您入住的{0}到退房时间了，已自动退房\n").format(
                    room_name[love_hotel_room_lv - 1]
                )
            )
            # 结算
            entertainment.set_hotel_room(0)
            action_info.set(0, "check_out_time", datetime.datetime(1, 1, 1))

    # 体外无壳卵：排出满1小时的卵进行受精判定
    from Script.System.Pregnancy_System import soft_egg_handle

    soft_egg_handle.check_soft_eggs_fertilization()


def character_aotu_change_value(
    character_id: int,
    now_time: datetime.datetime,
    since: datetime.datetime,
) -> None:
    """
    结算角色随时间自动增加的数值：当前行为与 (since, now_time) 重叠的那段，每分钟按比率精确累加，
    所以怎样切段结算合计都一样；重叠 0 分钟时不改数值
    Keyword arguments:
    character_id -- 角色id
    now_time -- 结算到的时间
    since -- 从这一时刻算起
    """
    # 延迟导入并缓存，避免循环导入且不在热路径反复执行导入机制
    global _drunk_sex_common
    if _drunk_sex_common is None:
        from Script.System.Sex_System import drunk_sex_common as _drunk_module

        _drunk_sex_common = _drunk_module
    drunk_sex_common = _drunk_sex_common
    now_character_data: identity.Identity = identity.of(character_id)
    now_behavior_id = activity.behavior(character_id).behavior_id
    if not identity.exists(activity.target(character_id)):
        activity.set_target(character_id, character_id)
    # 获取实际增加时间
    true_add_time = get_true_add_time(character_id, now_time, since)

    # 性技实操课的三次提醒（Plan 22 四期 §3.28.6）
    # 一律用跨越判定（上次结算 < 提醒时刻 <= 当前）：时钟按 5 分钟与行动的结束跳跃，
    #    提醒时刻不一定正好被停到，用等于判定的话提醒可能永远不会触发
    if character_id == 0:
        settle_sex_class_notify(
            now_character_data, now_behavior_id, now_time, since
        )
    if true_add_time == 0:
        return

    # 结算疲劳值
    settle_tired(character_id, true_add_time)

    # 休息时回复体力、气力
    if now_behavior_id == constant.Behavior.REST:
        settle_rest(character_id, true_add_time)

    # 睡觉时大量减少疲劳值，增加熟睡值，回复体力、气力
    elif now_behavior_id == constant.Behavior.SLEEP:
        settle_sleep(character_id, true_add_time)

    # 结算尿意值
    if character_id != 0 or playthrough.setting(playthrough.DIFFICULTY, 12):
        add_urinate: num.Num = num.jitter(
            true_add_time * URINE_PER_MINUTE, 80, 120
        ) * Fraction(playthrough.setting(playthrough.DIFFICULTY, 11), 2)
        needs.add(character_id, "urine", add_urinate, max=300)

    # 获取当前体力气力与最大值的比例，当前比例越低，调整系数越高，最高为无体力时的2倍，最低为满比例时的1倍
    # 比例读体力气力的整数部分：它们反馈进饥饿的比率，读精确值会让分母逐段变大
    hit_adjust_coefficient = 2 - Fraction(
        num.whole(needs.of(character_id)["hit"]),
        needs.of(character_id)["hit_max"],
    )
    mana_adjust_coefficient = 2 - Fraction(
        num.whole(needs.of(character_id)["mana"]),
        needs.of(character_id)["mana_max"],
    )

    # 结算饥饿值
    add_hunger: num.Num = (
        num.jitter(true_add_time * HUNGER_PER_MINUTE, 80, 120)
        * hit_adjust_coefficient
        * mana_adjust_coefficient
    )
    needs.add(character_id, "hunger", add_hunger, max=240)

    # 结算醉酒值
    drunk_sex_common.reduce_drunk_point(character_id, true_add_time)

    # 结算玩家
    if character_id == 0:
        # 非H模式下结算玩家的射精值减少
        if not flags.get(character_id, "is_h"):
            # 上次射精时间距离现在超过30分钟则射精值减少
            last_time = action_info.get(character_id, "last_eaj_add_time")
            if (game_time.now() - last_time) > datetime.timedelta(minutes=30):
                h_meters.add(character_id, "eja", -true_add_time * 10, min=0)

        # 玩家缓慢恢复精液量
        add_semen: num.Num = Fraction(true_add_time, 20)
        h_meters.add(
            character_id,
            "semen",
            add_semen,
            max=h_meters.of(character_id)["semen_max"],
        )

        # 结算玩家源石技艺的理智值消耗
        settle_player_ability(character_id, true_add_time)

        # 非时停中，当前地点有人睡觉时，结算玩家动作对所有睡眠NPC的影响
        if not handle_premise.handle_time_stop_on(
            character_id
        ) and handle_premise.handle_scene_someone_sleeping(character_id):
            settle_sleep_h(character_id, true_add_time)

    # 结算干员
    else:
        # 结算精液流动
        if dirty.has_semen_flow(character_id):
            settle_semen_flow(character_id, true_add_time)

        # 结算精液消化吸收
        if dirty.body_semen_amount(character_id, 8) > 0:
            semen_absorb(character_id, true_add_time, 8)
        if dirty.body_semen_amount(character_id, 15) > 0:
            semen_absorb(character_id, true_add_time, 15)

        # 结算乳汁量，仅结算有泌乳素质的
        if abilities.talent(character_id)[27]:
            add_milk = num.jitter(true_add_time * MILK_PER_MINUTE, 80, 120)
            milk_max = pregnancy.milk_max(character_id)
            needs.add(character_id, "milk", add_milk, max=milk_max)

        # 有意识下的部分持续结算
        if (
            handle_premise.handle_unconscious_flag_0(character_id)
            and handle_premise.handle_normal_1(character_id)
            and handle_premise.handle_normal_5(character_id)
            and handle_premise.handle_normal_6(character_id)
        ):
            settle_conscious_continuous(character_id, true_add_time)


def settle_sex_class_notify(
    pl_character_data: identity.Identity,
    now_behavior_id: str,
    now_time: datetime.datetime,
    since: datetime.datetime,
) -> None:
    """
    输出性技实操课的三次提醒（Plan 22 四期 §3.28.6、§3.28.9）

        1. 预约日当天玩家起床后 —— "今天几点在哪间教室有一节你安排的课"
        2. 节次开始前30分钟 —— "选修与点名必修的学生会在开课前 10 分钟动身赶来"
        3. 预定的下课时刻 —— "可以就此结束，也可以继续下去"，只在课上着的时候才发

    第三次的措辞必须写明不强制，否则玩家会以为系统在催他下课——
       玩家还在课堂 H 里时，下课时间由玩家手动决定，系统不自动下课；
       课堂 H 以别的方式结束（玩家已不在 H）时，由 settle_orphan_class 一并下课（Plan 32 §3.1）。
    Keyword arguments:
    pl_character_data -- 玩家角色数据
    now_behavior_id -- 玩家当前的行为id
    now_time -- 当前时刻
    since -- 上一次结算到的时刻；只发 (since, now_time] 里跨过的提醒
    Return arguments:
    无
    """
    from Script.System.Education_System import sex_class_handle

    text_list = []
    start_time = activity.behavior(pl_character_data.cid).start_time or since
    # 第一次：起床时，只在结算到起床开始的那一段里发
    if (
        now_behavior_id == constant.Behavior.GET_UP
        and since <= start_time < now_time
    ):
        wake_text = sex_class_handle.get_today_class_notify_text()
        if wake_text:
            text_list.append(wake_text)
    # 第二、三次：跨越判定，从行为开始与上一次结算中更晚的那个算起
    text_list.extend(
        sex_class_handle.check_and_send_notify(max(start_time, since), now_time)
    )
    for now_text in text_list:
        ui_hooks.emit_notice(now_text, use_text_width=True)


def get_true_add_time(
    character_id: int,
    now_time: datetime.datetime,
    since: datetime.datetime,
) -> int:
    """
    获取真实的行动时间\n
    Keyword arguments:\n
    character_id -- 角色id\n
    now_time -- 当前时间\n
    since -- 从这一时刻算起\n
    Return arguments:\n
    true_add_time -- 真实的行动时间\n
    """
    now_behavior = activity.behavior(character_id)
    add_time = now_behavior.duration
    # 真实的开始时间是当前角色行动开始时间和 since 中更晚的那个
    now_character_behavior_start_time = now_behavior.start_time
    true_start_time = max(now_character_behavior_start_time, since)
    # 真实的结束时间是当前角色行动结束时间和当前时间中更早的那个
    now_character_end_time = game_time.get_sub_date(
        minute=add_time, old_date=now_character_behavior_start_time
    )
    true_end_time = min(now_character_end_time, now_time)
    # 真实的行动时间是真实的结束时间减去真实的开始时间
    true_add_time = int((true_end_time - true_start_time).total_seconds() / 60)
    # 避免负数
    true_add_time = max(true_add_time, 0)
    return true_add_time


def settle_semen_flow(character_id: int, true_add_time: int) -> None:
    """
    结算精液流动\n
    Keyword arguments:\n
    character_id -- 角色id\n
    true_add_time -- 实际行动时间\n
    """
    # 每个目标每分钟最多流入 2 ml
    flow_semen_max = true_add_time * 2

    new_flow_list = []
    # 遍历每个部位的精液流动
    for all_flow_dict in dirty.view(character_id).semen_flow:
        # 如果all_flow_dict没有键"targets"，则跳过
        if "targets" not in all_flow_dict:
            continue
        # 实际流动的精液总量
        all_real_flow = 0
        # 源头数据
        source_id = all_flow_dict["source"]["id"]
        source_type = all_flow_dict["source"]["type"]
        new_target_list = []
        # 遍历每个流动的目标
        for now_flow_dict in all_flow_dict["targets"]:
            if now_flow_dict["remaining_volume"] > 0:
                # 计算该部位的精液流动
                now_flow = min(
                    flow_semen_max, now_flow_dict["remaining_volume"]
                )
                all_real_flow += now_flow
                now_flow_dict["remaining_volume"] -= now_flow
                now_part_cid = now_flow_dict["id"]
                semen_dirty_service.update_semen_dirty(
                    character_id=character_id,
                    part_cid=now_part_cid,
                    part_type=now_flow_dict["type"],
                    semen_count=now_flow,
                    update_shoot_position_flag=False,
                )
                # 如果目标部位的精液流动完毕，则将其从流动列表中移除
                if now_flow_dict["remaining_volume"] > 0:
                    new_target_list.append(now_flow_dict)
        # 更新流动的目标列表
        all_flow_dict["targets"] = new_target_list
        # 遍历完全目标后，如果实际流动的精液总量大于0，则在源头部位减少相应的精液量
        if all_real_flow > 0:
            semen_dirty_service.update_semen_dirty(
                character_id=character_id,
                part_cid=source_id,
                part_type=source_type,
                semen_count=-all_real_flow,
                update_shoot_position_flag=False,
            )
        # 如果源头部位的精液流动完毕，则将其从流动列表中移除，否则将其加入新的流动列表
        if len(all_flow_dict["targets"]):
            new_flow_list.append(all_flow_dict)
    # 更新流动的源头列表
    with dirty.editing(character_id) as d:
        d.semen_flow = new_flow_list


def semen_absorb(character_id: int, true_add_time: int, body_part: int) -> None:
    """
    结算精液吸收\n
    Keyword arguments:\n
    character_id -- 角色id\n
    true_add_time -- 实际行动时间\n
    body_part -- 身体部位id\n
    """
    now_body_semen = dirty.body_semen_amount(character_id, body_part)
    # 如果当前部位没有精液则返回
    if now_body_semen <= 0:
        return
    # 每分钟吸收 1/5 毫升或当前精液量（整数部分）的 1/500 中较大的那个，即每 5 分钟 1 毫升或 1%；不得高于当前精液量
    absorb_ml = min(
        max(Fraction(1, 5), Fraction(num.whole(now_body_semen), 500))
        * true_add_time,
        now_body_semen,
    )
    with dirty.editing(character_id) as d:
        # 从角色身体中吸收精液
        d.body_semen[body_part][1] -= absorb_ml
        # 更新吸收精液量
        d.absorbed_total_semen += absorb_ml
        # 根据吸收的精液量来减少饥饿度
        needs.add(character_id, "hunger", -absorb_ml, min=0)
        # 如果现存量小于3ml，则清零
        if d.body_semen[body_part][1] < 3:
            d.body_semen[body_part][1] = 0
        # 更新等级
        d.body_semen[body_part][2] = attr_calculation.get_semen_now_level(
            d.body_semen[body_part][1], body_part, 0
        )


def change_character_persistent_state(character_id: int) -> None:
    """
    结算角色的状态是否会持续\n
    Keyword arguments:\n
    character_id -- 角色id\n
    """
    now_time = game_time.now()
    ids = None if flags.get(character_id, "is_h") else (8, 9)
    for item_id, end_time in h_state.active_body_items(character_id, ids):
        if end_time is not None and game_time.judge_date_big_or_small(
            now_time, end_time
        ):
            h_state.set_body_item(character_id, item_id, False, None)


def settle_tired(character_id: int, true_add_time: int) -> None:
    """
    疲劳值结算：不睡觉、不在时停中时，每分钟增加 TIRED_PER_MINUTE_PLAYER / TIRED_PER_MINUTE_NPC，最多到 160
    参数:
        character_id (int): 角色ID
        true_add_time (int): 实际行动时间（分钟）
    返回:
        None
    """
    if activity.behavior(
        character_id
    ).behavior_id == constant.Behavior.SLEEP or not handle_premise.handle_time_stop_off(
        character_id
    ):
        return
    global _drunk_sex_common
    if _drunk_sex_common is None:
        from Script.System.Sex_System import drunk_sex_common as _drunk_module

        _drunk_sex_common = _drunk_module
    tired_change: num.Num = true_add_time * (
        TIRED_PER_MINUTE_PLAYER if character_id == 0 else TIRED_PER_MINUTE_NPC
    )
    # 当前在香薰疗愈-疲劳状态下，疲劳值增加减少
    if handle_premise.handle_aromatherapy_flag_8(character_id):
        tired_change *= Fraction(4, 5)
    # 在喝醉的情况下，根据醉酒等级来提升疲劳值增加速度
    drunk_level, __ = _drunk_sex_common.get_drunk_level(character_id)
    if drunk_level > 0:
        tired_change *= 1 + Fraction(drunk_level, 10)
    needs.add(character_id, "tired", tired_change, max=160)


def settle_rest(character_id: int, true_add_time: int) -> None:
    """
    休息状态结算：恢复体力和气力
    参数:
        character_id (int): 角色ID
        true_add_time (int): 实际行动时间（分钟）
    返回:
        None
    """
    # 休息室对回复效果的影响
    talent = abilities.talent(character_id)
    final_adjust: num.Num
    if handle_premise.handle_in_rest_room_or_dormitory(character_id):
        now_level = facility.level(31)
        facility_cid = game_config.config_facility_effect_data[_("休息室")][
            int(now_level)
        ]
        facility_effect = game_config.config_facility_effect[
            facility_cid
        ].effect
        final_adjust = 1 + Fraction(facility_effect, 100)
    else:
        final_adjust = Fraction(3, 10)
    # 素质对回复效果的影响
    if talent[351]:
        final_adjust *= Fraction(7, 10)
    elif talent[352]:
        final_adjust *= Fraction(3, 2)
    # 监禁条件判定
    if handle_premise.handle_imprisonment_1(character_id):
        setting = prison.setting(4)
        if setting == 0:
            final_adjust *= Fraction(1, 2)
        elif setting == 2:
            final_adjust *= Fraction(3, 2)
    # 回复体力和气力
    maxima = needs.of(character_id)
    hp_base = maxima["hit_max"] * Fraction(3, 1000) + 10
    mp_base = maxima["mana_max"] * Fraction(3, 500) + 20
    add_hp: num.Num = hp_base * true_add_time * final_adjust
    add_mp: num.Num = mp_base * true_add_time * final_adjust
    needs.add(character_id, "hit", add_hp, max=maxima["hit_max"])
    needs.add(character_id, "mana", add_mp, max=maxima["mana_max"])


def settle_sleep(character_id: int, true_add_time: int) -> None:
    """
    睡眠状态结算：每分钟减少疲劳 1/3，增加熟睡，恢复体力和气力
    参数:
        character_id (int): 角色ID
        true_add_time (int): 实际行动时间（分钟）
    返回:
        None
    """
    from Script.System.Dormitory_System import dormitory_manager_system

    talent = abilities.talent(character_id)
    now_char = identity.of(character_id)
    # 疲劳值越高，熟睡值增加越快，最高为疲劳值满时的2倍；读疲劳的整数部分，免得熟睡值的分母逐段变大
    tired_adjust = 1 + Fraction(num.whole(needs.of(character_id)["tired"]), 160)
    # 减少疲劳
    tired_change: num.Num = Fraction(true_add_time, 3)
    needs.add(character_id, "tired", -tired_change, min=0)
    # 增加熟睡值
    level, __ = attr_calculation.get_sleep_level(
        needs.of(character_id)["sleep"]
    )
    add_sleep: num.Num
    if level <= 1:
        add_sleep = true_add_time * tired_adjust * Fraction(3, 2)
    else:
        add_sleep = (
            true_add_time
            * tired_adjust
            * Fraction(random.randint(-30, 60), 100)
        )
    # 疲劳已完全恢复，且是白天，且没有服用安眠药，且非醉酒，则熟睡值减少
    if (
        handle_premise.handle_tired_le_0(character_id)
        and handle_premise.handle_time_day(character_id)
        and handle_premise.handle_self_not_sleep_pills(character_id)
        and handle_premise.handle_drunk_level_0(character_id)
    ):
        sleep_point: num.Num = needs.of(character_id)["sleep"] - add_sleep
        needs.set(character_id, sleep=min(max(sleep_point, 0), 100))
        # 熟睡值已减少到0时NPC直接醒来
        if needs.of(character_id)["sleep"] <= 0 and character_id:
            # 玩家与该角色在同一地点，且玩家正在对该角色睡奸中，则结算从无意识H中恢复意识
            if (
                activity.position(0) == activity.position(character_id)
                and activity.target(0) == character_id
                and flags.get(character_id, "unconscious_h") == 1
            ):
                info_text = _("\n{0}已经睡饱了，从睡梦中自然苏醒过来\n").format(
                    now_char.name
                )
                handle_npc_ai_in_h.recover_from_unconscious_h(0, info_text)
            # 否则打断睡眠，她在自己的行动结束处交由AI选择新行动
            else:
                from Script.Modules.gameplay_resolution import plan_queue

                plan_queue.interrupt(character_id)
            # 已醒来，跳过后续的睡眠回复结算
            return
    # 其他情况下正常增加熟睡值
    else:
        raised: num.Num = needs.of(character_id)["sleep"] + add_sleep
        needs.set(character_id, sleep=min(max(raised, 0), 100))
    # 回复体力和气力
    final_adjust: num.Num = 1
    if talent[351]:
        final_adjust *= Fraction(7, 10)
    elif talent[352]:
        final_adjust *= Fraction(3, 2)
    # 监禁条件判定
    if handle_premise.handle_imprisonment_1(character_id):
        setting = prison.setting(4)
        if setting == 0:
            final_adjust *= Fraction(1, 2)
        elif setting == 2:
            final_adjust *= Fraction(3, 2)
    # 宿舍的影响
    else:
        final_adjust *= num.exact(basement.calc_facility_efficiency(4))
        knowledge_level = (
            dormitory_manager_system.get_dormitory_manager_knowledge(
                character_id
            )
        )
        final_adjust *= 1 + Fraction(knowledge_level, 20)
    maxima = needs.of(character_id)
    hp_base = maxima["hit_max"] * Fraction(1, 400) + 3
    mp_base = maxima["mana_max"] * Fraction(1, 200) + 6
    add_hp: num.Num = hp_base * true_add_time * final_adjust
    add_mp: num.Num = mp_base * true_add_time * final_adjust
    needs.add(character_id, "hit", add_hp, max=maxima["hit_max"])
    needs.add(character_id, "mana", add_mp, max=maxima["mana_max"])


def settle_player_ability(character_id: int, true_add_time: int) -> None:
    """
    玩家源石技艺结算：视觉系技艺每分钟消耗理智 1/12（乘倍率），时停每分钟消耗 2；理智不足时耗到 0
    参数:
        character_id (int): 角色ID（玩家为0）
        true_add_time (int): 实际行动时间（分钟）
    返回:
        None
    """
    talent = abilities.talent(character_id)
    # 视觉系技艺消耗
    if player_ability.get(character_id, "visual"):
        multiple = talent[307] + talent[308] + talent[309]
        down_sp = min(
            Fraction(true_add_time, 12) * max(multiple, 1),
            needs.of(character_id)["sanity"],
        )
        needs.add(character_id, "sanity", -down_sp)
        player_ability.add_sanity_cost(character_id, down_sp)
    # 时停系技艺消耗
    if handle_premise.handle_time_stop_on(character_id):
        down_sp = min(true_add_time * 2, needs.of(character_id)["sanity"])
        needs.add(character_id, "sanity", -down_sp)
        player_ability.add_sanity_cost(character_id, down_sp)


ARTS_BREAK_EXEMPT = frozenset(
    {
        constant.Behavior.HYPNOSIS_CANCEL,
        constant.Behavior.TIME_STOP_OFF,
        constant.Behavior.LOW_OBSCENITY_ANUS,
        constant.Behavior.HIGH_OBSCENITY_ANUS,
        constant.Behavior.DO_H_FAIL,
    }
)
""" 玩家在做这些行为时理智耗尽，技艺不中断 """


def _arts_ends_to_plan(
    game: "core.GameState | None" = None,
) -> list[str]:
    """
    要给玩家排上的解除行为：催眠或时停还开着、解除行为还没排上
    Return arguments:
    list -- 解除催眠、解除时停的行为id
    """
    from Script.Modules.gameplay_resolution import plan_queue

    ends: list[str] = []
    if handle_premise.handle_target_in_hypnosis(0):
        ends.append(constant.Behavior.HYPNOSIS_CANCEL)
    if modes.time_stop(game):
        ends.append(constant.Behavior.TIME_STOP_OFF)
    return [b for b in ends if not plan_queue.plan_has(0, b, game)]


def arts_break_due(game: "core.GameState | None" = None) -> bool:
    """
    玩家理智耗尽、还有源石技艺开着且没排上解除
    Return arguments:
    bool -- 该中断技艺时为真
    """
    if (
        needs.of(0, game)["sanity"] > 0
        or activity.behavior(0, game).behavior_id in ARTS_BREAK_EXEMPT
    ):
        return False
    return bool(
        player_ability.get(0, "visual", game) or _arts_ends_to_plan(game)
    )


def break_arts() -> "core.Effects":
    """
    理智耗尽，开着的源石技艺全部中断：关透视，给玩家排上解除催眠与解除时停
    Return arguments:
    Effects -- 要交回内核的打断
    """
    from Script.Modules.gameplay_resolution import instruct_plan_service as ips

    ui_hooks.emit_notice(
        _("\n理智值不足，开启的源石技艺已全部中断\n"),
        wait=True,
        style="red",
        use_text_width=True,
    )
    needs.set(0, sanity=0)
    player_ability.set(0, visual=False)
    items: list[core.Effect] = []
    for behavior_id in _arts_ends_to_plan():
        items.extend(ips.plan_instruct_common_settle(behavior_id))
    return tuple(items)


def get_sleep_disturbance_value(
    behavior_id: str, true_add_time: int
) -> num.Num:
    """
    根据玩家行为类型计算对睡眠角色熟睡程度的减轻量：每分钟按行为类型的系数
    参数:
        behavior_id (str): 行为id
        true_add_time (int): 实际行动时间（分钟）
    返回:
        Num -- 本次行为对熟睡程度的减轻量
    """
    behavior_data = game_config.config_behavior.get(behavior_id)
    tags = getattr(behavior_data, "tag", "") if behavior_data else ""

    # 影响排序：插入 > 道具/侍奉 > 性爱 > 非性爱
    factor: num.Num
    if "插入" in tags:
        factor = 3
    elif "道具" in tags or "侍奉" in tags:
        factor = 2
    elif "性爱" in tags:
        factor = 1
    else:
        factor = Fraction(1, 2)
    return true_add_time * factor


def settle_sleep_h(character_id: int, true_add_time: int) -> None:
    """
    结算玩家当前场景内所有睡眠NPC的熟睡程度变化与被吵醒判定
    参数:
        character_id (int): 角色ID
        true_add_time (int): 实际行动时间（分钟）
    返回:
        None
    """
    # 延迟导入并缓存，避免循环导入且不在热路径反复执行导入机制
    global _map_handle, _drunk_sex_common
    if _map_handle is None:
        from Script.Design import map_handle as _map_handle_module

        _map_handle = _map_handle_module
    map_handle = _map_handle
    if _drunk_sex_common is None:
        from Script.System.Sex_System import drunk_sex_common as _drunk_module

        _drunk_sex_common = _drunk_module
    drunk_sex_common = _drunk_sex_common

    scene_path_str = map_handle.get_map_system_path_str_for_list(
        activity.position(character_id)
    )

    # 遍历玩家当前场景内所有睡眠中的NPC
    for sleeper_id in list(scene_state.occupants(scene_path_str)):
        # 上一个被吵醒的角色可能已经把玩家赶出了本场景，此时不再继续结算，避免玩家被连续推开多个场景
        if (
            map_handle.get_map_system_path_str_for_list(
                activity.position(character_id)
            )
            != scene_path_str
        ):
            break
        # 跳过玩家和非睡眠角色
        if sleeper_id == 0:
            continue
        sleeper_data: identity.Identity = identity.of(sleeper_id)
        if activity.behavior(sleeper_id).behavior_id != constant.Behavior.SLEEP:
            continue
        # 等待、休息、睡觉行为，或目标服用安眠药、烂醉爆睡时不受影响
        # 烂醉豁免与安眠药同级：深度昏睡状态不会被动静吵醒，否则会反复吵醒后又立刻重新爆睡
        if (
            activity.behavior(character_id).behavior_id
            in {
                constant.Behavior.WAIT,
                constant.Behavior.REST,
                constant.Behavior.SLEEP,
            }
            or h_state.body_item_on(sleeper_id, 9)
            or drunk_sex_common.get_drunk_level(sleeper_id)[0] >= 3
        ):
            continue

        # 计算本次动作对熟睡程度的影响
        down_sleep = get_sleep_disturbance_value(
            activity.behavior(character_id).behavior_id, true_add_time
        )

        # 仅玩家当前睡奸目标使用完整影响，非睡奸目标影响减半
        is_sleep_h_target = (
            sleeper_id == activity.target(character_id)
            and flags.get(sleeper_data.cid, "unconscious_h") == 1
        )
        if not is_sleep_h_target:
            down_sleep = Fraction(down_sleep, 2)
        if down_sleep <= 0:
            continue

        # 减少熟睡程度；睡眠等级大于1时也照常结算，只是不会进入醒来判定
        needs.set(
            sleeper_id, sleep=max(0, needs.of(sleeper_id)["sleep"] - down_sleep)
        )

        # 重新计算当前熟睡等级
        sleep_level, __ = attr_calculation.get_sleep_level(
            needs.of(sleeper_id)["sleep"]
        )
        # 只有睡眠等级小于等于1时才判定是否被吵醒
        if sleep_level <= 1:
            handle_npc_ai_in_h.judge_weak_up_in_sleep_h(
                character_id, sleeper_id
            )


def settle_conscious_continuous(character_id: int, true_add_time: int) -> None:
    """
    有意识下持续结算：羞耻、苦痛、欲情等状态增减
    参数:
        character_id (int): 角色ID
        true_add_time (int): 实际行动时间（分钟）
    返回:
        None
    """
    # 延迟导入并缓存，避免循环导入且不在热路径反复执行导入机制
    global _common_default, _map_handle
    if _common_default is None:
        from Script.Settle import common_default as _common_default_module
        from Script.Design import map_handle as _map_handle_module

        _common_default = _common_default_module
        _map_handle = _map_handle_module
    # 时间结算：状态的最终值保留精确值
    base_chara_state_common_settle = functools.partial(
        _common_default.base_chara_state_common_settle, exact=True
    )
    map_handle = _map_handle
    now_char_ability = abilities.ability(character_id)
    # 场景内的角色总数（只计算一次，后续判定复用）
    scene_chara_count = len(
        map_handle.get_chara_now_scene_all_chara_id_list(character_id)
    )
    # 场景内减去自己和玩家之外的角色数量
    others_count = scene_chara_count - 2
    # 限制最大加成
    other_chara_count_adjust = min(Fraction(others_count, 10), 2)
    # 和周围其他人相关的结算（场景角色数>2，等价于 handle_scene_over_two，复用已计算的人数）
    if scene_chara_count > 2:
        # 群交中增加羞耻和心理快感
        if handle_premise.handle_group_sex_mode_on(
            character_id
        ) and handle_premise.handle_self_is_h(character_id):
            base_chara_state_common_settle(
                character_id,
                add_time=true_add_time,
                state_id=16,
                base_value=0,
                ability_level=now_char_ability[34],
                extra_adjust=other_chara_count_adjust,
                tenths_add=False,
            )
            base_chara_state_common_settle(
                character_id,
                add_time=true_add_time,
                state_id=23,
                base_value=0,
                ability_level=now_char_ability[34],
                extra_adjust=other_chara_count_adjust,
                tenths_add=False,
            )
        # 需要周围有除了自己和玩家以外的有意识且没睡觉的其他人
        if handle_premise.handle_scene_others_conscious(character_id):
            # 自己未穿胸衣和内裤、自己异常2正常时羞耻
            if handle_premise.handle_not_wear_bra_or_pan(
                character_id
            ) and handle_premise.handle_normal_2(character_id):
                extra = 0
                if handle_premise.handle_not_wear_bra(character_id):
                    extra += 1
                if handle_premise.handle_not_wear_pan(character_id):
                    extra += 2
                base_chara_state_common_settle(
                    character_id,
                    add_time=true_add_time,
                    state_id=16,
                    base_value=0,
                    ability_level=now_char_ability[34],
                    extra_adjust=extra,
                    tenths_add=False,
                )
            # 隐奸中增加羞耻和心理快感
            if handle_premise.handle_hidden_sex_mode_ge_1(character_id):
                hidden_sex_mode = flags.get(character_id, "hidden_sex_mode")
                extra_add = 4 - hidden_sex_mode + Fraction(others_count, 10)
                base_chara_state_common_settle(
                    character_id,
                    add_time=true_add_time * 5,
                    state_id=16,
                    base_value=0,
                    ability_level=now_char_ability[34],
                    extra_adjust=extra_add,
                    tenths_add=False,
                )
                base_chara_state_common_settle(
                    character_id,
                    add_time=true_add_time * 5,
                    state_id=23,
                    base_value=0,
                    ability_level=now_char_ability[34],
                    extra_adjust=extra_add,
                    tenths_add=False,
                )
    # 露出中增加羞耻和心理快感
    if handle_premise.handle_exhibitionism_sex_mode_ge_1(character_id):
        base_chara_state_common_settle(
            character_id,
            add_time=true_add_time * 3,
            state_id=16,
            base_value=0,
            ability_level=now_char_ability[34],
            extra_adjust=other_chara_count_adjust,
            tenths_add=False,
        )
        base_chara_state_common_settle(
            character_id,
            add_time=true_add_time * 3,
            state_id=23,
            base_value=0,
            ability_level=now_char_ability[34],
            extra_adjust=other_chara_count_adjust,
            tenths_add=False,
        )
    # 女儿与自己H时增加欲情和心理快感
    if handle_premise.handle_self_is_player_daughter(
        character_id
    ) and handle_premise.handle_self_is_h(character_id):
        base_chara_state_common_settle(
            character_id,
            add_time=true_add_time * 5,
            state_id=12,
            base_value=0,
            ability_level=now_char_ability[33],
            extra_adjust=5,
            tenths_add=False,
        )
        base_chara_state_common_settle(
            character_id,
            add_time=true_add_time * 5,
            state_id=23,
            base_value=0,
            ability_level=now_char_ability[33],
            extra_adjust=5,
            tenths_add=False,
        )
    # 灌肠苦痛增加
    if handle_premise.handle_enema(character_id):
        extra = dirty.enema_capacity(character_id)
        base_chara_state_common_settle(
            character_id,
            add_time=true_add_time * 5,
            state_id=17,
            base_value=0,
            ability_level=now_char_ability[15],
            extra_adjust=extra,
            tenths_add=False,
        )
    # 捆绑时欲情、羞耻、苦痛
    if handle_premise.handle_self_now_bondage(character_id):
        bond_id = h_state.get(character_id, "bondage")
        data = game_config.config_bondage[bond_id]
        adjust = Fraction(data.level, 2)
        for sid in (12, 16, 17):
            base_chara_state_common_settle(
                character_id,
                add_time=true_add_time * 3,
                state_id=sid,
                base_value=0,
                ability_level=now_char_ability[
                    33 if sid == 12 else 34 if sid == 16 else 15
                ],
                extra_adjust=adjust,
                tenths_add=False,
            )
    # 破处下增加苦痛
    first_sex_adjust = 0
    if character_id != 0 and handle_premise.handle_first_sex_in_today(
        character_id
    ):
        first_sex_adjust += 3
    if handle_premise.handle_first_a_sex_in_today(character_id):
        first_sex_adjust += 3
    if handle_premise.handle_first_u_sex_in_today(character_id):
        first_sex_adjust += 10
    if handle_premise.handle_first_w_sex_in_today(character_id):
        first_sex_adjust += 5
    if first_sex_adjust > 0:
        base_chara_state_common_settle(
            character_id,
            add_time=true_add_time * 5,
            state_id=17,
            base_value=0,
            ability_level=now_char_ability[15],
            extra_adjust=first_sex_adjust,
            tenths_add=False,
        )
    # 被监禁状态下持续增长屈服和恐怖
    if handle_premise.handle_imprisonment_1(character_id):
        base_chara_state_common_settle(
            character_id,
            add_time=true_add_time * 5,
            state_id=15,
            base_value=0,
            ability_level=now_char_ability[14],
            extra_adjust=3,
            tenths_add=False,
        )
        base_chara_state_common_settle(
            character_id,
            add_time=true_add_time * 5,
            state_id=18,
            base_value=0,
            ability_level=now_char_ability[17],
            extra_adjust=3,
            tenths_add=False,
        )
    # 浴室中增加润滑
    if handle_premise.handle_h_in_bathroom(character_id):
        base_chara_state_common_settle(
            character_id,
            add_time=true_add_time * 10,
            state_id=8,
            base_value=0,
            tenths_add=False,
        )
