"""成就面板显示、成就获得提示绘制与成就结算入口 achievement_flow"""

from __future__ import annotations

from types import FunctionType
from Script.Core import get_text, flow_handle
from Script.Core import constant
from Script.UI.Moudle import draw, panel, view
from Script.Config import game_config, normal_config
from Script.Modules.domains import achievement, commission, inventory
from Script.Modules.gameplay_resolution import achievement_service

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def achievement_flow(achievement_type: str, achievement_id: int = 0) -> None:
    """按 achievement_type 结算成就（achievement_id 非 0 时强制结算该项），并绘制新达成成就的获得提示。"""
    draw_achievement_notice(
        achievement_service.settle_by_type(achievement_type, achievement_id)
    )


def draw_achievement_notice(achievement_id_list: list[int]) -> None:
    """
    绘制获得了一个成就的提示\n
    输入：\n
    - achievement_id_list: 成就ID列表
    """
    if not achievement_id_list:
        return
    # 遍历成就
    for achievement_id in achievement_id_list:
        # 获取成就信息
        achievement_data = game_config.config_achievement[achievement_id]
        name = achievement_data.name
        description = achievement_data.description
        # 绘制成就获得提示
        now_draw = draw.WaitDraw()
        draw_text = _("\n\n   ○ 获得蚀刻章：{name} ○\n").format(name=name)
        draw_text += _("      （{description}）\n\n\n").format(
            description=description
        )
        now_draw.text = draw_text
        now_draw.style = "gold_enrod"
        now_draw.draw()


class Achievement_Panel:
    """
    用于显示成就界面面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("蚀刻章")

        title_draw = draw.TitleLineDraw(title_text, self.width)
        handle_sub_panel = panel.PageHandlePanel(
            [], Achievement_Draw, 25, 1, self.width
        )
        while 1:
            return_list = []
            title_draw.draw()

            info_text = _(
                "○高难蚀刻章需要前置才能解锁，隐藏蚀刻章在达成前不显示解锁条件\n"
            )
            info_text += _("蚀刻章一览：")
            len_got = 0
            for got in achievement.get("achievement_dict").values():
                if got:
                    len_got += 1
            total = len(game_config.config_achievement)
            info_text += f"{len_got}/{total}\n"

            info_draw = draw.NormalDraw()
            info_draw.text = info_text
            info_draw.draw()
            line_feed.draw()

            # 刷新成就的按钮
            update_button_draw = draw.CenterButton(
                _("[刷新蚀刻章]"),
                _("刷新蚀刻章列表"),
                int(self.width / 4),
                cmd_func=self.update_achievement,
            )
            update_button_draw.draw()
            return_list.append(update_button_draw.return_text)
            line_feed.draw()
            line_feed.draw()

            # 遍历成就列表
            draw_achievement_list = []
            for cid in game_config.config_achievement:
                achievement_data = game_config.config_achievement[cid]
                # 跳过未实装的
                if achievement_data.todo == 1:
                    continue
                # 跳过有前置需求且前置需求没满足的
                if achievement_data.pre_id and not achievement.done(
                    achievement_data.pre_id
                ):
                    continue
                # 跳过有后置升级且该后置已满足的
                if cid in game_config.config_achievement_id_relation:
                    next_achievement_id = (
                        game_config.config_achievement_id_relation[cid]
                    )
                    if next_achievement_id and achievement.done(
                        next_achievement_id
                    ):
                        continue
                # 跳过未达成的隐藏成就
                if achievement_data.special and not achievement.done(cid):
                    continue
                draw_achievement_list.append(cid)

            # 更新当前面板
            handle_sub_panel.text_list = draw_achievement_list
            handle_sub_panel.update()
            handle_sub_panel.draw()

            return_list.extend(handle_sub_panel.return_list)
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def update_achievement(self) -> None:
        """
        更新成就列表
        功能：重新加载成就数据并刷新面板
        """
        # 如果某道具已拥有，则添加到购买过的道具列表中
        for item_id in inventory.items(0):
            if item_id not in achievement.get("buy_item_count_list"):
                achievement.append("buy_item_count_list", item_id)
        # 如果外勤数小于已完成的外勤统计数，则等于外勤统计数量
        if achievement.get("field_commission_count") < len(
            commission.finished()
        ):
            achievement.put(
                "field_commission_count", len(commission.finished())
            )
        # 刷新所有成就
        for achievement_id in game_config.config_achievement:
            achievement_data = game_config.config_achievement[achievement_id]
            # 跳过未实装的成就
            if achievement_data.todo == 1:
                continue
            # 跳过隐藏成就
            if achievement_data.special:
                continue
            # 结算该成就
            achievement_flow(achievement_data.type)


class Achievement_Draw:
    """
    成就绘制对象
    """

    def __init__(
        self,
        achievement_cid: int,
        width: int,
        is_button: bool,
        num_button: bool,
        button_id: int,
    ) -> None:
        """初始化绘制对象"""
        self.achievement_cid: int = achievement_cid
        """ 成就id """
        self.draw_text: str = ""
        """ 绘制文本 """
        self.width: int = width
        """ 最大宽度 """
        self.is_button: bool = is_button
        """ 是否为按钮 """
        self.num_button: bool = num_button
        """ 是否为数字按钮 """
        self.button_id: int = button_id
        """ 按钮编号 """
        self.button_return: str = ""
        """ 按钮返回值 """
        self.now_draw: draw.NormalDraw = draw.NormalDraw()
        """ 绘制的对象 """

        # 成就数据
        achievement_data = game_config.config_achievement[achievement_cid]
        # 判断是否已达成
        get_flag = achievement.done(achievement_cid)
        if get_flag:
            achievement_text = "●"
            draw_style = "standard"
            # 特殊成就特殊标志
            if achievement_data.special:
                achievement_text = "★"
                draw_style = "gold_enrod"
            # 带前置的成就标志
            elif achievement_data.pre_id:
                achievement_text = "●+"
                # 如果有前置的前置
                if game_config.config_achievement[
                    achievement_data.pre_id
                ].pre_id:
                    achievement_text = "●++"
        else:
            achievement_text = "○"
            # 如果该成就有前置
            if achievement_data.pre_id:
                achievement_text = " ┗○"
            draw_style = "deep_gray"

        achievement_name = achievement_data.name
        achievement_description = achievement_data.description
        achievement_text += f"{achievement_name}：{achievement_description}"
        # 绘制
        achievement_draw = draw.NormalDraw()
        achievement_draw.text = achievement_text
        achievement_draw.style = draw_style
        self.draw_text = ""
        self.now_draw = achievement_draw
        """ 绘制的对象 """

    def draw(self) -> None:
        """绘制对象"""
        self.now_draw.draw()
