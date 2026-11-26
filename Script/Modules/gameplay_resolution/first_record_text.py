"""
履历文本服务（first_record_text）
=================================
构建六个履历分组的展示文本。本模块不导入 Script.UI 与 Script.Settle。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from types import FunctionType
from Script.Core import game_type, get_text
from Script.Config import game_config
from Script.Design import attr_text, game_time
from Script.Modules.gameplay_resolution import hypnosis_service
from Script.Modules.domains import identity

if TYPE_CHECKING:
    import datetime

_: FunctionType = get_text._
""" 文本翻译函数。 """

GROUP_NAMES = [
    _("部位初体验"),
    _("初次被射精"),
    _("初次绝顶履历"),
    _("陷落与刻印履历"),
    _("H模式初体验"),
    _("特殊履历"),
]
""" 履历面板的6个履历分组名（初吻条目并入部位初体验组） """

_PART_SEX_NAME_DICT = {
    0: _("发交"),
    1: _("脸交"),
    2: _("口交"),
    3: _("乳交"),
    4: _("腋交"),
    5: _("手交"),
    6: _("V性交"),
    7: _("子宫性交"),
    8: _("A性交"),
    9: _("U性交"),
    10: _("腿交"),
    11: _("足交"),
    12: _("尾交"),
    13: _("兽角蹭"),
    14: _("兽耳蹭"),
    15: _("深喉"),
}
""" 部位交类型编号到交型名的映射（同h_state.insert_position的身体部位编号） """

_PART_SEX_VIRGIN_NAME_DICT = {
    6: _("处女"),
    7: _("子宫处女"),
    8: _("后庭处女"),
    9: _("尿道处女"),
}
""" 四类插入部位对应的处女名（破处条目沿用肉体情况页原句式） """

_ITEM_NAME_DICT = {
    0: _("手指"),
    1: _("振动棒"),
    2: _("采尿器"),
}
""" 部位交道具编号到道具名的映射 """

_MARK_TYPE_LIST = [
    ("happy", 13, 3),
    ("yield", 14, 3),
    ("pain", 15, 3),
    ("time", 16, 3),
    ("terror", 17, 3),
    ("hate", 18, 3),
    ("unconscious", 19, 6),
]
""" 刻印类型列表 [(二段行为id前缀, 刻印能力id, 最大等级)] """

_ORGASM_STATE_ID_LIST = [0, 1, 2, 4, 5, 6, 7, 21, 22, 23]
""" 绝顶履历遍历的快感部位id列表（NPC专用面板，排除3阴茎） """


def _format_time(now_time: datetime.datetime | None) -> str:
    """
    格式化履历时间文本（切掉"时间:"前缀的全库惯例，对异常时间数据做防御）
    Keyword arguments:
    now_time -- datetime时间\n
    Return arguments:
    str -- 格式化后的时间文本，无法解析时为"未知时间"
    """
    try:
        return game_time.get_date_until_day(now_time)[3:]
    except Exception:
        return _("未知时间")


def _format_place(place: list[str]) -> str:
    """
    格式化履历地点文本（对旧数据缺失地点做防御）
    Keyword arguments:
    place -- 场景路径列表\n
    Return arguments:
    str -- 场景路径文本，无法解析时为"未知地点"
    """
    try:
        return attr_text.get_scene_path_text(place)
    except KeyError:
        return _("未知地点")


def _get_character_name(character_id: int) -> str:
    """
    获取履历中对象角色的名字
    Keyword arguments:
    character_id -- 角色id\n
    Return arguments:
    str -- 角色名，查不到时为空串
    """
    if identity.exists(character_id):
        return identity.of(character_id).name
    return ""


def _build_part_sex_text(first_record: game_type.FIRST_RECORD) -> str:
    """
    构建部位初体验分组文本（初吻条目+各部位交条目；V/A/U/W破处条目沿用肉体情况页原句式，其余用统一简句式；未记录的条目不显示）
    Keyword arguments:
    first_record -- FIRST_RECORD实例（当前记录或历史周目快照）\n
    Return arguments:
    str -- 分组文本
    """
    now_text = ""
    first_kiss_id = getattr(first_record, "first_kiss_id", -1)
    if first_kiss_id != -1:
        now_text += _(
            "  初吻：于{kiss_time}在{kiss_palce}，向{character_name}博士"
        ).format(
            character_name=_get_character_name(first_kiss_id),
            kiss_time=_format_time(
                getattr(first_record, "first_kiss_time", None)
            ),
            kiss_palce=_format_place(
                getattr(first_record, "first_kiss_place", ["0"])
            ),
        )
        if getattr(first_record, "first_kiss_body_part", -1) == 1:
            now_text += _("的阴茎")
        now_text += _("献上了初吻\n")
    part_sex_dict = getattr(first_record, "first_part_sex_dict", {})
    for part_id in _PART_SEX_NAME_DICT:
        part_name = _PART_SEX_NAME_DICT[part_id]
        record = part_sex_dict.get(part_id, None)
        if record is None:
            continue
        target_name = (
            _get_character_name(record.get("id", -1))
            if record.get("id", -1) != -1
            else ""
        )
        time_text = _format_time(record.get("time", None))
        place_text = _format_place(record.get("place", ["0"]))
        posture = record.get("posture", "")
        if part_id in _PART_SEX_VIRGIN_NAME_DICT and target_name and posture:
            now_text += _(
                "  {part_name}：于{time}在{palce}，被{character_name}博士以{posture}夺走了{virgin_name}"
            ).format(
                part_name=part_name,
                time=time_text,
                palce=place_text,
                character_name=target_name,
                posture=posture,
                virgin_name=_PART_SEX_VIRGIN_NAME_DICT[part_id],
            )
        else:
            now_text += _("  {part_name}：于{time}在{palce}").format(
                part_name=part_name,
                time=time_text,
                palce=place_text,
            )
            if target_name:
                now_text += _("，与{character_name}博士初次体验").format(
                    character_name=target_name
                )
            else:
                now_text += _("初次体验")
            if posture:
                now_text += _("（姿势：{0}）").format(posture)
        item = record.get("item", -1)
        if item in _ITEM_NAME_DICT:
            now_text += _("（使用道具：{0}）").format(_ITEM_NAME_DICT[item])
        now_text += "\n"
    return now_text


def _build_shoot_body_text(first_record: game_type.FIRST_RECORD) -> str:
    """
    构建初次被射精分组文本（按BodyPart.csv全部位遍历，未记录的部位不显示）
    Keyword arguments:
    first_record -- FIRST_RECORD实例（当前记录或历史周目快照）\n
    Return arguments:
    str -- 分组文本
    """
    now_text = ""
    shoot_body_dict = getattr(first_record, "first_shoot_body_dict", {})
    for part_cid in game_config.config_body_part:
        part_name = game_config.config_body_part[part_cid].name
        record = shoot_body_dict.get(part_cid, None)
        if record is None:
            continue
        now_text += _("  {0}：于{1}在{2}\n").format(
            part_name, _format_time(record[0]), _format_place(record[1])
        )
    return now_text


def _build_orgasm_text(first_record: game_type.FIRST_RECORD) -> str:
    """
    构建初次绝顶履历分组文本（强绝顶/超强绝顶/多重绝顶三小节，无记录的小节与条目不显示）
    Keyword arguments:
    first_record -- FIRST_RECORD实例（当前记录或历史周目快照）\n
    Return arguments:
    str -- 分组文本
    """
    now_text = ""
    strong_dict = getattr(first_record, "first_strong_orgasm_dict", {})
    super_dict = getattr(first_record, "first_super_orgasm_dict", {})
    plural_dict = getattr(first_record, "first_plural_orgasm_dict", {})
    for degree_name, degree_dict in (
        (_("强绝顶"), strong_dict),
        (_("超强绝顶"), super_dict),
    ):
        if not len(degree_dict):
            continue
        now_text += _(" 【{0}】\n").format(degree_name)
        for state_id in _ORGASM_STATE_ID_LIST:
            state_name = game_config.config_character_state[state_id].name
            record = degree_dict.get(state_id, None)
            if record is None:
                continue
            now_text += _("  {0}：于{1}在{2}\n").format(
                state_name, _format_time(record[0]), _format_place(record[1])
            )
    if len(plural_dict):
        now_text += _(" 【多重绝顶】\n")
        for part_count in sorted(plural_dict):
            record = plural_dict[part_count]
            part_name_list = []
            for state_id in record[2]:
                if state_id in game_config.config_character_state:
                    part_name_list.append(
                        game_config.config_character_state[state_id].name
                    )
            now_text += _("  {0}重绝顶：于{1}在{2}，参与部位：{3}\n").format(
                part_count,
                _format_time(record[0]),
                _format_place(record[1]),
                _("、").join(part_name_list),
            )
    return now_text


def _build_fall_and_mark_text(first_record: game_type.FIRST_RECORD) -> str:
    """
    构建陷落与刻印履历分组文本（陷落素质/刻印两小节，无记录的小节与条目不显示）
    Keyword arguments:
    first_record -- FIRST_RECORD实例（当前记录或历史周目快照）\n
    Return arguments:
    str -- 分组文本
    """
    now_text = ""
    fall_dict = getattr(first_record, "fall_talent_time_dict", {})
    mark_dict = getattr(first_record, "first_mark_dict", {})
    if len(fall_dict):
        now_text += _(" 【陷落素质】\n")
        for talent_id in (201, 202, 203, 204, 211, 212, 213, 214):
            talent_name = game_config.config_talent[talent_id].name
            record = fall_dict.get(talent_id, None)
            if record is None:
                continue
            now_text += _("  {0}：于{1}在{2}获得\n").format(
                talent_name, _format_time(record[0]), _format_place(record[1])
            )
    if len(mark_dict):
        now_text += _(" 【刻印】\n")
        for mark_type, ability_id, max_level in _MARK_TYPE_LIST:
            for now_level in range(1, max_level + 1):
                mark_key = f"{mark_type}_mark_{now_level}"
                record = mark_dict.get(mark_key, None)
                if record is None:
                    continue
                mark_name = game_config.config_ability[ability_id].name
                now_text += _("  {0}{1}级：于{2}在{3}\n").format(
                    mark_name,
                    now_level,
                    _format_time(record[0]),
                    _format_place(record[1]),
                )
    return now_text


def _build_h_mode_text(first_record: game_type.FIRST_RECORD) -> str:
    """
    构建H模式初体验分组文本（固定11项：无意识7类型+群交/露出H/隐奸H/装睡H，未体验的条目不显示）
    Keyword arguments:
    first_record -- FIRST_RECORD实例（当前记录或历史周目快照）\n
    Return arguments:
    str -- 分组文本
    """
    now_text = ""
    h_mode_dict = getattr(first_record, "first_h_mode_dict", {})
    mode_list = []
    for unconscious_type in range(1, 8):
        mode_list.append(
            (
                f"unconscious_{unconscious_type}",
                _("第一次{0}H").format(
                    hypnosis_service.unconscious_list[unconscious_type]
                ),
            )
        )
    mode_list.append(("group_sex", _("第一次群交")))
    mode_list.append(("exhibitionism", _("第一次露出H")))
    mode_list.append(("hidden_sex", _("第一次隐奸H")))
    mode_list.append(("pretend_sleep", _("第一次装睡H")))
    for mode_key, mode_name in mode_list:
        record = h_mode_dict.get(mode_key, None)
        if record is None:
            continue
        now_text += _("  {0}：于{1}在{2}").format(
            mode_name, _format_time(record[0]), _format_place(record[1])
        )
        extra_data = record[2] if len(record) > 2 else ""
        if extra_data:
            if mode_key == "group_sex":
                now_text += _("（当时场景内共{0}人）").format(extra_data)
            else:
                now_text += _("（{0}）").format(extra_data)
        now_text += "\n"
    return now_text


def _build_special_record_text(first_record: game_type.FIRST_RECORD) -> str:
    """
    构建特殊履历分组文本（FirstRecordSpecial.csv配表驱动，配表加行后自动跟随；未达成的条目不显示）
    Keyword arguments:
    first_record -- FIRST_RECORD实例（当前记录或历史周目快照）\n
    Return arguments:
    str -- 分组文本
    """
    now_text = ""
    special_dict = getattr(first_record, "first_special_record_dict", {})
    for special_cid in sorted(game_config.config_first_record_special):
        special_name = game_config.config_first_record_special[special_cid].name
        record = special_dict.get(special_cid, None)
        if record is None:
            continue
        now_text += _("  {0}：于{1}在{2}").format(
            special_name, _format_time(record[0]), _format_place(record[1])
        )
        extra_data = record[2] if len(record) > 2 else ""
        if extra_data:
            now_text += _("（{0}）").format(extra_data)
        now_text += "\n"
    return now_text


_GROUP_BUILD_FUNC_LIST = [
    _build_part_sex_text,
    _build_shoot_body_text,
    _build_orgasm_text,
    _build_fall_and_mark_text,
    _build_h_mode_text,
    _build_special_record_text,
]
""" 6个分组的文本构建函数列表（与GROUP_NAMES顺序一致） """


def build_group_text(
    first_record: game_type.FIRST_RECORD, group_index: int
) -> str:
    """
    构建指定分组的履历文本（当前周目与历史周目块共用，未记录的条目一律不显示）
    Keyword arguments:
    first_record -- FIRST_RECORD实例（当前记录或历史周目快照）\n
    group_index -- 分组序号(0~5)\n
    Return arguments:
    str -- 分组文本
    """
    return _GROUP_BUILD_FUNC_LIST[group_index](first_record)
