"""
体检报告（physical_exam_report）
================================
根据角色基础档案、能力与素质、已完成检查集合和性爱履历拼接纯文本体检报告。
本模块不导入 Script.UI 与 Script.Settle。
"""

from collections.abc import Collection
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import attr_text, game_time, handle_premise
from Script.Modules.domains import abilities, first_record, hypnosis
from Script.Modules.domains import identity, pregnancy, relations

_: FunctionType = get_text._
""" 本地化翻译函数。 """
PREGNANCY_TALENTS = (0, 20, 21, 22, 23, 24, 26, 27, 35)
""" 受孕适应性行中按顺序展示的妊娠相关素质编号元组。 """
PREGNANT_TALENTS = (20, 21, 22, 23, 24)
""" 表示已怀孕状态的素质编号元组，持有任一项时隐藏受精概率。 """
HYPNOSIS_TALENTS = (73, 72, 71)
""" 按优先顺序检查的催眠素质编号元组。 """
BODY_PART_TALENTS = tuple(range(111, 133))
""" 性器行中展示的身体部位素质编号元组（111 至 132）。 """
SPECIAL_TALENTS = (*range(61, 65), *range(151, 180))
""" 特殊体质行中展示的素质编号元组（61 至 64 及 151 至 179）。 """


def _levels() -> dict[int, str]:
    """
    构造 0 至 8 级能力评价对应的本地化等级文本字典。
    Keyword arguments:
    无
    Return arguments:
    dict[int, str] -- 能力等级编号到评价文本的映射
    """
    return {
        0: _("缺陷"),
        1: _("普通"),
        2: _("普通"),
        3: _("标准"),
        4: _("标准"),
        5: _("标准"),
        6: _("优良"),
        7: _("优良"),
        8: _("卓越"),
    }


def _headings() -> dict[int, str]:
    """
    构造体检报告各条目的本地化标题字典。
    Keyword arguments:
    无
    Return arguments:
    dict[int, str] -- 条目索引到标题文本的映射
    """
    return {
        0: _("【基础敏感强度】"),
        1: _("【扩张耐受】"),
        2: _("【SM耐受】"),
        3: _("【受孕适应性】"),
        4: _("【催眠程度】"),
        5: _("【性器】"),
        6: _("【特殊体质】"),
        11: _("【初吻】"),
        12: _("【处女】"),
        13: _("【肛门处女】"),
    }


def _check_abilities() -> dict[str, tuple[int, str]]:
    """
    构造检查行为编号到对应能力编号与报告标题的本地化映射。
    Keyword arguments:
    无
    Return arguments:
    dict[str, tuple[int, str]] -- 检查行为编号到能力编号与标题元组的映射
    """
    return {
        "examine_sucking_and_swallowing": (71, _("【舌部机动】")),
        "examine_breast": (0, _("【胸部敏感】")),
        "examine_breast_clamping": (73, _("【乳压强度】")),
        "examine_cilitoris": (2, _("【阴蒂敏感】")),
        "examine_hands_flexibility": (70, _("【手部机动】")),
        "examine_foots_flexibility": (72, _("【足部机动】")),
        "examine_vulva_and_shape": (4, _("【阴道敏感】")),
        "examine_orifice": (7, _("【子宫敏感】")),
        "examine_vagina_firmness": (74, _("【阴道技巧】")),
        "examine_anus": (5, _("【肛门敏感】")),
        "examine_intestine_firmness": (75, _("【肛门技巧】")),
        "examine_urination_status": (6, _("【尿道敏感】")),
        "examine_tail_flexibility": (30, _("【尾部机动】")),
        "examine_tentacle_flexibility": (30, _("【触手机动】")),
    }


def _talent_names(cid: int, talent_ids: Collection[int]) -> str:
    """
    拼接角色在给定素质编号中已持有的素质名称，以一个空格开头，每个名称后接一个空格。
    Keyword arguments:
    cid -- int，目标角色编号
    talent_ids -- Collection[int]，待检查的素质编号集合
    Return arguments:
    str -- 以空格分隔的素质名称文本
    """
    talent = abilities.talent(cid)
    text = " "
    for talent_id in talent_ids:
        if talent_id in talent and talent[talent_id]:
            text += game_config.config_talent[talent_id].name + " "
    return text


