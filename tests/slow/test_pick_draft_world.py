# -*- coding: UTF-8 -*-
"""
世界里的面板选择只读：改动随行动或 0 分钟的 Edit 在开始时写入，掷骰与判定在开始时运行
==========================================================================================
- 衣柜：射在衣物上是具名编辑 locker_shoot，射精（掷骰与高潮结算）在 Edit 开始时运行；
  偷内裤随 Edit 写入；进了某人的衣柜什么也不做就退出：没有行动，玩家的交互对象不变。
- 食物背包：给交互对象吃特殊调味的食物，接受判定在行动开始时运行一次，被拒时开始的是拒绝食用；
  时停中被拒时，拒绝食用在内核里是 0 分钟，时钟不动。
- 冰箱带走母乳、使用理智药剂、一键全跟随：都是一个 0 分钟的 Edit，开始之后改动在缓存里。
- 地图：打开再返回，没有行动，缓存与随机数状态不变（场景提示的随机抽取不动游戏的随机数）。
- 亲自诊疗：有病人时打开面板，一项检查都不做就返回：没有行动，缓存不变。
- 背包里有旧版本食物（没有母乳量）的存档：读档后这份食物不在背包里，新版本的食物还在。
每个选择期间（定下行动之前）缓存与随机数状态的指纹不变，Edit 之后时钟不动。
"""

from collections.abc import Callable, Mapping
from typing import cast

from tests.slow.base import SlowTestCase
from tests import kernel_data

LOCKER_ROOM = ["大浴场", "更衣室"]
""" 大浴场的更衣室（浴场衣柜） """
PANTIES = 9
""" 服装类型：内裤 """
SPECIAL_SEASONING = 11
""" 特殊调味：精液_巧妙混合 """


