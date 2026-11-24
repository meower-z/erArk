"""
香薰疗愈查询服务（aromatherapy_query）
======================================
从游戏状态与配置表构建香薰疗愈面板快照，并生成调香行动计划。
本模块不导入界面与输入输出模块，供香薰疗愈面板调用。
"""

from types import FunctionType

from Script.Config import game_config
from Script.Core import constant, get_text
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, flags, identity
from Script.Modules.domains import tallies, warehouse
from Script.Protocol.boundary_snapshot import (
    AromatherapyActionPlan,
    AromatherapyRecipeOption,
    AromatherapySnapshot,
    CommandOutcome,
    RecipeIngredient,
    ResourceStockItem,
    SnapshotMeta,
)

_: FunctionType = get_text._
""" 翻译api """

ACTIONS: dict[int, tuple[str, int]] = {
    1: (
        constant.Behavior.AROMATHERAPY_1,
        constant.CharacterStatus.STATUS_AROMATHERAPY_1,
    ),
    2: (
        constant.Behavior.AROMATHERAPY_2,
        constant.CharacterStatus.STATUS_AROMATHERAPY_2,
    ),
    3: (
        constant.Behavior.AROMATHERAPY_3,
        constant.CharacterStatus.STATUS_AROMATHERAPY_3,
    ),
    4: (
        constant.Behavior.AROMATHERAPY_4,
        constant.CharacterStatus.STATUS_AROMATHERAPY_4,
    ),
    5: (
        constant.Behavior.AROMATHERAPY_5,
        constant.CharacterStatus.STATUS_AROMATHERAPY_5,
    ),
    6: (
        constant.Behavior.AROMATHERAPY_6,
        constant.CharacterStatus.STATUS_AROMATHERAPY_6,
    ),
    7: (
        constant.Behavior.AROMATHERAPY_7,
        constant.CharacterStatus.STATUS_AROMATHERAPY_7,
    ),
    8: (
        constant.Behavior.AROMATHERAPY_8,
        constant.CharacterStatus.STATUS_AROMATHERAPY_8,
    ),
}
""" 配方编号 1 至 8 到对应行为编号与角色状态常量的映射表。 """


def _lock_reasons(
    need_lv: int, agriculture_lv: int, target_sex: int, sex_need: int
) -> tuple[str, ...]:
    """
    计算单条配方在当前农业技能等级与对象性别下的未解锁提示元组。
    Keyword arguments:
    need_lv -- int，配方要求的最低农业技能等级
    agriculture_lv -- int，玩家当前的农业技能（能力 47）等级
    target_sex -- int，调香对象的性别编码（0 为男性，1 为女性）
    sex_need -- int，配方的性别限制编码（0 限男性，1 限女性，其余不限）
    Return arguments:
    tuple[str, ...] -- 按农业技能与性别顺序排列的本地化未解锁提示元组
    """
    reasons: list[str] = []
    if agriculture_lv < need_lv:
        reasons.append(_("(需要[农业技能]等级>={0})").format(need_lv))
    if target_sex == 0 and sex_need == 1:
        reasons.append(_("(仅限女性调香对象)"))
    elif target_sex == 1 and sex_need == 0:
        reasons.append(_("(仅限男性调香对象)"))
    return tuple(reasons)


def _recipe_options(target_sex: int) -> tuple[AromatherapyRecipeOption, ...]:
    """
    按配置顺序构建香薰配方的展示选项元组，跳过编号为 0 的配置项。
    Keyword arguments:
    target_sex -- int，调香对象的性别编码（0 为男性，1 为女性）
    Return arguments:
    tuple[AromatherapyRecipeOption, ...] -- 各配方的展示信息、解锁状态与材料消耗元组
    """
    agriculture_lv = abilities.ability(0)[47]
    options: list[AromatherapyRecipeOption] = []
    for recipe_id, data in game_config.config_aromatherapy_recipes.items():
        if recipe_id == 0:
            continue
        reasons = _lock_reasons(
            data.difficulty * 2, agriculture_lv, target_sex, data.sex_need
        )
        ingredients = tuple(
            RecipeIngredient(rid, game_config.config_resouce[rid].name, amount)
            for rid, amount in game_config.config_aromatherapy_recipes_data[
                recipe_id
            ].items()
        )
        options.append(
            AromatherapyRecipeOption(
                recipe_id,
                data.name,
                data.info,
                not reasons,
                reasons,
                ingredients,
            )
        )
    return tuple(options)


def build_aromatherapy_snapshot(
    selected_recipe_id: int = 0,
) -> AromatherapySnapshot:
    """
    读取当前时钟、玩家交互对象、今日剩余次数、香薰相关库存与配方配置，构建香薰疗愈面板的只读快照。
    Keyword arguments:
    selected_recipe_id -- int，当前选中的配方编号，默认为 0（未选择）
    Return arguments:
    AromatherapySnapshot -- 包含面板展示数据、可确认标记与配方选项的只读快照
    """
    meta = SnapshotMeta(core.state().clock, "aromatherapy")
    target = identity.of(activity.target(0))
    remaining_today = tallies.get(tallies.AROMATHERAPY)
    treated = flags.get(target.cid, "aromatherapy")
    target_today_recipe_name = (
        game_config.config_aromatherapy_recipes[treated].name
        if treated != 0
        else None
    )
    resources: list[ResourceStockItem] = []
    for rid in warehouse.stock():
        data = game_config.config_resouce[rid]
        if data.name == _("香料") or data.type == _("香水"):
            resources.append(
                ResourceStockItem(rid, data.name, warehouse.amount(rid))
            )
    return AromatherapySnapshot(
        meta,
        remaining_today,
        target.cid,
        target.name,
        target_today_recipe_name,
        tuple(resources),
        selected_recipe_id,
        game_config.config_aromatherapy_recipes[selected_recipe_id].name,
        selected_recipe_id != 0 and remaining_today > 0 and treated == 0,
        _recipe_options(target.sex),
    )


def plan_aromatherapy_action(recipe_id: int) -> AromatherapyActionPlan:
    """
    校验指定配方是否合法且库存充足，生成对应的调香行动计划。
    配方未登记时返回原因码 unknown_recipe，库存不足时返回原因码 insufficient_resources。
    Keyword arguments:
    recipe_id -- int，待执行的香薰配方编号
    Return arguments:
    AromatherapyActionPlan -- 含校验结果以及受理时行为编号、状态常量与配方编号的行动计划
    """
    if recipe_id not in ACTIONS:
        return AromatherapyActionPlan(CommandOutcome(False, "unknown_recipe"))
    needs = game_config.config_aromatherapy_recipes_data[recipe_id]
    if any(warehouse.amount(rid) < amount for rid, amount in needs.items()):
        return AromatherapyActionPlan(
            CommandOutcome(False, "insufficient_resources")
        )
    behavior_id, state = ACTIONS[recipe_id]
    return AromatherapyActionPlan(
        CommandOutcome(True), behavior_id, state, recipe_id
    )
