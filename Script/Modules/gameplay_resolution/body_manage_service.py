"""
身体管理服务（body_manage_service）
===================================
提供身体管理条件判定、管理表补齐、项目行构造、开关切换与职业联动、受管干员查询及批量取消。
本模块不导入 Script.UI 与 Script.Settle。
"""

from collections.abc import Callable, Collection
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import attr_calculation, basement, handle_premise
from Script.Design import second_behavior
from Script.Modules.domains import abilities, body_manage, chara_life, dirty
from Script.Modules.domains import hypnosis, identity, modes
from Script.Modules.domains import player_collection, roster

_: FunctionType = get_text._
""" 本地化翻译函数。 """
EXERCISES = range(31, 40)
""" 性爱练习类身体管理项目的编号区间（31 至 39）。 """
SEX_TRAINEE = 193
""" 性爱练习生特殊职业对应的工作类型编号（193）。 """

type Measure = tuple[str, Callable[[], int]]
""" 管理条件主指标类型别名，包含本地化模板与无参取值函数。 """


@dataclass(frozen=True, slots=True)
class ManageRow:
    """身体管理列表中单条管理项目的展示数据。"""

    number: int
    """ 按配置顺序统计的管理项序号。 """
    manage_id: int
    """ 身体管理项目编号。 """
    label: str
    """ 可选时的带状态标签，或不可选时的对齐名称与条件说明文本。 """
    available: bool
    """ 该管理项目在当前状态下是否可点击切换。 """


def _collected(name: str, cid: int) -> int:
    """
    统计玩家某类收藏品中属于指定角色的条目数量。
    Keyword arguments:
    name -- str，玩家收藏品类别键
    cid -- int，目标角色编号
    Return arguments:
    int -- 对应的收藏条目数量
    """
    return len(player_collection.get(name).get(cid, ()))


def _semen(cid: int) -> int:
    """
    计算指定角色身体部位 6 与部位 7 的累计精液量之和。
    Keyword arguments:
    cid -- int，目标角色编号
    Return arguments:
    int -- 两部位总精液量（下标 3）之和
    """
    semen = dirty.view(cid).body_semen
    return semen[6][3] + semen[7][3]


def _measures(cid: int) -> dict[str, Measure]:
    """
    构造二段行为编号到条件主指标模板及取值函数的映射表。
    Keyword arguments:
    cid -- int，目标角色编号
    Return arguments:
    dict[str, Measure] -- 二段行为编号到主指标元组的映射
    """
    ability = abilities.ability(cid)
    experience = abilities.experience(cid)
    panties = (_("内裤收藏数量{0}/{1}"), lambda: _collected("npc_panties", cid))
    sleep = (_("被睡姦经验{0}/{1}"), lambda: experience[121])
    nipple = (_("Ｂ感觉等级{0}/{1}"), lambda: ability[1])
    clit = (_("Ｃ感觉等级{0}/{1}"), lambda: ability[2])
    vagina = (_("Ｖ感觉等级{0}/{1}"), lambda: ability[4])
    anus = (_("Ａ感觉等级{0}/{1}"), lambda: ability[5])
    masturbation = (_("自慰经验{0}/{1}"), lambda: experience[54])
    semen = (_("精液经验{0}/{1}"), lambda: experience[24])
    return {
        "ask_give_pan_everyday": panties,
        "ask_give_socks_everyday": (
            _("袜子收藏数量{0}/{1}"),
            lambda: _collected("npc_socks", cid),
        ),
        "ask_not_wear_corset": (_("露出能力等级{0}/{1}"), lambda: ability[34]),
        "ask_not_wear_cloth_in_sleep": sleep,
        "ask_wear_different_socks_everyday": panties,
        "ask_equip_nipple_clamp_in_day": nipple,
        "ask_equip_nipple_clamp_in_sleep": nipple,
        "ask_equip_clit_clamp_in_day": clit,
        "ask_equip_clit_clamp_in_sleep": clit,
        "ask_equip_v_vibrator_in_day": vagina,
        "ask_equip_v_vibrator_in_sleep": vagina,
        "ask_equip_a_vibrator_in_day": anus,
        "ask_equip_a_vibrator_in_sleep": anus,
        "ask_not_wash_semen": (
            _("V与W总被射入精液{0}ml/{1}ml"),
            lambda: _semen(cid),
        ),
        "ask_masturbation_before_sleep": masturbation,
        "ask_not_masturbation": masturbation,
        "ask_not_active_h_for_player": (
            _("逆推经验{0}/{1}"),
            lambda: experience[36],
        ),
        "ask_not_lock_door_before_sleeping": sleep,
        "ask_not_take_bath": semen,
        "ask_not_wash_cloth": semen,
    }


