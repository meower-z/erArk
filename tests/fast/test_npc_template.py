# -*- coding: UTF-8 -*-
"""
世界生成的角色模板在内核状态里（roster.npc_templates）
======================================================
- 往返：局内生成的模板经存读档后属性不变，编号排在 ids() 末尾，静态模板仍是配置原对象。
- 版本 22 旧存档：读档导入文件 "1" 里的局内生成模板，从它的素质里去掉 6 与 7（Talent.csv 里没有的素质），
  保留其余字段并建出对应角色。
- 隔离：存档后当前对局新增的局内生成模板，读回该存档后不在模板表与角色表里。
"""

import tempfile
from unittest import mock

from Script.Config import character_config
from Script.Core import game_type, save_handle
from Script.Design import character_handle
from Script.Kernel import core
from Script.Modules.domains import country, identity, npc_template
from Script.Modules.domains import playthrough, roster
from Script.Modules.save_load import index
from tests import kernel_data, legacy_save
from tests.fast.base import FastTestCase

SAVE_ID = "npc_template_test"
""" 测试用的存档 id """
GENERATED = 9123
""" 测试用的局内生成角色模板编号（取 9000-9999 范围） """


def generated(talent: dict[int, int]) -> game_type.NpcTem:
    """
    构造一个编号为 GENERATED 的测试用局内生成角色模板
    Keyword arguments:
    talent -- 写入模板的素质表
    Return arguments:
    game_type.NpcTem -- 填好名字、编号、素质、HP 与 MP 的角色模板
    """
    template = character_handle.create_empty_character_tem()
    template.Name = "甲"
    template.AdvNpc = GENERATED
    template.Talent = dict(talent)
    template.Hp = 1500
    template.Mp = 1200
    return template


class NpcTemplateTest(FastTestCase):
    """局内生成角色模板的存读档往返、版本 22 导入与读档隔离测试"""

    def setUp(self) -> None:
        """复原小世界，切到临时存档目录并清空内核事件列表，放入玩家、名册、国家与周目设定"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.enterContext(mock.patch.object(core, "_events", []))
        self.world.chara(0, "博士")
        kernel_data.put(roster.set_active, {0})
        kernel_data.written(country.fill)
        kernel_data.written(playthrough.reset_difficulty_and_birth)

    def make_version_22(self, templates: dict[int, object]) -> None:
        """
        把已写出的测试槽位换成版本 22 的旧存档，其文件 "1" 的 npc_tem_data 存放 templates
        Keyword arguments:
        templates -- 写入旧存档文件 "1" 的 npc_tem_data 字典
        """
        cache = legacy_save.old("Cache", npc_tem_data=templates)
        legacy_save.to_legacy(SAVE_ID, cache, version=22)

    def test_generated_template_survives_save_and_load(self) -> None:
        """局内生成的模板经存读档后属性不变，编号排在末尾，静态模板仍是配置原对象"""
        template = generated({0: 1, 104: 1})
        template.Ability = {3: 2}
        template.Cloth = [501, 651]
        kernel_data.written(npc_template.add, template)
        save_handle.establish_save(SAVE_ID)
        save_handle.input_load_save(SAVE_ID)
        loaded = npc_template.get(GENERATED)
        assert loaded is not None
        self.assertEqual(vars(loaded), vars(template))
        self.assertEqual(npc_template.ids()[-1], GENERATED)
        self.assertIs(
            npc_template.get(1), character_config.character_tem_list[1]
        )

    def test_version_22_save_drops_gone_talents(self) -> None:
        """版本 22 存档读档后导入局内生成模板，去掉 6 与 7 号素质并保留其余字段，角色表包含该角色"""
        save_handle.establish_save(SAVE_ID)
        config = character_config.character_tem_list
        templates: dict[int, object] = dict.fromkeys(config)
        templates[GENERATED] = generated({0: 1, 6: 1, 7: 1, 104: 1})
        self.make_version_22(templates)
        save_handle.input_load_save(SAVE_ID)
        loaded = npc_template.get(GENERATED)
        assert loaded is not None
        self.assertEqual(loaded.Talent, {0: 1, 104: 1})
        self.assertEqual(
            (loaded.Name, loaded.Hp, loaded.Mp), ("甲", 1500, 1200)
        )
        self.assertEqual(npc_template.ids(), [*config, GENERATED])
        self.assertIn(GENERATED, identity.table())

    def test_load_keeps_running_game_templates_out(self) -> None:
        """存档后当前对局新增的局内生成模板，读回该存档后不在模板表与角色表里"""
        save_handle.establish_save(SAVE_ID)
        kernel_data.written(npc_template.add, generated({0: 1}))
        save_handle.input_load_save(SAVE_ID)
        self.assertIsNone(npc_template.get(GENERATED))
        self.assertNotIn(GENERATED, identity.table())
