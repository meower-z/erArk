"""
角色信息多页展示面板与通用信息块绘制模块。
展示规则与文本由 character_info_service 与 player_ability_service 提供。
"""

from types import FunctionType
from Script.UI.Moudle import draw, panel
from Script.Core import flow_handle, get_text
from Script.Config import normal_config
from Script.Design import character_image
from Script.UI.Panel import body_info_panel, character_info_head
from Script.UI.Panel import first_record_panel
from Script.Modules.domains import visitor
from Script.Modules.gameplay_resolution import character_info_service as svc
from Script.Modules.gameplay_resolution import (
    player_ability_service as player_svc,
)

_: FunctionType = get_text._
""" 本地化翻译函数。 """
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1
window_width = normal_config.config_normal.text_width
""" 全局配置的界面文本宽度。 """


def _normal(text: str, tooltip: str | None = None) -> draw.NormalDraw:
    """创建普通文本绘制对象并按需设置悬停提示。"""
    now_draw = draw.NormalDraw()
    now_draw.text = text
    if tooltip is not None:
        now_draw.tooltip = tooltip
    return now_draw


def _left(text: str, width: int, style: str | None = None) -> draw.LeftDraw:
    """创建指定宽度的左对齐文本绘制对象。"""
    now_draw = draw.LeftDraw()
    now_draw.text = text
    now_draw.width = width
    if style is not None:
        now_draw.style = style
    return now_draw


def _text_list(texts: list[str], width: int, column: int, center: bool) -> list:
    """按对齐方式与列数生成文本列表绘制对象。"""
    now_draw = (
        panel.CenterDrawTextListPanel()
        if center
        else panel.LeftDrawTextListPanel()
    )
    now_draw.set(texts, width, column)
    return now_draw.draw_list


def _draw_labels(draw_list: list, row_break: bool) -> int:
    """按顺序绘制对象列表并统计嵌套子项数量。"""
    line_feed.draw()
    count = 0
    for label in draw_list:
        if isinstance(label, list):
            for value in label:
                value.draw()
                count += 1
            if row_break:
                line_feed.draw()
        else:
            label.draw()
    return count


class SeeCharacterInfoPanel:
    """角色信息多标签主面板。"""

    def __init__(self, character_id: int, width: int) -> None:
        """初始化各标签子页面与底部标签切换栏。"""
        self.width: int = width
        self.now_panel: str = _("基础属性")
        self.character_id: int = character_id
        self.return_list: list[str] = []
        base = See_Character_Base_Attributes_Panel(character_id, width)
        detail = See_Character_Detailed_Attributes_Panel(character_id, width)
        third = SeeCharacterThirdPanel(character_id, width)
        setting = See_Character_Setting_Panel(character_id, width)
        if character_id == 0:
            self.draw_data: dict[
                str, _Page | first_record_panel.See_Character_First_Record_Panel
            ] = {
                _("基础属性"): base,
                _("能力、经验与宝珠"): detail,
                _("玩家能力"): third,
                _("角色设定"): setting,
            }
        else:
            first_record_draw = (
                first_record_panel.See_Character_First_Record_Panel(
                    character_id, width
                )
            )
            self.draw_data = {
                _("基础属性"): base,
                _("能力、经验与宝珠"): detail,
                _("肉体情况"): third,
                _("性行为履历"): first_record_draw,
                _("角色设定"): setting,
            }
        self.handle_panel = panel.CenterDrawButtonListPanel()
        self.change_panel(self.now_panel)

    def change_panel(self, panel_id: str) -> None:
        """切换当前显示标签并刷新底部标签按钮栏。"""
        self.now_panel = panel_id
        self.handle_panel.set(
            [f"[{text}]" for text in self.draw_data.keys()],
            list(self.draw_data.keys()),
            self.width,
            5,
            f"[{self.now_panel}]",
            self.change_panel,
        )

    def draw(self) -> None:
        """绘制当前标签页面、分隔线与底部切换栏。"""
        fallback = {
            _("玩家能力"): _("肉体情况"),
            _("肉体情况"): _("玩家能力"),
            _("性行为履历"): _("基础属性"),
        }
        if self.now_panel not in self.draw_data:
            self.now_panel = fallback[self.now_panel]
        self.draw_data[self.now_panel].draw()
        self.return_list = []
        self.return_list.extend(self.draw_data[self.now_panel].return_list)
        line_feed.draw()
        line = draw.LineDraw("=", self.width)
        line.draw()
        self.handle_panel.draw()
        self.return_list.extend(self.handle_panel.return_list)


