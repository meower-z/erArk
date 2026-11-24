"""势力外交界面的 Tk 面板，负责界面绘制、交互输入与提示展示。"""

from types import FunctionType
from Script.Core import get_text, flow_handle
from Script.Core import constant
from Script.UI.Moudle import draw, view
from Script.Config import normal_config
from Script.Design import attr_calculation
from Script.Modules.gameplay_resolution import nation_diplomacy_service

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
            draw.LineDraw("+", self.width).draw()

            facility_info_draw = draw.NormalDraw()
            facility_info_draw.text = _(
                "○与势力维持良好的关系有利于在对应地区的行动，包括外勤委托、商品贸易、技术交流、源石病治疗等\n"
            )
            facility_info_draw.width = self.width
            facility_info_draw.draw()
            draw.LineDraw("+", self.width).draw()

            info_text_list = [
                _("势力名称"),
                _("势力声望"),
                _("源石病治愈率(未实装)"),
                _("负责外交官"),
            ]
            text_width = int((self.width - 1) / (len(info_text_list)))
            is_other = self.now_panel == _("其他势力")
            if is_other:
                info_text_list = [_("势力名称"), _("势力声望")]
            for info_text in info_text_list:
                info_draw = draw.CenterDraw()
                info_draw.text = info_text
                info_draw.width = text_width
                info_draw.draw()
            line_feed.draw()
            draw.LineDraw("~", self.width).draw()

            for row in nation_diplomacy_service.list_nations(is_other):
                nation_name = attr_calculation.pad_display_width(
                    row.name, text_width, "center"
                )
                columns = (
                    f"{row.reputation}({row.reputation_level})",
                    str(
                        _("无")
                        if row.infection_rate is None
                        else row.infection_rate
                    ),
                    _("无") if row.diplomat_name is None else row.diplomat_name,
                )
                nation_text = nation_name + "".join(
                    attr_calculation.pad_display_width(
                        column, text_width, "center"
                    )
                    for column in columns
                )
                nation_draw = draw.LeftButton(
                    nation_text,
                    "\n" + nation_name,
                    self.width,
                    normal_style="gold_enrod" if row.is_local else "standard",
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
        detail = nation_diplomacy_service.get_nation_detail(nation_id)
        nation_specialty_str = "".join(
            f"{name} " for name in detail.specialties
        )
        nation_subordinate_str = "".join(
            f"{sub.name}{sub.reputation}({sub.reputation_level}) "
            for sub in detail.subordinates
        )

        while 1:
            return_list = []
            draw.LineDraw("-", self.width).draw()

            info_draw = draw.NormalDraw()
            info_draw.text = _("\n势力名称：{0}").format(detail.name)
            info_draw.text += _("\n势力声望：{0}").format(detail.reputation)
            if self.now_panel == _("国家及附属势力"):
                info_draw.text += _("\n源石病感染率：{0}").format(
                    detail.infection_rate
                )
            info_draw.text += _("\n势力特产：{0}").format(nation_specialty_str)
            info_draw.text += _("\n附属势力：{0}").format(
                nation_subordinate_str
            )
            info_draw.width = self.width
            info_draw.draw()
            line_feed.draw()
            line_feed.draw()

            if self.now_panel == _("国家及附属势力"):

                info_text = _(
                    "○负责地区势力的外交官会长期离岛停留在对应国家，只有当罗德岛本身也在同一国家时才会在岛上办公\n"
                )
                info_text += _("当前势力的负责外交官为：")
                diplomat = nation_diplomacy_service.get_diplomat_summary(
                    detail.country_id
                )
                if diplomat is not None:
                    now_diplomat_text = (
                        f"\n  [{str(diplomat.adv).rjust(4,'0')}]{diplomat.name}  "
                        f"{diplomat.ability_name}lv{diplomat.ability_level}：{diplomat.effect}%"
                    )
                else:
                    now_diplomat_text = _("  无")
                info_draw = draw.NormalDraw()
                info_draw.text = info_text + now_diplomat_text
                info_draw.width = self.width
                info_draw.draw()
                line_feed.draw()
                line_feed.draw()

                info_draw = draw.NormalDraw()
                info_draw.text = _("\n当前外交方针：{0}").format(
                    _("未任命外交官，无法制定外交方针")
                    if diplomat is None
                    else diplomat.policy_name
                )
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

                if diplomat is not None:
                    adjust_diplomatic_policy_button_draw = draw.CenterButton(
                        _("【调整外交方针】"),
                        _("\n【调整外交方针】"),
                        int(self.width / 3),
                        cmd_func=self.adjust_diplomatic_policy,
                        args=(nation_id,),
                    )
                    adjust_diplomatic_policy_button_draw.draw()
                    return_list.append(
                        adjust_diplomatic_policy_button_draw.return_text
                    )

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

    def adjust_NPC(self, nation_id: int) -> None:
        """
        调整负责外交官
        Keyword arguments:
        nation_id -- 势力编号
        """
        selection = nation_diplomacy_service.list_diplomat_candidates(nation_id)
        return_list = []
        draw.LineDraw("-", self.width).draw()

        info_draw_2 = draw.NormalDraw()
        info_draw_2.text = _(
            "\n可选择干员（需要出身地或势力为{0}）：\n\n"
        ).format(selection.country_name)
        info_draw_2.width = self.width
        info_draw_2.draw()
        for npc_draw_count, candidate in enumerate(selection.candidates, 1):
            draw_text = (
                f"[{str(candidate.adv).rjust(4,'0')}]{candidate.name}"
                f":lv{candidate.ability_level}"
            )
            button_draw = draw.LeftButton(
                draw_text,
                f"\n{candidate.character_id}",
                int(self.width / 6),
                normal_style=(
                    "gold_enrod" if candidate.is_current else "standard"
                ),
                cmd_func=self.sure_NPC,
                args=(candidate.character_id, selection.country_id),
            )
            button_draw.draw()
            return_list.append(button_draw.return_text)
            if npc_draw_count % 6 == 0:
                line_feed.draw()

        line_feed.draw()
        line_feed.draw()
        back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
        back_draw.draw()
        return_list.append(back_draw.return_text)
        flow_handle.askfor_all(return_list)

    def sure_NPC(self, character_id: int, country_id: int) -> None:
        """
        确认负责外交官
        Keyword arguments:
        character_id -- 角色编号
        country_id -- 势力编号
        """
        appointment = nation_diplomacy_service.assign_diplomat(
            character_id, country_id
        )
        if appointment is None:
            return
        if appointment.is_local:
            info_text = _(
                "\n{0}被任命为{1}的外交官，因为该地为当前罗德岛所在地，所以会在岛上办公，当罗德岛离开该国家后会进入离舰外派状态。\n"
            )
        else:
            info_text = _(
                "\n{0}被派遣到{1}作为外交官，将会长期停留在那里，直到被召回或罗德岛抵达该国家。\n"
            )
        info_draw = draw.WaitDraw()
        info_draw.text = info_text.format(
            appointment.diplomat_name, appointment.country_name
        )
        info_draw.width = window_width
        info_draw.draw()

    def adjust_diplomatic_policy(self, nation_id: int) -> None:
        """
        调整外交方针
        Keyword arguments:
        nation_id -- 势力编号
        """
        selection = nation_diplomacy_service.list_available_policies(nation_id)
        return_list = []
        draw.LineDraw("-", self.width).draw()

        info_draw_2 = draw.NormalDraw()
        info_draw_2.text = _(
            "\n○可选的方针受访客区等级、外交官能力、势力的声望与源石病情况等各种因素决定\n"
        )
        info_draw_2.text += _("\n可选择外交方针：\n\n")
        info_draw_2.width = self.width
        info_draw_2.draw()
        for option in selection.options:
            draw_text = (
                f"[{option.policy_id}]{option.name.ljust(15,'　')}："
                f"{option.info}"
            )
            button_draw = draw.LeftButton(
                draw_text,
                f"\n{option.policy_id}",
                self.width,
                normal_style=(
                    "gold_enrod" if option.is_selected else "standard"
                ),
                cmd_func=self.sure_diplomatic_policy,
                args=(option.policy_id, selection.country_id),
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

    def sure_diplomatic_policy(
        self, diplomatic_policy_id: int, country_id: int
    ) -> None:
        """
        确认外交方针
        Keyword arguments:
        diplomatic_policy_id -- 外交方针编号
        country_id -- 势力编号
        """
        nation_diplomacy_service.set_diplomatic_policy(
            country_id, diplomatic_policy_id
        )
