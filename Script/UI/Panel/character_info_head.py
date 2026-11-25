"""角色信息头部绘制面板模块，提供 CharacterInfoHead 面板类与状态标识绘制转换函数 get_character_status_list。"""

from types import FunctionType
from Script.UI.Moudle import draw
from Script.Core import get_text, num
from Script.Core import text_handle
from Script.Config import normal_config
from Script.Modules.gameplay_resolution import chara_head_service
from Script.Modules.gameplay_resolution import status_tag_service
from Script.Modules.domains import h_meters, needs

_: FunctionType = get_text._
""" 翻译api """

line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1
window_width = normal_config.config_normal.text_width
""" 屏幕宽度 """


def get_character_status_list(
    character_id: int,
) -> tuple[list[draw.LeftDraw], list[str]]:
    """
    将 status_tag_service.status_tags 返回的角色状态标识转换为绘制对象列表与文本列表。
    Keyword arguments:
    character_id -- int，角色编号
    Return arguments:
    tuple[list[draw.LeftDraw], list[str]] -- 按相同顺序排列的 LeftDraw 绘制对象列表与文本列表
    """
    status_list = []
    status_text_list = []
    for tag in status_tag_service.status_tags(character_id):
        tag_draw = draw.LeftDraw()
        tag_draw.text = tag.text
        tag_draw.style = tag.style
        tag_draw.tooltip = tag.tooltip
        status_list.append(tag_draw)
        status_text_list.append(tag.text)
    return status_list, status_text_list


class CharacterInfoHead:
    """
    角色信息面板头部面板
    Keyword arguments:
    character_id -- 角色id
    width -- 最大宽度
    """

    def __init__(self, character_id: int, width: int) -> None:
        """初始化绘制对象"""
        self.character_id: int = character_id
        """ 要绘制的角色id """
        self.width: int = width
        """ 当前最大可绘制宽度 """
        self.return_list: list[str] = []
        """ 当前面板监听的按钮列表 """
        self.draw_title: bool = True
        """ 是否绘制面板标题 """

        from Script.UI.Panel.see_item_info_panel import (
            use_drug,
            auto_use_sanity_drug,
        )

        status_list, status_text_list = get_character_status_list(character_id)
        message = chara_head_service.head_message(character_id)
        message_draw = draw.CenterDraw()
        text_width = text_handle.get_text_index(message)
        all_status_text = "".join(status_text_list)
        base_width = width / 3.5 - text_handle.get_text_index(all_status_text)
        max_width = max(base_width, text_width)
        message_draw.width = int(max_width)
        message_draw.text = message
        hp_draw = draw.InfoBarDraw()
        hp_draw.width = int(width / 6)
        hp_draw.scale = 0.8
        hp_draw.set(
            "HitPointbar",
            int(needs.of(character_id)["hit_max"]),
            num.shown(needs.of(character_id)["hit"]),
            _("体力"),
            tooltip=_("体力，最低为1时会疲劳到无法行动"),
        )
        mp_draw = draw.InfoBarDraw()
        mp_draw.width = int(width / 6)
        mp_draw.scale = 0.8
        mp_draw.set(
            "ManaPointbar",
            int(needs.of(character_id)["mana_max"]),
            num.shown(needs.of(character_id)["mana"]),
            _("气力"),
            tooltip=_("气力，精神上的耐力，最低为0时使体力的消耗增加"),
        )
        None_draw = draw.CenterDraw()
        None_draw.width = 1
        None_draw.text = " "
        self.draw_list: list = [
            tuple([message_draw] + status_list + [hp_draw, None_draw, mp_draw]),
        ]
        if character_id == 0:
            sanity_point_draw = draw.InfoBarDraw()
            sanity_point_draw.width = int(width / 7.5)
            sanity_point_draw.scale = 1
            sanity_point_draw.set(
                "SanityPointbar",
                int(needs.of(character_id)["sanity_max"]),
                num.shown(needs.of(character_id)["sanity"]),
                _("理智"),
                tooltip=_("理智，使用源石技艺时消耗"),
            )
            sanity_item_draw = draw.LeftButton(
                "✚",
                _("快速使用最小理智剂"),
                1,
                normal_style="sanity",
                cmd_func=auto_use_sanity_drug,
                tooltip=_("使用最小规格的理智恢复剂快速恢复理智"),
            )
            semen_point_draw = draw.InfoBarDraw()
            semen_point_draw.width = int(width / 7.5)
            semen_point_draw.scale = 1
            meters = h_meters.of(character_id)
            semen_point_draw.set(
                "SemenPointBar",
                int(meters["semen_max"]),
                num.shown(meters["semen"] + meters["extra_semen"]),
                _("精液"),
                tooltip=_("精液，进行射精时消耗"),
            )
            semen_item_draw = draw.LeftButton(
                "✚",
                _("快速使用精力剂"),
                1,
                normal_style="semen",
                cmd_func=use_drug,
                args=11,
                tooltip=_("使用精力恢复剂快速恢复精力"),
            )
            self.draw_list[0] = self.draw_list[0] + (
                None_draw,
                None_draw,
                sanity_point_draw,
            )
            has_sanity_drug, has_semen_drug = chara_head_service.quick_drugs(
                character_id
            )
            if has_sanity_drug:
                self.draw_list[0] = self.draw_list[0] + (sanity_item_draw,)
                self.return_list.append(sanity_item_draw.return_text)
            self.draw_list[0] = self.draw_list[0] + (
                None_draw,
                None_draw,
                semen_point_draw,
            )
            if has_semen_drug:
                self.draw_list[0] = self.draw_list[0] + (semen_item_draw,)
                self.return_list.append(semen_item_draw.return_text)
        """ 要绘制的面板列表 """

    def draw(self) -> None:
        """绘制面板"""
        if self.draw_title:
            title_draw = draw.TitleLineDraw(_("人物属性"), self.width)
            title_draw.draw()
        for draw_tuple in self.draw_list:
            for label in draw_tuple:
                label.draw()
            line_feed.draw()
