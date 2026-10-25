# -*- coding: UTF-8 -*-
"""
养成事件的候选池按成长阶段分桶；存档里事件表没有的事件读档后无害
================================================================
开新游戏后，取本局 id 最小的干员当母亲，经游戏自己的出生与长大路径生出两个女儿：
姐姐出生（character_handle.born_new_character）、长成幼女（pregnancy_handle.check_rearing_complete）、
长成学员（pregnancy_handle.check_all_child_grow_to_loli）；妹妹随后出生，再长成幼女。
- 妹妹是婴儿时、是幼女时，姐姐是学员时，growth_event_handle.get_candidate_event_list 列出的候选不为空，
  每条候选的 sub_key 都是她此刻的阶段或 0（通用桶）。
- 公务队列里放一条事件表里没有的事件与一条有的事件，学员的养成履历里也放那条没有的，经 save_handle 真实写盘、读档后：
  公务事件的两项静态检查（OFFICIAL-01 队列条目、OFFICIAL-02 事件履历）没有失败；
  数队列时那条没有的被静默清掉，有的那条还在；养成总览照常画出履历。
"""

import shutil
from unittest import mock

from tests.slow.base import SlowTestCase

BABY = 101
""" 婴儿素质 """
CHILD = 102
""" 幼女素质 """
TRAINEE = 103
""" 学员素质 """
ANY_STAGE = 0
""" 通用桶的 sub_key：婴儿、幼女、学员都派 """
REARING_TALENT = 24
""" 母亲的育儿素质 """
UNKNOWN_EVENT_UID = "萝莉28"
""" 事件表里没有的养成事件uid（「文件名 + cid」的写法），代表存档里留着、事件表里没有的事件 """
KNOWN_EVENT_UID = "萝莉3"
""" 事件表里有的学员事件uid """
SAVE_ID = "test_growth_events_match_stage"
""" 本测试写入 save/ 的存档id，测试结束时删掉 """


