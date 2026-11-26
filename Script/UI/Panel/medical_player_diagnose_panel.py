"""玩家亲自诊疗病人的界面面板模块，负责绘制诊疗界面与响应交互。"""

from __future__ import annotations

from collections.abc import Callable
from types import FunctionType

from Script.Config import normal_config
from Script.Core import constant, get_text, flow_handle
from Script.System.Medical_System import medical_core
from Script.System.Medical_System import (
    medical_player_diagnose_function as session,
)
from Script.Modules.gameplay_resolution import medical_diagnose_service as rules
from Script.Modules.gameplay_resolution import medical_diagnose_treatment
from Script.Modules.gameplay_resolution import medical_diagnose_view as texts
from Script.Modules.tk_ui import player_pick
from Script.UI.Moudle import draw, view
from Script.Modules.domains import medical_patient, identity

_: FunctionType = get_text._
""" 翻译函数 """
window_width: int = normal_config.config_normal.text_width
""" 默认面板宽度 """
line_feed = draw.NormalDraw()
""" 用于输出单个换行符的普通绘制对象。 """
line_feed.text = "\n"
line_feed.width = 1


@medical_core.edits
def start_player_diagnose_flow() -> bool:
    """在医疗编辑事务内创建并运行玩家诊疗面板，返回是否完成界面接管。"""
    panel = MedicalPlayerDiagnosePanel(window_width)
    return panel.draw()


