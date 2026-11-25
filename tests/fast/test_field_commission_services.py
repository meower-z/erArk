"""
外勤委托后端服务测试
====================
验证外勤委托服务的列表过滤、需求解析、运载速度、编队与派遣写入。
验证选人服务的筛选排序、分页、出勤资格、装备加成与自动选人规则。
同时在拦截界面与结算导入的子进程中按多种编码验证两项服务可独立运行。
"""

import datetime
import os
from typing import Any, cast
from unittest import mock

from Script.Config import game_config
from Script.Design import game_time
from Script.Modules.domains import chara_life, chara_profile, commission
from Script.Modules.domains import facility, flags, location, modes
from Script.Modules.domains import relations, roster, wardrobe, warehouse
from Script.Modules.gameplay_resolution import (
    commission_roster_service as team_view,
)
from Script.Modules.gameplay_resolution import (
    field_commission_service as service,
)
from tests import chara_abilities, kernel_data
from tests.fast.base import FastTestCase
from tests.kernel_data import put
from tests.ui_free_subprocess import run_ui_free

ENCODINGS = ("cp1252", "gbk", "utf-16")
""" 无界面子进程测试覆盖的 PYTHONIOENCODING 编码列表。 """
HOME = 9001
""" 测试夹具中罗德岛当前所在地的虚构国家编号（9001）。 """
FIXTURES = """
from Script.Config import config_def, game_config


def make(table, kind, cid, **fields):
    data = kind()
    data.cid = cid
    for key, value in fields.items():
        setattr(data, key, value)
    table[cid] = data


RES = min(game_config.config_resouce)
SKILL = min(
    cid for cid, data in game_config.config_ability.items()
    if data.ability_type == 4
)
base = dict(name="c", country_id=-1, level=0, type="资源", people=1, time=3,
            demand="无", reward="无", related_id=-1, special=0, description="d")
rows = {
    9101: dict(base, demand=f"r_{RES}_5", people=2, level=1),
    9102: dict(base, special=1),
    9103: dict(base, related_id=9101),
    9104: dict(base, level=5),
    9105: dict(base, type="角色", demand="c_3_1&a_{0}_2".format(SKILL)),
    9106: dict(base, special=1, related_id=9102),
    9201: dict(base, country_id=9001, level=2),
    9202: dict(base, country_id=9001, level=0),
}
for cid, fields in rows.items():
    make(game_config.config_commission, config_def.Commission, cid, **fields)
game_config.config_commission_id_by_country[-1] = [9106, 9105, 9104, 9103, 9102, 9101]
game_config.config_commission_id_by_country[9001] = [9201, 9202]
for vid, speed, capacity, special in (
    (91, 3, 4, "加速"), (92, 12, 1, "无"), (93, 1, 2, "加速"), (94, 2, 2, "护甲")
):
    make(game_config.config_vehicle, config_def.Vehicle, vid, name=f"v{vid}",
         speed=speed, capacity=capacity, special=special)
"""
""" 向委托与载具配置表注入合成测试条目的共享脚本片段。 """
UI_FREE_RUN = FIXTURES + """
import datetime
from Script.Config import map_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, chara_profile, commission, facility
from Script.Modules.domains import flags
from Script.Modules.domains import identity, location, modes, relations, roster
from Script.Modules.domains import wardrobe, warehouse
from Script.Modules.gameplay_resolution import commission_roster_service as view
from Script.Modules.gameplay_resolution import field_commission_service as fc
from Script.Modules.gameplay_resolution import working
from tests import chara_abilities, kernel_data
from tests.chara_activity import place
from tests.world import DEFAULT_SCENE, start_time
map_config.init_map_data()
kernel_data.reset_clock(start_time(), {})
for cid in (0, 1, 2, 3):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", adv=cid))
    chara_abilities.zero_tables(cid)
    place(cid, DEFAULT_SCENE)
    if cid:
        kernel_data.put(roster.add, cid)
rows = []
with working.based_on(core.state()):
    warehouse.start({})
    warehouse.set(RES, 9)
    location.set_move(9001, game_time.now())
    location.arrive()
    facility.set_level(14, 0)
    commission.add_vehicle(91, 2, 0)
    commission.add_vehicle(92, 1, 1)
    abilities.talent(1)[201] = 1
    abilities.talent(2)[211] = 1
    abilities.ability(1)[SKILL] = 3
    abilities.ability(2)[SKILL] = 2
    wardrobe.set(1, "equipment_condition", 2)
    wardrobe.set(2, "equipment_condition", -2)
    chara_profile.chara_setting.set(2, {2: 1})
    relations.father_id.set(2, 0)
    rows.append([fc.visible_commissions(False), fc.visible_commissions(True)])
    modes.set_debug(True)
    rows.append([fc.visible_commissions(False), fc.visible_commissions(True)])
    modes.set_debug(False)
    rows.append([fc.required_advs(9105), fc.required_advs(9101)])
    rows.append([fc.demand_parts(9105, [1]), fc.demand_parts(9102, [])])
    chosen = {}
    fc.add_vehicle(chosen, 91)
    fc.add_vehicle(chosen, 91)
    fc.add_vehicle(chosen, 91)
    fc.add_vehicle(chosen, 92)
    fc.remove_vehicle(chosen, 92)
    rows.append([sorted(chosen.items()), fc.available_vehicles()])
    rows.append([fc.fleet_speed(chosen), fc.fleet_speed({}), fc.fleet_effects(chosen)])
    team = []
    lead = fc.toggle_member(team, 0, 1, 9101)
    lead = fc.toggle_member(team, lead, 2, 9101)
    lead = fc.toggle_member(team, lead, 3, 9101)
    lead = fc.toggle_member(team, lead, 1, 9101)
    lead = fc.toggle_member(team, lead, 1, 9101)
    ready = fc.readiness(9101, team, chosen)
    rows.append([list(team), lead, ready.all, ready.capacity, fc.default_lead(0, team)])
    picked = []
    view.auto_pick(9105, picked)
    state = view.RosterView(skill=SKILL)
    for key in ("filter_fall", "filter_fall", "filter_fall", "sort_col", f"sort_{SKILL}"):
        view.press(state, key)
    listed = [view.candidates(view.RosterView(), [])]
    for fall in range(5):
        listed.append(view.candidates(view.RosterView(filter_fall=fall), []))
    listed.append(view.candidates(state, [2]))
    rows.append([picked, listed, view.page_of(list(range(45)), 9)[:2]])
    rows.append([view.skill_value(1, SKILL, True), view.equipment_label(2), view.skill_value(2, SKILL, True)])
    rows.append([view.skill_columns()[0][1] == SKILL, view.can_dispatch(1)])
    fc.lead_first(team, 1)
    near = fc.dispatch(9101, team, chosen)
    far = fc.dispatch(9202, [3], {})
    gone = [flags.get(c, "field_commission") for c in (1, 2, 3)]
    rows.append([near.days, far.days, warehouse.amount(RES), gone])
    rows.append([sorted(roster.active()), commission.vehicles()[91]])
    rows.append(list(commission.ongoing()[9101].team))
payload["rows"] = rows
"""
""" 在无界面子进程中依次调用两项服务全部入口的测试脚本。 """

