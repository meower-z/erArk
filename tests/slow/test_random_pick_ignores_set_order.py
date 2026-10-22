# -*- coding: UTF-8 -*-
"""
随机结果不随集合遍历顺序变化的回归测试
======================================
字符串的哈希按进程随机化（PYTHONHASHSEED），字符串集合的遍历顺序因此每个进程不同。
同一个随机状态、同一个游戏状态，不论集合按什么顺序遍历，都必须得出同一个结果。

每组断言把同一个调用跑两遍，两遍之间只差集合的遍历顺序：一遍按加入顺序，一遍按加入顺序倒过来。
被测代码自己新建的集合，用 mock 把它所在模块的 set 换掉；配置里的集合，用 mock 把那一项换掉；作为参数的集合，直接传入两种。

随机挑选：对 12 个种子逐个设好 random 再调用，每个种子两遍挑中的必须相同；12 个种子挑中的还要不止一种，证明候选确实有多个。
- NPC AI：handle_npc_ai.search_target 把同权重的目标id放进集合，再从中挑一个。开新游戏后对凯尔希检索全部目标。
- 口上：talk.choice_talk_from_talk_data 从同权重的口上id集合里挑一句。
- 调教助手：confinement_and_training.get_behavior_id_of_sex_assistant 把可用行为id经集合去重，再挑一个。
  开新游戏后博士在会议室锁门时被杜宾逆推（与 test_talk_common_nested 的开场相同），调教助手设为与博士同部位，监狱长为凯尔希，博士在爱抚胸部。

前提的判断顺序：前提集合里有「场景内有可交互对象」（判断时抽一次随机数）与「在音乐室」（此刻不成立），
遇到不成立的前提就停，所以先判断哪个决定了抽不抽随机数。两遍都从种子 0 开始，结束时的结果与随机状态必须相同。
先确认「场景内有可交互对象」此刻确实抽随机数：判断的角色身边放了另一名干员。
- 目标的前提：配置里同时要求这两个前提的目标，把它的前提集合换成只含这两个前提，search_target 检索这一个目标（凯尔希）。
- 口上与事件的前提：handle_premise.get_weight_from_premise_dict（凯尔希）。
- 指令的前提：see_instruct_panel.judge_single_instruct_filter，以及 Web 模式的两个 _check_single_instruct_premise（博士）。
"""
import random
from unittest import mock

from tests.slow.base import SlowTestCase

SEEDS = range(12)
""" 随机挑选的比较用的种子 """
ROOM = ["中枢", "会议室"]


class InsertionOrderSet(set):
    """按加入顺序遍历的集合（只支持 add、in 与遍历，被测代码只用到这些）"""

    def __init__(self, iterable=()):
        """
        建空集合，再按顺序加入 iterable 的元素
        Keyword arguments:
        iterable -- 初始元素
        Return arguments:
        无
        """
        super().__init__()
        self.order = []
        """ 元素第一次加入的顺序 """
        for item in iterable:
            self.add(item)

    def add(self, item):
        """
        加入元素，并记下第一次加入的顺序
        Keyword arguments:
        item -- 元素
        Return arguments:
        无
        """
        if item not in self:
            self.order.append(item)
        super().add(item)

    def __iter__(self):
        """
        按加入顺序遍历
        Keyword arguments:
        无
        Return arguments:
        iterator -- 元素的迭代器
        """
        return iter(self.order)


class ReversedOrderSet(InsertionOrderSet):
    """按加入顺序倒过来遍历的集合"""

    def __iter__(self):
        """
        按加入顺序倒过来遍历
        Keyword arguments:
        无
        Return arguments:
        iterator -- 元素的迭代器
        """
        return reversed(self.order)


