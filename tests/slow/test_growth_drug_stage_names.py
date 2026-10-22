# -*- coding: UTF-8 -*-
"""
成长阶段 102、103 的玩家可见名称（慢速层部分）
============================================
素质 102 叫幼女、素质 103 叫学员（STAGE_NAME）。开新游戏后取本局 id 最小的干员（不含博士）当母亲，给她生两个婴儿，博士站在育儿室里。
下列文字写着所指阶段的这个名字，没有「幼儿」，也没有 103 的旧名「萝莉」：
- 两个婴儿都到了长成幼女的前一天时，礼物面板说成长加速药对母亲无效的提示；
- 两个婴儿刚出生时，礼物面板选婴儿的两个按钮（按下第一个按钮选中了她）；
- 婴儿长成幼女（pregnancy_handle.check_rearing_complete）、幼女长成学员（pregnancy_handle.check_all_child_grow_to_loli）时画出的提示。
另查婴儿、幼女与学员的下一阶段名（pregnancy_handle.get_child_next_stage_name）依次是幼女、学员、少女。
配置文字、养成事件抬头与另两种成长药的提示在 tests/fast/test_child_stage_names.py。
"""
from unittest import mock

from tests.slow.base import SlowTestCase

STAGE_NAME = {102: "幼女", 103: "学员"}
""" 素质 102、103 的名称 """
UNUSED_NAMES = ("幼儿", "萝莉")
""" 玩家可见文字里不用来称呼 102、103 的名称 """
NEXT_STAGE_NAME = {101: "幼女", 102: "学员", 103: "少女"}
""" 婴儿、幼女、学员各自的下一阶段名 """
REARING_TALENT = 24
""" 母亲的育儿素质 """
GROWTH_ACCELERATE_DRUG = 39
""" 成长加速药 """
NURSERY_TAG = "Nursery"
""" 育儿室的场景标签 """
PANEL_WIDTH = 100
""" 礼物面板的绘制宽度 """


