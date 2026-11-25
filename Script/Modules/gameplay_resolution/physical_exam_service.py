"""
体检服务（physical_exam_service）
=================================
提供身体检查项目列表、检查次数上限、检查与报告记录、体检结束结算、体检日程配置与候选名单管理。
本模块不导入 Script.UI 与 Script.Settle。
"""

from collections.abc import Collection
from dataclasses import dataclass
from types import FunctionType, MappingProxyType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import handle_premise
from Script.Modules.domains import abilities, achievement, action_info
from Script.Modules.domains import physical_exam, roster
from Script.Modules.gameplay_resolution import achievement_service

_: FunctionType = get_text._
""" 本地化翻译函数。 """
MEDICINE = 46
""" 医术能力编号（能力编号 46）。 """
DAILY_COUNT = 6
""" 每次抽取体检人数对应的体检设置编号（设置编号 6）。 """
PREREQUISITE = MappingProxyType(
    {
        "examine_hair_smoothness": "examine_hair",
        "examine_sucking_and_swallowing": "examine_oral",
        "examine_armpit_clamping": "examine_armpit",
        "examine_nipple_and_areola": "examine_breast",
        "examine_breast_clamping": "examine_breast",
        "examine_hands_flexibility": "examine_hands",
        "examine_foots_flexibility": "examine_foot",
        "examine_vagina_and_folds": "examine_vulva_and_shape",
        "examine_hymen": "examine_vagina_and_folds",
        "examine_orifice": "examine_vagina_and_folds",
        "examine_vagina_firmness": "examine_vagina_and_folds",
        "examine_intestine_firmness": "examine_anus",
        "examine_urination_status": "examine_urethra",
        "examine_urethra_firmness": "examine_urethra",
        "examine_tail_flexibility": "examine_tail",
        "examine_horn_sensitivity": "examine_horn",
        "examine_ears_sensitivity": "examine_ears",
        "examine_wing_flexibility": "examine_wing",
        "examine_ring_sensitivity": "examine_ring",
        "examine_tentacle_flexibility": "examine_tentacle",
    }
)
""" 后续检查行为编号到所需前置检查行为编号的只读映射。 """
ORGAN_TALENT = MappingProxyType(
    {
        "examine_tail": 113,
        "examine_tail_flexibility": 113,
        "examine_horn": 112,
        "examine_ears": 111,
        "examine_wing": 115,
        "examine_ring": 114,
        "examine_tentacle": 116,
    }
)
""" 特殊身体部位检查行为编号到所需素质编号的只读映射。 """


@dataclass(frozen=True, slots=True)
class CheckRow:
    """身体检查列表中单条检查项目的展示数据。"""

    number: int
    """ 按配置顺序统计的检查项序号，统计时包含隐藏项。 """
    behavior_id: str
    """ 检查行为编号。 """
    label: str
    """ 带序号前缀与状态说明的展示文本。 """
    enabled: bool
    """ 当前是否允许选择该检查项。 """
    harassment: bool
    """ 行为标签含「测试」时为 True，供界面区分样式与骚扰判定。 """


@dataclass(frozen=True, slots=True)
class SettingRow:
    """体检日程设置列表中单条设置的展示数据。"""

    setting_id: int
    """ 体检设置编号。 """
    name: str
    """ 体检设置名称。 """
    option: str
    """ 当前选中选项的文本。 """
    option_count: int
    """ 该设置的可选条目总数。 """
    roster_size: int | None
    """ 设置 4 选中手动名单（值 2）时的已选人数，其他情况为 None。 """
    day_count: int | None
    """ 设置 7 选中手动体检日（值 1）时的已选天数，其他情况为 None。 """


