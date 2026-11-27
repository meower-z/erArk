# -*- coding: UTF-8 -*-
"""
烹饪数据函数与界面边界测试
==========================
- 菜谱映射（BuildMakefoodDataTest）：验证构建玩家可制作菜谱映射且不改写 view.makefood_data。
- 按类筛选（CookByFoodTypeTest）：验证六种类型名、未知类型名、跳过时间不小于 999 与读取传入映射。
- 筛选排序（FilteredSortedTest）：验证类型、难度、时间筛选与各排序维度及方向的组合结果。
- 面板状态（PanelViewStateTest）：验证做饭面板读写 view 状态并生成按页补齐 50 项的按钮列表。
- 导入边界（CookingImportBoundaryTest）：验证 cooking.py 源码不导入界面与输入输出模块。
- 无界面导入（CookingSystemUiFreeTest）：验证 Cooking_System 各模块在无界面子进程中成功导入且无受拦截导入。
"""

from pathlib import Path
from unittest import mock

from Script.Config import config_def, game_config
from Script.Core import constant, flow_handle, get_text
from Script.Modules.domains import inventory
from Script.System.Cooking_System import cooking
from Script.UI.Panel import make_food_panel
from Script.UI.Moudle import view
from tests import chara_abilities as ca, kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports
from tests.ui_free_subprocess import ChildRun, run_ui_free

_ = get_text._
"""get_text 提供的翻译函数。"""
WIDTH = 100
"""测试用的做饭面板绘制宽度（100）。"""
RECIPES = (
    (1, 0, 3, 30),
    (2, 0, 4, 31),
    (3, 1, 6, 60),
    (4, 1, 7, 61),
    (5, 2, 0, 0),
    (6, 3, 9, 120),
    (7, 8, 2, 15),
    (8, 9, 5, 45),
    (9, 0, 1, 999),
    (10, 3, 5, 1000),
    (11, 0, 3, 45),
    (12, 2, 6, 10),
)
"""测试菜谱表基础条目，每项依次为（菜谱编号, 类型, 难度, 制作时间）。"""
UNCOOKABLE = ((13, 4, 1, 10), (14, 5, 1, 10), (15, 0, 10, 10), (16, 1, 100, 5))
"""不可制作或超出技能上限的测试菜谱条目，字段顺序与 RECIPES 相同。"""
DATA = {str(cid): cid for cid, *_rest in RECIPES}
"""由 RECIPES 构造的菜谱编号文本到菜谱编号映射。"""
ANY_TYPE = "任意"
"""不在六种固定食物类型名中的测试类型名。"""
COOKING = "Script/System/Cooking_System/cooking.py"
"""待检查导入边界的 cooking.py 仓库相对路径。"""
PACKAGE = "Script.System.Cooking_System"
"""待测烹饪系统包的点分导入路径。"""
MODULES = tuple(
    sorted(path.stem for path in Path(ROOT, *PACKAGE.split(".")).glob("*.py"))
)
"""直接位于 PACKAGE 对应目录的已排序 .py 模块名元组，包含 __init__。"""
LOAD_ALL = """
import importlib
for name in MODULES:
    module = PACKAGE if name == "__init__" else PACKAGE + "." + name
    try:
        importlib.import_module(module)
    except ImportError as error:
        payload[name] = repr(error)
    else:
        payload[name] = None
"""
"""
供子进程执行的代码片段，依次导入 MODULES 各模块（遇到 __init__ 时直接导入 PACKAGE）。
模块导入成功时在 payload[name] 记 None，触发 ImportError 时记 repr(error)。
"""


def recipe_table(
    rows: tuple[tuple[int, int, int, int], ...],
) -> dict[int, config_def.Recipes]:
    """将测试菜谱元组序列构造为编号到 Recipes 配置对象的字典。"""
    table = {}
    for cid, kind, difficulty, time in rows:
        recipe = config_def.Recipes()
        recipe.cid = cid
        recipe.name = f"菜{cid}"
        recipe.type = kind
        recipe.difficulty = difficulty
        recipe.time = time
        table[cid] = recipe
    return table


def ids(food_list: list[tuple[str, str]]) -> list[int]:
    """从 (菜谱编号文本, 菜谱名) 列表中提取整数菜谱编号列表。"""
    return [int(food_id) for food_id, _name in food_list]


