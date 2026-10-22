# -*- coding: UTF-8 -*-
"""
婴儿与幼女离线、幼女不上学、女儿不跟随母亲见学的回归测试
========================================================
开新游戏后，取本局 id 最小的干员（不含博士）当母亲。
- 出生（character_handle.born_new_character）后、婴儿长成幼女（pregnancy_handle.check_rearing_complete）后，
  孩子都不在任何场景的角色名单里，也不在 npc_id_got 里；长成幼女时不置学生岗，不在养成名单里。
  幼女长成学员（睡眠结算里的 pregnancy_handle.check_all_child_grow_to_loli）后，孩子进了 npc_id_got 和一个场景，没有未初潮与未成年，
  置为学生岗、进养成名单。
- 离线的幼女照样被每日派发挑作养成事件的主体；以她为主体的事件入队、结算一个选项后，她的照料值或性格倾向变了。
- 另取第二名干员当女儿：工作日上课节次内、母亲在别的场景时，幼女与学员女儿的 AI 都不派见学的两个状态机
  （717 移动到母亲身边、718 跟着母亲见学），行为也不是跟随母亲见学。
"""
import datetime
from unittest import mock

from tests.slow.base import SlowTestCase

BABY = 101
""" 婴儿素质 """
CHILD = 102
""" 幼女素质 """
TRAINEE = 103
""" 学员素质 """
NO_MENARCHE = 6
""" 未初潮素质 """
UNDERAGE = 7
""" 未成年素质 """
REARING_TALENT = 24
""" 母亲的育儿素质 """
FOLLOW_MOTHER_STATE_MACHINE_SET = {717, 718}
""" 见学的两个状态机id：717 移动到母亲身边、718 跟着母亲见学 """
CLASS_TIME = datetime.datetime(2020, 12, 22, 10, 0)
""" 一个工作日的上课节次内（第二节 9:45~10:30） """


