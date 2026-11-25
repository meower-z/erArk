"""
做饭面板服务测试
================
验证 make_food_service 的筛选排序文本、分页补齐、调味显示与品质预测。
验证份数上限、耗时换算、确认文案与行为选择，并在无界面子进程中运行服务。
"""

import os
from unittest import mock

from Script.Config import config_def, game_config, normal_config
from Script.Core import constant
from Script.Design import basement, map_handle
from Script.Modules.domains import inventory, modes
from Script.Modules.gameplay_resolution import make_food_service as service
from Script.System.Cooking_System import cooking
from tests import chara_abilities as ca, kernel_data
from tests.chara_activity import place
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

ENCODINGS = ("cp1252", "gbk", "utf-16")
""" 无界面子进程测试遍历的 PYTHONIOENCODING 编码列表。 """
DRUG = min(cid for cid in game_config.config_seasoning if cid > 100)
""" 调味配置中编号大于 100 的最小药物编号。 """
NONE = service.ListFilter((), -1, -1, 0, 0)
""" 无筛选且无排序的默认 ListFilter 实例。 """
UI_FREE_RUN = """
from Script.Config import game_config, map_config, normal_config
from Script.Core import constant
from Script.Design import map_handle
from Script.Kernel import core
from Script.Modules.domains import identity, inventory, modes
from Script.Modules.gameplay_resolution import make_food_service as service
from Script.Modules.gameplay_resolution import working
from tests import chara_abilities, kernel_data
from tests.chara_activity import place
from tests.world import DEFAULT_SCENE, start_time
map_config.init_map_data()
kernel_data.reset_clock(start_time(), {})
kernel_data.put(identity.put, identity.Identity(0, name="p", sex=1))
chara_abilities.zero_tables(0)
place(0, DEFAULT_SCENE)
drug = min(cid for cid in game_config.config_seasoning if cid > 100)
wine = min(c for c, r in game_config.config_recipes.items() if r.type == 3)
query = service.ListFilter((0, 6), 1, 2, 2, 1)
rows = [service.status_text(query), service.status_text(service.ListFilter((), -1, -1, 0, 0))]
data = {str(c): c for c in game_config.config_recipes}
rows.append(len(service.button_rows(data, "主食", query, 0, 1, 0)))
with working.based_on(core.state()):
    inventory.set_item(0, drug, 0)
    rows.append(service.seasoning_listed(drug))
    modes.set_debug(True)
    rows.append(service.seasoning_listed(drug))
    modes.set_debug(False)
    inventory.set_item(0, drug, 3)
    rows.append([service.seasoning_listed(drug), service.max_count(drug)])
    normal_config.system_setting.makefood_cook_mode[0] = 5
    service.check_cook_mode(0)
    service.set_cook_mode(2, 1)
    normal_config.system_setting.makefood_make_count[1] = 0
    service.remember_count(2, 4)
    plan = service.confirm_plan(wine, drug, 1, 2)
    rows.append([plan.max_count, plan.start_count, service.cook_mode(2)])
    rows.append(service.confirm_text(plan, 2)[1] > 0)
    rows.append([service.panel_quality(1), service.asks_questions(wine, 1)])
    rows.append(service.cook_behavior(True))
    rows.append([service.cook_mode(0), service.start_count(1, 5)])
    rows.append([service.make_time(60, 1, 0.8), service.make_time(60, 1, 1.25)])
    bar = next(k for k, s in constant.scene_data.items() if "Bar" in s.scene_tag)
    place(0, map_handle.get_map_system_path_for_str(bar))
    dish = min(c for c, r in game_config.config_recipes.items() if r.type == 0)
    rows.append(service.recipe_quality(wine) - service.recipe_quality(dish))
payload["rows"] = rows
"""
""" 在拦截界面与结算模块的子进程中执行服务接口的测试脚本。 """


def recipe(
    cid: int, kind: int, difficulty: int, time: int
) -> config_def.Recipes:
    """构造带编号、类型、难度与耗时的测试菜谱配置对象。"""
    row = config_def.Recipes()
    row.cid = cid
    row.name = f"菜{cid}"
    row.type = kind
    row.difficulty = difficulty
    row.time = time
    row.alcohol = 0
    return row


