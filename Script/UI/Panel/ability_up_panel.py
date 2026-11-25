"""
角色能力升级面板：显示能力升级需求，并消耗宝珠提升能力
"""

from collections.abc import Callable, Mapping
from types import FunctionType

from Script.UI.Moudle import draw, panel, view
from Script.UI.Panel import (
    see_character_info_panel,
    talent_up_panel,
    character_info_head,
)
from Script.Core import get_text, game_type, py_cmd, flow_handle, constant
from Script.Config import game_config
from Script.Design import second_behavior
from Script.Modules.domains import abilities
from Script.Modules.gameplay_resolution import ability_up_service as svc
from Script.Modules.gameplay_resolution import mark_change_service as marks

_: FunctionType = get_text._
""" 翻译api """

line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1


def _info(title: str, width: int, text: str) -> draw.NormalDraw:
    """绘制标题线、正文文本与前后换行，并返回正文绘制对象。"""
    draw.TitleLineDraw(title, width, ":").draw()
    line_feed.draw()
    info_draw = draw.NormalDraw()
    info_draw.text = text
    info_draw.draw()
    line_feed.draw()
    return info_draw


def _ask(width: int, return_list: list[str]) -> str:
    """绘制分隔线与返回按钮、等待输入并清空指令后返回按键值。"""
    line_feed.draw()
    draw.LineDraw("=", width).draw()
    back_draw = draw.CenterButton(_("[返回]"), _("返回"), int(width))
    back_draw.draw()
    line_feed.draw()
    return_list.append(back_draw.return_text)
    yrn = flow_handle.askfor_all(return_list)
    py_cmd.clr_cmd()
    line_feed.draw()
    return yrn


class Characterabi_show_Text:
    """
    角色能力升级显示面板
    Keyword arguments:
    character_id -- 角色id
    width -- 最大宽度
    """

    def __init__(self, character_id: int, width: int) -> None:
        """初始化绘制对象"""
        self.character_id = character_id
        """ 绘制的角色id """
        self.width = width
        """ 当前最大可绘制宽度 """
        self.return_list: list[str] = []
        """ 监听的按钮列表 """

    def draw(self) -> None:
        """绘制对象"""
        self.return_list = []
        line_feed.draw()
        draw.LittleTitleLineDraw(_("能力"), self.width, ":").draw()
        for group in svc.ability_groups(self.character_id):
            for button in group.buttons:
                self._draw_button(button)
            if group.ability_type != 6:
                line_feed.draw()

    def _draw_button(self, button: svc.AbilityButton) -> None:
        """按按钮项的路由与高亮状态绘制单个能力或刻印按钮。"""
        ability_data = game_config.config_ability[button.ability_id]
        style = "gold_enrod" if button.highlight else "standard"
        cmd_func: Callable[[], None] | Callable[[int], None] = (
            self.mark_can_up_show
        )
        args: object = ()
        if button.route == "locked":
            style = "deep_gray"
        elif button.route == "ability":
            cmd_func = Characterabi_cmd_Text(
                self.character_id, self.width, button.ability_id
            ).draw
        else:
            cmd_func = (
                self.mark_up_show
                if button.route == "up"
                else self.mark_down_show
            )
            args = button.ability_id
        button_draw = draw.LeftButton(
            _(button.text),
            _(ability_data.name),
            int(self.width / 10),
            normal_style=style,
            cmd_func=cmd_func,
            args=args,
            tooltip=ability_data.info,
        )
        self.return_list.append(button_draw.return_text)
        button_draw.draw()

    def mark_up_show(self, ability_id: int) -> None:
        """显示刻印升级面板"""
        offer = marks.mark_up_offer(self.character_id, ability_id)
        while 1:
            return_list = []
            _info(_("使用宝珠升级刻印"), self.width, offer.text)
            if offer.enough:
                yes_draw = draw.CenterButton(
                    _("[确定]"),
                    _("确定"),
                    int(self.width),
                    cmd_func=self.mark_up,
                    args=(ability_id, offer.need_juel),
                )
                yes_draw.draw()
                return_list.append(yes_draw.return_text)
            if _ask(self.width, return_list) in return_list:
                break

    def mark_down_show(self, ability_id: int) -> None:
        """显示刻印降级面板"""
        offer = marks.mark_down_offer(self.character_id, ability_id)
        self.jewel_use_dict: dict[int, int] = {}
        while 1:
            total = 0
            return_list = []
            info_draw = _info(_("使用宝珠降低刻印"), self.width, offer.text)
            for juel_id, adjust in offer.entries:
                used = self.jewel_use_dict.setdefault(juel_id, 0)
                jewel_name = game_config.config_juel[juel_id].name
                value = int(used * adjust)
                btn = draw.LeftButton(
                    _("[{0}]{1} 当前用量:{2}，当前总值{3}").format(
                        juel_id, jewel_name, used, value
                    ),
                    _(jewel_name),
                    self.width,
                    cmd_func=self.input_juel_count,
                    args=(juel_id, adjust, total, offer.need),
                )
                btn.draw()
                return_list.append(btn.return_text)
                total += value
                line_feed.draw()
            info_draw.text = f"\n当前宝珠总值为：{total}\n"
            info_draw.draw()
            line_feed.draw()
            yes_draw = draw.CenterButton(
                _("[确定]"),
                _("确定"),
                int(self.width),
                cmd_func=self.mark_down,
                args=(ability_id),
            )
            if total >= offer.need:
                yes_draw.draw()
                return_list.append(yes_draw.return_text)
            yrn = _ask(self.width, return_list)
            if yrn in (return_list[-1], yes_draw.return_text):
                break

    def input_juel_count(
        self,
        juel_id: int,
        adjust: float,
        mark_down_data_all_value: int,
        need_juel_all_value: int,
    ) -> None:
        """
        输入宝珠使用量
        参数:
        juel_id: int -- 宝珠id
        adjust: float -- 宝珠调整值
        mark_down_data_all_value: int -- 当前宝珠总值
        need_juel_all_value: int -- 需要的宝珠总值
        """
        ask_panel = panel.AskForOneMessage()
        ask_panel.set(
            marks.juel_prompt(
                self.character_id,
                juel_id,
                adjust,
                mark_down_data_all_value,
                need_juel_all_value,
                self.jewel_use_dict[juel_id],
            ),
            99,
        )
        count = marks.juel_count(self.character_id, juel_id, ask_panel.draw())
        if count is not None:
            self.jewel_use_dict[juel_id] = count

    def mark_up(self, ability_id: int, need_juel: int) -> None:
        """升级刻印"""
        behavior_id = marks.mark_up(self.character_id, ability_id, need_juel)
        second_behavior.second_behavior_effect(
            self.character_id, game_type.CharacterStatusChange(), [behavior_id]
        )

    def mark_down(self, ability_id: int) -> None:
        """降级刻印"""
        info_draw = draw.WaitDraw()
        info_draw.text = marks.mark_down(
            self.character_id, ability_id, self.jewel_use_dict
        )
        info_draw.style = "gold_enrod"
        info_draw.draw()

    def mark_can_up_show(self) -> None:
        """显示无法升级的刻印信息"""
        now_draw = draw.WaitDraw()
        now_draw.text = _("\n该刻印当前无法使用宝珠升级\n")
        now_draw.draw()


