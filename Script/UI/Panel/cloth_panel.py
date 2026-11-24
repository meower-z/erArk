"""角色服装、脱衣服及穿脱切换相关的面板"""

from types import FunctionType
from Script.Core import constant, flow_handle
from Script.Core import get_text, py_cmd
from Script.Config import game_config, normal_config
from Script.UI.Moudle import draw, panel, rich_text_draw, view
from Script.Modules.gameplay_resolution import cloth_panel_service
from Script.Modules.tk_ui import player_pick
from Script.Modules.domains import activity

_: FunctionType = get_text._
""" 翻译api """

line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class SeeCharacterClothPanel:
    """
    显示角色服装面板对象
    Keyword arguments:
    character_id -- 角色id
    width -- 绘制宽度
    column -- 每行状态最大个数
    type_number -- 显示的状态类型
    """

    def __init__(
        self,
        character_id: int,
        width: int,
        column: int,
        type_number: int,
        center_status: bool = True,
    ) -> None:
        """初始化绘制对象"""
        self.character_id = character_id
        """ 要绘制的角色id """
        self.width = width
        """ 面板最大宽度 """
        self.column = column
        """ 每行状态最大个数 """
        self.draw_list: list[draw.Drawable] = []
        """ 绘制的文本列表 """
        self.return_list: list[str] = []
        """ 当前面板监听的按钮列表 """
        self.center_status: bool = center_status
        """ 居中绘制状态文本 """
        self.type_number = type_number
        """ 显示的状态类型 """
        self.draw_list.append(draw.LittleTitleLineDraw(_("服装"), width, ":"))
        now_text = cloth_panel_service.build_cloth_display_text()
        rich_text_draw_list = rich_text_draw.get_rich_text_draw_list(now_text)
        self.draw_list.extend(rich_text_draw_list)

    def draw(self) -> None:
        """绘制面板"""
        for label in self.draw_list:
            if isinstance(label, list):
                for value in label:
                    value.draw()
                line_feed.draw()
            else:
                label.draw()