class _Page:
    """角色信息子页面的绘制基类。"""

    collect = False
    """ 绘制时是否收集各子块的按钮返回文本。 """
    draw_list: list
    return_list: list[str]

    def draw(self) -> None:
        """按顺序绘制页面子块并按需汇总按钮返回值。"""
        for label in self.draw_list:
            label.draw()
            if self.collect:
                self.return_list.extend(label.return_list)


class See_Character_Base_Attributes_Panel(_Page):
    """基础属性标签子页面。"""

    def __init__(self, character_id: int, width: int) -> None:
        """组装头部、立绘、素质，按条件追加日程与访客块。"""
        self.draw_list = [
            character_info_head.CharacterInfoHead(character_id, width),
            CharacterImage(character_id, width),
            CharacterTalentText(character_id, width, 16, False),
        ]
        daily_draw = CharacterDailyText(character_id, width, 8, False)
        if character_id != 0:
            self.draw_list.append(daily_draw)
        if visitor.is_visitor(character_id):
            self.draw_list.append(
                CharacterVisitorText(character_id, width, 8, False)
            )
        self.return_list = []


class See_Character_Detailed_Attributes_Panel(_Page):
    """能力、经验与宝珠标签子页面。"""

    def __init__(self, character_id: int, width: int) -> None:
        """组装头部、能力、经验与宝珠展示块。"""
        self.draw_list = [
            character_info_head.CharacterInfoHead(character_id, width),
            CharacterabiText(character_id, width),
            CharacterExperienceText(character_id, width, 8, False),
            CharacterJuelText(character_id, width, 8, False),
        ]
        self.return_list = []


class SeeCharacterThirdPanel(_Page):
    """第三标签页，主角展示玩家能力，其余展示肉体情况。"""

    collect = True

    def __init__(self, character_id: int, width: int) -> None:
        """按角色是否为 0 组装玩家能力块或肉体情况块。"""
        head_draw = character_info_head.CharacterInfoHead(character_id, width)
        body_draw = body_info_panel.CharacterBodyText(
            character_id, width, 8, False
        )
        ability_draw = PlayerAbilityText(character_id, width, 8, False)
        if character_id == 0:
            self.draw_list = [head_draw, ability_draw]
        else:
            self.draw_list = [head_draw, body_draw]
        self.return_list = []


class See_Character_Setting_Panel(_Page):
    """角色设定标签子页面。"""

    collect = True

    def __init__(self, character_id: int, width: int) -> None:
        """组装角色头部与角色设定编辑块。"""
        from Script.UI.Panel import character_setting

        self.draw_list = [
            character_info_head.CharacterInfoHead(character_id, width),
            character_setting.CharacterSetting(character_id, width, 8, False),
        ]
        self.return_list = []


