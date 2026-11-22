# -*- coding: UTF-8 -*-
"""
load_save 读取旧存档缓存文件的测试
==================================
- 旧缓存文件里 npc_tem_data 以 None 占位的配置键补回配置模板，保留键序与局内生成模板；
- 丢掉 map_data、recipe_data 与罗德岛对象上重算的上限字段；
- 读 save.json 槽位报告的更新条数与读空旧缓存槽位相同。
"""

import tempfile
from unittest import mock

from Script.Config import character_config
from Script.Core import game_type, save_handle
from Script.Kernel import core
from Script.Modules.domains import country
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import index
from Script.UI.Moudle import draw
from tests import legacy_save
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
""" 旧存档中读档时丢弃并重新算出的罗德岛字段 """


class SaveLeavesOutTest(FastTestCase):
    """load_save 处理旧缓存文件与 save.json 槽位的测试"""

    def setUp(self) -> None:
        """复原小世界，把存档目录换成临时目录，备好一个局内生成模板"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        child = game_type.NpcTem()
        child.Name = "孩子"
        child.AdvNpc = CHILD
        self.child = child

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

    def test_load_puts_config_templates_back(self) -> None:
        """
        旧缓存的 npc_tem_data 对配置键存 None 时，load_save 保留键序、补回配置模板并保留局内模板
        """
        config = character_config.character_tem_list
        templates = {**dict.fromkeys(config), CHILD: self.child}
        legacy_save.write_cache(
            SLOT, legacy_save.old("Cache", npc_tem_data=templates)
        )
        loaded = save_handle.load_save(SLOT)["npc_tem_data"]
        self.assertEqual(list(loaded), list(templates))
        for key, template in loaded.items():
            if key in config:
                self.assertIs(template, config[key])
        self.assertEqual(loaded[CHILD].Name, "孩子")

    def test_old_save_loads_without_rebuilt_fields(self) -> None:
        """旧缓存带 map_data、recipe_data 与罗德岛 REBUILT 上限时，load_save 全部丢弃"""
        island = legacy_save.old(
            "Rhodes_Island",
            **{name: value for value, name in enumerate(REBUILT, start=7)},
        )
        legacy_save.write_cache(
            SLOT,
            legacy_save.old(
                "Cache", map_data={}, recipe_data={}, rhodes_island=island
            ),
        )
        loaded = save_handle.load_save(SLOT)
        self.assertFalse({"map_data", "recipe_data"} & loaded.keys())
        self.assertFalse(set(REBUILT) & vars(loaded["rhodes_island"]).keys())

    def test_json_save_imports_like_an_empty_old_cache(self) -> None:
        """
        读取 save.json 槽位报告的更新条数与读取带空旧缓存文件的同一槽位相同
        """
        self.world.chara(0, "博士")
        save_handle.establish_save(SLOT)
        from_json = self.load_message()
        legacy_save.to_legacy(SLOT, legacy_save.old("Cache"))
        self.assertFalse(index.is_json(SLOT))
        self.assertEqual(from_json, self.load_message())