class Undress_Panel:
    """
    用于查看脱衣服面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("脱衣服")
        """ 当前绘制的面板类型 """
        self.handle_panel: panel.PageHandlePanel | None = None
        """ 当前名字列表控制面板 """

    def draw(self) -> None:
        """绘制对象"""
        title_draw = draw.TitleLineDraw(_("脱衣服"), self.width)

        self.handle_panel = panel.PageHandlePanel(
            [], SeeUndressButtonList, 10, 1, self.width, True, True, 0
        )
        while 1:
            py_cmd.clr_cmd()
            button_text_list = cloth_panel_service.undress_option_labels()

            self.handle_panel.text_list = button_text_list
            self.handle_panel.update()
            title_draw.draw()
            return_list = []

            line_feed.draw()
            self.handle_panel.draw()
            return_list.extend(self.handle_panel.return_list)
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break


class SeeUndressButtonList:
    """
    点击后可选择脱衣服选项的按钮对象
    Keyword arguments:
    text -- 选项名字
    width -- 最大宽度
    is_button -- 绘制按钮
    num_button -- 绘制数字按钮
    button_id -- 数字按钮id
    """

    def __init__(
        self,
        text: str,
        width: int,
        is_button: bool,
        num_button: bool,
        button_id: int,
    ) -> None:
        """初始化绘制对象"""
        self.button_name_text: str = text
        """ 指令名字绘制文本 """
        self.draw_text: str = ""
        """ 绘制文本 """
        self.width: int = width
        """ 最大宽度 """
        self.num_button: bool = num_button
        """ 绘制数字按钮 """
        self.button_id: int = button_id
        """ 数字按钮的id """
        self.button_return: str = str(button_id)
        """ 按钮返回值 """

        option = cloth_panel_service.build_undress_option(
            button_id, self.button_name_text
        )
        name_draw: draw.NormalDraw | draw.LeftButton
        if option.selectable:
            name_draw = draw.LeftButton(
                option.text,
                self.button_return,
                self.width,
                cmd_func=self.chose_button,
            )
        else:
            name_draw = draw.LeftDraw()
            name_draw.text = option.text
            name_draw.width = self.width
        self.button_return = text
        self.draw_text = option.text
        self.now_draw = name_draw
        """ 绘制的对象 """

    def chose_button(self) -> None:
        """玩家点击了选项：脱衣在行动开始时进行"""
        player_pick.choose(
            activity.behavior(0).behavior_id,
            5,
            kind="undress",
            args={"choice": self.button_id},
        )

    def draw(self) -> None:
        """绘制对象"""
        self.now_draw.draw()


class SwitchCharacterClothPanel:
    """
    H 模式目标角色服装切换面板，已穿与已脱衣物均为点击切换穿脱状态的按钮（不含避孕套片段，
    全裸保留真空行且始终显示已脱衣物）。
    Keyword arguments:
    character_id -- 角色 id（仅保存）
    width -- 面板绘制宽度
    column / type_number -- 每行个数与状态类型（仅保存）
    center_status -- 是否居中显示（仅保存）
    """

    def __init__(
        self,
        character_id: int,
        width: int,
        column: int,
        type_number: int,
        center_status: bool = True,
    ) -> None:
        """保存面板参数并构建初始服装切换面板内容。"""
        self.character_id = character_id
        self.width = width
        self.column = column
        self.type_number = type_number
        self.center_status = center_status
        self.draw_list: list[draw.Drawable] = []
        self.button_list: list[SwitchClothButton] = []
        self.return_list: list[str] = []
        self._refresh_panel()

    def _refresh_panel(self) -> None:
        """根据 build_switch_cloth_layout 重建 draw_list 与 button_list，并将各按钮返回值追加到 return_list。"""
        self.draw_list.clear()
        self.button_list.clear()
        self.draw_list.append(
            draw.LittleTitleLineDraw(_("服装"), self.width, ":")
        )
        for token in cloth_panel_service.build_switch_cloth_layout():
            if isinstance(token, cloth_panel_service.SwitchClothItem):
                btn = SwitchClothButton(
                    token.cloth_id, token.clothing_type, token.is_wear, self
                )
                self.button_list.append(btn)
                self.return_list.append(btn.return_text)
                self.draw_list.append(btn)
            elif isinstance(token, cloth_panel_service.SwitchMarkup):
                self.draw_list.extend(
                    rich_text_draw.get_rich_text_draw_list(token.text)
                )
            elif isinstance(token, cloth_panel_service.SwitchLabel):
                label = draw.NormalDraw()
                label.text = token.text
                label.width = self.width
                self.draw_list.append(label)
            else:
                self.draw_list.append(line_feed)

    def draw(self) -> None:
        """
        绘制面板
        """
        for item in self.draw_list:
            if isinstance(item, list):
                for value in item:
                    value.draw()
                line_feed.draw()
            else:
                item.draw()


class SwitchClothButton(draw.LeftButton):
    """
    单件衣物的穿脱切换按钮，宽度为按钮文本长度的两倍。
    Keyword arguments:
    cloth_id -- 衣物 id
    clothing_type -- 衣物部位编号
    is_wear -- 当前是否穿着
    panel -- 所属 SwitchCharacterClothPanel 父面板
    """

    def __init__(
        self,
        cloth_id: int,
        clothing_type: int,
        is_wear: bool,
        panel: SwitchCharacterClothPanel,
    ) -> None:
        """保存衣物与父面板参数，并按“ <衣物名>”构建按钮文本与绘制属性。"""
        self.cloth_id = cloth_id
        self.clothing_type = clothing_type
        self.is_wear = is_wear
        self.panel = panel
        cloth_name = game_config.config_clothing_tem[cloth_id].name
        btn_text = f" {cloth_name}"
        btn_width = len(btn_text) * 2
        super().__init__(
            btn_text, str(cloth_id), btn_width, cmd_func=self.switch_cloth
        )

    def switch_cloth(self) -> None:
        """在 cloth switch 草稿上下文中切换该衣物的穿脱状态并刷新父面板。"""
        with player_pick.drafting("cloth switch"):
            cloth_panel_service.toggle_target_cloth(
                self.cloth_id, self.clothing_type, self.is_wear
            )
            self.panel._refresh_panel()