class _Block:
    """角色信息通用文本展示块基类。"""

    row_break = True
    """ 绘制列表项时每行末尾是否追加换行。 """

    def __init__(
        self,
        character_id: int,
        width: int,
        column: int,
        center_status: bool = True,
    ) -> None:
        """记录布局参数、初始化绘制列表并调用 fill。"""
        self.character_id = character_id
        self.width = width
        self.column = column
        self.center_status = center_status
        self.return_list: list[str] = []
        self.draw_list: list = []
        self.fill()

    def fill(self) -> None:
        """由子类实现以填充绘制对象列表。"""

    def titled(self, title: str, texts: list[str] | None = None) -> None:
        """追加小标题行并按需追加文本列表绘制对象。"""
        self.draw_list.append(draw.LittleTitleLineDraw(title, self.width, ":"))
        if texts is not None:
            self.draw_list.extend(
                _text_list(texts, self.width, self.column, self.center_status)
            )

    def draw(self) -> None:
        """输出本块的绘制对象列表。"""
        _draw_labels(self.draw_list, self.row_break)


class SeeCharacterStatusPanel(_Block):
    """角色状态进度条展示块。"""

    def __init__(
        self,
        character_id: int,
        width: int,
        column: int,
        type_number: int,
        center_status: bool = True,
    ) -> None:
        """初始化状态条块布局并记录类型编号参数。"""
        super().__init__(character_id, width, column, center_status)
        self.type_number = type_number

    def fill(self) -> None:
        """按状态分区生成进度条绘制对象与换行。"""
        for name, bars in svc.status_sections(self.character_id):
            self.titled(name)
            for count, bar in enumerate(bars, 1):
                bar_draw = draw.InfoBarDraw()
                bar_draw.width = int(self.width / self.column)
                bar_draw.scale = 0.8
                bar_draw.chara_state = True
                bar_draw.name_style = bar.style
                bar_draw.set(
                    "StatusPointbar",
                    bar.max_value,
                    bar.value,
                    bar.text,
                    bar.tooltip,
                )
                self.draw_list.append(bar_draw)
                if count % self.column == 0:
                    self.draw_list.append(line_feed)
            if len(bars) % self.column != 0:
                self.draw_list.append(line_feed)


class CharacterabiText(_Block):
    """角色能力等级展示块。"""

    def __init__(self, character_id: int, width: int) -> None:
        """以固定列数 0 初始化角色能力展示块。"""
        super().__init__(character_id, width, 0)

    def fill(self) -> None:
        """按能力分区构建名称、等级条与数值绘制项。"""
        self.titled(_("能力"))
        for ability_type, rows in svc.ability_sections(self.character_id):
            for row in rows:
                new_draw = draw.LeftMergeDraw(int(self.width / 16))
                if row.break_before:
                    new_draw.draw_list.append(_normal("\n"))
                new_draw.draw_list.append(_normal(row.label, row.info))
                new_draw.draw_list.append(draw.ExpLevelDraw(row.level))
                gap = _normal(" " if row.level == 8 else "  ")
                gap.width = len(gap.text)
                new_draw.draw_list.append(gap)
                new_draw.draw_list.append(_normal(str(row.level)))
                self.draw_list.append(new_draw)
            if ability_type != 6:
                type_break = _normal("\n")
                type_break.width = 1
                self.draw_list.append(type_break)


class CharacterImage:
    """角色立绘展示块。"""

    def __init__(self, character_id: int, width: int) -> None:
        """准备立绘标题并查询角色当前立绘文件名。"""
        self.character_id = character_id
        self.width = width
        self.title_list: list[draw.Drawable] = [
            draw.LittleTitleLineDraw(_("立绘"), width, ":")
        ]
        self.image_name = character_image.find_character_image_name(
            character_id
        )

    def draw(self) -> None:
        """为非主角角色绘制立绘标题与立绘按钮。"""
        if self.character_id != 0:
            for value in self.title_list:
                value.draw()
            gap = _normal(" ")
            gap.width = 1
            gap.draw()
            flow_handle.print_image_cmd(self.image_name, "立绘按钮")


class CharacterExperienceText(_Block):
    """角色经验展示块。"""

    def fill(self) -> None:
        """填充角色经验标题与非零经验列表。"""
        self.titled(_("经验"), svc.experience_texts(self.character_id))

    def draw(self) -> None:
        """绘制经验列表并在条目数不超过 8 时补换行。"""
        count = _draw_labels(self.draw_list, True)
        if count <= 8:
            line_feed.draw()
            if count == 0:
                line_feed.draw()


