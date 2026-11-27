"""
制作食物与批量确认面板交互测试
==============================
本测试从 Script.UI.Panel 导入 make_food_confirm_panel 与 make_food_panel。
测试替换两类按钮的 draw 方法，经 flow_handle.bind_cmd 注册按钮回调。
Clicks.answer 替换 flow_handle.askfor_all，按预设应答执行已绑定命令并记录各页按钮。
用例覆盖页签切换与取消返回、筛选排序重置、调味与模式选择、加料咖啡入口、药物库存上限及调试模式无库存退出。
"""

import unittest
from collections.abc import Callable, Mapping
from unittest import mock

from Script.Config import config_def, game_config, normal_config
from Script.Core import constant, flow_handle
from Script.Modules.domains import inventory, modes
from Script.Modules.tk_ui import player_pick
from Script.UI.Moudle import draw, view
from Script.UI.Panel import make_food_confirm_panel, make_food_panel
from tests import chara_abilities as ca, kernel_data
from tests.fast.base import FastTestCase

WIDTH = 100
""" 传给面板与菜谱按钮的绘制宽度。 """
DRUG = 105
""" 测试使用的药物类调味配置编号 105。 """
RECIPES = (
    (9001, 0, 1, 30),
    (9002, 0, 5, 60),
    (9003, 1, 2, 20),
    (9004, 8, 1, 10),
)
""" 测试菜谱条目，每项依次为（菜谱编号, 类型, 难度, 制作时间）。 """


def recipe_table() -> dict[int, config_def.Recipes]:
    """按 RECIPES 构造以菜谱编号为键的 Recipes 配置字典。"""
    table = {}
    for cid, kind, difficulty, time in RECIPES:
        recipe = config_def.Recipes()
        vars(recipe).update(
            cid=cid,
            name=f"菜{cid}",
            type=kind,
            difficulty=difficulty,
            time=time,
            introduce="",
        )
        table[cid] = recipe
    return table


