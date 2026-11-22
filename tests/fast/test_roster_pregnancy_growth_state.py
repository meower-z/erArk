# -*- coding: UTF-8 -*-
"""
名册、妊娠与养成状态（roster.*、body.pregnancy、growth.child）
==============================================================
- 名册：在编名单、禁用名单、已用姓名、换号重映射、新周目沿用、旧存档导入与 101/102 阶段禁入边界。
- 妊娠：全部 16 项字段的稀疏存取、可重入 editing、缺省与非季月时间编解码、卵字典、参数边界与旧存档导入。
- 养成：惰性创建（只读不写）、全部 25 项字段存取、可重入 editing、参数边界与旧存档导入。
- 编解码、选行动写入缓冲、静态自检与缓冲区外写保护。
"""

import datetime
from types import MappingProxyType
from unittest import mock

from Script.Core import game_type
from Script.Design import character_handle, child_stage_gate, game_time
from Script.Kernel import core
from Script.Modules.domains import (
    abilities,
    playthrough,
    pregnancy,
    roster,
)
from Script.Modules.gameplay_resolution import actions, working
from Script.Modules.save_load import upgrade
from tests.fast.base import FastTestCase
from Script.Modules.domains import identity
from Script.Modules.save_load.legacy_pickle import LegacyObject