class CharacterTalentText(_Block):
    """角色基础信息与素质展示块。"""

    row_break = False

    def fill(self) -> None:
        """填充职业、种族、势力、出身地与分类素质。"""
        self.titled(_("素质"))
        heading = svc.talent_heading(self.character_id)
        sections = svc.talent_sections(self.character_id)
        for index, (label, talents) in enumerate(sections):
            if index == 0:
                self.draw_list.extend(_normal(text) for text in heading)
            self.draw_list.append(_normal(label))
            for count, (text, info) in enumerate(talents, 1):
                self.draw_list.append(_normal(text, info))
                if count % self.column == 0:
                    self.draw_list.append(line_feed)
                    self.draw_list.append(_normal("           "))
            self.draw_list.append(line_feed)
        if self.draw_list[-1] == line_feed:
            self.draw_list.pop()


class CharacterDailyText(_Block):
    """角色日程与居住房间展示块。"""

    row_break = False

    def fill(self) -> None:
        """填充日程标题与日程展示文本。"""
        text = svc.daily_text(self.character_id)
        self.titled(_("日程"))
        self.draw_list.append(_left(text, self.width))


class CharacterVisitorText(_Block):
    """访客意愿、离去时间与房间展示块。"""

    row_break = False

    def fill(self) -> None:
        """填充访客标题与访客展示文本。"""
        self.titled(_("访客"))
        text = svc.visitor_text(self.character_id)
        self.draw_list.append(_left(text, self.width))


class CharacterJuelText(_Block):
    """角色宝珠展示块。"""

    def fill(self) -> None:
        """填充宝珠标题与宝珠数量列表。"""
        self.titled(_("宝珠"), svc.juel_texts(self.character_id))


class PlayerAbilityText(_Block):
    """玩家能力系别与信物装备展示块。"""

    def __init__(
        self,
        character_id: int,
        width: int,
        column: int,
        center_status: bool = True,
    ) -> None:
        """填充玩家能力分组、已装备信物与更改按钮。"""
        super().__init__(character_id, width, column, center_status)
        texts = [
            _("\n 【{}】\n".format(name)) + lines
            for name, lines in player_svc.arts_groups(character_id)
        ]
        self.titled(_("玩家能力"), texts)
        self.titled(_("装备信物"))
        self.draw_list.append(_left(player_svc.equipped_token_text(), width))
        self.draw_list.append(line_feed)
        button_text = _("[更改装备信物]")
        token_button_draw = draw.CenterButton(
            button_text, button_text, width / 4, cmd_func=self.change_token
        )
        self.return_list.append(token_button_draw.return_text)
        self.draw_list.append(token_button_draw)
        self.draw_list.append(line_feed)

    def change_token(self) -> None:
        """运行更改装备信物的交互循环直至点击返回。"""
        while 1:
            return_list = []
            line = draw.LineDraw("-", self.width)
            line.draw()
            _left(player_svc.token_heading(), self.width).draw()
            line_feed.draw()
            choices = player_svc.token_choices()
            for choice in choices:
                if choice.selectable:
                    button_draw = draw.LeftButton(
                        choice.text,
                        f"\n{choice.character_id}",
                        self.width,
                        normal_style=(
                            "gold_enrod" if choice.equipped else "standard"
                        ),
                        cmd_func=self.select_this_token,
                        args=choice.character_id,
                    )
                    button_draw.draw()
                    return_list.append(button_draw.return_text)
                else:
                    _left(choice.text, self.width, "deep_gray").draw()
                line_feed.draw()
            if not choices:
                _left(_("  当前没有可以选择的信物\n"), self.width).draw()
            line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def select_this_token(self, character_id: int) -> None:
        """切换指定干员信物的装备状态。"""
        player_svc.toggle_token(character_id)