class Clicks:
    """按预设应答驱动按钮交互并记录各页按钮文本的测试辅助类。"""

    def __init__(self, case: unittest.TestCase) -> None:
        """
        绑定测试用例实例，并初始化应答队列、当前页按钮列表与历史页面列表。
        Keyword arguments:
        case -- unittest.TestCase，用于执行断言的测试用例实例
        Return arguments:
        None -- 无返回值
        """
        self.case = case
        """ 用于执行断言的测试用例实例。 """
        self.answers: list[str] = []
        """ 按消费顺序排列的预设按钮返回值队列。 """
        self.drawn: list[str] = []
        """ 当前页面已绘制、尚未归档的按钮文本列表。 """
        self.pages: list[list[str]] = []
        """ 每次应答前已绘制的各页按钮文本列表。 """

    def bind(self, button: draw.CenterButton) -> None:
        """
        记录按钮显示文本，并按 button.return_text 经 flow_handle.bind_cmd 注册按钮回调与参数。
        Keyword arguments:
        button -- draw.CenterButton，调用 draw 方法的按钮对象（含子类 draw.LeftButton）
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append(button.text)
        flow_handle.bind_cmd(button.return_text, button.cmd_func, button.args)

    def answer(self, return_list: list[str], *args: object) -> str:
        """
        断言存在预设应答并取出队首项，再断言该项在 return_list 中并将当前页按钮归档到 self.pages。
        从 flow_handle.cmd_map 取出对应命令（未绑定时取 null_func），清空 cmd_map 后执行该命令并返回该应答。
        Keyword arguments:
        return_list -- list[str]，面板本次给出的按钮返回值列表
        args -- tuple[object, ...]，其余位置参数，本方法不使用
        Return arguments:
        str -- 本次消费的预设按钮返回值
        """
        self.case.assertTrue(
            self.answers, f"缺少预设应答，当前可选返回值：{return_list}"
        )
        wanted = self.answers.pop(0)
        self.case.assertIn(wanted, return_list)
        self.pages.append(self.drawn)
        self.drawn = []
        command = flow_handle.cmd_map.get(wanted, flow_handle.null_func)
        flow_handle.cmd_map.clear()
        command()
        return wanted

    def dishes(self) -> list[list[str]]:
        """
        按页提取 self.pages 中包含「] 菜」的按钮文本，返回「] 」之后的菜名列表。
        Return arguments:
        list[list[str]] -- 与 self.pages 逐页对应的菜名列表
        """
        return [
            [text.split("] ")[-1] for text in page if "] 菜" in text]
            for page in self.pages
        ]


class MakeFoodPanelTest(FastTestCase):
    """制作食物主面板与批量确认面板的按钮交互测试。"""

    def setUp(self) -> None:
        """
        初始化料理技能为 5 的博士角色、清空药物调味库存，并替换测试菜谱表与面板设置状态。
        创建 Clicks 辅助对象，并拦截 draw.CenterButton 与 draw.LeftButton 的 draw 方法及 flow_handle.askfor_all。
        """
        super().setUp()
        self.world.chara(0, "博士")
        ca.ability(0)[43] = 5
        for seasoning_cid in game_config.config_seasoning:
            if seasoning_cid > 100:
                kernel_data.put(inventory.set_item, 0, seasoning_cid, 0)
        self.enterContext(
            mock.patch.object(game_config, "config_recipes", recipe_table())
        )
        for name, value in (
            ("makefood_data", {}),
            ("makefood_filter_type", []),
            ("makefood_filter_difficulty", -1),
            ("makefood_filter_time", -1),
            ("makefood_sort_type", 0),
            ("makefood_sort_order", 0),
            ("now_panel_id", constant.Panel.MAKE_FOOD),
        ):
            self.enterContext(mock.patch.object(view, name, value))
        setting = normal_config.system_setting
        for name in ("makefood_cook_mode", "makefood_make_count"):
            self.enterContext(mock.patch.object(setting, name, {}))
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

    def run_panel(self, *answers: str) -> None:
        """
        写入预设应答并绘制默认入口的 Make_food_Panel，返回后断言预设应答已耗尽。
        Keyword arguments:
        answers -- tuple[str, ...]，按顺序执行的预设按钮返回值
        Return arguments:
        None -- 无返回值
        """
        self.clicks.answers = list(answers)
        make_food_panel.Make_food_Panel(WIDTH).draw()
        self.assertEqual(self.clicks.answers, [])

    def chosen(self, pick: Callable[[], object], *answers: str) -> dict:
        """
        写入预设应答并运行 pick，断言抛出 player_pick.Chosen、应答已耗尽且食物背包为空，返回选定行动数据字典。
        Keyword arguments:
        pick -- Callable[[], object]，触发面板交互并提交行动的可调用对象
        answers -- tuple[str, ...]，按顺序执行的预设按钮返回值
        Return arguments:
        dict -- 所抛异常中 action.action_data 转换得到的字典
        """
        self.clicks.answers = list(answers)
        with self.assertRaises(player_pick.Chosen) as raised:
            pick()
        self.assertEqual(self.clicks.answers, [])
        self.assertEqual(inventory.foods(0), {})
        data = raised.exception.action.action_data
        assert isinstance(data, Mapping)
        return dict(data)

    def test_tab_then_cancelled_pick_keeps_panel_open(self) -> None:
        """
        切换至「零食」页签并点选菜谱后在确认页点击「取消」，验证主面板重绘而非退出。
        随后点击「返回」，断言四页菜谱列表、面板切回 IN_SCENE、未记录制作数量且食物背包为空。
        """
        self.run_panel("零食", "0", "取消", "返回")
        self.assertEqual(
            self.clicks.dishes(),
            [["菜9001", "菜9002"], ["菜9003"], [], ["菜9003"]],
        )
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        self.assertEqual(normal_config.system_setting.makefood_make_count, {})
        self.assertEqual(inventory.foods(0), {})

    def test_list_buttons_sort_filter_and_reset(self) -> None:
        """
        依次操作排序维度、排序顺序、筛选子面板、重置按钮与返回按钮，断言七个页面的菜谱列表变化。
        验证重置后难度筛选回到 -1、排序维度回到 0，且返回后退出至 IN_SCENE。
        """
        self.run_panel(
            "sort_type_1",
            "sort_order_1",
            "[筛选]",
            "diff_0",
            "返回",
            "重置所有",
            "返回",
        )
        self.assertEqual(
            self.clicks.dishes(),
            [
                ["菜9001", "菜9002"],
                ["菜9001", "菜9002"],
                ["菜9002", "菜9001"],
                [],
                [],
                ["菜9001"],
                ["菜9001", "菜9002"],
            ],
        )
        self.assertEqual(
            (view.makefood_filter_difficulty, view.makefood_sort_type),
            (-1, 0),
        )
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)

    def test_seasoning_and_mode_reach_chosen_action(self) -> None:
        """
        持有 2 份 DRUG 时选定该调味与「精细模式」，进入确认页增加数量后确认制作。
        断言选定行动为 MAKE_FOOD 且参数正确，断言烹饪模式与数量设置已保存且 DRUG 库存尚未扣减。
        """
        kernel_data.put(inventory.set_item, 0, DRUG, 2)
        seasoning = f"[{game_config.config_seasoning[DRUG].name}]"
        panel = make_food_panel.Make_food_Panel(WIDTH)
        data = self.chosen(
            panel.draw, seasoning, "精细模式", "0", "增加", "确认"
        )
        self.assertEqual(data["behavior_id"], constant.Behavior.MAKE_FOOD)
        self.assertEqual(
            {k: data["args"][k] for k in ("recipe_id", "count", "seasoning")},
            {"recipe_id": 9001, "count": 2, "seasoning": DRUG},
        )
        setting = normal_config.system_setting
        self.assertEqual(
            (setting.makefood_cook_mode, setting.makefood_make_count),
            ({0: 1}, {0: 2}),
        )
        self.assertEqual(inventory.items(0)[DRUG], 2)

    def test_coffee_entry_picks_coffee_behavior(self) -> None:
        """
        以 make_food_type=1 打开加料咖啡入口并确认首个菜谱，断言首页仅列出菜9004。
        断言选定行动为 MAKE_COFFEE_ADD、状态为 STATUS_MAKE_COFFEE_ADD、菜谱编号为 9004 且数量记入入口 1。
        """
        panel = make_food_panel.Make_food_Panel(WIDTH, make_food_type=1)
        data = self.chosen(panel.draw, "0", "确认")
        self.assertEqual(self.clicks.dishes()[0], ["菜9004"])
        self.assertEqual(
            (data["behavior_id"], data["state"], data["args"]["recipe_id"]),
            (
                constant.Behavior.MAKE_COFFEE_ADD,
                constant.CharacterStatus.STATUS_MAKE_COFFEE_ADD,
                9004,
            ),
        )
        self.assertEqual(
            normal_config.system_setting.makefood_make_count, {1: 1}
        )

    def test_count_buttons_stay_within_drug_stock(self) -> None:
        """
        持有 3 份 DRUG 时直接调用菜谱按钮的 make_food_for_sure，依次点击一次减少、三次增加与确认。
        断言提交的菜谱编号为 9003、数量为 3，且 makefood_make_count 记为 {0: 3}。
        """
        kernel_data.put(inventory.set_item, 0, DRUG, 3)
        button = make_food_confirm_panel.SeeFoodListByFoodNameDraw(
            ("9003", "", DRUG, 0, 0), WIDTH, True, True, 0
        )
        data = self.chosen(
            button.make_food_for_sure, "减少", "增加", "增加", "增加", "确认"
        )
        self.assertEqual(
            (data["args"]["recipe_id"], data["args"]["count"]), (9003, 3)
        )
        self.assertEqual(
            normal_config.system_setting.makefood_make_count, {0: 3}
        )

    def test_debug_drug_without_stock_returns_to_scene(self) -> None:
        """
        调试模式下无 DRUG 库存时仍可选中该调味并确认制作，验证流程不抛出 player_pick.Chosen。
        断言面板正常返回并切回 IN_SCENE，且玩家食物背包保持为空。
        """
        self.enterContext(mock.patch.object(modes, "debug", return_value=True))
        seasoning = f"[{game_config.config_seasoning[DRUG].name}]"
        self.run_panel(seasoning, "0", "确认")
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        self.assertEqual(inventory.foods(0), {})