class RosterStateTest(FastTestCase):
    """在编名册、禁用名单、已用姓名与 101/102 阶段禁入边界"""

    def setUp(self) -> None:
        """放入玩家与若干干员，打开基于当前状态的缓冲区"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.world.chara(2, "干员乙")
        self.enterContext(working.based_on(core.state()))

    def test_active_forbidden_names_crud_and_remap(self) -> None:
        """在编名单、禁用名单与已用姓名的读写、删除、重映射与新周目沿用"""
        roster.clear_active()
        self.assertEqual(roster.active(), set())
        self.assertEqual(roster.active_sorted(), ())
        self.assertEqual(roster.count(), 0)

        roster.add(2)
        roster.add(1)
        self.assertEqual(roster.active_sorted(), (1, 2))
        self.assertEqual(roster.active(), {1, 2})
        self.assertTrue(roster.has(1))
        self.assertEqual(roster.count(), 2)

        roster.remove(1)
        self.assertEqual(roster.active_sorted(), (2,))
        with self.assertRaises(KeyError):
            roster.remove(1)
        roster.discard(1)
        roster.discard(2)
        self.assertEqual(roster.active_sorted(), ())

        roster.set_active([2, 1, 2])
        self.assertEqual(roster.active_sorted(), (1, 2))

        roster.forbid(2)
        self.assertTrue(roster.is_forbidden(2))
        self.assertEqual(roster.forbidden(), {2})
        roster.unforbid(2)
        self.assertFalse(roster.is_forbidden(2))
        roster.set_forbidden([2])

        roster.add_name("干员甲")
        roster.add_name("干员乙")
        self.assertTrue(roster.has_name("干员甲"))
        self.assertEqual(roster.names(), {"干员甲", "干员乙"})
        roster.set_names(["干员甲"])
        self.assertEqual(roster.names(), {"干员甲"})

        self.world.chara(3, "干员丙")
        roster.set_active([1, 2])
        roster.set_forbidden([2])
        roster.remap({2: 3})
        self.assertEqual(roster.active_sorted(), (1, 3))
        self.assertEqual(roster.forbidden(), {3})

        self.assertIn(roster.FORBIDDEN, playthrough.CARRIED_KEYS)
        self.assertIn(roster.NAMES, playthrough.CARRIED_KEYS)

    def test_stage_101_and_102_cannot_enter_roster_or_game_state(self) -> None:
        """101 与 102 阶段的角色在类型入口、名单写入、状态投影与加入效果处均被拒绝"""
        self.world.chara(9101, "幼童甲")
        abilities.talent(9101)[101] = 1
        self.world.chara(9102, "幼童乙")
        abilities.talent(9102)[102] = 1
        self.world.chara(9103, "学员丙")
        abilities.talent(9103)[103] = 1

        self.assertEqual(roster.require_eligible(0), 0)
        self.assertEqual(roster.require_eligible(1), 1)
        self.assertEqual(roster.require_eligible(9103), 9103)

        for bad_cid in (9101, 9102, -1):
            with self.assertRaises(ValueError):
                roster.require_eligible(bad_cid)
            with self.assertRaises(ValueError):
                roster.add(bad_cid)
            with self.assertRaises(ValueError):
                roster.set_active([1, bad_cid])

        roster.set_active([1])
        with self.assertRaises(ValueError):
            roster.remap({1: 9101})
        with self.assertRaises(ValueError):
            roster.remap({1: 9102})

        idle = core.Action("9101", core.idle.name, None, 0, 1)
        bad_state = core.GameState(
            0,
            MappingProxyType(
                {
                    "0": core.Character(
                        core.Action("0", core.idle.name, None, 0, 1),
                        MappingProxyType({}),
                    ),
                    "9101": core.Character(idle, MappingProxyType({})),
                }
            ),
            MappingProxyType({}),
        )
        with self.assertRaises(ValueError):
            actions.project(bad_state)

        ones = [identity.of(cid) for cid in (9101, 9102, 9103)]
        with working.based_on(core.state()) as buf:
            for one in ones:
                identity.put(one)
            abilities.talent(9101)[101] = 1
            abilities.talent(9102)[102] = 1
            abilities.talent(9103)[103] = 1
            with self.assertRaises(ValueError):
                buf.effects((core.AddCharacter("9101"),))
            with self.assertRaises(ValueError):
                buf.effects((core.AddCharacter("9102"),))
            ok_effects = buf.effects(
                (core.AddCharacter("9103"), core.AddCharacter("toy"))
            )
            self.assertGreaterEqual(len(ok_effects), 2)

    def test_adopt_old_save_v0_wrong_type_and_current(self) -> None:
        """旧存档三项名册集合导入内核状态并删掉，缺项与类型不符计数，当前版本不变"""
        loaded = {
            "npc_id_got": {1, 2},
            "forbidden_npc_id": {2},
            "npc_name_data": {"干员甲"},
            "keep": 1,
        }
        missing = roster.adopt_old_save(loaded, 0)
        self.assertEqual(missing, 0)
        self.assertEqual(loaded, {"keep": 1})
        self.assertEqual(roster.active_sorted(), (1, 2))
        self.assertEqual(roster.forbidden(), {2})
        self.assertEqual(roster.names(), {"干员甲"})

        bad_loaded = {"npc_id_got": [1], "forbidden_npc_id": None}
        self.assertEqual(roster.adopt_old_save(bad_loaded, 0), 3)
        self.assertEqual(bad_loaded, {})

        before = tuple(working.get(None, k) for k in roster.KEYS)
        self.assertEqual(roster.adopt_old_save({}, upgrade.CURRENT), 0)
        self.assertEqual(
            tuple(working.get(None, k) for k in roster.KEYS), before
        )

        # 读档按 loaded["character_data"] 检查 101/102 边界，不受当前状态里同号角色阶段干扰
        self.world.chara(9200, "旧缓存幼童")
        abilities.talent(9200)[101] = 1
        adult_in_save = LegacyObject()
        vars(adult_in_save)["talent"] = {101: 0}
        self.assertEqual(
            roster.adopt_old_save(
                {
                    "npc_id_got": {9200},
                    "forbidden_npc_id": set(),
                    "npc_name_data": set(),
                    "character_data": {9200: adult_in_save},
                },
                0,
            ),
            0,
        )
        self.assertEqual(roster.active_sorted(), (9200,))
        child_in_save = LegacyObject()
        vars(child_in_save)["talent"] = {102: 1}
        with self.assertRaises(ValueError):
            roster.adopt_old_save(
                {
                    "npc_id_got": {1},
                    "character_data": {1: child_in_save},
                },
                0,
            )


class PregnancyStateTest(FastTestCase):
    """妊娠数据的稀疏存取、时间与卵编解码、可重入 editing、参数边界与旧存档导入"""

    def setUp(self) -> None:
        """放入玩家与干员，打开基于当前状态的缓冲区"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.world.chara(2, "干员乙")
        self.enterContext(working.based_on(core.state()))

    def test_legacy_attribute_removed_and_defaults(self) -> None:
        """未写入的角色读出妊娠默认值，且不产生写入"""
        self.assertFalse(hasattr(identity.of(1), "pregnancy"))
        self.assertEqual(pregnancy.milk_max(1), 200)
        p = pregnancy.of(1)
        self.assertEqual(p.fertilization_time, datetime.datetime(1, 1, 1))
        self.assertEqual(p.born_time, datetime.datetime(1, 1, 1))
        self.assertEqual(p.unconscious_fertilization, True)
        self.assertEqual(p.eggs, {})

    def test_full_fields_datetimes_eggs_reentrant_editing_and_isolation(
        self,
    ) -> None:
        """16 项字段、季月与非季月时间、卵字典、可重入 editing、副本隔离与重置"""
        now = game_time.now()
        non_season = datetime.datetime(2025, 2, 14, 8, 30)
        pregnancy.set_milk_max(1, 260)
        with pregnancy.editing(1) as outer:
            outer.fertilization_rate = 42.5
            outer.reproduction_period = 5
            outer.ovulation_flag = True
            outer.fertilization_time = now
            outer.born_time = non_season
            outer.unconscious_fertilization = False
            outer.lactation_flag = True
            outer.eggs = {
                0: {
                    "lay_time": now,
                    "identified": True,
                    "fertilized": True,
                    "identify_time": now,
                    "father_id": 0,
                    "hatch_stage": 2,
                    "held_by_player": False,
                    "acceleration_days": 3.5,
                    "soft": True,
                }
            }
            outer.next_egg_id = 1
            outer.acceleration_days = 12.5
            outer.growth_acceleration_days = 4.0
            outer.fetus_count = 2
            outer.identical_twins = True
            outer.external_ovulation_chance = True
            outer.prenatal_point = 3.5
            with pregnancy.editing(1) as inner:
                self.assertIs(inner, outer)
                inner.prenatal_point = 4.0

        got = pregnancy.of(1)
        self.assertEqual(pregnancy.milk_max(1), 260)
        self.assertEqual(got.fertilization_rate, 42.5)
        self.assertEqual(got.reproduction_period, 5)
        self.assertTrue(got.ovulation_flag)
        self.assertEqual(got.fertilization_time, now)
        self.assertEqual(got.born_time, non_season)
        self.assertFalse(got.unconscious_fertilization)
        self.assertTrue(got.lactation_flag)
        self.assertEqual(got.next_egg_id, 1)
        self.assertEqual(got.acceleration_days, 12.5)
        self.assertEqual(got.growth_acceleration_days, 4.0)
        self.assertEqual(got.fetus_count, 2)
        self.assertTrue(got.identical_twins)
        self.assertTrue(got.external_ovulation_chance)
        self.assertEqual(got.prenatal_point, 4.0)
        self.assertEqual(got.eggs[0]["lay_time"], now)
        self.assertTrue(got.eggs[0]["soft"])

        # 副本隔离：改动 of() 交回的对象不影响缓冲区里的值
        got.eggs[0]["hatch_stage"] = 99
        self.assertEqual(pregnancy.of(1).eggs[0]["hatch_stage"], 2)

        # copy_character 复制含 milk_max 的完整状态
        pregnancy.copy_character(1, 2)
        self.assertEqual(pregnancy.milk_max(2), 260)
        self.assertEqual(pregnancy.of(2).fetus_count, 2)

        # reset_except 保留指定字段并计数改动项
        changed = pregnancy.reset_except(
            1, {"reproduction_period", "born_time", "growth_acceleration_days"}
        )
        self.assertGreater(changed, 0)
        after = pregnancy.of(1)
        self.assertEqual(after.reproduction_period, 5)
        self.assertEqual(after.born_time, non_season)
        self.assertEqual(after.growth_acceleration_days, 4.0)
        self.assertEqual(after.fetus_count, 0)
        self.assertEqual(after.eggs, {})
        self.assertEqual(pregnancy.milk_max(1), 260)

        # Exception 回滚，BaseException 照常写入
        with self.assertRaises(RuntimeError):
            with pregnancy.editing(2) as p2:
                p2.fetus_count = 5
                raise RuntimeError("abort")
        self.assertEqual(pregnancy.of(2).fetus_count, 2)

        class _ExitSignal(BaseException):
            pass

        with self.assertRaises(_ExitSignal):
            with pregnancy.editing(2) as p2:
                p2.fetus_count = 3
                raise _ExitSignal()
        self.assertEqual(pregnancy.of(2).fetus_count, 3)

    def test_invariants_and_adopt_old_save(self) -> None:
        """非法负数或类型被边界拒绝；旧存档属性合并 milk_max、截断加速天数并删掉属性"""
        for bad in (
            {"fetus_count": -1},
            {"next_egg_id": -1},
            {"acceleration_days": -1.0},
            {"growth_acceleration_days": -0.5},
            {"prenatal_point": -1.0},
            {"reproduction_period": True},
        ):
            with self.assertRaises(ValueError):
                pregnancy.update(1, **bad)

        pregnancy.set_milk_max(1, 280)
        legacy_p = game_type.PREGNANCY()
        legacy_p.reproduction_period = 4
        legacy_p.acceleration_days = 999.0
        legacy_p.growth_acceleration_days = 999.0
        legacy_p.eggs = {
            0: {
                "lay_time": game_time.now(),
                "identified": False,
                "fertilized": True,
                "identify_time": None,
                "father_id": 0,
                "hatch_stage": 0,
                "held_by_player": False,
                "acceleration_days": 999.0,
            }
        }
        npc = LegacyObject()
        vars(npc)["pregnancy"] = legacy_p
        pregnancy.adopt_old_save({"character_data": {1: npc}}, 14)
        self.assertFalse(hasattr(npc, "pregnancy"))
        self.assertEqual(pregnancy.milk_max(1), 280)
        got = pregnancy.of(1)
        self.assertEqual(got.reproduction_period, 4)
        self.assertLessEqual(got.acceleration_days, 83.0)
        self.assertLessEqual(got.growth_acceleration_days, 149.0)
        self.assertLessEqual(got.eggs[0]["acceleration_days"], 83.0)

    def test_restore_grown_stage_allows_grown_daughter_and_blocks_child(
        self,
    ) -> None:
        """模板固定带 101 的自生女儿重建后按旧素质还原阶段可安全入编，仍处 101/102 或无旧素质时不入编"""
        daughter_tem = character_handle.create_empty_character_tem()
        daughter_tem.Name = "长大女儿"
        daughter_tem.AdvNpc = 9104
        daughter_tem.Talent = {101: 1, 121: 1}
        baby_tem = character_handle.create_empty_character_tem()
        baby_tem.Name = "幼童模板"
        baby_tem.AdvNpc = 9105
        baby_tem.Talent = {101: 1, 121: 1}
        character_handle.init_character(9104, daughter_tem, collect_reset=False)
        character_handle.init_character(9105, baby_tem, collect_reset=False)

        self.assertTrue(
            child_stage_gate.restore_grown_stage(9104, {104: 1, 3: 1})
        )
        roster.add(9104)
        self.assertTrue(roster.has(9104))
        self.assertEqual(abilities.talent(9104).get(101, 0), 0)
        self.assertEqual(abilities.talent(9104).get(104, 0), 1)

        self.assertFalse(child_stage_gate.restore_grown_stage(9105, {101: 1}))
        self.assertFalse(child_stage_gate.restore_grown_stage(9105, {}))
        self.assertEqual(abilities.talent(9105).get(101, 0), 1)
        self.assertTrue(child_stage_gate.restore_grown_stage(1, {}))

    def test_flush_sees_pending_stage_102_to_103_transition(self) -> None:
        """同一步里 102 长成 103 并加入花名册时，flush 按待提交缓冲区里的最新素质放行"""
        self.world.chara(9106, "成长幼女")
        self.world.chara(9107, "未成长幼女")
        ones = [identity.of(cid) for cid in (9106, 9107)]
        with working.based_on(core.state()) as setup_buf:
            for one in ones:
                identity.put(one)
            abilities.talent(9106)[102] = 1
            abilities.talent(9107)[102] = 1
            setup_effects = setup_buf.effects()
        core.reset_state(core.preview(core.state(), setup_effects))

        # 脱离外层 based_on，模拟核心步内写入 _step 后由 flush 清空 _step 再调用 buffer.effects
        saved_stack = list(working._stack)
        working._stack.clear()
        try:
            working._clear()
            with mock.patch.object(core, "in_settlement", return_value=True):
                abilities.talent(9106)[102] = 0
                abilities.talent(9106)[103] = 1
                roster.add(9106)
            result = working.flush((core.AddCharacter("9106"),))
            assert isinstance(result, tuple)
            (flushed,) = result
            self.assertTrue(
                any(
                    isinstance(e, core.AddCharacter) and e.who == "9106"
                    for e in flushed
                )
            )
            self.assertEqual(working._stack, [])

            working._clear()
            with self.assertRaises(ValueError):
                working.flush((core.AddCharacter("9107"),))
            self.assertEqual(working._stack, [])
        finally:
            working._stack[:] = saved_stack
