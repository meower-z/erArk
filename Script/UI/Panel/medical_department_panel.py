# -*- coding: UTF-8 -*-
"""医疗经营系统 UI 面板

该模块提供医疗部总面板及其子页面，便于玩家在单一入口管理医生排班、
收费系数、病患与手术以及财务信息。"""

from __future__ import annotations

from typing import Any, cast
from types import FunctionType
from Script.Core import get_text, flow_handle, constant
from Script.Config import normal_config
from Script.UI.Moudle import draw, view
from Script.System.Medical_System import medical_constant, medical_service
from Script.Modules.gameplay_resolution import medical_department_service
from Script.Modules.gameplay_resolution import medical_management_service

_: FunctionType = get_text._
""" 翻译函数 """
window_width: int = normal_config.config_normal.text_width
""" 默认面板宽度 """
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1


def _draw_text(text: str, width: int) -> None:
    """按指定宽度创建普通文本绘制对象并立即绘制。"""
    now_draw = draw.NormalDraw()
    now_draw.width = width
    now_draw.text = text
    now_draw.draw()


def _draw_feedback(text: str, width: int) -> None:
    """反馈文本非空时前后补换行并按指定宽度绘制。"""
    if text:
        _draw_text(f"\n{text}\n", width)


class Medical_Department_Panel:
    """医疗部总面板，负责导航至各子页面"""

    def __init__(self, width: int) -> None:
        """初始化面板并建立即插即用的子面板

        参数:
            width (int): 面板绘制宽度。
        返回:
            None
        """

        self.width = width
        self.panel_order: list[str] = [
            _("经营概览"),
            _("医生管理"),
            _("收费设置"),
            _("医疗明细"),
            _("手术管理"),
            _("财务报表"),
        ]
        self.current_panel: str = self.panel_order[0]
        self.sub_panels: dict[str, _BaseSubPanel] = {
            self.panel_order[0]: OverviewSubPanel(width),
            self.panel_order[1]: DoctorManagementSubPanel(width),
            self.panel_order[2]: PriceSettingSubPanel(width),
            self.panel_order[3]: MedicalDetailSubPanel(width),
            self.panel_order[4]: SurgeryManagementSubPanel(width),
            self.panel_order[5]: FinanceReportSubPanel(width),
        }

    @medical_service.edits
    def draw(self) -> None:
        """绘制医疗部总面板并响应用户输入"""

        title_draw = draw.TitleLineDraw(_("医疗经营系统"), self.width)

        while True:
            return_list: list[str] = []
            title_draw.draw()

            for panel_name in self.panel_order:
                if panel_name == self.current_panel:
                    now_draw = draw.CenterDraw()
                    now_draw.text = f"[{panel_name}]"
                    now_draw.style = "onbutton"
                    now_draw.width = max(
                        12, int(self.width / len(self.panel_order))
                    )
                    now_draw.draw()
                else:
                    button_draw = draw.CenterButton(
                        f"[{panel_name}]",
                        panel_name,
                        max(12, int(self.width / len(self.panel_order))),
                        cmd_func=self.switch_panel,
                        args=(panel_name,),
                    )
                    button_draw.draw()
                    return_list.append(button_draw.return_text)
            line_feed.draw()
            draw.LineDraw("+", self.width).draw()
            line_feed.draw()

            sub_panel = self.sub_panels[self.current_panel]
            sub_return_list = sub_panel.draw()
            return_list.extend(sub_return_list)

            line_feed.draw()
            back_button = draw.CenterButton(
                _("[返回]"), _("返回"), window_width
            )
            back_button.draw()
            return_list.append(back_button.return_text)

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_button.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def switch_panel(self, panel_name: str) -> None:
        """切换当前显示的子面板"""

        if panel_name in self.sub_panels:
            self.current_panel = panel_name


class _BaseSubPanel:
    """子面板基类，提供统一接口"""

    def __init__(self, width: int) -> None:
        """
        初始化子面板
        Keyword arguments:
        width -- 绘制宽度
        Return arguments:
        无
        """
        self.width = width

    def draw(self) -> list[str]:
        """绘制子面板内容并返回交互按钮列表"""

        raise NotImplementedError()


