# -*- coding: UTF-8 -*-
"""
角色的能力、经验、宝珠与素质表在内核状态里的读写
================================================
abilities.Table 的读写与同内容的 dict 相同。不在一步、玩家选择或缓冲区里写时报 RuntimeError。
不在花名册里的角色的表存在 roster.offstage 里，上了花名册后存在角色数据里。
旧存档角色对象上的四张表搬进内核状态，素质表去掉 Talent.csv 里没有的 6 与 7。
copy_tables 整张抄表，clear 换成空表，carry 交回的表经 carried 读回。
"""

from collections.abc import Mapping
from types import SimpleNamespace

from Script.Kernel import core
from Script.Modules.domains import abilities
from Script.Modules.gameplay_resolution import working
from tests import kernel_data
from tests.fast.base import FastTestCase

NPC = 7
""" 测试用干员的角色id """


class TableTest(FastTestCase):
    """Table 的读写与同内容的 dict 相同，缓冲区之外的写入报错，表跟着角色存放"""

    def setUp(self) -> None:
        """玩家与一名干员，干员的能力表为 {1: 0, 2: 3}"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        with kernel_data.writing():
            abilities.ability(NPC).replace({1: 0, 2: 3})

    def test_reads_and_writes_match_a_dict(self) -> None:
        """
        对 Table 与 dict 做同一串 +=、setdefault、赋值与删除后，两者的内容、顺序、len、get 与 in 相同，
        缺键取值与删除报 KeyError。with 块结束后内核状态里的表与 dict 相同
        """
        expected = {1: 0, 2: 3}
        with kernel_data.writing():
            table = abilities.ability(NPC)
            for one in (table, expected):
                one[2] += 4
                one.setdefault(9, 5)
                one.setdefault(1, 8)
                one[3] = 1
                del one[1]
            self.assertEqual(table.copy(), expected)
            self.assertEqual(list(table), list(expected))
            self.assertEqual(len(table), len(expected))
            self.assertEqual(table.get(4, -1), expected.get(4, -1))
            self.assertIn(9, table)
            self.assertNotIn(1, table)
            with self.assertRaises(KeyError):
                table[1]
            with self.assertRaises(KeyError):
                del table[1]
        self.assertEqual(abilities.ability(NPC).copy(), expected)

    def test_merge_keeps_order_and_replace_swaps_whole(self) -> None:
        """merge 改已有项并把新项加在表尾，replace 换掉整张表"""
        with kernel_data.writing():
            abilities.ability(NPC).merge({5: 1, 2: 0})
        self.assertEqual(
            list(abilities.ability(NPC).items()), [(1, 0), (2, 0), (5, 1)]
        )
        with kernel_data.writing():
            abilities.ability(NPC).replace({4: 4})
        self.assertEqual(abilities.ability(NPC).copy(), {4: 4})

    def test_write_outside_a_step_raises(self) -> None:
        """不在一步、玩家选择或缓冲区里写能力表报 RuntimeError，这张表不变"""
        with self.assertRaises(RuntimeError):
            abilities.ability(NPC)[1] = 1
        self.assertEqual(abilities.ability(NPC).copy(), {1: 0, 2: 3})

    def test_absent_table_reads_empty(self) -> None:
        """没写过表的角色读到空表，取值报 KeyError"""
        self.assertEqual(abilities.juel(NPC + 1).copy(), {})
        with self.assertRaises(KeyError):
            abilities.juel(NPC + 1)[0]

    def test_table_lives_with_the_character(self) -> None:
        """
        不在花名册里的角色的表存在 roster.offstage 里。
        角色上了花名册后，表存在角色数据里，键为编号的字符串，读到的表不变
        """
        offstage = core.value(core.state(), None, working.OFFSTAGE)
        assert isinstance(offstage, Mapping)
        tables = offstage[str(NPC)]
        assert isinstance(tables, Mapping)
        self.assertEqual(tables[abilities.ABILITY], {"1": 0, "2": 3})
        game = core.state()
        joined = core.GameState(
            game.clock,
            {
                str(NPC): core.Character(
                    core.Action(str(NPC), core.idle.name, None, game.clock, 1),
                    {},
                )
            },
            game.data,
        )
        core.reset_state(working.reconcile(joined))
        held = core.state().characters[str(NPC)].data
        self.assertEqual(held[abilities.ABILITY], {"1": 0, "2": 3})
        self.assertEqual(abilities.ability(NPC).copy(), {1: 0, 2: 3})


class FoldTest(FastTestCase):
    """fold 的三种操作"""

    def test_ops(self) -> None:
        """set 改已有项并加新项，drop 去掉项，replace 换成整张表，三者都不改原表。别的操作名报 ValueError"""
        old = {"1": 0, "2": 3}
        self.assertEqual(
            abilities.fold(old, "set", {"2": 5, "4": 1}),
            {"1": 0, "2": 5, "4": 1},
        )
        self.assertEqual(abilities.fold(old, "drop", ("1",)), {"2": 3})
        self.assertEqual(abilities.fold(old, "replace", {"9": 9}), {"9": 9})
        self.assertEqual(old, {"1": 0, "2": 3})
        with self.assertRaises(ValueError):
            abilities.fold(old, "add", {})


class OldSaveTest(FastTestCase):
    """adopt_old_save 搬表，copy_tables、clear、carry 与 carried 读写内核状态里的表"""

    def test_adopt_moves_tables_and_drops_gone_talents(self) -> None:
        """
        带着四个属性的角色对象交出它们，表按角色id写进内核状态，素质表去掉 6 与 7，交回去掉的项数 2。
        不带这些属性的角色对象不变，它的素质表读到空表
        """
        old = SimpleNamespace(
            ability={1: 2},
            experience={3: 4},
            juel={5: 6},
            talent={6: 1, 7: 0, 8: 1},
        )
        new = SimpleNamespace(name="新角色")
        loaded = {"character_data": {NPC: old, NPC + 1: new}}
        with kernel_data.writing():
            dropped = abilities.adopt_old_save(loaded)
        self.assertEqual(dropped, 2)
        self.assertEqual(vars(old), {})
        self.assertEqual(vars(new), {"name": "新角色"})
        self.assertEqual(abilities.ability(NPC).copy(), {1: 2})
        self.assertEqual(abilities.experience(NPC).copy(), {3: 4})
        self.assertEqual(abilities.juel(NPC).copy(), {5: 6})
        self.assertEqual(abilities.talent(NPC).copy(), {8: 1})
        self.assertEqual(abilities.talent(NPC + 1).copy(), {})

    def test_copy_clear_and_carry(self) -> None:
        """
        copy_tables 把整张表抄给另一个角色。carry 交回的表经 carried 按 int 编号读回，没有的角色读到空表。
        clear 把四张表换成空表
        """
        with kernel_data.writing():
            abilities.talent(NPC).replace({1: 1})
            abilities.experience(NPC).replace({2: 30})
            abilities.copy_tables(NPC, NPC + 1)
        self.assertEqual(abilities.talent(NPC + 1).copy(), {1: 1})
        self.assertEqual(abilities.experience(NPC + 1).copy(), {2: 30})
        carried = abilities.carry([NPC, 0], core.state())
        self.assertEqual(abilities.carried(carried, NPC, "experience"), {2: 30})
        self.assertEqual(abilities.carried(carried, 99, "ability"), {})
        with kernel_data.writing():
            abilities.clear(NPC)
        for name in abilities.PICKLED:
            self.assertEqual(
                abilities.Table(NPC, abilities.PICKLED[name]).copy(), {}
            )
