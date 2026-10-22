# -*- coding: UTF-8 -*-
"""
外表年龄药、铜化方舟设定、「_小」立绘差分与默认女儿立绘不存在的检查
==================================================================
道具表与礼物表里没有道具 31、32；世界设定表里没有设定 1，旧存档里留着的 world_setting[1] 不改任何干员的素质 102~107；
image 目录与游戏的图片索引里没有以「_小」为差分段的图片名；干员带素质 102、103 时、女儿的母亲是阿米娅时，
立绘查找的结果都不含「_小」段；没有同名立绘、种族也没有女儿图的女儿没有立绘，查找结果不在图片索引里，web 渲染器给出空的立绘路径。
图片索引在导入 Script.Core.era_image 时建立，快速层不能导入它，所以本测试属于慢速层。
"""
import os
import re

from tests.slow.base import SlowTestCase
from tests.world import ROOT

AGE_DRUG_IDS = (31, 32)
""" 外表年龄增长药与减少药的道具id """
COPPER_ARK_SETTING_ID = 1
""" 铜化方舟的世界设定id """
CHILD_SEGMENT = re.compile(r"_小(_|\.|$)")
""" 图片名或文件名里的「_小」差分段 """
MOTHER_NAME = "阿米娅"
""" 女儿用例的母亲 """
AGE_TALENT_IDS = (102, 103, 104, 105, 106, 107)
""" 铜化方舟改写过的素质 102~107 """


class NoAgeDrugsOrChildPortraitsTest(SlowTestCase):
    """外表年龄药与铜化方舟设定不在配置里；立绘查找不返回「_小」差分；没有立绘的女儿不报错"""

    def test_age_drugs_and_setting_absent(self):
        """道具 31、32 不在道具表与礼物表；设定 1 不在世界设定表；world_setting[1] 为 1 时开局设定不改干员的素质 102~107"""
        from Script.Config import game_config
        from Script.Design import character_handle

        for item_id in AGE_DRUG_IDS:
            self.assertNotIn(item_id, game_config.config_item)
        self.assertEqual([gift.cid for gift in game_config.config_gift_items.values() if gift.item_id in AGE_DRUG_IDS], [])
        self.assertNotIn(COPPER_ARK_SETTING_ID, game_config.config_world_setting)

        before = {cid: [chara.talent.get(talent_id, 0) for talent_id in AGE_TALENT_IDS] for cid, chara in self.cache.character_data.items() if cid}
        self.assertTrue(any(any(talents[2:]) for talents in before.values()), "开局没有带素质 104~107 的干员，用例不成立")
        self.cache.world_setting[COPPER_ARK_SETTING_ID] = 1
        character_handle.handle_character_setting()
        after = {cid: [chara.talent.get(talent_id, 0) for talent_id in AGE_TALENT_IDS] for cid, chara in self.cache.character_data.items() if cid}
        self.assertEqual(after, before)

    def test_portrait_lookup_never_child_variant(self):
        """image 目录与图片索引里没有「_小」差分；带素质 102、103 的干员、母亲是 MOTHER_NAME 的女儿，查找结果都不含「_小」段"""
        from Script.Core import era_image
        from Script.Design import character_image

        child_files = [os.path.join(path, file) for path, _, files in os.walk(os.path.join(ROOT, "image")) for file in files if CHILD_SEGMENT.search(file)]
        self.assertEqual(child_files, [])
        self.assertEqual([name for name in era_image.image_path_data if CHILD_SEGMENT.search(name)], [])

        picked = {}
        """ 角色名 -> 立绘查找结果 """
        for cid, chara in self.cache.character_data.items():
            if cid == 0:
                continue
            chara.talent[102] = 1
            chara.talent[103] = 1
            picked[chara.name] = character_image.find_character_image_name(cid)
        self.assertIn(MOTHER_NAME, picked, f"开局的角色里没有{MOTHER_NAME}，用例不成立")
        self.assertEqual({name: image for name, image in picked.items() if CHILD_SEGMENT.search(image)}, {})

        mother_id = next(cid for cid, chara in self.cache.character_data.items() if chara.name == MOTHER_NAME)
        daughter = self.world.chara(max(self.cache.character_data) + 1, "测试女儿")
        daughter.relationship.father_id = 0
        daughter.relationship.mother_id = mother_id
        self.assertIsNone(CHILD_SEGMENT.search(character_image.find_character_image_name(daughter.cid)))

    def test_daughter_without_art_has_no_portrait(self):
        """母亲的种族没有女儿图时，女儿的立绘查找结果不在图片索引里，web 渲染器的三个图层路径都为空"""
        from Script.Core import era_image
        from Script.Design import character_image
        from Script.System.Web_Draw_System.character_renderer import CharacterRenderer

        mother_id = next((cid for cid in sorted(self.cache.character_data) if cid and character_image.find_daughter_race_image_name(self.cache.character_data[cid]) == ""), None)
        self.assertIsNotNone(mother_id, "没有种族缺女儿图的角色，用例不成立")
        daughter = self.world.chara(max(self.cache.character_data) + 1, "测试女儿", race=self.cache.character_data[mother_id].race)
        daughter.relationship.father_id = 0
        daughter.relationship.mother_id = mother_id
        image_name = character_image.find_character_image_name(daughter.cid)
        self.assertEqual([name for name in (image_name, f"{image_name}_半身") if name in era_image.image_path_data], [])
        image_data = CharacterRenderer().get_character_image_data(daughter.cid)
        self.assertEqual([image_data.get(key) for key in ("full_body_image", "half_body_image", "head_image")], ["", "", ""])
