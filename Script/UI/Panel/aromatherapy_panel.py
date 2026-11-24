"""香薰疗愈界面面板"""

from types import FunctionType
from Script.Core import get_text, flow_handle, constant
from Script.UI.Moudle import draw, view
from Script.Config import normal_config
from Script.Modules.tk_ui import player_pick
from Script.Modules.gameplay_resolution import aromatherapy_query

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class Aromatherapy_Panel:
    """
    用于香薰疗愈的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("香薰疗愈")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """
        self.now_choice_recipe_id = 0
        """ 当前选择的配方id """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("香薰疗愈")
        title_draw = draw.TitleLineDraw(title_text, self.width)

        while 1:
            snapshot = aromatherapy_query.build_aromatherapy_snapshot(
                self.now_choice_recipe_id
            )
            return_list = []
            title_draw.draw()

            # 绘制交易信息
            all_info_draw = draw.NormalDraw()
            all_info_draw.width = self.width

            now_text = ""
            now_text += _("\n  今日剩余调香次数    ：  {0}次").format(
                snapshot.remaining_today
            )
            all_info_draw.text = now_text
            all_info_draw.draw()
            line_feed.draw()

            now_text = ""
            now_text += _("\n  当前调香对象        ：  {0}").format(
                snapshot.target_name
            )
            if snapshot.target_today_recipe_name is not None:
                now_text += _("(今日已调香-{0})").format(
                    snapshot.target_today_recipe_name
                )
            all_info_draw.text = now_text
            all_info_draw.draw()
            line_feed.draw()

            now_text = ""
            now_text += _("\n  当前调香资源        ：")
            for item in snapshot.resources:
                now_text += f"  {item.name}：{item.amount}"
            all_info_draw.text = now_text
            all_info_draw.draw()
            line_feed.draw()

            now_text = ""
            now_text += _("\n  当前选择的调香配方  ：")
            now_text += f"  {snapshot.selected_recipe_name}"
            all_info_draw.text = now_text
            all_info_draw.draw()
            line_feed.draw()
            line_feed.draw()

            button_text = _(" [001]选择配方 ")
            button_draw = draw.CenterButton(
                _(button_text),
                _("1"),
                len(button_text) * 2,
                cmd_func=self.select_recipe,
            )
            return_list.append(button_draw.return_text)
            button_draw.draw()

            line_feed.draw()
            line_feed.draw()
            yes_draw = draw.CenterButton(
                _("[确定]"), _("确定"), int(window_width / 2)
            )
            if snapshot.can_confirm:
                yes_draw.draw()
                return_list.append(yes_draw.return_text)
            back_draw = draw.CenterButton(
                _("[返回]"), _("返回"), int(window_width / 2)
            )
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break
            elif yrn == yes_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                self.run_aromatherapy()
                break

    def select_recipe(self) -> None:
        """选择配方"""
        while 1:
            snapshot = aromatherapy_query.build_aromatherapy_snapshot(
                self.now_choice_recipe_id
            )
            line = draw.LineDraw("-", window_width)
            line.draw()
            all_info_draw = draw.NormalDraw()
            return_list = []

            now_text = ""
            now_text += _("\n\n当前可选的配方有：\n")
            all_info_draw.text = now_text
            all_info_draw.draw()

            for option in snapshot.recipes:
                recipes_text = (
                    f"[{str(option.recipe_id).rjust(3,'0')}]{option.name}"
                    + "".join(option.lock_reasons)
                    + f"：{option.info}"
                )
                if option.unlocked:
                    line_feed.draw()
                    button_draw = draw.LeftButton(
                        recipes_text,
                        f"\n{option.recipe_id}",
                        window_width,
                        cmd_func=self.change_now_choice_recipe_id,
                        args=(option.recipe_id),
                    )
                    button_draw.draw()
                    return_list.append(button_draw.return_text)
                    line_feed.draw()

                    now_text = _("     调香消耗：")
                    for ingredient in option.ingredients:
                        now_text += (
                            f"  {ingredient.name}：{ingredient.required}"
                        )

                    all_info_draw.text = now_text
                    all_info_draw.draw()
                else:
                    text_draw = draw.NormalDraw()
                    text_draw.text = recipes_text
                    text_draw.style = "deep_gray"
                    text_draw.draw()
                line_feed.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break

    def change_now_choice_recipe_id(self, recipe_id: int) -> None:
        """更改当前选择的配方id"""
        self.now_choice_recipe_id = recipe_id

    def run_aromatherapy(self) -> None:
        """进行调香"""
        plan = aromatherapy_query.plan_aromatherapy_action(
            self.now_choice_recipe_id
        )
        if plan.outcome.accepted and plan.behavior_id is not None:
            player_pick.choose(
                plan.behavior_id,
                60,
                kind="aromatherapy",
                state=plan.state,
                args={"recipe_id": plan.recipe_id},
            )
