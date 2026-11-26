"""
怀孕总览服务（pregnancy_overview_service）
==========================================
提供怀孕总览的阶段判定、关键时间文本、总览列表数据、页签列表与异常女儿排查文案及移除入口。
本模块不导入 Script.UI 与 Script.Settle。
"""

import datetime
from types import FunctionType

from Script.Core import get_text
from Script.Design import game_time, handle_premise
from Script.Modules.domains import abilities, identity, pregnancy, relations
from Script.Modules.domains import roster
from Script.System.Education_System import education_constant
from Script.System.Pregnancy_System import egg_handle, pregnancy_constant
from Script.System.Pregnancy_System import pregnancy_handle, soft_egg_handle

_: FunctionType = get_text._
""" 本地化翻译函数。 """


def get_chara_pregnancy_stage(character_id: int) -> int:
    """
    按受精到育儿的时间顺序判定角色当前怀孕阶段，同时满足多项时取最靠后者。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    int -- 阶段枚举值，不在任何阶段时返回 0
    """
    now_stage = pregnancy_constant.STAGE_NONE
    if handle_premise.handle_fertilization_1(character_id):
        now_stage = pregnancy_constant.STAGE_FERTILIZATION
    if len(egg_handle.get_unidentified_eggs(character_id, exclude_held=False)):
        now_stage = pregnancy_constant.STAGE_EGG_WAIT
    if len(soft_egg_handle.get_mother_soft_eggs(character_id)):
        now_stage = pregnancy_constant.STAGE_SOFT_EGG_WAIT
    if handle_premise.handle_pregnancy_1(character_id):
        now_stage = pregnancy_constant.STAGE_PREGNANCY
    if len(egg_handle.get_hatching_eggs(character_id)):
        now_stage = pregnancy_constant.STAGE_HATCHING
    if handle_premise.handle_parturient_1(character_id):
        now_stage = pregnancy_constant.STAGE_PARTURIENT
    if handle_premise.handle_postpartum_1(character_id):
        now_stage = pregnancy_constant.STAGE_POSTPARTUM
    if handle_premise.handle_rearing_1(character_id):
        now_stage = pregnancy_constant.STAGE_REARING
    return now_stage


def due_date_text(
    total_day: int, acceleration_day: float, start_time: datetime.datetime
) -> str:
    """
    计算预计日期的四季月日文本，扣除加速药的整天数并在日期已过时显示当天。
    Keyword arguments:
    total_day -- int，基准阶段总天数
    acceleration_day -- float，加速药累计加速天数（取整扣除）
    start_time -- datetime.datetime，阶段起始时间
    Return arguments:
    str -- 格式化后的预计月日文本
    """
    due_time = max(
        game_time.get_predict_date(
            total_day - int(acceleration_day), start_time
        ),
        game_time.now(),
    )
    return pregnancy_constant.format_season_date(due_time)


def get_fetus_count_text(character_id: int) -> str:
    """
    返回胎生阶段文案末尾的胎数后缀，单胎返回空串。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    str -- 胎数后缀文本（同卵双胞胎或 N 胞胎），单胎时为空串
    """
    preg = pregnancy.of(character_id)
    fetus_count = preg.fetus_count
    if fetus_count < 2:
        return ""
    if preg.identical_twins:
        return _("（同卵双胞胎）")
    return _("（{0}胞胎）").format(fetus_count)


def fetus_due_text(character_id: int, total_day: int, message: str) -> str:
    """
    将受精日期与预计日期填入文案模板，并拼接胎数后缀。
    Keyword arguments:
    character_id -- int，角色编号
    total_day -- int，受精到目标阶段的基准天数
    message -- str，含受精日期与预计日期两个占位符的文案模板
    Return arguments:
    str -- 填充日期并拼接胎数后缀后的说明文本
    """
    preg = pregnancy.of(character_id)
    return message.format(
        pregnancy_constant.format_season_date(preg.fertilization_time),
        due_date_text(
            total_day, preg.acceleration_days, preg.fertilization_time
        ),
    ) + get_fetus_count_text(character_id)


