"""
管理罗德岛面板（manage_basement_panel）
=======================================
提供管理罗德岛主面板与调整干员工作岗位面板的界面绘制与输入分发。
"""

from types import FunctionType

from Script.Config import game_config, normal_config
from Script.Core import constant, flow_handle, get_text
from Script.Modules.gameplay_resolution import (
    basement_overview_service as overview,
    work_assignment_service as assignment,
)
from Script.UI.Moudle import draw, view
from Script.UI.Panel import basement_roster_panel
from Script.UI.Panel.basement_roster_panel import draw_button, draw_text

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def change_npc_work_out(
    width: int, target_work_type_id: list[int] | None = None
) -> None:
    """打开调整干员工作岗位面板，可高亮并预展开指定岗位编号列表。"""
    now_panel = Change_Npc_Work_Panel(width, target_work_type_id)
    now_panel.draw()


def _back(return_list: list[str]) -> str:
    """绘制居中返回按钮并把其返回码加入 return_list。"""
    back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
    back_draw.draw()
    return_list.append(back_draw.return_text)
    return back_draw.return_text


class Manage_Basement_Panel:
    """管理罗德岛主面板，包含资源总览、部门概况与全干员一览三页。"""

    def __init__(self, width: int) -> None:
        """初始化管理罗德岛主面板的宽度、当前页签、资源折叠与干员页。"""
        self.width: int = width
        """ 面板内容区的显示宽度。 """
        self.now_panel = _("罗德岛资源总览")
        """ 当前选中的顶层页签名称。 """
        self.show_resource_type_dict: dict[str, bool] = {
            _("货币"): True,
            _("材料"): False,
            _("药剂"): False,
            _("乳制品"): False,
            _("香水"): False,
        }
        """ 五类资源在资源总览页中的展开状态映射。 """
        self.roster = basement_roster_panel.RosterTab(width)
        """ 全干员一览页签的 RosterTab 实例。 """

    def draw(self) -> None:
        """运行管理罗德岛主面板的绘制与输入循环，直至玩家返回场景。"""
        panel_list = [_("罗德岛资源总览"), _("各部门工作概况"), _("全干员一览")]
        title_draw = draw.TitleLineDraw(_("管理罗德岛"), self.width)
        tab_width = int(self.width / len(panel_list))
        while True:
            return_list: list[str] = []
            title_draw.draw()
            for now_panel in panel_list:
                if now_panel == self.now_panel:
                    now_draw = draw.CenterDraw()
                    now_draw.text = f"[{now_panel}]"
                    now_draw.style = "onbutton"
                    now_draw.width = tab_width
                    now_draw.draw()
                else:
                    draw_button(
                        return_list,
                        draw.CenterButton,
                        f"[{now_panel}]",
                        f"\n{now_panel}",
                        tab_width,
                        cmd_func=self.change_panel,
                        args=(now_panel,),
                    )
            line_feed.draw()
            draw.LineDraw("+", self.width).draw()
            if self.now_panel == panel_list[0]:
                self._draw_resources(return_list)
            elif self.now_panel == panel_list[1]:
                self._draw_departments(return_list)
            elif self.now_panel == panel_list[2]:
                self.roster.draw(return_list)
            line_feed.draw()
            line_feed.draw()
            back_text = _back(return_list)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_text:
                if self.roster.choosing_sort_mode != 0:
                    self.roster.choosing_sort_mode = 0
                else:
                    view.now_panel_id = constant.Panel.IN_SCENE
                    break
            else:
                self.roster.answer(yrn)

    def _draw_resources(self, return_list: list[str]) -> None:
        """绘制罗德岛资源总览页签的仓库容量与分类库存列表。"""
        draw_text(
            _(" 当前仓库容量（单资源存放上限）：{0}\n\n").format(
                overview.capacity()
            ),
            self.width,
        )
        for kind, shown in self.show_resource_type_dict.items():
            label = f" {'▼' if shown else '▶'}[{kind}]"
            draw_button(
                return_list,
                draw.LeftButton,
                label,
                kind,
                len(label) * 2,
                cmd_func=self.settle_show_resource_type,
                args=kind,
            )
            line_feed.draw()
            if shown:
                rows = overview.stock_rows(kind)
                text = "".join(f"\n  {name}：{amount}" for name, amount in rows)
                draw_text(text + "\n", self.width)
            line_feed.draw()

    def _draw_departments(self, return_list: list[str]) -> None:
        """绘制各部门工作概况页签的部门列表、子系统按钮与今日收入。"""
        systems = {
            _("动力区"): [_("[能源系统]")],
            _("工程部"): [_("[基建系统]"), _("[装备维护系统]")],
            _("宿舍区"): [_("[宿舍管理系统]")],
            _("生活娱乐区"): [_("[烹饪系统]")],
            _("制造加工区"): [_("[生产系统]")],
            _("图书馆"): [_("[图书馆管理系统]")],
            _("贸易区"): [_("[资源交易系统]")],
            _("文职部"): [_("[招募系统]")],
            _("教育区"): [_("[妊娠总览系统]"), _("[教育管理系统]")],
            _("医疗部"): [_("[医疗经营系统]"), _("[诊疗病人系统]")],
            _("访客区"): [_("[势力外交系统]"), _("[邀请访客系统]")],
            _("机库"): [_("[外勤委托系统]"), _("[载具管理系统]")],
            _("疗养庭院"): [_("[农业系统]")],
            _("关押区"): [_("[监禁调教系统]")],
        }
        working, total = overview.staffing()
        draw_text(
            _("\n 当前工作中干员/总干员：{0}/{1}").format(working, total)
            + _(
                "\n ↓点击[部门名]或[系统名]可查看对应详情，没有系统也没有工作的部门是未实装的空白部门\n\n"
            )
        )
        for department in overview.departments():
            label = f"[{department}]"
            draw_text("  ")
            draw_button(
                return_list,
                draw.CenterButton,
                label,
                f"\n{department}",
                max(len(label) * 2, 18),
                cmd_func=self.show_department,
                args=(department,),
            )
            draw_text("：")
            buttons = systems.get(department, [])
            for button_text in buttons:
                draw_button(
                    return_list,
                    draw.CenterButton,
                    button_text,
                    f"\n{button_text}",
                    max(len(button_text) * 2, 22),
                    cmd_func=self.jump_to_son_panel,
                    args=button_text,
                )
            for _blank in range(2 - len(buttons)):
                draw_text(" " * 22)
            draw_text("：")
            draw_text(overview.staff_text(department))
            line_feed.draw()
        draw_text(
            _("\n  截至目前为止，今日各部门龙门币总收入为：{0}\n\n").format(
                str(overview.income())
            ),
            self.width,
        )
        draw_button(
            return_list,
            draw.LeftButton,
            _("[001]调整干员岗位"),
            "\n1",
            self.width,
            cmd_func=change_npc_work_out,
            args=self.width,
        )

    def change_panel(self, now_panel: str) -> None:
        """将当前显示的顶层页签切换为 now_panel。"""
        self.now_panel = now_panel

    def jump_to_son_panel(self, son_panel: str) -> None:
        """校验子系统入口条件并打开对应子面板，不可进入时展示提示。"""
        from Script.UI.Panel import (
            agriculture_production_panel,
            building_panel,
            confinement_and_training,
            equipmen_panel,
            invite_visitor_panel,
            manage_assembly_line_panel,
            manage_dormitory_panel,
            manage_library,
            manage_power_system_panel,
            manage_vehicle_panel,
            nation_diplomacy_panel,
            recruit_panel,
            resource_exchange_panel,
        )
        from Script.System.Education_System import class_schedule_panel
        from Script.System.Field_Commission_System import field_commission_panel
        from Script.System.Medical_System import medical_department_panel
        from Script.System.Pregnancy_System import pregnancy_panel

        panels = {
            _("[基建系统]"): building_panel.Building_Panel,
            _(
                "[能源系统]"
            ): manage_power_system_panel.Manage_Power_System_Panel,
            _("[装备维护系统]"): equipmen_panel.Equipment_Maintain_Panel,
            _(
                "[生产系统]"
            ): manage_assembly_line_panel.Manage_Assembly_Line_Panel,
            _("[图书馆管理系统]"): manage_library.Manage_Library_Panel,
            _(
                "[资源交易系统]"
            ): resource_exchange_panel.Resource_Exchange_Line_Panel,
            _("[招募系统]"): recruit_panel.Recruit_Panel,
            _("[势力外交系统]"): nation_diplomacy_panel.Nation_Diplomacy_Panel,
            _("[邀请访客系统]"): invite_visitor_panel.Invite_Visitor_Panel,
            _("[外勤委托系统]"): field_commission_panel.Field_Commission_Panel,
            _("[载具管理系统]"): manage_vehicle_panel.Manage_Vehicle_Panel,
            _(
                "[农业系统]"
            ): agriculture_production_panel.Agriculture_Production_Panel,
            _("[宿舍管理系统]"): manage_dormitory_panel.Manage_Dormitory_Panel,
            _(
                "[监禁调教系统]"
            ): confinement_and_training.Confinement_And_Training_Manage_Panel,
            _(
                "[医疗经营系统]"
            ): medical_department_panel.Medical_Department_Panel,
            _("[妊娠总览系统]"): pregnancy_panel.Pregnancy_Overview_Panel,
            _("[教育管理系统]"): class_schedule_panel.Education_Manage_Panel,
        }
        notice = overview.entry_notice(son_panel)
        target = panels.get(son_panel)
        if notice is None and target is not None:
            target(self.width).draw()
            return
        info_draw = draw.WaitDraw()
        info_draw.text = notice or _(
            "\n○需要在医疗部-急诊室/门诊室中诊疗病人，无法在管理台直接诊疗病人\n"
        )
        info_draw.style = "gold_enrod"
        info_draw.width = self.width
        info_draw.draw()

    def show_department(self, department: str) -> None:
        """循环绘制单个部门的详细信息页，直至玩家点击返回。"""
        while True:
            draw.TitleLineDraw(department, self.width).draw()
            return_list: list[str] = []
            draw_text(overview.department_text(department), self.width)
            line_feed.draw()
            line_feed.draw()
            back_text = _back(return_list)
            if flow_handle.askfor_all(return_list) == back_text:
                break

    def settle_show_resource_type(self, resouce_type: str) -> None:
        """切换指定资源分类在资源总览页中的展开或折叠状态。"""
        self.show_resource_type_dict[resouce_type] = (
            not self.show_resource_type_dict[resouce_type]
        )