class PickDraftWorldTest(SlowTestCase):
    """世界里的面板选择"""

    def setUp(self) -> None:
        """开新游戏，记下内核开始的每个行动，取一名本局的干员"""
        super().setUp()
        from Script.Kernel import core

        self.started: list[core.Action] = []
        saved = core._bodies["kernel.StartAction"]

        def spy(act: core.Action) -> core.Effects:
            self.started.append(act)
            return saved(act)

        core._bodies["kernel.StartAction"] = spy
        self.addCleanup(core._bodies.__setitem__, "kernel.StartAction", saved)
        self.chara_id: int = sorted(i for i in self.cache.npc_id_got if i)[0]

    def run_pick(self, fn: "Callable[[], None]") -> tuple[int, int, bool]:
        """
        玩家这一次选择跑 fn；记下选择期间缓存与随机数状态的指纹是否变了
        Return arguments:
        tuple -- (选择前的分钟, 推进到玩家下一次选行动时的分钟, 选择期间指纹变了)
        """
        from Script.Kernel import core
        from tests import pick_guard, world

        changed: list[bool] = []

        def pick() -> None:
            before = pick_guard.fingerprint()
            try:
                fn()
            finally:
                changed.append(pick_guard.fingerprint() != before)

        clock = core.state().clock
        self.started.clear()
        world.act(pick)
        return clock, core.state().clock, changed[0]

    def player_starts(self) -> list[tuple[str, int]]:
        """这次选择以来玩家开始的行动：(action_id, 分钟数)"""
        return [(a.action_id, a.duration) for a in self.started if a.who == "0"]

    def show(self, panel_id: int) -> "Callable[[], None]":
        """
        显示面板的一轮（与主循环的一轮相同），安排的按钮都要按完
        Keyword arguments:
        panel_id -- 面板id
        """
        from Script.UI.Moudle import view
        from Script.Core import constant

        def round_() -> None:
            view.now_panel_id = panel_id
            constant.panel_data[panel_id]()
            self.world.player.check_done()

        return round_

    def assert_one_edit(self, start: int, end: int, changed: bool) -> None:
        """这次选择定下一个 0 分钟的 Edit，时钟不动，选择期间缓存不变"""
        from Script.Modules.gameplay_resolution import edits

        self.assertEqual(self.player_starts(), [(edits.EDIT, 0)])
        self.assertEqual(end, start)
        self.assertFalse(changed, "选择期间缓存或随机数状态变了")

    def fill_locker(self) -> int:
        """
        玩家进大浴场更衣室，干员的浴场衣柜里放一条内裤，玩家精液充足
        Return arguments:
        int -- 内裤的服装id
        """
        from Script.Config import game_config

        pan_id = next(
            cid
            for cid, cloth in game_config.config_clothing_tem.items()
            if cloth.clothing_type == PANTIES
        )
        self.world.move(0, LOCKER_ROOM)
        npc = self.cache.character_data[self.chara_id]
        npc.cloth.cloth_locker_in_shower[PANTIES] = [pan_id]
        npc.dirty.cloth_locker_semen[PANTIES] = [
            game_config.config_clothing_type[PANTIES].name,
            0,
            0,
            0,
        ]
        player = self.cache.character_data[0]
        player.semen_point = player.semen_point_max = 1000
        return pan_id

    def test_locker_shoot_settles_at_start(self) -> None:
        """射在衣柜的内裤上：一个 0 分钟的具名编辑，选择期间不掷骰，Edit 开始后精液射出"""
        from Script.Config import game_config
        from Script.Core import constant

        self.fill_locker()
        player = self.cache.character_data[0]
        before = player.semen_point
        self.world.player.press(
            "的衣柜",
            "用衣服冲",
            game_config.config_clothing_type[PANTIES].name,
        )
        start, end, changed = self.run_pick(
            self.show(constant.Panel.CHECK_LOCKER)
        )
        self.assert_one_edit(start, end, changed)
        edit = next(a for a in self.started if a.who == "0")
        data = cast(Mapping[str, object], edit.action_data)
        self.assertEqual(data["edit"], "locker_shoot")
        self.assertLess(player.semen_point, before)

    def test_locker_steal_rides_edit(self) -> None:
        """偷走内裤再退出：一个 0 分钟的 Edit，之后内裤在玩家的藏品里，衣柜空了"""
        from Script.Core import constant

        pan_id = self.fill_locker()
        self.world.player.press("的衣柜", "偷走内裤", "返回", "返回")
        start, end, changed = self.run_pick(
            self.show(constant.Panel.CHECK_LOCKER)
        )
        self.assert_one_edit(start, end, changed)
        player = self.cache.character_data[0]
        npc = self.cache.character_data[self.chara_id]
        self.assertEqual(
            player.pl_collection.npc_panties_tem[self.chara_id], [pan_id]
        )
        self.assertEqual(npc.cloth.cloth_locker_in_shower[PANTIES], [])

    def test_locker_look_only_commits_nothing(self) -> None:
        """进了干员的衣柜什么也不做，一层层退出：没有行动，缓存不变，交互对象不变"""
        from Script.Core import constant

        self.fill_locker()
        target = self.cache.character_data[0].target_character_id
        self.world.player.press("的衣柜", "返回", "返回")
        start, end, changed = self.run_pick(
            self.show(constant.Panel.CHECK_LOCKER)
        )
        self.assertEqual(self.player_starts(), [])
        self.assertEqual(end, start)
        self.assertFalse(changed)
        self.assertEqual(
            self.cache.character_data[0].target_character_id, target
        )

    def test_food_bag_judges_at_start(self) -> None:
        """给交互对象吃特殊调味的饭：选择时不判定，开始时判定一次，被拒时开始的是拒绝食用"""
        from types import SimpleNamespace
        from unittest import mock

        from Script.Config import game_config
        from Script.Core import constant
        from Script.Modules.tk_ui import player_pick
        from Script.System.Cooking_System import cooking, food_bag_panel

        player = self.cache.character_data[0]
        self.world.move(self.chara_id, player.position)
        player.target_character_id = self.chara_id
        if not self.cache.recipe_data:
            cooking.init_recipes()
        recipe_id = next(
            rid
            for rid in self.cache.recipe_data
            if rid != -1
            and rid in game_config.config_recipes
            and game_config.config_recipes[rid].alcohol == 0
        )
        food = cooking.create_food("0", recipe_id)
        food.special_seasoning = SPECIAL_SEASONING
        player.food_bag[food.uid] = food
        judged: list[bool] = []

        def refuse(_who: int, _food: object) -> bool:
            judged.append(player_pick.in_pick())
            return False

        def pick() -> None:
            with player_pick.drafting("food_bag"):
                food_bag_panel.FoodGroupDraw.eat_food(
                    cast(food_bag_panel.FoodGroupDraw, SimpleNamespace()),
                    food.uid,
                )

        with (
            mock.patch.object(
                cooking, "judge_accept_special_seasoning_food", refuse
            ),
            mock.patch.object(
                food_bag_panel.handle_premise,
                "handle_instruct_judge_high_obscenity",
                return_value=False,
            ),
        ):
            _start, _end, changed = self.run_pick(pick)
        self.assertFalse(changed)
        self.assertEqual(judged, [False])
        behaviors = [
            cast(Mapping[str, object], a.action_data)["behavior_id"]
            for a in self.started
            if a.who == "0"
        ]
        self.assertEqual(behaviors, [constant.Behavior.REFUSE_EAT])

    def test_time_stop_refused_food_takes_no_time(self) -> None:
        """时停中给交互对象吃特殊调味的饭被拒：开始的拒绝食用在内核里是 0 分钟，时钟不动"""
        from types import SimpleNamespace
        from unittest import mock

        from Script.Config import game_config
        from Script.Core import constant
        from Script.Modules.tk_ui import player_pick
        from Script.System.Cooking_System import cooking, food_bag_panel

        player = self.cache.character_data[0]
        self.world.move(self.chara_id, player.position)
        player.target_character_id = self.chara_id
        if not self.cache.recipe_data:
            cooking.init_recipes()
        recipe_id = next(
            rid
            for rid in self.cache.recipe_data
            if rid != -1
            and rid in game_config.config_recipes
            and game_config.config_recipes[rid].alcohol == 0
        )
        food = cooking.create_food("0", recipe_id)
        food.special_seasoning = SPECIAL_SEASONING
        player.food_bag[food.uid] = food
        self.cache.time_stop_mode = True

        def pick() -> None:
            with player_pick.drafting("food_bag"):
                food_bag_panel.FoodGroupDraw.eat_food(
                    cast(food_bag_panel.FoodGroupDraw, SimpleNamespace()),
                    food.uid,
                )

        with (
            mock.patch.object(
                cooking,
                "judge_accept_special_seasoning_food",
                return_value=False,
            ),
            mock.patch.object(
                food_bag_panel.handle_premise,
                "handle_instruct_judge_high_obscenity",
                return_value=False,
            ),
        ):
            start, end, _changed = self.run_pick(pick)
        started = [
            (
                cast(Mapping[str, object], a.action_data)["behavior_id"],
                a.duration,
            )
            for a in self.started
            if a.who == "0"
        ]
        self.assertEqual(
            (started, end - start),
            ([(constant.Behavior.REFUSE_EAT, 0)], 0),
            "（玩家开始的行为与内核时长，时钟走过的分钟）",
        )

    def test_fridge_take_milk_rides_edit(self) -> None:
        """冰箱里带走干员的母乳：一个 0 分钟的 Edit，之后背包里有这份母乳，冰箱里没有了"""
        from Script.Core import constant

        self.cache.rhodes_island.milk_in_fridge[self.chara_id] = 120
        self.world.player.press("[带走]", "返回")
        start, end, changed = self.run_pick(self.show(constant.Panel.FRIDGE))
        self.assert_one_edit(start, end, changed)
        bag = self.cache.character_data[0].food_bag.values()
        self.assertEqual([f.milk_ml for f in bag if f.milk_ml], [120])
        self.assertNotIn(self.chara_id, self.cache.rhodes_island.milk_in_fridge)

    def test_drug_rides_edit(self) -> None:
        """使用理智恢复剂：一个 0 分钟的 Edit，之后药少了一瓶，理智回升"""
        from Script.Modules.tk_ui import player_pick
        from Script.UI.Panel import see_item_info_panel

        player = self.cache.character_data[0]
        player.item[0] = 1
        kernel_data.set_needs(player.cid, sanity=0)

        def pick() -> None:
            with player_pick.drafting("item"):
                see_item_info_panel.use_drug(0)

        start, end, changed = self.run_pick(pick)
        self.assert_one_edit(start, end, changed)
        self.assertEqual(player.item[0], 0)
        self.assertGreater(kernel_data.needs_of(player.cid)["sanity"], 0)

    def test_call_all_follow_rides_edit(self) -> None:
        """一键全跟随：一个 0 分钟的 Edit，之后每名干员都在跟随"""
        from types import SimpleNamespace

        from Script.Modules.tk_ui import player_pick
        from Script.UI.Panel import all_npc_position_panel as position

        def pick() -> None:
            with player_pick.drafting("npc_position"):
                position.All_Npc_Position_Panel.call_all(
                    cast(position.All_Npc_Position_Panel, SimpleNamespace())
                )

        start, end, changed = self.run_pick(pick)
        self.assert_one_edit(start, end, changed)
        follow = {
            self.cache.character_data[i].sp_flag.is_follow
            for i in self.cache.npc_id_got
            if i
        }
        self.assertEqual(follow, {1})

    def test_load_drops_old_format_food(self) -> None:
        """存档里玩家背包有一份没有母乳量的旧版本食物：读档后它不在了，另一份新版本的食物还在"""
        import shutil

        from Script.Core import save_handle
        from Script.System.Cooking_System import cooking

        if not self.cache.recipe_data:
            cooking.init_recipes()
        recipe_id = next(rid for rid in self.cache.recipe_data if rid != -1)
        bag = self.cache.character_data[0].food_bag
        old = cooking.create_food("0", recipe_id)
        del old.milk_ml
        new = cooking.create_food("0", recipe_id)
        bag[old.uid] = old
        bag[new.uid] = new
        save_id = "test_pick_draft_world"
        save_handle.establish_save(save_id)
        try:
            save_handle.input_load_save(save_id)
        finally:
            shutil.rmtree(
                save_handle.get_save_dir_path(save_id), ignore_errors=True
            )
        bag = self.cache.character_data[0].food_bag
        self.assertNotIn(old.uid, bag)
        self.assertIn(new.uid, bag)

    def test_diagnose_leave_without_check_commits_nothing(self) -> None:
        """有病人时打开亲自诊疗面板，一项检查都不做就返回：没有行动，缓存不变，时钟不动"""
        from Script.Core import constant

        self.world.player.press("返回")
        start, end, changed = self.run_pick(
            self.show(constant.Panel.CURE_PATIENT)
        )
        self.assertTrue(
            any("患者编号" in str(text) for text in self.world.player.screen),
            "面板里有一名病人",
        )
        self.assertEqual(self.player_starts(), [])
        self.assertEqual(end, start)
        self.assertFalse(changed)

    def test_map_open_and_leave_keeps_random_state(self) -> None:
        """打开地图再返回：没有行动，缓存与随机数状态的指纹不变"""
        from Script.Core import constant

        self.world.player.press("返回")
        start, end, changed = self.run_pick(self.show(constant.Panel.SEE_MAP))
        self.assertEqual(self.player_starts(), [])
        self.assertEqual(end, start)
        self.assertFalse(changed, "打开地图动了缓存或随机数状态")
