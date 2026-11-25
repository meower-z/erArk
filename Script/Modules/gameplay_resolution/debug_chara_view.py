"""
调试面板角色状态展示服务（debug_chara_view）
============================================
提供调试面板 NPC 角色编辑页的菜单项、页眉与各子页面展示文本。
本模块不导入 Script.UI 与 Script.Settle。
"""

from collections.abc import Callable, Iterable
from types import MappingProxyType
from typing import Literal

from Script.Config import game_config
from Script.Core import num
from Script.Design import handle_premise
from Script.Modules.domains import abilities, action_info, activity, chara_life
from Script.Modules.domains import dirty, flags, h_meters, h_state, hypnosis
from Script.Modules.domains import identity, needs, physical_exam, pregnancy
from Script.Modules.domains import relations, status

type ScreenKind = Literal["list", "gap", "block", "strict"]
""" list逐行换行，gap加尾空行，block单块两换行单输入，strict同block须含逗号 """

MENU = (
    "[000]:基础属性（已实装）",
    "[001]:道具",
    "[002]:衣服",
    "[003]:当前行为状态",
    "[004]:当前二段行为状态（已实装）",
    "[005]:当前事件状态",
    "[006]:状态（已实装）",
    "[007]:能力（已实装）",
    "[008]:经验（已实装）",
    "[009]:宝珠（已实装）",
    "[010]:素质（已实装）",
    "[011]:初次状态记录",
    "[012]:污浊（已实装）",
    "[013]:本次H（已实装）",
    "[014]:助理情况（已实装）",
    "[015]:行动记录",
    "[016]:工作",
    "[017]:娱乐（已实装）",
    "[018]:怀孕（已实装）",
    "[019]:社会关系（已实装）",
    "[020]:特殊flag（已实装）",
    "[021]:催眠（已实装）",
)
""" 角色调试主菜单的 22 条项目标签元组。 """
FLAG_ROWS = (
    ("[000]:在H模式中：", "is_h"),
    ("[001]:AI行动里的原地发呆判定：", "wait_flag"),
    (
        "[002]:跟随玩家，int [0不跟随,1智能跟随,2强制跟随,3前往博士办公室,"
        "4前往博士当前位置]：",
        "is_follow",
    ),
    ("[003]:疲劳状态（HP=1）：", "tired"),
    ("[004]:被玩家惹生气：", "angry_with_player"),
    ("[005]:角色停止移动：", "move_stop"),
    ("[006]:被装袋搬走状态：", "be_bagged"),
    ("[007]:玩家正在装袋搬走的角色的id：", "bagging_chara_id"),
    ("[008]:被监禁状态：", "imprisonment"),
    ("[009]:洗澡状态，int [0无,1要更衣,2要洗澡,3要披浴巾,4洗完澡]：", "shower"),
    ("[010]:吃饭状态，int [0无,1要取餐,2要吃饭]：", "eat_food"),
    ("[011]:要睡觉状态：", "sleep"),
    ("[012]:要休息状态：", "rest"),
    ("[013]:要撒尿状态：", "pee"),
    ("[014]:发现食物不对劲：", "find_food_weird"),
    ("[015]:游泳状态，int [0无,1要换泳衣,2要游泳]：", "swim"),
    ("[016]:要检修状态：", "work_maintenance"),
    (
        "[017]:帮忙买午饭状态，int [0无,1要买饭,2要买第二份饭,3要送饭]：",
        "help_buy_food",
    ),
    ("[018]:帮忙做饭状态，int [0无,1要做饭,2要送饭]：", "help_make_food"),
    ("[019]:早安问候状态，int [0无,1要问候,2已问候]：", "morning_salutation"),
    ("[020]:晚安问候状态，int [0无,1要问候,2已问候]：", "night_salutation"),
    (
        "[021]:大浴场娱乐状态，int [0无,1要更衣,2要娱乐]：",
        "bathhouse_entertainment",
    ),
    ("[022]:要挤奶状态：", "milk"),
    ("[023]:要自慰状态：", "masturebate"),
    ("[024]:访客状态，int [0无,1访问中,2访问过]：", "vistor"),
    (
        "[025]:香薰疗愈状态，int [0无,1回复,2习得,3反感,4快感,5好感,6催眠]：",
        "aromatherapy",
    ),
    (
        "[026]:外勤委托状态，0为未外勤，否则为对应外勤委托编号：",
        "field_commission",
    ),
    ("[027]:要找玩家逆推来自慰的状态：", "npc_masturebate_for_player"),
)
""" 特殊 flag 子页（020）000 至 027 项的展示标签与字段名对照表。 """
_NORMAL_ROWS = (
    (
        "1:基础生理需求：睡觉、休息、解手、吃饭、沐浴（不含已洗澡）、挤奶、自慰：",
        handle_premise.handle_normal_1,
    ),
    ("2:AI行动基本停止：临盆、产后、监禁：", handle_premise.handle_normal_2),
    ("3:高优先级AI：助理、跟随、体检：", handle_premise.handle_normal_3),
    ("4:服装异常：大致全裸、全裸：", handle_premise.handle_normal_4),
    ("5:意识模糊，或弱交互：醉酒，平然：", handle_premise.handle_normal_5),
    (
        "6:完全意识不清醒，或无交互：睡眠（熟睡或完全深眠），时停，空气：",
        handle_premise.handle_normal_6,
    ),
    (
        "7:角色离线：装袋搬走、外勤、婴儿、幼女、他国外交访问、逃跑中：",
        handle_premise.handle_normal_7,
    ),
)
""" 特殊 flag 子页顶部 1 至 7 项异常状态说明与判定函数表。 """
_SEMEN_FORMAT = (
    "编号int:[部位名str,当前精液量int,当前精液等级int,总精液量int]："
)
""" 污浊子页精液数据结构说明文本前缀。 """


