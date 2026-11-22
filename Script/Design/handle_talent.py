"""素质的获得、查询与结算"""

from types import FunctionType
from Script.Design import attr_calculation, handle_premise
from Script.System.First_Record_System import first_record_handle
from Script.Core import cache_control, game_type, get_text, num
from Script.Config import game_config, normal_config
from Script.UI.Moudle import draw
from Script.UI.Panel import achievement_panel
from Script.Design import game_time
from Script.Modules.domains import (
    abilities,
    activity,
    dirty,
    first_record,
    hypnosis,
)
from Script.Modules.domains import pregnancy
from Script.Modules.domains import identity

_: FunctionType = get_text._
""" 翻译api """
cache: game_type.Cache = cache_control.cache
""" 游戏缓存数据 """

line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width = normal_config.config_normal.text_width
""" 屏幕宽度 """


def record_fall_talent_time(character_id: int, talent_id: int) -> None:
    """
    记录获得陷落素质的时间与地点\n
    Keyword arguments:
    character_id -- 角色id\n
    talent_id -- 素质id，仅陷落素质(201~204,211~214)会被记录
    """
    if talent_id not in {201, 202, 203, 204, 211, 212, 213, 214}:
        return
    with first_record.editing(character_id) as fr:
        if talent_id not in fr.fall_talent_time_dict:
            fr.fall_talent_time_dict[talent_id] = [
                game_time.now(),
                list(activity.position(character_id)),
            ]


def gain_talent(
    character_id: int, now_gain_type: int, traget_talent_id: int = 0
) -> None:
    """
    结算可以获得的素质\n
    Keyword arguments:
    character_id -- 角色id\n
    now_gain_type -- 素质获得类型(0随时自动，1手动，2指令绑定，3睡觉自动)\n
    """
    from Script.Design import second_behavior

    talent = abilities.talent(character_id)
    character_data: identity.Identity = identity.of(character_id)
    gain_talent_flag = False
    # 遍历全素质获得
    for gain_talent_cid in game_config.config_talent_gain:
        gain_talent_data = game_config.config_talent_gain[gain_talent_cid]
        gain_type = gain_talent_data.gain_type
        talent_id = gain_talent_data.talent_id

        # 大前提是NPC没有该素质
        if talent[talent_id]:
            continue

        # 手动结算的话跳过判断直接获得对应素质
        judge = 0
        if now_gain_type == 1 and traget_talent_id == talent_id:
            judge = 1
        # 需要为对应的结算时机
        elif gain_type != 1 and gain_type == now_gain_type:

            # 以&为分割判定是否有多个需求
            if "&" not in gain_talent_data.gain_need:
                need_list = []
                need_list.append(gain_talent_data.gain_need)
            else:
                need_list = gain_talent_data.gain_need.split("&")
            judge, __ = attr_calculation.judge_require(need_list, character_id)

        # 如果符合获得条件，则获得该素质
        if judge:
            talent[talent_id] = 1
            # 记录陷落素质的获得时间与地点
            record_fall_talent_time(character_id, talent_id)
            gain_talent_flag = True
            talent_name = game_config.config_talent[talent_id].name

            # 触发对应的二段行为结算
            if gain_talent_data.second_behavior_id:
                second_behavior_id = gain_talent_data.second_behavior_id
                second_behavior.character_get_second_behavior(
                    character_id, second_behavior_id
                )

            # 判断是否需要进行替代旧素质
            if gain_talent_data.replace_talent_id:
                old_talent_id = gain_talent_data.replace_talent_id
                talent[old_talent_id] = 0

            now_draw_succed = draw.WaitDraw()
            now_draw_succed.text = _("\n{0}获得了【{1}】\n").format(
                character_data.name, talent_name
            )
            now_draw_succed.draw()
    # print(f"debug {character_data.name}的睡觉结算素质结束，judge = {judge}")

    # 结算陷落素质的成就
    if gain_talent_flag:
        achievement_panel.achievement_flow(_("关系"))

    # 特殊素质获得
    if now_gain_type == 0:
        npc_gain_and_lost_cumflation(character_id)
        npc_gain_semen_drinking_climax_talent(character_id)
        npc_b_talent_change_for_lactation_flag(character_id)
        chara_settle_drink_talent(character_id)
    if now_gain_type == 3:
        settle_favorite_sex_position(character_id)


