"""
身体检查与管理界面面板。
本模块负责体检、身体管理、日程设置与检查报告的界面绘制和输入交互。
业务规则、报告拼接与状态读写委托给 physical_exam_service、physical_exam_report 与 body_manage_service。
"""

from types import FunctionType

from Script.Config import game_config, normal_config
from Script.Core import constant, flow_handle, get_text, py_cmd
from Script.Design import handle_premise
from Script.Modules.domains import activity, identity, physical_exam
from Script.Modules.gameplay_resolution import body_manage_service as manage
from Script.Modules.gameplay_resolution import physical_exam_report
from Script.Modules.gameplay_resolution import physical_exam_service as svc
from Script.System.Instruct_System import handle_instruct
from Script.UI.Moudle import draw, panel, view
from Script.UI.Panel import achievement_panel

_: FunctionType = get_text._
""" 本地化翻译函数。 """
line_feed = draw.NormalDraw()
""" 用于输出单个换行的通用绘制对象。 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 全局配置的界面文本宽度。 """


def _gray(text: str, width: int) -> None:
    """以深灰色样式绘制禁用提示文本。"""
    now_draw = draw.NormalDraw()
    now_draw.text = text
    now_draw.style = "deep_gray"
    now_draw.width = width
    now_draw.draw()


def _back(return_list: list[str]) -> str:
    """绘制居中的返回按钮并记录其返回文本。"""
    line_feed.draw()
    back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
    back_draw.draw()
    line_feed.draw()
    return_list.append(back_draw.return_text)
    return back_draw.return_text


def _button(
    return_list: list[str], text: str, cmd: str, width: int, func, args=()
) -> None:
    """换行后绘制左对齐按钮并记录其返回文本。"""
    button = draw.LeftButton(_(text), cmd, width, cmd_func=func, args=args)
    line_feed.draw()
    button.draw()
    return_list.append(button.return_text)


