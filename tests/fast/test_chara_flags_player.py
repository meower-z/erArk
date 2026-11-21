# -*- coding: UTF-8 -*-
"""
角色标记、行动记录、玩家能力与收藏品的内核键测试
================================================
验证 chara.flags、chara.action_info、player.ability、player.collection 四个角色键：
- 稀疏存储与默认值读写，恢复默认值时从表里删去，无变化写入不产出效果；
- 时间戳公元 1 年占位（year <= 1 -> None -> datetime(1, 1, 1)）与真实游戏时间往返；
- today_sanity_point_cost 保留精确数值类型（int / Fraction）并经文件 "2" 编解码往返；
- 收藏品整数键、元组与体外无壳卵编解码、新周目继承携带；
- 旧存档 adopt_old_save（含忽略 unnormal_flag、float 经 num.exact 转 Fraction、删去旧属性）、copy_to 与 remap；
- choice.Plan.get 与 starts.write_field 对 sp_flag.* / action_info.* 路径的转发；
- events 触发函数按传入的 GameState 读标记与能力；
- Character 不含这四个属性，存档版本为 17 且 STEPS[16] 存在。
"""

import datetime
import json
from fractions import Fraction
from unittest import mock

from Script.Core import game_type, get_text, old_chara_to_new
from Script.Design import character_handle, game_time
from Script.Kernel import core
from Script.Modules.domains import action_info, flags, player_ability
from Script.Modules.domains import player_collection
from Script.Modules.gameplay_resolution import events, starts, working
from Script.Modules.npc_action_choice import choice
from Script.Modules.save_load import kernel_state, upgrade
from tests import kernel_data
from tests.fast.base import FastTestCase


