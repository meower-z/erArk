# -*- coding: UTF-8 -*-
"""
角色键 social.*、life.*、profile.* 的读写、读档导入与快照投影
=============================================================
- 写进再读出，值与各层类型不变（int 键的表、列表、集合、借书历史里的游戏时间）。
  不在花名册里的角色，写下的键存进 roster.offstage。改读出的值不改存下的值。没有这一项时读到默认值。
- 值与类型都与当前值相同时不写。editing() 块正常结束时写回，块里抛错时不写。
  set_item() 只换一项。reset() 只把一名角色的键换回默认值。
  不在花名册里的角色，只改值类型的写入（3 换成 3.0）也提交进 GameState。
- 读档导入：旧存档的角色对象带着这些属性时，值写进 GameState。
  这些属性与 collection_character 从对象上删掉。对象上没有这些属性时什么也不写。
- 读档补全设置与助理服务时，值写在给出的角色id下，不用对象上的 cid。
- lift：角色对象上没有这些属性时，角色键的值按旧属性路径写到对象上。对象带着这些属性时不动。
- 读档修正角色编号：fix_wrong_character 移动角色前调 lift，随后的 adopt_old_save 把角色键写到新槽位，原槽位重置。
- 读档补空白模板：update_tem_character 补 Mother_id 时，带 favorability 且无 relationship 保持 0，两者均无时读角色键。
- 读档的 Reset：project 给花名册角色新建空数据之后，修补步骤读到的角色键是装存档时写下的值。
- 快照的角色投影记下这些键，不记 nick_name 与 nick_name_to_pl。
"""

import types
from types import MappingProxyType
from collections.abc import Mapping
from typing import Any, cast
from unittest import mock

from Script.Config import game_config
from Script.Core import game_type, old_chara_to_new, save_handle
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import (
    chara_key,
    chara_life,
    chara_profile,
    identity,
)
from Script.Modules.domains import relations
from Script.Modules import load_order
from Script.Modules.gameplay_resolution import actions, working
from tests import chara_key_projection, kernel_data
from tests.fast.base import FastTestCase


def typed(value: object) -> object:
    """
    值连同各层的类型，用来比较值与类型都相同
    Keyword arguments:
    value -- 值
    Return arguments:
    object -- 各层换成 (类型名, 内容)
    """
    if isinstance(value, dict):
        items = [(typed(k), typed(v)) for k, v in value.items()]
        return "dict", items
    if isinstance(value, (list, set)):
        inner = [typed(x) for x in value]
        return type(value).__name__, (
            inner if isinstance(value, list) else sorted(inner, key=repr)
        )
    return type(value).__name__, value


class Interrupt(Exception):
    """editing() 块里抛出的错"""


