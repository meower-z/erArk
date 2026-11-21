# -*- coding: UTF-8 -*-
"""
旧存档里的外勤委托：成员里有101/102阶段的孩子
==============================================
开新游戏，买一辆载具，按旧规则摆出两个女儿（101的婴儿与102的孩子），经外勤面板的派遣按钮（选人、加载具、派遣）派出委托。
经 save_handle 真实写盘、读档后：
- 成员全是孩子的委托已取消：不在进行中、载具已收回；时间过了它的返回时间、结算外勤完成后，资源与载具不变，不算完成，
  外勤成就计数不变；
  再写盘、读档一次，委托与载具都不变。
- 一名成年干员加一名孩子的委托：读档后只剩成年干员、仍在进行，到返回时间后照常完成（发奖励、算完成、干员上线、
  载具收回）。
"""

import datetime
import importlib
import shutil
from typing import Any

from tests.slow.base import SlowTestCase
from tests import chara_abilities as ca, kernel_data, world

SAVE_ID = "test_old_save_empty_field_commission"
""" 本测试写入 save/ 的存档id，测试结束时删掉 """
ALL_CHILD_COMMISSION = 17
""" 只派孩子的委托：深入树林采药，2人，奖励 r_11_50&e_89_5 """
PARTIAL_COMMISSION = 19
""" 派一名成年干员加一名孩子的委托：中型源石矿开采，2人，奖励 r_15_200&e_81_5 """
VEHICLE_ID = 1
""" 派出的载具：温顺的武装大驮兽 """
REWARD_RESOURCE = 15
""" PARTIAL_COMMISSION 奖励的资源id """


def commission() -> Any:
    """
    导入外勤委托与载具的模块 Script.Modules.domains.commission
    Return arguments:
    Any -- 模块
    """
    return importlib.import_module("Script.Modules.domains.commission")