def bar_scene() -> list[str]:
    """查找带 Bar 标签的场景并转换为系统地图路径列表。"""
    path = next(
        key
        for key, scene in constant.scene_data.items()
        if "Bar" in scene.scene_tag
    )
    return map_handle.get_map_system_path_for_str(path)


class MakeFoodCase(FastTestCase):
    """做饭服务单元测试基类，创建博士角色并隔离烹饪系统设置。"""

    def setUp(self) -> None:
        """初始化测试世界、创建博士角色并隔离模式与份数设置字典。"""
        super().setUp()
        self.world.chara(0, "博士")
        setting = normal_config.system_setting
        for name in ("makefood_cook_mode", "makefood_make_count"):
            self.enterContext(mock.patch.dict(getattr(setting, name)))


class ListTextTest(MakeFoodCase):
    """验证状态文本与菜谱按钮行生成逻辑的测试集。"""

    def test_status_text_names_every_filter_and_sort(self) -> None:
        """验证空条件、多类型含未知编号以及各难度时间排序档位的状态文本。"""
        self.assertEqual(service.status_text(NONE), ("筛选：无", "排序：无"))
        query = service.ListFilter((0, 6, 9), 1, 2, 2, 1)
        self.assertEqual(
            service.status_text(query),
            (
                "筛选：类型:正餐,6,其他 难度:中等(4-6) 时间:耗时(61+分)",
                "排序：时间降序",
            ),
        )
        query = service.ListFilter((), 0, 0, 1, 0)
        self.assertEqual(
            service.status_text(query),
            ("筛选：难度:简单(0-3) 时间:快速(≤30分)", "排序：难度升序"),
        )

    def test_button_rows_filter_sort_and_pad_to_pages(self) -> None:
        """验证菜谱按钮行的筛选、降序排序以及按 50 行整页补齐规则。"""
        table = {cid: recipe(cid, 0, cid % 9, 10 * cid) for cid in range(1, 61)}
        table[61] = recipe(61, 1, 2, 5)
        self.enterContext(
            mock.patch.object(game_config, "config_recipes", table)
        )
        data = {str(cid): cid for cid in table}
        rows = service.button_rows(
            data, "主食", service.ListFilter((), 2, 2, 1, 1), 11, 1, 2
        )
        picked = [cid for cid in range(7, 61) if cid % 9 >= 7]
        picked.sort(key=lambda cid: cid % 9, reverse=True)
        self.assertEqual(
            rows[: len(picked)],
            [(str(cid), f"菜{cid}", 11, 1, 2) for cid in picked],
        )
        self.assertEqual(
            rows[len(picked) :], [("-1", "", 11, 1, 2)] * (50 - len(picked))
        )
        some = {str(cid): cid for cid in range(1, 51)}
        self.assertEqual(
            len(service.button_rows(some, "主食", NONE, 0, 0, 0)), 50
        )
        self.assertEqual(
            len(service.button_rows(data, "主食", NONE, 0, 0, 0)), 100
        )
        self.assertEqual(
            service.button_rows(data, "饮品", NONE, 0, 0, 1),
            [("-1", "", 0, 0, 1)] * 50,
        )


class SeasoningAndModeTest(MakeFoodCase):
    """验证调味显示条件与烹饪模式读写校验的测试集。"""

    def test_drug_listed_with_stock_or_debug(self) -> None:
        """验证非药物显示及药物在库存或调试模式下的显示规则。"""
        kernel_data.put(inventory.set_item, 0, DRUG, 0)
        self.assertTrue(service.seasoning_listed(11))
        self.assertTrue(service.seasoning_listed(100))
        self.assertFalse(service.seasoning_listed(DRUG))
        kernel_data.put(modes.set_debug, True)
        self.assertTrue(service.seasoning_listed(DRUG))
        kernel_data.put(modes.set_debug, False)
        kernel_data.put(inventory.set_item, 0, DRUG, 1)
        self.assertTrue(service.seasoning_listed(DRUG))

    def test_cook_mode_per_type_and_bad_value_reset(self) -> None:
        """验证烹饪模式按入口独立读写，非法值归零且不污染缺省键。"""
        service.set_cook_mode(1, 1)
        service.set_cook_mode(2, 7)
        self.assertEqual(
            [service.cook_mode(t) for t in (0, 1, 2, 3)], [0, 1, 7, 0]
        )
        for make_food_type in (1, 2, 3):
            service.check_cook_mode(make_food_type)
        self.assertEqual(
            [service.cook_mode(t) for t in (0, 1, 2, 3)], [0, 1, 0, 0]
        )
        self.assertNotIn(3, normal_config.system_setting.makefood_cook_mode)