def header(cid: int) -> str:
    """
    生成角色调试页面顶部的编号与姓名页眉文本。
    Keyword arguments:
    cid -- int，目标角色编号
    Return arguments:
    str -- 形如 [0001]：姓名 的页眉文本
    """
    target = identity.of(cid)
    return f"[{str(target.adv).rjust(4, '0')}]：{target.name}\n\n"


def _base(cid: int) -> list[str]:
    """构造角色基础属性子页（000）的 20 条展示行。"""
    return [
        f"[000]:当前HP：{num.shown(needs.of(cid)['hit'])}",
        f"[001]:最大HP：{needs.of(cid)['hit_max']}",
        f"[002]:当前MP：{num.shown(needs.of(cid)['mana'])}",
        f"[003]:最大MP：{needs.of(cid)['mana_max']}",
        f"[004]:当前理智：{num.shown(needs.of(cid)['sanity'])}",
        f"[005]:最大理智：{needs.of(cid)['sanity_max']}",
        "[011]:疲劳值 6m=1点，16h=160点(max)："
        f"{num.shown(needs.of(cid)['tired'])}",
        "[012]:尿意值 1m=1点，4h=240点(max)："
        f"{num.shown(needs.of(cid)['urine'])}",
        "[013]:饥饿值 1m=1点，4h=240点(max)："
        f"{num.shown(needs.of(cid)['hunger'])}",
        "[014]:熟睡值 1m=10点，10min=100点(max)："
        f"{num.shown(needs.of(cid)['sleep'])}",
        f"[015]:愤怒槽：{needs.of(cid)['angry']}",
        f"[016]:射精槽：{num.shown(h_meters.of(cid)['eja'])}",
        f"[017]:对玩家的好感度：{relations.favorability(cid)[0]}",
        f"[018]:信赖度：{relations.trust(cid)}",
        f"[019]:乳汁量：{num.shown(needs.of(cid)['milk'])}",
        f"[020]:乳汁上限：{pregnancy.milk_max(cid)}",
        f"[021]:欲望值：{needs.of(cid)['desire']}",
        f"[022]:精液值：{num.shown(h_meters.of(cid)['semen'])}",
        f"[023]:精液值上限：{h_meters.of(cid)['semen_max']}",
        f"[024]:醉酒值 0~100点(max)：{num.shown(needs.of(cid)['drunk'])}",
    ]


def _second(cid: int) -> list[str]:
    """构造角色二段行为状态子页（004）的展示文本行。"""
    text = "\n"
    for behavior_cid in activity.second_ids(cid):
        name = game_config.config_behavior[behavior_cid].name
        value = activity.second_behavior(cid, behavior_cid)
        text += f"({behavior_cid}){name}:{value}  "
        if not behavior_cid % 5:
            text += "\n"
    return [f"[000]:二段行为列表：\n{text}"]


