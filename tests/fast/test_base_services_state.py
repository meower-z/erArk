# -*- coding: UTF-8 -*-
"""
招募、公务、外交、宿舍管理员与图书馆的状态
==========================================
- 招募线随文职部等级开放，新线各项为 0。进度满 100 的线结算：可招募的角色进待确认名单，进度归 0。
  主招聘专员换了岗位时刷新岗位撤下他。读档修补去掉待确认名单里不存在的角色，停止招募的线进度归 0。
- 公务事件推进队尾或队首，出队交回队首与它入队的时间。无主体事件的决断记进全局履历后不再入队。
  主体角色不在了的队列项在清理时丢掉。公务量按全局数值改时夹在 0 与总工作量之间。
- 外交按第一次登记的顺序列出，没登记的势力为空缺。换id时外交官跟着换。
- 宿舍管理员默认 1~9 层都未任命。同一人管两层时 ISLAND-16 报。
- 借阅表在没写过时列出配置里的每本书，都没有借出。干员随机借到一本没借出的书，还书后这本书又没有借出。
- 读档：罗德岛对象带着这九项旧属性时，值写进 GameState，属性从对象上删掉。招募线的元组照列表读，列表形式的
  主招聘专员取其中的id，效率一项不留。队列与履历里的时间换成分钟数存下，读出时还是那个时间。
  类型不符的属性取默认值并计入交回的个数。之后换id时主招聘专员、待确认名单、借书人与外交官跟着换。
- 存档：九项写进文件 "2" 的 JSON 再读回，读到的值不变。
"""

import datetime
import json
from types import SimpleNamespace

from Script.Config import game_config
from Script.Design import basement, game_time
from Script.Design.handle_premise import handle_premise_work
from Script.Kernel import core
from Script.Modules.domains import (
    diplomacy,
    dormitory,
    library,
    official,
    recruit,
    roster,
)
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import kernel_state, upgrade
from Script.System.Official_Event_System import official_event_handle
from Script.System.Official_Event_System import ri_value
from Script.Test.Static_Check.check_registry import get_all_checks
from Script.UI.Panel import borrow_book_panel, recruit_panel
from tests import kernel_data
from tests.fast.base import FastTestCase
from Script.Modules.domains import chara_life

CIVIL = 7
""" 文职部的设施id """
HR_WORK = 71
""" 招聘专员的职位id """


