# -*- coding: UTF-8 -*-
"""
基地的岗位名册（base.work 与 base.warden）
==========================================
- 刷新（basement.update_work_people）按遍历在编干员的顺序重建各岗位名册。招聘专员名单就是岗位 71 的名册，
  在岗人数不算没有岗位的。有监狱长岗位（191）的干员时监狱长换成她，没有时监狱长不变。
- 玩家选择里的刷新：名册与监狱长都没变时不留写入，离开面板时也就没有 0 分钟的 Edit。换了岗位时留一次名册的写入。
- 读档：罗德岛对象带着名册属性（旧存档）时，名册写进 GameState，名单按在编干员的遍历顺序，不在编的排在后面。
  没有人的岗位与配置里没有的岗位不写。监狱长写进 GameState，这些属性从对象上删掉。
  对象上没有这些属性（当前存档）时 GameState 不变。
- 自检 ISLAND-08 对合法名册不报，对岗位不符的成员报。ISLAND-29 的修复把指向非监狱长的引用改到唯一的监狱长。
"""

from collections.abc import Mapping
from typing import Any, cast

from Script.Design import basement
from Script.Modules.domains import roster, work
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import upgrade
from Script.Test.Static_Check import repair
from Script.Test.Static_Check.check_registry import get_all_checks
from tests import kernel_data
from tests.fast.base import FastTestCase
from Script.Modules.domains import chara_life
from Script.Modules.save_load.legacy_pickle import LegacyObject

JOBS = {1: 71, 2: 0, 3: 71, 4: 191, 5: 22, 6: 71}
""" 角色id到岗位id：三名招聘专员、一名无岗位、一名监狱长、一名检修 """


class WorkRostersTest(FastTestCase):
    """岗位名册的刷新、玩家选择里的刷新、读档与自检"""

    def setUp(self) -> None:
        """博士与 JOBS 里的六名干员，各自的岗位按 JOBS 设好，都在编"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid, job in JOBS.items():
            kernel_data.put(
                chara_life.work_type.set,
                self.world.chara(cid, f"干员{cid}").cid,
                job,
            )

    def met(self, job: int) -> tuple[int, ...]:
        """
        刷新遍历在编干员时遇到的岗位为 job 的角色
        Keyword arguments:
        job -- 岗位id
        Return arguments:
        tuple -- 按 npc_id_got 的遍历顺序排列的角色id
        """
        return tuple(
            cid
            for cid in roster.active()
            if cid and chara_life.work_type(cid) == job
        )

    def flagged(self, check_id: str) -> bool:
        """
        跑一项自检
        Keyword arguments:
        check_id -- 检查编号
        Return arguments:
        bool -- 这项检查报了问题时为 True
        """
        _name, run = get_all_checks()[check_id]
        return bool(run())

    def test_refresh_builds_rosters(self) -> None:
        """名册按遍历顺序，招聘专员名单是岗位 71 的名册，在岗人数是有岗位的五人，监狱长是 4 号"""
        kernel_data.written(basement.update_work_people)
        self.assertEqual(
            work.rosters(), {job: self.met(job) for job in (0, 22, 71, 191)}
        )
        self.assertEqual(work.roster(work.HR_WORK), self.met(71))
        self.assertEqual(work.people_now(), 5)
        self.assertEqual(work.warden(), 4)

    def test_warden_kept_without_191(self) -> None:
        """监狱长换了岗位后再刷新，没有别人是 191，监狱长仍是她"""
        kernel_data.written(basement.update_work_people)
        kernel_data.put(chara_life.work_type.set, 4, 0)
        kernel_data.written(basement.update_work_people)
        self.assertEqual(work.warden(), 4)
        self.assertEqual(work.roster(191), ())

    def test_pick_refresh_writes_only_changes(self) -> None:
        """选择里刷新：名册没变时交回的写入为空。换了一人的岗位后，交回一次 base.work 的整值替换"""
        kernel_data.written(basement.update_work_people)
        pick = working.open_pick()
        basement.update_work_people()
        self.assertEqual(working.close_pick(pick), ())
        kernel_data.put(chara_life.work_type.set, 2, 71)
        pick = working.open_pick()
        basement.update_work_people()
        carried = [
            cast("Mapping[str, Any]", item) for item in working.close_pick(pick)
        ]
        self.assertEqual([item["key"] for item in carried], [work.KEY])
        self.assertEqual(carried[0]["new"]["71"], self.met(71))

    def test_old_island_moves_into_state(self) -> None:
        """旧存档的罗德岛对象带着名册属性。名册按在编顺序写进 GameState，不在编的 8 号排在后面，属性从对象上删掉"""
        island = LegacyObject()
        vars(island).update(
            all_work_npc_set={0: set(), 71: {6, 3, 1}, 22: {8, 5}, 99999: {2}},
            work_people_now=6,
            hr_operator_ids_list=[3, 1, 6],
            current_warden_id=4,
        )
        npc = roster.active()
        with kernel_data.writing():
            upgrade.adopt_work({"rhodes_island": island, "npc_id_got": npc})
        self.assertEqual(
            work.rosters(),
            {22: (5, 8), 71: self.met(71)},
            "没有人与配置里没有的岗位不写",
        )
        self.assertEqual(work.people_now(), 5)
        self.assertEqual(work.warden(), 4)
        self.assertEqual(set(upgrade.V5_WORK) & set(vars(island)), set())

    def test_current_island_keeps_state(self) -> None:
        """当前存档的罗德岛对象没有名册属性。GameState 里的名册与监狱长不变"""
        kernel_data.written(basement.update_work_people)
        before = (work.rosters(), work.warden())
        with kernel_data.writing():
            upgrade.adopt_work({"rhodes_island": LegacyObject()})
        self.assertEqual((work.rosters(), work.warden()), before)

    def test_island_checks_and_repair(self) -> None:
        """ISLAND-08 对刷新后的名册不报，有人换了岗位而名册没刷新时报。ISLAND-29 的修复把监狱长改到 4 号"""
        kernel_data.written(basement.update_work_people)
        self.assertFalse(self.flagged("ISLAND-08"))
        kernel_data.put(chara_life.work_type.set, 5, 71)
        self.assertTrue(self.flagged("ISLAND-08"))
        with kernel_data.writing():
            work.set_warden(1)
        self.assertTrue(self.flagged("ISLAND-29"))
        with kernel_data.writing():
            repair.repair_warden_reference()
        self.assertEqual(work.warden(), 4)