def have_age_talent(character_id: int) -> int:
    """
    返回年龄素质\n
    """
    for talent_id in [101, 102, 103, 104, 105, 106, 107]:
        if abilities.talent(character_id)[talent_id]:
            return talent_id
    return 0


def have_chest_talent(character_id: int) -> int:
    """
    返回胸部大小素质\n
    """
    for talent_id in [121, 122, 123, 124, 125]:
        if abilities.talent(character_id)[talent_id]:
            return talent_id
    return 0


def have_hip_talent(character_id: int) -> int:
    """
    返回臀部大小素质\n
    """
    for talent_id in [126, 127, 128]:
        if abilities.talent(character_id)[talent_id]:
            return talent_id
    return 0


def have_leg_talent(character_id: int) -> int:
    """
    返回腿部大小素质\n
    """
    for talent_id in [129, 130]:
        if abilities.talent(character_id)[talent_id]:
            return talent_id
    return 0


def have_foot_talent(character_id: int) -> int:
    """
    返回脚部大小素质\n
    """
    for talent_id in [131, 132]:
        if abilities.talent(character_id)[talent_id]:
            return talent_id
    return 0


def have_hypnosis_talent() -> int:
    """
    验证是否有催眠系素质\n
    """
    for talent_id in [331, 332, 333, 334]:
        if abilities.talent(0)[talent_id]:
            return talent_id
    return 0


def have_hormone_talent() -> int:
    """
    验证是否有激素系素质\n
    """
    for talent_id in [306, 305, 304]:
        if abilities.talent(0)[talent_id]:
            return talent_id
    return 0


def have_visual_talent() -> int:
    """
    验证是否有视觉系素质\n
    """
    for talent_id in [309, 308, 307]:
        if abilities.talent(0)[talent_id]:
            return talent_id
    return 0


def have_tactile_talent() -> int:
    """
    验证是否有触觉系素质\n
    """
    for talent_id in [312, 311, 310]:
        if abilities.talent(0)[talent_id]:
            return talent_id
    return 0


def have_fall_talent(character_id: int) -> int:
    """
    验证是否有陷落素质\n
    """
    for talent_id in [201, 202, 203, 204, 211, 212, 213, 214]:
        if abilities.talent(character_id)[talent_id]:
            return talent_id
    return 0


def npc_gain_hypnosis_talent(character_id: int) -> None:
    """
    干员获得被催眠素质\n
    """
    from Script.Design import second_behavior

    character_data = identity.of(character_id)
    hyp_deg = hypnosis.of(character_id)["hypnosis_degree"]
    if hyp_deg < 1:
        return

    for cid in game_config.config_hypnosis_talent_of_npc:
        now_data = game_config.config_hypnosis_talent_of_npc[cid]
        # 如果已经有该素质则跳过
        if abilities.talent(character_id)[now_data.hypnosis_talent_id]:
            continue
        # 如果玩家没有对应的前置素质则跳过
        if not abilities.talent(0)[now_data.need_talent_id]:
            continue

        if hyp_deg >= now_data.hypnosis_degree:
            abilities.talent(character_id)[now_data.hypnosis_talent_id] = 1
            talent_name = game_config.config_talent[
                now_data.hypnosis_talent_id
            ].name
            # 触发对应的二段行为结算
            second_behavior.character_get_second_behavior(
                character_id, now_data.second_behavior_id
            )
            # 替换旧素质
            # if now_data.hypnosis_talent_id > 71:
            #     old_talent_id = now_data.hypnosis_talent_id - 1
            #     character_data.talent[old_talent_id] = 0
            # 绘制获得素质提示
            now_draw_succed = draw.WaitDraw()
            now_draw_succed.text = _(
                "\n○{0}的催眠深度达到{1}%，获得了[{2}]\n"
            ).format(character_data.name, now_data.hypnosis_degree, talent_name)
            now_draw_succed.draw()
            break
    achievement_panel.achievement_flow(_("催眠"))


