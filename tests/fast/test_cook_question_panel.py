"""
精细模式烹饪答题面板交互测试
============================
本测试验证 Script.UI.Panel.cook_question_panel.run_cook_question_flow 的答题交互流程。
测试替换菜谱与题库配置，并拦截 draw.LeftButton.draw 与 flow_handle.askfor_all 来驱动作答。
用例覆盖正误作答的品质变化与提示文本、空选项过滤、品质上下界、特殊调味换池及无题阶段跳过。
"""

from unittest import mock

from Script.Config import config_def, game_config
from Script.Core import flow_handle, text_handle
from Script.Design import attr_calculation
from Script.System.Cooking_System import cooking
from Script.UI.Moudle import draw
from Script.UI.Panel import cook_question_panel
from tests.fast.base import FastTestCase

FOOD = 1
""" 测试使用的假菜谱编号。 """
POOLS = (*cooking.COOK_QUESTION_STAGES, "调味_精液", "装盘_精液", "调味_药物")
""" 测试题库使用的题池键名，含 cooking.COOK_QUESTION_STAGES 与三个特殊调味替换题池。 """


def question(pool: str, wrong_2: str = "错2") -> dict[str, str]:
    """
    构造指定题池的单条测试题目字典，以 pool 为前缀生成题干与非空选项文本。
    当 wrong_2 为空字符串时，wrong_answer_2 设为空字符串。
    Keyword arguments:
    pool -- str，题池名称，用作题干与各非空选项的前缀
    wrong_2 -- str，二号错误答案后缀，默认 "错2"，为空字符串时 wrong_answer_2 置空
    Return arguments:
    dict[str, str] -- 含 question、correct_answer 与 wrong_answer_1 至 wrong_answer_3 的题目字典
    """
    return {
        "question": f"{pool}题",
        "correct_answer": f"{pool}对",
        "wrong_answer_1": f"{pool}错1",
        "wrong_answer_2": f"{pool}{wrong_2}" if wrong_2 else "",
        "wrong_answer_3": f"{pool}最错",
    }


def quality_name(value: int) -> str:
    """返回 attr_calculation.get_food_quality(value) 给出的品质名称。"""
    return attr_calculation.get_food_quality(value)[1]


