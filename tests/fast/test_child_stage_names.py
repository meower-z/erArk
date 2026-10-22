# -*- coding: UTF-8 -*-
"""
成长阶段 102、103 的玩家可见名称（快速层部分）
============================================
素质 102 叫幼女、素质 103 叫学员（STAGE_NAME）。玩家看到的下列文字写着所指阶段的这个名字，没有「幼儿」，也没有 103 的旧名「萝莉」：
- 游戏载入的配置：素质 102、103 的名称，成长停滞（素质 28）的说明，成长加速药与成长停滞药（道具 39、40）的说明，
  两个长大结算行为（child_to_loli、loli_to_girl）的名称；
- 幼女与学员女儿的养成事件抬头（growth_event_handle.get_growth_event_title）；
- 礼物面板里成长停滞药与成长继续药对少女女儿无效时的提示。
成长加速药的提示、选婴儿按钮、下一阶段名与长大时的提示要启动游戏，在 tests/slow/test_growth_drug_stage_names.py。
"""
from Script.Config import game_config
from Script.System.Education_System import growth_event_handle
from Script.UI.Panel import gift_panel
from tests.fast.base import FastTestCase

STAGE_NAME = {102: "幼女", 103: "学员"}
""" 素质 102、103 的名称 """
UNUSED_NAMES = ("幼儿", "萝莉")
""" 玩家可见文字里不用来称呼 102、103 的名称 """
STAGE_TALENT_LIST = (101, 102, 103, 104)
""" 成长阶段素质：婴儿、幼女、学员、少女 """
BOTH_STAGES = (102, 103)
""" 幼女与学员两个阶段 """
STAGE_TEXT_CONFIG = (
    ("素质 28 的说明", lambda: game_config.config_talent[28].info, BOTH_STAGES),
    ("道具 39 的说明", lambda: game_config.config_item[39].info, BOTH_STAGES),
    ("道具 40 的说明", lambda: game_config.config_item[40].info, BOTH_STAGES),
    ("行为 child_to_loli 的名称", lambda: game_config.config_behavior["child_to_loli"].name, BOTH_STAGES),
    ("行为 loli_to_girl 的名称", lambda: game_config.config_behavior["loli_to_girl"].name, (103,)),
)
""" 写着阶段名的配置文字：(说明, 取文字的函数, 文字里写着的阶段) """
GROWTH_STOP_DRUG_LIST = (40, 41)
""" 成长停滞药、成长继续药 """
PANEL_WIDTH = 100
""" 礼物面板的绘制宽度 """


def set_stage(character, talent_id: int):
    """
    把角色的成长阶段素质换成 talent_id
    Keyword arguments:
    character -- 角色对象
    talent_id -- STAGE_TALENT_LIST 之一
    Return arguments:
    无
    """
    for stage_id in STAGE_TALENT_LIST:
        character.talent[stage_id] = 1 if stage_id == talent_id else 0


class ChildStageNamesTest(FastTestCase):
    """素质 102 叫幼女、103 叫学员，玩家可见文字按这两个名字称呼她们"""

    def setUp(self):
        """
        造博士（id 0）
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.world.chara(0, "博士")

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

    def make_daughter(self, cid: int, talent_id: int):
        """
        造博士的女儿并设好成长阶段
        Keyword arguments:
        cid -- 角色id
        talent_id -- 成长阶段素质
        Return arguments:
        game_type.Character -- 女儿
        """
        daughter = self.world.chara(cid, f"女儿{cid}")
        daughter.relationship.father_id = 0
        set_stage(daughter, talent_id)
        return daughter

    def test_config_texts(self):
        """素质 102、103 的名称是幼女、学员；写着阶段名的素质、道具与行为配置按这两个名字写"""
        for talent_id, name in STAGE_NAME.items():
            self.assertEqual(game_config.config_talent[talent_id].name, name, f"素质 {talent_id} 的名称")
        for label, get_text, stage_list in STAGE_TEXT_CONFIG:
            self.assert_stage_text(label, get_text(), stage_list)

    def test_growth_event_title(self):
        """幼女与学员女儿的养成事件抬头写着她的阶段名"""
        for cid, talent_id in enumerate(BOTH_STAGES, start=1):
            self.make_daughter(cid, talent_id)
            self.assert_stage_text(f"素质 {talent_id} 的养成事件抬头", growth_event_handle.get_growth_event_title({"chara_id": cid}), (talent_id,))

    def test_growth_stop_drug_texts(self):
        """成长停滞药与成长继续药对少女女儿无效，提示写着幼女与学员"""
        daughter = self.make_daughter(1, 104)
        for drug_id in GROWTH_STOP_DRUG_LIST:
            self.world.wait_texts.clear()
            self.assertFalse(gift_panel.Gift_Panel(PANEL_WIDTH).is_drug_effective(drug_id, daughter), f"药物 {drug_id} 对少女女儿无效")
            self.assertEqual(len(self.world.wait_texts), 1, f"药物 {drug_id} 无效时画出一段提示")
            self.assert_stage_text(f"药物 {drug_id} 的提示", self.world.wait_texts[0], BOTH_STAGES)
