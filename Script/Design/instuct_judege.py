"""
指令实行值：按角色与目标角色的属性计算总实行值，并同步角色的行动开始时间
"""

import datetime
from types import FunctionType
from Script.Core import cache_control, flow_handle, game_type, get_text, num
from Script.Core import text_handle
from Script.Design import attr_calculation, handle_ability, handle_premise
from Script.Design import handle_talent, map_handle
from Script.Config import game_config, normal_config
from Script.UI.Moudle import draw
from Script.Modules.domains import abilities, action_info, entertainment, flags
from Script.Modules.domains import needs, player_ability

cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def init_character_behavior_start_time(
    character_id: int, now_time: datetime.datetime
) -> None:
    """
    将角色的行动开始时间同步为指定时间
    Keyword arguments:
    character_id -- 角色id
    now_time -- 指定时间
    """
    character_data = cache.character_data[character_id]
    # 用 replace 截到整分钟，保留游戏时间的类型
    start_time = now_time.replace(second=0, microsecond=0)
    character_data.behavior.start_time = start_time


def calculation_instuct_judege(
    character_id: int,
    target_character_id: int,
    instruct_name: str,
    not_draw_flag: bool = False,
    settle_hypnosis: bool = True,
) -> list[float]:
    """
    根据角色和目标角色的各属性来计算总实行值\n
    Keyword arguments:\n
    character_id -- 角色id\n
    target_character_id -- 目标角色id\n
    instruct_name -- 指令名字\n
    not_draw_flag -- 是否不输出文本\n
    settle_hypnosis -- 是否结算催眠补正的代价，默认结算：扣理智、累加今日消耗，理智不足时解除目标的催眠。\n
                       传 False 时补正照算（理智够就加补正），但不写任何数据，供前提、门槛、
                       名单这类只判不做的调用方用（Plan 31 §3.3）\n
    Return arguments:\n
    int -- 1成功,0失败\n
    int -- 实行值\n
    float -- 实行值与目标值的比值\n
    """
    from Script.System.Sex_System import drunk_sex_common

    ability = abilities.ability(target_character_id)
    talent = abilities.talent(target_character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    target_data: game_type.Character = cache.character_data[target_character_id]

    # 对玩家为目标的指令是必定成功的
    if target_character_id == 0:
        return [1, 1, 1.0]

    # 匹配到能力的id与能力等级对应的前提#
    judge_data = next(
        now_judge
        for now_judge in game_config.config_instruct_judge_data.values()
        if now_judge.instruct_name == instruct_name
    )
    judge_data_type = judge_data.need_type
    judge_data_value = judge_data.value

    calculation_text = ""
    if judge_data_type == "D":
        calculation_text += (
            _("需要基础实行值至少为") + str(judge_data_value) + "\n"
        )
    elif judge_data_type == "S":
        calculation_text += (
            _("需要性爱实行值至少为") + str(judge_data_value) + "\n"
        )
    calculation_text += _("当前值为：")

    judge = 0

    # 好感判定#
    __, judge_favorability = attr_calculation.get_favorability_level(
        target_data.favorability[0]
    )
    calculation_text += _("好感修正(") + str(judge_favorability) + ")"
    judge += judge_favorability

    # 信赖判定#
    __, judge_trust = attr_calculation.get_trust_level(target_data.trust)
    judge += judge_trust
    calculation_text += _("+信赖修正(") + str(judge_trust) + ")"

    # 状态修正
    # 欲情和快乐为低正修正，恭顺和屈服为高正修正，羞耻和抑郁低小负修正，苦痛和恐怖和反感为高负修正
    add_status_level_sum_s = attr_calculation.get_status_level(
        num.whole(target_data.status_data[12])
    ) + attr_calculation.get_status_level(
        num.whole(target_data.status_data[13])
    )
    add_status_level_sum_l = attr_calculation.get_status_level(
        num.whole(target_data.status_data[10])
    ) + attr_calculation.get_status_level(
        num.whole(target_data.status_data[15])
    )
    down_status_level_sum_s = attr_calculation.get_status_level(
        num.whole(target_data.status_data[16])
    ) + attr_calculation.get_status_level(
        num.whole(target_data.status_data[19])
    )
    down_status_level_sum_l = (
        attr_calculation.get_status_level(
            num.whole(target_data.status_data[17])
        )
        + attr_calculation.get_status_level(
            num.whole(target_data.status_data[18])
        )
        + attr_calculation.get_status_level(
            num.whole(target_data.status_data[20])
        )
    )
    judge_status = (
        add_status_level_sum_s * 5
        + add_status_level_sum_l * 10
        - down_status_level_sum_s * 5
        - down_status_level_sum_l * 10
    )
    judge += judge_status
    if judge_status:
        calculation_text += _("+状态修正(") + str(judge_status) + ")"

    # 能力修正，亲密(32)和欲望(33)修正#
    judge_ability = ability[32] * 10 + ability[33] * 5
    judge += judge_ability
    if judge_ability:
        calculation_text += _("+能力修正(") + str(judge_ability) + ")"

    # 刻印修正，快乐(13)、屈服(14)、苦痛(15)、时停(16)、恐怖(17)、反发(18)、无觉(19)修正#
    judge_mark = (
        ability[13] * 50
        + ability[14] * 50
        + ability[15] * 10
        + ability[19] * 25
    )
    judge_mark -= min(ability[17] - ability[16], 0) * 50 + ability[18] * 100
    judge += judge_mark
    if judge_mark:
        calculation_text += _("+全刻印总修正(") + str(judge_mark) + ")"

    # 心情修正，好心情+10，坏心情-10，愤怒-30
    angry = needs.of(target_character_id)["angry"]
    judge_angry = attr_calculation.get_angry_level(angry) * 20
    judge += judge_angry
    if judge_angry:
        calculation_text += _("+心情修正(") + str(judge_angry) + ")"

    # 陷落素质判定，第一阶段~第四阶段分别为30,50,80,100#
    judge_fall = (
        talent[201] * 30
        + talent[202] * 50
        + talent[203] * 80
        + talent[204] * 100
        + talent[211] * 30
        + talent[212] * 50
        + talent[213] * 80
        + talent[214] * 100
    )
    judge += judge_fall
    if judge_fall:
        calculation_text += _("+陷落修正(") + str(judge_fall) + ")"
    # 讨厌男性修正#
    judge_hate = talent[227] * 30
    judge -= judge_hate
    if judge_hate:
        calculation_text += _("+讨厌男性(-") + str(judge_hate) + ")"
    # 难以越过的底线修正#
    judge_hardlove = talent[224] * 100
    judge -= judge_hardlove
    if judge_hardlove:
        calculation_text += _("+难以越过的底线(-") + str(judge_hardlove) + ")"
    # 被对方持有把柄修正
    judge_weakness = talent[401] * 100
    judge -= judge_weakness
    if judge_weakness:
        calculation_text += _("+被对方持有把柄(-") + str(judge_weakness) + ")"
    # 持有对方把柄修正
    judge_weakness = talent[402] * 100
    judge += judge_weakness
    if judge_weakness:
        calculation_text += _("+持有对方把柄(+") + str(judge_weakness) + ")"
    # 女儿修正
    judge_daughter = talent[451] * 100
    judge += judge_daughter
    if judge_daughter:
        calculation_text += _("+女儿(+") + str(judge_daughter) + ")"

    # 醉酒修正
    drunk_level, _drunk_name = drunk_sex_common.get_drunk_level(target_data.cid)
    if drunk_level:
        # 醉酒等级 1~3 的修正值
        judge_drunk = {1: 20, 2: 100, 3: 500}[drunk_level]
        judge += judge_drunk
        calculation_text += _("+醉酒修正(") + str(judge_drunk) + ")"
    # 饮酒修正
    if _("饮酒") in instruct_name:
        # 工作时间内饮酒修正
        if handle_premise.handle_have_work(
            target_data.cid
        ) and handle_premise.handle_to_work_time_or_work_time(target_data.cid):
            judge -= 50
            calculation_text += _("+工作时间饮酒(-50)")
        # 未成年饮酒
        if handle_premise.handle_self_is_child(target_data.cid):
            judge -= 100
            calculation_text += _("+未成年饮酒(-100)")
        # 酒量好饮酒
        if handle_premise.handle_self_have_good_alcohol_tolerance(
            target_data.cid
        ):
            judge += 30
            calculation_text += _("+酒量好(+30)")
        # 酒量差饮酒
        if handle_premise.handle_self_have_bad_alcohol_tolerance(
            target_data.cid
        ):
            judge -= 30
            calculation_text += _("+酒量差(-30)")
        # 千杯不醉饮酒
        if handle_premise.handle_self_have_never_drunk(target_data.cid):
            judge += 100
            calculation_text += _("+千杯不醉(+100)")
        # 一杯就倒饮酒
        if handle_premise.handle_self_have_easily_drunk(target_data.cid):
            judge -= 100
            calculation_text += _("+一杯就倒(-100)")

    # 仅性爱指令
    if judge_data_type == "S":
        # 淫乱相关属性修正#
        if talent[40]:
            judge += 50
            calculation_text += _("+淫乱(+50)")
        # 性好奇
        if talent[220]:
            judge += 30
            calculation_text += _("+性好奇(+30)")
        # 性冷漠
        if talent[221]:
            judge -= 30
            calculation_text += _("+性冷漠(-30)")
        # 性无知
        if talent[222]:
            judge += 100
            calculation_text += _("+性无知(+100)")
        # 爱情旅馆修正
        if target_data.h_state.h_in_love_hotel:
            if entertainment.hotel_room() == 1:
                judge += 25
                calculation_text += _("+标间(+25)")
            elif entertainment.hotel_room() == 2:
                judge += 50
                calculation_text += _("+情趣主题房(+50)")
            elif entertainment.hotel_room() == 3:
                judge += 100
                calculation_text += _("+顶级套房(+100)")
        # 找博士逆推自慰修正
        if flags.get(target_character_id, "npc_masturebate_for_player"):
            judge += 50
            calculation_text += _("+找博士逆推(+50)")

    # 激素系能力修正#
    if player_ability.get(character_id, "hormone"):
        judge_information = (
            abilities.talent(character_id)[304] * 25
            + abilities.talent(character_id)[305] * 50
            + abilities.talent(character_id)[306] * 100
        )
        judge += judge_information
        talent_id = handle_talent.have_hormone_talent()
        talent_name = game_config.config_talent[talent_id].name
        if judge_information:
            calculation_text += f"+{talent_name}({str(judge_information)})"

    # 访客不判定的部分
    if judge_data_type != "V":

        # 当前场景有人修正，需要该对象角色有意识
        scene_path_str = map_handle.get_map_system_path_str_for_list(
            character_data.position
        )
        scene_data = cache.scene_data[scene_path_str]
        if len(
            scene_data.character_list
        ) > 2 and handle_premise.handle_t_normal_5_6(character_id):
            other_chara_count = len(scene_data.character_list) - 2
            if instruct_name in {_("群交"), _("隐奸")}:
                judge_other_people = 60 + 60 * other_chara_count
            elif judge_data_type == "S":
                judge_other_people = 40 + 40 * other_chara_count
            else:
                judge_other_people = 25 + 25 * other_chara_count
            # 露出修正
            adjust = handle_ability.get_ability_adjust(ability[34])
            judge_other_people = int(judge_other_people * (adjust - 1.6))
            judge += judge_other_people
            calculation_text += (
                _("+有别人在时的露出修正(")
                + text_handle.number_to_symbol_string(judge_other_people)
                + ")"
            )

        # 助理助攻修正
        if (
            character_data.assistant_character_id != target_character_id
            and character_data.assistant_character_id
            in scene_data.character_list
        ):
            assistant_character_data = cache.character_data[
                character_data.assistant_character_id
            ]
            if assistant_character_data.assistant_services[8]:
                judge += 50
                calculation_text += _("+助理助攻(+50)")

        # 今天H被打断了修正
        if judge_data_type == "S":
            judge_h_interrupt = (
                action_info.get(target_character_id, "h_interrupt") * 50
            )
            judge -= judge_h_interrupt
            if judge_h_interrupt:
                calculation_text += (
                    _("+今天H被打断过(-") + str(judge_h_interrupt) + ")"
                )

        # 监禁模式修正
        if handle_premise.handle_imprisonment_1(target_character_id):
            judge += 9999
            calculation_text += _("+监禁中(+9999)")

        # 睡眠修正
        if handle_premise.handle_unconscious_flag_1(target_character_id):
            judge += 9999
            calculation_text += _("+睡眠(+9999)")

        # 时停修正
        if handle_premise.handle_unconscious_flag_3(target_character_id):
            judge += 9999
            calculation_text += _("+时停(+9999)")

    # 姿势修正
    if instruct_name in {
        _("性交"),
        _("A性交"),
        _("U性交"),
        _("W性交"),
    } and handle_premise.handle_dr_have_sex_position(character_id):
        now_position = character_data.h_state.current_sex_position
        # 如果当前姿势是自己喜欢的体位，则增加额外快感
        favorite_position_id = handle_talent.settle_favorite_sex_position(
            target_character_id
        )
        if now_position == favorite_position_id:
            judge += 30
            calculation_text += _("+喜欢的体位(+30)")

    # 处女修正
    if (
        instruct_name == _("性交")
        and handle_premise.handle_have_virgin(target_character_id)
        and handle_premise.handle_self_sexual_ignorance_0(target_character_id)
    ):
        judge -= 250
        calculation_text += _("+处女(-250)")

    # A处女修正
    if (
        instruct_name == _("A性交")
        and talent[1]
        and handle_premise.handle_self_sexual_ignorance_0(target_character_id)
    ):
        judge -= 350
        calculation_text += _("+Ａ处女(-350)")

    # W处女修正
    if (
        instruct_name == _("W性交")
        and talent[3]
        and handle_premise.handle_self_sexual_ignorance_0(target_character_id)
    ):
        judge -= 400
        calculation_text += _("+Ｗ处女(-400)")

    # U处女修正
    if (
        instruct_name == _("U性交")
        and talent[2]
        and handle_premise.handle_self_sexual_ignorance_0(target_character_id)
    ):
        judge -= 400
        calculation_text += _("+Ｕ处女(-400)")

    # 初吻修正
    if (
        instruct_name == _("亲吻")
        and talent[4]
        and handle_premise.handle_self_sexual_ignorance_0(target_character_id)
    ):
        judge -= 125
        calculation_text += _("+初吻(-125)")

    # 性交的避孕相关修正
    if instruct_name in {_("性交"), _("W性交")}:
        # 妊娠合意、避孕套、避孕中出合意+事前避孕药、性无知，以上可直接通过
        if (
            talent[14]
            or character_data.h_state.body_item[13][1]
            or (talent[13] and target_data.h_state.body_item[11][1])
            or talent[222]
        ):
            pass
        else:
            if handle_premise.handle_reproduction_period_0(target_character_id):
                # 避孕中出合意合意
                if talent[13]:
                    pass
                else:
                    judge -= 10
                    calculation_text += _("+安全期(-10)")
            elif handle_premise.handle_reproduction_period_1(
                target_character_id
            ):
                judge -= 50
                calculation_text += _("+普通期(-50)")
            elif handle_premise.handle_reproduction_period_2(
                target_character_id
            ):
                judge -= 200
                calculation_text += _("+危险期(-200)")
            elif handle_premise.handle_reproduction_period_3(
                target_character_id
            ):
                judge -= 300
                calculation_text += _("+排卵期(-300)")

    # 催眠系能力的最后补正
    judge_hypnosis = 0  # 初始为零，方便其他修正判断是否进行了催眠
    # 需要在催眠状态中，性爱判定
    if (
        flags.get(target_character_id, "unconscious_h") in {4, 5, 6, 7}
        and judge_data_type == "S"
    ):
        # 完全催眠直接通过
        if handle_premise.handle_self_has_been_complete_hypnosis(
            target_character_id
        ):
            judge_hypnosis = 9999
            judge += judge_hypnosis
            calculation_text += _("+完全催眠(+9999)")
        # 否则仅在实行值不足时生效，需要消耗理智
        elif judge < judge_data_value:
            # 性骚扰级别需要至少50%催眠深度，性行为需要2级催眠和至少100%催眠深度
            if (
                (_("骚扰") in instruct_name or _("亲吻") in instruct_name)
                and handle_premise.handle_self_has_been_primary_hypnosis(
                    target_character_id
                )
            ) or (
                handle_premise.handle_intermediate_hypnosis(character_id)
                and handle_premise.handle_self_has_been_deep_hypnosis(
                    target_character_id
                )
            ):
                # 实行值不够的差值为
                unenough = judge_data_value - judge
                # 催眠基础补正为100，再不足的部分用理智折算为实行值
                if unenough <= 100:
                    judge_hypnosis = 100
                    sanity_point_cost = 5
                else:
                    # 刚好补齐需要的差值
                    judge_hypnosis = unenough
                    # 深层催眠下，1理智折算为20实行值
                    if handle_premise.handle_self_has_been_deep_hypnosis(
                        target_character_id
                    ):
                        sanity_point_cost = round(unenough / 20)
                    # 否则1理智折算为10实行值
                    else:
                        sanity_point_cost = round(unenough / 10)
                # 最后的总结算
                # settle_hypnosis 为假时只判不扣（Plan 31 §3.3）：前提、面板、名单每刷新一次就求值一次，
                #    在这里扣理智或解除催眠，同一个判定会越判越变，打开一次面板就改掉了存档数据
                if sanity_point_cost <= needs.of(character_id)["sanity"]:
                    judge += judge_hypnosis
                    if settle_hypnosis:
                        calculation_text += _("+催眠(+{0},消耗{1}理智)").format(
                            judge_hypnosis, sanity_point_cost
                        )
                        needs.add(character_id, "sanity", -sanity_point_cost)
                        player_ability.add_sanity_cost(
                            character_id, sanity_point_cost
                        )
                    else:
                        calculation_text += _("+催眠(+{0},需{1}理智)").format(
                            judge_hypnosis, sanity_point_cost
                        )
                elif settle_hypnosis:
                    calculation_text += _("+催眠(+0,理智不足,催眠解除)")
                    flags.set(target_character_id, unconscious_h=0)
                else:
                    calculation_text += _("+催眠(+0,理智不足)")

    # debug模式修正
    if cache.debug_mode:
        judge += 99999
        calculation_text += _("+debug模式(+99999)")

    # 是否通过
    if judge >= judge_data_value:
        final_judge = 1
    else:
        final_judge = 0
    judge_rate = judge / judge_data_value

    # 是否进行相关信息的绘制与结算
    if not not_draw_flag:

        # 问过玩家的戴套提示只显示一次：选择时 ask_judge 问过，开始时在这里记下
        if _asks_condom(character_data, target_data, instruct_name):
            target_data.h_state.condom_info_show_flag = False
        condom_flag = bool(character_data.h_state.body_item[13][1])

        # 正常直接判定，并输出文本
        if judge_data_type != "V":
            calculation_text += " = " + str(judge) + "\n"
            now_draw = draw.WaitDraw()
            now_draw.text = calculation_text
            now_draw.draw()

        # 合意获得的结算，大前提是1.5倍实行值、有意识、非监禁
        if (
            judge_rate >= 1.5
            and handle_premise.handle_unconscious_flag_0(target_character_id)
            and handle_premise.handle_imprisonment_0(target_character_id)
        ):
            agree_draw = draw.WaitDraw()
            draw_text = ""
            if instruct_name == _("亲吻") and talent[11] == 0:
                talent[11] = 1
                draw_text += _("\n 获得了{0}的【亲吻合意】\n").format(
                    target_data.name
                )
            if instruct_name == _("性交") and talent[12] == 0:
                talent[12] = 1
                draw_text += _("\n 获得了{0}的【本番合意】\n").format(
                    target_data.name
                )
            if instruct_name == _("A性交") and talent[15] == 0:
                talent[15] = 1
                draw_text += _("\n 获得了{0}的【Ａ性交合意】\n").format(
                    target_data.name
                )
            if instruct_name == _("U性交") and talent[16] == 0:
                talent[16] = 1
                draw_text += _("\n 获得了{0}的【Ｕ性交合意】\n").format(
                    target_data.name
                )
            # 避孕相关合意
            # 避孕中出合意需要在非处女、不带套、安全期时，通过判定才可获得
            if (
                handle_premise.handle_no_virgin(target_character_id)
                and (instruct_name == _("性交") or instruct_name == _("W性交"))
                and talent[13] == 0
                and not condom_flag
                and handle_premise.handle_reproduction_period_0(
                    target_character_id
                )
            ):
                talent[13] = 1
                draw_text += _("\n 获得了{0}的【避孕中出合意】\n").format(
                    target_data.name
                )
            # 妊娠合意需要在非处女、不带套、非安全期时，通过判定才可获得
            if (
                handle_premise.handle_no_virgin(target_character_id)
                and (instruct_name == _("性交") or instruct_name == _("W性交"))
                and talent[14] == 0
                and not condom_flag
                and (
                    handle_premise.handle_reproduction_period_2(
                        target_character_id
                    )
                    or handle_premise.handle_reproduction_period_3(
                        target_character_id
                    )
                )
            ):
                talent[14] = 1
                draw_text += _("\n 获得了{0}的【妊娠合意】\n").format(
                    target_data.name
                )
            if len(draw_text):
                agree_draw.text = draw_text
                agree_draw.draw()

    # 返回判定结果
    return [final_judge, judge, judge_rate]


def _asks_condom(
    character_data: game_type.Character,
    target_data: game_type.Character,
    instruct_name: str,
) -> bool:
    """
    性交时是否要问玩家戴不戴套：玩家没戴套，对方还没提示过
    Keyword arguments:
    character_data -- 玩家
    target_data -- 交互对象
    instruct_name -- 指令名字
    Return arguments:
    bool -- 要问时为真
    """
    return (
        instruct_name in {_("性交"), _("W性交")}
        and not character_data.h_state.body_item[13][1]
        and bool(target_data.h_state.condom_info_show_flag)
    )


def ask_text(
    character_id: int,
    target_character_id: int,
    instruct_name: str,
    judge_rate: float,
) -> str:
    """
    指令要先问玩家的话：夺走对方的初吻或处女，或不戴套；不用问时为空。只读数据
    Keyword arguments:
    character_id -- 角色id
    target_character_id -- 目标角色id
    instruct_name -- 指令名字
    judge_rate -- 实行值与目标值的比值，决定对方的态度
    Return arguments:
    str -- 要问的话
    """
    talent = abilities.talent(target_character_id)
    character_data: game_type.Character = cache.character_data[character_id]
    target_data: game_type.Character = cache.character_data[target_character_id]
    text = ""
    if instruct_name == _("亲吻") and talent[4]:
        text += _("\n\n 是否要夺走{0}的初吻？").format(target_data.name)
    if instruct_name == _("口交") and talent[4]:
        text += _("\n\n 是否要用阴茎夺走{0}的初吻？").format(target_data.name)
    elif instruct_name == _("性交") and talent[0]:
        text += _("\n\n 是否要夺走{0}的阴道处女？").format(target_data.name)
    elif instruct_name == _("A性交") and talent[1]:
        text += _("\n\n 是否要夺走{0}的肛门处女？").format(target_data.name)
    elif instruct_name == _("U性交") and talent[2]:
        text += _("\n\n 是否要夺走{0}的尿道处女？").format(target_data.name)
    elif instruct_name == _("W性交") and talent[3]:
        text += _("\n\n 是否要夺走{0}的子宫处女？").format(target_data.name)
    if _asks_condom(character_data, target_data, instruct_name):
        # 无意识
        if flags.get(target_character_id, "unconscious_h"):
            text += _("当前正在对{0}无意识奸，是否不戴套？\n").format(
                target_data.name
            )
        # 妊娠合意
        elif talent[14]:
            text += _(
                "{0}已经做好了随时都可以怀孕的准备，是否不戴套？\n"
            ).format(target_data.name)
        # 避孕中出合意+事前避孕药
        elif talent[13] and target_data.h_state.body_item[11][1]:
            text += _(
                "{0}已经吃过事前避孕药了，所以内射也不会怀孕，是否不戴套？\n"
            ).format(target_data.name)
        # 性无知
        elif talent[222]:
            text += _("{0}似乎对性和避孕都一无所知，是否不戴套？\n").format(
                target_data.name
            )
        elif judge_rate < 0.5:
            text += _(
                "{0}坚决地要求你必须戴上避孕套，是否坚持不带套？\n"
            ).format(target_data.name)
        elif judge_rate < 1:
            text += _("{0}希望你戴上避孕套，是否坚持不带套？\n").format(
                target_data.name
            )
        else:
            text += _(
                "{0}提醒你还没有戴避孕套，但也表示可以不戴就这样继续，是否不带套？\n"
            ).format(target_data.name)
    if not text:
        return ""
    # 判断态度
    text += _(" (对方的态度：")
    if judge_rate < 0.5:
        text += _("拒绝)\n")
    elif judge_rate < 1:
        text += _("犹豫)\n")
    else:
        text += _("接受)\n")
    return text


def ask_judge(
    character_id: int, target_character_id: int, instruct_name: str
) -> bool:
    """
    选择时先问玩家（ask_text 不为空时画出来，[确定]或[返回]）。只判不写数据，判定与代价在行动开始时
    Keyword arguments:
    character_id -- 角色id
    target_character_id -- 目标角色id
    instruct_name -- 指令名字
    Return arguments:
    bool -- 玩家确定或不用问时为真，[返回]时为假
    """
    if target_character_id == 0:
        return True
    judge_rate = calculation_instuct_judege(
        character_id,
        target_character_id,
        instruct_name,
        not_draw_flag=True,
        settle_hypnosis=False,
    )[2]
    text = ask_text(
        character_id, target_character_id, instruct_name, judge_rate
    )
    if not text:
        return True
    ask_draw = draw.WaitDraw()
    ask_draw.text = text
    ask_draw.draw()
    line_feed.draw()
    line_feed.draw()
    yes_draw = draw.CenterButton(_("[确定]"), _("确定"), int(window_width / 2))
    yes_draw.draw()
    back_draw = draw.CenterButton(_("[返回]"), _("返回"), int(window_width / 2))
    back_draw.draw()
    line_feed.draw()
    answer = flow_handle.askfor_all(
        [yes_draw.return_text, back_draw.return_text]
    )
    return answer == yes_draw.return_text
