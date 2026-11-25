"""
角色信息服务（character_info_service）
======================================
提供角色状态条、能力、经验、宝珠、素质、日程、访客及场景角色切换计算。
本模块不导入 Script.UI 与 Script.Settle。
"""

import os
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text, num
from Script.Design import attr_calculation, game_time, instuct_judege
from Script.Design import map_handle
from Script.Modules.domains import abilities, activity, chara_life, h_state
from Script.Modules.domains import identity, relations, scene_state, status
from Script.Modules.domains import visitor

_: FunctionType = get_text._
""" 本地化翻译函数。 """
LUBRICATION = 8
""" 状态编号 8，排入类型 0 状态分区末尾并从其余分区排除。 """
EDGE_STYLES = {1: "hot_pink", 2: "deep_pink", 3: "red"}
""" 1 至 3 次绝顶寸止累计次数到状态名称样式名的映射表。 """
MALE_HIDDEN_STATUS = frozenset({2, 4, 7})
""" sex 为 0 时在状态条与宝珠列表中隐藏的编号集合（2、4、7）。 """
MALE_HIDDEN_EXPERIENCE = frozenset(
    {2, 4, 7, 12, 14, 17, 20, 22, 26, 51, 54, 55, 58, 72, 74, 77, 86}
    | set(range(100, 107))
)
""" sex 为 0 时在经验列表中隐藏的经验编号集合。 """
PLAYER_HIDDEN_ABILITY_TYPES = frozenset({2, 6})
""" 角色编号为 0 时在能力列表中跳过的能力类型集合（2、6）。 """
TIME_STOP_MARK = 16
""" 在能力列表中固定跳过的能力编号（16）。 """
ABILITY_ROW_BREAKS = frozenset({48, 101})
""" 绘制前需要前置换行的能力编号集合（48、101）。 """


@dataclass(frozen=True, slots=True)
class StatusBar:
    """单条角色状态进度条的展示数据。"""

    text: str
    """ 进度条标题文本，格式为名称拼接 lv 与当前等级。 """
    max_value: int
    """ 当前状态等级对应的进度条上限值。 """
    value: int
    """ 当前展示的状态数值。 """
    tooltip: str
    """ 悬停提示文本，累计寸止次数不少于 1 时追加次数说明。 """
    style: str
    """ 状态名称样式名，无寸止累计时为空字符串。 """


@dataclass(frozen=True, slots=True)
class AbilityRow:
    """单条角色能力展示行的数据结构。"""

    label: str
    """ 前导两空格并按显示宽度 10 补齐的能力名称。 """
    info: str
    """ 能力配置说明文本，用作悬停提示。 """
    level: int
    """ 角色当前持有的该项能力等级。 """
    break_before: bool
    """ 该能力行之前是否需要插入换行。 """


def _status_bar(
    character_data: identity.Identity, status_id: int
) -> StatusBar | None:
    """
    为指定角色与状态编号构造单条状态进度条数据，按性别过滤隐藏项。
    Keyword arguments:
    character_data -- identity.Identity，目标角色身份对象
    status_id -- int，状态配置编号
    Return arguments:
    StatusBar | None -- 需要显示时返回状态条数据，按性别隐藏时返回 None
    """
    if status_id in MALE_HIDDEN_STATUS and character_data.sex == 0:
        return None
    if status_id == 3 and character_data.sex == 1:
        return None
    config = game_config.config_character_state[status_id]
    value = 0
    if status_id in status.of(character_data.cid):
        value = num.shown(status.of(character_data.cid)[status_id])
    level = attr_calculation.get_status_level(value)
    hs = h_state.view(character_data.cid)
    edge = hs.orgasm_edge_count.get(status_id, 0)
    edge += hs.time_stop_orgasm_count.get(status_id, 0)
    tooltip = config.info
    if edge >= 1:
        tooltip += _("(绝顶寸止{0}次)").format(edge)
    return StatusBar(
        f"{config.name}lv{level}",
        game_config.config_character_state_level[level].max_value,
        value,
        tooltip,
        "levelex" if edge >= 4 else EDGE_STYLES.get(edge, ""),
    )