def soft_egg_text(egg_data: dict) -> str:
    """
    构造单个待受精卵块的说明文本，列出所在地点、精液量与距受精判定的剩余分钟数。
    Keyword arguments:
    egg_data -- dict，单个体外卵块数据字典
    Return arguments:
    str -- 单枚卵块的地点、精液量与判定倒计时文本，无剩余分钟时显示即将判定
    """
    scene_name = soft_egg_handle.get_soft_egg_scene_name(egg_data)
    semen = int(egg_data["semen_count"])
    remain_minute = soft_egg_handle.get_soft_egg_remain_minute(egg_data)
    if remain_minute > 0:
        return _("{0}的卵块（{1}ml，{2}分钟后判定）").format(
            scene_name, semen, remain_minute
        )
    return _("{0}的卵块（{1}ml，即将判定）").format(scene_name, semen)


def rearing_text(character_id: int) -> str:
    """
    构造育儿阶段的关键时间文本，列出每名婴儿的预计长大日期。
    Keyword arguments:
    character_id -- int，母亲角色编号
    Return arguments:
    str -- 育儿室照顾列表文本，名下无婴儿时返回「育儿中」
    """
    baby_text_list = []
    for child_id in pregnancy_handle.get_baby_id_list(character_id):
        child_preg = pregnancy.of(child_id)
        grow_text = due_date_text(
            pregnancy_constant.REARING_COMPLETE_DAY,
            child_preg.growth_acceleration_days,
            child_preg.born_time,
        )
        baby_text_list.append(
            _("{0}（预计{1}长大）").format(
                identity.of(child_id).name, grow_text
            )
        )
    if len(baby_text_list):
        return _("正在育儿室照顾{0}").format("、".join(baby_text_list))
    return _("育儿中")


def get_stage_info_text(character_id: int, now_stage: int) -> str:
    """
    按角色当前怀孕阶段返回对应的关键时间说明文本。
    Keyword arguments:
    character_id -- int，角色编号
    now_stage -- int，阶段枚举值
    Return arguments:
    str -- 当前阶段的关键时间说明，无阶段时为空串
    """
    if now_stage == pregnancy_constant.STAGE_FERTILIZATION:
        return fetus_due_text(
            character_id,
            pregnancy_constant.PREGNANCY_DAY,
            _("受精于{0}，预计{1}妊娠"),
        )
    if now_stage == pregnancy_constant.STAGE_PREGNANCY:
        return fetus_due_text(
            character_id,
            pregnancy_constant.PARTURIENT_DAY,
            _("受精于{0}，预计{1}临盆"),
        )
    if now_stage == pregnancy_constant.STAGE_EGG_WAIT:
        egg_count = len(
            egg_handle.get_unidentified_eggs(character_id, exclude_held=False)
        )
        return _("{0}枚卵待鉴定").format(egg_count)
    if now_stage == pregnancy_constant.STAGE_SOFT_EGG_WAIT:
        egg_text_list = [
            soft_egg_text(egg_data)
            for egg_data in soft_egg_handle.get_mother_soft_eggs(
                character_id
            ).values()
        ]
        return _("待受精卵块：{0}").format("、".join(egg_text_list))
    if now_stage == pregnancy_constant.STAGE_HATCHING:
        first_egg = list(egg_handle.get_hatching_eggs(character_id).values())[0]
        return _("孵化第{0}天，预计{1}破壳").format(
            egg_handle.get_hatch_day(first_egg),
            due_date_text(
                pregnancy_constant.HATCH_TOTAL_DAY,
                first_egg.get("acceleration_days", 0),
                first_egg["lay_time"],
            ),
        )
    if now_stage == pregnancy_constant.STAGE_PARTURIENT:
        return _("已在住院区待产，预计近日生产") + get_fetus_count_text(
            character_id
        )
    if now_stage == pregnancy_constant.STAGE_POSTPARTUM:
        return _("生产完毕，正在住院区休养")
    if now_stage == pregnancy_constant.STAGE_REARING:
        return rearing_text(character_id)
    return ""


def overview_rows(
    filter_type: int, sort_type: int
) -> list[tuple[int, str, str]]:
    """
    生成总览页的干员阶段行列表，排序与筛选参数由面板传入，因为本服务不读取界面状态。
    Keyword arguments:
    filter_type -- int，阶段筛选枚举值，为 0 时不过滤
    sort_type -- int，排序方向，为 0 时按阶段降序，否则按阶段升序
    Return arguments:
    list[tuple[int, str, str]] -- 每项为（角色编号，姓名，阶段与关键时间行文本）
    """
    stage_rows = []
    for character_id in roster.active_sorted():
        if character_id == 0:
            continue
        now_stage = get_chara_pregnancy_stage(character_id)
        if now_stage == pregnancy_constant.STAGE_NONE:
            continue
        if filter_type and now_stage != filter_type:
            continue
        stage_rows.append((character_id, now_stage))
    stage_rows.sort(key=lambda row: row[1], reverse=sort_type == 0)
    return [
        (
            character_id,
            identity.of(character_id).name,
            f"　{pregnancy_constant.STAGE_NAME_LIST[now_stage]}　　"
            + get_stage_info_text(character_id, now_stage),
        )
        for character_id, now_stage in stage_rows
    ]


