"""
邀请访客面板，负责访客状态展示、邀请目标选择与提前去留结算界面。
"""

import os
from types import FunctionType
from Script.Core import constant, flow_handle, game_type
from Script.Core import get_text
from Script.Design import (
    attr_calculation,
    map_handle,
    game_time,
    handle_ability,
)
from Script.UI.Moudle import draw, view
from Script.Config import game_config, normal_config
from Script.UI.Panel import manage_basement_panel
from Script.Modules.domains import abilities, chara_life, facility
from Script.Modules.domains import location, relations, roster, visitor
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import recruit_service, visitor_service

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class Invite_Visitor_Panel:
    """
    用于邀请访客的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("邀请访客")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("邀请访客")
        title_draw = draw.TitleLineDraw(title_text, self.width)

        while 1:
            return_list = []
            title_draw.draw()

            all_info_draw = draw.NormalDraw()
            now_text = ""
            now_text += _(" 当前的访客上限为：{0}人\n").format(
                visitor.capacity()
            )
            if len(visitor.visitors()) == 0:
                now_text += _(" 目前没有访客\n")
            else:
                now_text += _(" 目前的访客有：")
                for chara_id, leave_time in visitor.visitors().items():
                    character_data: identity.Identity = identity.of(chara_id)
                    live_room = chara_life.dormitory(character_data.cid).split(
                        os.sep
                    )[-1]
                    leav_time = game_time.get_date_until_day(leave_time)
                    now_text += _(" [{0}]{1}，居住房间：{2}，离开{3}\n").format(
                        str(character_data.adv).rjust(4, "0"),
                        character_data.name,
                        live_room,
                        leav_time,
                    )
                now_text += "\n"

            all_info_draw.text = now_text
            all_info_draw.width = self.width
            all_info_draw.draw()

            # 邀请目标
            now_level = facility.level(13)
            now_text = _("\n 当前邀请目标：")
            if now_level <= 1:
                now_text += _(" 需要访客区至少为2级才可以邀请访客\n")
            elif visitor.invite()[0] == 0:
                now_text += _(" 无")
            else:
                chara_id, progress = visitor.invite()
                character_data = identity.of(chara_id)
                now_text += f" [{chara_id}]{character_data.name}"

                # 邀请进度
                now_text += _("\n 邀请进度：{0}%").format(progress)
                # 邀请效率加成
                all_effect: float = 0
                now_text += _("\n 邀请效率加成：")

                # 去掉玩家与访客
                id_list = [
                    i
                    for i in roster.active()
                    if i != 0 and not visitor.is_visitor(i)
                ]
                for chara_id in id_list:
                    character_data = identity.of(chara_id)
                    # 找到职业是外交官的
                    if chara_life.work_type(character_data.cid) == 131:
                        character_data = identity.of(chara_id)
                        character_effect = (
                            5
                            * handle_ability.get_ability_adjust(
                                abilities.ability(chara_id)[40]
                            )
                        )
                        now_text += f" {character_data.name}"
                        # 邀请效率
                        now_text += _("(话术lv{0}:+{1}%)").format(
                            abilities.ability(chara_id)[40],
                            round(character_effect, 1),
                        )
                        all_effect += character_effect
                now_text += f" = {round(all_effect, 1)}%"
            all_info_draw.text = now_text
            all_info_draw.draw()

            line_feed.draw()
            button_text = _("[001]人员增减")
            button_draw = draw.LeftButton(
                _(button_text),
                _(button_text),
                self.width,
                cmd_func=manage_basement_panel.change_npc_work_out,
                args=(self.width, [132]),
            )
            return_list.append(button_draw.return_text)
            button_draw.draw()
            line_feed.draw()
            if now_level >= 2:
                button_text = _("[002]目标选择")
                button_draw = draw.LeftButton(
                    _(button_text),
                    _(button_text),
                    self.width,
                    cmd_func=self.select_target,
                )
                return_list.append(button_draw.return_text)
                button_draw.draw()

            # 增加提前结算访客离开的按钮
            if len(visitor.visitors()) > 0:
                line_feed.draw()
                button_text = _("[100]提前结算访客离开")
                button_draw = draw.LeftButton(
                    _(button_text),
                    _(button_text),
                    self.width,
                    cmd_func=self.settle_visitor_departures,
                )
                return_list.append(button_draw.return_text)
                button_draw.draw()

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

    def select_target(self) -> None:
        """选择邀请目标"""

        while 1:
            line = draw.LineDraw("-", window_width)
            line.draw()
            return_list = []
            all_info_draw = draw.NormalDraw()

            # 邀请目标
            now_text = _("\n 当前邀请目标：")
            chara_id = visitor.invite()[0]
            if chara_id == 0:
                now_text += _(" 无\n")
            else:
                character_data: identity.Identity = identity.of(chara_id)
                now_text += f" [{str(character_data.adv).rjust(4,'0')}]{character_data.name}\n"

            # 访客区设施信息
            now_level = facility.level(13)
            facility_cid = game_config.config_facility_effect_data[_("访客区")][
                int(now_level)
            ]
            facility_effect = game_config.config_facility_effect[
                facility_cid
            ].effect
            now_text += _(" 访客区等级：{0}\n").format(now_level)
            now_text += _(" 访客停留时长：{0}天\n").format(facility_effect)
            now_text += _(" 访客数量上限：{0}人\n").format(visitor.capacity())

            # 可邀请范围
            now_country_id = location.country()
            now_country_name = game_config.config_birthplace[
                now_country_id
            ].name
            all_country_id_list = []
            if now_level == 2:
                now_invitation_range: str | list[str] = now_country_name
                now_text += _(" 可邀请范围：{0}\n\n").format(
                    now_invitation_range
                )
            elif now_level == 3:
                # 临近地点
                map_path_str = map_handle.get_map_system_path_str_for_list(
                    ["泰拉"]
                )
                map_data: game_type.Map = constant.map_data[map_path_str]
                path_edge = map_data.path_edge
                near_scene_path = path_edge[now_country_name].copy()
                # 仅需要keys
                now_invitation_range = list(near_scene_path.keys())
                now_text += _(" 可邀请范围：")
                for country_name in now_invitation_range:
                    now_text += f" {country_name}"
                    # 寻找该国家的id
                    for country_id in game_config.config_birthplace:
                        if (
                            game_config.config_birthplace[country_id].name
                            == country_name
                        ):
                            all_country_id_list.append(country_id)
                            break
                now_text += "\n\n"
            elif now_level >= 4:
                now_invitation_range = _("全泰拉")
                now_text += _(" 可邀请范围：{0}\n\n").format(
                    now_invitation_range
                )

            # 可邀请目标
            recruitable_npc_id_list = recruit_service.find_recruitable_npc()
            target_id_list = []
            for chara_id in recruitable_npc_id_list:
                # 本地
                if now_level == 2:
                    character_data = identity.of(chara_id)
                    # 出生地是当前所在地的角色
                    if (
                        relations.birthplace(character_data.cid)
                        != now_country_id
                    ):
                        continue
                    target_id_list.append(chara_id)
                # 临近
                elif now_level == 3:
                    character_data = identity.of(chara_id)
                    # 出生地在地点列表中的角色
                    if (
                        relations.birthplace(character_data.cid)
                        not in all_country_id_list
                    ):
                        continue
                    target_id_list.append(chara_id)
                # 全泰拉招募
                elif now_level >= 4:
                    target_id_list.append(chara_id)

            # 可邀请目标绘制
            if len(target_id_list):
                now_text += _(" 当前可邀请目标有（更改后会重置邀请进度）：")
                all_info_draw.text = now_text
                all_info_draw.draw()
                line_feed.draw()
                line_feed.draw()
                chara_id_count = 0
                for chara_id in target_id_list:
                    chara_id_count += 1
                    character_data = identity.of(chara_id)
                    # 均绘制为可选按钮
                    button_text = f" [{str(character_data.adv).rjust(4,'0')}]{character_data.name}"
                    button_text = attr_calculation.pad_display_width(
                        button_text, 22
                    )
                    # 角色颜色
                    draw_style = "standard"
                    if character_data.text_color != "":
                        draw_style = character_data.name
                    button_draw = draw.LeftButton(
                        button_text,
                        button_text,
                        25,
                        normal_style=draw_style,
                        cmd_func=self.change_invite_target,
                        args=chara_id,
                    )
                    button_draw.draw()
                    return_list.append(button_draw.return_text)
                    # 每行6个
                    if chara_id_count % 8 == 0:
                        line_feed.draw()
            else:
                now_text += _(" 当前没有可邀请目标\n")
                all_info_draw.text = now_text
                all_info_draw.draw()

            line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break

    def change_invite_target(self, chara_id: int) -> None:
        """更改邀请目标"""
        visitor.set_invite(chara_id)

    def settle_visitor_departures(self) -> None:
        """结算访客离开"""
        while 1:
            return_list = []
            line = draw.LineDraw("-", window_width)
            line.draw()
            line_feed.draw()

            # 遍历所有访客，输出每个访客的adv_id和姓名的按钮，每行输出三个
            visitor_id_list = list(visitor.visitors())
            visitor_count = 0
            for visitor_id in visitor_id_list:
                visitor_count += 1
                character_data: identity.Identity = identity.of(visitor_id)
                button_text = f" [{str(character_data.adv).rjust(4,'0')}]{character_data.name}"
                button_draw = draw.LeftButton(
                    button_text,
                    button_text,
                    int(len(button_text) * 2),
                    cmd_func=visitor_service.judge_visitor_if_leave,
                    args=visitor_id,
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)
                if visitor_count % 3 == 0:
                    line_feed.draw()

            line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break
