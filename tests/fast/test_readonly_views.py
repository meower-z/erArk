"""
工作集只读视图缓存与领域只读视图
================================
- 原始值未变时只解码一次并复用视图。缓冲区内 put 与 change 后立即读到新值，后续重复读取不重复解码。
- 不同 GameState 与嵌套 based_on 缓冲区互不串值。已丢弃的旧值不会误命中新状态。
- 缓存超过 LIMIT 时淘汰最久未用项。登记默认值与写入值均被冻结，不可原地修改。
- wardrobe.of、inventory.foods 与 second_behaviors 返回只读视图。clone 接口返回独立可变副本。
- FoodView 无实例字典且不可赋值。经 replace_foods 复制食物视图时原始记录原样保留。
- 食物背包分组每份食物只解码一次。脱衣的解码次数不超过服装写入次数加一。
- 单次经验结算只产生一条写入操作。批量偷内裤只调用一次 player_collection.put。
"""

import dataclasses
from collections.abc import Mapping
from types import MappingProxyType, SimpleNamespace
from typing import Any, cast
from unittest import mock

from Script.Config import game_config
from Script.Core import game_type
from Script.Design import clothing, handle_premise
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, inventory, kitchen
from Script.Modules.domains import player_collection, wardrobe
from Script.Modules.gameplay_resolution import readonly, working
from Script.Settle import common_default
from Script.System.Cooking_System import cooking
from Script.UI.Moudle import draw
from Script.UI.Panel import check_locker_panel, food_bag_panel
from tests import kernel_data
from tests.fast.base import FastTestCase

TABLE = "test_readonly.table"
COUNT = "test_readonly.count"
EMPTY = core.GameState(0, MappingProxyType({}), MappingProxyType({}))


def _add(old: core.JSON, op: str, operand: core.JSON) -> core.JSON:
    assert op == "add" and isinstance(old, Mapping)
    assert isinstance(operand, int)
    return {**old, "n": cast(int, old.get("n", 0)) + operand}


def _with(value: core.JSON) -> core.GameState:
    return core.with_value(EMPTY, None, TABLE, value)


def _assign(target: Any, key: object, value: object) -> None:
    target[key] = value


def _rebind(target: object, name: str, value: object) -> None:
    setattr(target, name, value)


def _append(target: Any, item: object) -> None:
    target.append(item)


class Decoded:
    """统计解码调用次数并把映射值转为整数元组的测试解码器"""

    def __init__(self) -> None:
        """将解码调用计数初始化为 0"""
        self.calls = 0

    def __call__(self, raw: core.JSON) -> tuple[int, ...]:
        """
        递增调用计数，将映射原始值的值转为整数元组
        Keyword arguments:
        raw -- 工作集读出的原始 JSON 值
        Return arguments:
        tuple[int, ...] -- 映射各项值转换成的整数元组，非映射时为空元组
        """
        self.calls += 1
        table = raw if isinstance(raw, Mapping) else {}
        return tuple(cast(int, v) for v in table.values())