RES = min(game_config.config_resouce)
""" 测试使用的最小资源配置编号。 """
SKILL = min(
    cid
    for cid, data in game_config.config_ability.items()
    if data.ability_type == 4
)
""" 测试使用的最小工作技能配置编号。 """


class CommissionCase(FastTestCase):
    """为外勤委托服务测试提供合成配置、角色与初始机库环境的基类。"""

    def setUp(self) -> None:
        """打补丁注入合成委托与载具表并初始化角色、地点与机库。"""
        super().setUp()
        for table in (
            game_config.config_commission,
            game_config.config_commission_id_by_country,
            game_config.config_vehicle,
        ):
            self.enterContext(mock.patch.dict(table))
        exec(FIXTURES, {})
        self.world.chara(0, "博士")
        for cid, name in ((1, "甲"), (2, "乙"), (3, "丙")):
            self.world.chara(cid, name, adv=cid)
        with kernel_data.writing():
            location.set_move(HOME, game_time.now())
            location.arrive()
            facility.set_level(service.HANGAR, 0)


class ListingTest(CommissionCase):
    """外勤委托列表可见性与需求解析规则测试类。"""

    def test_rules_hide_locked_commissions(self) -> None:
        """验证前置、特殊已完成、禁接与机库等级对列表的过滤规则。"""
        self.assertEqual(service.visible_commissions(False), [9202, 9105, 9101])
        self.assertEqual(service.visible_commissions(True), [9102])
        put(commission.mark, 9101, 1)
        put(commission.mark, 9102, 1)
        put(facility.set_level, service.HANGAR, 4)
        self.assertEqual(
            service.visible_commissions(False),
            [9202, 9201, 9105, 9103, 9101, 9104],
        )
        self.assertEqual(service.visible_commissions(True), [9106])
        put(commission.mark, 9103, -1)
        self.assertNotIn(9103, service.visible_commissions(False))

    def test_character_commission_needs_recruit(self) -> None:
        """验证角色型委托要求指定干员在编才会在列表中显示。"""
        self.assertIn(9105, service.visible_commissions(False))
        put(roster.remove, 3)
        self.assertNotIn(9105, service.visible_commissions(False))

    def test_debug_lists_every_commission_of_the_tab(self) -> None:
        """验证 debug 模式跳过常规过滤并列出页签下全部委托。"""
        put(roster.remove, 3)
        put(modes.set_debug, True)
        self.assertEqual(
            service.visible_commissions(False),
            [9202, 9201, 9105, 9103, 9101, 9104],
        )
        self.assertEqual(service.visible_commissions(True), [9106, 9102])

    def test_demand_text_parts(self) -> None:
        """验证必需干员提取与逐项需求文本及满足状态判定。"""
        self.assertEqual(service.required_advs(9105), [3])
        self.assertEqual(service.required_advs(9101), [])
        self.assertEqual(service.demand_parts(9102, [1]), [])
        put(warehouse.set, RES, 5)
        ((text, met),) = service.demand_parts(9101, [1])
        self.assertTrue(met)
        self.assertIn("5", text)
        chara_abilities.ability(1)[SKILL] = 1
        parts = service.demand_parts(9105, [1])
        self.assertEqual([met for _text, met in parts], [False, False])
        self.assertEqual(
            [met for _text, met in service.demand_parts(9105, [1, 3])],
            [True, False],
        )


