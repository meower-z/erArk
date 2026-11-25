"""关门、照顾婴儿、初始奖励能力选择、冰箱与预订房间等日常小面板"""

from types import FunctionType
from Script.UI.Moudle import draw, panel, view
from Script.Core import constant, flow_handle
from Script.Core import get_text
from Script.Config import normal_config
from Script.Modules.tk_ui import player_pick
from Script.Modules.gameplay_resolution import normal_panel_service as svc

_: FunctionType = get_text._
""" 翻译api """

line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width = normal_config.config_normal.text_width
""" 屏幕宽度 """


class Close_Door_Panel:
    """
    用于关门的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("关门")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.Drawable] = []
        """ 绘制的文本列表 """

    def draw(self) -> bool | None:
        """
        问玩家关不关门，只读数据：回答由指令带进行动，开始时生效（handle_instruct._close_door）。
        无法关门的地点回答否时退出选择（player_pick.back）
        Return arguments:
        bool | None -- 关门为真，不关为假；当前地点已问过（移动前不问第二次）时为 None
        """

        ask = svc.door_ask()
        if ask is None:
            return None

        title_text = _("关门")

        title_draw = draw.TitleLineDraw(title_text, self.width)
        while 1:
            return_list: list[str] = []
            title_draw.draw()
            now_draw_list: list[draw.Drawable] = []

            askfor_panel = panel.OneMessageAndSingleColumnButton()
            askfor_list = [_("是"), _("否")]
            askfor_panel.set(askfor_list, _(ask.prompt), 0)
            askfor_panel_return_list = askfor_panel.get_return_list()
            return_list.extend(askfor_panel_return_list.keys())
            now_draw_list.append(askfor_panel)

            self.draw_list = []
            """ 绘制的文本列表 """
            self.draw_list.extend(now_draw_list)

            for label in self.draw_list:
                if isinstance(label, list):
                    for value in label:
                        value.draw()
                    line_feed.draw()
                else:
                    label.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                if askfor_panel_return_list[yrn] == askfor_list[0]:
                    return True
                if ask.cancel_on_no:
                    player_pick.back()
                return False


class Take_Care_Baby_Panel:
    """
    用于照顾婴儿的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("照顾婴儿")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("照顾婴儿")
        title_draw = draw.TitleLineDraw(title_text, self.width)

        while 1:
            return_list = []
            title_draw.draw()

            info_draw = draw.NormalDraw()
            info_text = _("\n当前育儿室正在照料的婴儿有：\n\n")
            info_draw.text = info_text
            info_draw.draw()

            for baby in svc.babies():
                button_draw = draw.LeftButton(
                    _(baby.label),
                    _(str(baby.adv)),
                    self.width,
                    cmd_func=self.choice_take_care,
                    args=(baby.chara_id,),
                )
                return_list.append(button_draw.return_text)
                button_draw.draw()
                line_feed.draw()

            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def choice_take_care(self, chara_id: int) -> None:
        """选择照顾的方式"""
        self.target_chara_id = chara_id
        info_text = svc.care_title(chara_id)

        button_text_list = [option.label for option in svc.care_options()]

        while 1:
            return_list = []

            info_draw = draw.NormalDraw()
            info_draw.text = info_text
            info_draw.draw()

            for button_id in range(len(button_text_list)):
                button_text = _("[00{0}]:{1}").format(
                    button_id, button_text_list[button_id]
                )
                button_draw = draw.LeftButton(
                    _(button_text),
                    _(str(button_id)),
                    self.width,
                    cmd_func=self.settle_take_care,
                    args=(button_id,),
                )
                return_list.append(button_draw.return_text)
                button_draw.draw()
                line_feed.draw()

            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def settle_take_care(self, instruct_id: int) -> None:
        """结算照顾指令"""
        option = svc.care_options()[instruct_id]
        player_pick.choose(
            option.behavior_id,
            svc.CARE_MINUTES,
            target=self.target_chara_id,
            state=option.state,
        )