class Change_Npc_Work_Panel:
    """调整干员工作岗位面板，按岗位分组展示干员并提供岗位指派。"""

    def __init__(
        self, width: int, target_work_type_id: list[int] | None = None
    ) -> None:
        """初始化岗位调整面板的宽度、高亮岗位列表与各岗位展开状态。"""
        self.width: int = width
        """ 面板内容区的显示宽度。 """
        self.target_work_type_id_list: list[int] = target_work_type_id or []
        """ 需要高亮并默认展开的目标工作类型编号列表。 """
        self.work_type_state: dict[int, bool] = {
            wt_id: False for wt_id in game_config.config_work_type
        }
        """ 各工作类型编号对应的分组展开状态映射。 """
        self.work_type_state[0] = True
        for work_type_id in self.target_work_type_id_list:
            self.work_type_state[work_type_id] = True

    def _style(self, work_id: int) -> str:
        """为高亮列表中的岗位返回 gold_enrod 样式，其余返回 standard。"""
        if work_id in self.target_work_type_id_list:
            return "gold_enrod"
        return "standard"

    def draw(self) -> None:
        """循环刷新并绘制按岗位分组的干员列表，直至玩家点击返回。"""
        title_draw = draw.TitleLineDraw(_("调整干员工作岗位"), self.width)
        while True:
            title_draw.draw()
            groups = assignment.refresh_groups()
            return_list: list[str] = []
            for text, func in (
                (_("[展开所有类别]"), self.expand_all),
                (_("[收起所有类别]"), self.collapse_all),
            ):
                draw_button(
                    return_list,
                    draw.CenterButton,
                    text,
                    text,
                    len(text) * 2,
                    cmd_func=func,
                )
            line_feed.draw()
            line_feed.draw()
            draw_width = int(self.width / 7)
            for group in groups:
                expanded = self.work_type_state[group.work_id]
                draw_button(
                    return_list,
                    draw.LeftButton,
                    f"{'▼' if expanded else '▶'} {group.label}",
                    str(group.work_id),
                    draw_width,
                    normal_style=self._style(group.work_id),
                    cmd_func=self.toggle_work_type,
                    args=(group.work_id,),
                )
                for count, member in enumerate(
                    group.members if expanded else (), 1
                ):
                    draw_button(
                        return_list,
                        draw.LeftButton,
                        member.label,
                        member.name,
                        draw_width,
                        cmd_func=self.button_0,
                        args=(member.chara_id,),
                    )
                    if count % 6 == 0:
                        line_feed.draw()
                        draw_text(" " * (draw_width + 1))
                line_feed.draw()
            line_feed.draw()
            back_text = _back(return_list)
            line_feed.draw()
            if flow_handle.askfor_all(return_list) == back_text:
                break

    def toggle_work_type(self, work_type_id: int) -> None:
        """切换单个工作类型分组的展开或收起状态。"""
        self.work_type_state[work_type_id] = not self.work_type_state[
            work_type_id
        ]

    def expand_all(self) -> None:
        """展开所有工作类型分组。"""
        for key in self.work_type_state:
            self.work_type_state[key] = True

    def collapse_all(self) -> None:
        """收起所有工作类型分组。"""
        for key in self.work_type_state:
            self.work_type_state[key] = False

    def button_0(self, character_id: int) -> None:
        """绘制单个干员的当前工作与全部岗位选项，接受玩家指派或返回。"""
        while True:
            draw.LineDraw("-", window_width).draw()
            line_feed.draw()
            return_list: list[str] = []
            draw_text(assignment.current_work_text(character_id), window_width)
            for option in assignment.work_options(character_id):
                if option.pickable:
                    draw_button(
                        return_list,
                        draw.LeftButton,
                        option.text,
                        f"\n{option.work_id}",
                        window_width,
                        normal_style=self._style(option.work_id),
                        cmd_func=self.select_new_work,
                        args=(option.work_id, character_id),
                    )
                elif option.locked_reason is not None:
                    locked = draw.LeftDraw()
                    locked.text = option.text + _("（未开放：{0}）").format(
                        option.locked_reason
                    )
                    locked.style = "deep_gray"
                    locked.width = window_width
                    locked.draw()
                line_feed.draw()
            line_feed.draw()
            _back(return_list)
            line_feed.draw()
            if flow_handle.askfor_all(return_list) in return_list:
                break

    def select_new_work(self, work_id: int, character_id: int) -> None:
        """调用岗位指派服务将指定干员调整至目标工作类型。"""
        assignment.assign_work(character_id, work_id)