def _profile(cid: int) -> str:
    """
    生成报告的基础档案段，包含代号、性别、性交与无意识性交经验、出身地、种族与感染情况。
    感染情况行读取玩家当前查看对象而非 cid。
    Keyword arguments:
    cid -- int，受检角色编号
    Return arguments:
    str -- 基础档案段文本
    """
    exp = abilities.experience(cid)
    data = identity.of(cid)
    sex_exp = sum(exp[exp_id] for exp_id in (61, 62, 63, 64))
    text = "\n" + _("基础档案：\n")
    text += _(" 【代号】") + data.name + "\n"
    text += _(" 【性别】") + game_config.config_sex_tem[data.sex].name + "\n"
    text += _(" 【性交经验】") + str(sex_exp) + _("次\n")
    text += _(" 【无意识性交经验】") + str(exp[79]) + _("次\n")
    birthplace = game_config.config_birthplace[relations.birthplace(cid)]
    text += _(" 【出身地】") + birthplace.name + "\n"
    text += _(" 【种族】") + game_config.config_race[data.race].name + "\n"
    text += _(" 【矿石病感染情况】\n")
    if handle_premise.handle_target_is_patient(0):
        text += _("  参照医学检测报告，确认为感染者。\n")
    else:
        text += _("  参照医学检测报告，确认为非感染者。\n")
    return text


def _fertility(cid: int) -> str:
    """
    生成受孕适应性行文本，包含妊娠相关素质、未怀孕时的受精概率以及已生育子女名单。
    Keyword arguments:
    cid -- int，受检角色编号
    Return arguments:
    str -- 受孕适应性描述文本
    """
    talent = abilities.talent(cid)
    names = " "
    any_flag, pregnant = False, False
    for talent_id in PREGNANCY_TALENTS:
        if talent[talent_id]:
            any_flag = True
            names += game_config.config_talent[talent_id].name + " "
            if talent_id in PREGNANT_TALENTS:
                pregnant = True
    text = _("{0}").format(names) if any_flag else ""
    if not pregnant:
        text += _("当前受精概率{0}%").format(
            pregnancy.of(cid).fertilization_rate
        )
    children = relations.child_id_list(cid)
    if len(children) > 0:
        text += _(" 已经生育了{0}个孩子，分别是：{1}").format(
            len(children), "、".join([identity.of(c).name for c in children])
        )
    return text


def _hypnosis(cid: int) -> str:
    """
    生成催眠程度行文本，持有催眠素质时优先附带首个命中的素质名称。
    Keyword arguments:
    cid -- int，受检角色编号
    Return arguments:
    str -- 催眠程度描述文本
    """
    talent = abilities.talent(cid)
    degree = hypnosis.degree(cid)
    for talent_id in HYPNOSIS_TALENTS:
        if talent[talent_id]:
            name = " " + game_config.config_talent[talent_id].name + " "
            return _("{0}（{1}%）\n").format(name, degree)
    return _("{0}%\n").format(degree)