class RandomPickIgnoresSetOrderTest(SlowTestCase):
    """同一个随机状态在两种集合遍历顺序下得出同一个结果"""

    def assert_same_picks(self, pick):
        """
        对每个种子设好 random 后，两种遍历顺序下各调用一次 pick：每个种子挑中的都相同，且挑中的不止一种
        Keyword arguments:
        pick -- 函数，参数为集合类型，返回挑中的结果
        Return arguments:
        无
        """
        result = {}
        for set_type in (InsertionOrderSet, ReversedOrderSet):
            result[set_type] = []
            for seed in SEEDS:
                random.seed(seed)
                result[set_type].append(pick(set_type))
        forward = result[InsertionOrderSet]
        self.assertGreater(len(set(forward)), 1, f"每个种子都挑中同一个，比较不出顺序的影响：{forward}")
        self.assertEqual(forward, result[ReversedOrderSet])

    def draws(self, judge) -> tuple:
        """
        两种遍历顺序下各从种子 0 调用一次 judge
        Keyword arguments:
        judge -- 函数，参数为集合类型，返回判断结果
        Return arguments:
        tuple -- 按加入顺序、倒序两遍各自的（判断结果，之后的随机状态）
        """
        result = []
        for set_type in (InsertionOrderSet, ReversedOrderSet):
            random.seed(0)
            result.append((judge(set_type), random.getstate()))
        return tuple(result)

    def assert_same_draws(self, judge, name: str):
        """
        两种遍历顺序下各从种子 0 调用一次 judge：结果与之后的随机状态都相同
        Keyword arguments:
        judge -- 函数，参数为集合类型，返回判断结果
        name -- 被测函数的名字，写进断言信息
        Return arguments:
        无
        """
        forward, backward = self.draws(judge)
        self.assertEqual(forward[0], backward[0], f"{name}：两种判断顺序的结果不同")
        self.assertTrue(forward[1] == backward[1], f"{name}：两种判断顺序抽的随机数不同")

    def premise_set(self, set_type, character_id: int):
        """
        「场景内有可交互对象」与「在音乐室」两个前提，放进 set_type；先确认前者此刻抽随机数、后者不成立
        Keyword arguments:
        set_type -- 集合类型
        character_id -- 判断前提的角色id
        Return arguments:
        set -- 两个前提
        """
        from Script.Core import constant_promise
        from Script.Design import handle_premise

        draw = constant_promise.Premise.SCENE_SOMEONE_CAN_BE_INTERACT
        fail = constant_promise.Premise.IN_MUSIC_ROOM
        before = random.getstate()
        self.assertTrue(handle_premise.handle_premise(draw, character_id), "身边有可交互的干员")
        self.assertNotEqual(random.getstate(), before, "判断「场景内有可交互对象」抽了随机数")
        self.assertFalse(handle_premise.handle_premise(fail, character_id), "不在音乐室")
        random.setstate(before)
        return set_type([draw, fail])

    def beside(self, character_id: int) -> None:
        """
        把阿米娅放到角色身边，让「场景内有可交互对象」成立
        Keyword arguments:
        character_id -- 角色id
        Return arguments:
        无
        """
        self.world.move(self.npc("阿米娅"), self.cache.character_data[character_id].position)

    def test_npc_target(self):
        """凯尔希检索全部目标时，同一随机状态挑中同一个目标"""
        from Script.Config import game_config
        from Script.Design import handle_npc_ai

        operator_id = self.npc("凯尔希")
        all_targets = list(game_config.config_target.keys())

        def pick(set_type):
            """
            search_target 里新建的集合换成 set_type，检索全部目标
            Keyword arguments:
            set_type -- 集合类型
            Return arguments:
            str -- 挑中的目标id
            """
            with mock.patch.object(handle_npc_ai, "set", set_type, create=True):
                target, weight, judge, premise_data = handle_npc_ai.search_target(operator_id, all_targets, set(), {}, {})
            return target

        self.assert_same_picks(pick)

    def test_talk(self):
        """同权重的五句口上，同一随机状态挑中同一句"""
        from Script.Config import game_config
        from Script.Design import talk

        talk_ids = [talk_id for talk_id in game_config.config_talk if game_config.config_talk[talk_id].adv_id == 0][:5]

        def pick(set_type):
            """
            同权重的口上id放进 set_type，挑一句
            Keyword arguments:
            set_type -- 集合类型
            Return arguments:
            str -- 挑中的口上id
            """
            talk_text, talk_id, common_behavior_id = talk.choice_talk_from_talk_data({1: set_type(talk_ids)})
            return talk_id

        self.assert_same_picks(pick)

    def test_sex_assistant(self):
        """博士爱抚杜宾胸部时，调教助手在同一随机状态挑中同一个行为"""
        from Script.Core import constant
        from Script.UI.Panel import confinement_and_training

        self.walk(ROOM)
        operator_id = self.npc("杜宾")
        operator = self.cache.character_data[operator_id]
        self.world.move(operator_id, ROOM)
        operator.sp_flag.npc_masturebate_for_player = True
        self.world.player.press("逆来顺受")
        self.instruct(constant.Instruct.DOOR_LOCK_INNER)
        self.assertTrue(operator.sp_flag.is_h)
        setting = self.cache.rhodes_island.confinement_training_setting
        # 12：调教助手与博士同部位；13：调教对象不限于囚犯
        setting[12] = 1
        setting[13] = 1
        self.cache.rhodes_island.current_warden_id = self.npc("凯尔希")
        self.cache.character_data[0].behavior.behavior_id = constant.Behavior.BREAST_CARESS

        def pick(set_type):
            """
            去重用的集合换成 set_type，挑一个行为
            Keyword arguments:
            set_type -- 集合类型
            Return arguments:
            str -- 挑中的行为id
            """
            with mock.patch.object(confinement_and_training, "set", set_type, create=True):
                return confinement_and_training.get_behavior_id_of_sex_assistant()

        self.assert_same_picks(pick)

    def test_target_premises(self):
        """凯尔希检索一个要求「场景内有可交互对象」与「在音乐室」的目标，两种前提顺序抽的随机数相同"""
        from Script.Config import game_config
        from Script.Core import constant_promise
        from Script.Design import handle_npc_ai

        operator_id = self.npc("凯尔希")
        self.beside(operator_id)
        need = {constant_promise.Premise.SCENE_SOMEONE_CAN_BE_INTERACT, constant_promise.Premise.IN_MUSIC_ROOM}
        target = next(target for target, premises in game_config.config_target_premise_data.items() if need <= premises)

        def judge(set_type):
            """
            目标的前提集合换成只含两个前提的 set_type，检索这一个目标
            Keyword arguments:
            set_type -- 集合类型
            Return arguments:
            tuple -- 目标id、权重、是否找到
            """
            with mock.patch.dict(game_config.config_target_premise_data, {target: self.premise_set(set_type, operator_id)}):
                return handle_npc_ai.search_target(operator_id, [target], set(), {}, {})[:3]

        self.assert_same_draws(judge, "search_target")

    def test_talk_premises(self):
        """口上与事件的前提权重：两种前提顺序抽的随机数相同"""
        from Script.Design import handle_premise

        operator_id = self.npc("凯尔希")
        self.beside(operator_id)

        def judge(set_type):
            """
            对两个前提的 set_type 计算前提权重
            Keyword arguments:
            set_type -- 集合类型
            Return arguments:
            int -- 权重
            """
            return handle_premise.get_weight_from_premise_dict(self.premise_set(set_type, operator_id), operator_id, {})[0]

        self.assert_same_draws(judge, "get_weight_from_premise_dict")

    def test_instruct_premises(self):
        """博士的指令过滤（Tk 与 Web 两种界面）：两种前提顺序抽的随机数相同"""
        from Script.Core import constant
        from Script.Design import web_interaction_manager
        from Script.System.Instruct_System import see_instruct_panel
        from Script.System.Web_Draw_System import tab_menu

        self.beside(0)
        instruct_id = constant.Instruct.WAIT
        checks = {
            "see_instruct_panel": lambda: see_instruct_panel.judge_single_instruct_filter(instruct_id, {}, constant.InstructType.SYSTEM, use_type_filter_flag=False)[0],
            "web_interaction_manager": lambda: web_interaction_manager._check_single_instruct_premise(instruct_id, {}),
            "tab_menu": lambda: tab_menu._check_single_instruct_premise(instruct_id, {}),
        }
        differ = []
        """ 两种判断顺序下结果或随机状态不同的函数 """
        for name, check in checks.items():

            def judge(set_type):
                """
                指令的前提集合换成两个前提的 set_type，判断指令能否显示
                Keyword arguments:
                set_type -- 集合类型
                Return arguments:
                bool -- 指令能否显示
                """
                with mock.patch.dict(constant.instruct_premise_data, {instruct_id: self.premise_set(set_type, 0)}):
                    return check()

            forward, backward = self.draws(judge)
            if forward != backward:
                differ.append(name)
        self.assertEqual(differ, [], "这些函数在两种判断顺序下的结果或抽的随机数不同")
