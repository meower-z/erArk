"""
宿舍管理后端服务测试
====================
验证宿舍房间服务与宿舍管理员服务的查询、分配、排序与任免逻辑。
同时在拦截界面与结算模块导入的独立子进程中按多种终端编码运行，
确认两项服务均不加载或尝试导入受限模块。
"""

import os
from unittest import mock

from Script.Design import basement, map_handle
from Script.Modules.domains import activity, chara_life, dormitory, flags
from Script.Modules.domains import inventory, roster, work
from Script.Modules.gameplay_resolution import (
    dormitory_manager_service as managers,
)
from Script.Modules.gameplay_resolution import dormitory_room_service as rooms
from Script.System.Dormitory_System import common
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.kernel_data import put
from tests.ui_free_subprocess import run_ui_free

ENCODINGS = ("cp1252", "gbk", "utf-16")
""" 无界面子进程测试覆盖的 PYTHONIOENCODING 编码列表。 """
UI_FREE_RUN = """
from Script.Config import map_config
from Script.Design import attr_calculation
from Script.Modules.domains import chara_life, dormitory, flags, identity
from Script.Modules.domains import inventory, relations, roster, work
from Script.Modules.gameplay_resolution import dormitory_manager_service as managers
from Script.Modules.gameplay_resolution import dormitory_room_service as rooms
from Script.System.Dormitory_System import common
from tests import chara_abilities, kernel_data
from tests.chara_activity import place
from tests.world import DEFAULT_SCENE, start_time
map_config.init_map_data()
kernel_data.reset_clock(start_time(), {})
for cid in range(15):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", sex=1, adv=cid))
    chara_abilities.zero_tables(cid)
    services = attr_calculation.get_assistant_services_zero()
    kernel_data.put(relations.assistant_services.set, cid, services)
    place(cid, DEFAULT_SCENE)
    if cid:
        kernel_data.put(roster.add, cid)
paths = [p for _n, p in common.get_open_dormitory_rooms_by_layer()[1]]
homes = [0, 0, 0] + [1 + i // 2 for i in range(10)] + [0]
blank = rooms.TempBlank()
with kernel_data.writing():
    for cid, room in zip(range(1, 15), homes):
        chara_life.dormitory.set(cid, paths[room])
    flags.set(14, field_commission=1)
    roster.discard(14)
    for cid in (5, 6):
        chara_life.work_type.set(cid, managers.MANAGER_WORK)
    inventory.set_item(0, 301, 1)
    inventory.set_item(0, 302, 1)
    layers = managers.layer_managers()
    size = rooms.capacity(paths[0], rooms.occupancy())
    text = rooms.overview_text(blank.current(), layers)
    rows = [rooms.selectable_ids(), rooms.has_overcrowded_room()]
    rows += [rooms.can_change_room(c) for c in (1, 0, 14)]
    rows += [rooms.room_name(""), rooms.room_name("x"), len(rooms.room_choices(4))]
    rows += [rooms.change_header(1, [1])[0], managers.unassigned_manager_names()]
    rows.append(managers.manager_candidates())
    notes = [rooms.redistribute(), rooms.move_to_blank(1, blank)]
    notes += [rooms.move_to_blank(2, blank), rooms.auto_sort(blank)]
    notes.append(rooms.move_to_blank(13, blank))
    labels = [choice.label for choice in rooms.room_choices(1)]
    notes.append(rooms.auto_sort(blank))
    notes += [rooms.redistribute(), rooms.set_room(2, paths[0], blank)]
    notes += [managers.appoint(1, 5), managers.appoint(2, 5)]
    notes += [managers.appoint(2, 6), rooms.redistribute(), managers.dismiss(2)]
    notes += [managers.dismiss(3)]
    rows.append(managers.reset_unassigned_managers())
    after = [
        paths.index(chara_life.dormitory(c)) if chara_life.dormitory(c) in paths else -1
        for c in range(1, 15)
    ]
    after += [dormitory.managers().get(n, 0) for n in (1, 2)]
    after += [inventory.items(0)[n] for n in (301, 302)]
    after += [list(work.roster(managers.MANAGER_WORK)), blank.current()]
payload["text"] = text
payload["size"] = size
payload["labels"] = labels
payload["rows"] = [repr(row) for row in rows]
payload["waits"] = [None if n is None else n.wait for n in notes]
payload["lines"] = [len(n.lines) for n in notes if n is not None]
payload["flags"] = rows[1:5]
payload["after"] = after
"""
""" 在无界面与无结算子进程中执行两项服务全部公开入口的脚本。 """
WAITS = [
    "\n○当前剩余宿舍空位不足以重新分配，请升级宿舍后重试。\n",
    "\n○c1 已从 宿舍101房 移入临时空白位\n",
    "\n○c2 已从 宿舍101房 移入临时空白位\n",
    "\n○当前没有可用宿舍位置，无法进行自动排序\n",
    "\n○c13 已从 宿舍106房 移入临时空白位\n",
    "\n○已自动安置1名干员进入宿舍\n○仍有2名干员留在临时空白位（宿舍可用位置不足）\n",
    None,
    "\n○c2 的宿舍已从 暂无 调整为 宿舍101房\n",
    "\n○已任命 c5 为 1层宿舍管理员\n",
    "\n○已任命 c5 为 2层宿舍管理员\n",
    "\n○已任命 c6 为 2层宿舍管理员\n",
    "\n○已完成重新分配，共分配了1名角色。\n",
    "\n○已撤换 2层宿舍管理员\n",
    "\n○该层当前没有已任命管理员\n",
]
""" 无界面子进程脚本依次执行各操作后的预期等待提示列表。 """


