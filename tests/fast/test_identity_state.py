# -*- coding: UTF-8 -*-
"""
角色身份表（identity.characters）
================================
- 表按角色建立的先后排列，新角色排在最后，改已有角色时位置不变，删掉的角色不在表里。
- 不在花名册里的角色也读得到身份。角色进出花名册不改动身份表。
- 存档再读档后身份表与顺序不变，读档不改玩家名字。
- 读版本 24 之前的存档时，角色对象上的身份属性搬进身份表并从对象上删掉，缺失或类型不符的项取默认值，
  顺序同存档里的角色表。版本 24 起的存档不含角色对象，读档时按表顺序给每个角色生成空的旧角色对象。
- 读档先导入身份并从旧角色对象移除身份属性，随后的旧平铺 V 处女记录整理按角色表的键区分玩家与干员。
- 角色从身份表删掉后，roster.offstage 里她的数据在 Reset 整理时丢掉。
- 静态检查失败时的快照记下玩家与涉事角色的身份，表里没有的涉事id不记。
"""

import datetime
import tempfile
from collections.abc import Mapping
from typing import Any
from unittest import mock

from Script.Core import game_type, save_handle
from Script.Kernel import core
from Script.Modules.domains import identity, needs, roster
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import index
from Script.Test.Static_Check import snapshot
from tests import kernel_data
from tests.fast.base import FastTestCase
from Script.Modules.save_load.legacy_pickle import LegacyObject

SAVE_ID = "identity_test"
""" 测试用的存档id """


def record(cid: int, name: str, **fields: Any) -> identity.Identity:
    """构造测试用 Identity，默认性别为 1，其余字段取传入值或默认值"""
    return identity.Identity(cid, name=name, sex=1, **fields)


class IdentityTableTest(FastTestCase):
    """身份表的读写、顺序与存在性"""

    def setUp(self) -> None:
        """建立 0 号玩家，再按 30、7、12 的顺序写入三名不在在编名单里的角色身份"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid, name in ((30, "甲"), (7, "乙"), (12, "丙")):
            kernel_data.put(identity.put, record(cid, name, adv=cid))

    def test_creation_order_kept(self) -> None:
        """表按建立的先后排列，不按id排序。改已有角色时位置不变，新角色排在最后"""
        self.assertEqual(identity.ids(), (0, 30, 7, 12))
        kernel_data.put(identity.update, 30, name="甲二", talk_size=4)
        kernel_data.put(identity.put, record(5, "丁"))
        self.assertEqual(identity.ids(), (0, 30, 7, 12, 5))
        self.assertEqual(list(identity.table()), [0, 30, 7, 12, 5])
        self.assertEqual(
            (identity.of(30).name, identity.of(30).talk_size), ("甲二", 4)
        )

    def test_discarded_character_is_gone(self) -> None:
        """删掉的角色不在表里：exists 为 False，of 报 KeyError，get 为 None，其余顺序不变"""
        kernel_data.put(identity.discard, 7)
        self.assertFalse(identity.exists(7))
        self.assertIsNone(identity.get(7))
        with self.assertRaises(KeyError):
            identity.of(7)
        self.assertNotIn(7, identity.table())
        self.assertEqual(identity.ids(), (0, 30, 12))

    def test_off_roster_character_reads(self) -> None:
        """不在花名册里的角色读得到身份。她进出花名册后身份不变，位置也不变"""
        self.assertNotIn(12, roster.active())
        before = identity.of(12)
        self.assertEqual((before.cid, before.name, before.adv), (12, "丙", 12))
        kernel_data.put(roster.add, 12)
        self.assertEqual(identity.of(12), before)
        kernel_data.put(roster.discard, 12)
        self.assertEqual(identity.of(12), before)
        self.assertEqual(identity.ids(), (0, 30, 7, 12))

    def test_unchanged_write_records_nothing(self) -> None:
        """写入与当前值相同的身份时，缓冲区不产生任何写入效果"""
        with working.based_on(core.state()) as buffer:
            identity.put(identity.of(7))
            identity.update(7, name="乙")
            self.assertEqual(buffer.effects(), ())


class IdentitySaveTest(FastTestCase):
    """身份表随存档保存与读回"""

    def setUp(self) -> None:
        """将存档目录切到临时目录，建立 0 号玩家并只在在编名单里登记玩家"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.world.chara(0, "博士")
        kernel_data.put(roster.set_active, {0})

    def test_save_and_load_keep_table(self) -> None:
        """
        存档再读档后，存档时的角色仍按原顺序排在最前，名字、性别、生日、种族与 adv 不变。
        读档前改过的玩家名字恢复为存档时的值
        """
        birthday = datetime.date(1, 3, 14)
        kernel_data.put(
            identity.put,
            record(90040, "戊", birthday=birthday, race=2, adv=90040),
        )
        kernel_data.put(identity.put, record(90009, "己", adv=90009))
        saved = dict(identity.table())
        save_handle.establish_save(SAVE_ID)
        kernel_data.put(identity.update, 0, name="改过的名字")
        save_handle.input_load_save(SAVE_ID)
        self.assertEqual(identity.ids()[:3], (0, 90040, 90009))
        for cid, before in saved.items():
            after = identity.of(cid)
            self.assertEqual(
                (after.name, after.sex, after.birthday, after.race, after.adv),
                (
                    before.name,
                    before.sex,
                    before.birthday,
                    before.race,
                    before.adv,
                ),
            )