class ChildStagesOfflineTest(SlowTestCase):
    """婴儿与幼女离线、幼女不上学、女儿不跟随母亲见学"""

    def setUp(self):
        """
        开新游戏，取 id 最小的两名干员，第一名当母亲
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.mother_id, self.other_id = sorted(cid for cid in self.cache.npc_id_got if cid)[:2]
        self.mother = self.cache.character_data[self.mother_id]

    def scene_list_with(self, character_id: int) -> list:
        """
        列出角色名单里有这个角色的场景
        Keyword arguments:
        character_id -- 角色id
        Return arguments:
        list -- 场景路径字符串列表
        """
        return [path for path, scene in self.cache.scene_data.items() if character_id in scene.character_list]

    def test_child_offline_until_trainee(self):
        """出生后与长成幼女后不在任何场景、不在 npc_id_got、不上学；长成学员后上线、成年、上学"""
        from Script.Design import character_handle, talk
        from Script.System.Education_System import education_constant, growth_handle
        from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle

        # 母亲一侧必显二段的口上显示与本条无关，不显示
        self.addCleanup(setattr, talk, "must_show_talk_check", talk.must_show_talk_check)
        talk.must_show_talk_check = lambda character_id: None
        child_id = character_handle.born_new_character(self.mother_id, "测试女儿")
        child = self.cache.character_data[child_id]
        child.pregnancy.born_time = self.cache.game_time
        self.assertEqual(child.talent[BABY], 1, "出生时是婴儿")
        self.assertEqual(self.scene_list_with(child_id), [], "出生后不在任何场景")
        self.assertNotIn(child_id, self.cache.npc_id_got, "出生后不在 npc_id_got")

        self.mother.talent[REARING_TALENT] = 1
        with mock.patch.object(pregnancy_handle, "get_child_grow_day", return_value=pregnancy_constant.REARING_COMPLETE_DAY):
            pregnancy_handle.check_rearing_complete(self.mother_id)
        self.assertEqual(child.talent[CHILD], 1, "婴儿长成了幼女")
        self.assertEqual(self.scene_list_with(child_id), [], "长成幼女后不在任何场景")
        self.assertNotIn(child_id, self.cache.npc_id_got, "长成幼女后不在 npc_id_got")
        self.assertNotEqual(child.work.work_type, education_constant.STUDENT_WORK_TYPE, "长成幼女时不置学生岗")
        child.work.work_type = education_constant.STUDENT_WORK_TYPE
        self.cache.npc_id_got.add(child_id)
        self.assertNotIn(child_id, growth_handle.get_student_candidate_list(), "即便是学生岗、在 npc_id_got 里，幼女也不在养成名单里")
        self.cache.npc_id_got.discard(child_id)
        child.work.work_type = 0

        # 胸部成长按母亲的胸部素质算，与上线、上学无关；本局取来当母亲的干员未必有胸部素质，这里不结算它
        with mock.patch.object(pregnancy_handle, "get_child_grow_day", return_value=pregnancy_constant.GROW_TO_LOLI_DAY), \
                mock.patch.object(pregnancy_handle, "chest_grow", return_value=""):
            pregnancy_handle.check_all_child_grow_to_loli()
        self.assertEqual(child.talent[TRAINEE], 1, "幼女长成了学员")
        self.assertEqual((child.talent[NO_MENARCHE], child.talent[UNDERAGE]), (0, 0), "学员已成年：没有未初潮，也没有未成年")
        self.assertIn(child_id, self.cache.npc_id_got, "长成学员后进了 npc_id_got")
        self.assertEqual(len(self.scene_list_with(child_id)), 1, "长成学员后在一个场景里")
        self.assertEqual(child.work.work_type, education_constant.STUDENT_WORK_TYPE, "长成学员时置学生岗")
        self.assertIn(child_id, growth_handle.get_student_candidate_list(), "学员在养成名单里")

    def test_offline_child_growth_event(self):
        """
        离线的幼女照样派得到养成事件：每日派发会挑她当主体，挑一条选项会改她养成数值的事件入队，
        经 settle_official_event_option 结算那个选项后，她的照料值或性格倾向变了
        """
        import random

        from Script.Design import character_handle, talk
        from Script.System.Education_System import growth_event_handle, growth_handle
        from Script.System.Official_Event_System import official_event_handle
        from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle

        self.addCleanup(setattr, talk, "must_show_talk_check", talk.must_show_talk_check)
        talk.must_show_talk_check = lambda character_id: None
        child_id = character_handle.born_new_character(self.mother_id, "测试女儿")
        child = self.cache.character_data[child_id]
        child.pregnancy.born_time = self.cache.game_time
        self.mother.talent[REARING_TALENT] = 1
        with mock.patch.object(pregnancy_handle, "get_child_grow_day", return_value=pregnancy_constant.REARING_COMPLETE_DAY):
            pregnancy_handle.check_rearing_complete(self.mother_id)
        self.assertEqual(child.talent[CHILD], 1, "婴儿长成了幼女")
        self.assertNotIn(child_id, self.cache.npc_id_got, "幼女不在 npc_id_got")

        # 每日派发每个女儿只按一定概率派，这里让概率判定必过
        with mock.patch.object(random, "randint", return_value=1):
            pick_list = growth_event_handle.get_today_growth_event_pick_list()
        self.assertIn(child_id, [one["chara_id"] for one in pick_list], "每日派发挑了离线的幼女当主体")

        # 从她此刻可触发的事件里取一条有可选选项会改养成数值（Growth|10~13 性格倾向、Growth|20 照料值）的
        found = None
        for uid, _weight, partner_id in growth_event_handle.get_candidate_event_list(child_id):
            for option in official_event_handle.get_option_list(uid, child_id, partner_id):
                if option["can_use"] and "Growth|" in option["effect"]:
                    found = (uid, partner_id, option["index"])
                    break
            if found:
                break
        self.assertIsNotNone(found, "幼女有选项会改养成数值的可触发事件")
        uid, partner_id, option_index = found
        self.assertTrue(official_event_handle.push_official_event(uid, child_id, partner_id), "事件入队")
        self.assertIn((uid, child_id), [(one["uid"], one["chara_id"]) for one in official_event_handle.get_queue()], "队列里有以她为主体的这条事件")
        growth_data = growth_handle.get_child_growth(child_id)
        before = (growth_data.care_point, dict(growth_data.personality_point))
        official_event_handle.settle_official_event_option(uid, child_id, partner_id, option_index)
        self.assertNotEqual((growth_data.care_point, dict(growth_data.personality_point)), before, f"结算 {uid} 的选项 {option_index} 后照料值或性格倾向变了")

    def test_follow_mother_never_starts(self):
        """工作日上课节次内、母亲在别的场景时，幼女与学员女儿的 AI 都不派见学的状态机，行为也不是跟随母亲见学"""
        from Script.Core import constant
        from Script.Design import game_time, handle_npc_ai, map_handle
        from Script.System.Education_System import education_constant

        daughter_id = self.other_id
        daughter = self.cache.character_data[daughter_id]
        daughter.relationship.father_id = 0
        daughter.relationship.mother_id = self.mother_id
        daughter.target_character_id = daughter_id
        ran_list = []
        state_machine_data = dict(constant.handle_state_machine_data)
        for state_machine_id, run in state_machine_data.items():
            constant.handle_state_machine_data[state_machine_id] = lambda character_id, state_machine_id=state_machine_id, run=run: (ran_list.append(state_machine_id), run(character_id))
        self.addCleanup(constant.handle_state_machine_data.update, state_machine_data)
        self.cache.game_time = game_time.to_game_time(CLASS_TIME)
        if self.mother.position == daughter.position:
            other_scene = next(path for path in self.cache.scene_data if path != map_handle.get_map_system_path_str_for_list(daughter.position))
            map_handle.character_move_scene(self.mother.position, map_handle.get_map_system_path_for_str(other_scene), self.mother_id)
        for talent_id in (CHILD, TRAINEE):
            for stage_id in (BABY, CHILD, TRAINEE):
                daughter.talent[stage_id] = 1 if stage_id == talent_id else 0
            daughter.work.work_type = education_constant.STUDENT_WORK_TYPE if talent_id == TRAINEE else 0
            daughter.behavior.start_time = self.cache.game_time
            daughter.behavior.behavior_id = constant.Behavior.SHARE_BLANKLY
            ran_list.clear()
            handle_npc_ai.find_character_target(daughter_id, self.cache.game_time)
            self.assertFalse(FOLLOW_MOTHER_STATE_MACHINE_SET & set(ran_list), f"阶段 {talent_id} 派了见学的状态机：{ran_list}")
            self.assertNotEqual(daughter.behavior.behavior_id, constant.Behavior.FOLLOW_MOTHER, f"阶段 {talent_id} 在跟随母亲见学")
