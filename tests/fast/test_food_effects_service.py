"""
进食效果服务测试
================
覆盖品质钳制与手制加成、菜谱难度与烹饪时间系数、随机抽取顺序与种子复现、进食结算调用及无界面子进程运行。
"""

import datetime
import random
from unittest import mock

from Script.Config import config_def, game_config
from Script.Core import game_type
from Script.Modules.domains import activity, needs
from Script.Modules.gameplay_resolution import food_effects
from Script.Settle import default
from tests import kernel_data
from tests.chara_activity import aim, behave
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import BLOCKED, run_ui_free

RECIPE = 987654
""" 测试使用的合成菜谱编号（987654）。 """
UNKNOWN = 987655
""" 测试使用的未配置菜谱编号（987655）。 """
NOW = datetime.datetime(2026, 1, 1, 12, 0)
""" 进食结算测试使用的固定当前时间 datetime(2026, 1, 1, 12, 0)。 """
FOOD_RUN = """
import random
from Script.Config import config_def, game_config
from Script.Core import game_type
from Script.Kernel import core
from Script.Modules.domains import activity
from Script.Modules.gameplay_resolution import food_effects, working
recipe = config_def.Recipes()
recipe.difficulty, recipe.time = 2, 999
game_config.config_recipes[7] = recipe
food = game_type.Food()
food.quality, food.maker, food.recipe = 4, "maker", 7
random.uniform = lambda low, high: 1.0
with working.based_on(core.state()):
    activity.set_behavior(0, target_food=food)
    payload["effects"] = list(food_effects.calculate_food_effects(0, 60))
"""
"""在无界面子进程中配置测试菜谱与食物、运行 calculate_food_effects 并将结果写入 payload 的代码片段。"""


def recipe(difficulty: int, time: int) -> config_def.Recipes:
    """
    构造测试用的正餐菜谱配置对象（编号固定为 RECIPE，type 与 alcohol 均为 0）。
    Keyword arguments:
    difficulty -- int，菜谱难度
    time -- int，菜谱烹饪时间
    Return arguments:
    config_def.Recipes -- 构造完成的菜谱配置对象
    """
    data = config_def.Recipes()
    data.cid, data.name, data.type, data.alcohol = RECIPE, "测试菜", 0, 0
    data.difficulty, data.time = difficulty, time
    return data


def food(
    quality: int, maker: str = "", recipe_id: int = UNKNOWN
) -> game_type.Food:
    """
    构造测试用的食物对象。
    Keyword arguments:
    quality -- int，食物品质
    maker -- str，制作者名称，默认空字符串
    recipe_id -- int，菜谱编号，默认 UNKNOWN
    Return arguments:
    game_type.Food -- 构造完成的食物对象
    """
    made = game_type.Food()
    made.name, made.quality, made.maker = "测试菜", quality, maker
    made.recipe = recipe_id
    return made


