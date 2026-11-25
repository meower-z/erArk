"""
基建管理后端服务测试
====================
验证基建总览、全干员列表与岗位指派三项服务的查询、筛选排序与写入行为。
同时在拦截界面与结算模块导入的独立子进程中按多种终端编码运行上述服务，
确认无受限模块被加载或尝试导入。
"""

import datetime
import os
from unittest import mock

from Script.Config import game_config
from Script.Design import game_time, map_handle
from Script.Modules.domains import body_manage, chara_life
from Script.Modules.domains import chara_profile, commission, facility, flags
from Script.Modules.domains import maintenance, prison, recruit, relations
from Script.Modules.domains import roster, visitor, wardrobe, warehouse, work
from Script.Modules.gameplay_resolution import (
    basement_overview_service as overview,
)
from Script.Modules.gameplay_resolution import (
    operator_list_service as roster_view,
)
from Script.Modules.gameplay_resolution import (
    work_assignment_service as assignment,
)
from tests import chara_abilities, kernel_data
from tests.fast.base import FastTestCase
from tests.kernel_data import put
from tests.ui_free_subprocess import run_ui_free

ENCODINGS = ("cp1252", "gbk", "utf-16")
""" 无界面子进程测试覆盖的 PYTHONIOENCODING 编码列表。 """
NO_FILTER = {key: 0 for key in roster_view.FILTER_STEPS}
""" 五项筛选维度均为不筛选（0）的默认筛选字典。 """
SMITH = 22
""" 铁匠岗位的工作类型编号（22）。 """
DIPLOMAT = 131
""" 外交官岗位的工作类型编号（131）。 """
SMITHY = 13
""" 铁匠铺对应的待开放设施编号（13）。 """
OFFICE = 131
""" 外交办公室对应的待开放设施编号（131）。 """
PRISON_DORM = map_handle.get_map_system_path_str_for_list(["关押", "休息室"])
""" 关押区休息室的地图系统路径字符串。 """
UI_FREE_RUN = """
import datetime
from Script.Config import game_config, map_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, body_manage, chara_life, commission
from Script.Modules.domains import facility, identity, maintenance, prison
from Script.Modules.domains import recruit, roster, wardrobe, warehouse, work
from Script.Modules.gameplay_resolution import basement_overview_service as overview
from Script.Modules.gameplay_resolution import operator_list_service as roster_view
from Script.Modules.gameplay_resolution import work_assignment_service as assignment
from Script.Modules.gameplay_resolution import working
from tests import chara_abilities, kernel_data
from tests.chara_activity import place
from tests.world import DEFAULT_SCENE, start_time
map_config.init_map_data()
kernel_data.reset_clock(start_time(), {})
for cid in (0, 1, 2, 3):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", sex=1))
    chara_abilities.zero_tables(cid)
    place(cid, DEFAULT_SCENE)
    if cid:
        kernel_data.put(roster.add, cid)
last = {key: steps - 1 for key, steps in roster_view.FILTER_STEPS.items()}
none = {key: 0 for key in last}
keys = ["无", "默认ID", "好感", "信赖", "体力", "最大体力", "气力", "最大气力"]
keys += ["催眠深度", "工作", "装备", "皮肤"]
gates = ["[装备维护系统]", "[烹饪系统]", "[监禁调教系统]", "[基建系统]"]
back = game_time.now() + datetime.timedelta(days=3)
with working.based_on(core.state()):
    abilities.talent(1)[203] = 1
    abilities.talent(2)[211] = 1
    wardrobe.set(1, "equipment_condition", 2)
    wardrobe.set(2, "equipment_condition", -2)
    body_manage.set(3, 31, 1)
    chara_life.work_type.set(3, 193)
    warehouse.set(1, 5)
    prison.imprison(2, game_time.now())
    maintenance.set_damage("S1", 2)
    maintenance.set_place(1, "S2")
    recruit.open_lines([0])
    recruit.set_pending([1])
    commission.start(min(game_config.config_commission), [1], back, [])
    commission.add_vehicle(min(game_config.config_vehicle), 1, 0)
    rows = overview.stock_rows("货币") + [overview.capacity(), overview.income()]
    rows += [overview.staffing(), roster_view.page_of(41, 9)]
    text = "".join(
        overview.staff_text(d) + overview.department_text(d)
        for d in overview.departments()
    )
    notices = [overview.entry_notice(label) for label in gates]
    rows.append(roster_view.visible_ids(last, "无", "无", False, True))
    for key in keys:
        rows.append(roster_view.visible_ids(none, key, key, True, False))
    labels = [
        [
            roster_view.fall_label(c)[0],
            roster_view.equipment_label(c)[0],
            roster_view.work_name(c),
        ]
        for c in (1, 2, 3)
    ]
    rows += [roster_view.position_text(1), roster_view.is_collected(1)]
    rows += [roster_view.operator_ids(), assignment.current_work_text(1)]
    rows += [assignment.refresh_groups(), assignment.work_options(1)]
    facility.set_open(13, True)
    notices.append(overview.entry_notice(gates[0]))
    assignment.assign_work(1, 191)
    assignment.assign_work(2, 191)
    assignment.assign_work(2, 22)
    assignment.assign_work(3, 0)
    after = [work.warden(), chara_life.work_type(1), chara_life.work_type(2)]
    after.append(body_manage.of(3).get(31, 0))
payload["text"] = text
payload["labels"] = labels
payload["after"] = after
payload["notices"] = [notice is None for notice in notices]
"""
""" 在无界面与无结算子进程中执行三项服务全部入口的测试脚本。 """