class Physical_Check_And_Manage_Panel:
    """身体检查与管理主面板类，协调各子页面的绘制与输入循环。"""

    def __init__(self, width: int) -> None:
        """初始化面板宽度、主角身份缓存与当前目标已完成检查集合。"""
        self.width: int = width
        """ 面板绘制宽度。 """
        self.pl_character_data = identity.of(0)
        """ 主角身份数据对象。 """
        self.done_check_behavior_id_set: set[str] = svc.done_checks(
            activity.target(self.pl_character_data.cid)
        )
        """ 当前查看对象已完成的检查行为编号集合。 """

    def draw(self) -> None:
        """绘制身体检查与管理主菜单并响应选择，返回时调用 finish_exam 结束本次体检。"""
        title_draw = draw.TitleLineDraw(_("身体检查与管理"), self.width)
        while True:
            self.pl_character_data = identity.of(0)
            target_id = activity.target(self.pl_character_data.cid)
            name = identity.of(target_id).name
            return_list: list[str] = []
            title_draw.draw()
            info_draw = draw.NormalDraw()
            info_draw.text = _("\n要做什么呢？\n")
            info_draw.draw()
            self.done_check_behavior_id_set = svc.done_checks(target_id)
            done = self.done_check_behavior_id_set
            if target_id in physical_exam.checks(physical_exam.TODAY):
                _gray(_("[001]检查身体情况（今日已体检）"), self.width)
            elif handle_premise.handle_have_target(0):
                text = _("[001]检查{0}的身体情况").format(name)
                _button(
                    return_list,
                    text,
                    _("1"),
                    self.width,
                    self.check_target_physical,
                    (target_id,),
                )
            else:
                _gray(_("[001]检查身体情况（当前没有查看对象）"), self.width)
            if len(done) > 0:
                text = _("[002]对{0}进行身体管理").format(name)
                _button(
                    return_list,
                    text,
                    _("2"),
                    self.width,
                    self.manage_target_physical,
                    (target_id,),
                )
            else:
                text = _("\n[002]进行身体管理（需要先进行身体检查）")
                _gray(text, self.width)
            text = _("[003]取消身体管理")
            _button(
                return_list,
                text,
                _("3"),
                window_width,
                self.cancle_physical_manage_panel,
            )
            text = _("[004]调整体检日程")
            _button(
                return_list,
                text,
                _("4"),
                window_width,
                self.adjust_physical_check_schedule,
            )
            if len(done) > 0:
                text = _("[011]查看检查报告")
                _button(
                    return_list,
                    text,
                    _("11"),
                    window_width,
                    self.check_physcial_report,
                )
            else:
                _gray(
                    _("\n[011]查看检查报告（需要先进行身体检查）"), window_width
                )
            back = _back(return_list)
            if flow_handle.askfor_all(return_list) == back:
                svc.finish_exam(target_id, done)
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def check_target_physical(self, target_character_id: int) -> None:
        """绘制目标角色的身体检查项目列表与剩余次数并等待玩家选择。"""
        name = identity.of(target_character_id).name
        while True:
            return_list: list[str] = []
            line_feed.draw()
            draw.LineDraw("-", window_width).draw()
            py_cmd.clr_cmd()
            done = self.done_check_behavior_id_set
            done_times, total_times = svc.check_quota(done)
            info_text = _(
                "\n已进行的/共可进行的检查次数：{0}/{1}（每级医术技能+4）\n"
            ).format(done_times, total_times)
            info_text += _("请选择要对{0}进行的身体检查：\n\n").format(name)
            info_draw = draw.NormalDraw()
            info_draw.text = info_text
            info_draw.draw()
            for row in svc.check_rows(target_character_id, done):
                if not row.enabled:
                    _gray(row.label, window_width)
                else:
                    status_draw = draw.LeftButton(
                        _(row.label),
                        str(row.number),
                        window_width,
                        normal_style="pink" if row.harassment else "standard",
                        cmd_func=self.settle_target_physical_status,
                        args=(row.behavior_id),
                    )
                    status_draw.draw()
                    return_list.append(status_draw.return_text)
                line_feed.draw()
            back = _back(return_list)
            if flow_handle.askfor_all(return_list) == back:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def settle_target_physical_status(self, behavior_id: str) -> None:
        """记录单项身体检查、展示成就提示并调用指令结算流程。"""
        examined_id = activity.target(self.pl_character_data.cid)
        achieved = svc.record_check(examined_id, behavior_id)
        self.done_check_behavior_id_set = svc.done_checks(examined_id)
        draw.LineDraw("-", window_width).draw()
        line_feed.draw()
        achievement_panel.draw_achievement_notice(achieved)
        if "测试" in game_config.config_behavior[behavior_id].tag:
            handle_instruct.chara_handle_instruct_common_settle(
                behavior_id, judge=_("初级骚扰"), force_taget_wait=True
            )
        else:
            handle_instruct.chara_handle_instruct_common_settle(
                behavior_id, force_taget_wait=True
            )

    def manage_target_physical(self, target_character_id: int) -> None:
        """确保目标管理表完整后绘制身体管理项目列表并处理选择。"""
        manage.ensure_table(target_character_id)
        name = identity.of(target_character_id).name
        while True:
            return_list: list[str] = []
            line_feed.draw()
            draw.LineDraw("-", window_width).draw()
            info_draw = draw.NormalDraw()
            info_draw.text = _(
                "\n请选择要对{0}进行的身体管理（管理的条件中达成任意一项即可）：\n\n"
            ).format(name)
            info_draw.draw()
            done = self.done_check_behavior_id_set
            for row in manage.manage_rows(target_character_id, done):
                if not row.available:
                    _gray(row.label, window_width)
                    continue
                manage_draw = draw.LeftButton(
                    _(row.label),
                    str(row.number),
                    window_width,
                    cmd_func=self.settle_target_physical_manage,
                    args=(row.manage_id, target_character_id),
                )
                return_list.append(manage_draw.return_text)
                manage_draw.draw()
                line_feed.draw()
            back = _back(return_list)
            if flow_handle.askfor_all(return_list) == back:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def settle_target_physical_manage(
        self, manage_cid: int, target_character_id: int
    ) -> None:
        """切换身体管理项、显示结果文本并结算 1 分钟等待指令。"""
        info_draw = draw.WaitDraw()
        info_draw.text = manage.toggle(manage_cid, target_character_id)
        info_draw.draw()
        handle_instruct.chara_handle_instruct_common_settle(
            constant.Behavior.WAIT, duration=1, force_taget_wait=True
        )

    def cancle_physical_manage_panel(self) -> None:
        """打开受管干员分页选择界面以批量取消身体管理。"""
        info_text = _("请选择要取消身体管理的干员，将取消其全部管理：\n")
        self._select_npc(
            _("取消身体管理"),
            lambda: [
                [npc_id, self.cancle_physical_manage, []]
                for npc_id in manage.managed_npcs()
            ],
            info_text,
        )

    def cancle_physical_manage(self, target_character_id: int) -> None:
        """将指定干员的全部身体管理重置为关闭并展示生效提示。"""
        manage.cancel_all(target_character_id)
        info_draw = draw.WaitDraw()
        info_draw.text = _(
            "\n取消了对{0}的全部身体管理，将在明天睡醒后生效。\n"
        ).format(identity.of(target_character_id).name)
        info_draw.draw()

    def adjust_physical_check_schedule(self) -> None:
        """绘制体检日程设置列表并分发选项说明、切换与子名单入口。"""
        title_draw = draw.TitleLineDraw(_("调整体检日程"), self.width)
        while True:
            return_list: list[str] = []
            line_feed.draw()
            title_draw.draw()
            now_draw = draw.NormalDraw()
            now_draw.text = _(
                " \n ○点击[选项标题]显示[选项介绍]，点击[选项本身]即可[改变该选项]\n"
            )
            now_draw.width = self.width
            now_draw.draw()
            for row in svc.setting_rows():
                line_feed.draw()
                cid = row.setting_id
                text = f"  [{row.name}]： "
                self._setting_button(
                    return_list, text, text, 60, self.draw_info, (cid)
                )
                text = f" [{row.option}] "
                self._setting_button(
                    return_list,
                    text,
                    str(cid) + text,
                    20,
                    self.change_setting,
                    (cid, row.option_count),
                )
                if row.roster_size is not None:
                    text = _("[调整干员名单]({0}人)").format(row.roster_size)
                    func = self.adjust_target_list
                elif row.day_count is not None:
                    text = _("[调整体检日]({0}天)").format(row.day_count)
                    func = self.adjust_physical_exam_date
                else:
                    continue
                button_draw = draw.CenterButton(
                    text,
                    str(cid) + text,
                    max(len(text) * 2, 20),
                    cmd_func=func,
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)
            line_feed.draw()
            back = _back(return_list)
            if flow_handle.askfor_all(return_list) == back:
                break

    @staticmethod
    def _setting_button(
        return_list: list[str], text: str, cmd: str, least: int, func, args
    ) -> None:
        """绘制日程设置页中的左对齐按钮并追加到返回值列表。"""
        button_draw = draw.LeftButton(
            text, cmd, max(len(text) * 2, least), cmd_func=func, args=args
        )
        button_draw.draw()
        return_list.append(button_draw.return_text)

    def check_physcial_report(self) -> None:
        """记录报告查看成就后绘制目标角色的体检报告与成就提示。"""
        target_character_id = activity.target(self.pl_character_data.cid)
        achieved = svc.record_report(target_character_id)
        self.draw_report(target_character_id)
        achievement_panel.draw_achievement_notice(achieved)

    def draw_report(self, target_character_id: int) -> None:
        """调用 physical_exam_report 生成并循环绘制体检报告页面。"""
        report_text = physical_exam_report.report_text(
            target_character_id,
            self.done_check_behavior_id_set,
            self.pl_character_data.name,
        )
        while True:
            draw.TitleLineDraw("检查报告", self.width).draw()
            report_draw = draw.NormalDraw()
            report_draw.text = report_text
            report_draw.draw()
            return_list: list[str] = []
            back = _back(return_list)
            if flow_handle.askfor_all(return_list) == back:
                break

    def draw_info(self, cid: int) -> None:
        """在分割线之间展示指定体检日程设置项的说明文本。"""
        draw.LineDraw("-", self.width).draw()
        now_draw = draw.WaitDraw()
        now_draw.text = (
            f"\n {game_config.config_physical_exam_setting[cid].info}\n"
        )
        now_draw.width = self.width
        now_draw.draw()
        draw.LineDraw("-", self.width).draw()

    def change_setting(self, cid: int, option_len: int) -> None:
        """循环切换常规体检设置，对每日人数设置弹出数字输入框。"""
        if cid != svc.DAILY_COUNT:
            svc.cycle_setting(cid, option_len)
            return
        line_feed.draw()
        draw.LineDraw("-", self.width).draw()
        line_feed.draw()
        ask_panel = panel.AskForOneMessage()
        ask_panel.set(_("请输入1~10的数字\n"), 99)
        svc.set_daily_count(ask_panel.draw())

    def adjust_target_list(self) -> None:
        """打开体检对象名单分页选择界面。"""

        def entries() -> list[list]:
            """生成体检对象名单分页所需的候选干员条目列表。"""
            chosen = list(physical_exam.ids(physical_exam.CHOSEN))
            return [
                [npc_id, self.switch_chara_in_target_list, chosen]
                for npc_id in svc.exam_candidates()
            ]

        self._select_npc(_("体检对象名单"), entries)

    @staticmethod
    def _select_npc(title: str, entries, info_text: str = "") -> None:
        """运行通用干员分页选择循环直至玩家返回。"""
        from Script.UI.Panel import common_select_NPC

        now_draw_panel: panel.PageHandlePanel = panel.PageHandlePanel(
            [],
            common_select_NPC.CommonSelectNPCButtonList,
            50,
            5,
            window_width,
            True,
            False,
            0,
        )
        select_state: dict[str, int | str] = {}
        while True:
            now_draw_panel.text_list = entries()
            return_list, _other, select_state = (
                common_select_NPC.common_select_npc_button_list_func(
                    now_draw_panel, title, info_text, select_state
                )
            )
            if flow_handle.askfor_all(return_list) == _("返回"):
                break

    def switch_chara_in_target_list(self, character_id: int) -> None:
        """切换指定干员在手动体检名单中的选中状态。"""
        svc.toggle_chosen(character_id)

    def adjust_physical_exam_date(self) -> None:
        """绘制周一至周日按钮列表并循环处理体检日切换。"""
        week_data = game_config.config_week_day
        while True:
            line_feed.draw()
            draw.LineDraw("-", window_width).draw()
            line_feed.draw()
            return_list: list[str] = []
            info_draw = draw.NormalDraw()
            info_draw.text = _("请选择体检日期：\n")
            info_draw.draw()
            for week_id in range(7):
                draw_text = f" [{week_id}]{week_data[week_id].name}"
                draw_style = "standard"
                if week_id in physical_exam.week_days():
                    draw_text += _("(已选择)")
                    draw_style = "gold_enrod"
                week_draw = draw.LeftButton(
                    draw_text,
                    str(week_id),
                    window_width,
                    normal_style=draw_style,
                    cmd_func=self.set_physical_exam_date,
                    args=(week_id),
                )
                return_list.append(week_draw.return_text)
                week_draw.draw()
                line_feed.draw()
            back = _back(return_list)
            if flow_handle.askfor_all(return_list) == back:
                break

    def set_physical_exam_date(self, week_id: int) -> None:
        """切换指定星期编号的体检日状态。"""
        physical_exam.toggle_week_day(week_id)
