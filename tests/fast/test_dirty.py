# -*- coding: UTF-8 -*-
"""
角色的污浊数据（body.dirty）
==========================
- 稀疏存储：默认空表，新角色的 cloth_locker_semen 为空字典（与初始化语义一致）。
- body_semen、absorbed_total_semen、semen_flow 保留精确 Num（int 与 Fraction）。
- condom_decoration 的元组键 (部位类型, 部位cid) 经编码往返不变。
- reset 保留累计量、衣柜、无意识记录、精液流通与累计吸收，清零当前量与灌肠/避孕套装饰/阴茎污浊值；
  clear 全部清空。
- adopt_old_save 把 float 转为 Fraction，拆分共用的 cloth_semen/cloth_locker_semen，重置缺键的服装表。
"""

from fractions import Fraction
from unittest import mock

from Script.Config import game_config
from Script.Core import game_type
from Script.Design import game_time, handle_premise
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import dirty
from Script.Modules.gameplay_resolution import working
from Script.Settle import default as settle_default
from tests.fast.base import FastTestCase
from Script.Modules.save_load.legacy_pickle import LegacyObject


class DirtyTest(FastTestCase):
    """body.dirty 领域的稀疏读写、精确数值、重置与旧档导入"""

    def setUp(self) -> None:
        """载入内核模块并建出两名测试角色"""
        super().setUp()
        core.load(load_order.LOAD_ORDER)
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")

    def test_defaults_and_exact_num_roundtrip(self) -> None:
        """默认衣柜精液表为空；body_semen、absorbed_total_semen 与 semen_flow 保留 Fraction"""
        v0 = dirty.view(1)
        self.assertEqual(len(v0.body_semen), len(game_config.config_body_part))
        self.assertEqual(
            len(v0.cloth_semen), len(game_config.config_clothing_type)
        )
        self.assertEqual(v0.cloth_locker_semen, {})
        self.assertFalse(dirty.has_semen_flow(1))
        self.assertEqual(dirty.body_semen_amount(1, 8), 0)

        with working.based_on(core.state()) as buf:
            with dirty.editing(1) as d:
                d.body_semen[8][1] = Fraction(5, 2)
                d.body_semen[8][2] = 1
                d.body_semen[8][3] = 10
                d.absorbed_total_semen = Fraction(7, 4)
                d.semen_flow.append(
                    {
                        "source": {"type": 0, "id": 6},
                        "targets": [
                            {
                                "type": 0,
                                "id": 10,
                                "remaining_volume": Fraction(3, 2),
                            }
                        ],
                    }
                )
                d.condom_decoration[(0, 0)] = [12, 8]
                d.a_clean = 3
                d.enema_capacity = 2
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertTrue(dirty.has_semen_flow(1, next_state))
        self.assertEqual(
            dirty.body_semen_amount(1, 8, next_state), Fraction(5, 2)
        )
        self.assertIs(type(dirty.body_semen_amount(1, 8, next_state)), Fraction)
        self.assertEqual(dirty.enema_capacity(1, next_state), 2)
        v = dirty.view(1, next_state)
        self.assertEqual(v.absorbed_total_semen, Fraction(7, 4))
        self.assertIs(type(v.absorbed_total_semen), Fraction)
        self.assertEqual(
            v.semen_flow[0]["targets"][0]["remaining_volume"], Fraction(3, 2)
        )
        self.assertEqual(v.condom_decoration, {(0, 0): [12, 8]})

    def test_reset_vs_clear(self) -> None:
        """reset 保留累计与吸收/流通并清当前量与装饰；clear 全部清空"""
        with working.based_on(core.state()):
            with dirty.editing(1) as d:
                d.body_semen[2][1] = 15
                d.body_semen[2][2] = 2
                d.body_semen[2][3] = 30
                d.absorbed_total_semen = 12
                d.a_clean = 1
                d.enema_capacity = 3
                d.condom_decoration[(1, 10)] = [5]
                d.penis_dirty_dict["semen"] = True
            dirty.reset(1)
            after_reset = dirty.view(1)
            changed = dirty.clear(1)
            after_clear = dirty.view(1)
        self.assertTrue(changed)
        self.assertEqual(after_reset.body_semen[2][1], 0)
        self.assertEqual(after_reset.body_semen[2][2], 0)
        self.assertEqual(after_reset.body_semen[2][3], 30)
        self.assertEqual(after_reset.absorbed_total_semen, 12)
        self.assertEqual(after_reset.a_clean, 0)
        self.assertEqual(after_reset.enema_capacity, 0)
        self.assertEqual(after_reset.condom_decoration, {})
        self.assertEqual(after_reset.penis_dirty_dict, {"semen": False})
        self.assertEqual(after_clear.body_semen[2][3], 0)
        self.assertEqual(after_clear.absorbed_total_semen, 0)
        self.assertEqual(after_clear.penis_dirty_dict, {})

    def test_adopt_old_save_exact_and_unshared_and_short(self) -> None:
        """旧档 float 转 Fraction、共用衣柜表独立保存、缺键服装表重置为 0"""
        all_types = sorted(game_config.config_clothing_type)
        c1 = LegacyObject()
        d1 = game_type.DIRTY()
        d1.body_semen = {
            p: [game_config.config_body_part[p].name, 0, 0, 0]
            for p in game_config.config_body_part
        }
        d1.body_semen[0][1] = 1.5
        vars(d1)["absorbed_total_semen"] = 3.5
        d1.semen_flow = [
            {
                "source": {"type": 0, "id": 0},
                "targets": [{"type": 0, "id": 1, "remaining_volume": 2.25}],
            }
        ]
        d1.cloth_semen = {
            t: [game_config.config_clothing_type[t].name, 0, 0, 0]
            for t in all_types
        }
        d1.cloth_semen[10][1] = 20
        d1.cloth_semen[10][3] = 20
        d1.cloth_locker_semen = d1.cloth_semen  # 整表别名
        vars(c1)["dirty"] = d1

        c2 = LegacyObject()
        d2 = game_type.DIRTY()
        d2.cloth_semen = {
            t: [game_config.config_clothing_type[t].name, 5, 1, 5]
            for t in all_types[:-1]
        }
        d2.cloth_locker_semen = dict(d2.cloth_semen)
        vars(c2)["dirty"] = d2

        with working.based_on(core.state()) as buf:
            dirty.adopt_old_save({"character_data": {1: c1, 2: c2}})
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertFalse(hasattr(c1, "dirty"))
        self.assertFalse(hasattr(c2, "dirty"))
        v1 = dirty.view(1, next_state)
        self.assertEqual(v1.body_semen[0][1], Fraction(3, 2))
        self.assertIs(type(v1.body_semen[0][1]), Fraction)
        self.assertEqual(v1.absorbed_total_semen, Fraction(7, 2))
        self.assertEqual(
            v1.semen_flow[0]["targets"][0]["remaining_volume"], Fraction(9, 4)
        )
        self.assertEqual(v1.cloth_semen[10][1], 20)
        self.assertEqual(v1.cloth_locker_semen[10][1], 20)
        self.assertIsNot(v1.cloth_semen, v1.cloth_locker_semen)
        self.assertIsNot(v1.cloth_semen[10], v1.cloth_locker_semen[10])
        v2 = dirty.view(2, next_state)
        self.assertEqual(v2.cloth_semen[all_types[0]][1], 0)
        self.assertEqual(v2.cloth_locker_semen[all_types[0]][1], 0)
        self.assertEqual(len(v2.cloth_locker_semen), len(all_types))

    def test_adopt_old_save_preserves_player_partial_cloth_tables(self) -> None:
        """旧档玩家无模板时保留缺键服装表中的合法条目并补齐缺失槽位，空衣柜保持空表"""
        all_types = sorted(game_config.config_clothing_type)
        slot = all_types[0]
        slot_name = game_config.config_clothing_type[slot].name
        c0 = LegacyObject()
        d0 = game_type.DIRTY()
        d0.cloth_semen = {
            slot: [slot_name, 12, 1, 12],
            9999: ["无效", 3, 1, 3],
        }
        d0.cloth_locker_semen = {slot: [slot_name, 8, 1, 8]}
        vars(c0)["dirty"] = d0
        with working.based_on(core.state()) as buf:
            dirty.adopt_old_save({"character_data": {0: c0}})
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        v0 = dirty.view(0, next_state)
        self.assertEqual(len(v0.cloth_semen), len(all_types))
        self.assertEqual(v0.cloth_semen[slot][1], 12)
        self.assertEqual(v0.cloth_semen[all_types[-1]][1], 0)
        self.assertNotIn(9999, v0.cloth_semen)
        self.assertEqual(len(v0.cloth_locker_semen), len(all_types))
        self.assertEqual(v0.cloth_locker_semen[slot][1], 8)
        self.assertEqual(v0.cloth_locker_semen[all_types[-1]][1], 0)

        c0_empty = LegacyObject()
        d0_empty = game_type.DIRTY()
        d0_empty.cloth_semen = {slot: [slot_name, 4, 1, 4]}
        d0_empty.cloth_locker_semen = {}
        vars(c0_empty)["dirty"] = d0_empty
        with working.based_on(core.state()) as buf2:
            dirty.adopt_old_save({"character_data": {0: c0_empty}})
            effects2 = buf2.effects()
        next_state2 = core.preview(core.state(), effects2)
        v0_empty = dirty.view(0, next_state2)
        self.assertEqual(v0_empty.cloth_semen[slot][1], 4)
        self.assertEqual(v0_empty.cloth_locker_semen, {})

    def test_shower_reset_keeps_exact_fraction(self) -> None:
        """洗澡按比例保留精液时使用精确 Fraction，不产生 float"""
        now = game_time.now()
        with (
            working.based_on(core.state()) as buf,
            mock.patch.object(
                handle_premise,
                "handle_ask_not_wash_semen",
                return_value=False,
            ),
            mock.patch.object(
                handle_premise,
                "handle_ask_not_wash_cloth",
                return_value=False,
            ),
        ):
            with dirty.editing(1) as d:
                d.body_semen[6][1] = 33
                d.body_semen[6][3] = 33
                d.body_semen[7][1] = 21
                d.body_semen[7][3] = 21
                d.body_semen[8][1] = 25
                d.body_semen[8][3] = 25
                d.body_semen[15][1] = 17
                d.body_semen[15][3] = 17
            settle_default.handle_dirty_reset_in_shower(
                1, 5, game_type.CharacterStatusChange(), now
            )
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        v = dirty.view(1, next_state)
        self.assertEqual(v.body_semen[6][1], Fraction(33, 5))
        self.assertEqual(v.body_semen[7][1], Fraction(147, 10))
        self.assertEqual(v.body_semen[8][1], Fraction(15, 2))
        self.assertEqual(v.body_semen[15][1], 17)
        for part_id in (6, 7, 8, 15):
            self.assertNotIsInstance(v.body_semen[part_id][1], float)

    def test_clear_inside_editing_persists(self) -> None:
        """editing 块内调用 clear 后继续修改，清空与后续修改一起持久化"""
        with working.based_on(core.state()) as buf:
            dirty.set(1, a_clean=3, enema_capacity=4)
            with dirty.editing(1) as d:
                self.assertTrue(dirty.clear(1))
                self.assertEqual(d.a_clean, 0)
                self.assertEqual(d.enema_capacity, 0)
                d.a_clean = 2
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertEqual(dirty.get(1, "a_clean", next_state), 2)
        self.assertEqual(dirty.get(1, "enema_capacity", next_state), 0)

    def test_every_dirty_field_roundtrips(self) -> None:
        """DIRTY 类的每一个字段都被 _encode/_decode 覆盖并在编辑提交后保留"""
        expected_fields = {
            "a_clean",
            "absorbed_total_semen",
            "body_semen",
            "body_semen_in_unconscious",
            "cloth_locker_semen",
            "cloth_semen",
            "cloth_semen_in_unconscious",
            "condom_decoration",
            "enema_capacity",
            "penis_dirty_dict",
            "semen_flow",
        }
        self.assertEqual(set(vars(game_type.DIRTY())), expected_fields)
        all_types = sorted(game_config.config_clothing_type)
        with working.based_on(core.state()) as buf:
            with dirty.editing(1) as d:
                d.a_clean = 2
                d.enema_capacity = 3
                d.absorbed_total_semen = Fraction(5, 2)
                d.body_semen[0][1] = Fraction(3, 2)
                d.body_semen[0][3] = 5
                d.body_semen_in_unconscious = [0]
                d.cloth_semen[all_types[0]][1] = 6
                d.cloth_semen[all_types[0]][3] = 6
                d.cloth_locker_semen = {
                    t: [game_config.config_clothing_type[t].name, 0, 0, 0]
                    for t in all_types
                }
                d.cloth_locker_semen[all_types[0]][1] = 4
                d.cloth_locker_semen[all_types[0]][3] = 4
                d.cloth_semen_in_unconscious = [all_types[0]]
                d.condom_decoration[(0, 0)] = [7]
                d.penis_dirty_dict["semen"] = True
                d.semen_flow = [
                    {
                        "source": {"type": 0, "id": 6},
                        "targets": [
                            {"type": 0, "id": 10, "remaining_volume": 2}
                        ],
                    }
                ]
            effects = buf.effects()
        v = dirty.view(1, core.preview(core.state(), effects))
        self.assertEqual(v.a_clean, 2)
        self.assertEqual(v.enema_capacity, 3)
        self.assertEqual(v.absorbed_total_semen, Fraction(5, 2))
        self.assertEqual(v.body_semen[0][1], Fraction(3, 2))
        self.assertEqual(v.body_semen_in_unconscious, [0])
        self.assertEqual(v.cloth_semen[all_types[0]][1], 6)
        self.assertEqual(v.cloth_locker_semen[all_types[0]][1], 4)
        self.assertEqual(v.cloth_semen_in_unconscious, [all_types[0]])
        self.assertEqual(v.condom_decoration, {(0, 0): [7]})
        self.assertEqual(v.penis_dirty_dict, {"semen": True})
        self.assertEqual(len(v.semen_flow), 1)
