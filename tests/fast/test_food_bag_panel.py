"""
食物背包面板交互测试
====================
本测试从 Script.UI.Panel 导入 food_bag_panel。
测试复用 Clicks，替换 draw.CenterButton 与 draw.LeftButton 的 draw 方法以注册按钮回调。
测试将 flow_handle.askfor_all 替换为 Clicks.answer，按预设应答执行命令并记录各页按钮与返回值。
用例覆盖页签切换分组、展开分组并选择进食，以及不可用分组不绘制为按钮。
"""

from collections.abc import Mapping
from unittest import mock
from uuid import UUID

from Script.Config import config_def, game_config
from Script.Core import constant, flow_handle
from Script.Modules.domains import inventory
from Script.Modules.tk_ui import player_pick
from Script.System.Cooking_System import cooking
from Script.UI.Moudle import draw, view
from Script.UI.Panel import food_bag_panel
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_bondage_and_discovered_panels import Clicks

WIDTH = 100
""" 传给食物背包面板的绘制宽度（100）。 """
MEAL = 9101
""" 测试用的食用类菜谱编号（9101）。 """
DRINK = 9102
""" 测试用的饮用类菜谱编号（9102）。 """
SEASONING = 11
""" 测试用的特殊调味编号（11）。 """
UIDS = (
    UUID("11111111-0000-4000-8000-000000000001"),
    UUID("22222222-0000-4000-8000-000000000002"),
    UUID("33333333-0000-4000-8000-000000000003"),
    UUID("44444444-0000-4000-8000-000000000004"),
)
""" 四组前三位字符互不相同的固定测试食物 UUID，用于生成稳定按钮返回值。 """


def recipe_table() -> dict[int, config_def.Recipes]:
    """构造包含 MEAL（类型 0）与 DRINK（类型 2）的测试菜谱编号到 Recipes 配置对象映射。"""
    table = {}
    for cid, kind in ((MEAL, 0), (DRINK, 2)):
        recipe = config_def.Recipes()
        vars(recipe).update(
            cid=cid,
            name=f"菜{cid}",
            type=kind,
            difficulty=1,
            introduce="",
            alcohol=0,
        )
        table[cid] = recipe
    return table


def summary(text: str) -> tuple[str, str]:
    """
    按空白切分按钮显示文本，返回首词与尾词组成的二元组。
    Keyword arguments:
    text -- str，待提取首尾词的按钮显示文本
    Return arguments:
    tuple[str, str] -- 按空白切分后的首词与尾词
    """
    words = text.split()
    return words[0], words[-1]