class FoodEffectsCase(FastTestCase):
    """进食效果测试基类，初始化角色 0 并隔离菜谱配置字典。"""

    def setUp(self) -> None:
        """重置测试世界、创建角色 0（博士），并对 game_config.config_recipes 打补丁以在测试后还原。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(mock.patch.dict(game_config.config_recipes))

    def effects(
        self, eaten: game_type.Food | None = None, add_time: int = 60
    ) -> tuple[int, int]:
        """
        固定 random.uniform 返回 1.0，执行 calculate_food_effects 并断言其以 (0.8, 1.2) 恰好调用两次。
        Keyword arguments:
        eaten -- game_type.Food | None，待设置到角色 0 的目标食物，为 None 时保留现状
        add_time -- int，本次结算时间，默认 60
        Return arguments:
        tuple[int, int] -- calculate_food_effects 返回的 (state_add, hpmp_add)
        """
        if eaten is not None:
            behave(0, target_food=eaten)
        with mock.patch("random.uniform", return_value=1.0) as draw:
            result = food_effects.calculate_food_effects(0, add_time)
        self.assertEqual(draw.call_args_list, [mock.call(0.8, 1.2)] * 2)
        return result


class QualityTest(FoodEffectsCase):
    """目标食物默认值、品质钳制与手制加成的测试。"""

    def test_unset_food_uses_defaults(self) -> None:
        """未设置目标食物时按默认品质、难度与时间系数返回 (15, 25)。"""
        self.assertEqual(self.effects(), (15, 25))

    def test_missing_food_uses_defaults(self) -> None:
        """目标食物属性为 None 时按默认品质、难度与时间系数返回 (15, 25)。"""
        missing = mock.Mock(target_food=None)
        with mock.patch.object(activity, "behavior", return_value=missing):
            self.assertEqual(self.effects(), (15, 25))

    def test_quality_clamp(self) -> None:
        """品质 -3、0、1、2、7、8、9、10 分别对应状态值 15、15、15、60、735、960、15、15 且体力气力均为 25。"""
        cases = {-3: 15, 0: 15, 1: 15, 2: 60, 7: 735, 8: 960, 9: 15, 10: 15}
        for quality, state in cases.items():
            with self.subTest(quality=quality):
                self.assertEqual(self.effects(food(quality)), (state, 25))

    def test_handmade_bonus(self) -> None:
        """品质 2 的手制食物（maker 为「博士」）返回 (90, 25)，非手制返回 (60, 25)。"""
        self.assertEqual(self.effects(food(2, maker="博士")), (90, 25))
        self.assertEqual(self.effects(food(2, maker="")), (60, 25))


class RecipeTest(FoodEffectsCase):
    """菜谱难度、烹饪时间、未知菜谱与多系数连乘的测试。"""

    def test_difficulty(self) -> None:
        """烹饪时间 60 时，难度 -1、0、1 按下限 1 计均返回 (60, 25)，难度 3 返回 (180, 75)。"""
        cases = {-1: (60, 25), 0: (60, 25), 1: (60, 25), 3: (180, 75)}
        for difficulty, expected in cases.items():
            with self.subTest(difficulty=difficulty):
                game_config.config_recipes[RECIPE] = recipe(difficulty, 60)
                eaten = food(2, recipe_id=RECIPE)
                self.assertEqual(self.effects(eaten), expected)

    def test_cook_time(self) -> None:
        """
        烹饪时间 15、30、60、90、120（封顶 1.5）与 999（按 15 计）分别返回
        (15, 6)、(30, 12)、(60, 25)、(90, 37)、(90, 37) 与 (15, 6)。
        """
        cases = {15: (15, 6), 30: (30, 12), 60: (60, 25), 90: (90, 37)}
        cases.update({120: (90, 37), 999: (15, 6)})
        for time, expected in cases.items():
            with self.subTest(time=time):
                game_config.config_recipes[RECIPE] = recipe(1, time)
                eaten = food(2, recipe_id=RECIPE)
                self.assertEqual(self.effects(eaten), expected)

    def test_unknown_recipe(self) -> None:
        """菜谱编号不在配置中时难度与时间系数均取 1，返回 (60, 25)。"""
        self.assertEqual(self.effects(food(2, recipe_id=UNKNOWN)), (60, 25))

    def test_all_factors_multiply(self) -> None:
        """品质 4、手制、难度 2 且时间 999 的各系数相乘返回 (180, 12)。"""
        game_config.config_recipes[RECIPE] = recipe(2, 999)
        eaten = food(4, maker="博士", recipe_id=RECIPE)
        self.assertEqual(self.effects(eaten), (180, 12))


class RandomDrawTest(FoodEffectsCase):
    """随机浮动抽取顺序与固定种子可复现性的测试。"""

    def test_first_draw_state_second_hpmp(self) -> None:
        """random.uniform 依次返回 0.8 与 1.2 时返回 (48, 30)，验证首次抽取用于 state_add、第二次用于 hpmp_add。"""
        behave(0, target_food=food(2))
        with mock.patch("random.uniform", side_effect=[0.8, 1.2]):
            result = food_effects.calculate_food_effects(0, 60)
        self.assertEqual(result, (48, 30))

    def test_seeded_draws(self) -> None:
        """固定随机种子 7 时，计算结果与独立 Random(7) 前两次抽取一致，且后续 random.random() 推进同步。"""
        game_config.config_recipes[RECIPE] = recipe(3, 90)
        behave(0, target_food=food(5, maker="博士", recipe_id=RECIPE))
        reference = random.Random(7)
        first = reference.uniform(0.8, 1.2)
        second = reference.uniform(0.8, 1.2)
        random.seed(7)
        result = food_effects.calculate_food_effects(0, 40)
        expected = (
            int(40 * 6.25 * 1.5 * 3 * 1.5 * first),
            int(25 * 3 * 1.5 * second),
        )
        self.assertEqual(result, expected)
        self.assertEqual(random.random(), reference.random())


class EatSettleTest(FoodEffectsCase):
    """进食结算入口 handle_eat_add_just 调用 food_effects 的测试。"""

    def setUp(self) -> None:
        """配置角色 0 独自进食难度 2、时间 60、品质 4 的食物，并将体力置 0、气力置 100。"""
        super().setUp()
        aim(0, 0)
        game_config.config_recipes[RECIPE] = recipe(2, 60)
        behave(0, target_food=food(4, recipe_id=RECIPE))
        kernel_data.put(needs.set, 0, hit=0, mana=100)
        self.hit_max = needs.of(0)["hit_max"]

    def settle(self) -> game_type.TargetChange:
        """
        在内核写入上下文中以 add_time=10 执行角色 0 的进食结算。
        Keyword arguments:
        无
        Return arguments:
        game_type.TargetChange -- 角色 0 本次进食结算产生的状态变更记录
        """
        change = game_type.CharacterStatusChange()
        with kernel_data.writing():
            default.handle_eat_add_just(0, 10, change, NOW)
        return change.target_change[0]

    def points(self, hpmp: int) -> tuple[int, int]:
        """
        按角色 0 的最大体力与给定 hpmp 增量换算预期的体力与气力变更值。
        Keyword arguments:
        hpmp -- int，进食效果返回的体力气力增量
        Return arguments:
        tuple[int, int] -- 预期的 (hit_point, mana_point) 变更值
        """
        return (
            int(hpmp * (10 + self.hit_max * 0.005)),
            int(hpmp * (20 + self.hit_max * 0.01)),
        )

    def test_seeded_hp_and_mp(self) -> None:
        """固定随机种子 11 执行 handle_eat_add_just 时，角色 0 的体力与气力变更与公式计算结果一致。"""
        reference = random.Random(11)
        reference.uniform(0.8, 1.2)
        hpmp = int(25 * 2 * reference.uniform(0.8, 1.2))
        random.seed(11)
        change = self.settle()
        self.assertEqual(
            (change.hit_point, change.mana_point), self.points(hpmp)
        )

    def test_reads_service_result(self) -> None:
        """
        打桩 food_effects.calculate_food_effects 返回 (0, 2) 时，
        handle_eat_add_just 以 (0, 10) 调用一次并按增量 2 结算体力气力。
        """
        with mock.patch.object(
            food_effects, "calculate_food_effects", return_value=(0, 2)
        ) as calc:
            change = self.settle()
        calc.assert_called_once_with(0, 10)
        self.assertEqual((change.hit_point, change.mana_point), self.points(2))


class BoundaryTest(FastTestCase):
    """进食效果服务的无界面子进程运行测试。"""

    def test_runs_with_ui_blocked(self) -> None:
        """
        验证拦截默认受限模块时，子进程执行 FOOD_RUN 返回 payload 为 {"effects": [180, 12]}。
        同时验证子进程的 loaded 与 attempted 均为空列表。
        """
        run = run_ui_free(FOOD_RUN, blocked=BLOCKED)
        self.assertEqual(run.payload, {"effects": [180, 12]})
        self.assertEqual((run.loaded, run.attempted), ([], []))