class CharaFlagsPlayerTest(FastTestCase):
    """chara.flags / chara.action_info / player.ability / player.collection 单元测试"""

    def setUp(self) -> None:
        """建立包含玩家与两名成年干员的轻量世界"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.op_a = self.world.chara(1, "干员甲")
        self.op_b = self.world.chara(2, "干员乙")

    def test_character_has_no_legacy_attrs_and_version_17(self) -> None:
        """Character 实例不含四个角色键对应的旧属性，存档版本为 17"""
        fresh = game_type.Character()
        for attr in ("sp_flag", "action_info", "pl_ability", "pl_collection"):
            self.assertFalse(hasattr(fresh, attr), attr)
        self.assertEqual(upgrade.CURRENT, 17)
        self.assertIn(16, upgrade.STEPS)

    def test_flags_sparse_coerce_reset_copy_remap_adopt(self) -> None:
        """chara.flags：稀疏读写、类型规整、reset、copy_to、remap 与 adopt_old_save"""
        self.assertFalse(flags.get(1, "is_h"))
        self.assertEqual(flags.get(1, "is_follow"), 0)
        self.assertEqual(working.get("1", flags.KEY), {})

        with working.based_on(core.state()) as buf:
            flags.set(1, is_h=False, is_follow=0)
            self.assertEqual(buf.effects(), ())

        kernel_data.put(
            flags.set, 1, is_h=1, field_commission=True, bagging_chara_id=2
        )
        self.assertIs(flags.get(1, "is_h"), True)
        self.assertIs(type(flags.get(1, "field_commission")), int)
        self.assertEqual(flags.get(1, "field_commission"), 1)
        stored = working.get("1", flags.KEY)
        self.assertEqual(
            stored, {"is_h": True, "field_commission": 1, "bagging_chara_id": 2}
        )

        kernel_data.put(flags.copy_to, 1, 2)
        self.assertTrue(flags.get(2, "is_h"))
        kernel_data.put(flags.remap, (1, 2), {2: 99})
        self.assertEqual(flags.get(1, "bagging_chara_id"), 99)

        kernel_data.put(
            flags.set, 1, is_h=False, field_commission=0, bagging_chara_id=0
        )
        self.assertEqual(working.get("1", flags.KEY), {})

        kernel_data.put(flags.reset, 2)
        self.assertFalse(flags.get(2, "is_h"))
        with self.assertRaises(KeyError):
            flags.get(1, "no_such_flag")

        legacy = game_type.Character()
        sp = game_type.SPECIAL_FLAG()
        sp.tired = True
        sp.vistor = 2
        vars(legacy)["sp_flag"] = sp
        kernel_data.put(flags.adopt_old_save, {"character_data": {1: legacy}})
        self.assertFalse(hasattr(legacy, "sp_flag"))
        self.assertTrue(flags.get(1, "tired"))
        self.assertEqual(flags.get(1, "vistor"), 2)
        self.assertNotIn("unnormal_flag", flags.snapshot(1))

    def test_action_info_timestamps_lists_remap_adopt(self) -> None:
        """chara.action_info：占位时间与真实时间、移动历史、社交时间、init_zero、remap 与 adopt"""
        self.assertEqual(
            action_info.get(1, "talk_time"), datetime.datetime(1, 1, 1)
        )
        self.assertEqual(action_info.get(1, "plan_to_wake_time"), [6, 0])
        self.assertTrue(action_info.get(1, "day_first_shoot_semen"))

        now = game_time.now()
        kernel_data.put(action_info.set, 1, "talk_time", now)
        self.assertEqual(action_info.get(1, "talk_time"), now)
        kernel_data.put(
            action_info.set, 1, "talk_time", datetime.datetime(1, 1, 1)
        )
        self.assertEqual(
            action_info.get(1, "talk_time"), datetime.datetime(1, 1, 1)
        )
        self.assertEqual(working.get("1", action_info.KEY), {})

        kernel_data.put(action_info.add, 1, "talk_count", 3)
        self.assertEqual(action_info.get(1, "talk_count"), 3)
        kernel_data.put(action_info.set_plan_time, 1, "plan_to_wake_time", 0, 7)
        self.assertEqual(action_info.get(1, "plan_to_wake_time"), [7, 0])

        for i in range(12):
            kernel_data.put(action_info.record_move, 1, ["中枢", f"房间{i}"])
        kernel_data.put(action_info.record_move, 1, ["中枢", "房间11"])
        moves = action_info.get(1, "past_move_position_list")
        self.assertEqual(len(moves), 10)
        self.assertEqual(moves[0], ["中枢", "房间2"])
        self.assertEqual(moves[-1], ["中枢", "房间11"])
        popped = kernel_data.written(action_info.pop_past_move, 1)
        self.assertEqual(popped, ["中枢", "房间11"])
        self.assertEqual(len(action_info.get(1, "past_move_position_list")), 9)

        kernel_data.put(
            action_info.set, 1, "social_contact_last_time", {2: now}
        )
        with working.based_on(core.state()) as buf:
            action_info.set(1, "social_contact_last_time", {2: now})
            self.assertEqual(buf.effects(), ())
        kernel_data.put(
            action_info.update,
            1,
            ask_group_sex_refuse_chara_id_list=[2],
            interacting_character_end_info=[2, now],
        )
        kernel_data.put(action_info.remap, (1,), {2: 88})
        self.assertEqual(
            action_info.get(1, "ask_group_sex_refuse_chara_id_list"), [88]
        )
        self.assertEqual(
            action_info.get(1, "interacting_character_end_info"), [88, now]
        )
        self.assertEqual(
            action_info.get(1, "social_contact_last_time"), {88: now}
        )

        kernel_data.put(action_info.init_zero, 2)
        self.assertEqual(action_info.get(2, "talk_time"), now)
        self.assertEqual(action_info.get(2, "wake_time"), now)

        legacy = game_type.Character()
        ai = game_type.ACTION_INFO()
        ai.health_check_today = 2
        ai.last_gift_time = now
        vars(legacy)["action_info"] = ai
        kernel_data.put(
            action_info.adopt_old_save, {"character_data": {1: legacy}}
        )
        self.assertFalse(hasattr(legacy, "action_info"))
        self.assertEqual(action_info.get(1, "health_check_today"), 2)
        self.assertEqual(action_info.get(1, "last_gift_time"), now)

    def test_player_ability_exact_num_and_codec_roundtrip(self) -> None:
        """player.ability：today_sanity_point_cost 保留精确类型并经 JSON 编解码往返，adopt 转换 float"""
        self.assertEqual(player_ability.get(0, "follow_count"), 1)
        self.assertEqual(player_ability.get(0, "today_sanity_point_cost"), 0)
        self.assertIs(
            type(player_ability.get(0, "today_sanity_point_cost")), int
        )

        kernel_data.put(player_ability.add_sanity_cost, 0, Fraction(1, 3))
        kernel_data.put(
            player_ability.set,
            0,
            visual=True,
            air_hypnosis_position=["中枢", "0"],
        )
        val = player_ability.get(0, "today_sanity_point_cost")
        self.assertIs(type(val), Fraction)
        self.assertEqual(val, Fraction(1, 3))
        self.assertEqual(
            player_ability.get(0, "air_hypnosis_position"), ["中枢", "0"]
        )

        encoded = kernel_state.encode(core.state(), "tok")
        raw_text = json.dumps(encoded, ensure_ascii=False)
        self.assertIn('"$frac"', raw_text)
        decoded = kernel_state.decode(json.loads(raw_text), True)
        self.assertEqual(decoded, core.state())
        back_val = player_ability.get(0, "today_sanity_point_cost", decoded)
        self.assertIs(type(back_val), Fraction)
        self.assertEqual(back_val, Fraction(1, 3))

        legacy = game_type.Character()
        pa = game_type.PLAYER_ABILITY()
        vars(pa)["today_sanity_point_cost"] = 0.1
        pa.carry_chara_id_in_time_stop = 2
        vars(legacy)["pl_ability"] = pa
        kernel_data.put(
            player_ability.adopt_old_save, {"character_data": {0: legacy}}
        )
        self.assertFalse(hasattr(legacy, "pl_ability"))
        adopted = player_ability.get(0, "today_sanity_point_cost")
        self.assertIs(type(adopted), Fraction)
        self.assertEqual(adopted, Fraction(1, 10))
        kernel_data.put(player_ability.remap, (0,), {2: 77})
        self.assertEqual(
            player_ability.get(0, "carry_chara_id_in_time_stop"), 77
        )

    def test_player_collection_ops_remap_carry_adopt(self) -> None:
        """player.collection：各项读写、新周目携带、remap（含自映射）与 adopt_old_save"""
        now = game_time.now()
        kernel_data.put(player_collection.set_bonus, 102, True)
        self.assertTrue(player_collection.bonus(102))
        with working.based_on(core.state()) as buf:
            player_collection.set_bonus(102, True)
            self.assertEqual(buf.effects(), ())
        kernel_data.put(player_collection.set_token, 1, True)
        self.assertTrue(player_collection.get("token_list")[1])
        kernel_data.put(
            player_collection.append_list_map, "npc_panties", 1, "棉质"
        )
        kernel_data.put(
            player_collection.append_list_map, "npc_socks", 1, "长袜"
        )
        kernel_data.put(player_collection.add_total, "milk_total", 1, 25)
        kernel_data.put(player_collection.set_eqip_token, 2, [1])
        kernel_data.put(player_collection.append_used_condom, 12)
        held_id = kernel_data.written(player_collection.add_held_egg, 1, 0)
        soft_id = kernel_data.written(
            player_collection.add_soft_egg, 1, now, ["中枢", "0"], 10.0
        )
        self.assertTrue(player_collection.has_soft_eggs())

        carried = player_collection.carry_for_new_round(core.state())
        self.assertEqual(carried["npc_panties"], {"1": ("棉质",)})
        self.assertEqual(carried["npc_socks"], {"1": ("长袜",)})

        kernel_data.put(player_collection.remap, (0,), {0: 0, 1: 55})
        self.assertTrue(player_collection.get("token_list")[55])
        self.assertEqual(player_collection.get("npc_panties")[55], ["棉质"])
        self.assertEqual(player_collection.get("eqip_token"), [2, [55]])
        self.assertEqual(player_collection.get("held_eggs")[held_id], (55, 0))
        self.assertEqual(
            player_collection.get("soft_eggs")[soft_id]["mother_id"], 55
        )

        kernel_data.put(player_collection.put, "held_eggs", {})
        kernel_data.put(player_collection.remove_soft_egg, soft_id)
        self.assertFalse(player_collection.has_soft_eggs())

        legacy = game_type.Character()
        pc = game_type.PLAYER_COLLECTION()
        pc.token_list[2] = True
        pc.used_condoms = [5, 8]
        vars(legacy)["pl_collection"] = pc
        kernel_data.put(
            player_collection.adopt_old_save, {"character_data": {0: legacy}}
        )
        self.assertFalse(hasattr(legacy, "pl_collection"))
        self.assertTrue(player_collection.get("token_list")[2])
        self.assertEqual(player_collection.get("used_condoms"), [5, 8])

    def test_plan_and_starts_route_sp_flag_and_action_info(self) -> None:
        """choice.Plan.get 与 starts.write_field 转发 sp_flag.* 与 action_info.* 到内核键"""
        kernel_data.put(flags.set, 1, is_follow=2)
        kernel_data.put(action_info.set, 1, "eat_food_restaurant", 3)
        plan = choice.Plan(1)
        self.assertEqual(plan.get("sp_flag.is_follow"), 2)
        self.assertEqual(plan.get("action_info.eat_food_restaurant"), 3)
        plan.set("sp_flag.sleep", True)
        self.assertIs(plan.get("sp_flag.sleep"), True)

        kernel_data.put(starts.write_field, 1, "sp_flag.sleep", True)
        kernel_data.put(starts.write_field, 1, "action_info.talk_count", 4)
        self.assertIs(flags.get(1, "sleep"), True)
        self.assertEqual(action_info.get(1, "talk_count"), 4)

    def test_events_trigger_reads_passed_game_state(self) -> None:
        """events._becomes_tired 按传入的 GameState 读 tired 标记，flags.of 交回只读稀疏映射"""
        self.assertEqual(dict(flags.of(1, core.state())), {})
        kernel_data.set_needs(1, hit=1)
        without_tired = core.state()
        kernel_data.put(flags.set, 1, tired=True)
        with_tired = core.state()
        self.assertEqual(dict(flags.of(1, with_tired)), {"tired": True})
        self.assertTrue(events._becomes_tired(1, without_tired))
        self.assertFalse(events._becomes_tired(1, with_tired))

    def test_ensure_npc_checks_raw_without_decoding(self) -> None:
        """ensure_npc 命中已有干员时只查原始表，不解码整张 token_list"""
        self.assertTrue(kernel_data.written(player_collection.ensure_npc, 1))
        with mock.patch.object(
            player_collection,
            "get",
            side_effect=AssertionError("should not decode token_list"),
        ):
            self.assertFalse(
                kernel_data.written(player_collection.ensure_npc, 1)
            )

    def test_fix_wrong_character_amaya_keeps_cid_and_domains(self) -> None:
        """阿玛雅编号修复后目标槽位 cid 与四域对齐，原槽位按源 cid 重建"""
        self.op_a.adv = 450
        self.op_a.name = get_text._("阿玛雅")
        self.op_b.adv = 448
        kernel_data.put(flags.set, 1, is_h=True)
        kernel_data.put(action_info.set, 1, "talk_count", 7)
        kernel_data.put(flags.set, 2, rest=True)
        kernel_data.put(action_info.set, 2, "talk_count", 3)

        def fake_init(
            cid: int, _tem: object, collect_reset: bool = True
        ) -> game_type.Character:
            flags.reset(cid)
            action_info.set(cid, "talk_count", 0)
            rebuilt = game_type.Character()
            rebuilt.cid = cid
            rebuilt.adv = 450
            return rebuilt

        characters: dict[int, game_type.Character] = {
            1: self.op_a,
            2: self.op_b,
        }
        loaded: dict[str, object] = {
            "character_data": characters,
            "npc_tem_data": {1: object()},
        }
        with mock.patch.object(
            character_handle, "init_character", side_effect=fake_init
        ):
            updated = kernel_data.written(
                old_chara_to_new.fix_wrong_character, loaded
            )
        self.assertEqual(updated, 1)
        retained = characters[2]
        rebuilt = characters[1]
        self.assertEqual(retained.cid, 2)
        self.assertEqual(retained.adv, 448)
        self.assertIs(flags.get(retained.cid, "is_h"), True)
        self.assertIs(flags.get(retained.cid, "rest"), False)
        self.assertEqual(action_info.get(retained.cid, "talk_count"), 7)
        self.assertEqual(rebuilt.cid, 1)
        self.assertIs(flags.get(rebuilt.cid, "is_h"), False)
        self.assertEqual(action_info.get(rebuilt.cid, "talk_count"), 0)

    def test_world_move_works_inside_active_buffer(self) -> None:
        """world.move 在外层缓冲区或结算内调用时不重复调用 core.reset_state"""
        self.assertFalse(working.active())
        with kernel_data.writing():
            self.assertTrue(working.active())
            self.world.move(1, ["中枢", "0"])
        self.assertEqual(self.op_a.position, ["中枢", "0"])
        self.assertTrue(action_info.get(1, "past_move_position_list"))