class CharaKeysStateTest(FastTestCase):
    """角色键的读写、读档导入与快照投影"""

    def setUp(self) -> None:
        """GameState 的读写记在 working.based_on(core.state()) 开的缓冲区里"""
        super().setUp()
        self.enterContext(working.based_on(core.state()))

    def test_round_trip_keeps_types(self) -> None:
        """写进再读出，值与各层类型不变"""
        when = game_time.now()
        record = {"book_id": 7, "borrow_time": when, "return_time": None}
        values: list[tuple[chara_key.CharaKey[Any], object]] = [
            (relations.favorability, {0: 5, 3: 2}),
            (relations.trust, 12.5),
            (relations.assistant_services, {1: 2, 4: 0}),
            (relations.child_id_list, [3, 4]),
            (chara_profile.chara_setting, {1: 1}),
            (chara_profile.author_flag, {2: 7}),
            (chara_profile.nick_name, "甲"),
            (chara_life.officeroom, ["中枢", "办公室"]),
            (chara_life.entertainment_type, [1, 2, 3]),
            (chara_life.borrow_book_id_set, {5, 2}),
            (chara_life.read_book_progress, {5: 40}),
            (chara_life.borrow_book_history, [record]),
        ]
        for key, value in values:
            key.set(1, value)
        for key, value in values:
            with self.subTest(key=key.key):
                self.assertEqual(typed(key(1)), typed(value))

    def test_reads_are_fresh_values(self) -> None:
        """改读到的值不影响存下的值"""
        relations.favorability.set(1, {0: 5})
        relations.favorability(1)[0] = 9
        relations.child_id_list(1).append(4)
        self.assertEqual(relations.favorability(1), {0: 5})
        self.assertEqual(relations.child_id_list(1), [])

    def test_defaults(self) -> None:
        """没有这一项时读到默认值"""
        self.assertEqual(relations.favorability(1), {})
        self.assertEqual(relations.mother_id(1), -1)
        self.assertEqual(chara_life.entertainment_type(1), [0, 0, 0])
        self.assertEqual(chara_life.borrow_book_id_set(1), set())
        self.assertEqual(chara_profile.nick_name(1), "")

    def test_same_value_not_written(self) -> None:
        """值与类型都相同时不写，类型不同时写"""
        relations.trust.set(1, 3)
        with mock.patch.object(working, "put", wraps=working.put) as put:
            relations.trust.set(1, 3)
            chara_life.borrow_book_id_set.set(1, set())
            self.assertEqual(put.call_count, 0)
            relations.trust.set(1, 3.0)
            self.assertEqual(put.call_count, 1)
        self.assertIs(type(relations.trust(1)), float)

    def test_editing(self) -> None:
        """editing() 块正常结束时写回，块里出错时不写"""
        with chara_life.borrow_book_id_set.editing(1) as books:
            books.add(5)
        self.assertEqual(chara_life.borrow_book_id_set(1), {5})
        with self.assertRaises(Interrupt):
            with chara_life.borrow_book_id_set.editing(1) as books:
                books.add(6)
                raise Interrupt
        self.assertEqual(chara_life.borrow_book_id_set(1), {5})

    def test_set_item(self) -> None:
        """set_item() 只换一项"""
        relations.favorability.set(1, {0: 5, 3: 2})
        relations.favorability.set_item(1, 3, 4)
        chara_life.entertainment_type.set_item(1, 1, 9)
        self.assertEqual(relations.favorability(1), {0: 5, 3: 4})
        self.assertEqual(chara_life.entertainment_type(1), [0, 9, 0])

    def test_reset(self) -> None:
        """reset() 只把这名角色的键换回默认值"""
        relations.trust.set(1, 8)
        chara_profile.nick_name.set(1, "甲")
        relations.trust.set(2, 8)
        chara_key.reset(1)
        self.assertEqual(relations.trust(1), 0)
        self.assertEqual(chara_profile.nick_name(1), "")
        self.assertEqual(relations.trust(2), 8)

    def test_off_roster_character_parks_in_offstage(self) -> None:
        """不在花名册里的角色，写下的键存进 roster.offstage"""
        with kernel_data.writing():
            relations.trust.set(1, 8)
            chara_life.borrow_book_id_set.set(1, {5})
        offstage = cast(
            Mapping[str, Mapping[str, core.JSON]],
            core.value(core.state(), None, working.OFFSTAGE),
        )
        self.assertNotIn("1", core.state().characters)
        self.assertEqual(offstage["1"]["social.trust"], 8)
        self.assertEqual(offstage["1"]["life.borrow_book_id_set"], (5,))
        self.assertEqual(relations.trust(1, core.state()), 8)

    def test_off_roster_type_only_change_is_kept(self) -> None:
        """不在花名册里的角色，只改值类型的写入（3 换成 3.0）也提交进 GameState"""
        with kernel_data.writing():
            relations.trust.set(1, 3)
        with kernel_data.writing():
            relations.trust.set(1, 3.0)
        self.assertNotIn("1", core.state().characters)
        self.assertIs(type(relations.trust(1, core.state())), float)

    def test_config_fill_writes_under_given_id(self) -> None:
        """补全设置与助理服务时写在给出的角色id下，不用对象上的 cid"""
        old_chara_to_new.update_character_config_data(identity.Identity(7), 6)
        self.assertEqual(
            set(chara_profile.chara_setting(6)),
            set(game_config.config_chara_setting),
        )
        self.assertEqual(
            set(relations.assistant_services(6)),
            set(game_config.config_assistant_services),
        )
        self.assertEqual(chara_profile.chara_setting(7), {})
        self.assertEqual(relations.assistant_services(7), {})

    def test_old_character_moves_into_state(self) -> None:
        """旧存档的角色对象：值写进 GameState，属性从对象上删掉"""
        relationship = game_type.RELATIONSHIP()
        relationship.mother_id = 2
        relationship.nation = 3
        work = game_type.CHARA_WORK()
        work.work_type = 21
        entertainment = game_type.CHARA_ENTERTAINMENT()
        entertainment.borrow_book_id_set = {5}
        flags = game_type.AUTHOR_FLAG()
        flags.chara_int_flag_dict = {1: 6}
        flags.chara_str_flag_dict = {1: "甲"}
        old = types.SimpleNamespace(
            favorability={0: 5},
            trust=12.5,
            relationship=relationship,
            dormitory="中枢\\宿舍",
            work=work,
            entertainment=entertainment,
            nick_name="甲",
            author_flag=flags,
            collection_character={1},
            position=["中枢"],
        )
        loaded = {"character_data": {1: old}}
        relations.adopt_old_save(loaded)
        chara_life.adopt_old_save(loaded)
        chara_profile.adopt_old_save(loaded)
        self.assertEqual(relations.favorability(1), {0: 5})
        self.assertEqual(relations.trust(1), 12.5)
        self.assertEqual(relations.mother_id(1), 2)
        self.assertEqual(relations.nation(1), 3)
        self.assertEqual(chara_life.dormitory(1), "中枢\\宿舍")
        self.assertEqual(chara_life.work_type(1), 21)
        self.assertEqual(chara_life.dormitory_admin_phase(1), 0)
        self.assertEqual(chara_life.borrow_book_id_set(1), {5})
        self.assertEqual(chara_profile.nick_name(1), "甲")
        self.assertEqual(chara_profile.author_flag(1), {1: 6})
        self.assertEqual(vars(old), {"position": ["中枢"]})

    def test_lift_writes_keys_back_onto_current_objects(self) -> None:
        """lift 把角色键的值写到没有旧属性的角色对象上，带着旧属性的对象不动"""
        relations.mother_id.set(1, 2)
        relations.favorability.set(1, {0: 5})
        chara_life.work_type.set(1, 21)
        current = types.SimpleNamespace(position=[])
        old = types.SimpleNamespace(trust=3)
        chara_key.lift({"character_data": {1: current, 2: old}})
        self.assertEqual(current.relationship.mother_id, 2)
        self.assertEqual(current.relationship.nation, 0)
        self.assertEqual(current.favorability, {0: 5})
        self.assertEqual(current.work.work_type, 21)
        self.assertEqual(current.nick_name, "")
        self.assertEqual(vars(old), {"trust": 3})

    def test_id_fix_moves_keys_with_the_character(self) -> None:
        """fix_wrong_character 把角色移到目标槽位后，adopt_old_save 把角色键写到新槽位，原槽位重置"""
        relations.trust.set(1, 8)
        chara_life.work_type.set(1, 21)
        chara_profile.nick_name.set(1, "甲")
        name = old_chara_to_new._("阿玛雅")
        moved = types.SimpleNamespace(cid=1, adv=450, name=name)
        rebuilt = types.SimpleNamespace(cid=1)

        def rebuild(cid: int, *_args: object, **_kwargs: object) -> object:
            chara_key.reset(cid)
            return rebuilt

        loaded: dict[str, Any] = {
            "character_data": {
                1: moved,
                2: types.SimpleNamespace(cid=2, adv=448, name=""),
            },
            "npc_tem_data": {1: object()},
        }
        identity.adopt_old_save(loaded)
        with mock.patch.object(
            old_chara_to_new.character_handle, "init_character", rebuild
        ):
            self.assertEqual(old_chara_to_new.fix_wrong_character(loaded), 1)
        relations.adopt_old_save(loaded)
        chara_life.adopt_old_save(loaded)
        chara_profile.adopt_old_save(loaded)
        self.assertIs(loaded["character_data"][2], moved)
        self.assertEqual(relations.trust(2), 8)
        self.assertEqual(chara_life.work_type(2), 21)
        self.assertEqual(chara_profile.nick_name(2), "甲")
        self.assertEqual(relations.trust(1), 0)

    def test_template_fill_reads_mother_by_save_shape(self) -> None:
        """update_tem_character 补模板：带 favorability 且无 relationship 时保持 Mother_id 为 0，两者都无时读角色键"""
        relations.mother_id.set(6, 3)
        oldest = types.SimpleNamespace(cid=5, adv=905, name="乙", trust=0)
        oldest.favorability = {0: 0}
        current = types.SimpleNamespace(cid=6, adv=906, name="丙")
        loaded: dict[str, Any] = {
            "character_data": {5: oldest, 6: current},
            "npc_tem_data": {},
        }
        identity.adopt_old_save(loaded)
        with (
            mock.patch.dict(
                old_chara_to_new.character_config.character_tem_list, clear=True
            ),
            mock.patch.object(
                old_chara_to_new, "update_new_character", return_value=0
            ),
        ):
            old_chara_to_new.update_tem_character(loaded)
        self.assertEqual(loaded["npc_tem_data"][905].Mother_id, 0)
        self.assertEqual(loaded["npc_tem_data"][906].Mother_id, 3)

    def test_current_character_keeps_state(self) -> None:
        """当前存档的角色对象：什么也不写"""
        relations.trust.set(1, 8)
        game = working.get("1", relations.trust.key)
        loaded = {"character_data": {1: types.SimpleNamespace(position=[])}}
        with mock.patch.object(working, "put", wraps=working.put) as put:
            relations.adopt_old_save(loaded)
            chara_life.adopt_old_save(loaded)
            chara_profile.adopt_old_save(loaded)
        self.assertEqual(put.call_count, 0)
        self.assertEqual(working.get("1", relations.trust.key), game)

    def test_projection_leaves_out_nick_names(self) -> None:
        """角色投影记下这些键，不记 nick_name 与 nick_name_to_pl"""
        self.world.chara(0, "博士")
        self.world.chara(1, "干员")
        relations.favorability.set(1, {0: 5})
        chara_profile.nick_name.set(1, "甲")
        chara_profile.nick_name_to_pl.set(1, "乙")
        state: dict[str, object] = {}
        chara_key_projection.project(self.cache, state)
        self.assertEqual(state["chara.1.favorability.0"], 5)
        self.assertEqual(state["chara.1.relationship.mother_id"], -1)
        self.assertFalse([name for name in state if "nick_name" in name])