class Characterabi_cmd_Text:
    """
    角色能力升级指令面板
    Keyword arguments:
    character_id -- 角色id
    width -- 最大宽度
    ability_id -- 能力id
    """

    def __init__(self, character_id: int, width: int, ability_id: int) -> None:
        """初始化绘制对象"""
        self.character_id = character_id
        """ 绘制的角色id """
        self.width = width
        """ 当前最大可绘制宽度 """
        self.ability_id = ability_id
        """ 当前的能力id """
        self.return_list: list[str] = []
        """ 监听的按钮列表 """
        self.ability_level = abilities.ability(self.character_id)[ability_id]
        """ 能力等级 """

    def draw(self) -> None:
        """绘制对象"""
        self.return_list = []
        while self.ability_level != svc.MAX_LEVEL:
            need_list, need_list2 = svc.level_up_lists(
                self.ability_id, self.ability_level
            )
            draw.LineDraw(".", self.width).draw()
            line_feed.draw()
            ability_data = game_config.config_ability[self.ability_id]
            info_draw = draw.NormalDraw()
            info_draw.text = _("○当前能力及等级为：{0} - {1}\n").format(
                ability_data.name, self.ability_level
            )
            info_draw.text += "  " + ability_data.info + "\n\n"
            info_draw.draw()
            main = self._draw_needs(need_list)
            second = None
            if need_list2:
                line_feed.draw()
                info_draw = draw.NormalDraw()
                info_draw.text = _(
                    "○如果满足以下条件，则可以使用次需求进行升级：\n"
                )
                info_draw.draw()
                second = self._draw_needs(need_list2)
            judge, judge2 = svc.verdict(
                self.character_id,
                self.ability_id,
                main.met,
                second is None or second.met,
            )
            line_feed.draw()
            now_draw = draw.NormalDraw()
            now_draw.text = (
                _("满足条件，要升级吗？\n")
                if judge and judge2
                else _("不满足条件，无法升级\n")
            )
            now_draw.draw()
            line_feed.draw()
            if second is None:
                self._yes(judge, _("[确定]"), _("确定"), 1, main.cost)
            else:
                self._yes(
                    judge, _("[确定(主需求)]"), _("确定(主需求)"), 2, main.cost
                )
                self._yes(
                    judge2,
                    _("[确定(次需求)]"),
                    _("确定(次需求)"),
                    2,
                    second.cost,
                )
            if _ask(self.width, self.return_list) in self.return_list:
                break

    def _draw_needs(self, need_list: list[str]) -> svc.Needs:
        """查询并逐行绘制升级需求，返回对应的 Needs 检查结果。"""
        result = svc.needs(self.character_id, need_list)
        for row in result.rows:
            now_draw = draw.NormalDraw()
            now_draw.text = row
            now_draw.draw()
        return result

    def _yes(
        self,
        shown: bool,
        text: str,
        return_text: str,
        parts: int,
        cost: Mapping[int, int],
    ) -> None:
        """在满足显示条件时绘制绑定到 level_up 的居中确认按钮。"""
        if not shown:
            return
        yes_draw = draw.CenterButton(
            text,
            return_text,
            int(self.width / parts),
            cmd_func=self.level_up,
            args=cost,
        )
        yes_draw.draw()
        self.return_list.append(yes_draw.return_text)

    def level_up(self, jule_dict: dict[int, int]) -> None:
        """
        扣除升级所需的宝珠，把当前能力提升1级，并结算技能类成就
        Keyword arguments:
        jule_dict -- 要扣除的宝珠，宝珠id:数量
        Return arguments:
        None
        """
        svc.level_up(self.character_id, self.ability_id, jule_dict)