class GrowthDrugStageNamesTest(SlowTestCase):
    """成长加速药的提示、选婴儿按钮、下一阶段名与长大时的提示按幼女、学员称呼两个阶段"""

    def setUp(self):
        """
        开新游戏，取 id 最小的干员当母亲，给她生两个婴儿，博士走进育儿室、交互对象是母亲
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        from Script.Design import character_handle, map_handle, talk

        # 母亲一侧必显二段的口上显示与本条无关，不显示
        self.addCleanup(setattr, talk, "must_show_talk_check", talk.must_show_talk_check)
        talk.must_show_talk_check = lambda character_id: None
        self.mother_id = min(cid for cid in self.cache.npc_id_got if cid)
        self.mother = self.cache.character_data[self.mother_id]
        self.baby_id_list = [character_handle.born_new_character(self.mother_id, f"测试女儿{index}") for index in (1, 2)]
        nursery = next(key for key, scene in self.cache.scene_data.items() if NURSERY_TAG in scene.scene_tag)
        self.world.move(0, map_handle.get_map_system_path_for_str(nursery))
        self.cache.character_data[0].target_character_id = self.mother_id

    def assert_stage_text(self, label: str, text: str, stage_list: tuple):
        """
        text 写着 stage_list 里每个阶段的名称，没有 UNUSED_NAMES
        Keyword arguments:
        label -- 出错时指明是哪段文字
        text -- 玩家看到的文字
        stage_list -- 文字里写着的阶段素质
        Return arguments:
        无
        """
        for stage_id in stage_list:
            self.assertIn(STAGE_NAME[stage_id], text, f"{label}写着素质 {stage_id} 的名称：{text}")
        for name in UNUSED_NAMES:
            self.assertNotIn(name, text, f"{label}里有「{name}」：{text}")

    def set_born_day(self, day: int):
        """
        把两个婴儿的出生时间设为 day 天前
        Keyword arguments:
        day -- 出生了几天
        Return arguments:
        无
        """
        from Script.Design import game_time

        for baby_id in self.baby_id_list:
            self.cache.character_data[baby_id].pregnancy.born_time = game_time.get_sub_date(day=-day, old_date=self.cache.game_time)

    def test_growth_accelerate_drug_tip(self):
        """两个婴儿都快长成幼女时，成长加速药的无效提示写着幼女"""
        from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle
        from Script.UI.Panel import gift_panel

        player_input = self.world.player
        self.set_born_day(pregnancy_constant.REARING_COMPLETE_DAY - 1)
        self.assertEqual(len(pregnancy_handle.get_baby_id_list(self.mother_id)), 2, "母亲名下有两个婴儿")
        self.assertEqual(pregnancy_handle.get_accelerable_babies(self.mother_id), [], "两个婴儿都到了长成幼女的前一天，不能再加速")
        player_input.screen.clear()
        self.assertFalse(gift_panel.Gift_Panel(PANEL_WIDTH).is_drug_effective(GROWTH_ACCELERATE_DRUG, self.mother), "成长加速药对母亲无效")
        tip_text = "".join(player_input.screen)
        self.assertIn(self.mother.name, tip_text, "画出了无效提示")
        self.assert_stage_text("成长加速药的无效提示", tip_text, (102,))

    def test_select_baby_buttons(self):
        """两个婴儿刚出生时，选婴儿的两个按钮写着幼女，按下第一个按钮选中第一个婴儿"""
        from Script.System.Pregnancy_System import pregnancy_handle
        from Script.UI.Moudle import draw
        from Script.UI.Panel import gift_panel

        player_input = self.world.player
        self.set_born_day(0)
        self.assertEqual(pregnancy_handle.get_accelerable_babies(self.mother_id), self.baby_id_list, "两个婴儿刚出生，都能加速")
        button_text_list = []
        real_left_button = draw.LeftButton

        def record_left_button(text, *args, **kwargs):
            """
            记下按钮文字后照常造按钮
            Keyword arguments:
            text -- 按钮文字
            Return arguments:
            draw.LeftButton -- 按钮
            """
            button_text_list.append(text)
            return real_left_button(text, *args, **kwargs)

        first_baby_name = self.cache.character_data[self.baby_id_list[0]].name
        player_input.press(first_baby_name)
        with mock.patch.object(draw, "LeftButton", side_effect=record_left_button):
            self.assertTrue(gift_panel.Gift_Panel(PANEL_WIDTH).select_target_baby(), "选了婴儿")
        player_input.check_done()
        self.assertEqual(self.cache.character_data[0].behavior.gift_child_id, self.baby_id_list[0], "按下第一个按钮选中了第一个婴儿")
        self.assertEqual(len(button_text_list), 2, "两个婴儿各有一个按钮")
        for text in button_text_list:
            self.assert_stage_text("选婴儿按钮", text, (102,))

    def test_next_stage_name(self):
        """婴儿、幼女与学员的下一阶段名依次是幼女、学员、少女"""
        from Script.System.Pregnancy_System import pregnancy_handle

        child = self.cache.character_data[self.baby_id_list[0]]
        for talent_id, next_name in NEXT_STAGE_NAME.items():
            for stage_id in NEXT_STAGE_NAME:
                child.talent[stage_id] = 1 if stage_id == talent_id else 0
            self.assertEqual(pregnancy_handle.get_child_next_stage_name(child.cid), next_name, f"素质 {talent_id} 的下一阶段名")

    def test_grow_up_texts(self):
        """婴儿长成幼女、幼女长成学员时画出的提示写着两个阶段的名称"""
        from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle

        player_input = self.world.player
        child_id = self.baby_id_list[0]
        child_name = self.cache.character_data[child_id].name
        self.set_born_day(0)
        self.mother.talent[REARING_TALENT] = 1
        player_input.screen.clear()
        with mock.patch.object(pregnancy_handle, "get_child_grow_day", side_effect=lambda cid: pregnancy_constant.REARING_COMPLETE_DAY if cid == child_id else 0):
            pregnancy_handle.check_rearing_complete(self.mother_id)
        self.assertEqual(self.cache.character_data[child_id].talent[102], 1, "第一个婴儿长成了幼女")
        rearing_text = "".join(player_input.screen)
        self.assertIn(f"{child_name}从[婴儿]成长为了[{STAGE_NAME[102]}]", rearing_text, "画出了长成幼女的提示")
        self.assert_stage_text("长成幼女的提示", rearing_text, (102,))

        # 胸部成长按母亲的胸部素质算，与阶段名无关；本局取来当母亲的干员未必有胸部素质，这里不结算它
        player_input.screen.clear()
        with mock.patch.object(pregnancy_handle, "get_child_grow_day", return_value=pregnancy_constant.GROW_TO_LOLI_DAY), \
                mock.patch.object(pregnancy_handle, "chest_grow", return_value=""):
            pregnancy_handle.check_all_child_grow_to_loli()
        self.assertEqual(self.cache.character_data[child_id].talent[103], 1, "她长成了学员")
        trainee_text = "".join(player_input.screen)
        self.assertIn(f"{child_name}从[{STAGE_NAME[102]}]成长为了[{STAGE_NAME[103]}]", trainee_text, "画出了长成学员的提示")
        self.assert_stage_text("长成学员的提示", trainee_text, (102, 103))