def _listing(title: str, rows: Iterable[tuple[int, str, object]]) -> list[str]:
    """将编号、名称与数值序列格式化为单条列表展示文本。"""
    text = "\n"
    for key, name, value in rows:
        text += f"{key}:{name}={value} "
    return [f"[000]:{title}列表：\n{text}"]


def _states(cid: int) -> list[str]:
    """构造角色状态子页（006）的展示文本行。"""
    text = "\n"
    for state_id, state in game_config.config_character_state.items():
        shown = num.shown(status.of(cid)[state_id])
        text += f"{state_id}:{state.name}={shown} "
    return [f"[000]:状态列表：\n{text}"]


def _abilities(cid: int) -> list[str]:
    """构造角色能力子页（007）的展示文本行。"""
    table = abilities.ability(cid)
    config = game_config.config_ability
    return _listing("能力", ((k, config[k].name, table[k]) for k in config))


def _experience(cid: int) -> list[str]:
    """构造角色经验子页（008）的展示文本行。"""
    table = abilities.experience(cid)
    config = game_config.config_experience
    rows = ((k, config[k].name, table[k]) for k in table if k in config)
    return _listing("经验", rows)


def _juel(cid: int) -> list[str]:
    """构造角色宝珠子页（009）的展示文本行。"""
    table = abilities.juel(cid)
    config = game_config.config_juel
    return _listing("宝珠", ((k, config[k].name, table[k]) for k in table))


def _talent(cid: int) -> list[str]:
    """构造角色素质子页（010）的展示文本行。"""
    table = abilities.talent(cid)
    config = game_config.config_talent
    return _listing("素质", ((k, config[k].name, table[k]) for k in table))


def _assistant(cid: int) -> list[str]:
    """构造角色助理服务子页（014）的展示文本行。"""
    config = game_config.config_assistant_services
    rows = (
        (k, config[k].name, relations.assistant_services(cid)[k])
        for k in relations.assistant_services(cid)
    )
    return _listing("服务", rows)


def _dirty(cid: int) -> list[str]:
    """构造角色污浊与精液子页（012）的展示文本行。"""
    view = dirty.view(cid)
    body = {
        part: [slot[0], num.shown(slot[1]), *slot[2:]]
        for part, slot in view.body_semen.items()
    }
    return [
        f"[000]:身体精液情况，{_SEMEN_FORMAT}\n{body}",
        f"\n[001]:服装精液情况，{_SEMEN_FORMAT}\n{view.cloth_semen}",
        f"\n[002]:衣柜里的服装精液情况，{_SEMEN_FORMAT}\n"
        f"{view.cloth_locker_semen}",
        "\n[003]:A是否干净 [0脏污,1灌肠中,2已灌肠,3精液灌肠中,4已精液灌肠]："
        f"{view.a_clean}",
        "[004]:身体部位:当前精液量int，输入4,0,5即可把0号部位的精液量改为5",
        "[005]:身体部位:当前精液等级int，输入5,0,1即可把0号部位的精液等级改为1",
        "[006]:服装部位:当前精液量int，输入6,1,5即可把1号服装的精液量改为5",
        "[007]:服装部位:当前精液等级int，输入7,1,1即可把1号服装的精液等级改为1",
        "[008]:增加身体、服装、衣柜服装全部位精液量int",
    ]


def _h_state(cid: int) -> list[str]:
    """构造角色本次 H 状态子页（013）的展示文本行。"""
    view = h_state.view(cid)
    return [
        "[000]:身体道具情况:编号int:[道具名str,当前有无bool,"
        f"状态的结束时间datetime.datetime]：\n{view.body_item}",
        f"\n[001]:绳子捆绑情况:编号int：{view.bondage}",
        "\n[002]:阴茎插入位置，int，-1为未插入，其他同身体部位："
        f"{view.insert_position}",
        "\n[003]:身体上的射精位置，int，-1为未射精，其他同身体部位："
        f"{view.shoot_position_body}",
        "\n[004]:衣服上的射精位置，int，-1为未射精，其他同衣服部位："
        f"{view.shoot_position_cloth}",
        "\n[005]:高潮程度记录，每3级一个循环，1为小绝顶，2为普绝顶，3为强绝顶："
        f"\n{view.orgasm_level}",
        "\n[006]:衣服上的射精位置，int，-1为未射精，其他同衣服部位："
        f"\n{view.orgasm_count}",
    ]