class LoadStepsTest(FastTestCase):
    """读档的 Reset 步骤里，修补步骤读到的角色键"""

    def test_repair_reads_adopted_values_after_projection(self) -> None:
        """project 给花名册角色新建空数据之后，读档修补读到装存档时写下的值"""
        self.world.chara(0, "博士")
        self.world.chara(1, "干员")
        seen: list[float] = []

        def install(*args: object) -> None:
            relations.trust.set(1, 8)

        def project(new: core.GameState) -> core.GameState:
            act = core.Action("1", core.idle.name, None, new.clock, 1)
            characters = {"1": core.Character(act, MappingProxyType({}))}
            return core.GameState(
                new.clock, MappingProxyType(characters), new.data
            )

        for module, name, fn in (
            (save_handle, "install_save", install),
            (save_handle, "exact_stats", lambda: None),
            (
                save_handle,
                "repair_installed",
                lambda: seen.append(relations.trust(1)),
            ),
            (actions, "project", project),
        ):
            self.enterContext(mock.patch.object(module, name, fn))
        core.load(load_order.LOAD_ORDER)
        empty = core.GameState(
            core.state().clock, MappingProxyType({}), MappingProxyType({})
        )
        core.reset_state(empty, {"cause": "load", "save": "1"})
        self.assertEqual(seen, [8])
        self.assertEqual(relations.trust(1, core.state()), 8)
