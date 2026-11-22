# -*- coding: UTF-8 -*-
"""
角色的道具、食物背包、服装、身体管理与状态值在内核状态里
======================================================
- 给状态值加量时按给出的上下限夹住，整数加分数得分数。给没有的状态加量报 KeyError。
- 综合数值结算按状态效果给角色状态值加量，并在结算记录里记下改变量。
- 商店买道具时数量停在 99。用掉一个道具时数量减一。
- 食物背包按放进的顺序排列。拿走一份食物时，别的食物顺序不变。
- 变质结算拿走品质降到 0 或更低的食物，留下的食物品质下降。
- 脱下首饰和必须穿着的衣物以外的服装时，脱衣途中嵌套调用穿上的衣物留在服装里。
- 新角色有每种状态、道具与身体管理的项，值为 0。
- 读档时 adopt_old_save 把角色对象上的五个属性搬进内核状态，并从对象上删掉。服装缺的属性取默认值，多的属性不存。
  没有 milk_ml 的食物照样搬进背包，读档修复 _drop_old_format_food 再删掉它。
- 存档编解码后五个键的值与类型不变，分数的状态值仍是分数。
- 写回读出的同一个值不产生写入。值相等而类型不同时产生写入。
- body_manage.clear 把给出编号里不为 0 的项清成 0，其余项不变。
- H 中的服装面板绘制时在写缓冲外读取服装，被外衣遮住的内衣不显示按钮，
  不改存下的 cloth_see，只记下本次绘制判定的可见性。
- 记下的可见性在选择草稿开启时、点服装按钮重绘后，或之后第一个行动开始
  （开始代码之前）或结束时写入 cloth_see；点按钮时接着脱下对应衣物。
- H 中外衣遮住胸衣时，在选择阶段绘制面板并点击外衣按钮，草稿在开启时与重绘后
  各写入一次可见性，落成的编辑行动正常开始，外衣脱下，cloth_see[6] 变为可见。
- H 中下衣遮住内裤且无透视时，绘制面板后再选收走内裤：行动开始先写入绘制判定的
  不可见，收内裤开始代码再把 cloth_see[9] 设为 True，内裤收入玩家收藏。
- 从衣柜拿走内裤时同步清空面板副本，再次拿取不再重复加入收藏。
"""

import json
from fractions import Fraction
from types import SimpleNamespace
from typing import Any
from unittest import mock

from Script.Config import game_config
from Script.Design import attr_calculation, character, clothing, game_time
from Script.Design import settle_behavior
from Script.Kernel import core
from Script.Core import constant, game_type
from Script.Modules.domains import body_manage, flags, inventory, modes
from Script.Modules.domains import player_collection, status, wardrobe
from Script.Modules.gameplay_resolution import working
from Script.Modules.tk_ui import player_pick
from Script.Modules.save_load import kernel_state
from Script.System.Cooking_System import cooking
from Script.UI.Moudle import draw
from Script.UI.Panel import check_locker_panel, cloth_panel, h_item_shop_panel
from Script.Settle import item_effect
from tests import chara_abilities as ca, kernel_data
from tests import world as world_module
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

THIRD = Fraction(1, 3)


def _cloth_of_part(part: int) -> int:
    """取部位 part 里编号最小的服装编号"""
    tem = game_config.config_clothing_tem
    return min(i for i in tem if tem[i].clothing_type == part)


def _food(quality: int) -> game_type.Food:
    """按编号最小的菜谱做一份食物，品质为 quality"""
    recipes = game_config.config_recipes
    food = cooking.create_food("0", min(recipes))
    food.quality = quality
    return food


