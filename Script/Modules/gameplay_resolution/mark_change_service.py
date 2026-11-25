"""
刻印升降级规则与状态服务（mark_change_service）
===============================================
本模块提供刻印升降级判定、报价文案、宝珠用量校验与升降级写入。
本模块公开常量 PRISON 与 NEGATIVE_MARKS，
数据类 MarkUpOffer 与 MarkDownOffer。
本模块公开函数 can_raise、raise_ok、lower_ok、mark_up_offer、
mark_up、mark_down_offer、juel_prompt、juel_count 与 mark_down。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import handle_premise, second_behavior
from Script.Modules.domains import abilities, facility, modes

_: FunctionType = get_text._
""" 翻译api """

PRISON = 19
""" 关押区设施对应的设施编号。 """
NEGATIVE_MARKS = frozenset({17, 18})
""" 不可直接用宝珠升级的负面刻印能力编号集合。 """


@dataclass(frozen=True, slots=True)
class MarkUpOffer:
    """
    刻印升级报价数据，含说明文本 text、
    所需宝珠数 need_juel 与库存足够标志 enough。
    """

    text: str
    need_juel: int
    enough: bool


@dataclass(frozen=True, slots=True)
class MarkDownOffer:
    """
    刻印降级报价数据，含说明文本 text、
    降级需求值 need（被关押时为折后值）与可选宝珠及权重列表 entries。
    """

    text: str
    need: int
    entries: tuple[tuple[int, float], ...]


def _expand(entries: list[str]) -> list[str]:
    """将宝珠条目中的占位符 "1" 展开为所有类型为 0 的状态编号。"""
    if "1" not in entries:
        return list(entries)
    kept = [entry for entry in entries if entry != "1"]
    for state_id, state in game_config.config_character_state.items():
        if state.type == 0:
            kept.append(str(state_id))
    return kept


def _entries(entries: list[str]) -> tuple[tuple[int, float], ...]:
    """将宝珠配置条目解析为编号与权重元组，并跳过 "0" 项。"""
    parsed: list[tuple[int, float]] = []
    for entry in entries:
        if entry == "0":
            continue
        if "|" in entry:
            parsed.append(
                (int(entry.split("|")[0]), float(entry.split("|")[1]))
            )
        else:
            parsed.append((int(entry), 1))
    return tuple(parsed)


def _total(cid: int, entries: list[str]) -> int:
    """按解析后的宝珠权重汇总角色可用宝珠的加权总值。"""
    juel = abilities.juel(cid)
    return sum(
        int(juel.get(juel_id, 0) * adjust)
        for juel_id, adjust in _entries(entries)
    )


def _prison() -> tuple[int, int]:
    """读取关押区设施当前等级及其对应的降级折扣百分比。"""
    level = facility.level(PRISON)
    effect_id = game_config.config_facility_effect_data[_("关押区")][int(level)]
    return level, game_config.config_facility_effect[effect_id].effect


def _discounted(cid: int, need: int) -> int:
    """若角色处于关押状态则按关押区效果折减降级所需总值。"""
    if not handle_premise.handle_imprisonment_1(cid):
        return need
    effect = _prison()[1]
    return int(need * (1 - effect / 100))


def can_raise(ability_id: int, level: int) -> bool:
    """
    判断指定刻印在当前等级是否具备使用宝珠升级的入口资格。
    Keyword arguments:
    ability_id -- int，刻印对应的能力编号
    level -- int，刻印当前等级
    Return arguments:
    bool -- 有升级配置、等级低于 3 且非负面刻印时返回 True
    """
    return (
        ability_id in game_config.config_mark_up_data_by_ability
        and level < 3
        and ability_id not in NEGATIVE_MARKS
    )


def raise_ok(cid: int, ability_id: int, level: int) -> bool:
    """
    判断角色当前状态值与对应宝珠库存是否满足刻印升级需求。
    Keyword arguments:
    cid -- int，角色编号
    ability_id -- int，刻印对应的能力编号
    level -- int，刻印当前等级
    Return arguments:
    bool -- 满足升级条件返回 True，异常时回退为调试模式开关
    """
    try:
        data_id = game_config.config_mark_up_data_by_ability[ability_id][level]
        data = game_config.config_mark_up_data[data_id]
        need = data.need_state_all_value
        state_total = (
            second_behavior.get_now_state_all_value_and_text_from_mark_up_data(
                data_id, cid
            )[0]
        )
        if state_total >= need:
            return True
        need_juel = max(int(need - state_total), 0)
        return abilities.juel(cid).get(data.need_juel_type, 0) >= need_juel
    except Exception:
        return bool(modes.debug())


def lower_ok(cid: int, ability_id: int, level: int) -> bool:
    """
    判断角色可用宝珠加权总值是否达到刻印降级需求（被关押时按折后值）。
    Keyword arguments:
    cid -- int，角色编号
    ability_id -- int，刻印对应的能力编号
    level -- int，刻印当前等级
    Return arguments:
    bool -- 满足降级条件返回 True，异常时回退为调试模式开关
    """
    try:
        data = game_config.config_mark_down_data[
            game_config.config_mark_down_data_by_ability[ability_id][level]
        ]
        entries = _expand(
            [data.need_juel_1, data.need_juel_2, data.need_juel_3]
        )
        total = _total(cid, entries)
        return total >= _discounted(cid, data.need_juel_all_value)
    except Exception:
        return bool(modes.debug())


def mark_up_offer(cid: int, ability_id: int) -> MarkUpOffer:
    """
    生成刻印升级页的说明文本、待补宝珠数量与库存足够标志。
    Keyword arguments:
    cid -- int，角色编号
    ability_id -- int，刻印对应的能力编号
    Return arguments:
    MarkUpOffer -- 刻印升级报价数据
    """
    level = abilities.ability(cid)[ability_id]
    data_id = game_config.config_mark_up_data_by_ability[ability_id][level]
    data = game_config.config_mark_up_data[data_id]
    state_total, state_text = (
        second_behavior.get_now_state_all_value_and_text_from_mark_up_data(
            data_id, cid
        )
    )
    ability_data = game_config.config_ability[ability_id]
    text = _(
        "○部分刻印除了其原本的升级获取方式之外，还可以通过消耗大量宝珠来直接升级\n\n"
    )
    text += _("当前刻印及等级为：{0} - {1}\n").format(ability_data.name, level)
    text += "  " + ability_data.info + "\n\n"
    text += _("升级需要的总值为：{0}\n").format(data.need_state_all_value)
    text += _("当前角色状态可以提供的总值为：")
    if state_text == "":
        state_text = _("无")
    text += state_text + "\n"
    need_juel = max(int(data.need_state_all_value - state_total), 0)
    have = abilities.juel(cid)[data.need_juel_type]
    text += _("减去提供值后需要消耗的宝珠为：{0} {1}，当前拥有：{2}\n").format(
        game_config.config_juel[data.need_juel_type].name, need_juel, have
    )
    return MarkUpOffer(text, need_juel, have >= need_juel)


def mark_up(cid: int, ability_id: int, need_juel: int) -> str:
    """
    扣除升级宝珠、提升刻印 1 级并授予对应二段行为。
    Keyword arguments:
    cid -- int，角色编号
    ability_id -- int，刻印对应的能力编号
    need_juel -- int，需扣除的宝珠数量
    Return arguments:
    str -- 本次升级授予的二段行为标识
    """
    level = abilities.ability(cid)[ability_id]
    data = game_config.config_mark_up_data[
        game_config.config_mark_up_data_by_ability[ability_id][level]
    ]
    abilities.juel(cid)[data.need_juel_type] -= need_juel
    abilities.ability(cid)[ability_id] += 1
    second_behavior.character_get_second_behavior(cid, data.second_behavior)
    return data.second_behavior


def mark_down_offer(cid: int, ability_id: int) -> MarkDownOffer:
    """
    生成刻印降级页的说明文本、折后需求值与可选宝珠权重条目。
    Keyword arguments:
    cid -- int，角色编号
    ability_id -- int，刻印对应的能力编号
    Return arguments:
    MarkDownOffer -- 刻印降级报价数据
    """
    level = abilities.ability(cid)[ability_id]
    data = game_config.config_mark_down_data[
        game_config.config_mark_down_data_by_ability[ability_id][level]
    ]
    entries = _entries(
        _expand([data.need_juel_1, data.need_juel_2, data.need_juel_3])
    )
    prison_level, effect = _prison()
    ability_data = game_config.config_ability[ability_id]
    need = data.need_juel_all_value
    text = _(
        "○非正面刻印除了通过源石技艺降级之外，还可以通过消耗大量宝珠来直接降级\n\n"
    )
    text += _("当前刻印及等级为：{0} - {1}\n").format(ability_data.name, level)
    text += "  " + ability_data.info + "\n\n"
    text += _("降级需要的总值为：{0}\n").format(need)
    if handle_premise.handle_imprisonment_1(cid):
        need = int(need * (1 - effect / 100))
        text += _(
            "该干员已被关押，当前关押区等级为{0}，降级所需宝珠值降低{1}%，降级所需宝珠值为{2}\n"
        ).format(prison_level, effect, need)
    return MarkDownOffer(text, need, entries)


def juel_prompt(
    cid: int, juel_id: int, adjust: float, so_far: int, need: int, used: int
) -> str:
    """
    生成输入单个宝珠使用量时的本地化提示文本与预计需求数。
    Keyword arguments:
    cid -- int，角色编号
    juel_id -- int，宝珠编号
    adjust -- float，该宝珠对应的权重系数
    so_far -- int，当前条目之前已累计的宝珠总值
    need -- int，降级所需的目标总值
    used -- int，该宝珠当前已填使用量
    Return arguments:
    str -- 包含上限、已用量与预计需求数的提示文本
    """
    have = abilities.juel(cid)[juel_id]
    guess = 0 if so_far >= need else int((need - so_far) / adjust)
    return _(
        "\n请输入要使用的宝珠数量，最多可以使用{0}个{1}，当前使用量为{2}，预计需要{3}个\n"
    ).format(have, game_config.config_juel[juel_id].name, used, guess)


def juel_count(cid: int, juel_id: int, text: str) -> int | None:
    """
    解析宝珠数量输入文本并将其限制在 0 与当前库存之间。
    Keyword arguments:
    cid -- int，角色编号
    juel_id -- int，宝珠编号
    text -- str，用户输入的文本
    Return arguments:
    int | None -- 合法输入返回夹紧后的数量，非纯数字返回 None
    """
    if not text.isdigit():
        return None
    return min(max(int(text), 0), abilities.juel(cid)[juel_id])


def mark_down(cid: int, ability_id: int, use: Mapping[int, int]) -> str:
    """
    将刻印降低 1 级、按映射扣除所选宝珠并返回降级成功提示。
    Keyword arguments:
    cid -- int，角色编号
    ability_id -- int，刻印对应的能力编号
    use -- Mapping[int, int]，各宝珠编号到扣除数量的映射
    Return arguments:
    str -- 含刻印名称与新等级的本地化成功提示
    """
    abilities.ability(cid)[ability_id] -= 1
    juel = abilities.juel(cid)
    for juel_id, count in use.items():
        juel[juel_id] -= count
    return _("\n刻印降级成功，{0}降至{1}级\n").format(
        game_config.config_ability[ability_id].name,
        abilities.ability(cid)[ability_id],
    )
