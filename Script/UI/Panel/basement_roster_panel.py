"""
全干员一览页签（basement_roster_panel）
=======================================
绘制管理罗德岛界面的全干员一览页签并处理筛选、排序、分页与详情跳转。
"""

from types import FunctionType

from Script.Core import constant, get_text, num
from Script.Design import attr_calculation
from Script.Modules.domains import abilities, hypnosis, identity, needs
from Script.Modules.domains import relations
from Script.Modules.gameplay_resolution import operator_list_service as svc
from Script.UI.Moudle import draw, view
from Script.UI.Panel import see_character_info_panel

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1


def pass_func() -> None:
    """空回调函数，供仅依赖返回码分发的界面按钮占位使用。"""


def draw_text(
    text: str, width: float | None = None, style: str | None = None
) -> None:
    """绘制一段普通文本，可按需设置显示宽度与文本样式。"""
    now_draw = draw.NormalDraw()
    now_draw.text = text
    if width is not None:
        now_draw.width = width
    if style is not None:
        now_draw.style = style
    now_draw.draw()


def draw_button(
    return_list: list[str], cls: type[draw.CenterButton], *args, **kwargs
) -> None:
    """构造并绘制一个按钮，并将其返回码追加到 return_list。"""
    button = cls(*args, **kwargs)
    button.draw()
    return_list.append(button.return_text)


