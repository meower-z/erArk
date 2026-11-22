# -*- coding: UTF-8 -*-
"""
面板的子菜单只读：送礼、五子棋、素质升级、做饭
==============================================
每个面板在玩家选行动时只读，子菜单也是；要写的值放进行动（fields 或 args），行动开始时才写进缓存。
- 在任意一层取消：这一轮没有 Chosen，指纹（缓存去掉界面状态，加上内核状态）、时钟与开始门的调用次数都不变。
- 定下行动：Chosen 抛出之前指纹不变；行动开始时（starts.behave 跑完）玩家的行为数据里写着选好的值，
  开始代码做好了要做的事。
"""

import copy
from collections.abc import Callable, Iterator, Mapping
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant, flow_handle, game_type
from Script.Design import game_time, update
from Script.Kernel import core
from Script.Modules.gameplay_resolution import start_gate, starts
from Script.Modules.tk_ui import player_pick
from Script.System.Cooking_System import cooking, make_food_panel
from Script.System.Instruct_System import handle_instruct
from Script.System.Pregnancy_System import egg_handle, pregnancy_handle
from Script.UI.Panel import gift_panel, play_gomoku_panel, talent_up_panel
from Script.Modules.domains import achievement, activity, inventory, pregnancy
from Script.Modules.domains import modes
from tests import chara_abilities as ca, kernel_data, pick_guard
from tests import world as world_module
from tests.chara_activity import aim
from tests.fast.base import FastTestCase
from Script.UI.Moudle import view

LOADED_FIRST = (update, handle_instruct)
""" 先于 Script.Modules 导入的 update；handle_instruct 登记指令处理函数 """
NPC = 1
""" 玩家的交互对象 """
WIDTH = 100
""" 面板宽度 """
DRUG = 103
""" 药物调味（媚药）的调味cid，也是道具id """


class UnplannedAnswer(BaseException):
    """面板等的回答测试没有安排：是 BaseException，面板循环里的 except Exception 拦不住，不会一直重画"""