class ViewCacheTest(FastTestCase):
    """验证 readonly.view 缓存命中、失效、隔离、淘汰与工作集值冻结"""

    def setUp(self) -> None:
        """隔离工作集键表，登记测试键 TABLE 与 COUNT，并准备计数解码器"""
        super().setUp()
        self.enterContext(mock.patch.dict(working._keys))
        working.register(TABLE, {})
        working.register(COUNT, {}, _add)
        self.decode = Decoded()

    def view(self, game: core.GameState | None = None) -> tuple[int, ...]:
        """
        经 readonly.view 读取并解码测试键 TABLE
        Keyword arguments:
        game -- 给出时只读该 GameState，为 None 时读当前缓冲区
        Return arguments:
        tuple[int, ...] -- 解码得到的整数元组
        """
        return readonly.view(None, TABLE, self.decode, game)

    def test_unchanged_value_decodes_once(self) -> None:
        """同一状态连续读取六次只解码一次，且每次返回同一个视图对象"""
        game = _with({"a": 1, "b": 2})
        first = self.view(game)
        self.assertEqual(first, (1, 2))
        for _ in range(5):
            self.assertIs(self.view(game), first)
        self.assertEqual(self.decode.calls, 1)

    def test_put_and_change_are_read_back(self) -> None:
        """缓冲区内 put 与 change 后立即读到新值，后续重复读取复用缓存不重复解码"""
        with working.based_on(_with({"a": 1})):
            self.assertEqual(self.view(), (1,))
            working.put(None, TABLE, {"a": 7})
            self.assertEqual(self.view(), (7,))
            self.assertEqual(self.view(), (7,))
            self.assertEqual(self.decode.calls, 2)
        with working.based_on(EMPTY):
            counted = Decoded()
            self.assertEqual(readonly.view(None, COUNT, counted), ())
            working.change(None, COUNT, "add", 3)
            self.assertEqual(readonly.view(None, COUNT, counted), (3,))
            working.change(None, COUNT, "add", 4)
            self.assertEqual(readonly.view(None, COUNT, counted), (7,))
            self.assertEqual(counted.calls, 3)

    def test_states_and_buffers_stay_apart(self) -> None:
        """不同 GameState 与嵌套 based_on 缓冲区各自读到对应值。退出内层缓冲区后恢复外层读值。"""
        one, two = _with({"a": 1}), _with({"a": 2})
        for _ in range(2):
            self.assertEqual(self.view(one), (1,))
            self.assertEqual(self.view(two), (2,))
        with working.based_on(one):
            working.put(None, TABLE, {"a": 3})
            self.assertEqual(self.view(), (3,))
            self.assertEqual(self.view(one), (1,))
            with working.based_on(two):
                self.assertEqual(self.view(), (2,))
            self.assertEqual(self.view(), (3,))
        with working.based_on(one):
            self.assertEqual(self.view(), (1,))

    def test_discarded_values_never_answer_for_new_ones(self) -> None:
        """连续创建并丢弃 2000 份状态时，每次读取都解码一次并返回对应新值"""
        for n in range(2000):
            self.assertEqual(self.view(_with({"n": n})), (n,))
        self.assertEqual(self.decode.calls, 2000)

    def test_cache_stays_bounded(self) -> None:
        """缓存条目超过 LIMIT 后读值保持正确。最久未用的条目会被淘汰，重读时重新解码。"""
        game = _with({"a": 1})
        for who in range(readonly.LIMIT + 10):
            readonly.view(str(who), TABLE, self.decode, game)
        self.assertEqual(self.view(game), (1,))
        before = self.decode.calls
        readonly.view("0", TABLE, self.decode, game)
        self.assertEqual(self.decode.calls, before + 1)

    def test_written_values_are_frozen(self) -> None:
        """登记默认值与 put 写入值均不可原地修改。写入后修改原字典不影响已存值。"""
        given: dict[str, Any] = {"a": [1, 2]}
        with working.based_on(EMPTY):
            default = working.get(None, TABLE)
            working.put(None, TABLE, given)
            given["a"].append(3)
            given["b"] = [4]
            stored = working.get(None, TABLE)
        assert isinstance(stored, Mapping)
        self.assertEqual(dict(stored), {"a": (1, 2)})
        for table in (default, stored):
            with self.assertRaises(TypeError):
                _assign(table, "c", 0)


