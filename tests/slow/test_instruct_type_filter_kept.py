# -*- coding: UTF-8 -*-
"""
指令面板按交互对象隐藏指令类型时，玩家的指令类型过滤设置保持不变
==============================================================
开新游戏后，玩家用面板的类型按钮打开猥亵类（新游戏默认关着），杜宾作为普通成年交互对象。
交互对象临盆（素质22）、产后（素质23）、婴儿（素质101）或幼女（素质102）时，Tk指令面板不列出技艺、猥亵、性爱三类的指令，
前提 obscenity_panel_show 不成立；画完面板后玩家的设置 cache.instruct_type_filter 与画之前相同，
换回杜宾为交互对象时，猥亵类的指令照玩家的设置列出，obscenity_panel_show 成立。
玩家用按钮关上猥亵类时，以杜宾为交互对象也不列出猥亵类的指令。
测试里没有任何角色进入H状态，也没有执行任何指令。
"""

from tests.slow.base import SlowTestCase

AGE_TALENTS = range(101, 109)
""" 年龄素质 """
HIDDEN_TYPES = {4, 5, 6}
""" 交互对象临盆、产后或处于幼年阶段时隐藏的指令类型：技艺、猥亵、性爱 """
OBSCENITY = 5
""" 猥亵类 """
PANEL_WIDTH = 100
""" 指令面板的绘制宽度 """


class InstructTypeFilterKeptTest(SlowTestCase):
  """面板按交互对象隐藏技艺、猥亵、性爱三类，不改写玩家的指令类型过滤设置"""

  def setUp(self):
    """
    开新游戏，把杜宾放到博士所在的场景
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    self.pl = self.cache.character_data[0]
    self.adult_id = self.npc("杜宾")
    self.world.move(self.adult_id, self.pl.position)

  def listed_types(self, target_id: int) -> dict:
    """
    以 target_id 为交互对象画一次Tk指令面板，按类型归拢面板列出的指令
    Keyword arguments:
    target_id -- 交互对象的角色id
    Return arguments:
    dict -- 指令类型: 列出的指令id列表
    """
    from Script.Core import constant
    from Script.System.Instruct_System import see_instruct_panel

    self.pl.target_character_id = target_id
    panel = see_instruct_panel.SeeInstructPanel(PANEL_WIDTH)
    panel.draw()
    type_of = {
        instruct_id: instruct_type
        for instruct_type, instruct_ids in constant.instruct_type_data.items()
        for instruct_id in instruct_ids
    }
    listed = {}
    for return_text in panel.return_list:
      cid = int(return_text) if str(return_text).isdigit() else None
      if cid in constant.cid_to_instruct_id:
        instruct_id = constant.cid_to_instruct_id[cid]
        listed.setdefault(type_of[instruct_id], []).append(instruct_id)
    return listed

  def toggle_type(self, instruct_type: int):
    """
    像玩家点面板上的类型按钮一样切换一类指令的开关
    Keyword arguments:
    instruct_type -- 指令类型
    Return arguments:
    无
    """
    from Script.System.Instruct_System import see_instruct_panel

    see_instruct_panel.SeeInstructPanel(PANEL_WIDTH).change_filter(
        instruct_type
    )

  def obscenity_panel_shown(self) -> float:
    """
    前提 obscenity_panel_show 对博士的结果
    Keyword arguments:
    无
    Return arguments:
    float -- 前提的结果
    """
    from Script.Design import handle_premise

    return handle_premise.handle_premise("obscenity_panel_show", 0)

  def make_special_target(self, kind: str, name: str) -> int:
    """
    把一名干员改成临盆、产后、婴儿或幼女，放到博士所在的场景
    Keyword arguments:
    kind -- "临盆"、"产后"、"婴儿"或"幼女"
    name -- 干员名字
    Return arguments:
    int -- 角色id
    """
    chara_id = self.npc(name)
    chara = self.cache.character_data[chara_id]
    if kind == "临盆":
      chara.talent[22] = 1
    elif kind == "产后":
      chara.talent[23] = 1
    else:
      for talent_id in AGE_TALENTS:
        chara.talent[talent_id] = 0
      chara.talent[{"婴儿": 101, "幼女": 102}[kind]] = 1
    self.world.move(chara_id, self.pl.position)
    return chara_id

  def test_special_target_keeps_player_setting(self):
    """交互对象临盆、产后、婴儿或幼女：三类不列出；玩家的设置不变，换回成年交互对象时猥亵类照设置列出"""
    self.toggle_type(OBSCENITY)
    before = dict(self.cache.instruct_type_filter)
    self.assertTrue(before[OBSCENITY], "玩家打开了猥亵类")
    self.assertIn(
        OBSCENITY,
        self.listed_types(self.adult_id),
        "杜宾为交互对象时列出猥亵类",
    )
    special_list = (
        ("临盆", "阿米娅"),
        ("产后", "凯尔希"),
        ("婴儿", "可露希尔"),
        ("幼女", "华法琳"),
    )
    for kind, name in special_list:
      special_id = self.make_special_target(kind, name)
      listed = self.listed_types(special_id)
      self.assertEqual(
          HIDDEN_TYPES & set(listed),
          set(),
          f"交互对象{kind}时列出的技艺、猥亵、性爱类：{listed}",
      )
      self.assertEqual(
          self.obscenity_panel_shown(),
          0,
          f"交互对象{kind}时 obscenity_panel_show",
      )
      self.assertEqual(
          dict(self.cache.instruct_type_filter),
          before,
          f"交互对象{kind}时画完面板后的玩家设置",
      )
      self.assertIn(
          OBSCENITY,
          self.listed_types(self.adult_id),
          f"交互对象{kind}之后换回杜宾，猥亵类照玩家的设置列出",
      )
      self.assertEqual(
          self.obscenity_panel_shown(),
          1,
          f"交互对象{kind}之后换回杜宾，obscenity_panel_show",
      )

  def test_adult_target_follows_player_setting(self):
    """杜宾为交互对象：猥亵类随玩家的按钮列出或不列出"""
    self.assertNotIn(
        OBSCENITY,
        self.listed_types(self.adult_id),
        "新游戏默认关着猥亵类，不列出",
    )
    self.toggle_type(OBSCENITY)
    self.assertIn(
        OBSCENITY, self.listed_types(self.adult_id), "玩家打开猥亵类后列出"
    )
    self.toggle_type(OBSCENITY)
    self.assertNotIn(
        OBSCENITY, self.listed_types(self.adult_id), "玩家再关上猥亵类后不列出"
    )
