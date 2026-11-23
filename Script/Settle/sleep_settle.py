"""玩家睡觉时的刷新、角色状态结算为珠、自动存档、理智值自然成长与临时最大精液量刷新"""

import random
from types import FunctionType
from Script.Core import game_path_config, get_text, io_init, num
from Script.Design import (
    handle_premise,
    attr_calculation,
    handle_talent,
    handle_ability,
)
from Script.System.Pregnancy_System import pregnancy_handle
from Script.UI.Moudle import draw
from Script.Config import game_config, normal_config
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.domains import (
    abilities,
    action_info,
    activity,
    first_record,
    flags,
)
from Script.Modules.domains import h_meters, h_state, needs, plan
from Script.Modules.domains import player_ability, roster, status, relations
from Script.Modules.domains import identity

game_path = game_path_config.game_path
_: FunctionType = get_text._
""" 翻译api """
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1


def update_sleep() -> None:
    """
    玩家睡觉时的刷新\n
    Keyword arguments:
    无\n
    Return arguments:
    无
    """

    now_draw = draw.NormalDraw()
    now_draw.width = window_width
    now_draw.text = _("\n博士入睡，开始结算各种数据\n")
    now_draw.draw()
    io_init.flush()
    id_list = roster.active()
    id_list.add(0)

    # 角色刷新
    for character_id in id_list:
        character_data: identity.Identity = identity.of(character_id)
        # 结算数值为珠
        settle_character_juel(character_id)
        # 玩家结算
        if character_id == 0:
            sanity_point_grow()  # 玩家理智成长
            h_meters.set(0, eja=0)  # 清零射精槽
            action_info.set(character_data.cid, "day_first_shoot_semen", True)
            assistant_id = relations.assistant_character_id(character_id)
            # 对玩家助理结算
            if assistant_id > 0:
                # 如果助理的早安问候已开启，则清零助理早安问候
                if handle_premise.handle_assistant_morning_salutation_on(
                    assistant_id
                ):
                    flags.set(assistant_id, morning_salutation=0)
                # 如果此时助理在睡眠中，则清零助理晚安问候
                if handle_premise.handle_assistant_night_salutation_on(
                    assistant_id
                ) and handle_premise.handle_action_sleep(assistant_id):
                    flags.set(assistant_id, night_salutation=0)
                # 如果助理的跟随服务已开启，且没有在跟随，则让助理跟随
                if flags.get(
                    assistant_id, "is_follow"
                ) != 1 and handle_premise.handle_assistant_follow_1(
                    assistant_id
                ):
                    flags.set(assistant_id, is_follow=1)
                achievement_service.settle_and_notify(_("助理"))
            # 体外无壳卵：长时间睡眠期间到期的卵进行受精判定（先于各NPC的破壳判定）
            from Script.System.Pregnancy_System import soft_egg_handle

            soft_egg_handle.check_soft_eggs_fertilization()
            # 幼女离线、不在 npc_id_got 里，长成学员的检查在这里统一做
            pregnancy_handle.check_all_child_grow_to_loli()
            # 检查是否有可以升级的能力
            if normal_config.system_setting.base_setting[1]:
                handle_ability.gain_ability(character_id)
            line_feed.draw()
        else:
            # 清零并随机重置生气程度
            needs.set(character_id, angry=random.randrange(1, 35))
            # 清零H被撞破的flag
            action_info.set(character_data.cid, "h_interrupt", 0)
            # 重置每天第一次见面
            first_record.set(character_id, day_first_meet=1)
            # 检查并处理受精怀孕部分
            pregnancy_handle.check_all_pregnancy(character_id)
            # 检查是否有可以获得的素质
            handle_talent.gain_talent(character_id, now_gain_type=3)
            # 检查是否有可以升级的能力
            if normal_config.system_setting.base_setting[2]:
                handle_ability.gain_ability(character_id)
            # 清零H状态
            h_state.reset(character_id)
            # 清零睡奸中醒来状态
            flags.set(character_data.cid, sleep_h_awake=False)

    # 非角色部分
    plan.set_sleep_save(True)


