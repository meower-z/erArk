"""
制作食物确认面板（make_food_confirm_panel）
===========================================
绘制菜谱列表按钮与批量制作二级确认弹窗，并在确认后提交做饭行动。
"""

from types import FunctionType
from Script.Core import get_text, flow_handle, text_handle, py_cmd
from Script.Design import attr_calculation
from Script.Modules.gameplay_resolution import make_food_service as service
from Script.Modules.tk_ui import player_pick
from Script.System.Cooking_System import cooking, cook_question_panel
from Script.UI.Moudle import draw
from Script.Config import game_config, normal_config

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def draw_q(val: int) -> None:
    """
    绘制品质预测文本
    Keyword arguments:
    val -- 食物品质值
    """
    _level, quality_name = attr_calculation.get_food_quality(val)
    d = draw.NormalDraw()
    d.text = f"[{quality_name}+{val}]"
    if val >= 7:
        d.style = "green"
    d.draw()


def draw_text(text: str) -> None:
    """创建普通文本绘制对象并立即输出给定文本。"""
    now_draw = draw.NormalDraw()
    now_draw.text = text
    now_draw.draw()


def draw_quality(base: int, top: int) -> None:
    """绘制基础品质标签，上界与基础值不同时追加波浪号与上界标签。"""
    draw_q(base)
    if top != base:
        draw_text("~")
        draw_q(top)


def add_button(
    return_list: list[str], text: str, return_text: str, width: int, **kw
) -> str:
    """绘制居中按钮，将其返回码追加到列表后返回该返回码。"""
    button = draw.CenterButton(text, return_text, width, **kw)
    button.draw()
    return_list.append(button.return_text)
    return button.return_text