def sort_button_text(sort_type: int) -> str:
    """
    按排序方向返回总览页排序按钮的显示文本。
    Keyword arguments:
    sort_type -- int，排序方向，为 0 时为降序，否则为升序
    Return arguments:
    str -- 排序按钮文本（[按阶段降序▼] 或 [按阶段升序▲]）
    """
    if sort_type == 0:
        return _("[按阶段降序▼]")
    return _("[按阶段升序▲]")


def page_names() -> list[str]:
    """
    返回当前应显示的页签名称列表。
    仅存在疑似误入女儿时附带「异常女儿排查」页签，以免正常存档看到该入口。
    Return arguments:
    list[str] -- 按显示顺序排列的页签名称列表
    """
    names = [_("总览"), _("生育谱系图")]
    if pregnancy_handle.get_suspected_abnormal_daughter_list():
        names.append(_("异常女儿排查"))
    return names


def live_id(character_id: int) -> int:
    """
    检查角色编号是否仍存在于当前存档。
    Keyword arguments:
    character_id -- int，待检查的角色编号
    Return arguments:
    int -- 角色存在时返回原编号，否则返回 0
    """
    if identity.exists(character_id):
        return character_id
    return 0


def remove_confirm_text(character_id: int) -> str:
    """
    构造移除疑似误入女儿前的二次确认提示文本。
    Keyword arguments:
    character_id -- int，待移除女儿的角色编号
    Return arguments:
    str -- 含女儿姓名与编号的确认提示文本
    """
    return _(
        "\n　确定要从本存档彻底移除女儿「{0}」（id:{1}）吗？\n　此操作不可撤销。\n"
    ).format(identity.of(character_id).name, character_id)


def abnormal_count_text() -> str:
    """
    构造本存档博士女儿总数、在册数与疑似误入数的统计文本。
    Return arguments:
    str -- 博士女儿分类计数提示文本
    """
    all_count = len(pregnancy_handle.get_all_player_daughter_id_list())
    abnormal_count = len(
        pregnancy_handle.get_suspected_abnormal_daughter_list()
    )
    return _(
        "　本存档共有 {0} 名博士女儿，其中 {1} 名在册（正常），{2} 名疑似误入：\n"
    ).format(all_count, all_count - abnormal_count, abnormal_count)


def growth_stage_name(character_id: int) -> str:
    """
    按婴儿至少女的成长素质顺序返回角色当前成长阶段名称。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    str -- 匹配的成长阶段名称，无成长素质时返回「成年」
    """
    talent = abilities.talent(character_id)
    for talent_id in education_constant.CHILD_TALENT_ID_LIST:
        if talent.get(talent_id):
            return education_constant.STAGE_TALENT_NAME[talent_id]
    return _("成年")


def abnormal_rows() -> list[tuple[int, str]]:
    """
    生成异常女儿排查页的疑似误入女儿行列表。
    Return arguments:
    list[tuple[int, str]] -- 每项为（角色编号，含姓名、编号、母亲名与成长阶段的行文本）
    """
    rows = []
    for character_id in pregnancy_handle.get_suspected_abnormal_daughter_list():
        mother = identity.get(relations.mother_id(character_id))
        mother_name = mother.name if mother is not None else _("未知")
        text = _("　{0}（id:{1}）　母亲：{2}　成长阶段：{3}\n").format(
            identity.of(character_id).name,
            character_id,
            mother_name,
            growth_stage_name(character_id),
        )
        rows.append((character_id, text))
    return rows


def remove_abnormal(character_id: int, tree_center_id: int) -> int:
    """
    调用妊娠模块移除疑似误入女儿，并在移除对象为当前谱系图中心时将中心编号重置为 0。
    Keyword arguments:
    character_id -- int，待移除的角色编号
    tree_center_id -- int，当前谱系图中心角色编号
    Return arguments:
    int -- 更新后的谱系图中心角色编号
    """
    if (
        pregnancy_handle.remove_abnormal_daughter(character_id)
        and tree_center_id == character_id
    ):
        return 0
    return tree_center_id