class RosterTab:
    """全干员一览页签的界面状态持有者与绘制控制器。"""

    def __init__(self, width: int) -> None:
        """初始化全干员一览的页码、分类、筛选条件与排序状态。"""
        self.width: int = width
        """ 面板内容区的显示宽度。 """
        self.chara_list_page = 0
        """ 当前显示的干员列表页码（从 0 开始）。 """
        self.info_category_list = [
            _("【体力气力】"),
            _("【好感信赖】"),
            _("【感度类】"),
            _("【扩张类】"),
            _("【刻印类】"),
            _("【基础属性】"),
            _("【工作技能】"),
            _("【性技能】"),
        ]
        """ 干员信息展示分类页签的标题列表。 """
        self.current_category_index = 0
        """ 当前选中的信息分类索引。 """
        self.filters = {key: 0 for key in svc.FILTER_STEPS}
        """ 五项干员筛选条件（工作、陷落、女儿、访客、收藏）的当前选项值。 """
        self.sort_main = _("默认ID")
        """ 主排序键的显示名称。 """
        self.sort_sub = _("无")
        """ 副排序键的显示名称。 """
        self.sort_reverse = False
        """ 干员列表是否倒序排列的开关。 """
        self.sort_collection_first = True
        """ 是否将已收藏干员优先排在前面的开关。 """
        self.choosing_sort_mode = 0
        """ 排序键选择模式（0 正常列表，1 选主排序，2 选副排序）。 """

    def change_chara_page(self, amount: int) -> None:
        """按增量 amount 调整当前干员列表页码。"""
        self.chara_list_page += amount

    def change_info_category(self, target_index: int) -> None:
        """将当前信息分类索引切换为 target_index。"""
        self.current_category_index = target_index

    def answer(self, yrn: object) -> None:
        """根据按钮返回码更新筛选、排序状态并在列表变更时回到首页。"""
        toggles = {f"toggle_filter_{k}": k for k in svc.FILTER_STEPS}
        if yrn in toggles:
            key = toggles[yrn]
            steps = svc.FILTER_STEPS[key]
            self.filters[key] = (self.filters[key] + 1) % steps
        elif yrn == "modify_sort_main":
            self.choosing_sort_mode = 1
            return
        elif yrn == "modify_sort_sub":
            self.choosing_sort_mode = 2
            return
        elif yrn == "reset_sort_main":
            self.sort_main = _("默认ID")
        elif yrn == "reset_sort_sub":
            self.sort_sub = _("无")
        elif yrn == "toggle_sort_reverse":
            self.sort_reverse = not self.sort_reverse
        elif yrn == "toggle_sort_collection_first":
            self.sort_collection_first = not self.sort_collection_first
        elif type(yrn) is str and yrn.startswith("select_sort_"):
            sort_key = yrn.replace("select_sort_", "")
            if self.choosing_sort_mode == 1:
                self.sort_main = sort_key
            elif self.choosing_sort_mode == 2:
                self.sort_sub = sort_key
            self.choosing_sort_mode = 0
        else:
            return
        self.chara_list_page = 0

    def _draw_controls(self, return_list: list[str]) -> None:
        """绘制信息分类栏、五项筛选按钮与排序控制栏。"""
        for i, cat_name in enumerate(self.info_category_list):
            if i == self.current_category_index:
                draw_text(f" {cat_name} ", style="gold_enrod")
            else:
                draw_button(
                    return_list,
                    draw.LeftButton,
                    f" {cat_name} ",
                    str(i + 1000),
                    len(cat_name) * 2 + 2,
                    cmd_func=self.change_info_category,
                    args=(i,),
                )
        line_feed.draw()
        draw.LineDraw("-", self.width).draw()
        bool_names = [_("不筛选"), _("是"), _("否")]
        filter_buttons = (
            ("work", _("[工作:{0}]"), [_("不筛选"), _("有"), _("无")]),
            (
                "fall",
                _("[陷落:{0}]"),
                [_("不筛选"), _("无"), _("有"), _("爱情"), _("隶属")],
            ),
            ("daughter", _("[女儿:{0}]"), bool_names),
            ("visitor", _("[访客:{0}]"), bool_names),
            ("collection", _("[收藏:{0}]"), bool_names),
        )
        draw_text(_(" 筛选: "))
        for key, label, names in filter_buttons:
            value = self.filters[key]
            draw_button(
                return_list,
                draw.LeftButton,
                label.format(names[value]),
                f"toggle_filter_{key}",
                18,
                cmd_func=pass_func,
                normal_style="gold_enrod" if value else "standard",
            )
        line_feed.draw()
        draw_text(_(" 排序: "))
        for prefix, text, value in (
            ("main", _("主排序:{0} "), self.sort_main),
            ("sub", _(" 副排序:{0} "), self.sort_sub),
        ):
            draw_text(text.format(value))
            for action, label, width in (
                ("modify", _("[修改]"), 8),
                ("reset", _("[重置默认]"), 12),
            ):
                draw_button(
                    return_list,
                    draw.LeftButton,
                    label,
                    f"{action}_sort_{prefix}",
                    width,
                    cmd_func=pass_func,
                )
        line_feed.draw()
        draw_text("       ")
        draw_button(
            return_list,
            draw.LeftButton,
            _("[升序]") if not self.sort_reverse else _("[倒序]"),
            "toggle_sort_reverse",
            8,
            cmd_func=pass_func,
        )
        draw_button(
            return_list,
            draw.LeftButton,
            _("[收藏优先]"),
            "toggle_sort_collection_first",
            12,
            cmd_func=pass_func,
            normal_style=(
                "gold_enrod" if self.sort_collection_first else "standard"
            ),
        )
        line_feed.draw()
        line_feed.draw()

    def _draw_sort_choices(
        self, return_list: list[str], columns: svc.Columns
    ) -> None:
        """绘制主排序或副排序的可选排序键按钮网格。"""
        target = _("主排序") if self.choosing_sort_mode == 1 else _("副排序")
        draw_text(_("正在修改 {0}，请选择:\n").format(target))
        groups = [
            [_("无"), _("默认ID"), _("好感"), _("信赖")],
            [
                _("体力"),
                _("最大体力"),
                _("气力"),
                _("最大气力"),
                _("催眠深度"),
                _("工作"),
                _("装备"),
            ],
        ]
        groups += [[name for name, _cid in cols] for cols in columns.values()]
        for group in groups:
            for opt in group:
                draw_button(
                    return_list,
                    draw.LeftButton,
                    f"[{opt}]",
                    f"select_sort_{opt}",
                    len(opt) * 2 + 4,
                    cmd_func=pass_func,
                )
            line_feed.draw()

    def draw(self, return_list: list[str]) -> None:
        """绘制全干员一览页签的完整界面，含表头、当前页行与翻页栏。"""
        columns = svc.ability_columns()
        self._draw_controls(return_list)
        if self.choosing_sort_mode != 0:
            self._draw_sort_choices(return_list, columns)
            return
        cols = columns.get(self.current_category_index - 2, [])
        skill_tab = self.current_category_index == 6
        if self.current_category_index >= 2:
            header = " " * 24 + "".join(f"{name}|" for name, _cid in cols)
            draw_text(header + (_("装备|工作") if skill_tab else ""))
        line_feed.draw()
        found = svc.visible_ids(
            self.filters,
            self.sort_main,
            self.sort_sub,
            self.sort_reverse,
            self.sort_collection_first,
        )
        page, total = svc.page_of(len(found), self.chara_list_page)
        self.chara_list_page = page
        size = svc.PAGE_SIZE
        shown = found[page * size : page * size + size]
        for character_id in shown:
            self._draw_row(return_list, character_id, cols, skill_tab)
            line_feed.draw()
        for _blank in range(size - len(shown)):
            line_feed.draw()
        line_feed.draw()
        draw.LineDraw("-", self.width).draw()
        self._page_button(return_list, _("[888]上一页"), "888", -1, page > 0)
        draw_text(_("  [{0}/{1}页]  ").format(page + 1, total))
        self._page_button(
            return_list, _("[222]下一页"), "222", 1, page < total - 1
        )

    def _page_button(
        self,
        return_list: list[str],
        text: str,
        key: str,
        step: int,
        active: bool,
    ) -> None:
        """按是否可翻页绘制有效翻页按钮或灰色禁用文本。"""
        if active:
            draw_button(
                return_list,
                draw.LeftButton,
                text,
                key,
                12,
                cmd_func=self.change_chara_page,
                args=(step,),
            )
        else:
            draw_text(text, 12, "deep_gray")

    def _draw_row(
        self,
        return_list: list[str],
        character_id: int,
        cols: list[tuple[str, int]],
        skill_tab: bool,
    ) -> None:
        """绘制单个干员的名字按钮及当前分类对应的属性列。"""
        data = identity.of(character_id)
        star = "⭐" if svc.is_collected(character_id) else "  "
        name = f"[{str(data.adv).rjust(4, '0')}]{star}{data.name}"
        draw_button(
            return_list,
            draw.LeftButton,
            attr_calculation.pad_display_width(name, 24),
            str(character_id),
            24,
            cmd_func=self.see_attr,
            args=(character_id,),
        )
        if self.current_category_index == 0:
            self._draw_bars(character_id)
        elif self.current_category_index == 1:
            self._draw_relation(character_id)
        else:
            ability = abilities.ability(character_id)
            for _name, col_id in cols:
                val = ability.get(col_id, 0)
                rank = attr_calculation.judge_grade(val)
                draw_text(
                    attr_calculation.pad_display_width(rank, 3),
                    style=f"level{rank.lower()}",
                )
                draw_text(f"{val}|")
            if skill_tab:
                equip, style = svc.equipment_label(character_id)
                draw_text(equip, style=style)
                draw_text("|")
                draw_text(svc.work_name(character_id))

    def _draw_bars(self, character_id: int) -> None:
        """绘制单个干员的体力条、气力条与当前状态标签。"""
        from Script.UI.Panel.character_info_head import (
            get_character_status_list,
        )

        state = needs.of(character_id)
        for bar, top, now, label in (
            ("HitPointbar", "hit_max", "hit", "体力"),
            ("ManaPointbar", "mana_max", "mana", "气力"),
        ):
            bar_draw = draw.InfoBarDraw()
            bar_draw.width = int(self.width / 5)
            bar_draw.scale = 0.8
            bar_draw.set(bar, int(state[top]), num.shown(state[now]), label)
            bar_draw.draw()
            shown = f"({num.shown(state[now])}/{int(state[top])})"
            draw_text(" " * max(0, 12 - len(shown)) + "   ")
        status_list, _temp_text = get_character_status_list(character_id)
        for status_draw in status_list:
            status_draw.draw()

    def _draw_relation(self, character_id: int) -> None:
        """绘制单个干员的好感、信赖、催眠深度、陷落与当前位置。"""
        favor = relations.favorability(character_id).get(0, 0)
        trust = relations.trust(character_id)
        degree = hypnosis.degree(character_id)
        fall_name, fall_color = svc.fall_label(character_id)
        draw_text(
            _(" 好感度: {0} | 信赖度: {1}% | 催眠深度: {2}% | 陷落: ").format(
                str(favor).ljust(6),
                str(round(trust, 1)).ljust(6),
                str(round(degree, 1)).ljust(5),
            )
        )
        draw_text(
            _("[{0}]").format(
                attr_calculation.pad_display_width(fall_name, 8, "center")
            ),
            style=fall_color,
        )
        draw_text(_(" | 现在位置: {0}").format(svc.position_text(character_id)))

    def see_attr(self, character_id: int) -> None:
        """打开干员属性详情面板查看目标干员，关闭后回到场景面板。"""
        now_draw = see_character_info_panel.SeeCharacterInfoHandleInScene(
            character_id, self.width, svc.operator_ids()
        )
        now_draw.draw()
        view.now_panel_id = constant.Panel.IN_SCENE
