"""
角色状态标识服务（status_tag_service）
======================================
本模块按固定顺序计算角色信息头部的 18 项状态标识数据。
本模块公开数据类 StatusTag 与函数 status_tags。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

from collections.abc import Callable
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config, normal_config
from Script.Core import constant, get_text
from Script.Design import attr_calculation, game_time, handle_premise
from Script.Modules.domains import abilities, action_info, activity
from Script.Modules.domains import flags, h_state
from Script.Modules.domains import hypnosis, identity, needs
from Script.Modules.gameplay_resolution import class_tip_service
from Script.Modules.gameplay_resolution import hypnosis_service

_: FunctionType = get_text._
""" 翻译api """

_MEAL_HOURS = frozenset({6, 7, 8, 11, 12, 13, 16, 17, 18})
""" 非玩家角色显示饥饿标识 <饿> 所需的行为开始小时集合。 """


@dataclass(frozen=True, slots=True)
class StatusTag:
    """
    角色信息头部的单条状态标识数据。
    属性 text 为显示文本，style 为绘制样式名，tooltip 为悬停提示文本。
    默认值分别为空字符串、"standard" 与空字符串。
    """

    text: str = ""
    style: str = "standard"
    tooltip: str = ""


def _follow(character_id: int) -> StatusTag:
    if handle_premise.handle_is_follow_1(character_id):
        return StatusTag(
            _(" <跟>"),
            "spring_green",
            _("处于智能跟随状态，会自动跟随玩家行动"),
        )
    return StatusTag(style="spring_green")


def _class(character_id: int) -> StatusTag:
    class_tip = class_tip_service.get_now_class_tip(character_id)
    if not class_tip:
        return StatusTag(style="light_steel_blue")
    if class_tip[0]:
        return StatusTag(_(" <翘>"), "red", class_tip[1])
    return StatusTag(_(" <课>"), "light_steel_blue", class_tip[1])


def _angry(character_id: int) -> StatusTag:
    angry_text = ""
    if character_id != 0:
        angry_text = attr_calculation.get_angry_text(
            needs.of(character_id)["angry"]
        )
        angry_text = "" if angry_text == _("普通") else " " + angry_text
    if angry_text == _(" 愉快"):
        return StatusTag(
            angry_text, "coral", _("当前心情愉快，部分行为实行值提升")
        )
    return StatusTag(angry_text, "red", _("当前心情不佳，部分行为实行值下降"))


def _hunger(character_id: int) -> StatusTag:
    hungry = handle_premise.handle_hunger_ge_80
    tooltip = _("肚子饿了，想要吃点东西")
    if character_id != 0:
        hunger_text = _(" <饿>") if hungry(character_id) else ""
        start_hour = activity.behavior(character_id).start_time.hour
        if start_hour not in _MEAL_HOURS:
            hunger_text = ""
        return StatusTag(hunger_text, "beige", tooltip)
    if normal_config.system_setting.draw_setting.get(17, 1) == 1:
        hunger_text = _(" <饿>") if hungry(character_id) else ""
        return StatusTag(hunger_text, "beige", tooltip)
    return StatusTag(style="beige")


def _urinate(character_id: int) -> StatusTag:
    urinate_text = ""
    tooltip = ""
    if handle_premise.handle_urinate_ge_80(character_id):
        urinate_text = _(" <尿>")
        tooltip = _("有较强的尿意，想要去洗手间解决")
    if (
        character_id == 0
        and normal_config.system_setting.draw_setting.get(17, 1) == 0
    ):
        urinate_text = ""
    return StatusTag(urinate_text, "khaki", tooltip)


def _sleep(character_id: int) -> StatusTag:
    now = needs.of(character_id)
    style = "little_dark_slate_blue"
    tooltip = ""
    tired_lv = attr_calculation.get_tired_level(now["tired"])
    sleep_text = " <" + constant.tired_text_list[tired_lv] + ">"
    if sleep_text == _(" <清醒>"):
        sleep_text = ""
    if character_id <= 0:
        return StatusTag(sleep_text, style, tooltip)
    if handle_premise.handle_action_sleep(
        character_id
    ) or handle_premise.handle_unconscious_flag_1(character_id):
        sleep_lv, sleep_name = attr_calculation.get_sleep_level(now["sleep"])
        sleep_text = f" <{sleep_name}>"
        tooltip = game_config.config_sleep_level[sleep_lv].introduction
        style = game_config.config_sleep_level[sleep_lv].color
        if (
            handle_premise.handle_tired_le_0(character_id)
            and handle_premise.handle_time_day(character_id)
            and handle_premise.handle_self_not_sleep_pills(character_id)
            and handle_premise.handle_drunk_level_0(character_id)
        ):
            sleep_text += _("(将醒)")
            tooltip = _("已经睡饱了，会很快醒来，如果不想被发现最好快点结束")
            style = "warning"
    if handle_premise.handle_self_sleep_h_awake_but_pretend_sleep(character_id):
        sleep_text = _(" <装睡>")
        tooltip = _("已经醒来，但决定装睡来默认你的行为")
    elif handle_premise.handle_sleep_disturbed_1(character_id):
        sleep_text = _(" <被吵醒>")
        left_minute = int(
            (
                action_info.get(character_id, "sleep_disturbed_end_time")
                - game_time.now()
            ).total_seconds()
            // 60
        )
        tooltip = _("刚被吵醒，还需{0}分钟才会重新想睡").format(
            max(1, left_minute)
        )
        style = "warning"
    return StatusTag(sleep_text, style, tooltip)


def _drunk(character_id: int) -> StatusTag:
    from Script.System.Sex_System import drunk_sex_common

    drunk_level, drunk_name = drunk_sex_common.get_drunk_level(character_id)
    if drunk_level <= 0:
        return StatusTag()
    level_data = game_config.config_drunk_level[drunk_level]
    return StatusTag(" " + drunk_name, level_data.color, level_data.info)


def _tired(character_id: int) -> StatusTag:
    if handle_premise.handle_self_tired(character_id):
        return StatusTag(
            _(" <累>"),
            "little_dark_slate_blue",
            _("疲劳度过高，需要回宿舍睡觉"),
        )
    return StatusTag(style="little_dark_slate_blue")


def _hypnosis(character_id: int) -> StatusTag:
    hyp_deg = hypnosis.degree(character_id)
    mode = normal_config.system_setting.draw_setting[4]
    if not mode or not (
        handle_premise.handle_unconscious_hypnosis_flag(character_id)
        or (hyp_deg > 0 and mode == 2)
    ):
        return StatusTag()
    sub_types = game_config.config_hypnosis_sub_type
    hypnosis_text = _(" <催眠")
    tooltip = ""
    if mode == 2:
        hypnosis_text += f"({round(hyp_deg, 1)}%)"
    if handle_premise.handle_unconscious_hypnosis_flag(character_id):
        hypnosis_cid = flags.get(character_id, "unconscious_h") - 3
        type_data = game_config.config_hypnosis_type[hypnosis_cid]
        hypnosis_text += _(":{0}").format(type_data.name)
        tooltip = type_data.introduce
    if handle_premise.handle_hypnosis_increase_body_sensitivity(character_id):
        hypnosis_text += _("(敏感)")
        tooltip = sub_types[1].introduce
    if handle_premise.handle_hypnosis_force_ovulation(character_id):
        hypnosis_text += _("(排卵)")
        tooltip = sub_types[3].introduce
    if handle_premise.handle_hypnosis_blockhead(character_id):
        hypnosis_text += _("(木头人)")
        tooltip = sub_types[4].introduce
    if handle_premise.handle_hypnosis_active_h(character_id):
        hypnosis_text += _("(逆推)")
        tooltip = sub_types[5].introduce
    if handle_premise.handle_hypnosis_roleplay(character_id):
        hypnosis_text += _("(扮演")
        for role_play_cid in hypnosis.roleplay(character_id):
            role_play_name = game_config.config_roleplay[role_play_cid].name
            hypnosis_text += f"-{role_play_name}"
        hypnosis_text += ")"
        tooltip = sub_types[12].introduce
    if handle_premise.handle_hypnosis_pain_as_pleasure(character_id):
        hypnosis_text += _("(痛→快感)")
        tooltip = sub_types[11].introduce
    return StatusTag(
        hypnosis_text + ">",
        hypnosis_service.get_hypnosis_degree_color(hyp_deg),
        tooltip,
    )


def _bag(character_id: int) -> StatusTag:
    bagging_id = flags.get(character_id, "bagging_chara_id")
    if not bagging_id:
        return StatusTag()
    return StatusTag(
        _(" <携袋:{0}>").format(identity.of(bagging_id).name),
        tooltip=_("将失去意识的干员装进了袋子中，用于在关押区监禁到牢房里"),
    )


def _visitor(character_id: int) -> StatusTag:
    if flags.get(character_id, "vistor") != 1:
        return StatusTag()
    return StatusTag(
        _(" <访>"),
        tooltip=_(
            "作为访客来罗德岛参观，不会参与工作和常规活动，在访问期结束后会离开罗德岛或留下成为干员"
        ),
    )


def _active_h(character_id: int) -> StatusTag:
    if handle_premise.handle_npc_active_h(character_id):
        return StatusTag(_(" <逆>"), "light_pink", _("对博士主动进行性行为"))
    return StatusTag(style="light_pink")


def _orgasm_edge(character_id: int) -> StatusTag:
    if not handle_premise.handle_self_orgasm_edge(character_id):
        return StatusTag()
    margin = abilities.ability(0)[30] * 3 - sum(
        value * value
        for value in h_state.view(character_id).orgasm_edge_count.values()
    )
    if margin >= 3:
        return StatusTag(
            _(" <寸止>"), "hot_pink", _("被进行了绝顶寸止，会无法绝顶高潮")
        )
    if margin >= 0:
        return StatusTag(
            _(" <寸止!>"),
            "red",
            _("被进行了绝顶寸止，差不多到了能控制住的极限"),
        )
    return StatusTag(
        _(" <寸止!!>"),
        "levelex",
        _("被进行了绝顶寸止，已经超过能控制住的极限"),
    )


def _imprisonment(character_id: int) -> StatusTag:
    if handle_premise.handle_imprisonment_1(character_id):
        return StatusTag(_(" <监>"), "crimson", _("被监禁，无法自由行动"))
    return StatusTag(style="crimson")


def _time_stop(character_id: int) -> StatusTag:
    if handle_premise.handle_unconscious_flag_3(character_id):
        return StatusTag(
            _(" <停>"), "light_sky_blue", _("处于时间停止状态，无法行动")
        )
    return StatusTag(style="light_sky_blue")


def _hidden(character_id: int) -> StatusTag:
    if character_id == 0:
        hidden = handle_premise.handle_hidden_sex_mode_3(
            character_id
        ) or handle_premise.handle_hidden_sex_mode_4(character_id)
    else:
        hidden = handle_premise.handle_hidden_sex_mode_2(
            character_id
        ) or handle_premise.handle_hidden_sex_mode_4(character_id)
    if not hidden:
        return StatusTag(style="deep_gray")
    return StatusTag(
        _(" <隐>"),
        "deep_gray",
        _("正在偷偷进行性行为，享受避免被他人发现的刺激感"),
    )


def _exhibitionism(character_id: int) -> StatusTag:
    if handle_premise.handle_exhibitionism_sex_mode_ge_1(character_id):
        return StatusTag(
            _(" <露>"),
            "hot_pink",
            _("正在进行露出行为，享受被他人看到的刺激感"),
        )
    return StatusTag(style="hot_pink")


def _first_sex(character_id: int) -> StatusTag:
    text = ""
    tooltip = ""
    if handle_premise.handle_first_sex_in_today(character_id):
        if character_id == 0:
            text += _(" <P破处>")
            tooltip += _("今天失去了童贞")
        else:
            text += _(" <V破处>")
            tooltip += _("今天失去了阴道处女，还残留着隐痛和扩张感")
    if handle_premise.handle_first_a_sex_in_today(character_id):
        text += _(" <A破处>")
        tooltip += _("今天失去了肛门处女，还残留着隐痛和扩张感")
    if handle_premise.handle_first_u_sex_in_today(character_id):
        text += _(" <U破处>")
        tooltip += _("今天失去了尿道处女，还残留着隐痛和扩张感")
    if handle_premise.handle_first_w_sex_in_today(character_id):
        text += _(" <W破处>")
        tooltip += _("今天失去了子宫处女，还残留着隐痛和扩张感")
    return StatusTag(text, "crimson", tooltip)


_TAG_RULES: tuple[Callable[[int], StatusTag], ...] = (
    _follow,
    _class,
    _angry,
    _hunger,
    _urinate,
    _sleep,
    _drunk,
    _tired,
    _hypnosis,
    _bag,
    _visitor,
    _active_h,
    _orgasm_edge,
    _imprisonment,
    _time_stop,
    _hidden,
    _exhibitionism,
    _first_sex,
)
""" 按固定展示顺序排列的 18 项状态标识规则函数元组。 """


def status_tags(character_id: int) -> list[StatusTag]:
    """
    按 _TAG_RULES 顺序计算角色的全部 18 项状态标识。
    未触发的标识以空文本占位，并保留对应规则设定的样式与悬停提示。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    list[StatusTag] -- 长度为 18 的状态标识列表
    """
    return [rule(character_id) for rule in _TAG_RULES]
