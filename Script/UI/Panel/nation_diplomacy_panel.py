"""
势力外交界面面板。
本模块负责势力外交界面的绘制与输入交互。
数据查询与游戏状态修改委托给 nation_diplomacy_service。
"""

from types import FunctionType

from Script.Config import normal_config
from Script.Core import constant, flow_handle, get_text
from Script.Design import attr_calculation
from Script.Modules.gameplay_resolution import nation_diplomacy_service as svc
from Script.UI.Moudle import draw, view

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class Nation_Diplomacy_Panel:
    """
    用于显示势力外交界面面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("国家及附属势力")
        """ 当前绘制的页面 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("势力外交")
        commission_type_list = [_("国家及附属势力"), _("其他势力")]

        title_draw = draw.TitleLineDraw(title_text, self.width)
        while 1:
            return_list = []
            title_draw.draw()

            for commission_type in commission_type_list:
                if commission_type == self.now_panel:
                    now_draw: draw.CenterDraw | draw.CenterButton
                    now_draw = draw.CenterDraw()
                    now_draw.text = f"[{commission_type}]"
                    now_draw.style = "onbutton"
                    now_draw.width = int(self.width / len(commission_type_list))
                    now_draw.draw()
                else:
                    now_draw = draw.CenterButton(
                        f"[{commission_type}]",
                        f"\n{commission_type}",
                        int(self.width / len(commission_type_list)),
                        cmd_func=self.change_panel,
                        args=(commission_type,),
                    )
                    now_draw.draw()
                    return_list.append(now_draw.return_text)
            line_feed.draw()
            line = draw.LineDraw("+", self.width)
            line.draw()

            facility_info_draw = draw.NormalDraw()
            facility_info_draw.text = _(
                "○与势力维持良好的关系有利于在对应地区的行动，包括外勤委托、商品贸易、技术交流、源石病治疗等\n"
            )
            facility_info_draw.width = self.width
            facility_info_draw.draw()
            line = draw.LineDraw("+", self.width)
            line.draw()

            info_text_list = [
                _("势力名称"),
                _("势力声望"),
                _("源石病治愈率(未实装)"),
                _("负责外交官"),
            ]
            text_width = int((self.width - 1) / (len(info_text_list)))
            countries = self.now_panel == _("国家及附属势力")
            if not countries:
                info_text_list = [_("势力名称"), _("势力声望")]
            for info_text in info_text_list:
                info_draw = draw.CenterDraw()
                info_draw.text = info_text
                info_draw.width = text_width
                info_draw.draw()
            line_feed.draw()
            line = draw.LineDraw("~", self.width)
            line.draw()

            for row in svc.list_nations(countries):
                nation_name = attr_calculation.pad_display_width(
                    row.name, text_width, "center"
                )
                cells = [
                    f"{row.reputation}({row.reputation_level})",
                    (
                        _("无")
                        if row.infection_rate is None
                        else str(row.infection_rate)
                    ),
                    _("无") if row.diplomat_name is None else row.diplomat_name,
                ]
                nation_text = nation_name + "".join(
                    attr_calculation.pad_display_width(
                        cell, text_width, "center"
                    )
                    for cell in cells
                )
                nation_draw = draw.LeftButton(
                    nation_text,
                    "\n" + nation_name,
                    self.width,
                    normal_style="gold_enrod" if row.local else "standard",
                    cmd_func=self.nation_info,
                    args=(row.nation_id,),
                )
                nation_draw.draw()
                return_list.append(nation_draw.return_text)
                line_feed.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def change_panel(self, building_type: str) -> None:
        """
        切换当前面板显示
        Keyword arguments:
        building_type -- 要切换的面板类型
        """

        self.now_panel = building_type

    def nation_info(self, nation_id: int) -> None:
        """
        显示势力详细信息
        Keyword arguments:
        nation_id -- 势力编号
        """

        detail = svc.nation_detail(nation_id)
        specialty_text = "".join(f"{name} " for name in detail.specialties)
        subordinate_text = "".join(
            f"{sub.name}{sub.reputation}({sub.reputation_level}) "
            for sub in detail.subordinates
        )

        while 1:
            return_list = []
            line = draw.LineDraw("-", self.width)
            line.draw()

            info_draw = draw.NormalDraw()
            info_draw.text = _("\n势力名称：{0}").format(detail.name)
            info_draw.text += _("\n势力声望：{0}").format(detail.reputation)
            if self.now_panel == _("国家及附属势力"):
                info_draw.text += _("\n源石病感染率：{0}").format(
                    detail.infection_rate
                )
            info_draw.text += _("\n势力特产：{0}").format(specialty_text)
            info_draw.text += _("\n附属势力：{0}").format(subordinate_text)
            info_draw.width = self.width
            info_draw.draw()
            line_feed.draw()
            line_feed.draw()

            if self.now_panel == _("国家及附属势力"):
                self.draw_posting(nation_id, return_list)

            line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(
                _("[返回]"), _("返回"), int(self.width / 2)
            )
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def draw_posting(self, nation_id: int, return_list: list[str]) -> None:
        """
        绘制势力所属国家的负责外交官、当前外交方针与对应的调整按钮。
        已任命外交官时同时绘制调整外交方针按钮，并将按钮返回值追加到 return_list。
        Keyword arguments:
        nation_id -- int，势力编号
        return_list -- list[str]，用于收集本页按钮返回值的列表
        Return arguments:
        None -- 无返回值
        """

        post = svc.posting(nation_id)
        info_text = _(
            "○负责地区势力的外交官会长期离岛停留在对应国家，只有当罗德岛本身也在同一国家时才会在岛上办公\n"
        )
        info_text += _("当前势力的负责外交官为：")
        if post is None:
            diplomat_text = _("  无")
            policy_text = _("未任命外交官，无法制定外交方针")
        else:
            diplomat = post.diplomat
            diplomat_text = (
                f"\n  [{str(diplomat.adv).rjust(4,'0')}]{diplomat.name}  "
                f"{post.skill_name}lv{diplomat.skill}：{post.effect}%"
            )
            policy_text = post.policy_name
        info_draw = draw.NormalDraw()
        info_draw.text = info_text + diplomat_text
        info_draw.width = self.width
        info_draw.draw()
        line_feed.draw()
        line_feed.draw()

        info_draw = draw.NormalDraw()
        info_draw.text = _("\n当前外交方针：{0}").format(policy_text)
        info_draw.width = self.width
        info_draw.draw()
        line_feed.draw()

        line_feed.draw()
        line_feed.draw()
        adjust_NPC_button_draw = draw.CenterButton(
            _("【调整负责外交官】"),
            _("\n【调整负责外交官】"),
            int(self.width / 3),
            cmd_func=self.adjust_NPC,
            args=(nation_id,),
        )
        adjust_NPC_button_draw.draw()
        return_list.append(adjust_NPC_button_draw.return_text)

        if post is not None:
            adjust_diplomatic_policy_button_draw = draw.CenterButton(
                _("【调整外交方针】"),
                _("\n【调整外交方针】"),
                int(self.width / 3),
                cmd_func=self.adjust_diplomatic_policy,
                args=(nation_id,),
            )
            adjust_diplomatic_policy_button_draw.draw()
            return_list.append(adjust_diplomatic_policy_button_draw.return_text)

    def adjust_NPC(self, nation_id: int) -> None:
        """
        调整负责外交官
        Keyword arguments:
        nation_id -- 势力编号
        """

        found = svc.candidates(nation_id)
        return_list = []
        line = draw.LineDraw("-", self.width)
        line.draw()

        info_draw_2 = draw.NormalDraw()
        info_draw_2.text = _(
            "\n可选择干员（需要出身地或势力为{0}）：\n\n"
        ).format(found.country_name)
        info_draw_2.width = self.width
        info_draw_2.draw()
        for count, diplomat in enumerate(found.diplomats, 1):
            draw_style = "standard"
            if diplomat.character_id == found.current_id:
                draw_style = "gold_enrod"
            draw_text = f"[{str(diplomat.adv).rjust(4,'0')}]{diplomat.name}:lv{diplomat.skill}"
            button_draw = draw.LeftButton(
                draw_text,
                f"\n{diplomat.character_id}",
                int(self.width / 6),
                normal_style=draw_style,
                cmd_func=self.sure_NPC,
                args=(diplomat.character_id, nation_id),
            )
            button_draw.draw()
            return_list.append(button_draw.return_text)
            if count % 6 == 0:
                line_feed.draw()

        line_feed.draw()
        line_feed.draw()
        back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
        back_draw.draw()
        return_list.append(back_draw.return_text)
        flow_handle.askfor_all(return_list)

    def sure_NPC(self, character_id: int, nation_id: int) -> None:
        """
        调用服务任免势力所属国家的外交官，并在产生新任命时绘制驻地提示。
        仅解除原在任外交官时不绘制提示。
        Keyword arguments:
        character_id -- int，角色编号
        nation_id -- int，势力编号
        Return arguments:
        None -- 无返回值
        """

        appointment = svc.assign_diplomat(character_id, nation_id)
        if appointment is None:
            return
        if appointment.local:
            info_text = _(
                "\n{0}被任命为{1}的外交官，因为该地为当前罗德岛所在地，所以会在岛上办公，当罗德岛离开该国家后会进入离舰外派状态。\n"
            )
        else:
            info_text = _(
                "\n{0}被派遣到{1}作为外交官，将会长期停留在那里，直到被召回或罗德岛抵达该国家。\n"
            )
        info_draw = draw.WaitDraw()
        info_draw.text = info_text.format(
            appointment.name, appointment.country_name
        )
        info_draw.width = window_width
        info_draw.draw()

    def adjust_diplomatic_policy(self, nation_id: int) -> None:
        """
        调整外交方针
        Keyword arguments:
        nation_id -- 势力编号
        """

        return_list = []
        line = draw.LineDraw("-", self.width)
        line.draw()

        info_draw_2 = draw.NormalDraw()
        info_draw_2.text = _(
            "\n○可选的方针受访客区等级、外交官能力、势力的声望与源石病情况等各种因素决定\n"
        )
        info_draw_2.text += _("\n可选择外交方针：\n\n")
        info_draw_2.width = self.width
        info_draw_2.draw()
        for policy in svc.policies(nation_id):
            draw_text = (
                f"[{policy.policy_id}]{policy.name.ljust(15,'　')}："
                f"{policy.info}"
            )
            button_draw = draw.LeftButton(
                draw_text,
                f"\n{policy.policy_id}",
                self.width,
                normal_style="gold_enrod" if policy.selected else "standard",
                cmd_func=svc.set_policy,
                args=(nation_id, policy.policy_id),
            )
            button_draw.draw()
            return_list.append(button_draw.return_text)
            line_feed.draw()

        line_feed.draw()
        line_feed.draw()
        back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
        back_draw.draw()
        return_list.append(back_draw.return_text)
        flow_handle.askfor_all(return_list)