def npc_gain_and_lost_cumflation(character_id: int) -> None:
    """
    干员获得和失去精液膨腹素质\n
    """
    talent = abilities.talent(character_id)
    character_data = identity.of(character_id)

    # 计算腹部精液总量
    abdomen_all_semen: num.Num = 0
    for i in [6, 7, 8, 15]:
        abdomen_all_semen += dirty.body_semen_amount(character_id, i)

    # 判断是否获得或失去精液膨腹
    now_draw_text = ""
    if abdomen_all_semen >= 6000 and not talent[32]:
        talent[32] = 1
        # 记录特殊履历：第一次获得精液膨腹素质（附记当时的腹部精液总量，失去再获得由dict去重不重写）
        first_record_handle.record_first_special_record(
            character_id, 6, f"{num.shown(abdomen_all_semen)}ml"
        )
        now_draw_text += _("\n○{0}获得了[精液膨腹]\n").format(
            character_data.name
        )
    elif abdomen_all_semen < 6000 and talent[32]:
        talent[32] = 0
        now_draw_text += _("\n○{0}失去了[精液膨腹]\n").format(
            character_data.name
        )

    # 绘制获得素质提示
    if now_draw_text != "" and activity.position(
        character_id
    ) == activity.position(0):
        now_draw_succed = draw.WaitDraw()
        now_draw_succed.text = now_draw_text
        now_draw_succed.draw()


def npc_gain_semen_drinking_climax_talent(character_id: int) -> None:
    """
    干员获得饮精绝顶素质\n
    """
    talent = abilities.talent(character_id)
    character_data = identity.of(character_id)
    if talent[31]:
        return
    if abilities.experience(character_id)[111] >= 50:
        talent[31] = 1
        # 记录特殊履历：获得精爱味觉素质（附记精液来源：H中记当时的H模式，精液食物记食物名称）
        first_record_handle.record_first_special_record(
            character_id,
            8,
            first_record_handle.get_semen_source_text(character_id),
        )
        now_draw_text = _(
            "\n{0}因为经常性地在绝顶的同时被口内射精，因此以后尝到精液的味道就会条件反射性地绝顶了\n"
        ).format(character_data.name)
        now_draw_text += _("{0}获得了[饮精绝顶]\n").format(character_data.name)
        now_draw_succed = draw.WaitDraw()
        now_draw_succed.text = now_draw_text
        now_draw_succed.draw()


def npc_b_talent_change_for_lactation_flag(character_id: int) -> None:
    """
    干员因涨奶而发生的罩杯变化\n
    """
    lactating = abilities.talent(character_id)[27]

    # 奶量超过上限的80%时，罩杯变大
    if (
        lactating
        and handle_premise.handle_milk_ge_80(character_id)
        and not pregnancy.of(character_id).lactation_flag
    ):
        if body_part_talent_update(
            character_id, [121, 122, 123, 124, 125], True, _("胸部")
        ):
            pregnancy.update(character_id, lactation_flag=True)
    # 奶量降到上限的79%及以下时，或失去泌乳素质（停乳药、育儿结束）后，罩杯变小
    elif (
        not lactating or handle_premise.handle_milk_le_79(character_id)
    ) and pregnancy.of(character_id).lactation_flag == 1:
        pregnancy.update(character_id, lactation_flag=False)
        if body_part_talent_update(
            character_id, [121, 122, 123, 124, 125], False, _("胸部")
        ):
            pass


def body_part_talent_update(
    character_id: int, talent_ids: list[int], increase: bool, body_part: str
) -> str:
    """
    根据素质id表来使角色的身体部位素质变大或变小
    Keyword arguments:
    character_id -- 角色id
    talent_ids -- 素质id列表
    increase -- 是否增加
    body_part -- 身体部位
    """
    talent = abilities.talent(character_id)
    now_character_data = identity.of(character_id)
    # 获取当前素质id
    now_talent_id = -1
    for talent_id in talent_ids:
        if talent[talent_id] == 1:
            now_talent_id = talent_id
            break
    if now_talent_id == -1:
        return _("未找到目标素质，无法进行变化\n")
    # 更新素质id
    if increase:
        new_talent_id = min(now_talent_id + 1, talent_ids[-1])
    else:
        new_talent_id = max(now_talent_id - 1, talent_ids[0])
    # 如果已经是极限值，则不进行变化
    if now_talent_id == new_talent_id:
        return ""
    talent[now_talent_id] = 0
    talent[new_talent_id] = 1
    # 输出信息
    change_text = _("变大了") if increase else _("变小了")
    return_text = _(
        "{0}的{1}{2}，现在是【{3}】\n".format(
            now_character_data.name,
            body_part,
            change_text,
            game_config.config_talent[new_talent_id].name,
        )
    )
    return return_text


