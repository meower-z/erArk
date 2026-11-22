"""
动力系统的每日结算与人力发电
本模块用 power_supply 算出的数值写文本、绘制并结算成就
"""

from types import FunctionType

from Script.Config import game_config, normal_config
from Script.Core import cache_control, get_text
from Script.Modules.domains import achievement, power, power_supply
from Script.Modules.domains import status
from Script.UI.Moudle import draw

_: FunctionType = get_text._
window_width: int = normal_config.config_normal.text_width


def settle_power_system(draw_flag: bool = True) -> tuple[float, str]:
    """
    结算一天的动力（power_supply.settle_day），写出结算文本，并按发电量结算成就821、822、823
    燃料用量为 0 且发电不少于耗电时结算成就826
    Keyword arguments:
    draw_flag -- 为 True 时立即绘制文本
    Return arguments:
    tuple -- (仍缺的电量占耗电量的比例, 结算文本)
    """
    from Script.UI.Panel import achievement_panel

    day = power_supply.settle_day()
    text = _("\n○动力区结算\n")
    if day["fuel_use"] + 1e-6 < day["fuel_plan"]:
        text += _(
            " - 火力发电：燃料不足（计划 {0:.1f}，实际 {1:.1f}），按比例产出 {2:.1f} 单位电量\n"
        ).format(day["fuel_plan"], day["fuel_use"], day["fire_power"])
    else:
        text += _(
            " - 火力发电：消耗燃料 {0:.1f} 单位，产出 {1:.1f} 单位电量\n"
        ).format(day["fuel_use"], day["fire_power"])
    text += _(
        " - 清洁能源：水 {0} 风 {1} 太阳能 {2} 台，总产出 {3:.1f} 单位电量\n"
    ).format(*day["clean"], day["clean_power"])
    text += _(
        " - 汇总：总发电 {0:.1f} 单位电量，总耗电 {1:.1f} 单位电量\n"
    ).format(day["generated"], day["consumed"])
    if day["short"]:
        text += _(
            " - 亏电：缺口 {0:.1f} 单位电量，已从蓄电池补充 {1:.1f} 单位电量，剩余储能 {2:.1f}/{3}\n"
        ).format(day["gap"], day["drawn"], day["storage"], day["storage_max"])
        if day["remain_gap"] > 1e-6:
            text += _(
                " - 警告：仍缺 {0:.1f} 单位电量，占需求 {1:.1%}\n"
            ).format(day["remain_gap"], day["shortage_ratio"])
        else:
            text += _(" - 已完全由蓄电池弥补当日缺口\n")
    else:
        text += _(
            " - 自放电：损失 {0:.1f} 单位电量 ({1:.2%})，储能剩余 {2:.1f}\n"
        ).format(
            day["discharged"], day["discharge_rate"], day["after_discharge"]
        )
        text += _(
            " - 结余：过剩 {0:.1f} 单位电量，充入 {1:.1f} 单位电量，当前储能 {2:.1f}/{3}，溢出 {4:.1f} 单位电量\n"
        ).format(
            day["surplus"],
            day["charged"],
            day["storage"],
            day["storage_max"],
            day["overflow"],
        )
    if draw_flag:
        draw_text = draw.WaitDraw()
        draw_text.width = window_width
        draw_text.text = text
        draw_text.draw()
    generated = int(day["generated"])
    achievement_panel.get_achievement_judge_by_value(821, generated)
    achievement_panel.get_achievement_judge_by_value(822, generated)
    achievement_panel.get_achievement_judge_by_value(823, generated)
    if day["fuel_use"] == 0 and day["generated"] >= day["consumed"]:
        achievement_panel.get_achievement_judge_by_value(826, 1)
    return day["shortage_ratio"], text


def store_power_by_human_power(
    climax_degree: int, character_id: int, draw_flag: bool = True
) -> float:
    """
    一次人力发电。按绝顶程度算出电量（power_supply.human_power）存进储能，并把角色的状态12减半
    成就827未达成且电量达到它的数值时结算该成就。没有电量时什么也不做
    Keyword arguments:
    climax_degree -- 绝顶程度，1 小，2 普，3 强，4 超，5 及以上为多重绝顶
    character_id -- 角色id
    draw_flag -- 为 True 时立即绘制提示
    Return arguments:
    float -- 发出的电量，保留 2 位小数。没有电量时为 0.0
    """
    per_degree = power_supply.human_power(climax_degree, character_id)
    if per_degree is None:
        return 0.0
    character = cache_control.cache.character_data[character_id]
    status.set(character_id, 12, int(status.of(character_id)[12] / 2))
    power.store(per_degree)
    if draw_flag:
        draw_text = draw.WaitDraw()
        draw_text.width = window_width
        if climax_degree <= 4:
            if character_id == 0:
                draw_text.text = _("\n在{0}射精的同时，").format(character.name)
            else:
                draw_text.text = _("\n在{0}绝顶的同时，").format(character.name)
        else:
            draw_text.text = _("\n在{0}{1}重绝顶的同时，").format(
                character.name, climax_degree - 3
            )
        draw_text.text += _("性爱发电装置产生了 {0:.1f} 单位电量\n").format(
            per_degree
        )
        draw_text.draw()
    if not achievement.done(827):
        achievement_data = game_config.config_achievement[827]
        if per_degree >= achievement_data.value:
            from Script.UI.Panel import achievement_panel

            achievement_panel.achievement_flow(achievement_data.type, 827)
    return round(per_degree, 2)