def status_sections(character_id: int) -> list[tuple[str, list[StatusBar]]]:
    """
    按状态分类构造角色的状态条分区列表，将编号 8 置于类型 0 分区末尾并从其余分区排除。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    list[tuple[str, list[StatusBar]]] -- 各状态分类名称及对应状态条列表
    """
    character_data = identity.of(character_id)
    sections = []
    for (
        status_type,
        ids,
    ) in game_config.config_character_state_type_data.items():
        if status_type == 0:
            order = [*ids, LUBRICATION]
        else:
            order = [i for i in ids if i != LUBRICATION]
        bars = [_status_bar(character_data, i) for i in order]
        sections.append(
            (
                game_config.config_character_state_type[status_type].name,
                [bar for bar in bars if bar is not None],
            )
        )
    return sections


def ability_sections(character_id: int) -> list[tuple[int, list[AbilityRow]]]:
    """
    按能力分类构造角色的能力行分区列表，过滤主角跳过分类、性别不符项及编号 16。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    list[tuple[int, list[AbilityRow]]] -- 各能力分类编号及对应能力行列表
    """
    sex = identity.of(character_id).sex
    levels = abilities.ability(character_id)
    sections = []
    for ability_type, ids in game_config.config_ability_type_data.items():
        if character_id == 0 and ability_type in PLAYER_HIDDEN_ABILITY_TYPES:
            continue
        rows = []
        for ability_id in ids:
            data = game_config.config_ability[ability_id]
            if (sex, data.sex_need) in {(0, 1), (1, 0)}:
                continue
            if ability_id == TIME_STOP_MARK:
                continue
            rows.append(
                AbilityRow(
                    "  " + attr_calculation.pad_display_width(data.name, 10),
                    data.info,
                    levels[ability_id],
                    ability_id in ABILITY_ROW_BREAKS,
                )
            )
        sections.append((ability_type, rows))
    return sections


def experience_texts(character_id: int) -> list[str]:
    """
    构造角色大于 0 的经验展示文本列表，sex 为 0 时跳过隐藏经验编号。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    list[str] -- 形如「 名称:数值」的经验文本列表
    """
    experience = abilities.experience(character_id)
    sex = identity.of(character_id).sex
    texts = []
    for experience_id, data in game_config.config_experience.items():
        if sex == 0 and experience_id in MALE_HIDDEN_EXPERIENCE:
            continue
        if experience.get(experience_id, 0) > 0:
            texts.append(f" {data.name}:{experience[experience_id]}")
    return texts


def juel_texts(character_id: int) -> list[str]:
    """
    构造角色各宝珠的展示文本列表，缺失项按 0 显示，sex 为 0 时跳过隐藏编号。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    list[str] -- 形如「 名称:数值」的宝珠文本列表
    """
    juel = abilities.juel(character_id)
    sex = identity.of(character_id).sex
    return [
        f" {data.name}:{juel.get(juel_id, 0)}"
        for juel_id, data in game_config.config_juel.items()
        if not (sex == 0 and juel_id in MALE_HIDDEN_STATUS)
    ]


def talent_heading(character_id: int) -> list[str]:
    """
    构造角色素质区顶部的职业、种族、势力与出身地四行文本。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    list[str] -- 按职业、种族、势力、出身地顺序排列的四条展示文本
    """
    character_data = identity.of(character_id)
    profession = game_config.config_profession[character_data.profession].name
    race = game_config.config_race[character_data.race].name
    birthplace = game_config.config_birthplace[
        int(relations.birthplace(character_id))
    ].name
    nation = game_config.config_nation[int(relations.nation(character_id))].name
    return [
        _(" 职业    ：[{profession_text}]\n").format(
            profession_text=profession
        ),
        _(" 种族    ：[{race_text}]\n").format(race_text=race),
        _(" 势力    ：[{nation_text}]\n").format(nation_text=nation),
        _(" 出身地  ：[{birthplace_text}]\n").format(
            birthplace_text=birthplace
        ),
    ]


