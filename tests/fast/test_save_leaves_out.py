# -*- coding: UTF-8 -*-
"""
缓存文件不写读档时重新算出的字段
================================
save_handle.write_save_data 写出的缓存文件（文件 "1"）里没有地图和菜谱。
文件里的罗德岛数据没有仓库容量、干员人数上限、访客上限和床位上限。
文件里，与配置是同一个对象的角色模板存成 None，测试放进去的孩子模板照常存下。
save_handle.load_save 读回的角色模板保持存档前的键序，配置里有的键换回配置的模板对象。
直接 pickle 整个缓存的旧存档，读回后不带地图、菜谱和这四个上限。
读档结束时报的更新条数，与读到的缓存带着全部字段时相同。
"""

import os
import pickle
import tempfile
from unittest import mock

from Script.Config import character_config
from Script.Core import game_type, save_handle
from Script.Design import attr_calculation
from Script.Modules.save_load import index
from Script.UI.Moudle import draw
from tests import kernel_data
from tests.fast.base import FastTestCase

SLOT = "leaves_out"
""" 测试写的存档id """
CHILD = 9999
""" 孩子模板的键，取游戏给新生孩子用的 9000-9999 里的一个 """
REBUILT = (
    "warehouse_capacity",
    "people_max",
    "visitor_max",
    "medical_bed_limit",
)
""" 缓存文件不写、读档时重新算出的罗德岛字段 """


class SaveLeavesOutTest(FastTestCase):
    """缓存文件不写读档时重新算出的字段"""

    def setUp(self) -> None:
        """复原小世界，把存档目录换成临时目录，在角色模板里放一个孩子模板，把四个上限设成非 0 的值"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        child = game_type.NpcTem()
        child.Name = "孩子"
        child.AdvNpc = CHILD
        self.cache.npc_tem_data[CHILD] = child
        for value, name in enumerate(REBUILT, start=7):
            setattr(self.cache.rhodes_island, name, value)

    def raw(self) -> game_type.Cache:
        """
        不经读档的补全，直接解开存档的缓存文件
        Return arguments:
        game_type.Cache -- 文件里存的缓存
        """
        file_path = os.path.join(index.path(SLOT), index.CACHE_FILE)
        with open(file_path, "rb") as f:
            return save_handle.SaveUnpickler(f).load()

    def load_message(self) -> str:
        """
        读档的 Reset 步骤读入存档，返回最后报更新条数的那句话。
        画面输出换成记下文本。小世界没有国家数据，国家的重算换成原样返回。
        Return arguments:
        str -- 「检测完毕，共有N条数据完成了更新」那句话
        """
        texts: list[str] = []

        class Recorder:
            """记下要画的文本，不画"""

            def __init__(self) -> None:
                """文本为空"""
                self.text = ""
                self.width = 0

            def draw(self) -> None:
                """记下文本"""
                texts.append(self.text)

        with (
            mock.patch.object(draw, "NormalDraw", Recorder),
            mock.patch.object(draw, "LeftDraw", Recorder),
            mock.patch.object(
                attr_calculation, "get_country_reset", lambda c: c
            ),
            kernel_data.writing(),
        ):
            save_handle.install_save(SLOT, 1)
        return next(text for text in texts if "完成了更新" in text)

    def test_file_leaves_out_rebuilt_fields(self) -> None:
        """文件里没有地图、菜谱和四个上限。配置里有的键存成 None，孩子模板照常存下，键序与存档前相同"""
        save_handle.write_save_data(SLOT, index.CACHE_FILE, self.cache)
        raw = self.raw()
        self.assertFalse({"map_data", "recipe_data"} & vars(raw).keys())
        self.assertFalse(set(REBUILT) & vars(raw.rhodes_island).keys())
        self.assertEqual(list(raw.npc_tem_data), list(self.cache.npc_tem_data))
        config = character_config.character_tem_list
        saved = {k for k, v in raw.npc_tem_data.items() if v is not None}
        self.assertEqual(saved, set(self.cache.npc_tem_data) - set(config))
        self.assertEqual(raw.npc_tem_data[CHILD].Name, "孩子")

    def test_load_puts_config_templates_back(self) -> None:
        """读回的角色模板与存档前键序相同。配置里有的键是配置的模板对象，孩子模板是存下的那份"""
        save_handle.write_save_data(SLOT, index.CACHE_FILE, self.cache)
        loaded = save_handle.load_save(SLOT)
        self.assertEqual(
            list(loaded.npc_tem_data), list(self.cache.npc_tem_data)
        )
        config = character_config.character_tem_list
        for key, template in loaded.npc_tem_data.items():
            if key in config:
                self.assertIs(template, config[key])
        self.assertEqual(loaded.npc_tem_data[CHILD].Name, "孩子")

    def test_old_save_loads_without_rebuilt_fields(self) -> None:
        """直接 pickle 整个缓存的旧存档，读回后没有地图、菜谱和四个上限"""
        os.makedirs(index.path(SLOT))
        file_path = os.path.join(index.path(SLOT), index.CACHE_FILE)
        with open(file_path, "wb") as f:
            pickle.dump(self.cache, f)
        loaded = save_handle.load_save(SLOT)
        self.assertFalse({"map_data", "recipe_data"} & vars(loaded).keys())
        self.assertFalse(set(REBUILT) & vars(loaded.rhodes_island).keys())

    def test_load_message_counts_no_left_out_field(self) -> None:
        """读档结束时报的更新条数，与读到的缓存带着全部字段时相同，缓存文件不写的字段不算作跨版本更新"""
        self.world.chara(0, "博士")
        whole = pickle.loads(pickle.dumps(self.cache))
        save_handle.write_save_data(SLOT, index.CACHE_FILE, self.cache)
        left_out = self.load_message()
        with mock.patch.object(save_handle, "load_save", lambda save_id: whole):
            self.assertEqual(left_out, self.load_message())
