# -*- coding: UTF-8 -*-
"""
婴儿与幼女不穿情趣内衣的回归测试
================================
开新游戏后，取本局 id 最小的干员（不含博士）当母亲，第二名干员当成年对照。
- 母亲生下女儿（character_handle.born_new_character，婴儿 101），再长成幼女（pregnancy_handle.check_rearing_complete，幼女 102）。
  两个阶段各经 clothing.get_underwear 换 30 次胸衣与内裤：指定情趣内衣（type_cid=2）时，
  与攻略等级 2、博士有情趣内衣收藏加成时，都挑不到服装表 tag 为 2（情趣）的衣服。
- 成年干员指定情趣内衣时，挑到的胸衣与内裤都是情趣内衣。
"""

from unittest import mock

from tests.slow.base import SlowTestCase

BABY = 101
""" 婴儿素质 """
CHILD = 102
""" 幼女素质 """
REARING_TALENT = 24
""" 母亲的育儿素质 """
UNDERWEAR_TYPE_LIST = (6, 9)
""" 胸衣与内裤的服装类型 """
H_UNDERWEAR_TAG = 2
""" 情趣内衣在服装表里的 tag """
H_UNDERWEAR_TYPE_CID = 2
""" get_underwear 指定情趣内衣时的 type_cid """
H_UNDERWEAR_BONUS_ID = 102
""" 解锁情趣内衣的收藏加成编号 """
ROUNDS = 30
""" 每种情形换内衣的次数 """


class ChildUnderwearNeverHTest(SlowTestCase):
  """婴儿与幼女挑不到情趣内衣，成年干员指定时照样挑到"""

  def setUp(self):
    """
    开新游戏，取 id 最小的两名干员，第一名当母亲，第二名当成年对照
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    self.mother_id, self.adult_id = sorted(
        cid for cid in self.cache.npc_id_got if cid
    )[:2]

  def dress(self, character_id: int, type_cid: int) -> list:
    """
    清空胸衣与内裤后经 get_underwear 重新穿上，重复 ROUNDS 次
    Keyword arguments:
    character_id -- 角色id
    type_cid -- 传给 get_underwear 的 type_cid
    Return arguments:
    list -- 每次挑到的 (服装类型, 衣服id)
    """
    from Script.Design import clothing

    cloth_wear = self.cache.character_data[character_id].cloth.cloth_wear
    picked = []
    for _ in range(ROUNDS):
      for clothing_type in UNDERWEAR_TYPE_LIST:
        cloth_wear[clothing_type] = []
      clothing.get_underwear(character_id, type_cid=type_cid)
      for clothing_type in UNDERWEAR_TYPE_LIST:
        picked += [(clothing_type, cid) for cid in cloth_wear[clothing_type]]
    return picked

  def dress_child(self, child_id: int, stage: str) -> dict:
    """
    孩子先指定情趣内衣换 ROUNDS 次，再在攻略等级 2、博士有情趣内衣收藏加成时不指定类别换 ROUNDS 次
    Keyword arguments:
    child_id -- 孩子的角色id
    stage -- 阶段名，写进返回的键
    Return arguments:
    dict -- 「阶段 情形」: 挑到的 (服装类型, 衣服id) 列表
    """
    from Script.Design import attr_calculation

    picked = {
        stage + " 指定情趣内衣": self.dress(child_id, H_UNDERWEAR_TYPE_CID)
    }
    player = self.cache.character_data[0]
    player.pl_collection = attr_calculation.get_collection_zero()
    player.pl_collection.collection_bonus[H_UNDERWEAR_BONUS_ID] = 1
    with mock.patch.object(
        attr_calculation, "get_character_fall_level", return_value=2
    ):
      picked[stage + " 攻略等级与收藏加成"] = self.dress(child_id, 0)
    return picked

  def h_picks(self, picked: list) -> list:
    """
    从挑到的衣服里取出情趣内衣
    Keyword arguments:
    picked -- (服装类型, 衣服id) 列表
    Return arguments:
    list -- 其中 tag 为情趣内衣的项
    """
    from Script.Config import game_config

    return [
        one
        for one in picked
        if game_config.config_clothing_tem[one[1]].tag == H_UNDERWEAR_TAG
    ]

  def test_child_stages_get_no_h_underwear(self):
    """出生的婴儿与长成的幼女，指定情趣内衣或有攻略等级与收藏加成时，都挑不到情趣内衣"""
    from Script.Design import character_handle, talk
    from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle

    # 母亲一侧必显二段的口上显示与本条无关，不显示
    self.addCleanup(
        setattr, talk, "must_show_talk_check", talk.must_show_talk_check
    )
    talk.must_show_talk_check = lambda character_id: None
    child_id = character_handle.born_new_character(self.mother_id, "测试女儿")
    child = self.cache.character_data[child_id]
    child.pregnancy.born_time = self.cache.game_time
    self.assertEqual(child.talent[BABY], 1, "出生时是婴儿")
    picked = self.dress_child(child_id, "婴儿")

    self.cache.character_data[self.mother_id].talent[REARING_TALENT] = 1
    with mock.patch.object(
        pregnancy_handle,
        "get_child_grow_day",
        return_value=pregnancy_constant.REARING_COMPLETE_DAY,
    ):
      pregnancy_handle.check_rearing_complete(self.mother_id)
    self.assertEqual(child.talent[CHILD], 1, "婴儿长成了幼女")
    picked.update(self.dress_child(child_id, "幼女"))

    for case, case_picked in picked.items():
      self.assertEqual(
          {clothing_type for clothing_type, _ in case_picked},
          set(UNDERWEAR_TYPE_LIST),
          f"{case}：穿上了胸衣与内裤",
      )
    self.assertEqual(
        {
            case: len(self.h_picks(case_picked))
            for case, case_picked in picked.items()
        },
        {case: 0 for case in picked},
        "各情形挑到情趣内衣的次数",
    )

  def test_adult_gets_h_underwear_when_asked(self):
    """成年干员指定情趣内衣时，挑到的胸衣与内裤全是情趣内衣"""
    picked = self.dress(self.adult_id, H_UNDERWEAR_TYPE_CID)
    self.assertEqual(
        {clothing_type for clothing_type, _ in picked},
        set(UNDERWEAR_TYPE_LIST),
        "成年干员穿上了胸衣与内裤",
    )
    self.assertEqual(self.h_picks(picked), picked, "成年干员挑到的都是情趣内衣")