def done_checks(examined_id: int) -> set[str]:
    """
    查询角色当前已完成的身体检查行为集合，优先读取今日已完成记录，否则读取进行中记录。
    Keyword arguments:
    examined_id -- int，受检角色编号
    Return arguments:
    set[str] -- 已完成的检查行为编号集合，无记录时为空集合
    """
    today = physical_exam.checks(physical_exam.TODAY)
    if examined_id in today:
        return today[examined_id]
    return physical_exam.checks(physical_exam.IN_PROGRESS).get(
        examined_id, set()
    )


def check_quota(done: Collection[str]) -> tuple[int, int]:
    """
    计算已完成检查次数与玩家医术等级决定的单次体检上限。
    Keyword arguments:
    done -- Collection[str]，已完成的检查行为编号集合
    Return arguments:
    tuple[int, int] -- 已完成次数与总可用次数，总次数为玩家医术等级加 1 后乘以 4
    """
    return len(done), (abilities.ability(0)[MEDICINE] + 1) * 4


def check_rows(examined_id: int, done: Collection[str]) -> list[CheckRow]:
    """
    按配置顺序生成目标角色的可见身体检查行列表，过滤缺少前置检查或对应部位素质的项目，并标记禁用原因。
    Keyword arguments:
    examined_id -- int，受检角色编号
    done -- Collection[str]，已完成的检查行为编号集合
    Return arguments:
    list[CheckRow] -- 按配置顺序排列的可见检查项列表
    """
    talent = abilities.talent(examined_id)
    done_times, total_times = check_quota(done)
    rows = []
    count = 0
    for behavior_id, behavior_data in game_config.config_behavior.items():
        if "检查" not in behavior_data.tag:
            continue
        count += 1
        label = f"[{str(count).rjust(2,'0')}]：{behavior_data.name}"
        blocked = False
        if behavior_id in done:
            blocked = True
            label += _("(已检查)")
        prerequisite = PREREQUISITE.get(behavior_id)
        if prerequisite is not None and prerequisite not in done:
            continue
        if behavior_id == "examine_sucking_and_swallowing" and talent[4]:
            blocked = True
            label += _("(未初吻)")
        elif (
            behavior_id in ("examine_orifice", "examine_vagina_firmness")
            and talent[0]
        ):
            blocked = True
            label += _("(未破处)")
        elif behavior_id == "examine_intestine_firmness" and talent[1]:
            blocked = True
            label += _("(未破处)")
        elif behavior_id == "examine_urethra_firmness" and talent[2]:
            blocked = True
            label += _("(未破处)")
        if behavior_id == "examine_hymen" and not (
            handle_premise.handle_have_virgin(examined_id)
            or handle_premise.handle_first_sex_in_today(examined_id)
        ):
            blocked = True
            label += _("(需要是处女或者今日刚破处)")
        if (
            behavior_id in ORGAN_TALENT
            and not talent[ORGAN_TALENT[behavior_id]]
        ):
            continue
        if total_times - done_times <= 0:
            blocked = True
        rows.append(
            CheckRow(
                count,
                behavior_id,
                label,
                not blocked,
                "测试" in behavior_data.tag,
            )
        )
    return rows


def record_check(examined_id: int, behavior_id: str) -> list[int]:
    """
    登记一次进行中的身体检查，累加检查计数并结算「身体检查」成就，当日破处且执行 examine_hymen 时追加结算成就 1046。
    Keyword arguments:
    examined_id -- int，受检角色编号
    behavior_id -- str，检查行为编号
    Return arguments:
    list[int] -- 本次新达成的成就编号列表
    """
    physical_exam.record_check(examined_id, behavior_id)
    achievement.add("health_check_count", 1)
    achieved = achievement_service.settle_by_type(_("身体检查"))
    if (
        handle_premise.handle_first_sex_in_today(examined_id)
        and behavior_id == "examine_hymen"
    ):
        achieved += achievement_service.settle_by_type(_("身体检查"), 1046)
    return achieved