class QualityTest(MakeFoodCase):
    """验证主面板品质预测、酒吧加成与题库判定的测试集。"""

    def test_panel_quality_fine_mode_adds_four_up_to_cap(self) -> None:
        """验证精细模式在基础品质上最多加 4 且不超过品质绝对上限。"""
        top = cooking.get_max_food_quality()
        good = cooking.get_good_quality_cap()
        ca.ability(0)[43] = 2
        self.assertEqual(service.panel_quality(0), (2, 2))
        self.assertEqual(service.panel_quality(1), (2, min(6, top)))
        ca.ability(0)[43] = 99
        self.assertEqual(service.panel_quality(1), (good, min(good + 4, top)))

    def test_wine_gains_one_in_bar_and_questions_need_library(self) -> None:
        """验证酒吧内酒类基础品质加 1，以及精细答题依赖题库存在。"""
        ca.ability(0)[43] = 2
        wine = min(
            c for c, r in game_config.config_recipes.items() if r.type == 3
        )
        dish = min(
            c for c, r in game_config.config_recipes.items() if r.type == 0
        )
        self.assertEqual(
            [service.recipe_quality(r) for r in (wine, dish)], [2, 2]
        )
        place(0, bar_scene())
        self.assertEqual(
            [service.recipe_quality(r) for r in (wine, dish)], [3, 2]
        )
        asked = next(
            c
            for c in game_config.config_recipes
            if cooking.has_cook_question_library(c)
        )
        bare = next(
            c
            for c in game_config.config_recipes
            if not cooking.has_cook_question_library(c)
        )
        self.assertEqual(
            [
                service.asks_questions(asked, 1),
                service.asks_questions(asked, 0),
            ],
            [True, False],
        )
        self.assertFalse(service.asks_questions(bare, 1))