def settle_favorite_sex_position(character_id: int) -> int:
    """
    结算角色最喜欢的体位素质
    输入: character_id(int) 角色id
    输出: favorite_position_id(int) 最喜欢的体位id
    功能: 自动结算该角色最喜欢的体位行为
    """
    talent = abilities.talent(character_id)
    character_data: identity.Identity = identity.of(character_id)
    favorite_position_id = -1
    # 遍历250~261号素质，检查是否有已存在的喜好
    for pos_id in range(250, 262):
        # 如果已经有喜好则直接返回
        if talent[pos_id]:
            favorite_position_id = pos_id - 249
            return favorite_position_id
    # 遍历141到152号经验，检查最高的经验是否超过了100
    max_exp = 0
    for pos_id in range(141, 153):
        exp = abilities.experience(character_id)[pos_id]
        if exp > max_exp and exp >= 100:
            max_exp = exp
            favorite_position_id = pos_id - 140
    # 如果有喜好则设置该喜好素质
    if favorite_position_id != -1:
        talent_id = favorite_position_id + 249
        talent[talent_id] = 1
        # 绘制获得素质提示
        now_draw_succed = draw.WaitDraw()
        sex_position_name = game_config.config_sex_position_data[
            favorite_position_id
        ].name
        talent_name = game_config.config_talent[talent_id].name
        now_draw_succed.text = _(
            "\n○{0}因为经常使用{1}体位，获得了【{2}】\n"
        ).format(character_data.name, sex_position_name, talent_name)
        now_draw_succed.draw()
    return favorite_position_id


def chara_settle_drink_talent(character_id: int) -> None:
    """
    角色结算酒量相关素质\n
    Keyword arguments:\n
    character_id -- 角色id\n
    """
    experience = abilities.experience(character_id)
    talent = abilities.talent(character_id)
    character_data = identity.of(character_id)
    if (
        handle_premise.handle_self_have_easily_drunk(character_id)
        and experience[94] >= 30
    ):
        talent[360] = 0
        talent[353] = 1
        now_draw_text = _(
            "\n{0}因为稍微习惯了酒精（饮酒经验>=30），因此对酒精的耐受力稍微提高了\n"
        ).format(character_data.name)
        now_draw_text += _("{0}失去了[酒量差]\n").format(character_data.name)
        now_draw_text += _("{0}获得了[酒量差]\n").format(character_data.name)
        now_draw_succed = draw.WaitDraw()
        now_draw_succed.text = now_draw_text
        now_draw_succed.draw()
    if (
        handle_premise.handle_self_have_bad_alcohol_tolerance(character_id)
        and experience[94] >= 100
    ):
        talent[353] = 0
        now_draw_text = _(
            "\n{0}因为经常饮酒（饮酒经验>=100），因此对酒精的耐受力提高了\n"
        ).format(character_data.name)
        now_draw_text += _("{0}失去了[酒量差]\n").format(character_data.name)
        now_draw_succed = draw.WaitDraw()
        now_draw_succed.text = now_draw_text
        now_draw_succed.draw()
    if (
        not handle_premise.handle_self_have_good_alcohol_tolerance(character_id)
        and experience[94] >= 300
    ):
        talent[354] = 1
        now_draw_text = _(
            "\n{0}因为长期性地饮酒（饮酒经验>=300），因此对酒精的耐受力大大提高了\n"
        ).format(character_data.name)
        now_draw_text += _("{0}获得了[好酒量]\n").format(character_data.name)
        now_draw_succed = draw.WaitDraw()
        now_draw_succed.text = now_draw_text
        now_draw_succed.draw()