def finish_exam(examined_id: int, done: Collection[str]) -> None:
    """
    结束角色本次体检，在 done 非空时转入今日记录、更新周期与等待名单并清零今日体检时段，done 为空时不写入。
    Keyword arguments:
    examined_id -- int，受检角色编号
    done -- Collection[str]，本次已完成的检查行为编号集合
    Return arguments:
    None -- 无返回值
    """
    if len(done) > 0:
        physical_exam.finish(examined_id, done)
        action_info.set(examined_id, "health_check_today", 0)


def record_report(examined_id: int) -> list[int]:
    """
    将受检角色编号追加到报告查看记录列表并结算「体检报告」成就，即使该编号已在列表中仍会重复追加。
    Keyword arguments:
    examined_id -- int，受检角色编号
    Return arguments:
    list[int] -- 本次新达成的成就编号列表
    """
    achievement.append("body_report_chara_count_list", examined_id)
    return achievement_service.settle_by_type(_("体检报告"))


def setting_rows() -> list[SettingRow]:
    """
    按配置顺序生成体检日程设置行，在设置 2 为 0 时止于设置 3 之前，对尚无存储值的设置项写入 0。
    Keyword arguments:
    无
    Return arguments:
    list[SettingRow] -- 当前展示的体检日程设置行列表
    """
    rows = []
    for cid, setting_data in game_config.config_physical_exam_setting.items():
        if cid >= 3 and physical_exam.setting(2) == 0:
            break
        if cid not in physical_exam.settings():
            physical_exam.set_setting(cid, 0)
        value = physical_exam.setting(cid)
        options = game_config.config_physical_exam_setting_option[cid]
        roster_size = day_count = None
        if cid == 4 and value == 2:
            roster_size = len(physical_exam.ids(physical_exam.CHOSEN))
        elif cid == 7 and value == 1:
            day_count = len(physical_exam.week_days())
        rows.append(
            SettingRow(
                cid,
                setting_data.name,
                options[value],
                len(options),
                roster_size,
                day_count,
            )
        )
    return rows


def cycle_setting(setting_id: int, option_count: int) -> None:
    """
    将指定体检设置切至下一个选项，已处于最后一项时回绕至 0。
    Keyword arguments:
    setting_id -- int，体检设置编号
    option_count -- int，该设置的选项总数
    Return arguments:
    None -- 无返回值
    """
    if physical_exam.setting(setting_id) < option_count - 1:
        physical_exam.set_setting(
            setting_id, physical_exam.setting(setting_id) + 1
        )
    else:
        physical_exam.set_setting(setting_id, 0)


def set_daily_count(value: str) -> None:
    """
    解析输入文本并写入每日抽取体检人数设置，空文本或非纯数字会被忽略，有效数字减 1 后限制在 0 到 9 之间。
    Keyword arguments:
    value -- str，输入的数字文本
    Return arguments:
    None -- 无返回值
    """
    if not value or not value.isdigit():
        return
    physical_exam.set_setting(DAILY_COUNT, min(max(int(value) - 1, 0), 9))


def exam_candidates() -> list[int]:
    """
    查询可加入手动体检名单的在编干员编号列表，按升序排列并排除主角以及未通过异常状态检查 2 或 7 的角色。
    Keyword arguments:
    无
    Return arguments:
    list[int] -- 符合条件的干员编号列表
    """
    return [
        npc_id
        for npc_id in roster.active_sorted()
        if npc_id != 0
        and handle_premise.handle_normal_2(npc_id)
        and handle_premise.handle_normal_7(npc_id)
    ]


def toggle_chosen(character_id: int) -> None:
    """
    在手动体检对象名单中切换指定角色的选中状态。
    Keyword arguments:
    character_id -- int，待切换的角色编号
    Return arguments:
    None -- 无返回值
    """
    if physical_exam.has(physical_exam.CHOSEN, character_id):
        physical_exam.discard(physical_exam.CHOSEN, character_id)
    else:
        physical_exam.add(physical_exam.CHOSEN, character_id)
