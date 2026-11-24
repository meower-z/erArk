# -*- coding: UTF-8 -*-
"""
角色的 H 状态（h.state）
======================
- 稀疏存储：默认值时内核里为空表，view 补齐配置里的身体道具名与快感部位键。
- 零拷贝热读（get、body_item_on、active_body_items）、单字段写入（set、set_body_item）与 editing 块。
- reset 保留 0/2 类身体道具、时停绝顶计数、忍住不射次数与群交开关；clear 全部清空。
- 群交模板角色id 重映射与移除。
- adopt_old_save 修复旧档 orgasm_count==0 与列表型 body_item 并返回更新计数。
"""

from unittest import mock

from Script.Config import game_config
from Script.Core import game_type
from Script.Design import game_time, handle_npc_ai_in_h, handle_premise
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import flags, h_state
from Script.Modules.gameplay_resolution import group_sex_service, working
from Script.Settle import default as settle_default
from tests import kernel_data
from tests.fast.base import FastTestCase
from Script.Modules.save_load.legacy_pickle import LegacyObject


class HStateTest(FastTestCase):
    """h.state 领域的稀疏读写、重置与旧档导入"""

    def setUp(self) -> None:
        """载入内核模块并建出两名测试角色"""
        super().setUp()
        core.load(load_order.LOAD_ORDER)
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")

    def test_sparse_defaults_and_hot_reads(self) -> None:
        """默认稀疏为空，热读返回默认值，view 补全身体道具名与部位键"""
        self.assertEqual(h_state.get(1, "insert_position"), -1)
        self.assertFalse(h_state.body_item_on(1, 0))
        self.assertEqual(h_state.active_body_items(1), [])
        v = h_state.view(1)
        self.assertEqual(len(v.body_item), len(game_config.config_body_item))
        self.assertEqual(v.insert_position, -1)
        self.assertEqual(v.condom_count, [0, 0])
        self.assertEqual(v.plural_orgasm_set, set())

    def test_set_body_item_and_editing(self) -> None:
        """set、set_body_item 与 editing 块写入并在退出时编码回稀疏结构"""
        end = game_time.at(game_time.minutes(game_time.now()) + 30)
        with working.based_on(core.state()) as buf:
            h_state.set(1, bondage=2, just_shoot=1, condom_count=(3, 45))
            h_state.set_body_item(1, 8, True, end)
            with h_state.editing(1) as hs:
                hs.orgasm_level[4] = 3
                hs.orgasm_count[4] = [1, 2]
                hs.plural_orgasm_set.add(4)
                hs.plural_orgasm_set.add(1)
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertEqual(h_state.get(1, "bondage", next_state), 2)
        self.assertTrue(h_state.body_item_on(1, 8, next_state))
        self.assertEqual(h_state.body_item_end(1, 8, next_state), end)
        self.assertEqual(
            h_state.active_body_items(1, (8, 9), next_state), [(8, end)]
        )
        v = h_state.view(1, next_state)
        self.assertEqual(v.condom_count, [3, 45])
        self.assertEqual(v.orgasm_level[4], 3)
        self.assertEqual(v.orgasm_count[4], [1, 2])
        self.assertEqual(v.plural_orgasm_set, {1, 4})

    def test_reset_preserves_persistent_fields_and_clear_empties(self) -> None:
        """reset 保留 0/2 类身体道具、时停绝顶、忍住计数与群交设置；clear 全清"""
        from Script.Config import game_config

        keep_item = next(
            k
            for k, v in game_config.config_body_item.items()
            if v.type in {0, 2}
        )
        drop_item = next(
            k
            for k, v in game_config.config_body_item.items()
            if v.type not in {0, 2}
        )
        end = game_time.at(game_time.minutes(game_time.now()) + 60)
        with working.based_on(core.state()) as buf:
            h_state.set(
                1,
                bondage=1,
                endure_not_shot_count=3,
                group_sex_lock_flag=True,
                npc_ai_type_in_group_sex=2,
            )
            h_state.set_body_item(1, keep_item, True, end)  # 0/2类（保留）
            h_state.set_body_item(1, drop_item, True, None)  # 1类H道具（清掉）
            with h_state.editing(1) as hs:
                hs.time_stop_orgasm_count[4] = 5
                hs.orgasm_level[4] = 2
            h_state.reset(1)
            after_reset = h_state.view(1)
            changed = h_state.clear(1)
            after_clear = h_state.view(1)
            _ = buf.effects()
        self.assertTrue(changed)
        self.assertEqual(after_reset.bondage, 0)
        self.assertEqual(after_reset.endure_not_shot_count, 3)
        self.assertTrue(after_reset.group_sex_lock_flag)
        self.assertEqual(after_reset.npc_ai_type_in_group_sex, 2)
        self.assertTrue(after_reset.body_item[keep_item][1])
        self.assertEqual(after_reset.body_item[keep_item][2], end)
        self.assertFalse(after_reset.body_item[drop_item][1])
        self.assertEqual(after_reset.time_stop_orgasm_count[4], 5)
        self.assertEqual(after_reset.orgasm_level[4], 0)
        self.assertEqual(after_clear.endure_not_shot_count, 0)
        self.assertFalse(after_clear.body_item[keep_item][1])

    def test_group_sex_template_remap_and_remove(self) -> None:
        """群交模板里的角色id 可重映射也可按集合移除"""
        with working.based_on(core.state()):
            with h_state.editing(0) as hs:
                hs.group_sex_body_template_dict["A"][0]["mouth"] = [10, 5]
                hs.group_sex_body_template_dict["A"][1] = [[10, 20], 9]
            h_state.remap_group_sex_ids(0, {10: 100})
            tpl = h_state.view(0).group_sex_body_template_dict["A"]
            self.assertEqual(tpl[0]["mouth"], [100, 5])
            self.assertEqual(tpl[1], [[100, 20], 9])
            removed = h_state.remove_from_group_sex_template(0, {100, 20})
            self.assertEqual(removed, 2)
            tpl2 = h_state.view(0).group_sex_body_template_dict["A"]
            self.assertEqual(tpl2[0]["mouth"], [-1, -1])
            self.assertEqual(tpl2[1], [[-1], -1])

    def test_adopt_old_save_repairs_legacy_shapes(self) -> None:
        """旧档 orgasm_count==0 与列表型 body_item 在导入时修复并计入更新数"""
        chara = LegacyObject()
        old = game_type.BODY_H_STATE()
        old.bondage = 3
        vars(old)["body_item"] = []
        vars(old)["orgasm_count"] = {4: 0}
        vars(chara)["h_state"] = old
        with working.based_on(core.state()) as buf:
            count = h_state.adopt_old_save({"character_data": {1: chara}})
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertFalse(hasattr(chara, "h_state"))
        self.assertEqual(count, 1 + len(game_config.config_body_item))
        self.assertEqual(h_state.get(1, "bondage", next_state), 3)
        self.assertEqual(h_state.view(1, next_state).orgasm_count[4], [0, 0])

    def test_npc_ai_in_group_sex_persists_template_writes(self) -> None:
        """npc_ai_in_group_sex 的占单部位、占侍奉位、加入侍奉三条路径都写回内核状态"""
        self.world.chara(2, "能天使")
        self.world.chara(3, "德克萨斯")
        for cid in (1, 2, 3):
            kernel_data.put(flags.set, cid, is_h=True)
        with (
            working.based_on(core.state()) as buf,
            mock.patch.object(
                handle_premise, "handle_group_sex_mode_off", return_value=False
            ),
            mock.patch.object(
                handle_premise, "handle_self_now_bondage", return_value=False
            ),
            mock.patch.object(
                handle_premise,
                "handle_npc_ai_type_1_in_group_sex",
                return_value=False,
            ),
            mock.patch.object(
                group_sex_service,
                "get_now_template_part_list",
                side_effect=[
                    (["mouth"], []),
                    (["侍奉"], []),
                    (["加入侍奉"], []),
                ],
            ),
            mock.patch.object(
                group_sex_service,
                "get_status_id_list_from_group_sex_body_part",
                side_effect=[["ST_MOUTH"], ["ST_SERVE"]],
            ),
        ):
            handle_npc_ai_in_h.npc_ai_in_group_sex(1)
            handle_npc_ai_in_h.npc_ai_in_group_sex(2)
            handle_npc_ai_in_h.npc_ai_in_group_sex(3)
            participants = set(
                group_sex_service.count_group_sex_character_list()
            )
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        tpl = h_state.view(0, next_state).group_sex_body_template_dict["A"]
        self.assertEqual(tpl[0]["mouth"], [1, "ST_MOUTH"])
        self.assertEqual(tpl[1], [[2, 3], "ST_SERVE"])
        self.assertEqual(participants, {1, 2, 3})

    def test_dr_position_effects_write_player_not_npc(self) -> None:
        """DR_POSITION_* 结算由 NPC 触发时仍写入博士（cid=0）的体位字段"""
        now = game_time.now()
        with working.based_on(core.state()) as buf:
            settle_default.handle_dr_position_normal(
                1, 5, game_type.CharacterStatusChange(), now
            )
            settle_default.handle_dr_position_womb_insert(
                1, 5, game_type.CharacterStatusChange(), now
            )
            effects = buf.effects()
        next_state = core.preview(core.state(), effects)
        self.assertEqual(h_state.get(0, "current_sex_position", next_state), 1)
        self.assertEqual(
            h_state.get(0, "current_womb_sex_position", next_state), 1
        )
        self.assertEqual(h_state.get(1, "current_sex_position", next_state), -1)
        self.assertEqual(
            h_state.get(1, "current_womb_sex_position", next_state), 0
        )

    def test_reset_and_clear_inside_editing_persist(self) -> None:
        """editing 块内调用 reset/clear 就地更新并持久化，reset 保留块内已改的持久字段"""
        with working.based_on(core.state()) as buf:
            with h_state.editing(1) as hs:
                hs.bondage = 2
                hs.endure_not_shot_count = 4
                h_state.reset(1)
                self.assertEqual(hs.bondage, 0)
                self.assertEqual(hs.endure_not_shot_count, 4)
                hs.just_shoot = 1
            effects = buf.effects()
        st1 = core.preview(core.state(), effects)
        self.assertEqual(h_state.get(1, "bondage", st1), 0)
        self.assertEqual(h_state.get(1, "endure_not_shot_count", st1), 4)
        self.assertEqual(h_state.get(1, "just_shoot", st1), 1)

        with working.based_on(st1) as buf2:
            with h_state.editing(1) as hs2:
                self.assertTrue(h_state.clear(1))
                self.assertEqual(hs2.endure_not_shot_count, 0)
                hs2.bondage = 3
            effects2 = buf2.effects()
        st2 = core.preview(st1, effects2)
        self.assertEqual(h_state.get(1, "endure_not_shot_count", st2), 0)
        self.assertEqual(h_state.get(1, "bondage", st2), 3)

    def test_every_h_state_field_roundtrips(self) -> None:
        """BODY_H_STATE 类的全部字段都被 _encode/_decode 覆盖并在编辑提交后保留"""
        expected_fields = {
            "all_group_sex_temple_run",
            "body_item",
            "bondage",
            "condom_count",
            "condom_info_show_flag",
            "current_sex_position",
            "current_womb_sex_position",
            "endure_not_shot_count",
            "extra_orgasm_count",
            "extra_orgasm_feel",
            "group_sex_body_template_dict",
            "group_sex_lock_flag",
            "h_in_bathroom",
            "h_in_love_hotel",
            "hidden_sex_discovery_dregree",
            "insert_position",
            "insert_position_change_save",
            "just_shoot",
            "npc_active_h",
            "npc_ai_type_in_group_sex",
            "orgasm_count",
            "orgasm_edge",
            "orgasm_edge_count",
            "orgasm_level",
            "plural_orgasm_set",
            "pre_sex_position",
            "pretend_sleep",
            "sex_assist",
            "shoot_position_body",
            "shoot_position_cloth",
            "shoot_semen_amount",
            "time_stop_orgasm_count",
            "time_stop_release",
            "used_semen_energy_agent",
        }
        self.assertEqual(set(vars(game_type.BODY_H_STATE())), expected_fields)
        with working.based_on(core.state()) as buf:
            with h_state.editing(1) as hs:
                hs.all_group_sex_temple_run = True
                hs.body_item[0][1] = True
                hs.bondage = 2
                hs.condom_count = [2, 30]
                hs.condom_info_show_flag = True
                hs.current_sex_position = 3
                hs.current_womb_sex_position = 2
                hs.endure_not_shot_count = 5
                hs.extra_orgasm_count = 2
                hs.extra_orgasm_feel[4] = 150
                hs.group_sex_body_template_dict["A"][0]["mouth"] = [1, "S"]
                hs.group_sex_lock_flag = True
                hs.h_in_bathroom = True
                hs.h_in_love_hotel = True
                hs.hidden_sex_discovery_dregree = 12
                hs.insert_position = 6
                hs.insert_position_change_save = 2
                hs.just_shoot = True
                hs.npc_active_h = True
                hs.npc_ai_type_in_group_sex = 1
                hs.orgasm_count[4] = [3, 1]
                hs.orgasm_edge = 1
                hs.orgasm_edge_count[4] = 2
                hs.orgasm_level[4] = 4
                hs.plural_orgasm_set.add(4)
                hs.pre_sex_position = 2
                hs.pretend_sleep = True
                hs.sex_assist = True
                hs.shoot_position_body = 6
                hs.shoot_position_cloth = 10
                hs.shoot_semen_amount = 25
                hs.time_stop_orgasm_count[4] = 2
                hs.time_stop_release = True
                hs.used_semen_energy_agent = True
            effects = buf.effects()
        v = h_state.view(1, core.preview(core.state(), effects))
        self.assertTrue(v.all_group_sex_temple_run)
        self.assertTrue(v.body_item[0][1])
        self.assertEqual(v.bondage, 2)
        self.assertEqual(v.condom_count, [2, 30])
        self.assertTrue(v.condom_info_show_flag)
        self.assertEqual(v.current_sex_position, 3)
        self.assertEqual(v.current_womb_sex_position, 2)
        self.assertEqual(v.endure_not_shot_count, 5)
        self.assertEqual(v.extra_orgasm_count, 2)
        self.assertEqual(v.extra_orgasm_feel[4], 150)
        self.assertEqual(
            v.group_sex_body_template_dict["A"][0]["mouth"], [1, "S"]
        )
        self.assertTrue(v.group_sex_lock_flag)
        self.assertTrue(v.h_in_bathroom)
        self.assertTrue(v.h_in_love_hotel)
        self.assertEqual(v.hidden_sex_discovery_dregree, 12)
        self.assertEqual(v.insert_position, 6)
        self.assertEqual(v.insert_position_change_save, 2)
        self.assertTrue(v.just_shoot)
        self.assertTrue(v.npc_active_h)
        self.assertEqual(v.npc_ai_type_in_group_sex, 1)
        self.assertEqual(v.orgasm_count[4], [3, 1])
        self.assertEqual(v.orgasm_edge, 1)
        self.assertEqual(v.orgasm_edge_count[4], 2)
        self.assertEqual(v.orgasm_level[4], 4)
        self.assertEqual(v.plural_orgasm_set, {4})
        self.assertEqual(v.pre_sex_position, 2)
        self.assertTrue(v.pretend_sleep)
        self.assertTrue(v.sex_assist)
        self.assertEqual(v.shoot_position_body, 6)
        self.assertEqual(v.shoot_position_cloth, 10)
        self.assertEqual(v.shoot_semen_amount, 25)
        self.assertEqual(v.time_stop_orgasm_count[4], 2)
        self.assertTrue(v.time_stop_release)
        self.assertTrue(v.used_semen_energy_agent)
