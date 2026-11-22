# -*- coding: UTF-8 -*-
"""
缓存文件不写读档时重新算出的字段
================================
save_handle.write_save_data 写出的缓存文件（文件 "1"）里没有地图和菜谱。
文件里也没有罗德岛对象。
旧格式缓存文件带着 npc_tem_data，其中配置键为 None，局内生成模板为原对象。
save_handle.load_save 读回后保持原来的键序，把配置键的 None 换回配置的模板对象，并保留局内生成模板。
直接 pickle 整个缓存的旧存档，读回后不带地图、菜谱，罗德岛对象上没有仓库容量、干员人数上限与床位上限。
读档结束时报的更新条数，与读到的缓存带着全部字段时相同。
"""

import os
import pickle
import tempfile
from unittest import mock

from Script.Config import character_config
from Script.Core import game_type, save_handle
from Script.Kernel import core
from Script.Modules.domains import country
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import index
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase

SLOT = "leaves_out"
""" 测试写的存档id """
CHILD = 9999
""" 孩子模板的键，取游戏给新生孩子用的 9000-9999 里的一个 """
REBUILT = (
    "warehouse_capacity",
    "people_max",
    "medical_bed_limit",
)
""" 缓存文件不写、读档时重新算出的罗德岛字段 """


class SaveLeavesOutTest(FastTestCase):
    """缓存文件不写读档时重新算出的字段"""

    def setUp(self) -> None:
        """复原小世界，把存档目录换成临时目录，备好一个局内生成模板"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        child = game_type.NpcTem()
        child.Name = "孩子"
        child.AdvNpc = CHILD
        self.child = child

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
        用读档的 Reset 步骤读入存档，交回最后报更新条数的那句话。
        读档在以当前 GameState 为底的缓冲区里进行，写下的数据随后丢掉，所以每次都从同一个状态读档。
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
            mock.patch.object(country, "fill", lambda: None),
            working.based_on(core.state()),
        ):
            save_handle.install_save(SLOT, 1)
        return next(text for text in texts if "完成了更新" in text)

    def test_file_leaves_out_rebuilt_fields(self) -> None:
        """写出的缓存文件里没有 map_data、recipe_data 与罗德岛对象"""
        save_handle.write_save_data(SLOT, index.CACHE_FILE, self.cache)
        raw = self.raw()
        self.assertFalse({"map_data", "recipe_data"} & vars(raw).keys())
        self.assertNotIn("rhodes_island", vars(raw))

    def test_load_puts_config_templates_back(self) -> None:
        """旧格式缓存文件经 load_save 读回后，npc_tem_data 保持键序，配置键换回配置的模板对象，局内生成模板不变"""
        config = character_config.character_tem_list
        templates = {**dict.fromkeys(config), CHILD: self.child}
        legacy = game_type.Cache.__new__(game_type.Cache)
        vars(legacy).update(vars(self.cache), npc_tem_data=templates)
        save_handle.write_save_data(SLOT, index.CACHE_FILE, legacy)
        loaded = vars(save_handle.load_save(SLOT))["npc_tem_data"]
        self.assertEqual(list(loaded), list(templates))
        for key, template in loaded.items():
            if key in config:
                self.assertIs(template, config[key])
        self.assertEqual(loaded[CHILD].Name, "孩子")

    def test_old_save_loads_without_rebuilt_fields(self) -> None:
        """直接 pickle 整个缓存的旧存档，读回后没有地图、菜谱，罗德岛对象上没有 REBUILT 的三个上限"""
        old = pickle.loads(pickle.dumps(self.cache))
        old.rhodes_island = game_type.Rhodes_Island()
        for value, name in enumerate(REBUILT, start=7):
            setattr(old.rhodes_island, name, value)
        os.makedirs(index.path(SLOT))
        file_path = os.path.join(index.path(SLOT), index.CACHE_FILE)
        with open(file_path, "wb") as f:
            pickle.dump(old, f)
        loaded = save_handle.load_save(SLOT)
        self.assertFalse({"map_data", "recipe_data"} & vars(loaded).keys())
        island = vars(loaded)["rhodes_island"]
        self.assertFalse(set(REBUILT) & vars(island).keys())

    def test_load_message_counts_no_left_out_field(self) -> None:
        """读档结束时报的更新条数，与读到的缓存带着全部字段时相同，缓存文件不写的字段不算作跨版本更新"""
        self.world.chara(0, "博士")
        whole = pickle.loads(pickle.dumps(self.cache))
        whole.rhodes_island = game_type.Rhodes_Island()
        save_handle.write_save_data(SLOT, index.CACHE_FILE, self.cache)
        left_out = self.load_message()
        with mock.patch.object(save_handle, "load_save", lambda save_id: whole):
            self.assertEqual(left_out, self.load_message())