class AdoptOldSaveTest(FastTestCase):
    """读档时身份导入与占位表构造"""

    def setUp(self) -> None:
        """打开以当前内核状态为基础的写入缓冲区"""
        super().setUp()
        self.enterContext(working.based_on(core.state()))

    def test_pickled_attributes_move_into_table(self) -> None:
        """
        版本 24 之前的角色对象经 adopt_old_save 导入身份表，身份属性从对象移除，其余属性保留。
        缺失或类型不符的字段取默认值
        """
        first = LegacyObject()
        vars(first).update(
            cid=8,
            name="庚",
            sex=1,
            talk_size=3,
            text_color="red",
            birthday=datetime.datetime(1, 5, 6, 7, 8),
            adv=88,
            profession=2,
            race=4,
            token_text="信物",
            pregnancy="留着",
        )
        second = LegacyObject()
        vars(second).update(name=None, sex="1", talk_size=2.5)
        loaded: dict[str, Any] = {"character_data": {8: first, 3: second}}
        identity.adopt_old_save(loaded)
        self.assertEqual(identity.ids(), (8, 3))
        self.assertEqual(
            identity.of(8),
            identity.Identity(
                8,
                name="庚",
                sex=1,
                talk_size=3,
                text_color="red",
                birthday=datetime.date(1, 5, 6),
                adv=88,
                profession=2,
                race=4,
                token_text="信物",
            ),
        )
        self.assertEqual(identity.of(3), identity.Identity(3))
        self.assertEqual(vars(first), {"pregnancy": "留着"})
        self.assertEqual(vars(second), {})
        self.assertIs(loaded["character_data"][8], first)

    def test_new_save_gets_empty_records(self) -> None:
        """
        版本 24 起的存档不含角色对象，adopt_old_save 保留身份表，
        并按表顺序在 loaded_dict["character_data"] 填入空的旧角色对象
        """
        for cid, name in ((0, "博士"), (21, "辛"), (4, "壬")):
            identity.put(record(cid, name))
        loaded: dict[str, Any] = {}
        identity.adopt_old_save(loaded)
        self.assertEqual(identity.ids(), (0, 21, 4))
        self.assertEqual(list(loaded["character_data"]), [0, 21, 4])
        for chara in loaded["character_data"].values():
            self.assertIsInstance(chara, LegacyObject)
            self.assertEqual(vars(chara), {})


class FirstRecordAfterAdoptTest(FastTestCase):
    """读档导入身份后的旧平铺初次记录整理"""

    def test_npc_flat_first_record_moves_by_key(self) -> None:
        """
        经 adopt_old_save 移除旧角色对象的身份属性后，路径整理按角色表的键区分玩家与干员。
        干员（键 6）的平铺 V 处女记录转入 first_part_sex_dict[6] 并重置 first_sex_id。
        玩家（键 0）的平铺记录保持不变
        """
        characters = {}
        records = {}
        for cid in (0, 6):
            chara = LegacyObject()
            records[cid] = game_type.FIRST_RECORD()
            del records[cid].first_part_sex_dict
            records[cid].first_sex_id = 0
            vars(chara).update(
                cid=cid, name=f"角色{cid}", first_record=records[cid]
            )
            characters[cid] = chara
        loaded: dict[str, Any] = {"character_data": characters}
        with working.based_on(core.state()):
            identity.adopt_old_save(loaded)
            save_handle._normalize_loaded_save_paths(loaded)
        npc, player = records[6], records[0]
        self.assertEqual(
            (npc.first_part_sex_dict[6]["id"], npc.first_sex_id), (0, -1)
        )
        self.assertEqual(
            (6 in player.first_part_sex_dict, player.first_sex_id), (False, 0)
        )


class ReconcileTest(FastTestCase):
    """移除角色后停放数据的清理"""

    def test_parked_data_of_discarded_character_dropped(self) -> None:
        """不在花名册里的两名角色各停放了生理需求。删掉其中一名后，Reset 整理丢掉她的数据并留下另一名的"""
        self.world.chara(0, "博士")
        for cid, name in ((51, "癸"), (52, "子")):
            kernel_data.put(identity.put, record(cid, name))
            kernel_data.put(needs.set, cid, hunger=5)
        kernel_data.put(identity.discard, 51)
        reconciled = working.reconcile(core.state())
        offstage = core.value(reconciled, None, working.OFFSTAGE)
        assert isinstance(offstage, Mapping)
        self.assertNotIn("51", offstage)
        self.assertIn("52", offstage)


class CheckSnapshotTest(FastTestCase):
    """静态检查失败时的快照转储"""

    def test_snapshot_keeps_player_and_involved(self) -> None:
        """传入涉事角色 7 与不存在的 99 时，快照只保留玩家与 7 的身份，并写入已转储角色id说明"""
        self.world.chara(0, "博士")
        for cid, name in ((7, "丑"), (8, "寅")):
            kernel_data.put(identity.put, record(cid, name, adv=cid))
        got = snapshot.build_snapshot({7, 99})
        self.assertEqual(sorted(got[identity.KEY]), ["0", "7"])
        self.assertEqual(got[identity.KEY]["7"]["name"], "丑")
        self.assertIn("[0, 7]", got[f"{identity.KEY}_omitted"])
