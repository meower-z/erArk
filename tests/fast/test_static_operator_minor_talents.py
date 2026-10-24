# -*- coding: UTF-8 -*-
"""
静态干员不带未初潮、未成年与萝莉素质的测试
==========================================
data/character/ 下的静态干员模板不带未初潮（T|6）、未成年（T|7）与萝莉（T|103）素质；
GIRL_OPERATOR_ADV_IDS 列出的 26 名干员带少女（T|104）素质。
断言落在 MinimalWorld 载入的模板素质（cache.npc_tem_data）上，新游戏按这些模板生成静态干员。
"""

from tests.fast.base import FastTestCase

NO_MENARCHE_TALENT = 6
""" 未初潮素质 """
UNDERAGE_TALENT = 7
""" 未成年素质 """
LOLI_TALENT = 103
""" 萝莉素质 """
GIRL_TALENT = 104
""" 少女素质 """
GIRL_OPERATOR_ADV_IDS = (
    133,
    134,
    151,
    190,
    214,
    254,
    277,
    290,
    298,
    352,
    358,
    369,
    381,
    464,
    501,
    566,
    569,
    4100,
    4105,
    4163,
    4164,
    4207,
    4211,
    4224,
    4235,
    4236,
)
""" 须带少女素质的 26 名静态干员的剧情npc编号（模板文件名前缀） """


class StaticOperatorMinorTalentTest(FastTestCase):
  """静态干员模板不带未初潮、未成年与萝莉素质"""

  def test_no_minor_talents(self) -> None:
    """没有静态干员模板带未初潮、未成年或萝莉素质"""
    for talent_id in (NO_MENARCHE_TALENT, UNDERAGE_TALENT, LOLI_TALENT):
      with self.subTest(talent_id=talent_id):
        holders = sorted(
            adv_id
            for adv_id, character_tem in self.cache.npc_tem_data.items()
            if character_tem.Talent.get(talent_id)
        )
        self.assertEqual(holders, [], f"带素质 {talent_id} 的静态干员模板")

  def test_operators_have_girl_talent(self) -> None:
    """这 26 名静态干员模板都带少女素质"""
    missing = [
        adv_id
        for adv_id in GIRL_OPERATOR_ADV_IDS
        if not self.cache.npc_tem_data[adv_id].Talent.get(GIRL_TALENT)
    ]
    self.assertEqual(missing, [])