class SquadTest(CommissionCase):
    """外勤运载速度、编队成员、就绪检查与派遣写入测试类。"""

    def test_speed_capacity_and_days(self) -> None:
        """验证两套速度上限、运载量、特效去重与加速耗时换算。"""
        self.assertEqual(service.team_speed([]), 1)
        self.assertEqual(service.team_speed([91, 92]), 3)
        self.assertEqual(service.team_speed([92]), 9)
        self.assertEqual(service.fleet_speed({}), 1)
        self.assertEqual(service.fleet_speed({92: 1}), 12)
        self.assertEqual(service.fleet_capacity({91: 2, 93: 1}), 10)
        self.assertEqual(
            service.fleet_effects({91: 1, 92: 1, 93: 1, 94: 1}),
            ["加速", "护甲"],
        )
        self.assertEqual(service.capacity_need(9101), 4)
        self.assertIsNone(service.travel_minutes(3, 1))
        self.assertEqual(service.travel_days(3, 1), 3)
        self.assertEqual(service.travel_minutes(2, 3), 2099)
        self.assertEqual(service.travel_days(2, 3), 1.5)

    def test_vehicle_choice_is_capped_by_free_count(self) -> None:
        """验证可用载具查询及增减载具受空闲数量上限约束。"""
        put(commission.add_vehicle, 91, 3, 1)
        put(commission.add_vehicle, 92, 1, 1)
        self.assertEqual(service.available_vehicles(), [(91, 2)])
        chosen: dict[int, int] = {}
        for _ in range(3):
            service.add_vehicle(chosen, 91)
        self.assertEqual(chosen, {91: 2})
        service.add_vehicle(chosen, 92)
        self.assertEqual(chosen, {91: 2, 92: 0})
        service.remove_vehicle(chosen, 91)
        service.remove_vehicle(chosen, 92)
        service.remove_vehicle(chosen, 93)
        self.assertEqual(chosen, {91: 1})
        service.remove_vehicle(chosen, 91)
        self.assertEqual(chosen, {})

    def test_members_and_leader(self) -> None:
        """验证人员切换、人数上限、队长交接与队长前置排序。"""
        team: list[int] = []
        lead = service.toggle_member(team, 0, 2, 9101)
        lead = service.toggle_member(team, lead, 1, 9101)
        self.assertEqual((team, lead), ([2, 1], 2))
        self.assertEqual(service.toggle_member(team, lead, 3, 9101), 2)
        self.assertEqual(team, [2, 1])
        self.assertEqual(service.toggle_member(team, lead, 1, 9101), 2)
        self.assertEqual(service.toggle_member(team, 2, 1, 9101), 2)
        self.assertEqual(service.toggle_member(team, 2, 2, 9101), 1)
        self.assertEqual(service.toggle_member(team, 1, 1, 9101), 0)
        self.assertEqual(team, [])
        self.assertEqual(service.default_lead(0, [3, 1]), 3)
        self.assertEqual(service.default_lead(2, [3, 1]), 2)
        self.assertEqual(service.default_lead(0, []), 0)
        team = [3, 1, 2]
        service.lead_first(team, 2)
        self.assertEqual(team, [2, 3, 1])

    def test_readiness(self) -> None:
        """验证人数、运载量与额外需求三项就绪标志的综合判定。"""
        put(warehouse.set, RES, 5)
        ready = service.readiness(9101, [1], {91: 1})
        self.assertEqual(
            (ready.people, ready.capacity, ready.capacity_ok, ready.demand),
            (False, 4, True, True),
        )
        self.assertFalse(ready.all)
        self.assertTrue(service.readiness(9101, [1, 2], {91: 1}).all)
        self.assertFalse(service.readiness(9101, [1, 2], {93: 1}).all)
        put(warehouse.set, RES, 4)
        self.assertFalse(service.readiness(9101, [1, 2], {91: 1}).all)

    def test_dispatch_spends_and_sends(self) -> None:
        """验证派遣扣资源、设标记、离队、占载具与返回时间计算。"""
        put(warehouse.set, RES, 7)
        put(commission.add_vehicle, 91, 2, 0)
        put(commission.add_vehicle, 94, 1, 0)
        start = game_time.now()
        with kernel_data.writing():
            near = service.dispatch(9101, [2, 1], {91: 1, 94: 0})
            far = service.dispatch(9202, [3], {})
        self.assertEqual((near.days, far.days), (2.2, 3))
        self.assertEqual(
            near.returns_at - start, datetime.timedelta(minutes=3149)
        )
        self.assertEqual(far.returns_at - start, datetime.timedelta(days=3))
        self.assertEqual(warehouse.amount(RES), 2)
        self.assertEqual(
            [flags.get(c, "field_commission") for c in (1, 2, 3)],
            [9101, 9101, 9202],
        )
        self.assertEqual(sorted(roster.active()), [])
        self.assertEqual(commission.vehicles()[91], (2, 1))
        self.assertEqual(commission.vehicles()[94], (1, 0))
        going = commission.ongoing()
        self.assertEqual(list(going[9101].team), [2, 1])
        self.assertEqual(list(going[9101].vehicles), [91])
        self.assertEqual(list(going[9202].vehicles), [])


