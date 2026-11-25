"""多周目结算与继承服务单元测试，覆盖点数、消耗、重建与无界面边界。"""

from typing import cast

from Script.Config import game_config
from Script.Core import constant
from Script.Kernel import core
from Script.Modules.domains import abilities, chara_life, facility, h_meters
from Script.Modules.domains import hypnosis, identity, modes, needs
from Script.Modules.domains import npc_template, player_collection
from Script.Modules.domains import playthrough, relations, roster
from Script.Modules.gameplay_resolution import new_round_inherit_service
from Script.Modules.gameplay_resolution import new_round_service as svc
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free
from tests.world import start_time

LEVELS = (1, 2, 1, 5, 1, 2, 3)
""" 测试用七项继承等级元组。 """
CHILD_RUN = """
from Script.Config import character_config, game_config, map_config
from Script.Core import constant
character_config.init_character_tem_data()
map_config.init_map_data()
from Script.Kernel import core
from Script.Modules.domains import abilities, chara_life, facility, identity, modes
from Script.Modules.domains import npc_template
from Script.Modules.domains import relations, roster
from Script.Modules.gameplay_resolution import new_round_inherit_service as inh
from Script.Modules.gameplay_resolution import new_round_service as svc
from Script.Modules.gameplay_resolution import working
from tests import chara_abilities, kernel_data
from tests.chara_activity import place
from tests.world import DEFAULT_SCENE, start_time
ids = [cid for cid in npc_template.ids() if cid][:2]
payload["runs"] = []
for debug, levels in ((False, [0] * 7), (True, [1, 2, 1, 5, 1, 2, 3])):
    kernel_data.reset_clock(start_time(), {})
    for cid in (0, *ids):
        kernel_data.put(identity.put, identity.Identity(cid, name=str(cid), sex=cid % 2))
        kernel_data.put(relations.favorability.set, cid, {0: 0})
        chara_abilities.zero_tables(cid)
        place(cid, DEFAULT_SCENE)
    for cid in ids:
        kernel_data.put(roster.add, cid)
    with working.based_on(core.state()):
        modes.set_debug(debug)
        abilities.talent(ids[0])[203] = 1
        for talent_id in (304, 308, 312, 334):
            abilities.talent(0)[talent_id] = 1
        relations.trust.set(ids[0], 80)
        points = svc.points()
        run = [points.total, [svc.cost(t, lv) for t, lv in enumerate(levels)]]
        run.append([svc.step(t, lv, d) for t, lv in enumerate(levels) for d in (-1, 1)])
        run.append(svc.growth_preview(svc.rate(2, levels[2])))
        run.append({t: g[0] for t, g in svc.ability_groups(ids[1]).items()})
        run.append(svc.experience_texts(0, 40))
        choices = svc.choices(levels, [ids[0]], {1: 1})
    kernel_data.reset_clock(start_time(), {})
    with working.based_on(core.state()):
        report, world = inh.rebuild(choices)
        names = game_config.config_facility_open_name_set
        room = next(k for k, v in constant.scene_data.items() if v.scene_name in names)
        chara_life.dormitory.set(ids[0], room)
        inh.open_dormitories([ids[0]])
        opened = facility.is_open(game_config.config_facility_open_name_to_cid[constant.scene_data[room].scene_name])
        run += [report.count("\\n"), world, opened, relations.trust(ids[0])]
    payload["runs"].append(run)
"""
""" 在拦截界面与结算模块的子进程中依次调用两服务公开接口的脚本。 """


def inherit_rate(type_id: int, level: int) -> int:
    """从配置表查询指定继承类型与等级对应的继承比例。"""
    cid = game_config.config_new_round_inherit_type_data[type_id][level]
    return game_config.config_new_round_inherit[cid].inherit_rate