class DomainViewTest(FastTestCase):
    """验证服装、食物背包、二段行为的只读视图与热路径读写次数"""

    def setUp(self) -> None:
        """创建玩家（角色 0）与干员（角色 1）"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.npc = self.world.chara(1, "干员")

    def test_cloth_view_is_shared_and_read_only(self) -> None:
        """wardrobe.of 复用同一只读 ClothView 并拒绝修改。写入后旧视图不变，新读取反映更新。"""
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 9, [901])
        cloth = wardrobe.of(1)
        self.assertIs(wardrobe.of(1), cloth)
        self.assertEqual(cloth.cloth_wear[9], (901,))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            _rebind(cloth, "cloth_wear", {})
        with self.assertRaises(TypeError):
            _assign(cloth.cloth_wear, 9, ())
        with self.assertRaises(AttributeError):
            _append(cloth.cloth_wear[9], 902)
        kernel_data.put(wardrobe.append, 1, "cloth_wear", 9, 902)
        self.assertEqual(cloth.cloth_wear[9], (901,))
        self.assertEqual(wardrobe.of(1).cloth_wear[9], (901, 902))

    def test_cloth_clone_is_independent(self) -> None:
        """wardrobe.clone_mutable_snapshot 每次返回独立可变 CLOTH。改副本不影响衣柜，put 后才更新。"""
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 9, [901])
        clone = wardrobe.clone_mutable_snapshot(1)
        self.assertIsInstance(clone, game_type.CLOTH)
        self.assertIsNot(clone, wardrobe.clone_mutable_snapshot(1))
        clone.cloth_wear[9].append(902)
        clone.equipment_condition = 2
        self.assertEqual(wardrobe.of(1).cloth_wear[9], (901,))
        kernel_data.put(wardrobe.put, 1, clone)
        self.assertEqual(wardrobe.of(1).cloth_wear[9], (901, 902))
        self.assertEqual(wardrobe.of(1).equipment_condition, 2)

    def test_food_bag_view_is_shared_and_read_only(self) -> None:
        """inventory.foods 复用同一只读映射与 FoodView。修改或删除 clone_mutable_snapshot_foods 副本不影响背包。"""
        food = cooking.create_food("0", min(game_config.config_recipes))
        kernel_data.put(inventory.put_food, 1, food)
        bag = inventory.foods(1)
        self.assertIs(inventory.foods(1), bag)
        self.assertEqual(bag[food.uid].quality, food.quality)
        with self.assertRaises(TypeError):
            _assign(bag, food.uid, bag[food.uid])
        with self.assertRaises(dataclasses.FrozenInstanceError):
            _rebind(bag[food.uid], "quality", 0)
        clone = inventory.clone_mutable_snapshot_foods(1)
        clone[food.uid].quality = 0
        del clone[food.uid]
        self.assertEqual(list(inventory.foods(1)), [food.uid])
        self.assertEqual(inventory.foods(1)[food.uid].quality, food.quality)

    def test_food_view_has_no_instance_dict(self) -> None:
        """FoodView 没有实例字典，对它调用 vars 报 TypeError，给属性赋值报 FrozenInstanceError。再次读取的品质不变。"""
        food = cooking.create_food("0", min(game_config.config_recipes))
        kernel_data.put(inventory.put_food, 1, food)
        view = inventory.foods(1)[food.uid]
        with self.assertRaises(TypeError):
            vars(view)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            _rebind(view, "quality", 0)
        self.assertEqual(inventory.foods(1)[food.uid].quality, food.quality)

    def test_copied_bag_keeps_stored_records(self) -> None:
        """将 inventory.foods 视图经 replace_foods 复制到另一角色时，原始食物记录原样保留，不补默认值也不丢额外键"""
        uid = "12345678-1234-5678-1234-567812345678"
        old: dict[str, core.JSON] = {
            "id": "0",
            "name": "old",
            "special_seasoning": 11,
            "kept": 7,
        }
        kernel_data.put(working.put, "1", inventory.FOODS, {uid: old})
        kernel_data.put(inventory.replace_foods, 0, inventory.foods(1))
        copied = cast(Mapping[str, Any], working.get("0", inventory.FOODS))
        self.assertEqual(dict(copied[uid]), old)

    def test_second_behaviors_are_the_stored_table(self) -> None:
        """activity.second_behaviors 重复读取返回同一个只读映射对象，并拒绝原地赋值"""
        second = next(iter(activity.second_order()))
        kernel_data.put(activity.set_second_behavior, 1, second, 1)
        table = activity.second_behaviors(1)
        self.assertIs(activity.second_behaviors(1), table)
        self.assertEqual(dict(table), {second: 1})
        with self.assertRaises(TypeError):
            _assign(table, second, 0)

    def test_food_bag_groups_decode_each_food_once(self) -> None:
        """食物背包分组与食物前提判定共享缓存，六份食物共只构造六次 FoodView"""
        recipe = min(game_config.config_recipes)
        foods = [cooking.create_food("0", recipe) for _ in range(6)]
        with kernel_data.writing():
            for food in foods:
                inventory.put_food(0, food)
        panel = food_bag_panel.FoodBagPanel(100)
        with mock.patch.object(
            kitchen, "food_view", wraps=kitchen.food_view
        ) as made:
            normal, special = panel.get_food_group()
            handle_premise.handle_have_food(0)
            handle_premise.handle_not_have_food(0)
        self.assertEqual(made.call_count, len(foods))
        grouped = [uid for uids in normal.values() for uid in uids]
        self.assertEqual(grouped, [food.uid for food in foods])
        self.assertEqual(special, {})

    def test_strip_decodes_clothes_once_per_write(self) -> None:
        """脱去非必穿服装时，ClothView 构造次数不超过服装写入次数加一"""
        worn = clothing.get_cloth_wear_zero_except_need
        writes: list[str] = []
        put = wardrobe.put

        def counted(cid: int, cloth: game_type.CLOTH) -> None:
            writes.append(str(cid))
            put(cid, cloth)

        view_type = wardrobe.ClothView
        with (
            mock.patch.object(wardrobe, "put", counted),
            mock.patch.object(wardrobe, "ClothView", wraps=view_type) as made,
        ):
            kernel_data.written(worn, 1)
        self.assertLessEqual(made.call_count, len(writes) + 1)

    def test_experience_delta_is_one_write(self) -> None:
        """单次经验结算在缺键与有键、增减与下限归零情况下均得出正确值，且只产生一条经验写入操作"""
        exp_id = min(
            i
            for i, row in game_config.config_experience.items()
            if row.type not in (1, 7)
        )
        cases = ((None, 3, 3), (None, -2, 0), (5, -2, 3), (2, -9, 0))
        for start, delta, end in cases:
            with self.subTest(start=start, delta=delta):
                kernel_data.put(abilities.experience(1).pop, exp_id, None)
                if start is not None:
                    kernel_data.put(
                        abilities.experience(1).__setitem__, exp_id, start
                    )
                with working.based_on(core.state()) as buffer:
                    common_default.base_chara_experience_common_settle(
                        1, exp_id, delta
                    )
                    got = abilities.experience(1)[exp_id]
                ops = [
                    op
                    for op in buffer.carried()
                    if isinstance(op, Mapping)
                    and op.get("key") == abilities.EXPERIENCE
                ]
                self.assertEqual(got, end)
                self.assertEqual(len(ops), 1)

    def test_bulk_locker_steal_writes_collection_once(self) -> None:
        """批量偷取多名干员浴场衣柜内裤时只调用一次 player_collection.put，并按顺序追加到各干员收藏列表"""
        pans = [
            i
            for i, row in game_config.config_clothing_tem.items()
            if row.clothing_type == 9
        ][:3]
        second = self.world.chara(2, "干员二")
        locker = "cloth_locker_in_shower"
        kernel_data.put(wardrobe.set_part, 1, locker, 9, pans[:2])
        kernel_data.put(wardrobe.set_part, second.cid, locker, 9, pans[2:])
        kernel_data.put(player_collection.init_zero, 0)
        scene: Any = SimpleNamespace(scene_tag=["Locker_Room"])
        panel: Any = SimpleNamespace()
        put = player_collection.put
        with (
            mock.patch.object(draw.WaitDraw, "draw"),
            mock.patch.object(player_collection, "put", wraps=put) as writes,
            kernel_data.writing(),
        ):
            check_locker_panel.Check_locker_Panel.steal_all_pan(
                panel, [1, second.cid], scene
            )
        self.assertEqual(writes.call_count, 1)
        stolen = player_collection.get("npc_panties_tem")
        self.assertEqual(stolen[1][-2:], pans[:2])
        self.assertEqual(stolen[second.cid][-1:], pans[2:])