class PanelSubMenusReadOnly(FastTestCase):
    """送礼、五子棋、素质升级、做饭的子菜单：取消什么都不写，定下的值在开始时写"""

    def setUp(self) -> None:
        """博士与一名干员在场景里，干员是交互对象。博士的道具 DRUG 为 0。内核停在玩家选行动"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        aim(self.player.cid, NPC)
        kernel_data.put(inventory.set_item, 0, DRUG, 0)
        view.now_panel_id = constant.Panel.IN_SCENE
        self.answers: list[str] = []
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self.answer)
        )
        self.started: list[activity.Behavior] = []
        behave = starts.behave

        def recording(
            act: core.Action, extra: starts.Extra | None = None
        ) -> core.Effects:
            effects = behave(act, extra)
            if act.who == "0":
                self.started.append(
                    copy.deepcopy(activity.behavior(self.player.cid))
                )
            return effects

        self.enterContext(mock.patch.object(starts, "behave", recording))
        world_module.act(lambda: None)

    def answer(self, return_list: list[str], *args: object) -> str:
        """
        按安排的顺序回答面板的选择
        Keyword arguments:
        return_list -- 面板画出的按钮的返回值
        Return arguments:
        str -- 安排的下一个回答，它必须在按钮里
        """
        if not self.answers or self.answers[0] not in return_list:
            raise UnplannedAnswer(
                f"安排的回答 {self.answers[:1]} 不在按钮 {return_list} 里"
            )
        return self.answers.pop(0)

    def play(
        self, answers: list[str], round_fn: Callable[[], None]
    ) -> pick_guard.Round:
        """
        玩家跑一轮选择：回答安排好的按钮，这一轮的选择跑完后游戏推进到玩家下一次选行动
        Keyword arguments:
        answers -- 依次按下的按钮的返回值
        round_fn -- 一轮选择
        Return arguments:
        Round -- 这一轮的记录
        """
        self.answers = list(answers)
        guard = pick_guard.watch()
        world_module.act(guard(round_fn))
        self.assertEqual(self.answers, [], "安排的回答都用掉了")
        self.assertEqual(len(guard.rounds), 1)
        return guard.rounds[0]

    def assert_backs_out(
        self, answers: list[str], round_fn: Callable[[], None]
    ) -> None:
        """
        这一轮取消：没有 Chosen，指纹、时钟与开始门的调用次数不变，回到场景面板
        Keyword arguments:
        answers -- 依次按下的按钮的返回值
        round_fn -- 一轮选择
        """
        before = pick_guard.fingerprint()
        gate_calls = start_gate.calls
        got = self.play(answers, round_fn)
        self.assertEqual((got.chosen, got.changed), (False, False))
        self.assertTrue(
            pick_guard.fingerprint() == before, "缓存与内核状态不变"
        )
        self.assertEqual(start_gate.calls, gate_calls)
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)

    def assert_commits(
        self, answers: list[str], round_fn: Callable[[], None]
    ) -> activity.Behavior:
        """
        这一轮定下行动，Chosen 之前什么都没写；行动开始过，时钟走了
        Keyword arguments:
        answers -- 依次按下的按钮的返回值
        round_fn -- 一轮选择
        Return arguments:
        Behavior -- 玩家的行动开始时（开始代码跑完）的行为数据
        """
        clock = core.state().clock
        self.started.clear()
        got = self.play(answers, round_fn)
        self.assertEqual((got.chosen, got.changed), (True, False))
        self.assertGreater(core.state().clock, clock)
        return self.started[0]

    def chosen(self, answers: list[str], pick: Callable[[], object]) -> dict:
        """
        跑一次选择直到 Chosen，不开始行动
        Keyword arguments:
        answers -- 依次按下的按钮的返回值
        pick -- 选择
        Return arguments:
        dict -- 定下的行动的意图
        """
        self.answers = list(answers)
        before = pick_guard.fingerprint()
        with self.assertRaises(player_pick.Chosen) as raised:
            pick()
        self.assertTrue(
            pick_guard.fingerprint() == before, "Chosen 之前什么都没写"
        )
        self.assertEqual(self.answers, [])
        data = raised.exception.action.action_data
        assert isinstance(data, Mapping)
        return dict(data)

    def test_gift(self) -> None:
        """送礼：选卵、选婴儿在任一层返回都回到礼物列表；选好的礼物、卵、婴儿在开始时写进玩家的行为"""
        panel = gift_panel.Gift_Panel(WIDTH)
        self.enterContext(
            mock.patch.object(
                gift_panel.Gift_Panel, "check_gift_available", return_value=True
            )
        )
        now = game_time.now()
        eggs = {
            3: {"lay_time": now, "acceleration_days": 0},
            5: {"lay_time": now, "acceleration_days": 0},
        }
        self.enterContext(
            mock.patch.object(
                egg_handle, "get_accelerable_hatching_eggs", return_value=eggs
            )
        )
        self.enterContext(
            mock.patch.object(egg_handle, "get_hatch_day", return_value=1)
        )
        for cid in (2, 3):
            self.world.chara(cid, f"婴儿{cid}")
            kernel_data.put(pregnancy.update, cid, born_time=now)
        self.enterContext(
            mock.patch.object(
                pregnancy_handle,
                "is_growth_drug_self_target",
                return_value=False,
            )
        )
        self.enterContext(
            mock.patch.object(
                pregnancy_handle, "get_accelerable_babies", return_value=[2, 3]
            )
        )
        self.enterContext(
            mock.patch.object(
                pregnancy_handle, "get_child_grow_day", return_value=1
            )
        )
        world_module.act(lambda: None)
        with self.subTest("选卵时返回"):
            self.assert_backs_out(["返回选卵"], lambda: panel.select_gift(36))
        with self.subTest("选婴儿时返回"):
            self.assert_backs_out(["返回选婴儿"], lambda: panel.select_gift(39))
        with self.subTest("选好卵"):
            data = self.chosen(["5"], lambda: panel.select_gift(36))
            self.assertEqual(
                data["fields"],
                {"behavior.gift_id": 36, "behavior.gift_egg_id": 5},
            )
        with self.subTest("选好婴儿"):
            data = self.chosen(["3"], lambda: panel.select_gift(39))
            self.assertEqual(
                data["fields"],
                {"behavior.gift_id": 39, "behavior.gift_child_id": 3},
            )
        with self.subTest("送出道歉礼物，开始时"):
            kernel_data.put(
                inventory.set_item,
                self.player.cid,
                game_config.config_gift_items[2].item_id,
                1,
            )
            behavior = self.assert_commits([], lambda: panel.select_gift(2))
            self.assertEqual(
                (behavior.behavior_id, behavior.gift_id),
                (constant.Behavior.GIVE_GIFT, 2),
            )

    def test_gomoku(self) -> None:
        """五子棋：难度、先后手在返回时取消整个行动，结束游戏不定下行动；下完一局在开始时写游戏类型与难度"""
        gomoku = play_gomoku_panel.GomokuPanel
        with self.subTest("选难度时返回"):
            self.assert_backs_out(["返回"], lambda: gomoku(WIDTH).draw())
        with self.subTest("选先后手时返回"):
            self.assert_backs_out(
                ["低难度", "返回"], lambda: gomoku(WIDTH).draw()
            )
        with self.subTest("结束游戏"):
            self.assert_backs_out(
                ["低难度", "玩家先手", "结束游戏"], lambda: gomoku(WIDTH).draw()
            )
        with self.subTest("下完一局，开始时"):
            self.answers = ["中难度"]
            with mock.patch.object(modes, "debug", return_value=True):
                panel = gomoku(WIDTH)
            panel.DEPTH = 4
            behavior = self.assert_commits([], lambda: panel.end_settle(1))
            self.assertEqual(
                (
                    behavior.behavior_id,
                    behavior.board_game_type,
                    behavior.board_game_ai_difficulty,
                ),
                (constant.Behavior.PL_LOSE_IN_BOARD_GAME, 1, 2),
            )

    def test_talent_up(self) -> None:
        """素质升级：确定后才在 1 分钟等待开始时获得素质"""
        talent = ca.talent(NPC)
        talent_id = next(
            gain.talent_id
            for gain in game_config.config_talent_gain.values()
            if not talent[gain.talent_id]
            and gain.talent_id not in {201, 211, 203, 213}
        )
        panel = object.__new__(talent_up_panel.Character_talent_show_Text)
        panel.character_id = NPC
        behavior = self.assert_commits([], lambda: panel.level_up(talent_id))
        self.assertEqual(
            (behavior.behavior_id, behavior.duration),
            (constant.Behavior.WAIT, 1),
        )
        self.assertEqual(talent[talent_id], 1)

    def food_button(
        self, seasoning: int, cook_mode: int
    ) -> make_food_panel.SeeFoodListByFoodNameDraw:
        """
        做饭面板里一道有题库的家常菜的按钮
        Keyword arguments:
        seasoning -- 调味cid
        cook_mode -- 0 标准，1 精细
        Return arguments:
        SeeFoodListByFoodNameDraw -- 按钮对象
        """
        recipe_id = next(
            rid
            for rid, recipe in game_config.config_recipes.items()
            if cooking.has_cook_question_library(rid)
            and recipe.type not in {3, 8}
        )
        return make_food_panel.SeeFoodListByFoodNameDraw(
            (str(recipe_id), "", seasoning, cook_mode, 0), WIDTH, True, True, 0
        )

    def bag(self) -> Iterator[game_type.Food]:
        """玩家背包里的食物"""
        return iter(inventory.foods(self.player.cid).values())

    def test_cooking_backs_out(self) -> None:
        """做饭：筛选、调整数量后取消、材料不够时都不写游戏数据"""
        with self.subTest("筛选"):
            self.assert_backs_out(
                ["清除筛选", "返回"],
                lambda: make_food_panel.Make_food_Panel(
                    WIDTH
                ).open_filter_panel(),
            )
        with self.subTest("调整数量后取消"):
            self.assert_backs_out(
                ["增加", "最大", "减少", "取消"],
                lambda: self.food_button(0, 0).make_food_for_sure(),
            )
        with self.subTest("药物调味没有药"):
            self.assert_backs_out(
                ["确认"], lambda: self.food_button(DRUG, 0).make_food_for_sure()
            )

    def test_cooking_commits(self) -> None:
        """做饭：确认后开始时才做出食物、用掉药、计入成就；精细模式的品质是答题的结果"""
        with self.subTest("药物调味做两份"):
            kernel_data.put(inventory.set_item, self.player.cid, DRUG, 2)
            made_before = achievement.get("make_food_count")
            button = self.food_button(DRUG, 0)
            data = self.chosen(["增加", "确认"], button.make_food_for_sure)
            self.assertEqual(
                {k: data["args"][k] for k in ("count", "seasoning")},
                {"count": 2, "seasoning": DRUG},
            )
            behavior = self.assert_commits(
                ["增加", "确认"], button.make_food_for_sure
            )
            foods = list(self.bag())
            self.assertEqual(len(foods), 2)
            self.assertEqual(inventory.items(self.player.cid)[DRUG], 0)
            self.assertEqual(
                achievement.get("make_food_count"), made_before + 2
            )
            self.assertEqual(behavior.make_food_count, 2)
            self.assertEqual(behavior.target_food.uid, foods[-1].uid)
            self.assertEqual(
                [food.special_seasoning for food in foods], [DRUG, DRUG]
            )
        with self.subTest("精细模式答题"):
            kernel_data.put(inventory.replace_foods, self.player.cid, {})
            normal_config.system_setting.makefood_make_count = {}
            button = self.food_button(0, 1)
            questions = cooking.get_food_cook_questions(int(button.cid))
            asked = sum(
                1
                for stage in cooking.COOK_QUESTION_STAGES
                if questions.get(stage)
            )
            answers = ["确认"] + ["0"] * asked
            data = self.chosen(answers, button.make_food_for_sure)
            base = cooking.get_base_food_quality(0)
            self.assertLessEqual(abs(data["args"]["quality"] - base), asked)
            behavior = self.assert_commits(answers, button.make_food_for_sure)
            (food,) = self.bag()
            self.assertLessEqual(abs(food.quality - base), asked)
            self.assertEqual(behavior.target_food.uid, food.uid)