class CookQuestionPanelTest(FastTestCase):
    """精细模式烹饪答题面板交互与品质计算流程测试。"""

    def setUp(self) -> None:
        """
        调用父类 setUp，构造测试菜谱「测试菜」并初始化题库与作答记录属性。
        替换菜谱与题库配置，并以 _bind 和 _answer 分别拦截 LeftButton.draw 与 askfor_all。
        """
        super().setUp()
        recipe = config_def.Recipes()
        recipe.cid = FOOD
        recipe.name = "测试菜"
        self.library: dict[str, list[dict[str, str]]] = {
            pool: [question(pool)] for pool in POOLS
        }
        """ 测试菜谱的假题库映射，按题池名映射到题目列表，默认每池含一道测试题。 """
        self.choices: list[str] = []
        """ 按消费顺序排列的预设选项文本列表，每道题对应一项。 """
        self.drawn: list[draw.LeftButton] = []
        """ 当前题目已绘制、尚未被 _answer 消费的选项按钮列表。 """
        self.pages: list[list[str]] = []
        """ 按题目页记录的选项文本列表，每页按按钮绘制顺序保存去掉 id_index 前缀后的文本。 """
        self.enterContext(
            mock.patch.object(game_config, "config_recipes", {FOOD: recipe})
        )
        self.enterContext(
            mock.patch.object(
                game_config, "config_cook_question", {FOOD: self.library}
            )
        )
        self.enterContext(
            mock.patch.object(
                draw.LeftButton, "draw", autospec=True, side_effect=self._bind
            )
        )
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self._answer)
        )

    def _bind(self, button: draw.LeftButton) -> None:
        """
        按 button.return_text 经 flow_handle.bind_cmd 注册按钮回调，再将按钮追加到 self.drawn。
        Keyword arguments:
        button -- draw.LeftButton，调用 draw 方法的选项按钮对象
        Return arguments:
        None -- 无返回值
        """
        flow_handle.bind_cmd(button.return_text, button.cmd_func, button.args)
        self.drawn.append(button)

    def _answer(self, return_list: list[str], *args: object) -> str:
        """
        断言 self.choices 非空并取出队首预设选项，取出并清空 self.drawn，断言按钮返回值与 return_list 一致。
        将本页去掉 id_index 前缀的选项文本记入 self.pages，并定位文本为序号前缀加预设选项的唯一按钮。
        从 flow_handle.cmd_map 取该按钮命令（未绑定时取 null_func），清空 cmd_map 后执行并返回其 return_text。
        Keyword arguments:
        return_list -- list[str]，面板本次给出的选项按钮返回值列表
        args -- tuple[object, ...]，其余位置参数，本方法不使用
        Return arguments:
        str -- 命中选项按钮的 return_text
        """
        self.assertTrue(self.choices, f"缺少针对 {return_list} 的预设选项")
        choice = self.choices.pop(0)
        buttons, self.drawn = self.drawn, []
        self.assertEqual([b.return_text for b in buttons], return_list)
        self.pages.append(
            [
                b.text.removeprefix(text_handle.id_index(i))
                for i, b in enumerate(buttons)
            ]
        )
        (button,) = [
            b
            for i, b in enumerate(buttons)
            if b.text == text_handle.id_index(i) + choice
        ]
        command = flow_handle.cmd_map.get(
            button.return_text, flow_handle.null_func
        )
        flow_handle.cmd_map.clear()
        command()
        return button.return_text

    def run_flow(
        self, base: int, choices: list[str], seasoning: int = 0
    ) -> int:
        """
        以 FOOD 和给定参数运行 cook_question_panel.run_cook_question_flow。
        运行前写入 self.choices，运行后断言 self.choices 耗尽并返回最终品质值。
        Keyword arguments:
        base -- int，答题开始前的基础食物品质值
        choices -- list[str]，按作答顺序排列的预设选项文本列表
        seasoning -- int，传给答题流程的调味编号，默认 0
        Return arguments:
        int -- 答题流程结束后返回的最终品质值
        """
        self.choices = list(choices)
        quality = cook_question_panel.run_cook_question_flow(
            FOOD, base, seasoning
        )
        self.assertEqual(self.choices, [])
        return quality

    def test_answers_change_quality(self) -> None:
        """
        置空调味题 wrong_answer_2 并从品质 3 依次选备料对、烹饪最错、调味错1与装盘对，断言最终品质为 4。
        断言四页选项集合已过滤空选项，且 self.world.wait_texts 中的四条结果提示与预期一致。
        """
        self.assertNotEqual(quality_name(3), quality_name(4))
        self.library["调味"] = [question("调味", wrong_2="")]
        quality = self.run_flow(3, ["备料对", "烹饪最错", "调味错1", "装盘对"])
        self.assertEqual(quality, 4)
        self.assertEqual(
            [sorted(page) for page in self.pages],
            [
                (
                    sorted(
                        f"{stage}{tail}"
                        for tail in ("对", "错1", "错2", "最错")
                    )
                    if stage != "调味"
                    else sorted(["调味对", "调味错1", "调味最错"])
                )
                for stage in cooking.COOK_QUESTION_STAGES
            ],
        )
        self.assertEqual(
            self.world.wait_texts,
            [
                f"处理方式完全正确！食物品质+1，当前品质：{quality_name(4)}\n",
                f"处理方式完全错误，正确方式是「烹饪对」。品质降低，当前品质：{quality_name(3)}\n",
                f"处理方式不够好，正确方式是「调味对」。品质不变，当前品质：{quality_name(3)}\n",
                f"处理方式完全正确！食物品质+1，当前品质：{quality_name(4)}\n",
            ],
        )

    def test_quality_stays_in_bounds(self) -> None:
        """验证从最大品质减 1 四题答对后停在上限，从品质 1 四题选最错后停在 0。"""
        top = cooking.get_max_food_quality()
        right = [f"{stage}对" for stage in cooking.COOK_QUESTION_STAGES]
        worst = [f"{stage}最错" for stage in cooking.COOK_QUESTION_STAGES]
        self.assertEqual(self.run_flow(top - 1, right), top)
        self.assertEqual(self.run_flow(1, worst), 0)

    def test_special_seasoning_swaps_pool(self) -> None:
        """
        以子测试传入调味编号 11、12 与 101，验证对应阶段分别使用调味_精液、装盘_精液与调味_药物题池。
        每个子测试从品质 0 按常规与替换题池的正确答案作答，并断言最终品质为 4。
        """
        cases = {
            11: ["备料对", "烹饪对", "调味_精液对", "装盘对"],
            12: ["备料对", "烹饪对", "调味对", "装盘_精液对"],
            101: ["备料对", "烹饪对", "调味_药物对", "装盘对"],
        }
        for seasoning, choices in cases.items():
            with self.subTest(seasoning=seasoning):
                self.assertEqual(self.run_flow(0, choices, seasoning), 4)

    def test_stage_without_questions_is_skipped(self) -> None:
        """删去烹饪题池并置空装盘题池后从品质 0 答完其余两阶段，断言最终品质为 2 且记录 2 页题目。"""
        del self.library["烹饪"]
        self.library["装盘"] = []
        self.assertEqual(self.run_flow(0, ["备料对", "调味对"]), 2)
        self.assertEqual(len(self.pages), 2)
