"""
外勤委托面板（field_commission_panel）
======================================
绘制外勤委托主列表、委托详情界面并衔接编队、载具与派遣流程。
"""

from types import FunctionType
from Script.Core import get_text, flow_handle, constant
from Script.UI.Moudle import draw, panel, view
from Script.Config import game_config, normal_config
from Script.Design import game_time, attr_calculation, talk
from Script.UI.Panel import commission_squad_panel
from Script.System.Field_Commission_System.field_commission_function import (
    get_commission_demand_and_reward,
)
from Script.Modules.domains import commission, facility, identity
from Script.Modules.gameplay_resolution import field_commission_service

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """
COLUMNS = 6
""" 外勤委托列表表头与单行展示的列数（6）。 """


class Field_Commission_Panel:
    """外勤委托主界面，负责常规与特殊委托页签与分页列表展示。"""

    def __init__(self, width: int) -> None:
        """初始化外勤委托主界面的绘制宽度与默认页签状态。"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("常规外勤")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """
        self.send_npc_list: list[int] = []
        """ 派遣人员列表 """
        self.send_vehicle_dict: dict[int, int] = {}
        """ 派遣载具字典 """

    def _draw_tabs(self, return_list: list[str]) -> None:
        """绘制常规外勤与特殊外勤两个顶层页签按钮。"""
        commission_type_list = [_("常规外勤"), _("特殊外勤")]
        tab_width = int(self.width / len(commission_type_list))
        for commission_type in commission_type_list:
            now_draw: draw.CenterDraw | draw.CenterButton
            if commission_type == self.now_panel:
                now_draw = draw.CenterDraw()
                now_draw.text = f"[{commission_type}]"
                now_draw.style = "onbutton"
                now_draw.width = tab_width
                now_draw.draw()
            else:
                now_draw = draw.CenterButton(
                    f"[{commission_type}]",
                    f"\n{commission_type}",
                    tab_width,
                    cmd_func=self.change_panel,
                    args=(commission_type,),
                )
                now_draw.draw()
                return_list.append(now_draw.return_text)
        line_feed.draw()
        draw.LineDraw("+", self.width).draw()

    def _draw_header(self) -> None:
        """绘制机库等级说明与委托列表六列表头。"""
        now_level = facility.level(field_commission_service.HANGAR)
        facility_info_draw = draw.NormalDraw()
        facility_info_draw.text = (
            _(
                "○通用委托无论在哪里都可以接到，地区委托则需要罗德岛移动到对应地区时才可接到，能接到的委托等级与机库的等级有关\n"
            )
            + _("○常规外勤委托可以多次反复完成，特殊外勤只能完成一次\n")
            + _(
                "○罗德岛的移动：控制中枢-指挥室-导航，购买载具：机库-格纳库-管理载具\n"
            )
            + _("○当前机库等级：{0}，最高可接到{1}级的委托\n").format(
                now_level, now_level + 1
            )
        )
        facility_info_draw.draw()
        draw.LineDraw("+", self.width).draw()
        info_text_list = [
            _("委托等级"),
            _("委托类型"),
            _("委托名称"),
            _("派遣人数与耗时天数"),
            _("需求类型"),
            _("奖励类型"),
        ]
        info_draw_len = int(self.width / len(info_text_list))
        for info_text in info_text_list:
            info_draw = draw.CenterDraw()
            info_draw.text = attr_calculation.pad_display_width(
                info_text, info_draw_len, "center"
            )
            info_draw.width = info_draw_len
            info_draw.draw()
        line_feed.draw()
        draw.LineDraw("~", self.width).draw()

    def draw(self) -> None:
        """运行外勤委托主界面循环并处理列表分页与返回操作。"""
        self.handle_panel = panel.PageHandlePanel(
            [], CommissionDraw, 20, 1, self.width
        )
        title_draw = draw.TitleLineDraw(_("外勤委托"), self.width)
        while True:
            return_list: list[str] = []
            title_draw.draw()
            self._draw_tabs(return_list)
            self._draw_header()
            self.handle_panel.text_list = (
                field_commission_service.visible_commissions(
                    self.now_panel == _("特殊外勤")
                )
            )
            self.handle_panel.update()
            self.handle_panel.draw()
            return_list.extend(self.handle_panel.return_list)
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def change_panel(self, building_type: str) -> None:
        """切换当前显示的委托页签名称。"""
        self.now_panel = building_type