def talent_sections(
    character_id: int,
) -> list[tuple[str, list[tuple[str, str]]]]:
    """
    按素质分类整理角色已拥有的素质标签与说明文本。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    list[tuple[str, list[tuple[str, str]]]] -- 各分类标题及已拥有素质的 (展示标签, 说明) 列表
    """
    owned = abilities.talent(character_id)
    sections = []
    for talent_type, ids in game_config.config_talent_type_data.items():
        name = game_config.config_talent_type[talent_type].name
        label = f" {name}  ：" if talent_type == 0 else f" {name}："
        talents = [
            (
                f"[{game_config.config_talent[i].name}] ",
                game_config.config_talent[i].info,
            )
            for i in ids
            if owned[i]
        ]
        sections.append((label, talents))
    return sections


def daily_text(character_id: int) -> str:
    """
    构造角色当前工作、今日三时段安排与居住房间的日程文本。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    str -- 角色日程与居住房间展示文本
    """
    work_type = chara_life.work_type(character_id)
    plans = [
        game_config.config_entertainment[i].name
        for i in chara_life.entertainment_type(character_id)
    ]
    text = _("当前工作：{0}     ").format(
        game_config.config_work_type[work_type].name
    )
    if game_time.judge_work_today(character_id) and work_type:
        text += _(" 今日上午：工作    今日下午：工作    今日晚上：{0}").format(
            plans[2]
        )
    else:
        text += _(" 今日上午：{0}    今日下午：{1}    今日晚上：{2}").format(
            plans[0], plans[1], plans[2]
        )
    room = chara_life.dormitory(character_id).split(os.sep)[-1]
    return text + _("\n居住房间：{0}").format(room)


def visitor_text(character_id: int) -> str:
    """
    构造访客的留下意愿、离开时间与居住房间展示文本。
    Keyword arguments:
    character_id -- int，目标访客角色编号
    Return arguments:
    str -- 访客状态展示文本
    """
    stay = instuct_judege.calculation_instuct_judege(
        0, character_id, _("访客留下")
    )[2]
    stay_text = next(
        data.name
        for data in game_config.config_visitor_stay_attitude.values()
        if stay < data.rate
    )
    leave = game_time.get_date_until_day(visitor.visitors()[character_id])
    room = chara_life.dormitory(character_id).split(os.sep)[-1]
    text = _("留下意愿：{0}     ").format(stay_text)
    text += _("离开时间：{0}     ").format(leave)
    return text + _("居住房间：{0}").format(room)


def scene_others() -> list[int]:
    """
    获取当前与主角同处一场景且不含主角的角色编号列表。
    Keyword arguments:
    无
    Return arguments:
    list[int] -- 同场景其他角色编号列表
    """
    path = map_handle.get_map_system_path_str_for_list(activity.position(0))
    others = list(scene_state.occupants(path))
    others.remove(0)
    return others


def previous_in_scene(current: int, others: list[int]) -> int:
    """
    在角色列表与主角编号 0 之间向前循环步进一位。
    Keyword arguments:
    current -- int，当前查看的角色编号
    others -- list[int]，参与切换的非主角角色编号列表
    Return arguments:
    int -- 切换后的角色编号，列表为空或当前编号不在其中时返回原值
    """
    if not others:
        return current
    if not current:
        return others[-1]
    if current not in others:
        return current
    index = others.index(current)
    return others[index - 1] if index else 0


def next_in_scene(current: int, others: list[int]) -> int:
    """
    在角色列表与主角编号 0 之间向后循环步进一位。
    Keyword arguments:
    current -- int，当前查看的角色编号
    others -- list[int]，参与切换的非主角角色编号列表
    Return arguments:
    int -- 切换后的角色编号，列表为空或当前编号不在其中时返回原值
    """
    if not others:
        return current
    if not current:
        return others[0]
    if current not in others:
        return current
    index = others.index(current)
    return 0 if index == len(others) - 1 else others[index + 1]