class FoodBagPanelTest(FastTestCase):
    """食物背包面板（FoodBagPanel）的页签分组、进食选择与禁用行交互测试。"""

    def setUp(self) -> None:
        """
        注册命令映射清理，创建角色 0（博士）并将饥饿与尿意分别设为 240 与 0。
        替换测试菜谱表，将 view.now_panel_id 设为 constant.Panel.FOOD_BAG，并创建 Clicks 辅助对象。
        拦截 draw.CenterButton 与 draw.LeftButton 的 draw 方法，并替换 flow_handle.askfor_all。
        """
        super().setUp()
        self.addCleanup(flow_handle.cmd_map.clear)
        self.world.chara(0, "博士")
        kernel_data.set_needs(0, hunger=240, urine=0)
        self.enterContext(
            mock.patch.object(game_config, "config_recipes", recipe_table())
        )
        self.enterContext(
            mock.patch.object(view, "now_panel_id", constant.Panel.FOOD_BAG)
        )
        self.clicks = Clicks(self)
        """ 驱动面板按钮交互并记录页面的 Clicks 辅助对象。 """
        bind = self.clicks.bind
        for button in (draw.CenterButton, draw.LeftButton):
            self.enterContext(
                mock.patch.object(
                    button, "draw", autospec=True, side_effect=bind
                )
            )
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self.clicks.answer)
        )

    def stock(self, *items: tuple[int, int]) -> list[UUID]:
        """
        按顺序取 UIDS 创建食物并设置特殊调味，再写入角色 0 背包。
        Keyword arguments:
        items -- tuple[tuple[int, int], ...]，待入包的（菜谱编号, 特殊调味编号）二元组序列
        Return arguments:
        list[UUID] -- 按入包顺序返回的食物 UUID 列表
        """
        uids = []
        with kernel_data.writing():
            for uid, (recipe, seasoning) in zip(
                UIDS[: len(items)], items, strict=True
            ):
                food = cooking.create_food("0", recipe)
                food.uid = uid
                food.special_seasoning = seasoning
                inventory.put_food(0, food)
                uids.append(uid)
        return uids

    def run_panel(self, *answers: str) -> None:
        """
        断言当前面板为 FOOD_BAG，写入预设应答并在 kernel_data.written 内绘制食物背包面板。
        绘制结束后断言预设应答已耗尽，并断言面板处于 IN_SCENE。
        Keyword arguments:
        answers -- tuple[str, ...]，按顺序执行的预设按钮返回值
        Return arguments:
        None -- 无返回值
        """
        self.assertEqual(view.now_panel_id, constant.Panel.FOOD_BAG)
        self.clicks.answers = list(answers)
        kernel_data.written(food_bag_panel.FoodBagPanel(WIDTH).draw)
        self.assertEqual(self.clicks.answers, [])
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)

    def test_tabs_split_meals_from_drinks(self) -> None:
        """
        向背包放入两份食用菜品与一份饮品，依次点击「饮用」与「返回」。
        断言两页的按钮返回值列表与分组行摘要，验证「食用」与「饮用」页签分别列出对应分组与数量。
        """
        meal, _second, drink = self.stock((MEAL, 0), (MEAL, 0), (DRINK, 0))
        self.run_panel("饮用", "返回")
        meal_group = f"\ngroup_菜{MEAL}_{str(meal)[:3]}"
        drink_group = f"\ngroup_菜{DRINK}_{str(drink)[:3]}"
        self.assertEqual(
            self.clicks.offers,
            [["饮用", meal_group, "返回"], ["食用", drink_group, "返回"]],
        )
        self.assertEqual(
            [summary(text) for text in self.clicks.pages[0][1:2]],
            [(f"菜{MEAL}", "x2")],
        )
        self.assertEqual(
            [summary(text) for text in self.clicks.pages[1][1:2]],
            [(f"菜{DRINK}", "x1")],
        )

    def test_group_lists_each_food_and_eats_the_pick(self) -> None:
        """
        放入两份同菜谱食物后展开分组并点选第二份，断言展开页列出两项进食返回值与「返回」并抛出 player_pick.Chosen。
        断言选定行为为 EAT、参数中的 food_uid 对应第二份食物，且面板处于 IN_SCENE。
        """
        first, second = self.stock((MEAL, 0), (MEAL, 0))
        group = f"\ngroup_菜{MEAL}_{str(first)[:3]}"
        eats = [f"\neat_菜{MEAL}_{str(uid)[:3]}" for uid in (first, second)]
        self.clicks.answers = [group, eats[1]]
        with self.assertRaises(player_pick.Chosen) as raised:
            food_bag_panel.FoodBagPanel(WIDTH).draw()
        self.assertEqual(self.clicks.answers, [])
        self.assertEqual(self.clicks.offers[1], [*eats, "返回"])
        data = raised.exception.action.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["behavior_id"], constant.Behavior.EAT)
        self.assertEqual(data["args"], {"food_uid": str(second)})
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)

    def test_unavailable_groups_are_not_buttons(self) -> None:
        """
        无目标且饥饿时放入普通与特殊调味食物，断言两分组中仅普通分组绘为按钮且特殊调味行返回值为 "2"。
        将角色 0 饥饿设为 0 后重开面板，断言两分组均不绘为按钮且页面按钮仅有「[饮用]」与「[返回]」。
        """
        meal, _seasoned = self.stock((MEAL, 0), (MEAL, SEASONING))
        meal_group = f"\ngroup_菜{MEAL}_{str(meal)[:3]}"
        self.run_panel("返回")
        self.assertEqual(
            self.clicks.offers, [["饮用", meal_group, "2", "返回"]]
        )
        page = self.clicks.pages[0]
        self.assertEqual(
            (page[0], summary(page[1]), page[2:]),
            ("[饮用]", (f"菜{MEAL}", "x1"), ["[返回]"]),
        )
        kernel_data.set_needs(0, hunger=0)
        view.now_panel_id = constant.Panel.FOOD_BAG
        self.clicks.offers = []
        self.clicks.pages = []
        self.run_panel("返回")
        self.assertEqual(self.clicks.offers, [["饮用", "0", "2", "返回"]])
        self.assertEqual(self.clicks.pages, [["[饮用]", "[返回]"]])
