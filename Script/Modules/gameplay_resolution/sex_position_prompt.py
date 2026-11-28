"""
性交体位提示规则（sex_position_prompt）
=======================================
本模块提供性交体位选项构造函数 position_options 与体位行为映射函数 behavior，
并定义相关能力、模式与体位编号常量。
本模块不导入界面模块。
"""

from Script.Config import game_config
from Script.Core import constant, get_text
from Script.Design import attr_calculation, map_handle
from Script.Modules.domains import abilities, activity, flags, h_state
from Script.Protocol.modal_prompts import ChoiceOption, OptionAvailability

_ = get_text._
""" 文本翻译函数，指向 get_text._。 """
WAIST_SKILL = 76
""" 腰技能力编号常量（76）。 """
CARRY_MODE = 5
""" 隐奸携带模式标志值常量（5）。 """
CARRY_POSITION = 9
""" 隐奸携带模式允许使用的体位编号常量（9，对面抱位）。 """


def position_options() -> tuple[ChoiceOption, ...]:
    """
    按配置表顺序构造性交体位菜单的 ChoiceOption 元组。
    函数读取角色 0 的腰技、当前体位、所在场景家具等级与隐奸携带模式。
    函数为 game_config.config_sex_position_data 中编号大于 0 的每条体位生成一项选项。
    每项以编号字符串作为 option_id，note 保持为空。
    标签依次包含两位编号、10 栏宽名称、当前体位标记、体力消耗、不可用原因与体位说明。
    当前体位的 availability 为 "current"，其余不满足家具、腰技或携带模式条件时为
    "blocked"，否则为 "open"。
    Return arguments:
    tuple[ChoiceOption, ...] -- 按配置表顺序排列的性交体位选项元组
    """
    skill = abilities.ability(0)[WAIST_SKILL]
    current = h_state.get(0, "current_sex_position")
    scene_path = map_handle.get_map_system_path_str_for_list(
        activity.position(0)
    )
    furniture = constant.scene_data[scene_path].have_furniture
    carrying = flags.get(0, "hidden_sex_mode") == CARRY_MODE
    options = []
    for position_id, data in game_config.config_sex_position_data.items():
        if position_id <= 0:
            continue
        name = attr_calculation.pad_display_width(data.name, 10)
        label = f"[{str(position_id).rjust(2, '0')}]{name}："
        blocked = False
        if position_id == current:
            label += _("(当前体位)")
        if data.stamina_cost == 1:
            label += _("(体力消耗小)")
        elif data.stamina_cost == 2:
            label += _("(体力消耗中)")
        elif data.stamina_cost == 3:
            label += _("(体力消耗大)")
        if data.furniture_req > furniture:
            if data.furniture_req == 1:
                label += _("(需要房间内有桌椅等级的家具)")
            elif data.furniture_req == 3:
                label += _("(需要房间内有床铺等级的家具)")
            blocked = True
        if data.skill_req > skill:
            label += _("(需要博士腰技至少为{0}级)").format(data.skill_req)
            blocked = True
        if carrying and position_id != CARRY_POSITION:
            label += _("(携带中只能使用对面抱位)")
            blocked = True
        label += data.info
        availability: OptionAvailability = "open"
        if position_id == current:
            availability = "current"
        elif blocked:
            availability = "blocked"
        options.append(ChoiceOption(str(position_id), label, availability))
    return tuple(options)


def behavior(position_id: int, sex_type: int) -> tuple[str, str]:
    """
    按体位编号与性交类型查询对应的行为标识与判定名称。
    性交类型 1 至 5 依次对应阴道、子宫口、子宫、肛门与尿道的行为字段。
    对应的判定名称依次为 "性交"、"W性交"、"W性交"、"A性交" 与 "U性交" 的译文。
    Keyword arguments:
    position_id -- int，性交体位编号
    sex_type -- int，性交类型编号（1 阴道、2 子宫口、3 子宫、4 肛门、5 尿道）
    Return arguments:
    tuple[str, str] -- 行为标识与对应译文判定名称的二元组
    """
    field, judge = {
        1: ("vaginal_sex_behavior_id", _("性交")),
        2: ("cervix_sex_behavior_id", _("W性交")),
        3: ("womb_sex_behavior_id", _("W性交")),
        4: ("anal_sex_behavior_id", _("A性交")),
        5: ("urethral_sex_behavior_id", _("U性交")),
    }[sex_type]
    data = game_config.config_sex_position_data[position_id]
    return getattr(data, field), judge