class BaseServicesStateTest(FastTestCase):
    """招募、公务、外交、宿舍管理员与图书馆的读写、读档与存档"""

    def setUp(self) -> None:
        """放进博士，再以 core.state() 为底开一个缓冲区，测试里对 GameState 的读写都记在里面"""
        super().setUp()
        self.world.chara(0, "博士")
        self.buffer = self.enterContext(working.based_on(core.state()))

    def operator(self, cid: int) -> int:
        """
        造一名在编干员，模板与角色id相同
        Keyword arguments:
        cid -- 有模板的角色id
        Return arguments:
        int -- 角色id
        """
        self.world.chara(cid, f"干员{cid}")
        roster.add(cid)
        return cid

    def test_lines_open_by_level(self) -> None:
        """文职部 4 级时有 0、1、2 号招募线，各项为 0"""
        kernel_data.set_facility_level(CIVIL, 4)
        basement.get_base_updata()
        self.assertEqual(recruit.lines(), dict.fromkeys(range(3), recruit.IDLE))

    def test_full_line_recruits(self) -> None:
        """进度满 100 的全泰拉招募线：唯一可招募的角色进待确认名单，进度归 0。没满的线不变"""
        candidate = next(
            cid
            for cid, tem in self.cache.npc_tem_data.items()
            if not roster.is_forbidden(cid)
            and cid
            and tem.Mother_id == 0
            and tem.AdvNpc < 9000
        )
        self.world.chara(candidate, "候选")
        roster.discard(candidate)
        recruit.open_lines([0, 1])
        recruit.set_line(0, progress=100, strategy=1)
        recruit.set_line(1, progress=40.5, strategy=1)
        self.assertEqual(recruit_panel.find_recruitable_npc(), [candidate])
        recruit_panel.update_recruit()
        self.assertEqual(recruit.pending(), {candidate})
        self.assertEqual(recruit.lines()[0], {**recruit.IDLE, "strategy": 1})
        self.assertEqual(recruit.lines()[1]["progress"], 40.5)
        self.assertEqual(recruit_panel.find_recruitable_npc(), [])

    def test_main_recruiter(self) -> None:
        """同一人任命到另一条线时从原线撤下。换了岗位的主招聘专员在刷新岗位时撤下"""
        recruit.open_lines([0, 1])
        hr = self.operator(5)
        kernel_data.put(chara_life.work_type.set, hr, HR_WORK)
        recruit.appoint(0, hr)
        recruit.appoint(1, hr)
        self.assertEqual([v["main"] for v in recruit.lines().values()], [0, hr])
        basement.update_work_people()
        self.assertEqual(recruit.lines()[1]["main"], hr)
        kernel_data.put(chara_life.work_type.set, hr, 0)
        basement.update_work_people()
        self.assertEqual(recruit.lines()[1]["main"], 0)

    def test_load_repair(self) -> None:
        """读档修补：待确认名单里的 0 与不存在的角色去掉，停止招募（策略 11）的线进度归 0"""
        kept = self.operator(5)
        recruit.set_pending({0, kept, 999999})
        recruit.open_lines([0, 1])
        recruit.set_line(0, progress=30, strategy=11)
        recruit.set_line(1, progress=30, strategy=1)
        recruit_panel.repair_recruit_lines()
        self.assertEqual(recruit.pending(), {kept})
        progress = [v["progress"] for v in recruit.lines().values()]
        self.assertEqual(progress, [0, 30])

    def test_official_queue(self) -> None:
        """推进队尾与队首，同一主体同一事件不重复入队，出队交回队首与入队时间。主体不在了的项清理时丢掉"""
        uid_a, uid_b = list(game_config.config_official_event)[:2]
        sister = self.operator(5)
        official_event_handle.push_official_event(uid_a, sister)
        official_event_handle.push_official_event(uid_b, 0, to_front=True)
        self.assertTrue(
            official_event_handle.judge_event_already_in_queue(uid_a, sister)
        )
        self.assertEqual(
            official_event_handle.get_official_event_queue_count(), 2
        )
        head = official_event_handle.pop_official_event()
        assert head is not None
        self.assertEqual((head["uid"], head["chara_id"]), (uid_b, 0))
        self.assertEqual(head["add_time"], game_time.now())
        del self.cache.character_data[sister]
        official_event_handle.clean_official_event_queue()
        self.assertEqual(official.queue(), [])

    def test_history_blocks_repeat(self) -> None:
        """无主体事件的决断记进全局履历，之后这条事件不再入队，履历里记着决断的时间与选项"""
        uid = next(iter(game_config.config_official_event))
        official_event_handle.record_event_done(uid, 0, 2)
        self.assertFalse(official_event_handle.judge_event_can_enqueue(uid))
        self.assertEqual(
            official.history()[uid], {"time": game_time.now(), "choice": 2}
        )

    def test_office_work(self) -> None:
        """新游戏的公务量为 200。按全局数值改时夹在 0 与总工作量之间。公务量为 0 时前提不成立"""
        self.assertEqual(official.office_work(), 200)
        self.assertTrue(
            handle_premise_work.handle_have_office_work_need_to_do(0)
        )
        ri_value.set_ri_value("Work", 10**9)
        self.assertEqual(
            ri_value.get_ri_value("Work"), ri_value.get_all_office_work()
        )
        ri_value.set_ri_value("Work", -5)
        self.assertEqual(official.office_work(), 0)
        self.assertFalse(
            handle_premise_work.handle_have_office_work_need_to_do(0)
        )

    def test_diplomats(self) -> None:
        """外交按第一次登记的顺序列出，没登记的势力为空缺。换id时外交官跟着换，空缺不换"""
        diplomacy.set_post(3, diplomat=5)
        diplomacy.set_post(1, policy=2)
        diplomacy.set_post(3, policy=4)
        self.assertEqual(list(diplomacy.table()), [3, 1])
        self.assertEqual(diplomacy.of(3), {"diplomat": 5, "policy": 4})
        self.assertEqual(diplomacy.of(9), diplomacy.VACANT)
        diplomacy.remap({5: 50, 0: 7})
        self.assertEqual(diplomacy.of(3)["diplomat"], 50)
        self.assertEqual(diplomacy.of(1)["diplomat"], 0)

    def test_dormitory_managers(self) -> None:
        """默认 1~9 层都未任命。任命合法时 ISLAND-16 不报，同一人管两层时报"""
        self.assertEqual(dormitory.managers(), dict.fromkeys(range(1, 10), 0))
        manager = self.operator(5)
        dormitory.set_manager(2, manager)
        _name, run = get_all_checks()["ISLAND-16"]
        self.assertFalse(run())
        dormitory.set_manager(3, manager)
        self.assertTrue(run())

    def test_borrow_and_return(self) -> None:
        """借阅表没写过时列出配置里的每本书，都没有借出。干员借到一本没借出的书，还书后这本书又没有借出"""
        self.assertEqual(
            library.holders(),
            dict.fromkeys(game_config.config_book, library.FREE),
        )
        reader = self.operator(5)
        self.assertEqual(borrow_book_panel.check_random_borrow_book(reader), 1)
        (book,) = chara_life.borrow_book_id_set(reader)
        self.assertEqual(library.holders()[book], reader)
        chara_life.book_return_possibility.set(reader, 101)
        self.assertEqual(borrow_book_panel.check_return_book(reader), 1)
        self.assertEqual(library.holders()[book], library.FREE)
        self.assertEqual(chara_life.borrow_book_id_set(reader), set())

    def old_island(self) -> SimpleNamespace:
        """
        版本 11 之前的罗德岛对象，带着九项旧属性与一项别的属性
        Return arguments:
        SimpleNamespace -- 罗德岛对象
        """
        added = datetime.datetime(2020, 12, 21, 9, 30)
        return SimpleNamespace(
            recruit_line={0: [55.5, 1, [6], 12.5], 1: (10, 11, 0, 0)},
            recruited_id={8, 9},
            official_event_queue=[
                {"uid": "u1", "department": 7, "chara_id": 6, "add_time": added}
            ],
            official_event_history={"u2": {"time": added, "choice": 1}},
            office_work=88.5,
            diplomat_of_country={4: [6, 3], 2: [[0, 9]]},
            dormitory_managers={1: 6, 2: 0},
            book_borrow_dict={12: 6, 11: -1},
            recommend_book_type_set={3, 1},
            party_day_of_week={},
        )

    def adopt(self, island: SimpleNamespace, version: int) -> int:
        """
        把五个领域模块的 adopt_old_save 依次用在 island 上
        Keyword arguments:
        island -- 罗德岛对象
        version -- 存档的版本
        Return arguments:
        int -- 交回的属性个数之和
        """
        loaded = {"rhodes_island": island}
        modules = (recruit, official, diplomacy, dormitory, library)
        return sum(m.adopt_old_save(loaded, version) for m in modules)

    def test_old_island_moves_into_state(self) -> None:
        """旧存档的九项写进 GameState，属性从对象上删掉，交回 0。之后换id时各处的角色id跟着换"""
        island = self.old_island()
        added = island.official_event_queue[0]["add_time"]
        self.assertEqual(self.adopt(island, 0), 0)
        self.assertEqual(vars(island), {"party_day_of_week": {}})
        self.assertEqual(
            recruit.lines(),
            {
                0: {"progress": 55.5, "strategy": 1, "main": 6},
                1: {"progress": 10, "strategy": 11, "main": 0},
            },
        )
        self.assertEqual(recruit.pending(), {8, 9})
        self.assertEqual(official.queue()[0]["add_time"], added)
        self.assertEqual(
            official.history(), {"u2": {"time": added, "choice": 1}}
        )
        self.assertEqual(official.office_work(), 88.5)
        self.assertEqual(
            diplomacy.table(),
            {4: {"diplomat": 6, "policy": 3}, 2: {"diplomat": 9, "policy": 0}},
        )
        self.assertEqual(dormitory.managers(), {1: 6, 2: 0})
        self.assertEqual(list(library.holders())[:2], [12, 11])
        self.assertEqual(library.recommended(), {1, 3})
        old_to_new = {6: 60, 8: 80}
        recruit.remap(old_to_new)
        diplomacy.remap(old_to_new)
        library.remap(old_to_new)
        self.assertEqual(recruit.lines()[0]["main"], 60)
        self.assertEqual(recruit.pending(), {80, 9})
        self.assertEqual(diplomacy.of(4)["diplomat"], 60)
        self.assertEqual(library.holders()[12], 60)

    def test_wrong_types_read_defaults(self) -> None:
        """类型不符的属性取默认值，属性照样删掉。缺了的与类型不符的计入交回的个数，当前版本的存档交回 0"""
        island = SimpleNamespace(
            recruited_id=[5], dormitory_managers=None, office_work=3
        )
        self.assertEqual(self.adopt(island, 10), 8)
        self.assertEqual(vars(island), {})
        self.assertEqual(recruit.pending(), set())
        self.assertEqual(dormitory.managers(), dict.fromkeys(range(1, 10), 0))
        self.assertEqual(official.office_work(), 3)
        self.assertEqual(self.adopt(SimpleNamespace(), upgrade.CURRENT), 0)

    def test_old_int_pending(self) -> None:
        """
        旧存档的待确认招募存成 int：0 读作空集合，算一项类型不符；
        非 0 的 int 读作只有这一人的集合，不算类型不符
        """
        loaded = {"rhodes_island": SimpleNamespace(recruited_id=0)}
        self.assertEqual(recruit.adopt_old_save(loaded, 0), 2)
        self.assertEqual(recruit.pending(), set())
        loaded = {"rhodes_island": SimpleNamespace(recruited_id=7)}
        self.assertEqual(recruit.adopt_old_save(loaded, 0), 1)
        self.assertEqual(recruit.pending(), {7})

    def test_save_round_trip(self) -> None:
        """九项写进文件 "2" 的 JSON 再读回，读到的值不变"""
        self.adopt(self.old_island(), 0)
        readers = (
            recruit.lines,
            recruit.pending,
            official.office_work,
            official.queue,
            official.history,
            diplomacy.table,
            dormitory.managers,
            library.holders,
            library.recommended,
        )
        before = [read() for read in readers]
        game = core.preview(core.state(), self.buffer.effects())
        text = json.dumps(kernel_state.encode(game, "t"))
        decoded = kernel_state.decode(json.loads(text), tagged=True)
        self.assertEqual([read(decoded) for read in readers], before)
