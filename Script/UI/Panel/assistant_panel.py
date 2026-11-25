"""
助理选择与助理服务调整界面面板。
本模块负责界面绘制、玩家输入交互以及早安与晚安服务预定时间设置，并将助理业务规则委托给 assistant_service。
"""

from types import FunctionType
from Script.Core import constant, flow_handle
from Script.Core import get_text, py_cmd
from Script.UI.Moudle import draw, panel, view
from Script.Modules.domains import action_info, relations
from Script.Modules.gameplay_resolution import assistant_service
from Script.Config import game_config, normal_config

from Script.Modules.domains import identity

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def chose_assistant() -> None:
    """选择助理"""
    from Script.UI.Panel import common_select_NPC

    now_draw_panel: panel.PageHandlePanel = panel.PageHandlePanel(
        [],
        common_select_NPC.CommonSelectNPCButtonList,
        80,
        8,
        window_width,
        True,
        False,
        0,
    )
    select_state: dict[str, int | str] = {}
    while 1:
        assistant_id = relations.assistant_character_id(0)
        target_data: identity.Identity = identity.of(assistant_id)
        if assistant_id != 0:
            now_npc_text = _("当前助理为 [{0}]{1}，请选择新的助理：\n").format(
                str(target_data.adv).rjust(4, "0"), target_data.name
            )
        else:
            now_npc_text = _("当前无助理，请选择新的助理：\n")
        selected_id_list = [assistant_id]
        final_list = []
        for npc_id in assistant_service.get_assistant_candidates():
            now_list = [
                npc_id,
                assistant_service.assistant_replace,
                selected_id_list,
            ]
            final_list.append(now_list)
        now_draw_panel.text_list = final_list

        return_list, other_return_list, select_state = (
            common_select_NPC.common_select_npc_button_list_func(
                now_draw_panel, _("选择助理"), now_npc_text, select_state
            )
        )

        yrn = flow_handle.askfor_all(return_list)
        if yrn in return_list and yrn not in other_return_list:
            break