class BasementCase(FastTestCase):
    """基建服务单元测试基类，预置博士与三名测试干员。"""

    def setUp(self) -> None:
        """初始化世界状态并创建博士与甲、乙、丙三名干员。"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid, name in ((1, "甲"), (2, "乙"), (3, "丙")):
            self.world.chara(cid, name, adv=cid * 7)


class OverviewTest(BasementCase):
    """验证 basement_overview_service 各查询与提示逻辑的测试集。"""

    def test_stock_rows_keep_only_the_kind(self) -> None:
        """验证 stock_rows 仅返回匹配资源类型的库存条目。"""
        money = [
            r for r, d in game_config.config_resouce.items() if d.type == "货币"
        ]
        other = [
            r for r, d in game_config.config_resouce.items() if d.type == "材料"
        ]
        put(warehouse.set, money[0], 77)
        put(warehouse.set, other[0], 5)
        rows = dict(overview.stock_rows("货币"))
        self.assertEqual(rows[game_config.config_resouce[money[0]].name], 77)
        self.assertNotIn(game_config.config_resouce[other[0]].name, rows)

    def test_staff_text_counts_rosters_teams_and_prisoners(self) -> None:
        """验证 staff_text 正确统计岗位人数、外勤干员数与囚犯数。"""
        put(work.set_rosters, {21: [1, 2], 22: [3]})
        self.assertEqual(
            overview.staff_text("工程部"), "  检修工程师 — 2  铁匠 — 1"
        )
        end = game_time.now() + datetime.timedelta(days=2)
        put(commission.start, 1, [1, 2], end, [])
        self.assertTrue(overview.staff_text("机库").endswith("  外勤干员 — 2"))
        put(prison.imprison, 3, game_time.now())
        self.assertTrue(overview.staff_text("关押区").endswith("  囚犯 — 1"))

    def test_engineering_grid_wraps_every_three(self) -> None:
        """验证工程部故障与检修文本按每行三项换行且空时显示无。"""
        empty = overview.department_text("工程部")
        self.assertIn("当前故障地点与设施损坏数：\n    无", empty)
        for index in range(4):
            put(maintenance.set_damage, f"S{index}", index + 1)
        put(maintenance.set_place, 2, "S9")
        text = overview.department_text("工程部")
        self.assertIn("\n    S0-1    S1-2    S2-3\n    S3-4", text)
        self.assertIn("当前检修人员与其负责地点：\n    乙-S9", text)

    def test_roster_names_or_none(self) -> None:
        """验证部门详情列出岗位在岗姓名、读者数及空岗位的暂无文案。"""
        put(work.set_rosters, {101: [1, 3]})
        text = overview.department_text("图书馆")
        self.assertIn("当前正在工作的图书馆管理员： 甲 丙", text)
        self.assertIn("当前读者人数：0 人", text)
        self.assertIn(
            "当前正在工作的招募专员： 暂无", overview.department_text("文职部")
        )

    def test_clerical_lists_pending_and_first_four_lines(self) -> None:
        """验证文职部详情展示待确认人数且仅列出前四个招募位进度。"""
        self.assertIn("当前没有已招募干员", overview.department_text("文职部"))
        put(recruit.open_lines, [0, 4])
        put(recruit.set_line, 0, progress=12.34)
        put(recruit.set_pending, [1, 2])
        text = overview.department_text("文职部")
        self.assertIn("当前已招募未确认干员人数为：2人", text)
        self.assertIn("1号招募位进度：12.3%/100%", text)
        self.assertNotIn("5号招募位", text)

    def test_hangar_days_and_vehicles(self) -> None:
        """验证机库详情正确格式化委托剩余天数与非零载具数量。"""
        self.assertIn(
            "当前外勤委托情况：\n  无", overview.department_text("机库")
        )
        first, second = sorted(game_config.config_commission)[:2]
        now = game_time.now()
        put(
            commission.start,
            first,
            [1, 2],
            now + datetime.timedelta(hours=5),
            [],
        )
        put(commission.start, second, [3], now + datetime.timedelta(days=4), [])
        vehicles = sorted(game_config.config_vehicle)
        put(commission.add_vehicle, vehicles[0], 2, 1)
        put(commission.add_vehicle, vehicles[1], 0, 0)
        text = overview.department_text("机库")
        name = game_config.config_commission[first].name
        self.assertIn(f"[{name}]：甲、乙，剩余不足一天", text)
        self.assertIn("丙，剩余4天", text)
        car = game_config.config_vehicle[vehicles[0]].name
        self.assertIn(f"[{car}]：可用2辆，出动中1辆", text)
        self.assertNotIn(game_config.config_vehicle[vehicles[1]].name, text)

    def test_dormitory_counts_people_against_capacity(self) -> None:
        """验证宿舍区详情包含干员总数与宿舍容量且以换行结尾。"""
        text = overview.department_text("宿舍区")
        self.assertIn(f"干员总数/宿舍容量：3/{facility.people_max()}", text)
        self.assertTrue(text.endswith("\n"))

    def test_entry_notice_gates(self) -> None:
        """验证装备维护、烹饪、监禁调教与基建系统的入口提示分支。"""
        self.assertIn(
            "铁匠铺未开放", str(overview.entry_notice("[装备维护系统]"))
        )
        put(facility.set_open, SMITHY, True)
        self.assertIsNone(overview.entry_notice("[装备维护系统]"))
        self.assertIn("厨房", str(overview.entry_notice("[烹饪系统]")))
        self.assertIn(
            "未任命监狱长", str(overview.entry_notice("[监禁调教系统]"))
        )
        put(work.set_warden, 2)
        self.assertIsNone(overview.entry_notice("[监禁调教系统]"))
        self.assertIsNone(overview.entry_notice("[基建系统]"))


class OperatorListTest(BasementCase):
    """验证 operator_list_service 筛选、排序、分页与标签逻辑。"""

    def ids(self, **changes: int) -> list[int]:
        """按覆盖筛选参数 changes 返回默认排序的可见干员编号列表。"""
        filters = {**NO_FILTER, **changes}
        return roster_view.visible_ids(filters, "默认ID", "无", False, False)

    def test_filters(self) -> None:
        """验证工作、陷落、女儿、访客与收藏五项筛选条件的过滤结果。"""
        put(roster.add, 0)
        put(chara_life.work_type.set, 1, 21)
        put(relations.father_id.set, 2, 0)
        put(flags.set, 3, vistor=1)
        put(chara_profile.chara_setting.set, 3, {2: 1})
        chara_abilities.talent(1)[201] = 1
        chara_abilities.talent(2)[211] = 1
        self.assertEqual(self.ids(), [1, 2, 3])
        self.assertEqual((self.ids(work=1), self.ids(work=2)), ([1], [2, 3]))
        self.assertEqual(
            [self.ids(fall=v) for v in range(1, 5)], [[3], [1, 2], [1], [2]]
        )
        self.assertEqual(
            (self.ids(daughter=1), self.ids(daughter=2)), ([2], [1, 3])
        )
        self.assertEqual(
            (self.ids(visitor=1), self.ids(visitor=2)), ([3], [1, 2])
        )
        self.assertEqual(
            (self.ids(collection=1), self.ids(collection=2)), ([3], [1, 2])
        )

    def test_sort_keys_collection_and_reverse(self) -> None:
        """验证主副排序、整体倒序与收藏优先对干员列表顺序的影响。"""
        for cid, favor in ((1, 30), (2, 10), (3, 20)):
            put(relations.favorability.set, cid, {0: favor})
        self.assertEqual(
            roster_view.visible_ids(NO_FILTER, "好感", "无", False, False),
            [2, 3, 1],
        )
        self.assertEqual(
            roster_view.visible_ids(NO_FILTER, "好感", "无", True, False),
            [1, 3, 2],
        )
        put(chara_profile.chara_setting.set, 1, {2: 1})
        self.assertEqual(
            roster_view.visible_ids(NO_FILTER, "好感", "无", False, True),
            [1, 2, 3],
        )
        self.assertEqual(
            roster_view.visible_ids(NO_FILTER, "无", "默认ID", True, False),
            [3, 2, 1],
        )

    def test_ability_column_key_and_equipment_rank(self) -> None:
        """验证能力列排序键、未知键回退 0 与装备维护排序分值。"""
        columns = roster_view.ability_columns()
        self.assertIn(("皮肤", 0), columns[0])
        chara_abilities.ability(2)[0] = 5
        self.assertEqual(roster_view.sort_value(2, "皮肤", columns), 5)
        self.assertEqual(roster_view.sort_value(2, "不存在", columns), 0)
        put(wardrobe.set, 1, "equipment_condition", 2)
        put(wardrobe.set, 3, "equipment_condition", -2)
        ranks = [roster_view.sort_value(c, "装备", columns) for c in (1, 2, 3)]
        self.assertEqual(ranks, [2, 0, -1])

    def test_page_of_clamps(self) -> None:
        """验证 page_of 在空列表、越界页码与负页码时的钳制结果。"""
        self.assertEqual(roster_view.page_of(0, 3), (0, 1))
        self.assertEqual(roster_view.page_of(41, 9), (2, 3))
        self.assertEqual(roster_view.page_of(40, -1), (0, 2))

    def test_labels(self) -> None:
        """验证陷落标签优先级、装备状态标签与非玩家干员编号列表。"""
        self.assertEqual(roster_view.fall_label(1), ("无", "standard"))
        chara_abilities.talent(1)[211] = 1
        chara_abilities.talent(1)[202] = 1
        self.assertEqual(roster_view.fall_label(1), ("恋慕", "deep_pink"))
        put(wardrobe.set, 2, "equipment_condition", -2)
        put(wardrobe.set, 3, "equipment_condition", 2)
        self.assertEqual(
            [roster_view.equipment_label(c) for c in (1, 2, 3)],
            [("正常", "standard"), ("损坏", "red"), ("完美", "spring_green")],
        )
        put(roster.add, 0)
        self.assertEqual(roster_view.operator_ids(), [1, 2, 3])


class WorkAssignmentTest(BasementCase):
    """验证 work_assignment_service 分组、选项判定与岗位写入。"""

    def test_groups_skip_visitors_and_prisoners(self) -> None:
        """验证 refresh_groups 刷新名册并跳过访客与被监禁干员。"""
        put(chara_life.work_type.set, 1, SMITH)
        put(chara_life.work_type.set, 2, SMITH)
        chara_abilities.ability(1)[48] = 3
        put(visitor.arrive, 3, game_time.now())
        with kernel_data.writing():
            groups = {g.work_id: g for g in assignment.refresh_groups()}
        self.assertEqual(work.roster(SMITH), (1, 2))
        put(flags.set, 2, imprisonment=1)
        with kernel_data.writing():
            again = {g.work_id: g for g in assignment.refresh_groups()}
        self.assertEqual(groups[SMITH].label, "铁匠(制造)(2人)")
        self.assertEqual(groups[0].members, ())
        self.assertEqual(
            [m.label for m in groups[SMITH].members],
            ["[0007]甲(lv3)", "[0014]乙(lv0)"],
        )
        self.assertEqual([m.chara_id for m in again[SMITH].members], [1])

    def option(self, chara_id: int, work_id: int) -> assignment.WorkOption:
        """返回角色 chara_id 在指定岗位 work_id 对应的 WorkOption。"""
        return {o.work_id: o for o in assignment.work_options(chara_id)}[
            work_id
        ]

    def test_facility_need_and_grey_tag(self) -> None:
        """验证设施开放、need 条件与 tag 为 1 的灰显岗位判定及文案。"""
        smith = self.option(1, SMITH)
        self.assertEqual((smith.pickable, smith.locked_reason), (False, "无"))
        put(facility.set_open, SMITHY, True)
        self.assertEqual(self.option(1, SMITH).pickable, True)
        diplomat = self.option(1, DIPLOMAT)
        self.assertFalse(diplomat.pickable)
        self.assertTrue(
            str(diplomat.locked_reason).startswith(
                "需要在[外交势力]系统中任命 需要:"
            )
        )
        self.assertTrue(
            self.option(1, SMITH).text.startswith(
                "[022]铁匠(铁匠铺)" + "　" * 6 + "(制造:0)："
            )
        )
        self.assertTrue(
            self.option(1, 92).text.startswith(
                "[092]健身锻炼员(健身区)" + "　" * 7 + "："
            )
        )
        put(facility.set_open, OFFICE, True)
        diplomat = self.option(1, DIPLOMAT)
        self.assertEqual(
            (diplomat.pickable, diplomat.locked_reason),
            (False, "需要在[外交势力]系统中任命"),
        )
        put(
            facility.set_open,
            game_config.config_facility_open_name_to_cid["温室"],
            True,
        )
        florist = self.option(1, 162)
        self.assertFalse(florist.pickable)
        self.assertIn("需要:", str(florist.locked_reason))

    def test_special_unlocks(self) -> None:
        """验证 191 监狱长与 193 性爱练习生的特殊解锁条件及当前工作文案。"""
        self.assertFalse(self.option(1, 191).pickable)
        chara_abilities.talent(1)[213] = 1
        self.assertFalse(self.option(1, 191).pickable)
        put(prison.imprison, 2, game_time.now())
        self.assertTrue(self.option(1, 191).pickable)
        self.assertFalse(self.option(1, 193).pickable)
        put(body_manage.set, 1, 35, 1)
        self.assertTrue(self.option(1, 193).pickable)
        self.assertIn("甲的当前工作为：无(无)", assignment.current_work_text(1))

    def test_warden_swap_and_trainee_reset(self) -> None:
        """验证监狱长交接、宿舍恢复，以及练习生改岗时清空训练项。"""
        with kernel_data.writing():
            assignment.assign_work(1, 191)
        self.assertEqual(
            (work.warden(), chara_life.dormitory(1)), (1, PRISON_DORM)
        )
        with kernel_data.writing():
            assignment.assign_work(2, 191)
        self.assertEqual(
            (work.warden(), chara_life.work_type(1), chara_life.work_type(2)),
            (2, 0, 191),
        )
        self.assertNotEqual(chara_life.dormitory(1), PRISON_DORM)
        with kernel_data.writing():
            assignment.assign_work(2, SMITH)
        self.assertEqual((work.warden(), chara_life.work_type(2)), (0, SMITH))
        put(chara_life.work_type.set, 3, 193)
        put(body_manage.set, 3, 31, 1)
        with kernel_data.writing():
            assignment.assign_work(3, 0)
        self.assertEqual(body_manage.of(3).get(31, 0), 0)
        self.assertEqual(work.roster(SMITH), (2,))


class UiFreeRunTest(FastTestCase):
    """验证三项基建服务在拦截界面与结算模块的子进程中可运行。"""

    def test_services_run_without_ui_or_settle(self) -> None:
        """在三种终端编码下通过 run_ui_free 运行服务并校验输出与零拦截。"""
        for encoding in ENCODINGS:
            with self.subTest(encoding):
                with mock.patch.dict(
                    os.environ, {"PYTHONIOENCODING": encoding}
                ):
                    run = run_ui_free(UI_FREE_RUN, boot=True)
                self.assertEqual((run.loaded, run.attempted), ([], []))
                self.assertEqual(run.payload["after"], [0, 0, 22, 0])
                self.assertEqual(
                    run.payload["notices"], [False, False, False, True, True]
                )
                self.assertEqual(
                    run.payload["labels"],
                    [
                        ["恋人", "完美", "无"],
                        ["屈从", "损坏", "无"],
                        ["无", "正常", "性爱练习生"],
                    ],
                )
                for part in (
                    "S1-2",
                    "c1-S2",
                    "1号招募位进度",
                    "剩余3天",
                    "干员总数",
                    "当前读者人数",
                    "囚犯 — 1",
                ):
                    self.assertIn(part, str(run.payload["text"]))