class OverviewSubPanel(_BaseSubPanel):
    """经营概览子面板，汇总医疗部关键指标"""

    def draw(self) -> list[str]:
        """绘制经营概览页的摘要、状态统计与药品扣除缓存文本。"""
        _draw_text(medical_department_service.overview_text(), self.width)
        line_feed.draw()
        _draw_text(medical_department_service.overview_state_text(), self.width)
        line_feed.draw()
        _draw_text(medical_department_service.overview_cache_text(), self.width)
        return []


class DoctorManagementSubPanel(_BaseSubPanel):
    """医生管理子面板，提供手动调配与分科"""

    def __init__(self, width: int) -> None:
        """初始化医生管理子面板并置空操作反馈文本。"""
        super().__init__(width)
        self.feedback_text: str = ""

    def draw(self) -> list[str]:
        """绘制医生管理页面并返回所有按钮的返回值列表"""

        return_list: list[str] = []
        _draw_text(medical_management_service.doctor_text(), self.width)
        line_feed.draw()

        from Script.UI.Panel import manage_basement_panel

        adjust_button = draw.CenterButton(
            _("[医生增减]"),
            _("医生增减"),
            max(len(_("[医生增减]")) * 2, 16),
            cmd_func=manage_basement_panel.change_npc_work_out,
            args=(
                self.width,
                [
                    medical_constant.MedicalDoctorProfession.CLINICIAN,
                    medical_constant.MedicalDoctorProfession.HOSPITALIST,
                ],
            ),
        )
        adjust_button.draw()
        return_list.append(adjust_button.return_text)
        line_feed.draw()
        line_feed.draw()

        priority_mode = medical_service.get_patient_priority_mode()
        _draw_text(
            medical_management_service.priority_text(priority_mode),
            self.width,
        )
        for mode, label in medical_constant.PRIORITY_OPTIONS:
            if mode == priority_mode:
                now_draw = draw.CenterDraw()
                now_draw.text = f"[{label}]"
                now_draw.style = "onbutton"
                now_draw.width = max(len(label) * 2 + 4, 16)
                now_draw.draw()
            else:
                button = draw.CenterButton(
                    f"[{label}]",
                    label,
                    max(len(label) * 2 + 4, 16),
                    cmd_func=self._set_priority_mode,
                    args=(mode,),
                )
                button.draw()
                return_list.append(button.return_text)
        line_feed.draw()
        line_feed.draw()

        _draw_text(
            _(
                "○全科医生看诊与治疗所有病人，但效率较低，专科医生仅看诊与治疗对应分科病人，效率更高。\n"
            ),
            self.width,
        )
        line_feed.draw()
        self._draw_specialization_section(
            medical_constant.SPECIALIZATION_ROLE_CLINIC, return_list
        )
        line_feed.draw()
        if medical_management_service.shows_hospital_specialties():
            self._draw_specialization_section(
                medical_constant.SPECIALIZATION_ROLE_HOSPITAL, return_list
            )
            line_feed.draw()

        _draw_feedback(self.feedback_text, self.width)
        return return_list

    def _draw_specialization_section(
        self, role_key: str, return_list: list[str]
    ) -> None:
        """绘制指定岗位的医生分科信息并提供分配按钮"""

        rows = medical_management_service.specialty_rows(role_key)
        _draw_text(
            medical_management_service.specialty_heading(role_key), self.width
        )
        for row in rows:
            _draw_text(row.summary, self.width)
            button_text = _("[分配]")
            assign_button = draw.CenterButton(
                button_text,
                row.return_text,
                max(len(button_text) * 2, 10),
                cmd_func=self._prompt_assign,
                args=(role_key, row.category_key),
            )
            assign_button.draw()
            return_list.append(assign_button.return_text)
            _draw_text(row.doctors, self.width)
            line_feed.draw()

    def _prompt_assign(self, role_key: str, category_key: str) -> None:
        """弹出干员选择面板，将医生调整至指定分科"""

        doctor_ids = medical_service.list_role_doctors(role_key)
        if not doctor_ids:
            self.feedback_text = get_text._("当前岗位没有可分配的医生。")
            return

        target = medical_management_service.assign_target(
            role_key, category_key
        )

        from Script.UI.Panel import common_select_NPC
        from Script.UI.Moudle import panel

        select_panel = panel.PageHandlePanel(
            [],
            common_select_NPC.CommonSelectNPCButtonList,
            50,
            5,
            self.width,
            True,
            False,
            0,
        )
        select_state: dict[str, Any] = {}
        result_holder: dict[str, bool] = {"done": False}

        def _assign(doctor_id: int) -> None:
            self.feedback_text = medical_management_service.assign_doctor(
                target, doctor_id
            )
            result_holder["done"] = True

        while True:
            entries: list[list[Any]] = [
                [doctor_id, _assign, list(target.assigned_ids)]
                for doctor_id in doctor_ids
            ]
            select_panel.text_list = cast(list[Any], entries)
            return_options, _, select_state = (
                common_select_NPC.common_select_npc_button_list_func(
                    select_panel,
                    get_text._("分配医生"),
                    medical_management_service.assign_prompt(target),
                    select_state,
                )
            )
            if not return_options:
                break
            choice = flow_handle.askfor_all(return_options)
            if choice == get_text._("返回"):
                break
            if result_holder.get("done"):
                break

    def _set_priority_mode(
        self, mode: medical_constant.MedicalPatientPriority
    ) -> None:
        """切换病人接诊优先策略并提示结果"""
        medical_service.set_patient_priority_mode(mode)