class DormitoryCase(FastTestCase):
    """宿舍服务单元测试基类，预置博士与四名测试干员。"""

    def setUp(self) -> None:
        """初始化世界状态、测试角色、一楼宿舍路径与空白位。"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid, name in ((1, "甲"), (2, "乙"), (3, "丙"), (4, "丁")):
            self.world.chara(cid, name, adv=50 - cid)
            put(chara_life.dormitory.set, cid, "")
        self.paths = [
            path for __, path in common.get_open_dormitory_rooms_by_layer()[1]
        ]
        """ 第一层已开放宿舍房间的场景路径列表。 """
        self.blank = rooms.TempBlank()
        """ 当前测试用例使用的临时空白位实例。 """

    def live(self, **rooms_of: int) -> None:
        """按角色名关键字参数将测试角色写入对应序号的宿舍。"""
        for name, index in rooms_of.items():
            cid = " 甲乙丙丁".index(name)
            put(chara_life.dormitory.set, cid, self.paths[index])

    def rooms_now(self) -> list[int]:
        """返回四名测试干员当前宿舍在 paths 中的序号列表。"""
        return [
            (
                self.paths.index(chara_life.dormitory(c))
                if chara_life.dormitory(c) in self.paths
                else -1
            )
            for c in (1, 2, 3, 4)
        ]


class RoomServiceTest(DormitoryCase):
    """验证 dormitory_room_service 查询与房间调整逻辑的测试集。"""

    def test_occupancy_counts_off_island_and_capacity_grows(self) -> None:
        """验证入住统计计入离岛角色且超员宿舍容量随人数上浮。"""
        self.live(甲=0, 乙=0, 丙=0, 丁=1)
        put(flags.set, 4, field_commission=1)
        put(roster.discard, 4)
        counts = rooms.occupancy()
        self.assertEqual((counts[self.paths[0]], counts[self.paths[1]]), (3, 1))
        self.assertEqual(rooms.capacity(self.paths[0], counts), 3)
        self.assertEqual(rooms.capacity(self.paths[2], counts), 2)
        self.assertTrue(rooms.has_overcrowded_room())
        put(chara_life.dormitory.set, 2, "")
        self.assertNotIn("", rooms.occupancy())
        self.assertFalse(rooms.has_overcrowded_room())

    def test_room_choices_skip_own_and_full_rooms(self) -> None:
        """验证可选宿舍跳过当前所住与已满房间并拼出住户标签。"""
        self.live(甲=0, 乙=1, 丙=1, 丁=2)
        choices = rooms.room_choices(1)
        paths = [choice.room_path for choice in choices]
        self.assertNotIn(self.paths[0], paths)
        self.assertNotIn(self.paths[1], paths)
        self.assertEqual(paths[0], self.paths[2])
        self.assertTrue(choices[0].label.startswith("[1层] "))
        self.assertTrue(choices[0].label.endswith(" (1/2) - 丁"))
        self.assertTrue(choices[1].label.endswith(" (0/2)"))

    def test_temp_blank_moves_and_cleans(self) -> None:
        """验证移入空白位、去重清理、迁入新房与抬头文案。"""
        self.live(甲=0)
        with kernel_data.writing():
            note = rooms.move_to_blank(1, self.blank)
            rooms.move_to_blank(1, self.blank)
        self.assertEqual(self.blank.ids, [1])
        self.assertEqual(chara_life.dormitory(1), "")
        self.assertIn("甲 已从 宿舍101房 移入临时空白位", str(note.wait))
        self.blank.ids += [9, 1]
        self.assertEqual(self.blank.current(), [1])
        with kernel_data.writing():
            note = rooms.set_room(1, self.paths[3], self.blank)
        self.assertEqual((self.blank.ids, self.rooms_now()[0]), ([], 3))
        self.assertIn("从 暂无 调整为 宿舍104房", str(note.wait))
        self.assertEqual(rooms.change_header(1, [1])[0], "调整宿舍：甲")
        self.assertIn("临时空白位", rooms.change_header(1, [1])[1])
        self.assertNotIn("临时空白位", rooms.change_header(1, [])[1])

    def test_auto_sort_fills_free_beds_in_order(self) -> None:
        """验证自动排序按开放房间空位顺序安置全部空白位干员。"""
        self.assertIsNone(rooms.auto_sort(self.blank))
        self.live(甲=2, 乙=1, 丙=3, 丁=4)
        with kernel_data.writing():
            for cid in (3, 4, 1):
                rooms.move_to_blank(cid, self.blank)
            note = rooms.auto_sort(self.blank)
        self.assertEqual(self.rooms_now(), [1, 1, 0, 0])
        self.assertEqual(self.blank.ids, [])
        self.assertEqual(note and note.wait, "\n○已自动安置3名干员进入宿舍\n")

    def test_auto_sort_keeps_the_rest_without_beds(self) -> None:
        """验证空位不足时自动排序保留余下干员并在无空位时提示。"""
        for index in range(len(self.paths) * 2 - 1):
            self.world.chara(index + 10, "住客")
            put(chara_life.dormitory.set, index + 10, self.paths[index // 2])
        self.live(甲=0, 乙=0)
        with kernel_data.writing():
            rooms.move_to_blank(1, self.blank)
            rooms.move_to_blank(2, self.blank)
            note = rooms.auto_sort(self.blank)
        self.assertEqual((self.rooms_now()[0], self.blank.ids), (5, [2]))
        self.assertIn("已自动安置1名干员", str(note and note.wait))
        self.assertIn("仍有1名干员", str(note and note.wait))
        with kernel_data.writing():
            note = rooms.auto_sort(self.blank)
        self.assertIn("当前没有可用宿舍位置", str(note and note.wait))
        self.assertEqual(self.blank.ids, [2])

    def test_redistribute_keeps_two_by_adv(self) -> None:
        """验证重分配按 adv 保留每间前两名住户并安置其余住户。"""
        self.assertIsNone(rooms.redistribute())
        self.assertFalse(rooms.has_overcrowded_room())
        self.live(甲=0, 乙=0, 丙=0, 丁=0)
        self.assertTrue(rooms.has_overcrowded_room())
        with kernel_data.writing():
            note = rooms.redistribute()
        self.assertEqual(self.rooms_now(), [1, 1, 0, 0])
        self.assertIn("共分配了2名角色", str(note and note.wait))

    def test_redistribute_needs_enough_beds(self) -> None:
        """验证全层空位不足时重分配返回提示且不改变既有住宿。"""
        for index, path in enumerate(self.paths):
            for extra in (10, 30):
                self.world.chara(index + extra, "住客", adv=index + extra)
                put(chara_life.dormitory.set, index + extra, path)
        self.live(甲=0)
        with kernel_data.writing():
            note = rooms.redistribute()
        self.assertIn("空位不足", str(note and note.wait))
        self.assertEqual(self.rooms_now()[0], 0)

    def test_overview_text(self) -> None:
        """验证宿舍总览文本展示等级、开放数、空白位与管理员。"""
        self.blank.ids = [2, 3]
        text = rooms.overview_text(self.blank.current(), [(1, "甲"), (2, None)])
        self.assertIn("当前宿舍区块等级：1", text)
        self.assertIn("当前开放层数：1 层\n", text)
        self.assertIn(f"当前开放房间数：{len(self.paths)} 间", text)
        self.assertIn("临时空白位：2人（乙、丙）", text)
        self.assertTrue(text.endswith("  1层：甲\n  2层：未任命\n"))
        empty = rooms.overview_text([], [])
        self.assertIn("临时空白位：0人", empty)
        self.assertTrue(empty.endswith("暂无开放层\n"))

    def test_names_selectable_and_premise(self) -> None:
        """验证房间名解析、可选干员排序及手动换宿舍前提判断。"""
        self.assertEqual(rooms.room_name(""), "暂无")
        self.assertEqual(rooms.room_name(self.paths[0]), "宿舍101房")
        self.assertEqual(rooms.room_name(os.sep.join(["甲", "乙"])), "乙")
        put(roster.add, 0)
        self.assertEqual(rooms.selectable_ids(), [4, 3, 2, 1])
        self.assertTrue(rooms.can_change_room(1))
        self.assertFalse(rooms.can_change_room(0))
        put(chara_life.work_type.set, 1, managers.MANAGER_WORK)
        self.assertFalse(rooms.can_change_room(1))


class ManagerServiceTest(DormitoryCase):
    """验证 dormitory_manager_service 任免与重置逻辑的测试集。"""

    def setUp(self) -> None:
        """将宿舍区升至 3 级并预置管理员岗位干员与舍管房路径。"""
        super().setUp()
        kernel_data.set_facility_level(4, 3)
        kernel_data.written(basement.get_base_updata)
        self.office = [
            map_handle.get_map_system_path_str_for_list(
                ["宿舍", f"{n}区", "舍管房"]
            )
            for n in (1, 2)
        ]
        """ 第一层与第二层舍管房的地图系统路径列表。 """
        for cid in (1, 2, 3):
            put(chara_life.work_type.set, cid, managers.MANAGER_WORK)
        self.live(甲=0, 乙=1, 丙=2)

    def test_appoint_moves_in_and_hands_over(self) -> None:
        """验证任命迁入舍管房、跨层调任收钥匙与卸任迁出。"""
        with kernel_data.writing():
            note = managers.appoint(1, 1)
        self.assertEqual(dormitory.managers()[1], 1)
        self.assertEqual(chara_life.dormitory(1), self.office[0])
        self.assertEqual(chara_life.permanent_dormitory(1), self.paths[0])
        self.assertEqual(
            map_handle.get_map_system_path_str_for_list(activity.position(1)),
            self.office[0],
        )
        self.assertEqual(note.wait, "\n○已任命 甲 为 1层宿舍管理员\n")
        put(inventory.set_item, 0, 301, 1)
        with kernel_data.writing():
            note = managers.appoint(2, 1)
            managers.appoint(1, 2)
            managers.appoint(1, 3)
            managers.appoint(3, 4)
        self.assertEqual(chara_life.work_type(4), managers.MANAGER_WORK)
        self.assertIn(4, work.roster(managers.MANAGER_WORK))
        self.assertEqual(dormitory.managers()[1], 3)
        self.assertEqual(chara_life.dormitory(1), self.office[1])
        self.assertEqual(chara_life.dormitory(2), self.paths[1])
        self.assertEqual(inventory.items(0)[301], 0)
        self.assertEqual(len(note.lines), 1)
        self.assertIn("甲的1层管理员任命已被撤销", note.lines[0])

    def test_dismiss_restores_room_and_takes_key(self) -> None:
        """验证撤换管理员恢复登记宿舍、保持岗位并按需收回钥匙。"""
        self.assertEqual(
            managers.dismiss(1).wait, "\n○该层当前没有已任命管理员\n"
        )
        with kernel_data.writing():
            managers.appoint(1, 1)
        put(inventory.set_item, 0, 301, 2)
        with kernel_data.writing():
            note = managers.dismiss(1)
        self.assertEqual(dormitory.managers()[1], 0)
        self.assertEqual(chara_life.dormitory(1), self.paths[0])
        self.assertEqual(chara_life.work_type(1), managers.MANAGER_WORK)
        self.assertEqual(inventory.items(0)[301], 0)
        self.assertEqual(len(note.lines), 1)
        self.assertEqual(note.wait, "\n○已撤换 1层宿舍管理员\n")
        with kernel_data.writing():
            managers.appoint(1, 1)
            self.assertEqual(managers.dismiss(1).lines, ())
        before = activity.position(3)
        put(dormitory.set_manager, 2, 3)
        put(inventory.set_item, 0, 302, 0)
        with kernel_data.writing():
            managers.dismiss(2)
        self.assertEqual(activity.position(3), before)
        self.assertEqual(chara_life.dormitory(3), self.paths[2])

    def test_lists_and_reset_of_unassigned(self) -> None:
        """验证候选列表、未分配名单、各层状态与未分配岗位重置。"""
        with kernel_data.writing():
            candidates = managers.manager_candidates()
            managers.appoint(2, 2)
        put(dormitory.set_manager, 3, 99)
        self.assertEqual(
            [label for __, __, label in candidates],
            ["[0047] 丙", "[0048] 乙", "[0049] 甲"],
        )
        self.assertEqual(managers.unassigned_manager_names(), ["丙", "甲"])
        layers = managers.layer_managers()
        self.assertEqual(layers, [(1, None), (2, "乙"), (3, None)])
        with kernel_data.writing():
            self.assertEqual(managers.reset_unassigned_managers(), 2)
        self.assertEqual(work.roster(managers.MANAGER_WORK), (2,))
        self.assertEqual(chara_life.work_type(1), 0)
        with kernel_data.writing():
            self.assertEqual(managers.reset_unassigned_managers(), 0)


class UiFreeRunTest(FastTestCase):
    """验证两项服务在无界面无结算子进程下可运行的测试集。"""

    def test_services_run_without_ui_or_settle(self) -> None:
        """验证多编码子进程运行两项服务不触发受限模块导入。"""
        for encoding in ENCODINGS:
            with self.subTest(encoding):
                with mock.patch.dict(
                    os.environ, {"PYTHONIOENCODING": encoding}
                ):
                    run = run_ui_free(UI_FREE_RUN, boot=True)
                self.assertEqual((run.loaded, run.attempted), ([], []))
                self.assertIn("临时空白位：0人", str(run.payload["text"]))
                self.assertIn("1层：未任命", str(run.payload["text"]))
                self.assertEqual(
                    run.payload["after"],
                    [5, 0, 0, 1, 1, 0, 2, 3, 3, 4, 4, 5, -1, 2]
                    + [0, 0, 0, 0, [], [13]],
                )
                self.assertEqual(
                    run.payload["flags"], [True, True, False, False]
                )
                self.assertEqual(run.payload["size"], 4)
                self.assertEqual(
                    run.payload["labels"], ["[1层] 宿舍106房 (1/2) - c12"]
                )
                self.assertEqual(run.payload["waits"], WAITS)
                self.assertEqual(
                    run.payload["lines"], [0] * 8 + [1, 0, 0, 1, 0]
                )