def _fun(cid: int) -> list[str]:
    """构造角色娱乐与借书子页（017）的展示文本块。"""
    return [
        f"[000]:娱乐活动的类型：{chara_life.entertainment_type(cid)}\n"
        f"[001]:借的书的id：{chara_life.borrow_book_id_set(cid)}\n"
        "[002]:归还当前阅读书籍的可能性比例："
        f"{chara_life.book_return_possibility(cid)}\n"
    ]


def _pregnancy(cid: int) -> list[str]:
    """构造角色怀孕与乳汁子页（018）的展示文本行。"""
    preg = pregnancy.of(cid)
    talent = abilities.talent(cid)
    period = game_config.config_reproduction_period[preg.reproduction_period]
    period_text = game_config.ui_text_data["h_state"][f"生理期{period.type}"]
    return [
        f"[000]:受精概率：{preg.fertilization_rate}",
        "[001]:生殖周期的第几天(0安全1普通2危险3排卵，0110232)："
        f"{preg.reproduction_period},{period_text}",
        f"[002]:开始受精的时间：{preg.fertilization_time}      年月日分别为0,1,2",
        f"[003]:当前妊娠素质：0受精-{talent[20]}，1妊娠-{talent[21]}，"
        f"2临盆-{talent[22]}，3产后-{talent[23]}，4育儿-{talent[24]}",
        f"[004]:出生的时间：{preg.born_time}      年月日分别为0,1,2",
        "[005]:一键触发生产事件",
        "[006]:一键触发育儿+育儿完成事件",
        f"[007]:角色当前乳汁量：{num.shown(needs.of(cid)['milk'])}",
        f"[008]:角色最大乳汁量：{pregnancy.milk_max(cid)}",
    ]


def _relations(cid: int) -> list[str]:
    """构造角色父母与孩子关系子页（019）的展示文本块。"""
    return [
        f"[000]:父亲id：{relations.father_id(cid)}\n"
        f"[001]:母亲id：{relations.mother_id(cid)}\n"
        f"[002]:孩子id列表：{relations.child_id_list(cid)}\n"
    ]


def _flags(cid: int) -> list[str]:
    """构造角色异常判定与特殊 flag 子页（020）的展示文本块。"""
    text = "1~7异常状态：正常为1"
    for label, judge in _NORMAL_ROWS:
        text += f"    \n{label}{judge(cid)}"
    text += "\n\n"
    for label, flag in FLAG_ROWS:
        text += f"{label}{flags.get(cid, flag)}\n"
    text += (
        "[028]:正在等待体检状态（仅查看，无法修改）："
        f"{physical_exam.has(physical_exam.WAITING, cid)}\n"
        "[029]:今天体检时间，[0不需要，1上午，2下午，3新干员立刻体检]："
        f"{action_info.get(cid, 'health_check_today')}\n"
    )
    return [text]


def _hypnosis(cid: int) -> list[str]:
    """构造角色催眠状态子页（021）的展示文本块。"""
    view = hypnosis.view(cid)
    return [
        f"[000]:催眠程度：{view.hypnosis_degree}\n"
        f"[001]:体控-敏感度提升：{view.increase_body_sensitivity}\n"
        f"[002]:体控-强制排卵：{view.force_ovulation}\n"
        f"[003]:体控-木头人：{view.blockhead}\n"
        f"[004]:体控-逆推：{view.active_h}\n"
        f"[005]:心控-角色扮演，0为无，其他见Roleplay.csv：{view.roleplay}\n"
    ]


SCREENS: MappingProxyType[
    int, tuple[ScreenKind, Callable[[int], list[str]]]
] = MappingProxyType(
    {
        0: ("list", _base),
        4: ("list", _second),
        6: ("list", _states),
        7: ("list", _abilities),
        8: ("list", _experience),
        9: ("list", _juel),
        10: ("list", _talent),
        12: ("list", _dirty),
        13: ("list", _h_state),
        14: ("list", _assistant),
        17: ("block", _fun),
        18: ("gap", _pregnancy),
        19: ("block", _relations),
        20: ("strict", _flags),
        21: ("strict", _hypnosis),
    }
)
""" 角色调试子页编号到布局类型与文本构造函数的只读映射。 """