class MedicalPlayerDiagnosePanel:
    """玩家亲自诊疗界面面板，负责渲染检查、治疗方案并调度会话操作。"""

    def __init__(self, width: int) -> None:
        """初始化面板状态，并在存在玩家角色时尝试开启新的诊疗会话。"""
        self.width = width
        self.player: identity.Identity | None = identity.get(0)
        self._checks_executed = 0
        self._reset_runtime_flags()
        patient = None
        if self.player is not None:
            patient = session.start_player_diagnose_session(self.player)
        if patient is not None:
            self._prepare_new_patient_session(patient)

    def _reset_runtime_flags(self) -> None:
        """重置单次诊疗会话的界面状态、展开项与检查上限字段。"""
        self.session_active = False
        self.patient: medical_patient.MedicalPatient | None = None
        self.feedback_text = ""
        self.last_check_results: list[dict[str, object]] = []
        self._should_close = False
        self._abort_requested = False
        self._awaiting_treatment_confirmation = False
        self.menu_expanded = False
        self.expanded_system_id: int | None = None
        self.expanded_part_id: int | None = None
        self._pending_continue_after_treatment = False
        self.executed_complication_ids: list[int] = []
        self.check_catalog: rules.Catalog = {}
        self.target_complication_count = 0
        self.max_parallel = 1
        self.max_checks = rules.check_limit(self.player)

    def _prepare_new_patient_session(
        self, patient: medical_patient.MedicalPatient
    ) -> None:
        """绑定新病人并初始化目标并发症数、并行检查上限与检查目录。"""
        self._reset_runtime_flags()
        self.patient = patient
        self.session_active = True
        self.target_complication_count = len(patient.complications)
        self.max_parallel = max(1, self.target_complication_count)
        self.check_catalog = session.build_player_check_catalog(patient)

    def draw(self) -> bool:
        """绘制医疗诊疗面板，无活跃会话时绘制无病人提示并返回，否则循环交互并在关闭前收尾。"""
        if not self.session_active:
            draw.TitleLineDraw(_("医疗诊疗"), self.width).draw()
            self._text(_("当前医疗部暂无可供博士亲自诊疗的病人。") + "\n")
            view.now_panel_id = constant.Panel.IN_SCENE
            return True
        while not self._should_close:
            self.max_checks = rules.check_limit(self.player)
            draw.TitleLineDraw(_("医疗诊疗"), self.width).draw()
            return_list: list[str] = []
            self._text(texts.help_text())
            if self.patient is not None:
                self._draw_session(self.patient, return_list)
            flow_handle.askfor_all(return_list)
        self._finalize_session()
        return True

    def _draw_session(
        self, patient: medical_patient.MedicalPatient, return_list: list[str]
    ) -> None:
        """按区块顺序绘制提示栏、患者概览、检查菜单、治疗方案与操作按钮。"""
        self._draw_hint_section(return_list)
        self._text(texts.overview_text(patient))
        line_feed.draw()
        limits = (self.max_checks, self.max_parallel)
        self._text(texts.check_status(patient, self.check_catalog, limits))
        self._draw_check_menu(patient, return_list)
        self._draw_treatment_methods(patient)
        self._draw_feedback()
        self._draw_operation_buttons(patient, return_list)

    def _text(self, text: str, style: str = "") -> None:
        """按面板宽度与可选样式创建普通文本对象并立即绘制。"""
        text_draw = draw.NormalDraw()
        text_draw.width = self.width
        if style:
            text_draw.style = style
        text_draw.text = text
        text_draw.draw()

    def _button(
        self,
        text: str,
        name: str,
        width: int,
        cmd_func: Callable[..., object],
        args: tuple[object, ...] = (),
        left: bool = False,
        style: str = "standard",
    ) -> str:
        """创建居中或左对齐按钮并立即绘制，返回按钮注册的回传文本。"""
        cls = draw.LeftButton if left else draw.CenterButton
        button = cls(
            text, name, width, normal_style=style, cmd_func=cmd_func, args=args
        )
        button.draw()
        return button.return_text

    def _draw_hint_section(self, return_list: list[str]) -> None:
        """绘制当前治病提示状态及切换提示按钮。"""
        value, __, options = rules.hint_context(self.player)
        self._text(texts.hint_status(value, options))
        toggle_text = _("[切换提示]")
        return_list.append(
            self._button(
                toggle_text,
                _("切换提示"),
                len(toggle_text) * 2 + 4,
                self._toggle_hint,
            )
        )
        line_feed.draw()
        line_feed.draw()

    def _draw_check_menu(
        self, patient: medical_patient.MedicalPatient, return_list: list[str]
    ) -> None:
        """按检查进度与展开状态绘制折叠式三级检查菜单或待检提示。"""
        hint, __, __ = rules.hint_context(self.player)
        marks = (
            self.executed_complication_ids,
            rules.highlights(patient, hint),
        )
        found = rules.confirmed(patient)
        target = self.target_complication_count
        if rules.used_checks(
            patient
        ) >= self.max_checks or not rules.undiagnosed(patient, target, found):
            self.menu_expanded = False
            self.expanded_system_id = None
            self.expanded_part_id = None
            pending = rules.pending_checks(patient)
            if pending:
                self._text(
                    _(
                        "已选择 {0} 项检查，执行后即可获得新的诊断线索。\n"
                    ).format(len(pending))
                )
                line_feed.draw()
            return
        label = (
            _(" [展开检查菜单]")
            if not self.menu_expanded
            else _(" [收起检查菜单]")
        )
        return_list.append(
            self._button(
                label,
                _("切换检查菜单"),
                max(len(label) * 2 + 4, 22),
                self._toggle_check_menu,
                left=True,
                style="standard" if self.menu_expanded else "gold_enrod",
            )
        )
        line_feed.draw()
        if not self.menu_expanded:
            line_feed.draw()
            return
        expanded = (self.expanded_system_id, self.expanded_part_id)
        actions = {
            "system": self._toggle_system_expand,
            "part": self._toggle_part_expand,
            "option": self._toggle_pending_option,
        }
        for row in texts.menu_rows(
            patient, self.check_catalog, expanded, marks
        ):
            if row.kind == "done":
                self._text(row.label, row.style)
            else:
                return_list.append(
                    self._button(
                        row.label,
                        row.name,
                        row.width or self.width,
                        actions[row.kind],
                        row.args,
                        True,
                        row.style,
                    )
                )
            line_feed.draw()
        line_feed.draw()

    def _toggle_check_menu(self) -> None:
        """切换检查菜单展开状态，收起时同步清空已展开的系统与部位。"""
        self.menu_expanded = not self.menu_expanded
        if not self.menu_expanded:
            self.expanded_system_id = None
            self.expanded_part_id = None

    def _toggle_system_expand(self, system_id: int) -> None:
        """展开或收起指定身体系统，同时重置当前展开的部位编号。"""
        if self.expanded_system_id == system_id:
            self.expanded_system_id = None
        else:
            self.expanded_system_id = system_id
        self.expanded_part_id = None

    def _toggle_part_expand(self, system_id: int, part_id: int) -> None:
        """展开或收起指定身体部位，跨系统点击时同步切换展开系统。"""
        if self.expanded_system_id != system_id:
            self.expanded_system_id = system_id
            self.expanded_part_id = part_id
        elif self.expanded_part_id == part_id:
            self.expanded_part_id = None
        else:
            self.expanded_part_id = part_id

    def _toggle_pending_option(
        self, system_id: int, part_id: int, complication_id: int
    ) -> None:
        """调用诊疗规则服务切换指定并发症在病人待检列表中的选中状态。"""
        if self.patient is None:
            return
        rules.toggle_pending(
            self.patient,
            self.check_catalog,
            (system_id, part_id, complication_id),
            (self.max_checks, self.max_parallel),
        )

    def _draw_treatment_methods(
        self, patient: medical_patient.MedicalPatient
    ) -> None:
        """绘制累计检查报告，以及达到展示条件时的治疗方案与未确诊提示。"""
        if self.last_check_results:
            self._text(_("检查报告一览：\n"))
            for outcome, style, suffix in texts.report_rows(
                self.last_check_results
            ):
                prefix_draw = draw.NormalDraw()
                prefix_draw.text = "·("
                prefix_draw.draw()
                outcome_draw = draw.NormalDraw()
                outcome_draw.text = outcome
                outcome_draw.style = style
                outcome_draw.draw()
                self._text(suffix)
            line_feed.draw()
        if not rules.confirmed(patient) and (
            rules.used_checks(patient) < self.max_checks
        ):
            return
        summary, notice = medical_diagnose_treatment.treatment_text(
            patient, self.check_catalog
        )
        self._text(summary)
        if notice:
            self._text(notice, "gold_enrod")
        line_feed.draw()

    def _draw_feedback(self) -> None:
        """反馈文本非空时以高亮样式绘制底部提示信息。"""
        if not self.feedback_text:
            return
        line_feed.draw()
        feedback_draw = draw.NormalDraw()
        feedback_draw.text = self.feedback_text + "\n"
        feedback_draw.style = "gold_enrod"
        feedback_draw.draw()
        line_feed.draw()

    def _draw_operation_buttons(
        self, patient: medical_patient.MedicalPatient, return_list: list[str]
    ) -> None:
        """将界面服务生成的操作按钮列表映射为面板回调并逐一绘制。"""
        actions = {
            "confirm": self._confirm_treatment_after_prompt,
            "cancel": self._cancel_treatment_confirmation,
            "execute": self._execute_checks,
            "clear": self._clear_pending,
            "treat": self._handle_treatment_request,
            "abort": self._handle_abort,
        }
        awaiting = self._awaiting_treatment_confirmation
        for text, name, key, args in texts.operation_buttons(
            patient, self.max_checks, awaiting
        ):
            return_list.append(
                self._button(text, name, self.width // 4, actions[key], args)
            )

    def _handle_treatment_request(self, continue_after: bool) -> None:
        """处理开药结束或接诊下一位请求，存在未确诊且有余次时触发二次确认。"""
        if self.patient is None or self.player is None:
            self._pending_continue_after_treatment = False
            return
        self._pending_continue_after_treatment = continue_after
        missing = rules.missing_count(
            self.patient,
            self.target_complication_count,
            rules.confirmed(self.patient),
        )
        remaining = self.max_checks - rules.used_checks(self.patient)
        if (
            not self._awaiting_treatment_confirmation
            and missing > 0
            and remaining > 0
        ):
            self._awaiting_treatment_confirmation = True
            self.feedback_text = _(
                "仍有 {count} 项疑似并发症尚未确诊，确认要直接结束治疗吗？"
            ).format(count=missing)
            return
        self._awaiting_treatment_confirmation = False
        self._execute_treatment_commit(continue_after=continue_after)

    def _confirm_treatment_after_prompt(self) -> None:
        """确认二次提示后按暂存的接诊意愿提交当前诊疗结果。"""
        if self.patient is None or self.player is None:
            return
        self._awaiting_treatment_confirmation = False
        self._execute_treatment_commit(
            continue_after=self._pending_continue_after_treatment
        )

    def _cancel_treatment_confirmation(self) -> None:
        """取消提前结束治疗确认并更新反馈提示以继续检查。"""
        self._awaiting_treatment_confirmation = False
        self._pending_continue_after_treatment = False
        self.feedback_text = _("已返回诊疗流程，可以继续安排检查。")

    def _execute_treatment_commit(self, *, continue_after: bool) -> None:
        """提交诊疗结算并更新反馈，按需衔接下一位病人或关闭面板。"""
        if self.patient is None or self.player is None:
            self._pending_continue_after_treatment = False
            return
        outcome = session.commit_player_diagnose_session(
            self.player, patient=self.patient
        )
        self._pending_continue_after_treatment = False
        if not outcome.get("success"):
            self.feedback_text = _("治疗操作失败：{0}").format(
                outcome.get("reason", "unknown")
            )
            return
        message = medical_diagnose_treatment.treatment_message(
            outcome, self.patient
        )
        next_patient = None
        if continue_after:
            next_patient = session.start_player_diagnose_session(self.player)
        if next_patient is not None:
            self.feedback_text = message + _(
                "已为博士安排下一位病人，请继续诊疗。"
            )
            self._draw_feedback()
            self._prepare_new_patient_session(next_patient)
            return
        if continue_after:
            message += _(" 当前暂无其他病人需要诊疗，流程已结束。")
        self.feedback_text = message
        self._should_close = True
        self._draw_feedback()

    def _toggle_hint(self) -> None:
        """请求切换治病提示档位，无法切换时将反馈写入面板。"""
        feedback = rules.next_hint(self.player)
        if feedback is not None:
            self.feedback_text = feedback

    def _clear_pending(self) -> None:
        """清空当前病人的待执行检查列表。"""
        if self.patient is not None:
            self.patient.player_pending_checks = []

    def _execute_checks(self) -> None:
        """提交当前待检列表执行检查，成功后记录已检项、结果并自动收起菜单。"""
        if self.patient is None:
            return
        pending = rules.pending_checks(self.patient)
        if not pending:
            return
        result = session.execute_player_diagnose_checks(
            pending, patient=self.patient
        )
        if not result.get("success"):
            self.feedback_text = _("执行检查失败：{0}").format(
                result.get("reason", "unknown")
            )
            return
        rules.mark_executed(self.executed_complication_ids, pending)
        self.last_check_results.extend(rules.check_results(result))
        self._checks_executed += 1
        if self.menu_expanded:
            self._toggle_check_menu()

    def _handle_abort(self) -> None:
        """中止当前诊疗会话并标记关闭，存在活跃患者时通知会话层并绘制反馈。"""
        if self.patient is None or self.player is None:
            self._should_close = True
            self._abort_requested = True
            return
        self._awaiting_treatment_confirmation = False
        session.abort_player_diagnose_session(self.player, patient=self.patient)
        self.feedback_text = _("已结束本次诊疗流程。")
        self._draw_feedback()
        self._abort_requested = True
        self._should_close = True

    def _finalize_session(self) -> None:
        """切回场景面板，零检查中止时回退选择，并按检查轮数执行通用行为结算。"""
        view.now_panel_id = constant.Panel.IN_SCENE
        if self._abort_requested and self._checks_executed == 0:
            player_pick.back()
        duration = rules.session_minutes(self._checks_executed)
        from Script.System.Instruct_System.handle_instruct import (
            chara_handle_instruct_common_settle,
        )

        if self._abort_requested:
            chara_handle_instruct_common_settle(
                constant.Behavior.WAIT, duration=duration, force_taget_wait=True
            )
        else:
            chara_handle_instruct_common_settle(
                constant.Behavior.CURE_PATIENT,
                duration=duration,
                force_taget_wait=False,
            )
