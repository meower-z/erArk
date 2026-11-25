"""
做饭面板服务（make_food_service）
=================================
提供制作食物面板的筛选排序、分页、调味显示、品质预测与确认计算。
本模块不导入 Script.UI 与 Script.Settle。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config, normal_config
from Script.Core import constant, get_text
from Script.Design import basement, handle_premise
from Script.Modules.domains import inventory, modes
from Script.System.Cooking_System import cooking

_: FunctionType = get_text._
""" 翻译api """
PAGE_SIZE = 50
""" 菜谱列表每页显示的按钮行数。 """
MAX_COUNT = 10
""" 单次批量制作允许选择的最大份数。 """
FINE_BONUS = 4
""" 精细模式在品质预测中相对基础品质最多增加的点数。 """
LEISURE_ZONE = 5
""" 生活娱乐区设施编号（5），其设施效率用于换算制作耗时。 """
ButtonRow = tuple[str, str, int, int, int]
""" 菜谱按钮行元组类型，依次含菜谱编号、菜名、调味、模式与入口类型。 """


@dataclass(frozen=True, slots=True)
class ListFilter:
    """菜谱列表筛选与排序条件，含类型元组、难度、时间、排序维度与顺序。"""

    types: tuple[int, ...]
    difficulty: int
    time: int
    sort_type: int
    sort_order: int


@dataclass(frozen=True, slots=True)
class ConfirmPlan:
    """二级确认页初始化参数，含菜谱、调味名、品质区间、份数与设施效率。"""

    recipe_id: int
    seasoning_name: str
    base_quality: int
    max_quality: int
    max_count: int
    start_count: int
    facility_adjust: float


def type_labels() -> dict[int, str]:
    """
    返回菜谱类型编号到当前语言显示名称的映射。
    Return arguments:
    dict[int, str] -- 菜谱类型编号（0至5、8、9）到名称的映射
    """
    return {
        0: _("正餐"),
        1: _("零食"),
        2: _("饮品"),
        3: _("酒类"),
        4: _("乳制品"),
        5: _("预制食物"),
        8: _("加料咖啡"),
        9: _("其他"),
    }


def difficulty_labels() -> list[tuple[int, str]]:
    """
    返回难度筛选档位编号与当前语言名称的列表。
    Return arguments:
    list[tuple[int, str]] -- 难度档位（0至2）与名称的二元组列表
    """
    return [(0, _("简单(0-3)")), (1, _("中等(4-6)")), (2, _("困难(7+)"))]


def time_labels() -> list[tuple[int, str]]:
    """
    返回时间筛选档位编号与当前语言名称的列表。
    Return arguments:
    list[tuple[int, str]] -- 时间档位（0至2）与名称的二元组列表
    """
    return [
        (0, _("快速(≤30分)")),
        (1, _("中等(31-60分)")),
        (2, _("耗时(61+分)")),
    ]


def sort_type_labels() -> list[tuple[int, str]]:
    """
    返回排序维度编号与当前语言名称的列表。
    Return arguments:
    list[tuple[int, str]] -- 排序维度（0至3）与名称的二元组列表
    """
    return [(0, _("无")), (1, _("难度")), (2, _("时间")), (3, _("类型"))]


def sort_order_labels() -> list[tuple[int, str]]:
    """
    返回排序顺序编号与当前语言名称的列表。
    Return arguments:
    list[tuple[int, str]] -- 排序顺序（0升序、1降序）与名称列表
    """
    return [(0, _("升序")), (1, _("降序"))]


def status_text(query: ListFilter) -> tuple[str, str]:
    """
    按筛选与排序条件生成筛选状态文本与排序状态文本。
    Keyword arguments:
    query -- ListFilter，当前的筛选与排序条件
    Return arguments:
    tuple[str, str] -- 筛选状态文本与排序状态文本的二元组
    """
    parts = []
    if query.types:
        names = type_labels()
        joined = ",".join(names.get(t, str(t)) for t in query.types)
        parts.append(_("类型:{0}").format(joined))
    if query.difficulty != -1:
        label = dict(difficulty_labels())[query.difficulty]
        parts.append(_("难度:{0}").format(label))
    if query.time != -1:
        parts.append(_("时间:{0}").format(dict(time_labels())[query.time]))
    if parts:
        filter_text = _("筛选：{0}").format(" ".join(parts))
    else:
        filter_text = _("筛选：无")
    if query.sort_type != 0:
        sort_text = _("排序：{0}{1}").format(
            dict(sort_type_labels())[query.sort_type],
            dict(sort_order_labels())[query.sort_order],
        )
    else:
        sort_text = _("排序：无")
    return filter_text, sort_text


def button_rows(
    data: Mapping[str, int],
    food_type: str,
    query: ListFilter,
    seasoning: int,
    cook_mode: int,
    make_food_type: int,
) -> list[ButtonRow]:
    """
    按页签与筛选排序生成菜谱按钮行并补齐至每页行数的倍数。
    Keyword arguments:
    data, food_type -- Mapping[str, int] 与 str，菜谱映射与页签
    query -- ListFilter，当前的筛选与排序条件
    seasoning, cook_mode, make_food_type -- int，调味、模式与入口类型
    Return arguments:
    list[ButtonRow] -- 含空白占位行且长度为 50 倍数的按钮行列表
    """
    rows: list[ButtonRow] = [
        (cid, name, seasoning, cook_mode, make_food_type)
        for cid, name in cooking.get_filtered_sorted_cook_data(
            data,
            food_type,
            filter_type=query.types,
            filter_difficulty=query.difficulty,
            filter_time=query.time,
            sort_type=query.sort_type,
            sort_order=query.sort_order,
        )
    ]
    pad = -len(rows) % PAGE_SIZE if rows else PAGE_SIZE
    return rows + [("-1", "", seasoning, cook_mode, make_food_type)] * pad


def seasoning_listed(seasoning: int) -> bool:
    """
    判断指定调味编号是否应在制作面板中显示为按钮。
    Keyword arguments:
    seasoning -- int，调味配置编号
    Return arguments:
    bool -- 编号不大于 100、持有对应药物或调试模式开启时返回真
    """
    return (
        seasoning <= 100 or bool(inventory.items(0)[seasoning]) or modes.debug()
    )


def cook_mode(make_food_type: int) -> int:
    """
    读取指定制作入口保存的烹饪模式，缺省时返回 0。
    Keyword arguments:
    make_food_type -- int，制作入口类型（0做饭、1泡咖啡、2调酒）
    Return arguments:
    int -- 系统设置中的烹饪模式值
    """
    return normal_config.system_setting.makefood_cook_mode.get(
        make_food_type, 0
    )


def set_cook_mode(make_food_type: int, mode: int) -> None:
    """
    将指定制作入口的烹饪模式写入系统设置。
    Keyword arguments:
    make_food_type -- int，制作入口类型（0做饭、1泡咖啡、2调酒）
    mode -- int，要保存的烹饪模式（0标准、1精细）
    """
    normal_config.system_setting.makefood_cook_mode[make_food_type] = mode


def check_cook_mode(make_food_type: int) -> None:
    """
    校验指定制作入口的烹饪模式，非法值重置为 0。
    Keyword arguments:
    make_food_type -- int，制作入口类型（0做饭、1泡咖啡、2调酒）
    """
    if cook_mode(make_food_type) not in {0, 1}:
        set_cook_mode(make_food_type, 0)


def quality_range(base: int, fine: bool) -> tuple[int, int]:
    """
    按基础品质与精细标记计算品质预测的上下界。
    Keyword arguments:
    base -- int，制作前的基础品质值
    fine -- bool，是否按精细模式展开预测上界
    Return arguments:
    tuple[int, int] -- 预测品质的下界与上界
    """
    if not fine:
        return base, base
    return base, min(base + FINE_BONUS, cooking.get_max_food_quality())


def panel_quality(mode: int) -> tuple[int, int]:
    """
    按玩家基础料理品质与当前烹饪模式计算主面板品质预测区间。
    Keyword arguments:
    mode -- int，烹饪模式（1 时展开精细上界）
    Return arguments:
    tuple[int, int] -- 预测品质的下界与上界
    """
    return quality_range(cooking.get_base_food_quality(0), mode == 1)


def recipe_quality(recipe_id: int) -> int:
    """
    计算单道菜谱的基础品质，酒吧内制作酒类时额外加 1。
    Keyword arguments:
    recipe_id -- int，菜谱编号
    Return arguments:
    int -- 计入酒吧加成后的菜谱基础品质
    """
    quality = cooking.get_base_food_quality(0)
    recipe = game_config.config_recipes[recipe_id]
    if recipe.type == 3 and handle_premise.handle_in_bar(0):
        quality += 1
    return quality


def asks_questions(recipe_id: int, mode: int) -> bool:
    """
    判断指定菜谱在当前烹饪模式下是否进入精细答题流程。
    Keyword arguments:
    recipe_id -- int，菜谱编号
    mode -- int，烹饪模式（1 为精细模式）
    Return arguments:
    bool -- 处于精细模式且该菜谱存在题库时返回真
    """
    return mode == 1 and cooking.has_cook_question_library(recipe_id)


def max_count(seasoning: int) -> int:
    """
    计算当前调味下的单次最大制作份数，下限为 1。
    Keyword arguments:
    seasoning -- int，调味配置编号（大于 100 时受药物库存限制）
    Return arguments:
    int -- 允许选择的最大制作份数（1 至 10）
    """
    count = MAX_COUNT
    if seasoning > 100:
        count = min(count, inventory.items(0)[seasoning])
    return max(1, count)


def start_count(make_food_type: int, limit: int) -> int:
    """
    读取指定入口记忆的制作份数并钳制到本次上限内。
    Keyword arguments:
    make_food_type -- int，制作入口类型（0做饭、1泡咖啡、2调酒）
    limit -- int，本次允许的最大份数上限
    Return arguments:
    int -- 确认面板默认显示的起始份数
    """
    counts = normal_config.system_setting.makefood_make_count
    remembered = counts.get(make_food_type, 1)
    if not isinstance(remembered, int) or remembered < 1:
        remembered = 1
    return min(remembered, limit)


def remember_count(make_food_type: int, count: int) -> None:
    """
    将指定制作入口本次确认的制作份数写入系统设置。
    Keyword arguments:
    make_food_type -- int，制作入口类型（0做饭、1泡咖啡、2调酒）
    count -- int，本次确认制作的份数
    """
    normal_config.system_setting.makefood_make_count[make_food_type] = count


def confirm_plan(
    recipe_id: int, seasoning: int, mode: int, make_food_type: int
) -> ConfirmPlan:
    """
    汇总二级确认页所需的调味名、品质区间、份数与设施效率。
    Keyword arguments:
    recipe_id, seasoning -- int，菜谱编号与调味编号
    mode, make_food_type -- int，烹饪模式与制作入口类型
    Return arguments:
    ConfirmPlan -- 供二级确认页使用的参数快照
    """
    seasoning_name = game_config.config_seasoning[seasoning].name
    adjust = basement.calc_facility_efficiency(LEISURE_ZONE)
    base, top = quality_range(
        recipe_quality(recipe_id), asks_questions(recipe_id, mode)
    )
    limit = max_count(seasoning)
    start = start_count(make_food_type, limit)
    return ConfirmPlan(
        recipe_id, seasoning_name, base, top, limit, start, adjust
    )


def make_time(minutes: int, count: int, adjust: float) -> tuple[int, str]:
    """
    按份数递增与设施效率计算总耗时及效率变动后缀文本。
    Keyword arguments:
    minutes -- int，单份菜谱基础耗时（分钟）
    count -- int，本次制作份数
    adjust -- float，生活娱乐区设施效率系数
    Return arguments:
    tuple[int, str] -- 总耗时分钟数与效率百分比后缀文本
    """
    base_total = int(minutes * (1 + (count - 1) * 0.1))
    if adjust == 1.0 or base_total <= 0:
        return base_total, ""
    total = int(base_total / adjust)
    rate = (total - base_total) / base_total
    if rate > 0:
        return total, _("（+{0:.1f}%）").format(rate * 100)
    if rate < 0:
        return total, _("（{0:.1f}%）").format(rate * 100)
    return total, ""


def confirm_text(plan: ConfirmPlan, count: int) -> tuple[str, int]:
    """
    按确认参数与当前份数拼装确认页信息文本并计算总耗时。
    Keyword arguments:
    plan -- ConfirmPlan，确认页初始化参数
    count -- int，当前选中的制作份数
    Return arguments:
    tuple[str, int] -- 确认信息多行文本与总耗时分钟数
    """
    recipe = game_config.config_recipes[plan.recipe_id]
    total, adjust_text = make_time(recipe.time, count, plan.facility_adjust)
    text = _("食物名字: {0}\n").format(recipe.name)
    text += _("菜谱难度: {0}\n").format(recipe.difficulty)
    if recipe.type == 3:
        alcohol = game_config.config_alcohol_level[recipe.alcohol].name
        text += _("酒精程度: {0}\n").format(alcohol)
    text += _("制作数量: {0} （最多 {1}）\n").format(count, plan.max_count)
    text += _("预计耗时: {0} 分钟{1}\n").format(total, adjust_text)
    text += _("当前调味: {0}\n").format(plan.seasoning_name)
    return text, total


def cook_behavior(add_coffee: bool) -> tuple[str, int]:
    """
    按是否为加料咖啡返回对应的行为标识与角色状态编号。
    Keyword arguments:
    add_coffee -- bool，是否为加料咖啡菜谱（type 为 8）
    Return arguments:
    tuple[str, int] -- 行为标识常量与角色状态常量
    """
    behavior, status = constant.Behavior, constant.CharacterStatus
    if add_coffee:
        return behavior.MAKE_COFFEE_ADD, status.STATUS_MAKE_COFFEE_ADD
    return behavior.MAKE_FOOD, status.STATUS_MAKE_FOOD