class RecipeCase(FastTestCase):
    """烹饪测试基类，初始化玩家角色并替换为测试菜谱表。"""

    def setUp(self) -> None:
        """创建玩家角色并将 game_config.config_recipes 替换为测试菜谱表。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(
            mock.patch.object(
                game_config,
                "config_recipes",
                recipe_table(RECIPES + UNCOOKABLE),
            )
        )


class BuildMakefoodDataTest(RecipeCase):
    """验证 build_makefood_data 构造玩家可制作菜谱映射的行为。"""

    def test_cookable_recipes_by_id_text(self) -> None:
        """验证料理技能为 5 时 build_makefood_data 返回对应可制作菜谱映射且不改写 view.makefood_data。"""
        ca.ability(0)[43] = 5
        with mock.patch.object(view, "makefood_data", {"0": 0}):
            data = cooking.build_makefood_data()
            self.assertEqual(view.makefood_data, {"0": 0})
        self.assertEqual(
            data,
            {
                str(cid): cid
                for cid, kind, difficulty, _time in RECIPES
                if difficulty <= 5 and kind != 9
            },
        )


class CookByFoodTypeTest(RecipeCase):
    """验证 get_cook_from_makefood_data_by_food_type 的类型筛选与输入映射读取。"""

    def test_food_types(self) -> None:
        """验证六种食物类型名与任意类型名按顺序返回匹配菜谱并跳过时间大于等于 999 的条目。"""
        expected = {
            _("主食"): [1, 2, 11],
            _("零食"): [3, 4],
            _("饮品"): [5, 12],
            _("酒类"): [6],
            _("咖啡"): [7],
            _("其他"): [8],
            ANY_TYPE: [1, 2, 3, 4, 5, 6, 7, 8, 11, 12],
        }
        for food_type, cids in expected.items():
            with self.subTest(food_type=food_type):
                got = cooking.get_cook_from_makefood_data_by_food_type(
                    DATA, food_type
                )
                self.assertEqual(
                    list(got.items()), [(str(cid), f"菜{cid}") for cid in cids]
                )

    def test_reads_given_data(self) -> None:
        """验证函数按传入映射顺序筛选菜谱，不受 view.makefood_data 内容影响。"""
        with mock.patch.object(view, "makefood_data", DATA):
            got = cooking.get_cook_from_makefood_data_by_food_type(
                {"11": 11, "2": 2, "9": 9}, _("主食")
            )
        self.assertEqual(list(got), ["11", "2"])


class FilteredSortedTest(RecipeCase):
    """验证 get_filtered_sorted_cook_data 的筛选、排序与组合行为。"""

    def listed(
        self,
        filter_type: list[int],
        filter_difficulty: int,
        filter_time: int,
        sort_type: int = 0,
        sort_order: int = 0,
    ) -> list[int]:
        """以 DATA 与任意类型调用 get_filtered_sorted_cook_data 并返回菜谱编号列表。"""
        return ids(
            cooking.get_filtered_sorted_cook_data(
                DATA,
                ANY_TYPE,
                filter_type=filter_type,
                filter_difficulty=filter_difficulty,
                filter_time=filter_time,
                sort_type=sort_type,
                sort_order=sort_order,
            )
        )

    def test_filters(self) -> None:
        """验证无筛选、类型、难度三档、时间三档以及三者组合的筛选结果。"""
        cases = {
            "none": ([], -1, -1, [1, 2, 3, 4, 5, 6, 7, 8, 11, 12]),
            "type": ([0, 3], -1, -1, [1, 2, 6, 11]),
            "easy": ([], 0, -1, [1, 5, 7, 11]),
            "medium": ([], 1, -1, [2, 3, 8, 12]),
            "hard": ([], 2, -1, [4, 6]),
            "quick": ([], -1, 0, [1, 5, 7, 12]),
            "middle": ([], -1, 1, [2, 3, 8, 11]),
            "long": ([], -1, 2, [4, 6]),
            "all three": ([0], 0, 1, [11]),
        }
        for name, (kinds, difficulty, time, cids) in cases.items():
            with self.subTest(name):
                self.assertEqual(self.listed(kinds, difficulty, time), cids)

    def test_sorts(self) -> None:
        """验证不排序及按难度、时间、类型升序与降序排列的结果顺序。"""
        cases = {
            "unsorted descending": (0, 1, [1, 2, 3, 4, 5, 6, 7, 8, 11, 12]),
            "difficulty": (1, 0, [5, 7, 1, 11, 2, 8, 3, 12, 4, 6]),
            "difficulty descending": (1, 1, [6, 4, 3, 12, 8, 2, 1, 11, 7, 5]),
            "time": (2, 0, [5, 12, 7, 1, 2, 8, 11, 3, 4, 6]),
            "time descending": (2, 1, [6, 4, 3, 8, 11, 2, 1, 7, 12, 5]),
            "type": (3, 0, [1, 2, 11, 3, 4, 5, 12, 6, 7, 8]),
            "type descending": (3, 1, [8, 7, 6, 5, 12, 3, 4, 1, 2, 11]),
        }
        for name, (sort_type, sort_order, cids) in cases.items():
            with self.subTest(name):
                self.assertEqual(
                    self.listed([], -1, -1, sort_type, sort_order),
                    cids,
                )

    def test_filter_then_sort(self) -> None:
        """验证在主食分类下先按难度筛选再按时间降序排列的返回列表。"""
        got = cooking.get_filtered_sorted_cook_data(
            DATA,
            _("主食"),
            filter_difficulty=0,
            sort_type=2,
            sort_order=1,
        )
        self.assertEqual(got, [("11", "菜11"), ("1", "菜1")])


class PanelViewStateTest(RecipeCase):
    """验证 Make_food_Panel 读写 view 状态并按筛选排序生成按钮列表。"""

    def setUp(self) -> None:
        """设置料理技能为 9、清空药物调味库存并初始化 view 中的做饭面板状态。"""
        super().setUp()
        ca.ability(0)[43] = 9
        for seasoning_cid in game_config.config_seasoning:
            if seasoning_cid > 100:
                kernel_data.put(inventory.set_item, 0, seasoning_cid, 0)
        for name, value in (
            ("makefood_data", {}),
            ("makefood_filter_type", [0, 1]),
            ("makefood_filter_difficulty", 0),
            ("makefood_filter_time", -1),
            ("makefood_sort_type", 2),
            ("makefood_sort_order", 1),
            ("now_panel_id", constant.Panel.MAKE_FOOD),
        ):
            self.enterContext(mock.patch.object(view, name, value))

    def expected(self, cids: list[int]) -> list[tuple[str, str, int, int, int]]:
        """按菜谱编号列表生成补齐至 50 项的面板按钮预期行列表。"""
        rows = [(str(cid), f"菜{cid}", 0, 0, 0) for cid in cids]
        return rows + [("-1", "", 0, 0, 0)] * (50 - len(rows))

    def test_draw_rebuilds_data_and_lists(self) -> None:
        """验证 draw 刷新 view.makefood_data 并按当前 view 条件生成主食页按钮列表。"""
        panel = make_food_panel.Make_food_Panel(WIDTH)
        with mock.patch.object(
            flow_handle, "askfor_all", return_value=_("返回")
        ):
            panel.draw()
        self.assertEqual(view.makefood_data, cooking.build_makefood_data())
        self.assertEqual(panel.handle_panel.text_list, self.expected([11, 1]))

    def test_change_panel_lists(self) -> None:
        """验证 change_panel 在 view 筛选与排序条件变化后重新生成零食页按钮列表。"""
        view.makefood_data = DATA
        panel = make_food_panel.Make_food_Panel(WIDTH)
        panel.change_panel(_("零食"))
        self.assertEqual(panel.handle_panel.text_list, self.expected([]))
        view.makefood_filter_type.clear()
        view.makefood_filter_difficulty = -1
        view.makefood_sort_type = 1
        panel.change_panel(_("零食"))
        self.assertEqual(panel.handle_panel.text_list, self.expected([4, 3]))
        view.makefood_filter_time = 2
        panel.change_panel(_("零食"))
        self.assertEqual(panel.handle_panel.text_list, self.expected([4]))
        view.makefood_filter_type.append(0)
        panel.change_panel(_("零食"))
        self.assertEqual(panel.handle_panel.text_list, self.expected([]))


class CookingImportBoundaryTest(FastTestCase):
    """验证 cooking.py 不导入界面与输入输出模块的语法树边界测试。"""

    def test_cooking_imports_no_ui(self) -> None:
        """验证 cooking.py 通过后端界面边界守卫 banned_imports 检查且不存在违规导入。"""
        self.assertEqual(
            banned_imports((ROOT / COOKING).read_bytes(), COOKING), []
        )


class CookingSystemUiFreeTest(FastTestCase):
    """Script/System/Cooking_System 模块的无界面子进程导入测试。"""

    child: ChildRun
    """setUpClass 运行无界面子进程后保存的 ChildRun 结果。"""

    @classmethod
    def setUpClass(cls) -> None:
        """以 boot=True 调用 run_ui_free 运行 LOAD_ALL 导入 MODULES 各模块，并将结果存入 cls.child。"""
        cls.child = run_ui_free(
            f"PACKAGE = {PACKAGE!r}\nMODULES = {MODULES!r}\n{LOAD_ALL}",
            boot=True,
        )

    def test_modules_load_without_ui(self) -> None:
        """
        断言 MODULES 包含 __init__ 与 cooking。
        断言子进程成功导入各模块，未尝试导入也未加载受拦截模块。
        """
        self.assertTrue({"__init__", "cooking"} <= set(MODULES))
        self.assertEqual(self.child.payload, dict.fromkeys(MODULES))
        self.assertEqual(self.child.attempted, [])
        self.assertEqual(self.child.loaded, [])