def settle_character_juel(character_id: int) -> int:
    """
    校验角色状态并结算为珠
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    bool -- 本次update时间切片内活动是否已完成
    """
    juel = abilities.juel(character_id)
    character_data: identity.Identity = identity.of(character_id)
    for status_id in game_config.config_character_state:
        if character_data.sex == 0:
            if status_id in {2, 4, 7, 8}:
                continue
        elif character_data.sex == 1:
            if status_id == 3:
                continue
        status_value: num.Num = 0
        # 获得状态值并清零
        if status_id in status.of(character_id):
            status_value = status.of(character_id)[status_id]
            status.set(character_id, status_id, 0)
            # print("status_value :",status_value)
        # 只要状态值不为0就结算为对应珠
        if status_value != 0:
            add_juel = attr_calculation.get_juel(status_value)
            juel.setdefault(status_id, 0)
            if status_id in [17, 18, 19]:
                juel[status_id] += add_juel // 4
                juel[20] += add_juel // 2
            else:
                juel[status_id] += add_juel
            # juel_text = game_config.config_juel[status_id].name
            # print("宝珠名：",juel_text,"。增加了 :",add_juel)
    # 当反感珠大于0时，计算和其他珠的抵消
    if juel[20] > 0:
        draw_text = _("\n当前共{0}反发珠，抵消了：").format(juel[20])
        for i in [15, 10, 11, 12, 13]:
            # 1好意抵消2反发
            if juel[i] > 0:
                juel_down = min(juel[20], juel[i] * 2)
                juel[20] -= juel_down
                juel[i] -= juel_down // 2
                draw_text += _(" {0}个{1} ").format(
                    juel_down // 2, game_config.config_juel[i].name
                )
        draw_text += _("，剩余{0}个反发珠\n").format(juel[20])
        now_draw = draw.NormalDraw()
        now_draw.text = draw_text
        # now_draw.draw()
    return 1


def update_save() -> None:
    """
    自动存档\n
    Keyword arguments:
    无\n
    Return arguments:
    无
    """
    from Script.Core import save_handle

    now_draw = draw.WaitDraw()
    now_draw.width = window_width
    now_draw.text = _("\n全部结算完毕，开始自动保存\n")
    # 播放一条提示信息
    info_list = []
    for i in game_config.config_tip_data:
        info_list.append(i)
    info_id = random.choice(info_list)
    info_text = game_config.config_tip_data[info_id].info
    now_draw.text += _(
        "\n请博士在保存时阅读今日的小贴士：\n\n  {0}\n\n\n"
    ).format(info_text)
    now_draw.draw()
    save_handle.establish_save("auto")


def sanity_point_grow() -> None:
    """
    玩家理智值的自然成长\n
    Keyword arguments:
    无
    """
    character_data: identity.Identity = identity.of(0)
    today_cost = player_ability.get(0, "today_sanity_point_cost")
    player_ability.set(0, today_sanity_point_cost=0)
    # 消耗超过90时进行成长
    if today_cost >= 50 and needs.of(character_data.cid)["sanity_max"] < 9999:
        # 成长值为消耗值的1/50，四舍五入取整
        grow_value = round(today_cost / 50)
        needs.add(character_data.cid, "sanity_max", grow_value)
        needs.set(
            character_data.cid,
            sanity_max=min(needs.of(character_data.cid)["sanity_max"], 9999),
        )
        # 绘制说明信息
        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = _(
            "\n在刻苦的锻炼下，博士理智最大值成长了{0}点\n"
        ).format(grow_value)
        now_draw.draw()


def refresh_temp_semen_max() -> None:
    """
    刷新临时最大精液量\n
    """
    talent = abilities.talent(0)
    meters = h_meters.of(0)
    now_semen = num.whole(meters["semen"])
    # 需要睡眠时长至少大于等于6h
    if now_semen and activity.behavior(0).duration >= 360:
        # 最大额外精液量为正常上限的4倍
        limit = meters["semen_max"] * 4
        new_extra = min(meters["extra_semen"] + now_semen // 2, limit)
        h_meters.set(0, extra_semen=new_extra)
        # 获得浓厚精液
        talent[33] = 1 if new_extra >= limit else 0
        # 绘制说明信息
        now_draw = draw.NormalDraw()
        now_draw.width = window_width
        draw_text = _(
            "\n在充足的睡眠下，今日未消耗的 {0}ml 精液转化为了 {1}ml 次日额外精液"
        ).format(now_semen, now_semen // 2)
        if new_extra >= limit:
            draw_text += _("，额外精液量已达上限，并获得了为期一天的[浓厚精液]")
        draw_text += "\n"
        now_draw.text = draw_text
        now_draw.draw()