class TeamViewTest(CommissionCase):
    """外勤选人界面状态、筛选排序、出勤资格与分页测试类。"""

    def test_press_cycles_and_resets_page(self) -> None:
        """验证选人按键状态机对翻页、筛选、排序与装备开关的处理。"""
        view = team_view.RosterView(page=2)
        team_view.press(view, "222")
        team_view.press(view, "toggle_equip")
        self.assertEqual((view.page, view.equipment), (3, False))
        for _ in range(5):
            team_view.press(view, "filter_fall")
        self.assertEqual((view.filter_fall, view.page), (0, 0))
        team_view.press(view, "888")
        team_view.press(view, "filter_work")
        team_view.press(view, "sort_sel")
        team_view.press(view, f"sort_{SKILL}")
        team_view.press(view, "返回")
        self.assertEqual(
            (view.page, view.filter_work, view.selected_first, view.skill),
            (0, 1, False, SKILL),
        )

    def test_filters_and_sort(self) -> None:
        """验证工作、陷落、女儿、收藏筛选及各类排序优先级。"""
        chara_abilities.talent(1)[201] = 1
        chara_abilities.talent(2)[211] = 1
        put(chara_life.work_type.set, 3, 22)
        put(chara_profile.chara_setting.set, 2, {2: 1})
        put(relations.father_id.set, 1, 0)
        put(roster.add, 0)

        def ids(**fields: Any) -> list[int]:
            return team_view.candidates(team_view.RosterView(**fields), [3])

        self.assertEqual(ids(), [3, 1, 2])
        self.assertEqual(ids(selected_first=False), [1, 2, 3])
        self.assertEqual(ids(filter_work=1), [3])
        self.assertEqual(ids(filter_work=2), [1, 2])
        self.assertEqual(
            [ids(filter_fall=f) for f in (1, 2, 3, 4)], [[3], [1, 2], [1], [2]]
        )
        self.assertEqual(ids(filter_daughter=1), [1])
        self.assertEqual(ids(filter_collection=2), [3, 1])
        self.assertEqual(
            ids(selected_first=False, collection_first=True), [2, 1, 3]
        )
        self.assertEqual(ids(selected_first=False, work_sort=True), [1, 2, 3])
        put(chara_life.work_type.set, 1, 131)
        self.assertEqual(ids(selected_first=False, work_sort=True), [2, 3, 1])
        chara_abilities.ability(2)[SKILL] = 5
        self.assertEqual(ids(selected_first=False, skill=SKILL), [2, 1, 3])

    def test_dispatch_rules_and_equipment(self) -> None:
        """验证装备修正与标签、出勤排除条件及必需干员自动选人。"""
        for cid, value, condition in ((1, 7, 2), (2, 3, -2), (3, 8, 2)):
            chara_abilities.ability(cid)[SKILL] = value
            put(wardrobe.set, cid, "equipment_condition", condition)
        values = [team_view.skill_value(c, SKILL, True) for c in (1, 2, 3)]
        self.assertEqual(values, [8, 2, 8])
        self.assertEqual(team_view.skill_value(1, SKILL, False), 7)
        chara_abilities.ability(2)[SKILL] = 0
        self.assertEqual(team_view.skill_value(2, SKILL, True), 0)
        labels = [team_view.equipment_label(c)[1] for c in (1, 2)]
        self.assertEqual(labels, ["spring_green", "red"])
        put(wardrobe.set, 3, "equipment_condition", 0)
        self.assertEqual(team_view.equipment_label(3)[1], "standard")
        self.assertTrue(team_view.can_dispatch(1))
        put(wardrobe.set, 1, "equipment_condition", -3)
        put(flags.set, 2, vistor=1)
        self.assertEqual(team_view.candidates(team_view.RosterView(), []), [3])
        team: list[int] = [1]
        team_view.auto_pick(9105, team)
        self.assertEqual(team, [1, 3])
        team_view.auto_pick(9105, team)
        self.assertEqual(team, [1, 3])
        put(flags.set, 3, vistor=1)
        team = []
        team_view.auto_pick(9105, team)
        self.assertEqual(team, [])

    def test_paging_and_columns(self) -> None:
        """验证选人列表分页钳制及工作技能列简称生成。"""
        ids = list(range(45))
        self.assertEqual(team_view.page_of(ids, 9)[:2], (2, 3))
        self.assertEqual(team_view.page_of(ids, 9)[2], ids[40:])
        self.assertEqual(team_view.page_of(ids, -1)[2], ids[:20])
        self.assertEqual(team_view.page_of([], 3)[:2], (0, 1))
        names = [cid for _name, cid in team_view.skill_columns()]
        self.assertIn(SKILL, names)
        other = min(
            cid
            for cid, data in game_config.config_ability.items()
            if data.ability_type not in (0, team_view.WORK_SKILL)
        )
        self.assertNotIn(other, names)
        self.assertTrue(
            all(
                not name.endswith("技能")
                for name, _ in team_view.skill_columns()
            )
        )