class NewRoundCase(FastTestCase):
    """多周目服务测试基类，准备博士与三名非初始模板干员。"""

    def setUp(self) -> None:
        """初始化测试角色并为前两名干员授予陷落天赋。"""
        super().setUp()
        self.world.chara(0, "博士")
        first = constant.first_NPC_adv_set
        self.a, self.b, self.c = [
            cid
            for cid, tem in sorted(npc_template.table().items())
            if cid and tem.AdvNpc not in first
        ][:3]
        for cid in (self.a, self.b, self.c):
            self.world.chara(cid, f"干员{cid}")
        with kernel_data.writing():
            abilities.talent(self.a)[203] = 1
            abilities.talent(self.b)[212] = 1

    def set_maxima(self) -> None:
        """为博士设置用于成长与消耗测试的四项属性上限。"""
        with kernel_data.writing():
            needs.set(0, hit_max=3000, mana_max=1600, sanity_max=300)
            h_meters.set(0, semen_max=180)


class PointsTest(NewRoundCase):
    """周目点数汇总与调试加成计算测试。"""

    def test_points_add_round_fallen_and_collection(self) -> None:
        """验证周目、陷落、收藏品点数及调试加成计算结果。"""
        with kernel_data.writing():
            playthrough.set_game_round(3)
            player_collection.update(
                npc_panties={str(self.a): ["p1", "p2"], str(self.b): ["p3"]},
                npc_socks={str(self.a): ["s1"]},
            )
        points = svc.points()
        fallen = [(f.chara_id, f.talent_id, f.point) for f in points.fallen]
        self.assertEqual(fallen, [(self.a, 203, 6), (self.b, 212, 4)])
        self.assertEqual(
            (points.round_point, points.fallen_point, points.collection_point),
            (60, 10, 4),
        )
        self.assertEqual(points.total, 74)
        with kernel_data.writing():
            modes.set_debug(True)
        self.assertEqual(svc.points().total, 74 + 9999)


class CostTest(NewRoundCase):
    """继承消耗、成长预览与等级夹紧规则测试。"""

    def test_arts_cost_counts_owned_talents_by_tier(self) -> None:
        """验证源石技艺继承按持有天赋档位计费且零级为零。"""
        with kernel_data.writing():
            for talent_id in range(301, 350):
                abilities.talent(0)[talent_id] = 0
            for talent_id in (304, 308, 312, 334, 301):
                abilities.talent(0)[talent_id] = 1
        self.assertEqual(svc.cost(0, 1), 10 + 30 + 60 + 120)
        self.assertEqual(svc.cost(0, 0), 0)

    def test_growth_cost_and_preview(self) -> None:
        """验证属性上限成长消耗与预览数值按比例计算。"""
        self.set_maxima()
        self.assertEqual(inherit_rate(2, 1), 50)
        self.assertEqual(svc.cost(2, 1), 20 + 6 + 100 + 40)
        self.assertEqual(svc.cost(2, 0), 0)
        self.assertEqual(
            svc.growth_preview(50), [3000, 2000, 1600, 1300, 300, 200, 180, 140]
        )

    def test_other_types_cost_their_configured_points(self) -> None:
        """验证其余继承类型消耗与配置表点数一致。"""
        data = game_config.config_new_round_inherit_type_data
        for type_id in (1, 3, 4, 5, 6):
            for level, cid in data[type_id].items():
                with self.subTest(type_id=type_id, level=level):
                    self.assertEqual(
                        svc.cost(type_id, level),
                        game_config.config_new_round_inherit[cid].point_cost,
                    )

    def test_step_stays_within_levels(self) -> None:
        """验证等级步进调整不会越过零级与最高级边界。"""
        top = len(game_config.config_new_round_inherit_type_data[1]) - 1
        self.assertEqual(svc.step(1, 0, -1), 0)
        self.assertEqual(svc.step(1, 0, 1), 1)
        self.assertEqual(svc.step(1, top, 1), top)
        self.assertEqual(svc.step(1, top, -1), top - 1)