class Character_abi_up_main_Handle:
    """
    带返回的角色能力上升主面板
    Keyword arguments:
    character_id -- 角色id
    width -- 最大宽度
    character_list -- 角色id列表
    """

    def __init__(self, character_id: int, width: int) -> None:
        """初始化绘制对象"""
        self.character_id: int = character_id
        """ 要绘制的角色id """
        self.width: int = width
        """ 面板最大宽度 """
        self.return_list: list[str] = []
        """ 当前面板监听的按钮列表 """

    def draw(self) -> None:
        """绘制面板"""
        back_draw = draw.CenterButton(_("[返回]"), _("返回"), int(self.width))
        now_panel_id = _("属性升级")
        while 1:
            self.return_list = []
            now_character_panel = Character_abi_up_sub_Handle(
                self.character_id, self.width
            )
            now_character_panel.change_panel(now_panel_id)
            now_character_panel.draw()
            back_draw.draw()
            line_feed.draw()
            self.return_list.extend(now_character_panel.return_list)
            self.return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(self.return_list)
            py_cmd.clr_cmd()
            line_feed.draw()
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break
            elif yrn in now_character_panel.draw_data:
                now_panel_id = yrn


class Character_abi_up_sub_Handle:
    """
    角色能力上升子面板
    Keyword arguments:
    character_id -- 角色id
    width -- 绘制宽度
    """

    def __init__(self, character_id: int, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel: str = _("属性升级")
        """ 当前的属性页id """
        self.character_id: int = character_id
        """ 要绘制的角色id """
        self.return_list: list[str] = []
        """ 当前面板监听的按钮列表 """
        main_first_draw = Character_abi_up_main_panel(character_id, width)
        self.draw_data = {
            _("属性升级"): main_first_draw,
        }
        """ 按钮文本对应属性面板 """
        self.handle_panel = panel.CenterDrawButtonListPanel()
        """ 属性列表的控制面板 """
        self.change_panel(self.now_panel)

    def change_panel(self, panel_id: str) -> None:
        """
        切换当前面板
        Keyword arguments:
        panel_id -- 要切换的面板id
        """
        self.now_panel = panel_id
        self.handle_panel.set(
            [f"[{text}]" for text in self.draw_data.keys()],
            list(self.draw_data.keys()),
            self.width,
            4,
            f"[{self.now_panel}]",
            self.change_panel,
        )

    def draw(self) -> None:
        """绘制面板"""
        self.draw_data[self.now_panel].draw()
        self.return_list = []
        self.return_list.extend(self.draw_data[self.now_panel].return_list)

        line_feed.draw()
        line = draw.LineDraw("=", self.width)
        line.draw()


class Character_abi_up_main_panel:
    """
    角色能力升级面板第一页对象
    Keyword arguments:
    character_id -- 角色id
    width -- 绘制宽度
    """

    def __init__(self, character_id: int, width: int) -> None:
        """初始化绘制对象"""
        head_draw = character_info_head.CharacterInfoHead(character_id, width)
        Juel_draw = see_character_info_panel.CharacterJuelText(
            character_id, width, 8, False
        )
        Experience_draw = see_character_info_panel.CharacterExperienceText(
            character_id, width, 8, False
        )
        abi_draw = Characterabi_show_Text(character_id, width)
        tal_draw = talent_up_panel.Character_talent_show_Text(
            character_id, width
        )
        self.draw_list: list = [head_draw, Juel_draw, Experience_draw, abi_draw]
        """ 绘制的面板列表 """
        if character_id != 0:
            self.draw_list.append(tal_draw)
        self.return_list: list[str] = []
        """ 当前面板监听的按钮列表 """

    def draw(self) -> None:
        """绘制面板"""
        for label in self.draw_list:
            label.draw()
            if "return_list" in label.__dict__:
                self.return_list.extend(label.return_list)