class UiFreeRunTest(FastTestCase):
    """外勤委托与选人服务无界面子进程隔离运行测试类。"""

    def test_services_run_without_ui_or_settle(self) -> None:
        """验证两项服务在三种编码下均不导入界面与结算模块并结果正确。"""
        for encoding in ENCODINGS:
            with self.subTest(encoding):
                with mock.patch.dict(
                    os.environ, {"PYTHONIOENCODING": encoding}
                ):
                    run = run_ui_free(UI_FREE_RUN, boot=True)
                self.assertEqual((run.loaded, run.attempted), ([], []))
                rows = cast(list[Any], run.payload["rows"])
                self.assertEqual(rows[0], [[9202, 9105, 9101], [9102]])
                self.assertEqual(
                    rows[1],
                    [[9202, 9201, 9105, 9103, 9101, 9104], [9106, 9102]],
                )
                self.assertEqual(rows[2], [[3], []])
                self.assertEqual([met for _t, met in rows[3][0]], [False, True])
                self.assertEqual(rows[4], [[[91, 2]], [[91, 2]]])
                self.assertEqual(rows[5], [3, 1, ["加速"]])
                self.assertEqual(rows[6], [[2, 1], 2, True, 8, 2])
                fall = [[1, 2, 3], [3], [1, 2], [1], [2]]
                self.assertEqual(
                    rows[7], [[3], [[1, 2, 3], *fall, [1]], [2, 3]]
                )
                self.assertEqual(rows[8], [4, ["损坏", "red"], 1])
                self.assertEqual(rows[10], [2.2, 3, 4, [9101, 9101, 9202]])
                self.assertEqual(rows[11], [[], [2, 2]])
                self.assertEqual(rows[12], [1, 2])
