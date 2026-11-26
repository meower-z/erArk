"""
外勤编队与载具面板（commission_squad_panel）
============================================
绘制外勤委托的派遣人员选择界面与载具选择界面。
"""

from types import FunctionType
from typing import TYPE_CHECKING

from Script.Config import game_config, normal_config
from Script.Core import flow_handle, get_text
from Script.Design import attr_calculation
from Script.Modules.domains import chara_life, identity
from Script.Modules.gameplay_resolution import commission_roster_service
from Script.Modules.gameplay_resolution import field_commission_service
from Script.UI.Moudle import draw

if TYPE_CHECKING:
    from Script.UI.Panel.field_commission_panel import CommissionDraw

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """
NAME_WIDTH = 24
""" 选人列表中角色名称按钮列的显示宽度（24）。 """
FILTER_WIDTH = 19
""" 选人界面筛选与装备加成按钮的显示宽度（19）。 """


def pass_func() -> None:
    """空回调函数，供仅按返回码分发的按钮占位使用。"""


def _style(on: bool) -> str:
    """根据激活状态返回高亮或标准文本样式名。"""
    return "gold_enrod" if on else "standard"


def _text(text: str, style: str = "", width: int = 0) -> None:
    """按可选样式与宽度绘制一段普通文本。"""
    now_draw = draw.NormalDraw()
    now_draw.text = text
    if style:
        now_draw.style = style
    if width:
        now_draw.width = width
    now_draw.draw()


def _button(
    return_list: list[str], text: str, key: str, width: int, on: bool
) -> None:
    """绘制居中控制按钮并将返回码追加到列表。"""
    button = draw.CenterButton(
        text, key, width, cmd_func=pass_func, normal_style=_style(on)
    )
    button.draw()
    return_list.append(button.return_text)


def _page_button(
    return_list: list[str], text: str, key: str, enabled: bool
) -> None:
    """绘制翻页按钮，不可翻页时以灰色文本占位。"""
    if enabled:
        button = draw.LeftButton(text, key, 12, cmd_func=pass_func)
        button.draw()
        return_list.append(button.return_text)
    else:
        _text(text, "deep_gray", 12)


def _draw_progress(owner: "CommissionDraw", commission_id: int) -> None:
    """绘制当前派遣人数、需求满足状态及队长与队员名单。"""
    people = game_config.config_commission[commission_id].people
    team = owner.send_npc_list
    _text(_("\n当前派遣进度： "))
    _text(
        _("[人数({0}/{1})] ").format(len(team), people),
        "spring_green" if len(team) >= people else "red",
    )
    for text, met in field_commission_service.demand_parts(commission_id, team):
        _text(f"[{text}] ", "spring_green" if met else "red")
    line_feed.draw()
    info_text = _("（无意识/重伤/特殊职位等无法出勤）\n")
    info_text += _("队长：")
    if owner.lead_chara_id != 0:
        info_text += identity.of(owner.lead_chara_id).name
    else:
        info_text += _("无")
    info_text += _("。队员：")
    for npc_id in team:
        if npc_id != owner.lead_chara_id:
            info_text += identity.of(npc_id).name + " "
    _text(info_text + "\n\n", width=owner.width)


def _draw_controls(
    view: commission_roster_service.RosterView,
    columns: list[tuple[str, int]],
    return_list: list[str],
) -> None:
    """绘制选人界面的筛选、排序、装备开关与技能排序按钮。"""
    _text(_(" 筛选: "))
    choice_names = [_("不筛选"), _("是"), _("否")]
    filters = [
        (_("[工作:{0}]"), "filter_work", [_("不筛选"), _("有"), _("无")]),
        (
            _("[陷落:{0}]"),
            "filter_fall",
            [_("不筛选"), _("无"), _("有"), _("爱情"), _("隶属")],
        ),
        (_("[女儿:{0}]"), "filter_daughter", choice_names),
        (_("[收藏:{0}]"), "filter_collection", choice_names),
    ]
    for label, key, names in filters:
        choice = getattr(view, key)
        text = label.format(names[choice])
        _button(return_list, text, key, FILTER_WIDTH, bool(choice))
    line_feed.draw()
    _text(_(" 排序: "))
    _button(return_list, _("[已选优先]"), "sort_sel", 12, view.selected_first)
    _button(return_list, _("[收藏优先]"), "sort_col", 12, view.collection_first)
    _button(return_list, _("[工作排序]"), "sort_work", 12, view.work_sort)
    status = _("开") if view.equipment else _("关")
    _button(
        return_list,
        _("[装备加成:{0}] ").format(status),
        "toggle_equip",
        FILTER_WIDTH,
        view.equipment,
    )
    line_feed.draw()
    _text(_(" 技能排序: "))
    _button(return_list, _("[默认ID] "), "sort_0", 10, view.skill == 0)
    for name, sid in columns:
        text = f"[{name}] "
        _button(
            return_list, text, f"sort_{sid}", len(text) * 2, view.skill == sid
        )


def _draw_row(
    owner: "CommissionDraw",
    npc_id: int,
    view: commission_roster_service.RosterView,
    columns: list[tuple[str, int]],
    return_list: list[str],
) -> None:
    """绘制选人列表中单个干员的按钮、技能值、装备与工作列。"""
    character_data = identity.of(npc_id)
    chosen = npc_id in owner.send_npc_list
    check_mark = "√" if chosen else " "
    id_str = str(character_data.adv).rjust(4, "0")
    star_str = (
        "⭐"
        if commission_roster_service.is_collected(character_data.cid)
        else "  "
    )
    name_str = attr_calculation.pad_display_width(
        f"[{check_mark}][{id_str}]{star_str}{character_data.name}",
        NAME_WIDTH,
    )
    name_btn = draw.LeftButton(
        name_str,
        str(npc_id),
        NAME_WIDTH,
        normal_style=_style(chosen),
        cmd_func=owner.select_this_npc,
        args=(npc_id,),
    )
    name_btn.draw()
    return_list.append(name_btn.return_text)
    for _col_name, col_id in columns:
        value = commission_roster_service.skill_value(
            npc_id, col_id, view.equipment
        )
        rank = attr_calculation.judge_grade(value)
        _text(
            attr_calculation.pad_display_width(rank, 3), f"level{rank.lower()}"
        )
        _text(f"{value}|")
    _text(*commission_roster_service.equipment_label(npc_id))
    _text("|")
    work_type_id = chara_life.work_type(character_data.cid)
    _text(f"{game_config.config_work_type[work_type_id].name}")
    line_feed.draw()


def adjust_team(owner: "CommissionDraw", commission_id: int) -> None:
    """运行外勤派遣人员选择界面循环并响应筛选、排序与翻页。"""
    owner.now_commision_id = commission_id
    commission_roster_service.auto_pick(commission_id, owner.send_npc_list)
    owner.lead_chara_id = field_commission_service.default_lead(
        getattr(owner, "lead_chara_id", 0), owner.send_npc_list
    )
    view = commission_roster_service.RosterView()
    columns = commission_roster_service.skill_columns()
    while True:
        return_list: list[str] = []
        line = draw.LineDraw("-", owner.width)
        line.draw()
        _draw_progress(owner, commission_id)
        _draw_controls(view, columns, return_list)
        line_feed.draw()
        line_feed.draw()
        line.draw()
        _text(" " * NAME_WIDTH)
        for col_name, col_id in columns:
            _text(f"{col_name}", _style(view.skill == col_id))
            _text("|")
        _text(_("装备|当前工作"))
        line_feed.draw()
        ids = commission_roster_service.candidates(view, owner.send_npc_list)
        view.page, total, page_ids = commission_roster_service.page_of(
            ids, view.page
        )
        for npc_id in page_ids:
            _draw_row(owner, npc_id, view, columns, return_list)
        for __ in range(commission_roster_service.PAGE_SIZE - len(page_ids)):
            line_feed.draw()
        line_feed.draw()
        line.draw()
        _page_button(return_list, _("[888]上一页"), "888", view.page > 0)
        _text(_("  [{0}/{1}页]  ").format(view.page + 1, total))
        _page_button(
            return_list, _("[222]下一页"), "222", view.page < total - 1
        )
        line_feed.draw()
        line_feed.draw()
        back_draw = draw.CenterButton(
            _("[完成 / 返回]"), _("返回"), window_width
        )
        back_draw.draw()
        return_list.append(back_draw.return_text)
        yrn = flow_handle.askfor_all(return_list)
        if yrn == back_draw.return_text:
            break
        commission_roster_service.press(view, yrn)


def _draw_vehicle(
    owner: "CommissionDraw", vehicle_cid: int, count: int
) -> None:
    """绘制单个可用载具的速度、运载、特效与选定数量行。"""
    vehicle_data = game_config.config_vehicle[vehicle_cid]
    chosen = owner.send_vehicle_dict.get(vehicle_cid, 0)
    pad = attr_calculation.pad_display_width
    fields = [
        pad(
            f"[{str(vehicle_cid).rjust(2, '0')}]{vehicle_data.name}",
            24,
            "center",
        ),
        pad(
            _("速度:{0}").format(str(vehicle_data.speed).rjust(2)), 16, "center"
        ),
        pad(
            _("运载:{0}").format(str(vehicle_data.capacity).rjust(3)),
            16,
            "center",
        ),
        pad(_("特效:{0}").format(vehicle_data.special), 16, "center"),
        pad(_("选定: {0}/{1}").format(chosen, count), 16, "center"),
    ]
    _text(" " + " | ".join(fields), _style(chosen > 0))


def adjust_vehicles(owner: "CommissionDraw", capacity_need: int) -> None:
    """运行外勤载具选择界面循环并汇总运载量、速度与特效。"""
    while True:
        return_list: list[str] = []
        line = draw.LineDraw("-", owner.width)
        line.draw()
        _text(_("\n 可派遣载具：\n\n"), width=owner.width)
        for vehicle_cid, count in field_commission_service.available_vehicles():
            _draw_vehicle(owner, vehicle_cid, count)
            for text, sign, func in (
                (_("[+1]"), "+1", owner.add_this_vehicle),
                (_("[-1]"), "-1", owner.reduce_this_vehicle),
            ):
                button = draw.CenterButton(
                    text,
                    f"\n{vehicle_cid}{sign}",
                    6,
                    cmd_func=func,
                    args=vehicle_cid,
                )
                button.draw()
                return_list.append(button.return_text)
                if sign == "+1":
                    _text(" ")
            line_feed.draw()
        chosen = owner.send_vehicle_dict
        capacity = field_commission_service.fleet_capacity(chosen)
        speed = field_commission_service.fleet_speed(chosen)
        effects = field_commission_service.fleet_effects(chosen)
        effect_text = "".join(f"{effect} " for effect in effects) or _("无")
        days = game_config.config_commission[owner.commission_id].time
        calc_day = field_commission_service.travel_days(days, speed)
        line_feed.draw()
        _text(_("\n 当前总运载量 / 需求运载量："))
        _text(
            f"{capacity} / {capacity_need}\n",
            "spring_green" if capacity >= capacity_need else "red",
        )
        _text(
            _(" 当前队伍速度：{0} (预计耗时计算: {1}天)\n").format(
                speed, calc_day
            )
            + _(" 附加特殊效果：{0}\n").format(effect_text)
        )
        line_feed.draw()
        line_feed.draw()
        back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
        back_draw.draw()
        return_list.append(back_draw.return_text)
        yrn = flow_handle.askfor_all(return_list)
        if yrn == back_draw.return_text:
            break