class ChoicesTest(NewRoundCase):
    """多周目继承快照构造测试。"""

    def test_choices_name_levels_and_carry_fallen_data(self) -> None:
        """验证继承快照包含七项等级及陷落干员携带数据。"""
        self.set_maxima()
        with kernel_data.writing():
            hypnosis.set(self.a, hypnosis_degree=50)
            relations.trust.set(self.a, 80)
            relations.favorability.set_item(self.a, 0, 70)
            relations.trust.set(self.b, 10)
            relations.favorability.set_item(self.b, 0, 5)
        choices = svc.choices(LEVELS, [self.a, self.b], {1: 1, 2: 0})
        self.assertEqual(
            {key: choices[key] for key in svc.KEYS},
            dict(zip(svc.KEYS, LEVELS, strict=True)),
        )
        self.assertEqual(choices["pl_originium_arts_count"], 1)
        self.assertEqual(choices["chara_hypnosis_count"], 3)
        self.assertEqual(choices["all_fall_chara_list"], (self.a, self.b))
        self.assertEqual(choices["world_setting"], {"1": 1, "2": 0})
        self.assertEqual(
            choices["player_maxima"],
            {
                "hit_max": 3000,
                "mana_max": 1600,
                "sanity_max": 300,
                "semen_max": 180,
            },
        )
        self.assertEqual(choices["npc_hypnosis"], {str(self.a): 50})
        self.assertEqual(
            choices["fallen_social"],
            {str(self.a): (80, 70), str(self.b): (10, 5)},
        )


class RebuildTest(NewRoundCase):
    """新周目状态重建与异常快照校验测试。"""

    def rebuild(self, levels: tuple[int, ...]) -> tuple[str, dict[int, int]]:
        """写入旧周目测试数据并重置状态后执行重建。"""
        self.set_maxima()
        with kernel_data.writing():
            abilities.ability(0)[5] = 7
            abilities.experience(0)[4] = 250
            abilities.talent(0)[304] = 1
            abilities.ability(self.a)[5] = 5
            hypnosis.set(self.a, hypnosis_degree=50)
            relations.trust.set(self.a, 80)
            relations.favorability.set_item(self.a, 0, 70)
            player_collection.update(
                npc_panties={
                    str(self.a): ["p1", "p2", "p3"],
                    str(self.b): ["p4"],
                },
                npc_socks={str(self.a): ["s1"], str(self.b): ["s2"]},
            )
        choices = svc.choices(levels, [self.a], {1: 1, 2: 0})
        kernel_data.reset_clock(start_time(), {})
        return kernel_data.written(new_round_inherit_service.rebuild, choices)

    def test_rebuild_scales_player_and_fallen_operator(self) -> None:
        """验证非零等级重建正确缩放玩家与陷落干员数据。"""
        report, world = self.rebuild(LEVELS)
        self.assertEqual(world, {1: 1, 2: 0})
        self.assertEqual(abilities.ability(0)[5], int(7 * 40 / 100))
        self.assertEqual(abilities.experience(0)[4], 100)
        self.assertEqual(abilities.talent(0)[304], 1)
        player = needs.of(0)
        self.assertEqual(
            [player[k] for k in ("hit_max", "mana_max", "sanity_max")],
            [2000, 1300, 200],
        )
        self.assertEqual(h_meters.of(0)["semen_max"], 140)
        owned = {
            name: {k: v for k, v in player_collection.get(name).items() if v}
            for name in ("npc_panties", "npc_socks")
        }
        self.assertEqual(
            owned,
            {
                "npc_panties": {self.a: ["p1", "p2", "p3"], self.b: ["p4"]},
                "npc_socks": {self.a: ["s1"], self.b: ["s2"]},
            },
        )
        self.assertIn(self.a, roster.active())
        self.assertNotIn(self.b, roster.active())
        self.assertEqual(relations.trust(self.a), int(80 * 20 / 100))
        self.assertEqual(relations.favorability(self.a)[0], 14)
        self.assertEqual(abilities.ability(self.a)[5], 2)
        self.assertEqual(hypnosis.degree(self.a), 30)
        self.assertRegex(report, "共有[0-9]+名陷落干员继承到下一周目")
        self.assertIn("共继承了20%的好感与信任", report)
        self.assertIn("共继承了60%的催眠进度", report)

    def test_rebuild_at_level_zero_keeps_template_values(self) -> None:
        """验证零级重建保持模板初值并输出未继承报告行。"""
        report, _world = self.rebuild((0,) * 7)
        self.assertEqual(abilities.talent(0)[304], 0)
        self.assertEqual(abilities.ability(0)[5], 0)
        self.assertEqual(needs.of(0)["hit_max"], 1000)
        self.assertEqual(relations.trust(self.a), 0)
        self.assertEqual(hypnosis.degree(self.a), 0)
        for text in ("好感与信任", "能力与经验", "催眠进度"):
            self.assertIn(f"干员{text}未继承", report)

    def test_rebuild_rejects_malformed_choices(self) -> None:
        """验证陷落干员列表类型错误时抛出 TypeError。"""
        choices = svc.choices(LEVELS, [self.a], {})
        broken = {**choices, "all_fall_chara_list": cast(core.JSON, [self.a])}
        with self.assertRaises(TypeError):
            kernel_data.written(new_round_inherit_service.rebuild, broken)