class TestOldSaveEmptyFieldCommission(SlowTestCase):
    """旧存档读档后，成员全是101/102孩子的外勤委托取消，有成年干员的照常进行"""

    def tearDown(self) -> None:
        """
        删掉本测试写入的存档
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Core import save_handle

        shutil.rmtree(
            save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True
        )
        super().tearDown()

    def _mother_id(self) -> int:
        """
        当母亲的静态干员
        Keyword arguments:
        无
        Return arguments:
        int -- 角色id
        """
        return min(
            cid
            for cid in self.cache.npc_id_got
            if cid != 0
            and self.cache.character_data[cid].relationship.father_id != 0
        )

    def _daughter(self, name: str, stage: int) -> int:
        """
        生一个女儿，按旧存档的样子摆到101或102阶段
        Keyword arguments:
        name -- 女儿的名字
        stage -- 101或102
        Return arguments:
        int -- 女儿的角色id
        """

        daughter_id = kernel_data.born(self._mother_id(), name)
        talent = ca.talent(daughter_id)
        for talent_id in (101, 102, 103, 104):
            talent[talent_id] = 0
        talent[stage] = 1
        return daughter_id

    def _buy_vehicle(self) -> None:
        """
        像在载具管理面板里一样买一辆 VEHICLE_ID 载具
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Config import normal_config
        from Script.UI.Panel import manage_vehicle_panel

        manage_vehicle_panel.update_basement_vehicle_data()
        panel = manage_vehicle_panel.Manage_Vehicle_Panel(
            normal_config.config_normal.text_width
        )
        with kernel_data.writing():
            panel.buy_vehicle(VEHICLE_ID)
        self.assertEqual(
            commission().vehicles()[VEHICLE_ID],
            (1, 0),
            "派遣前有一辆空闲的载具",
        )

    def _send(self, commission_id: int, member_id_list: list) -> None:
        """
        经外勤面板的按钮派出委托：选人、加一辆载具、派遣
        Keyword arguments:
        commission_id -- 委托id
        member_id_list -- 派遣的角色id列表
        Return arguments:
        无
        """
        from Script.Config import normal_config
        from Script.System.Field_Commission_System import field_commission_panel

        panel = field_commission_panel.CommissionDraw(
            commission_id,
            normal_config.config_normal.text_width,
            False,
            False,
            0,
        )
        panel.now_commision_id = commission_id
        for chara_id in member_id_list:
            panel.select_this_npc(chara_id)
        panel.add_this_vehicle(VEHICLE_ID)
        with kernel_data.writing():
            panel.send_commision(commission_id)
        self.assertEqual(
            list(commission().ongoing()[commission_id].team),
            member_id_list,
            f"委托{commission_id}已派出",
        )
        self.assertEqual(
            commission().vehicles()[VEHICLE_ID], (1, 1), "载具已派出"
        )

    def _save_and_load(self) -> None:
        """
        写盘再读档
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Core import save_handle

        save_handle.establish_save(SAVE_ID)
        self.assertTrue(
            save_handle.judge_save_file_exist(SAVE_ID), "存档应已写到盘上"
        )
        save_handle.input_load_save(SAVE_ID)

    def _finish_after(self, end_time: datetime.datetime) -> None:
        """
        让时间过了返回时间，再结算外勤完成
        Keyword arguments:
        end_time -- 委托的返回时间
        Return arguments:
        无
        """
        from Script.System.Field_Commission_System import (
            field_commission_function,
        )

        world.set_clock(end_time + datetime.timedelta(days=1))
        with kernel_data.writing():
            field_commission_function.judge_field_commission_finish()

    def test_all_child_commission_cancelled_on_load(self) -> None:
        """
        成员全是101/102阶段孩子的委托读档后取消，载具收回。再写盘、读档一次，委托与载具不变。
        过了返回时间结算后，资源与载具不变，委托不算完成，外勤成就计数不变
        """
        domain = commission()
        self._buy_vehicle()
        child_id_list = [
            self._daughter("测试女儿101", 101),
            self._daughter("测试女儿102", 102),
        ]
        self._send(ALL_CHILD_COMMISSION, child_id_list)
        end_time = domain.ongoing()[ALL_CHILD_COMMISSION].end
        achievement = importlib.import_module(
            "Script.Modules.domains.achievement"
        )
        achievement_count = achievement.get("field_commission_count")
        self._save_and_load()
        self.assertNotIn(
            ALL_CHILD_COMMISSION,
            domain.ongoing(),
            "全是孩子的委托读档后取消",
        )
        self.assertEqual(
            domain.vehicles()[VEHICLE_ID], (1, 0), "取消的委托的载具收回"
        )
        # 再写盘、读档一次，委托与载具都不变
        loaded_state = (domain.ongoing(), domain.vehicles())
        self._save_and_load()
        self.assertEqual(
            (domain.ongoing(), domain.vehicles()),
            loaded_state,
            "再读一次，委托与载具不变",
        )
        # 过了返回时间：不发奖励、不算完成
        warehouse = importlib.import_module("Script.Modules.domains.warehouse")
        resource_before = warehouse.stock()
        self._finish_after(end_time)
        self.assertEqual(
            warehouse.stock(), resource_before, "取消的委托不发奖励"
        )
        self.assertNotIn(
            ALL_CHILD_COMMISSION,
            domain.finished(),
            "取消的委托不算完成",
        )
        self.assertEqual(
            achievement.get("field_commission_count"),
            achievement_count,
            "取消的委托不计外勤成就",
        )
        self.assertEqual(
            domain.vehicles()[VEHICLE_ID], (1, 0), "过了返回时间，载具不变"
        )

    def test_partial_team_keeps_running_and_finishes(self) -> None:
        """
        一名成年干员加一名孩子的委托读档后只剩成年干员，仍在进行。到返回时间后照常完成：发奖励、算完成、计成就、
        成年干员的外勤标记清零、载具收回
        """
        domain = commission()
        self._buy_vehicle()
        adult_id = self._mother_id()
        child_id = self._daughter("测试女儿102", 102)
        self._send(PARTIAL_COMMISSION, [adult_id, child_id])
        end_time = domain.ongoing()[PARTIAL_COMMISSION].end
        achievement = importlib.import_module(
            "Script.Modules.domains.achievement"
        )
        achievement_count = achievement.get("field_commission_count")
        self._save_and_load()
        self.assertEqual(
            domain.ongoing()[PARTIAL_COMMISSION].team,
            (adult_id,),
            "有成年干员的委托仍在进行，只剩成年干员",
        )
        self.assertEqual(
            domain.vehicles()[VEHICLE_ID], (1, 1), "进行中的委托的载具仍在外"
        )
        warehouse = importlib.import_module("Script.Modules.domains.warehouse")
        resource_before = warehouse.amount(REWARD_RESOURCE)
        self._finish_after(end_time)
        self.assertNotIn(
            PARTIAL_COMMISSION,
            domain.ongoing(),
            "到返回时间委托结束",
        )
        self.assertEqual(
            warehouse.amount(REWARD_RESOURCE),
            resource_before + 200,
            "完成的委托发奖励",
        )
        self.assertIn(
            PARTIAL_COMMISSION,
            domain.finished(),
            "完成的委托算完成",
        )
        self.assertEqual(
            achievement.get("field_commission_count"),
            achievement_count + 1,
            "完成的委托计外勤成就",
        )
        self.assertEqual(
            self.cache.character_data[adult_id].sp_flag.field_commission,
            0,
            "成年干员回来了",
        )
        self.assertEqual(
            domain.vehicles()[VEHICLE_ID][1], 0, "完成的委托的载具收回"
        )