class Chose_First_bonus_ability_Panel:
    """
    用于初始奖励中的能力选择的面板
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.chose_ability_id = 0
        """ 选择的能力ID """

    def draw(self) -> None:
        """绘制对象"""

        while 1:
            return_list = []
            line = draw.LineDraw("-", window_width)
            line.draw()
            now_npc_draw = draw.NormalDraw()
            now_npc_draw.text = svc.bonus_prompt(self.chose_ability_id)
            now_npc_draw.draw()
            line_feed.draw()

            for ability in svc.bonus_abilities():
                button_text = ability.label
                button_draw = draw.LeftButton(
                    _(button_text),
                    _(button_text),
                    int(len(button_text) * 2),
                    cmd_func=self.chose_this_ability,
                    args=ability.ability_id,
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
            if yrn in return_list:
                break

    def chose_this_ability(self, ability_id: int) -> None:
        """选项1"""
        self.chose_ability_id = ability_id
        svc.choose_bonus(ability_id)


class Fridge_Panel:
    """
    用于查看冰箱的面板
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("冰箱")
        title_draw = draw.TitleLineDraw(title_text, self.width)

        while 1:
            return_list = []
            title_draw.draw()
            now_draw = draw.NormalDraw()
            draw_text = _("\n 【母乳】\n")
            draw_text += _(
                "  ○母乳可以被博士带走饮用或制作其他乳制品，有效期截止当天24点，到期后背包和冰箱里未使用的母乳会全部转"
                "化为资源【鲜母乳】\n"
            )
            draw_text += _("  当前冰箱内各干员母乳情况：\n")
            now_draw.text = draw_text
            now_draw.draw()

            milk_rows = svc.milk_rows()
            if len(milk_rows) == 0:
                draw_text = _("\n    当前冰箱里没有母乳\n")
                now_draw.text = draw_text
                now_draw.draw()

            for row in milk_rows:
                character_id = row.chara_id
                now_draw.text = row.label
                now_draw.draw()
                button_text = _("  [带走]  ")
                button_draw = draw.CenterButton(
                    _(button_text),
                    _(button_text + f"_{character_id}"),
                    len(button_text) * 2,
                    cmd_func=self.take_milk,
                    args=character_id,
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)
                button_text = _("  [转化]  ")
                button_draw = draw.CenterButton(
                    _(button_text),
                    _(button_text + f"_{character_id}"),
                    len(button_text) * 2,
                    cmd_func=self.turn_milk,
                    args=character_id,
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)
                line_feed.draw()

            line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(
                _("[返回]"), _("返回\n"), window_width
            )
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def take_milk(self, character_id: int) -> None:
        """拿走母乳并放进玩家背包"""
        now_draw = draw.WaitDraw()
        now_draw.text = svc.take_milk(character_id)
        now_draw.draw()

    def turn_milk(self, character_id: int) -> None:
        """转化母乳为资源【鲜母乳】"""
        now_draw = draw.WaitDraw()
        now_draw.text = svc.turn_milk(character_id)
        now_draw.draw()


class Order_Hotel_Room_Panel:
    """
    用于预订房间的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("预订房间")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("预订房间")
        title_draw = draw.TitleLineDraw(title_text, self.width)

        while 1:
            return_list = []
            title_draw.draw()

            info_draw = draw.NormalDraw()
            now_draw_text = ""
            now_draw_text += _(
                "\n○酒店有标间、情趣主题房和顶级套房三种选择，高级的房间能够提供更好的氛围，本区的四家酒店可任意选择入住，退房时间均为次日中午12点\n"
            )
            now_draw_text += _(
                "  情趣主题房会免费赠送一瓶润滑液和五个避孕套，顶级套房则在时限内无限量供应所有H消耗品，"
                "并免费提供所有H道具的租用服务\n"
            )
            now_draw_text += _("  请问要入住哪种房间呢？\n\n")
            info_draw.text = now_draw_text
            info_draw.draw()

            for i, room_text in enumerate(svc.room_offers()):
                button_draw = draw.LeftButton(
                    _(f"[{i}]" + room_text),
                    _(str(i)),
                    self.width,
                    cmd_func=self.order_room,
                    args=(i,),
                )
                return_list.append(button_draw.return_text)
                button_draw.draw()
                line_feed.draw()
            booked = svc.booked_text()
            if booked is not None:
                info_draw.text = booked
                info_draw.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def order_room(self, room_id: int) -> None:
        """预订房间"""
        now_draw = draw.WaitDraw()
        now_draw.text = svc.order_room(room_id)
        now_draw.draw()