class Assistant_Panel:
    """
    用于查看助理界面面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("助理相关调整")
        """ 当前绘制的食物类型 """

    def draw(self) -> None:
        """绘制对象"""
        title_draw = draw.TitleLineDraw(_("助理相关调整"), self.width)

        while 1:
            assistant_id = relations.assistant_character_id(0)
            assistant_data = identity.of(assistant_id)
            services = relations.assistant_services(assistant_id)

            title_draw.draw()
            py_cmd.clr_cmd()
            return_list = []

            info_draw = draw.NormalDraw()
            info_draw.text = _(
                "\n●助理会自动获得打开玩家房门的权限，因此在执行问候、同居等服务时可以自由进出玩家房间\n\n"
            )
            info_draw.draw()

            button_text = _("[001]助理服务")
            if assistant_id == 0:
                button_text += _("    当前无助理")
            else:
                assistant_name = assistant_data.name
                button_text += _("    当前助理：{0}").format(assistant_name)

            button_draw = draw.LeftButton(
                button_text,
                button_text,
                self.width,
                cmd_func=self.chose_button,
                args=(0,),
            )
            button_draw.draw()
            return_list.append(button_draw.return_text)
            line_feed.draw()

            if assistant_id != 0:

                for cid in game_config.config_assistant_services:
                    if cid == 9:
                        continue
                    service_data = game_config.config_assistant_services[cid]
                    service_option_data = (
                        game_config.config_assistant_services_option[cid]
                    )
                    service_option_text_all = service_option_data[0]
                    service_option_text_now = service_option_text_all[
                        services.get(cid, 0)
                    ]

                    button_text = (
                        f"[{str(cid).rjust(3,'0')}]{service_data.name}"
                    )
                    button_text += f"    {service_option_text_now}"
                    button_draw = draw.LeftButton(
                        button_text,
                        button_text,
                        self.width,
                        cmd_func=self.chose_button,
                        args=(cid,),
                    )
                    button_draw.draw()
                    return_list.append(button_draw.return_text)
                    line_feed.draw()

                    if cid == 5 and services[cid]:
                        button_text = _(
                            "  [更改早安服务预定时间]——当前预定时间：{0}:{1}"
                        ).format(
                            str(
                                action_info.get(0, "plan_to_wake_time")[0]
                            ).rjust(2, "0"),
                            str(
                                action_info.get(0, "plan_to_wake_time")[1]
                            ).rjust(2, "0"),
                        )
                        button_draw = draw.LeftButton(
                            button_text,
                            button_text,
                            self.width,
                            cmd_func=self.select_morning_salutation_time,
                        )
                        button_draw.draw()
                        return_list.append(button_draw.return_text)
                        line_feed.draw()
                    if cid == 6 and services[cid]:
                        button_text = _(
                            "  [更改晚安服务预定时间]——当前预定时间：{0}:{1}"
                        ).format(
                            str(
                                action_info.get(0, "plan_to_sleep_time")[0]
                            ).rjust(2, "0"),
                            str(
                                action_info.get(0, "plan_to_sleep_time")[1]
                            ).rjust(2, "0"),
                        )
                        button_draw = draw.LeftButton(
                            button_text,
                            button_text,
                            self.width,
                            cmd_func=self.select_night_salutation_time,
                        )
                        button_draw.draw()
                        return_list.append(button_draw.return_text)
                        line_feed.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def chose_button(self, service_cid: int) -> None:
        """
        处理助理面板按钮点击。
        service_cid 为 0 时打开助理选择界面。
        service_cid 非 0 时调用 assistant_service.cycle_service 切换对应服务档位。
        Keyword arguments:
        service_cid -- int，按钮对应的服务编号，0 表示打开助理选择界面
        Return arguments:
        None -- 无返回值
        """
        if service_cid == 0:
            chose_assistant()
        else:
            assistant_service.cycle_service(service_cid)

    def select_morning_salutation_time(self) -> None:
        """选择早安服务的时间"""
        return_list = []

        while 1:
            line_feed.draw()
            line_draw = draw.LineDraw("-", self.width)
            line_draw.draw()
            line_feed.draw()
            plan_to_wake_time = action_info.get(0, "plan_to_wake_time")
            now_time_hour, now_time_minute = (
                plan_to_wake_time[0],
                plan_to_wake_time[1],
            )
            now_time_text = _("当前预定早安服务时间为：{0}:{1}\n\n").format(
                str(now_time_hour).rjust(2, "0"),
                str(now_time_minute).rjust(2, "0"),
            )
            now_time_text += _(
                "除非太累了等特殊情况，助理干员会在该时间之前醒来，并前往博士位置\n"
            )
            now_time_text += _(
                "如果这个时间博士还没醒来，助理干员会来到博士床前，悄悄进行早安问候，然后一直等待到博士醒来为止\n"
            )
            now_time_text += _(
                "如果这个时间博士已经醒来，助理干员会直接前往博士身边，进行早安服务后离开\n"
            )
            now_time_text += _(
                "\n○同居状态下，如果助理干员提前醒来，也有可能提前进行早安服务\n"
            )
            now_time_draw = draw.NormalDraw()
            now_time_draw.text = now_time_text
            now_time_draw.width = window_width
            now_time_draw.draw()
            line_feed.draw()

            hour_button = draw.CenterButton(
                _("[更改小时 (24小时制) ]"),
                _("更改小时，不得晚于9时"),
                int(window_width / 6),
                cmd_func=self.change_hour,
                args=(True,),
            )
            hour_button.draw()
            return_list.append(hour_button.return_text)
            minute_button = draw.CenterButton(
                _("[更改分钟]"),
                _("更改分钟"),
                int(window_width / 6),
                cmd_func=self.change_minute,
                args=(True,),
            )
            minute_button.draw()
            return_list.append(minute_button.return_text)
            line_feed.draw()
            line_feed.draw()

            back_button = draw.CenterButton(
                _("[返回]"), _("返回"), window_width
            )
            back_button.draw()
            line_feed.draw()
            return_list.append(back_button.return_text)

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_button.return_text:
                break

    def select_night_salutation_time(self) -> None:
        """选择晚安服务的时间"""
        return_list = []

        while 1:
            line_feed.draw()
            line_draw = draw.LineDraw("-", self.width)
            line_draw.draw()
            line_feed.draw()
            plan_to_sleep_time = action_info.get(0, "plan_to_sleep_time")
            now_time_hour, now_time_minute = (
                plan_to_sleep_time[0],
                plan_to_sleep_time[1],
            )
            now_time_text = _("当前预定晚安服务时间为：{0}:{1}\n\n").format(
                str(now_time_hour).rjust(2, "0"),
                str(now_time_minute).rjust(2, "0"),
            )
            now_time_text += _(
                "如果这个时间博士还没有入睡，助理干员会前来催促睡觉，一直到博士睡前进行晚安服务后再离开\n"
            )
            now_time_text += _(
                "如果这个时间博士已经入睡，助理干员会来到博士床前，悄悄进行晚安服务后离开\n"
            )
            now_time_draw = draw.NormalDraw()
            now_time_draw.text = now_time_text
            now_time_draw.width = window_width
            now_time_draw.draw()
            line_feed.draw()

            hour_button = draw.CenterButton(
                _("[更改小时 (24小时制) ]"),
                _("更改小时，不得早于18时"),
                int(window_width / 6),
                cmd_func=self.change_hour,
                args=(False,),
            )
            hour_button.draw()
            return_list.append(hour_button.return_text)
            minute_button = draw.CenterButton(
                _("[更改分钟]"),
                _("更改分钟"),
                int(window_width / 6),
                cmd_func=self.change_minute,
                args=(False,),
            )
            minute_button.draw()
            return_list.append(minute_button.return_text)
            line_feed.draw()
            line_feed.draw()

            back_button = draw.CenterButton(
                _("[返回]"), _("返回"), window_width
            )
            back_button.draw()
            line_feed.draw()
            return_list.append(back_button.return_text)

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_button.return_text:
                break

    def change_hour(self, morning_flag: bool = True) -> None:
        """更改小时"""
        while 1:
            input_text = flow_handle.askfor_str(_(_("请输入小时(24小时制)：")))
            try:
                user_input = int(input_text)
            except BaseException:
                continue
            if morning_flag:
                if user_input <= 0:
                    user_input = 0
                elif user_input > 9:
                    user_input = 9
                action_info.set_plan_time(0, "plan_to_wake_time", 0, user_input)
                break
            else:
                if user_input <= 18:
                    user_input = 18
                elif user_input > 0:
                    if user_input > 23:
                        user_input = 23
                    action_info.set_plan_time(
                        0, "plan_to_sleep_time", 0, user_input
                    )
                    break

    def change_minute(self, morning_flag: bool = True) -> None:
        """更改分钟"""
        while 1:
            input_text = flow_handle.askfor_str(_(_("请输入分钟：")))
            try:
                user_input = int(input_text)
            except BaseException:
                continue
            if user_input < 0:
                continue
            elif user_input >= 0:
                if user_input > 59:
                    user_input = 59
                if morning_flag:
                    action_info.set_plan_time(
                        0, "plan_to_wake_time", 1, user_input
                    )
                else:
                    action_info.set_plan_time(
                        0, "plan_to_sleep_time", 1, user_input
                    )
                break