class DormitoryTest(NewRoundCase):
    """宿舍设施开放写入测试。"""

    def test_open_dormitories_opens_closed_rooms(self) -> None:
        """验证已关闭的干员宿舍设施在调用后被打开。"""
        names = game_config.config_facility_open_name_set
        key = next(
            k for k, s in constant.scene_data.items() if s.scene_name in names
        )
        open_cid = game_config.config_facility_open_name_to_cid[
            constant.scene_data[key].scene_name
        ]
        with kernel_data.writing():
            chara_life.dormitory.set(self.a, key)
            facility.set_open(open_cid, False)
        kernel_data.written(
            new_round_inherit_service.open_dormitories, [self.a]
        )
        self.assertTrue(facility.is_open(open_cid))


class PanelRowsTest(NewRoundCase):
    """面板能力分组与经验预览行查询测试。"""

    def test_ability_groups_hide_player_types_and_other_sex(self) -> None:
        """验证能力分组按角色与性别过滤并保留完整类型数。"""
        types = game_config.config_ability_type_data
        player = svc.ability_groups(0)
        self.assertEqual(set(player), set(types) - {0, 1, 2, 6})
        kernel_data.put(
            identity.put, identity.Identity(self.c, name="男性", sex=0)
        )
        for cid, hidden in ((self.a, {3}), (self.c, {73, 74, 75})):
            groups = svc.ability_groups(cid)
            self.assertEqual(set(groups), set(types))
            for ability_type, (size, shown) in groups.items():
                with self.subTest(cid=cid, ability_type=ability_type):
                    ids = list(types[ability_type])
                    self.assertEqual(size, len(ids))
                    self.assertEqual(shown, [i for i in ids if i not in hidden])

    def test_experience_texts_show_owned_values_with_inherited_part(
        self,
    ) -> None:
        """验证经验文本仅输出非零项并附带继承后数值。"""
        with kernel_data.writing():
            abilities.experience(self.a)[1] = 250
            abilities.experience(self.a)[3] = 9
            abilities.experience(self.a)[2] = 0
        name = game_config.config_experience[1].name
        texts = svc.experience_texts(self.a, 40)
        self.assertIn(f" {name}:250(→100)", texts)
        self.assertEqual(len(texts), 1)


class BackendIsolationTest(FastTestCase):
    """两服务无界面与无结算导入隔离测试。"""

    def test_services_run_without_ui_or_settle(self) -> None:
        """验证两服务在受限子进程中无受限导入且结果正确。"""
        child = run_ui_free(CHILD_RUN, boot=True)
        self.assertEqual((child.loaded, child.attempted), ([], []))
        plain, full = cast(list[list], child.payload["runs"])
        self.assertEqual(plain[0] + 9999, full[0])
        self.assertEqual(plain[1], [0] * 7)
        self.assertEqual(full[1][0], 220)
        self.assertEqual((plain[-1], full[-1]), (0, 16))