class ConfirmTest(MakeFoodCase):
    """验证份数上下限、耗时换算、确认文案与行为选择的测试集。"""

    def test_counts_follow_drug_stock_and_memory(self) -> None:
        """验证药物库存约束最大份数并保底 1，起始份数钳制且拦截非法记忆。"""
        kernel_data.put(inventory.set_item, 0, DRUG, 3)
        self.assertEqual(
            [service.max_count(0), service.max_count(DRUG)], [10, 3]
        )
        kernel_data.put(inventory.set_item, 0, DRUG, 0)
        self.assertEqual(service.max_count(DRUG), 1)
        service.remember_count(1, 7)
        self.assertEqual(normal_config.system_setting.makefood_make_count[1], 7)
        self.assertEqual(
            [service.start_count(1, 10), service.start_count(1, 3)], [7, 3]
        )
        setting = normal_config.system_setting
        for bad in (0, -2, "4", None):
            with mock.patch.object(setting, "makefood_make_count", {1: bad}):
                self.assertEqual(service.start_count(1, 10), 1)
        self.assertEqual(service.start_count(9, 10), 1)

    def test_make_time_scales_by_count_and_facility(self) -> None:
        """验证耗时按份数递增与设施效率缩放，以及零耗时与零变动后缀。"""
        self.assertEqual(service.make_time(30, 1, 1.0), (30, ""))
        self.assertEqual(service.make_time(30, 3, 1.0), (36, ""))
        self.assertEqual(service.make_time(60, 1, 0.8), (75, "（+25.0%）"))
        self.assertEqual(service.make_time(60, 1, 1.25), (48, "（-20.0%）"))
        self.assertEqual(service.make_time(0, 4, 0.5), (0, ""))
        self.assertEqual(service.make_time(10, 1, 1.01), (9, "（-10.0%）"))
        self.assertEqual(service.make_time(100, 1, 0.9999), (100, ""))

    def test_plan_and_text_for_wine_with_drug(self) -> None:
        """验证带药酒类与普通菜谱的确认参数快照及确认文本各项内容。"""
        ca.ability(0)[43] = 1
        wine = min(
            c for c, r in game_config.config_recipes.items() if r.type == 3
        )
        recipe_row = game_config.config_recipes[wine]
        kernel_data.put(inventory.set_item, 0, DRUG, 4)
        service.remember_count(2, 6)
        kernel_data.set_facility_level(4, 1)
        kernel_data.set_facility_level(5, 5)
        plan = service.confirm_plan(wine, DRUG, 0, 2)
        leisure = basement.calc_facility_efficiency(5)
        self.assertNotEqual(leisure, basement.calc_facility_efficiency(4))
        self.assertEqual(plan.facility_adjust, leisure)
        self.assertEqual(
            (
                plan.recipe_id,
                plan.seasoning_name,
                plan.base_quality,
                plan.max_quality,
            ),
            (wine, game_config.config_seasoning[DRUG].name, 1, 1),
        )
        self.assertEqual((plan.max_count, plan.start_count), (4, 4))
        asked = next(
            c
            for c, r in game_config.config_recipes.items()
            if r.type != 3 and cooking.has_cook_question_library(c)
        )
        fine = service.confirm_plan(asked, 0, 1, 0)
        self.assertEqual(
            (fine.base_quality, fine.max_quality, fine.start_count),
            (1, min(5, cooking.get_max_food_quality()), 1),
        )
        text, total = service.confirm_text(plan, 3)
        expected, _suffix = service.make_time(
            recipe_row.time, 3, plan.facility_adjust
        )
        self.assertEqual(total, expected)
        alcohol = game_config.config_alcohol_level[recipe_row.alcohol].name
        for line in (
            f"食物名字: {recipe_row.name}\n",
            f"菜谱难度: {recipe_row.difficulty}\n",
            f"酒精程度: {alcohol}\n",
            "制作数量: 3 （最多 4）\n",
            f"预计耗时: {total} 分钟",
            f"当前调味: {plan.seasoning_name}\n",
        ):
            self.assertIn(line, text)
        dish = min(
            c for c, r in game_config.config_recipes.items() if r.type == 0
        )
        self.assertNotIn(
            "酒精程度",
            service.confirm_text(service.confirm_plan(dish, 0, 0, 0), 1)[0],
        )

    def test_cook_behavior_for_coffee_and_food(self) -> None:
        """验证加料咖啡与普通做饭分别返回对应的行为标识与角色状态。"""
        self.assertEqual(
            service.cook_behavior(True),
            (
                constant.Behavior.MAKE_COFFEE_ADD,
                constant.CharacterStatus.STATUS_MAKE_COFFEE_ADD,
            ),
        )
        self.assertEqual(
            service.cook_behavior(False),
            (
                constant.Behavior.MAKE_FOOD,
                constant.CharacterStatus.STATUS_MAKE_FOOD,
            ),
        )


class UiFreeRunTest(FastTestCase):
    """验证无界面无结算子进程运行边界的测试集。"""

    def test_service_runs_without_ui_or_settle(self) -> None:
        """在三种终端编码的受限子进程中运行服务，确认无受限模块加载或导入尝试。"""
        for encoding in ENCODINGS:
            with self.subTest(encoding):
                with mock.patch.dict(
                    os.environ, {"PYTHONIOENCODING": encoding}
                ):
                    run = run_ui_free(UI_FREE_RUN, boot=True)
                self.assertEqual((run.loaded, run.attempted), ([], []))
                rows = run.payload["rows"]
                assert isinstance(rows, list)
                self.assertEqual(
                    rows[:2],
                    [
                        [
                            "筛选：类型:正餐,6 难度:中等(4-6) 时间:耗时(61+分)",
                            "排序：时间降序",
                        ],
                        ["筛选：无", "排序：无"],
                    ],
                )
                self.assertEqual(rows[2] % 50, 0)
                self.assertEqual(rows[3:7], [False, True, [True, 3], [3, 3, 1]])
                self.assertEqual(rows[7], True)
                self.assertEqual(rows[9], ["make_coffee_add", 132])
                self.assertEqual(rows[10], [0, 1])
                self.assertEqual(
                    rows[11], [[75, "（+25.0%）"], [48, "（-20.0%）"]]
                )
                self.assertEqual(rows[12], 1)