class PriceSettingSubPanel(_BaseSubPanel):
    """收费设置子面板，维护医疗价格与预测信息"""

    def __init__(self, width: int) -> None:
        """初始化收费设置子面板并置空操作反馈文本。"""
        super().__init__(width)
        self.feedback_text: str = ""

    def draw(self) -> list[str]:
        """绘制收费设置面板并返回交互按钮列表"""

        return_list: list[str] = []
        _draw_text(medical_management_service.price_text(), self.width)
        line_feed.draw()

        adjust_options = [
            (-10, _("-10%")),
            (-5, _("-5%")),
            (-1, _("-1%")),
            (1, _("+1%")),
            (5, _("+5%")),
            (10, _("+10%")),
        ]
        for delta, label in adjust_options:
            button = draw.CenterButton(
                f"[{label}]",
                label,
                max(len(label) * 2 + 4, 10),
                cmd_func=self._adjust_ratio,
                args=(delta,),
            )
            button.draw()
            return_list.append(button.return_text)

        reset_button = draw.CenterButton(
            _("[重置为100%]"),
            _("重置收费"),
            max(len(_("[重置为100%]")) * 2, 18),
            cmd_func=self._reset_ratio,
        )
        reset_button.draw()
        return_list.append(reset_button.return_text)
        line_feed.draw()

        _draw_feedback(self.feedback_text, self.width)
        return return_list

    def _adjust_ratio(self, delta_percent: int) -> None:
        """按百分比调整收费系数并刷新提示"""

        self.feedback_text = medical_management_service.adjust_price_ratio(
            delta_percent
        )

    def _reset_ratio(self) -> None:
        """将收费系数重置为 1.0"""

        self.feedback_text = medical_management_service.reset_price_ratio()


class MedicalDetailSubPanel(_BaseSubPanel):
    """医疗明细子面板，可查看病患分布与药品缓存"""

    def draw(self) -> list[str]:
        """绘制医疗明细并返回交互按钮列表"""

        _draw_text(medical_department_service.detail_state_text(), self.width)
        line_feed.draw()
        _draw_text(medical_department_service.pending_text(), self.width)
        line_feed.draw()
        _draw_text(medical_department_service.detail_cache_text(), self.width)
        return []


class SurgeryManagementSubPanel(_BaseSubPanel):
    """手术管理子面板，展示待手术与历史记录"""

    def draw(self) -> list[str]:
        """绘制手术管理界面"""

        _draw_text(medical_department_service.surgery_text(), self.width)
        line_feed.draw()
        _draw_text(medical_department_service.surgery_record_text(), self.width)
        return []


class FinanceReportSubPanel(_BaseSubPanel):
    """财务报表子面板，输出医疗收入与用药预估"""

    def draw(self) -> list[str]:
        """绘制财务报表信息"""

        _draw_text(medical_department_service.finance_text(), self.width)
        line_feed.draw()
        _draw_text(medical_department_service.medicine_need_text(), self.width)
        line_feed.draw()
        log_button = draw.LeftButton(
            _("[401]查看最近经营日志"),
            _("查看最近经营日志"),
            self.width,
            cmd_func=self._show_recent_reports,
        )
        log_button.draw()
        line_feed.draw()
        return [log_button.return_text]

    def _show_recent_reports(self) -> None:
        """弹出最近几日的医疗经营日志"""
        wait_draw = draw.WaitDraw()
        wait_draw.width = self.width
        wait_draw.text = medical_department_service.recent_reports_text()
        wait_draw.draw()