class CommissionDraw:
    """单个外勤委托列表行及其详情、编队、载具与派遣交互控制器。"""

    lead_chara_id: int
    """ 当前派遣队伍的队长角色编号，由选人操作设置。 """
    now_commision_id: int
    """ 当前正在调整人员的委托编号，供选人回调读取。 """

    def __init__(
        self,
        commission_id: int,
        width: int,
        is_button: bool,
        num_button: bool,
        button_id: int,
    ) -> None:
        """构造单条委托的列表行内容与点击按钮或灰色进行中文本。"""
        self.commission_id: int = commission_id
        """ 委托编号 """
        self.width: int = width
        """ 绘制的最大宽度 """
        self.is_button: bool = is_button
        """ 是否为按钮 """
        self.num_button: bool = num_button
        """ 是否为数字按钮 """
        self.button_id: int = button_id
        """ 按钮编号 """
        self.draw_text: str = ""
        """ 绘制文本 """
        self.button_return: str = ""
        """ 按钮返回文本 """
        self.send_npc_list: list[int] = []
        """ 派遣人员列表 """
        self.send_vehicle_dict: dict[int, int] = {}
        """ 派遣载具字典 """
        text_width = int((self.width - 1) / COLUMNS)
        data = game_config.config_commission[self.commission_id]
        name = data.name
        if self.commission_id not in commission.finished():
            name = "⭐" + name
        if self.commission_id in commission.ongoing():
            name += _("（进行中）")
        demand = get_commission_demand_and_reward(
            self.commission_id, self.send_npc_list
        )
        reward = get_commission_demand_and_reward(
            self.commission_id, self.send_npc_list, True
        )
        cells = [
            str(data.level),
            data.type,
            name,
            str(data.people) + _("人") + "  " + str(data.time) + _("天"),
            demand[1],
            reward[1],
        ]
        commision_text = "".join(
            attr_calculation.pad_display_width(cell, text_width, "center")
            for cell in cells
        )
        commision_draw: draw.LeftButton | draw.NormalDraw
        if self.commission_id not in commission.ongoing():
            commision_draw = draw.LeftButton(
                commision_text,
                "\n" + data.name,
                self.width,
                cmd_func=self.commision_info,
                args=(self.commission_id,),
            )
            self.button_return = commision_draw.return_text
        else:
            commision_draw = draw.NormalDraw()
            commision_draw.text = commision_text
            commision_draw.width = self.width
            commision_draw.style = "deep_gray"
        self.draw_text = commision_draw.text
        self.now_draw = commision_draw

    def draw(self) -> None:
        """绘制当前委托在列表中的单行元素。"""
        self.now_draw.draw()

    def _team_text(self, commision_id: int) -> str:
        """拼装详情页的已选人员、已选载具与预计耗时说明文本。"""
        text = _("\n\n派遣人员：")
        if not self.send_npc_list:
            text += _(" 无")
        for chara_id in self.send_npc_list:
            text += f"  {identity.of(chara_id).name}"
        text += _("\n\n派遣载具：")
        if not self.send_vehicle_dict:
            text += _(" 无")
        for vehicle_id, count in self.send_vehicle_dict.items():
            text += f"  {game_config.config_vehicle[vehicle_id].name} * {count}"
        speed = field_commission_service.team_speed(
            list(self.send_vehicle_dict)
        )
        calc_day = field_commission_service.travel_days(
            game_config.config_commission[commision_id].time, speed
        )
        text += _("\n  (当前队伍速度: {0} ，预计耗时计算: {1}天)").format(
            speed, calc_day
        )
        return text + _("\n\n需求满足情况：\n")

    def _draw_needs(
        self,
        commision_id: int,
        need: int,
        ready: field_commission_service.Readiness,
    ) -> None:
        """在详情页绘制人数、运载量与逐项额外需求的满足状态。"""
        data = game_config.config_commission[commision_id]
        info_draw = draw.NormalDraw()
        info_draw.text = self._team_text(commision_id)
        info_draw.width = self.width
        info_draw.draw()
        rows = [
            (
                _("  人数：{0} / {1}")
                .format(len(self.send_npc_list), data.people)
                .ljust(15),
                ready.people,
            ),
            (
                _("  运量：{0} / {1} [{2}(天-1) * {3}(人)]")
                .format(ready.capacity, need, data.time - 1, data.people)
                .ljust(35),
                ready.capacity_ok,
            ),
        ]
        for text, met in rows:
            row_draw = draw.NormalDraw()
            row_draw.text = text
            row_draw.style = "spring_green" if met else "red"
            row_draw.draw()
        line_feed.draw()
        demand_label = draw.NormalDraw()
        demand_label.text = _("  其他需求：")
        demand_label.draw()
        parts = field_commission_service.demand_parts(
            commision_id, self.send_npc_list
        )
        for text, met in parts or [(None, True)]:
            part_draw = draw.NormalDraw()
            part_draw.text = _("无") if text is None else f"[{text}] "
            part_draw.style = "spring_green" if met else "red"
            part_draw.draw()

    def commision_info(self, commision_id: int) -> None:
        """运行单个委托的详情界面循环并提供选人、选载具与执行入口。"""
        data = game_config.config_commission[commision_id]
        name = data.name
        if commision_id not in commission.finished():
            name = "⭐" + name
        need = field_commission_service.capacity_need(commision_id)
        reward = get_commission_demand_and_reward(
            commision_id, self.send_npc_list, True
        )[2]
        description = data.description.replace("\\n", "\n      ")
        self.send_npc_list = []
        self.send_vehicle_dict = {}
        while True:
            ready = field_commission_service.readiness(
                commision_id, self.send_npc_list, self.send_vehicle_dict
            )
            return_list: list[str] = []
            line = draw.LineDraw("-", self.width)
            line.draw()
            info_draw = draw.NormalDraw()
            info_draw.text = (
                _("\n委托名称：{0}").format(name)
                + _("\n委托等级：{0}").format(str(data.level))
                + _("\n耗时天数：{0}").format(str(data.time) + _("天"))
                + _("\n奖励：{0}").format(reward)
                + _("\n介绍：{0}").format(description)
            )
            info_draw.width = self.width
            info_draw.draw()
            self._draw_needs(commision_id, need, ready)
            line_feed.draw()
            line_feed.draw()
            for text, key, func, arg, met in (
                (
                    _("【调整派遣人员】"),
                    _("调整派遣人员"),
                    self.adjust_send_npc,
                    commision_id,
                    ready.people and ready.demand,
                ),
                (
                    _("【调整使用载具】"),
                    _("调整使用载具"),
                    self.adjust_send_vehicle,
                    need,
                    ready.capacity_ok,
                ),
            ):
                button = draw.CenterButton(
                    text,
                    key,
                    int(self.width / 2),
                    cmd_func=func,
                    args=(arg,),
                    normal_style="standard" if met else "gold_enrod",
                )
                button.draw()
                return_list.append(button.return_text)
            line_feed.draw()
            line_feed.draw()
            line.draw()
            yes_draw: draw.CenterButton | draw.CenterDraw
            if ready.all:
                yes_draw = draw.CenterButton(
                    _("[执行委托]"),
                    _("执行委托"),
                    self.width,
                    cmd_func=self.send_commision,
                    args=(commision_id,),
                    normal_style="spring_green",
                )
                yes_draw.draw()
                return_list.append(yes_draw.return_text)
            else:
                yes_draw = draw.CenterDraw()
                yes_draw.text = _("[执行委托]")
                yes_draw.style = "deep_gray"
                yes_draw.width = self.width
                yes_draw.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), self.width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == _("执行委托") or yrn == back_draw.return_text:
                break

    def adjust_send_npc(self, commision_id: int) -> None:
        """打开外勤派遣人员选择界面。"""
        commission_squad_panel.adjust_team(self, commision_id)

    def select_this_npc(self, character_id: int) -> None:
        """切换指定干员的派遣选中状态并同步更新队长编号。"""
        self.lead_chara_id = field_commission_service.toggle_member(
            self.send_npc_list,
            getattr(self, "lead_chara_id", 0),
            character_id,
            self.now_commision_id,
        )

    def add_this_vehicle(self, vehicle_id: int) -> None:
        """将指定载具的派遣数量加一并受空闲数量限制。"""
        field_commission_service.add_vehicle(self.send_vehicle_dict, vehicle_id)

    def reduce_this_vehicle(self, vehicle_id: int) -> None:
        """将指定载具的派遣数量减一。"""
        field_commission_service.remove_vehicle(
            self.send_vehicle_dict, vehicle_id
        )

    def send_commision(self, commision_id: int) -> None:
        """校验人数、播报队长出发口上、执行派遣写入并显示返回提示。"""
        from Script.Design import second_behavior

        data = game_config.config_commission[commision_id]
        if len(self.send_npc_list) < data.people:
            return
        if self.lead_chara_id:
            field_commission_service.lead_first(
                self.send_npc_list, self.lead_chara_id
            )
            second_behavior.character_get_second_behavior(
                self.lead_chara_id, "start_field_commission_as_leader"
            )
            talk.must_show_talk_check(self.lead_chara_id)
        report = field_commission_service.dispatch(
            commision_id, self.send_npc_list, self.send_vehicle_dict
        )
        names = "".join(
            f"{identity.of(cid).name} " for cid in self.send_npc_list
        )
        info_draw = draw.WaitDraw()
        info_draw.text = (
            _("\n\n已派遣 ")
            + names
            + _("执行委托：")
            + data.name
            + _("，耗时：")
            + str(report.days)
            + _("天，将在 ")
            + game_time.get_date_until_day(report.returns_at)
            + _(" 返回\n\n")
        )
        info_draw.style = "gold_enrod"
        info_draw.width = window_width
        info_draw.draw()
        self.send_npc_list = []
        self.send_vehicle_dict = {}

    def adjust_send_vehicle(self, commision_capacity_int: int) -> None:
        """打开外勤载具选择界面。"""
        commission_squad_panel.adjust_vehicles(self, commision_capacity_int)