def _exam(cid: int, done: Collection[str]) -> str:
    """
    生成综合体检测试段，包含基础敏感、扩张与 SM 耐受、受孕适应性、催眠程度、已完成检查项能力评价、性器与特殊体质。
    Keyword arguments:
    cid -- int，受检角色编号
    done -- Collection[str]，已完成的检查行为编号集合
    Return arguments:
    str -- 综合体检测试段文本
    """
    ability = abilities.ability(cid)
    levels = _levels()
    headings = _headings()
    text = _("\n综合体检测试：\n")
    text += f" {headings[0]}{levels[ability[1]]}\n"
    resist = int(sum(ability[i] for i in (9, 10, 11, 12)) // 4)
    text += f" {headings[1]}{levels[resist]}\n"
    sm = max(0, *(ability[i] for i in (35, 36)))
    text += f" {headings[2]}{levels[sm]}\n"
    text += " " + headings[3] + _fertility(cid) + "\n"
    text += " " + headings[4] + _hypnosis(cid)
    for cmd_id, (ability_id, name) in _check_abilities().items():
        if cmd_id in done:
            text += f" {name}{levels[ability[ability_id]]}\n"
    text += f" {headings[5]}{_talent_names(cid, BODY_PART_TALENTS)}\n"
    special = _talent_names(cid, SPECIAL_TALENTS)
    if special == " ":
        special = _("无")
    text += f" {headings[6]}{special}\n"
    return text


def _first_kiss(cid: int) -> str:
    """
    生成初吻履历文本，保有初吻或无初吻对象记录时返回对应结果，否则格式化时间、地点、对象与部位说明。
    Keyword arguments:
    cid -- int，受检角色编号
    Return arguments:
    str -- 初吻履历文本
    """
    record = first_record.view(cid)
    if abilities.talent(cid)[4]:
        return _("保有初吻")
    if record.first_kiss_id == -1:
        return ""
    kiss_time = record.first_kiss_time
    text = _("于{kiss_time}在{kiss_palce}，向{character_name}博士").format(
        character_name=identity.of(record.first_kiss_id).name,
        kiss_time=game_time.get_month_text(kiss_time)
        + _("月")
        + str(kiss_time.day)
        + _("日"),
        kiss_palce=attr_text.get_scene_path_text(record.first_kiss_place),
    )
    if record.first_kiss_body_part == 1:
        text += _("的阴茎")
    return text + _("献上了初吻")


def _first_sex(
    cid: int, talent_id: int, part: int, kept: str, lost: str
) -> str:
    """
    生成指定部位的处女履历文本，保有对应素质时返回保有文本，无记录时返回空文本，否则格式化失身记录。
    Keyword arguments:
    cid -- int，受检角色编号
    talent_id -- int，对应处女素质编号
    part -- int，部位初体验字典的部位键
    kept -- str，保有状态展示文本
    lost -- str，失身记录格式化模板
    Return arguments:
    str -- 该部位的处女履历文本
    """
    if abilities.talent(cid)[talent_id]:
        return kept
    record = first_record.view(cid).first_part_sex_dict.get(part, None)
    if record is None or record["id"] == -1:
        return ""
    return lost.format(
        character_name=identity.of(record["id"]).name,
        time=game_time.get_date_until_day(record["time"])[3:],
        palce=attr_text.get_scene_path_text(record["place"]),
        posture=record["posture"],
    )


def _history(cid: int) -> str:
    """
    生成性爱履历段，依次汇总初吻、V 处女（键 6）与 A 处女（键 8）记录。
    Keyword arguments:
    cid -- int，受检角色编号
    Return arguments:
    str -- 性爱履历段文本
    """
    headings = _headings()
    text = _("\n性爱履历：\n")
    text += f" {headings[11]}{_first_kiss(cid)}\n"
    virgin = _first_sex(
        cid,
        0,
        6,
        _("保有处女"),
        _("于{time}在{palce}，被{character_name}博士以{posture}夺走了处女"),
    )
    text += f" {headings[12]}{virgin}\n"
    anal = _first_sex(
        cid,
        1,
        8,
        _("保有后庭处女"),
        _("于{time}在{palce}，被{character_name}博士以{posture}夺走了A处女"),
    )
    text += f" {headings[13]}{anal}\n"
    return text


def report_text(cid: int, done: Collection[str], examiner: str) -> str:
    """
    汇总基础档案、综合体检测试、性爱履历、检查人与检查日期，生成只读体检报告文本。
    Keyword arguments:
    cid -- int，受检角色编号
    done -- Collection[str]，已完成的检查行为编号集合
    examiner -- str，检查人名称
    Return arguments:
    str -- 完整的体检报告文本
    """
    text = _profile(cid) + _exam(cid, done) + _history(cid)
    text += _("\n检查人：Dr.{0}\n").format(examiner)
    text += _("检查日期：{0}\n").format(game_time.get_date_until_day()[3:])
    return text