def _blockers(manage_id: int, cid: int) -> list[tuple[str, bool]]:
    """
    检查指定管理项目的硬性前置条件，返回提示文本与是否受阻的列表。
    Keyword arguments:
    manage_id -- int，身体管理项目编号
    cid -- int，目标角色编号
    Return arguments:
    list[tuple[str, bool]] -- 前置说明文本与阻塞布尔值列表
    """
    talent = abilities.talent(cid)
    found = []
    if manage_id == 36:
        found.append((_(" 需要非处女"), bool(talent[0])))
    elif manage_id == 37:
        found.append((_(" 需要非A处女"), bool(talent[1])))
    if manage_id in {11, 15}:
        found.append(
            (_(" 需要持有乳夹"), not handle_premise.handle_have_nipple_clamp(0))
        )
    elif manage_id in {12, 16}:
        found.append(
            (_(" 需要持有阴蒂夹"), not handle_premise.handle_have_clit_clamp(0))
        )
    elif manage_id in {13, 14, 17, 18}:
        found.append(
            (_(" 需要持有震动棒"), not handle_premise.handle_have_vibrator(0))
        )
    if manage_id in EXERCISES:
        found.append(
            (
                _(" 需要已送给对方自己的阴茎倒模"),
                not handle_premise.handle_target_have_penis_mold(0),
            )
        )
    return found


def _conflicts(manage_id: int, cid: int) -> list[str]:
    """
    检查指定管理项目与已激活项目或练习数量上限的冲突，返回冲突提示列表。
    Keyword arguments:
    manage_id -- int，身体管理项目编号
    cid -- int，目标角色编号
    Return arguments:
    list[str] -- 触发的冲突说明文本列表
    """
    found = []
    if manage_id in {22, 25} and handle_premise.handle_ask_not_masturbation(
        cid
    ):
        found.append(_(" 需要未选择[禁止自慰]"))
    if manage_id == 23 and handle_premise.handle_ask_masturbation_before_sleep(
        cid
    ):
        found.append(_(" 需要未选择[每天晚上睡前都要自慰]"))
    if manage_id == 23 and handle_premise.handle_ask_not_active_h_for_player(
        cid
    ):
        found.append(_(" 需要未选择[禁止逆推]"))
    if manage_id == 26 and handle_premise.handle_ask_not_wash_semen(cid):
        found.append(_(" 需要未选择[洗澡时不再清洗阴道内的精液]"))
    if manage_id == 21 and handle_premise.handle_ask_not_take_bath(cid):
        found.append(_(" 需要未选择[禁止一切洗澡]"))
    if manage_id in EXERCISES and handle_premise.handle_ask_ge_3_exercises(cid):
        found.append(_(" 最多只能选择3项练习项目"))
    return found


def requirement(manage_id: int, cid: int) -> tuple[bool, str]:
    """
    判定角色是否满足指定身体管理项目的开启条件，并组装条件说明文本。
    Keyword arguments:
    manage_id -- int，身体管理项目编号
    cid -- int，目标角色编号
    Return arguments:
    tuple[bool, str] -- 是否满足条件以及拼接后的条件说明文本
    """
    data = game_config.config_body_manage_requirement[manage_id]
    met = False
    text = ""
    measure = _measures(cid).get(data.second_behavior_id)
    if measure is not None:
        template, read = measure
        value = read()
        text += template.format(value, data.need_value_1)
        met = value >= data.need_value_1
    fall = attr_calculation.get_character_fall_level(cid)
    text += _(" 或 攻略进度{0}/{1}").format(fall, data.need_value_2)
    met = met or fall >= data.need_value_2
    degree = hypnosis.degree(cid)
    text += _(" 或 催眠程度{0}%/{1}%").format(degree, data.need_value_3)
    met = met or degree >= data.need_value_3
    for note, blocked in _blockers(manage_id, cid):
        text += note
        met = met and not blocked
    for note in _conflicts(manage_id, cid):
        text += note
        met = False
    return met, text