class SeeFoodListByFoodNameDraw:
    """
    点击后可查看食物列表的食物名字按钮对象
    Keyword arguments:
    text -- 食物名字
    width -- 最大宽度
    is_button -- 绘制按钮
    num_button -- 绘制数字按钮
    button_id -- 数字按钮id
    """

    last_confirm_result: str
    """ 二级确认面板最后一次操作的结果（确认或取消），经类对象读写 """

    def __init__(
        self,
        text: tuple[str, str, int, int, int],
        width: int,
        is_button: bool,
        num_button: bool,
        button_id: int,
    ) -> None:
        """初始化绘制对象"""
        self.cid: str = text[0]
        """ 菜谱id字符串 """
        self.text: str = text[1]
        """ 食物名字 """
        self.special_seasoning = text[2]
        """ 调味类型 """
        self.cook_mode = text[3]
        """ 烹饪模式：0标准模式，1精细模式 """
        self.make_food_type = text[4]
        """ 做饭类型：0普通做饭，1泡咖啡，2酒类 """
        self.draw_text: str = ""
        """ 食物名字绘制文本 """
        self.width: int = width
        """ 最大宽度 """
        self.num_button: bool = num_button
        """ 绘制数字按钮 """
        self.button_id: int = button_id
        """ 数字按钮的id """
        self.button_return: str = str(button_id)
        """ 按钮返回值 """
        self.make_food_time: int = 0
        """ 做饭所需时间 """
        self.food_name: str = ""
        """ 食物名字 """
        self.add_coffee: bool = False
        """ 是否为加料咖啡 """
        self.last_confirm_result: str = ""
        """ 记录二级确认面板最后一次操作结果（如：取消） """

        name_draw: (
            draw.NormalDraw
            | draw.CenterDraw
            | draw.LeftButton
            | draw.CenterButton
        )
        if self.cid == "-1":
            self.draw_text = " "
            name_draw = draw.CenterDraw()
            name_draw.text = " "
            name_draw.width = self.width
            self.now_draw: (
                draw.NormalDraw | draw.LeftButton | draw.CenterButton
            ) = name_draw
            return

        self.food_cid: str = self.cid
        """ 菜谱id字符串 """
        food_recipe = game_config.config_recipes[int(self.food_cid)]
        self.food_name = food_recipe.name
        self.make_food_time = food_recipe.time
        if food_recipe.type == 8:
            self.add_coffee = True
        diff_text = _("难度{0}").format(food_recipe.difficulty)
        name_draw = draw.NormalDraw()
        if is_button:
            if num_button:
                index_text = text_handle.id_index(button_id)
                button_text = f"{index_text}[{diff_text}] {self.food_name}"
                name_draw = draw.LeftButton(
                    button_text,
                    self.button_return,
                    self.width,
                    cmd_func=self.make_food_for_sure,
                )
            else:
                button_text = f"[[{diff_text}] {self.food_name}]"
                name_draw = draw.CenterButton(
                    button_text,
                    str(self.text),
                    self.width,
                    cmd_func=self.make_food_for_sure,
                )
            self.button_return = name_draw.return_text
            self.draw_text = button_text
        else:
            name_draw = draw.CenterDraw()
            name_draw.text = f"[[{diff_text}] {self.food_name}]"
            name_draw.width = self.width
            self.draw_text = name_draw.text
        self.now_draw = name_draw
        """ 绘制的对象 """

    def make_food_for_sure(self) -> None:
        """确认是否制作食物，并选择制作数量"""
        recipe_id = int(self.food_cid)
        plan = service.confirm_plan(
            recipe_id,
            self.special_seasoning,
            self.cook_mode,
            self.make_food_type,
        )
        make_count = plan.start_count
        introduce = game_config.config_recipes[recipe_id].introduce
        while 1:
            py_cmd.clr_cmd()
            line_feed.draw()
            confirm_text, make_food_time = service.confirm_text(
                plan, make_count
            )
            draw_text(confirm_text)
            draw_text(_("品质预测: "))
            draw_quality(plan.base_quality, plan.max_quality)
            draw_text(_("\n介绍    : {0}\n").format(introduce))
            line_feed.draw()
            return_list: list[str] = []
            quarter = int(window_width / 4)
            minus = add_button(return_list, _("[-1]"), _("减少"), quarter)
            plus = add_button(return_list, _("[+1]"), _("增加"), quarter)
            top = add_button(return_list, _("[最大]"), _("最大"), quarter)
            line_feed.draw()
            line_feed.draw()
            half = int(window_width / 2)
            confirm = add_button(return_list, _("[确认制作]"), _("确认"), half)
            add_button(return_list, _("[取消]"), _("取消"), half)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == minus:
                make_count = max(1, make_count - 1)
            elif yrn == plus:
                make_count = min(plan.max_count, make_count + 1)
            elif yrn == top:
                make_count = plan.max_count
            elif yrn == confirm:
                service.remember_count(self.make_food_type, make_count)
                self.make_food(make_food_time, make_count)
                SeeFoodListByFoodNameDraw.last_confirm_result = _("确认")
                break
            else:
                SeeFoodListByFoodNameDraw.last_confirm_result = _("取消")
                break

    def make_food(
        self, new_make_food_time: int = 0, make_count: int = 1
    ) -> None:
        """
        玩家定下做饭：调味材料连一份都不够时提示后不定下行动；精细模式先答题定下品质；
        食物在行动开始时由 panel_starters 的 make_food 做出
        Keyword arguments:
        new_make_food_time -- 本次制作的总耗时（分钟）
        make_count -- 制作数量
        """
        recipe_id = int(self.food_cid)
        if not cooking.player_can_season(self.special_seasoning):
            py_cmd.clr_cmd()
            line_feed.draw()
            draw_text(_("制作失败：没有足够的调味材料或精液量！\n"))
            line_feed.draw()
            return
        food_quality = service.recipe_quality(recipe_id)
        if service.asks_questions(recipe_id, self.cook_mode):
            food_quality = cook_question_panel.run_cook_question_flow(
                recipe_id, food_quality, self.special_seasoning
            )
        behavior_id, state = service.cook_behavior(self.add_coffee)
        player_pick.choose(
            behavior_id,
            new_make_food_time,
            kind="make_food",
            state=state,
            fields={"behavior.make_food_time": new_make_food_time},
            args={
                "recipe_id": recipe_id,
                "count": make_count,
                "quality": food_quality,
                "seasoning": self.special_seasoning,
            },
        )

    def draw(self) -> None:
        """绘制对象"""
        self.now_draw.draw()