class GrowthEventsMatchStageTest(SlowTestCase):
  """候选池按成长阶段分桶；存档里事件表没有的事件读档后无害"""

  def tearDown(self) -> None:
    """
    删掉本测试写入的存档
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Core import save_handle

    shutil.rmtree(save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True)
    super().tearDown()

  def make_daughters(self) -> tuple[int, int, int]:
    """
    生出学员姐姐，再生出婴儿妹妹
    Keyword arguments:
    无
    Return arguments:
    tuple -- (母亲id int, 姐姐id int, 妹妹id int)
    """
    from Script.Design import character_handle, talk
    from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle

    # 长大时必显二段的口上显示与本测试无关，不显示
    self.addCleanup(
        setattr, talk, "must_show_talk_check", talk.must_show_talk_check
    )
    talk.must_show_talk_check = lambda character_id: None
    mother_id = min(cid for cid in self.cache.npc_id_got if cid)
    mother = self.cache.character_data[mother_id]
    elder_id = character_handle.born_new_character(mother_id, "测试姐姐")
    mother.talent[REARING_TALENT] = 1
    with mock.patch.object(
        pregnancy_handle,
        "get_child_grow_day",
        return_value=pregnancy_constant.REARING_COMPLETE_DAY,
    ):
      pregnancy_handle.check_rearing_complete(mother_id)
    # 胸部成长按母亲的胸部素质算，与本测试无关，不结算
    with mock.patch.object(
        pregnancy_handle,
        "get_child_grow_day",
        return_value=pregnancy_constant.GROW_TO_LOLI_DAY,
    ), mock.patch.object(pregnancy_handle, "chest_grow", return_value=""):
      pregnancy_handle.check_all_child_grow_to_loli()
    self.assertEqual(
        self.cache.character_data[elder_id].talent[TRAINEE], 1, "姐姐长成了学员"
    )
    younger_id = character_handle.born_new_character(mother_id, "测试妹妹")
    self.assertEqual(
        self.cache.character_data[younger_id].talent[BABY],
        1,
        "妹妹出生时是婴儿",
    )
    return mother_id, elder_id, younger_id

  def check_pool(self, character_id: int, stage: int) -> None:
    """
    候选不为空，每条候选的 sub_key 都是孩子此刻的阶段或通用桶
    Keyword arguments:
    character_id -- 孩子角色id
    stage -- 孩子此刻的成长阶段素质id
    Return arguments:
    无
    """
    from Script.Config import game_config
    from Script.System.Education_System import growth_event_handle

    self.assertEqual(
        self.cache.character_data[character_id].talent[stage],
        1,
        f"孩子此刻是阶段 {stage}",
    )
    uid_list = [
        one[0]
        for one in growth_event_handle.get_candidate_event_list(character_id)
    ]
    self.assertTrue(uid_list, f"阶段 {stage} 的候选不为空")
    wrong = sorted(
        uid
        for uid in uid_list
        if game_config.config_official_event[uid]["sub_key"]
        not in (stage, ANY_STAGE)
    )
    self.assertEqual(wrong, [], f"阶段 {stage} 的候选里有别的阶段桶的事件")

  def test_candidate_pool_matches_stage(self) -> None:
    """婴儿、幼女、学员的候选池都不为空，候选都来自本阶段桶或通用桶"""
    from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle

    mother_id, elder_id, younger_id = self.make_daughters()
    self.check_pool(younger_id, BABY)
    self.check_pool(elder_id, TRAINEE)
    self.cache.character_data[mother_id].talent[REARING_TALENT] = 1
    with mock.patch.object(
        pregnancy_handle,
        "get_child_grow_day",
        return_value=pregnancy_constant.REARING_COMPLETE_DAY,
    ):
      pregnancy_handle.check_rearing_complete(mother_id)
    self.check_pool(younger_id, CHILD)

  def test_old_save_with_unknown_event(self) -> None:
    """存档的公务队列与养成履历里有事件表没有的事件：读档后静态检查通过，队列里那一条被静默清掉，养成总览照常画出"""
    import datetime

    from Script.Config import game_config
    from Script.Core import save_handle
    from Script.System.Education_System import education_constant, growth_handle, growth_panel
    from Script.System.Official_Event_System import official_event_handle
    from Script.Test.Static_Check.checks import check_official

    self.assertNotIn(
        UNKNOWN_EVENT_UID,
        game_config.config_official_event,
        "事件表里没有这条事件",
    )
    _mother_id, elder_id, _younger_id = self.make_daughters()
    # 事件表里没有的事件按存档里的样子摆进队列：字段与 push_official_event 写入的相同
    official_event_handle.get_queue().append(
        {
            "uid": UNKNOWN_EVENT_UID,
            "department": education_constant.GROWTH_EVENT_DEPARTMENT,
            "chara_id": elder_id,
            "partner_id": 0,
            "add_time": self.cache.game_time,
        }
    )
    self.assertTrue(
        official_event_handle.push_official_event(KNOWN_EVENT_UID, elder_id, 0),
        f"{KNOWN_EVENT_UID} 入队",
    )
    growth_handle.get_child_growth(elder_id).event_history[
        UNKNOWN_EVENT_UID
    ] = {
        "time": datetime.datetime(2020, 12, 1),
        "choice": 1,
    }
    save_handle.establish_save(SAVE_ID)
    self.assertTrue(
        save_handle.judge_save_file_exist(SAVE_ID), "存档应已写到盘上"
    )
    save_handle.input_load_save(SAVE_ID)

    failure_list = (
        check_official.check_official_01() + check_official.check_official_02()
    )
    self.assertEqual(
        [one.check_id for one in failure_list], [], "公务事件的静态检查没有失败"
    )
    self.assertIn(
        UNKNOWN_EVENT_UID,
        self.cache.character_data[elder_id].child_growth.event_history,
        "读档后履历里还留着这条事件",
    )
    self.assertEqual(
        official_event_handle.get_official_event_queue_count(elder_id),
        1,
        "数队列时只剩一条",
    )
    self.assertEqual(
        [
            one["uid"]
            for one in official_event_handle.get_queue()
            if one["chara_id"] == elder_id
        ],
        [KNOWN_EVENT_UID],
        "留在队列里的是事件表里有的那一条",
    )
    growth_panel.Growth_Panel(80)._draw_event_history(elder_id)