def ensure_table(cid: int) -> None:
    """
    确保角色的身体管理状态表包含配置中的全部项目编号，空表初始化为全 0，缺项时补写为 0。
    Keyword arguments:
    cid -- int，目标角色编号
    Return arguments:
    None -- 无返回值
    """
    if not len(body_manage.of(cid)):
        body_manage.replace(cid, attr_calculation.get_body_manage_zero())
    elif len(body_manage.of(cid)) != len(
        game_config.config_body_manage_requirement
    ):
        for manage_id in game_config.config_body_manage_requirement:
            if manage_id not in body_manage.of(cid):
                body_manage.set(cid, manage_id, 0)


def manage_rows(cid: int, done: Collection[str]) -> list[ManageRow]:
    """
    按配置顺序生成角色的可见身体管理行，跳过待办项并隐藏未完成前置检查的未激活项，调试模式放开可见行。
    Keyword arguments:
    cid -- int，目标角色编号
    done -- Collection[str]，已完成的检查行为编号集合
    Return arguments:
    list[ManageRow] -- 可见身体管理项目行列表
    """
    rows = []
    count = 0
    for manage_id, data in game_config.config_body_manage_requirement.items():
        name = game_config.config_behavior[data.second_behavior_id].name
        name = name.replace(_("被要求"), "")
        count += 1
        if data.todo:
            continue
        met, text = requirement(manage_id, cid)
        if text.startswith(" 或 "):
            text = text[3:]
        active = bool(body_manage.of(cid)[manage_id])
        if active:
            met = True
        elif data.need_examine_id != "0" and data.need_examine_id not in done:
            continue
        if modes.debug():
            met = True
        number = str(count).rjust(2, "0")
        if met:
            label = f"[{number}]：{name}"
            if body_manage.of(cid)[manage_id]:
                label += _("(进行中)")
        else:
            label = f"[{number}]：{name.ljust(20, '　')}（ {text} ）\n"
        rows.append(ManageRow(count, manage_id, label, met))
    return rows


def toggle(manage_id: int, cid: int) -> str:
    """
    切换角色指定身体管理项目的开关状态，开启时赋予二段行为并按练习项目规则联动性爱练习生职业与工作名单。
    Keyword arguments:
    manage_id -- int，身体管理项目编号
    cid -- int，目标角色编号
    Return arguments:
    str -- 操作结果与职业变动提示文本
    """
    behavior_id = game_config.config_body_manage_requirement[
        manage_id
    ].second_behavior_id
    name = identity.of(cid).name
    behavior_name = game_config.config_behavior[behavior_id].name
    trainee = game_config.config_work_type[SEX_TRAINEE].name
    text = "\n"
    if body_manage.of(cid)[manage_id] == 0:
        second_behavior.character_get_second_behavior(cid, behavior_id)
        body_manage.set(cid, manage_id, 1)
        text += _("对{0}进行了{1}的身体管理，将在明天睡醒后生效。\n").format(
            name, behavior_name
        )
        if (
            manage_id in EXERCISES
            and not handle_premise.handle_work_is_sex_trainee(cid)
        ):
            chara_life.work_type.set(cid, SEX_TRAINEE)
            basement.update_work_people()
            text += _(
                "因为被要求进行性爱的相关练习，所以{0}的工作被调整为特殊职业-{1}了\n"
            ).format(name, trainee)
    else:
        body_manage.set(cid, manage_id, 0)
        text += _("取消了对{0}的{1}的身体管理，将在明天睡醒后生效。\n").format(
            name, behavior_name
        )
        if (
            manage_id in EXERCISES
            and handle_premise.handle_ask_none_exercises(cid)
            and handle_premise.handle_work_is_sex_trainee(cid)
        ):
            chara_life.work_type.set(cid, 0)
            basement.update_work_people()
            text += _(
                "因为没有进行性爱的相关练习，所以{0}的特殊职业-{1}被取消了\n"
            ).format(name, trainee)
    return text


def managed_npcs() -> list[int]:
    """
    查询除主角外至少有一项身体管理处于开启状态的在编干员编号列表。
    Keyword arguments:
    无
    Return arguments:
    list[int] -- 存在生效身体管理项的干员编号列表
    """
    return [
        npc_id
        for npc_id in roster.active()
        if npc_id != 0
        and any(
            body_manage.of(npc_id)[manage_id] > 0
            for manage_id in game_config.config_body_manage_requirement
        )
    ]


def cancel_all(cid: int) -> None:
    """
    将角色的身体管理状态表整体重置为全 0，不改动其当前工作类型。
    Keyword arguments:
    cid -- int，目标角色编号
    Return arguments:
    None -- 无返回值
    """
    body_manage.replace(cid, attr_calculation.get_body_manage_zero())