class CharaInventoryBodyStateTest(FastTestCase):
    """五项角色数据经领域模块读写，存在内核状态里"""

    def setUp(self) -> None:
        """建玩家（角色 0）与干员（角色 1）"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.npc = self.world.chara(1, "干员")

    def test_status_add_clamps_and_stays_exact(self) -> None:
        """加的量按上下限夹住。整数加分数得分数。给没有的状态加量报 KeyError"""
        with kernel_data.writing():
            status.add(1, 0, 5)
            status.add(1, 0, THIRD)
            status.add(1, 12, 50, max=30)
            status.add(1, 13, -5, min=0)
        table = status.of(1)
        self.assertEqual(table[0], 5 + THIRD)
        self.assertIs(type(table[0]), Fraction)
        self.assertEqual((table[12], table[13]), (30, 0))
        with self.assertRaises(KeyError), kernel_data.writing():
            status.add(1, 999999, 1)

    def test_value_effect_adds_to_status(self) -> None:
        """综合数值结算 S|12 G 10 给角色 1 的状态 12 加 10，结算记录也记下 10"""
        change = game_type.CharacterStatusChange()
        kernel_data.written(
            settle_behavior.handle_comprehensive_value_effect,
            1,
            ["A1", "S|12", "G", "10"],
            change,
        )
        self.assertEqual(status.of(1)[12], 10)
        self.assertEqual(change.status_data[12], 10)

    def test_shop_stops_at_99_and_use_takes_one(self) -> None:
        """有 98 个道具 100 时再买 5 个，数量为 99。handle_use_body_lubricant 用掉一个后为 98"""
        lubricant = 100
        kernel_data.put(inventory.set_item, 0, lubricant, 98)
        kernel_data.put(modes.set_debug, True)
        try:
            button = h_item_shop_panel.BuyItemByItemNameDraw(
                lubricant, 60, True, True, 0
            )
            kernel_data.written(button.buy_item, 5)
        finally:
            kernel_data.put(modes.set_debug, False)
        self.assertEqual(inventory.items(0)[lubricant], 99)
        change = game_type.CharacterStatusChange()
        kernel_data.written(
            item_effect.handle_use_body_lubricant, 0, 1, change, game_time.now()
        )
        self.assertEqual(inventory.items(0)[lubricant], 98)

    def test_food_bag_keeps_order_through_take_and_spoil(self) -> None:
        """拿走第一份食物再放回后它排在最后，另两份顺序不变。变质结算拿走品质降到 0 或更低的食物，留下的食物品质下降"""
        first, middle, last = _food(5), _food(1), _food(9)
        with kernel_data.writing():
            for food in (first, middle, last):
                inventory.put_food(1, food)
        self.assertEqual(
            list(inventory.foods(1)), [first.uid, middle.uid, last.uid]
        )
        with kernel_data.writing():
            taken = inventory.take_food(1, first.uid)
            inventory.put_food(1, taken)
        self.assertEqual(vars(taken), vars(first))
        self.assertEqual(
            list(inventory.foods(1)), [middle.uid, last.uid, first.uid]
        )
        gone = kernel_data.written(cooking.handle_food_deterioration, 1)
        self.assertEqual(gone, 1)
        bag = inventory.foods(1)
        self.assertEqual(list(bag), [last.uid, first.uid])
        self.assertEqual([f.quality for f in bag.values()], [4, 2])

    def test_strip_keeps_cloth_worn_by_nested_call(self) -> None:
        """
        有素质 150 的角色脱到只剩首饰和必须穿着的衣物。首饰以外的标准服装脱下，
        脱衣途中嵌套调用穿上的服装 1301（部位 13）留在身上
        """
        ca.talent(1)[150] = 1
        worn = wardrobe.of(1).cloth_wear
        jewelry = {
            part: ids
            for part, ids in worn.items()
            if ids and game_config.config_clothing_tem[ids[0]].tag == 6
        }
        kernel_data.written(clothing.get_cloth_wear_zero_except_need, 1)
        left = {p: ids for p, ids in wardrobe.of(1).cloth_wear.items() if ids}
        self.assertEqual(left, {**jewelry, 13: [1301]})

    def test_new_character_has_zero_tables(self) -> None:
        """init_attr 之后每种状态、道具与身体管理都有一项，值为 0"""
        kernel_data.written(character.init_attr, 1)
        self.assertEqual(
            dict(status.of(1)),
            dict.fromkeys(game_config.config_character_state, 0),
        )
        self.assertEqual(
            dict(inventory.items(1)), dict.fromkeys(game_config.config_item, 0)
        )
        self.assertEqual(
            dict(body_manage.of(1)), attr_calculation.get_body_manage_zero()
        )

    def test_adopt_old_save_moves_fields_off_characters(self) -> None:
        """
        存档的角色对象带着五个属性时，adopt_old_save 把它们搬进内核状态并从对象上删掉。
        服装缺的属性取默认值，多的属性不存。没有这些属性的角色读默认值。没有 milk_ml 的食物照样搬进背包，
        _drop_old_format_food 再删掉它
        """
        old_cloth = SimpleNamespace(
            cloth_wear={5: [501]}, cloth_off={}, retired_field=1
        )
        stale = _food(3)
        del stale.milk_ml
        fresh = _food(4)
        pickled = SimpleNamespace(
            item={100: 3},
            food_bag={stale.uid: stale, fresh.uid: fresh},
            cloth=old_cloth,
            body_manage={24: 1},
            status_data={0: THIRD, 12: 7},
        )
        bare = SimpleNamespace()
        loaded: dict[str, Any] = {"character_data": {1: pickled, 8: bare}}
        with kernel_data.writing():
            for domain in (inventory, wardrobe, body_manage, status):
                domain.adopt_old_save(loaded)
        self.assertEqual(vars(pickled), {})
        self.assertEqual(dict(inventory.items(1)), {100: 3})
        self.assertEqual(dict(status.of(1)), {0: THIRD, 12: 7})
        self.assertEqual(dict(body_manage.of(1)), {24: 1})
        cloth = wardrobe.of(1)
        self.assertEqual(cloth.cloth_wear, {5: [501]})
        self.assertEqual(cloth.equipment_condition, 0)
        self.assertFalse(hasattr(cloth, "retired_field"))
        bag = inventory.foods(1)
        self.assertEqual(list(bag), [stale.uid, fresh.uid])
        self.assertFalse(hasattr(bag[stale.uid], "milk_ml"))
        self.assertEqual(dict(status.of(8)), {})
        self.assertEqual(vars(wardrobe.of(8)), vars(game_type.CLOTH()))
        kernel_data.written(cooking._drop_old_format_food)
        self.assertEqual(list(inventory.foods(1)), [fresh.uid])

    def test_save_round_trip_keeps_values_and_types(self) -> None:
        """存档编解码后五个键的值不变。分数的状态值仍是分数，道具与服装的键是 int，食物按 uid 读回"""
        food = _food(6)
        with kernel_data.writing():
            status.set(1, 0, THIRD)
            inventory.set_item(1, 100, 4)
            inventory.put_food(1, food)
            wardrobe.set_part(1, "cloth_off", 7, [751])
            body_manage.set(1, 24, 1)
        before = core.state()
        text = json.dumps(kernel_state.encode(before, "tok"))
        after = kernel_state.decode(json.loads(text), tagged=True)
        self.assertEqual(status.of(1, after)[0], THIRD)
        self.assertIs(type(status.of(1, after)[0]), Fraction)
        self.assertEqual(dict(inventory.items(1, after))[100], 4)
        self.assertEqual(vars(inventory.foods(1, after)[food.uid]), vars(food))
        self.assertEqual(wardrobe.of(1, after).cloth_off[7], [751])
        self.assertEqual(vars(wardrobe.of(1, after)), vars(wardrobe.of(1)))
        self.assertEqual(
            dict(body_manage.of(1, after)), dict(body_manage.of(1))
        )

    def test_writing_back_same_value_writes_nothing(self) -> None:
        """读出再写回同一个值不产生效果。把状态 0 的值 0 换成 Fraction(0) 产生效果"""
        kernel_data.put(inventory.put_food, 1, _food(5))
        with working.based_on(core.state()) as buffer:
            wardrobe.put(1, wardrobe.of(1))
            status.replace(1, status.of(1))
            status.set(1, 0, status.of(1)[0])
            inventory.replace_items(1, inventory.items(1))
            inventory.replace_foods(1, inventory.foods(1))
            body_manage.replace(1, body_manage.of(1))
            self.assertEqual(buffer.effects(), ())
            status.set(1, 0, Fraction(0))
            self.assertNotEqual(buffer.effects(), ())

    def test_body_manage_clear_zeroes_given_ids(self) -> None:
        """清掉 30~39 的身体管理时，这些项里不为 0 的换成 0，别的项不变"""
        kernel_data.put(body_manage.replace, 1, {24: 1, 31: 1, 35: 0})
        kernel_data.put(body_manage.clear, 1, range(30, 40))
        self.assertEqual(dict(body_manage.of(1)), {24: 1, 31: 0, 35: 0})

    def test_h_cloth_panel_reads_without_writing(self) -> None:
        """
        穿着外衣（部位 5）与胸衣（部位 6）时，写缓冲外建 SwitchCharacterClothPanel
        只列外衣按钮、不列胸衣按钮，存下的 cloth_see 不变
        """
        coat, bra = _cloth_of_part(5), _cloth_of_part(6)
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 5, [coat])
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 6, [bra])
        kernel_data.put(wardrobe.set, 1, "cloth_see", {6: True, 9: True})
        aim(0, 1)
        panel = cloth_panel.SwitchCharacterClothPanel(0, 100, 20, 0, False)
        shown = {b.cloth_id for b in panel.button_list}
        self.assertIn(coat, shown)
        self.assertNotIn(bra, shown)
        self.assertEqual(wardrobe.of(1).cloth_see, {6: True, 9: True})

    def test_h_cloth_button_keeps_drawn_see(self) -> None:
        """
        玩家处于 H（is_h=1）、目标未穿下衣且穿着内裤（部位 9）、存下的 cloth_see
        为 {6: False, 9: False} 时，在玩家选择（world.act）中绘制面板并点击内裤
        按钮（switch_cloth）：草稿在开启时写入绘制判定的可见性，cloth_see 更新为
        {6: False, 9: True}，内裤从 cloth_wear[9] 移入 cloth_off[9]
        """
        pan = _cloth_of_part(9)
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 9, [pan])
        kernel_data.put(wardrobe.set, 1, "cloth_see", {6: False, 9: False})
        kernel_data.put(flags.set, 0, is_h=1)
        aim(0, 1)

        def click_pan() -> None:
            panel = cloth_panel.SwitchCharacterClothPanel(0, 100, 20, 0, False)
            next(
                b for b in panel.button_list if b.cloth_id == pan
            ).switch_cloth()

        world_module.act(click_pan)
        self.assertEqual(wardrobe.of(1).cloth_see, {6: False, 9: True})
        self.assertEqual(wardrobe.of(1).cloth_wear[9], [])
        self.assertIn(pan, wardrobe.of(1).cloth_off[9])

    def test_h_cloth_drawn_see_kept_by_next_action(self) -> None:
        """
        玩家处于 H（is_h=1）、目标只穿内裤（部位 9）且存下的 cloth_see 为
        {6: False, 9: False} 时，绘制服装面板而不点按钮，再选择等待 5 分钟：
        绘制时不写 cloth_see，等待开始时将其更新为 {6: False, 9: True}；
        随后不改 cloth_see 直接清空 cloth_wear[9]，再次绘制面板时内裤一栏显示「真空」
        """
        pan = _cloth_of_part(9)
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 9, [pan])
        kernel_data.put(wardrobe.set, 1, "cloth_see", {6: False, 9: False})
        kernel_data.put(flags.set, 0, is_h=1)
        aim(0, 1)

        def draw_then_wait() -> None:
            cloth_panel.SwitchCharacterClothPanel(0, 100, 20, 0, False)
            self.assertEqual(wardrobe.of(1).cloth_see[9], False)
            player_pick.choose(constant.Behavior.WAIT, 5, target=1)

        world_module.act(draw_then_wait)
        self.assertEqual(wardrobe.of(1).cloth_see, {6: False, 9: True})
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 9, [])
        aim(0, 1)
        panel = cloth_panel.SwitchCharacterClothPanel(0, 100, 20, 0, False)
        texts = [getattr(d, "text", "") for d in panel.draw_list]
        name = game_config.config_clothing_type[9].name
        self.assertIn(f"  [{name}]: 真空", texts)

    def test_h_cloth_outer_click_runs_as_edit(self) -> None:
        """
        玩家处于 H（is_h=1）、目标穿着外衣（部位 5）与胸衣（部位 6）且存下的 cloth_see
        为 {6: False, 9: False} 时，在玩家选择（world.act）中绘制面板并点击外衣按钮：
        草稿在开启时与重绘后各写入一次可见性，形成的编辑行动正常开始不报错，
        外衣从 cloth_wear[5] 移入 cloth_off[5]，cloth_see[6] 更新为重绘判定的 True
        """
        coat, bra = _cloth_of_part(5), _cloth_of_part(6)
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 5, [coat])
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 6, [bra])
        kernel_data.put(wardrobe.set, 1, "cloth_see", {6: False, 9: False})
        kernel_data.put(flags.set, 0, is_h=1)
        aim(0, 1)

        def click_coat() -> None:
            panel = cloth_panel.SwitchCharacterClothPanel(0, 100, 20, 0, False)
            next(
                b for b in panel.button_list if b.cloth_id == coat
            ).switch_cloth()

        world_module.act(click_coat)
        self.assertEqual(wardrobe.of(1).cloth_wear[5], [])
        self.assertIn(coat, wardrobe.of(1).cloth_off[5])
        self.assertEqual(wardrobe.of(1).cloth_see[6], True)

    def test_h_start_code_sets_see_after_drawn(self) -> None:
        """
        玩家处于 H（is_h=1）且无透视、目标穿着下衣（部位 8）遮住内裤（部位 9）时，
        在玩家选择（world.act）中先绘制服装面板，再选脱衣面板的「把内裤收走」：
        行动开始先写入绘制判定的不可见，随后脱衣开始代码把 cloth_see[9] 设为 True，
        内裤收入玩家收藏
        """
        skirt, pan = _cloth_of_part(8), _cloth_of_part(9)
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 8, [skirt])
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 9, [pan])
        kernel_data.put(wardrobe.set, 1, "cloth_see", {6: False, 9: False})
        kernel_data.put(flags.set, 0, is_h=1)
        aim(0, 1)

        def draw_then_take() -> None:
            cloth_panel.SwitchCharacterClothPanel(0, 100, 20, 0, False)
            take_pan: Any = SimpleNamespace(button_id=3)
            cloth_panel.SeeUndressButtonList.chose_button(take_pan)

        world_module.act(draw_then_take)
        self.assertIn(pan, player_collection.get("npc_panties_tem")[1])
        self.assertEqual(wardrobe.of(1).cloth_see[9], True)

    def test_locker_panel_takes_panties_once(self) -> None:
        """
        淋浴间衣柜有内裤（部位 9）时，连调两次 FindDraw.get_pan 后衣柜和面板副本
        now_locker[9] 都清空，内裤只加入收藏一次
        """
        pan = _cloth_of_part(9)
        shower = clothing.CLOTH_LOCKER_TYPE_SHOWER
        kernel_data.put(
            wardrobe.set_part, 1, "cloth_locker_in_shower", 9, [pan]
        )
        find: Any = SimpleNamespace(
            npc_id=1,
            locker_type=shower,
            pl_data=self.player,
            character_data=self.npc,
            now_locker=clothing.get_cloth_locker_by_type(1, shower),
        )
        with mock.patch.object(draw.WaitDraw, "draw"), kernel_data.writing():
            check_locker_panel.FindDraw.get_pan(find)
            check_locker_panel.FindDraw.get_pan(find)
        self.assertEqual(find.now_locker[9], [])
        self.assertEqual(wardrobe.of(1).cloth_locker_in_shower[9], [])
        self.assertEqual(player_collection.get("npc_panties_tem")[1], [pan])
