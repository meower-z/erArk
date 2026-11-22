# -*- coding: UTF-8 -*-
"""
读版本 22 存档后开新周目去掉配置外素质
======================================
开新游戏并存档，把槽位换成版本 22 的旧存档，在文件 "1" 的 npc_tem_data 里放入带 6 与 7 号素质的局内生成模板。
6 与 7 号素质不在 Talent.csv（game_config.config_talent）里。
读档后验证该角色存在，再按「醒来」开始新周目。
新周目后该角色仍存在，且 identity.table() 里每个角色都不带 game_config.config_talent 中没有的素质编号。
"""

import importlib
import shutil
from types import ModuleType

from tests.slow.base import SlowTestCase

SAVE_ID = "test_new_round_generated_talents"
""" 测试用的存档 id """
GENERATED = 9123
""" 测试用的局内生成角色模板编号（取 9000-9999 范围） """


def game(name: str) -> ModuleType:
    """
    按模块名延迟导入游戏模块，避免在 SlowTestCase 启动 FullWorld 之前触发导入
    Keyword arguments:
    name -- 要导入的完整模块名
    Return arguments:
    ModuleType -- 导入后的模块对象
    """
    return importlib.import_module(name)


class NewRoundGeneratedTalentsTest(SlowTestCase):
    """读版本 22 存档并开新周目后，验证局内生成角色不带配置外素质"""

    def write_version_22(self) -> None:
        """
        存一份当前进度，再把它换成版本 22 的旧存档。
        文件 "1" 的 npc_tem_data 写入静态配置键的 None 占位与带 6、7 号素质的局内生成模板，
        文件 "2" 的版本设为 22
        """
        character_config = game("Script.Config.character_config")
        character_handle = game("Script.Design.character_handle")
        save_handle = game("Script.Core.save_handle")
        legacy_save = game("tests.legacy_save")
        template = character_handle.create_empty_character_tem()
        template.Name = "甲"
        template.AdvNpc = GENERATED
        template.Talent = {0: 1, 6: 1, 7: 1, 104: 1}
        template.Hp = 1500
        template.Mp = 1200
        save_handle.establish_save(SAVE_ID)
        templates = dict.fromkeys(character_config.character_tem_list)
        cache = legacy_save.old(
            "Cache", npc_tem_data={**templates, GENERATED: template}
        )
        legacy_save.to_legacy(SAVE_ID, cache, version=22)

    def test_new_round_after_version_22_load(self) -> None:
        """读版本 22 存档并开新周目后，局内生成角色仍存在，所有角色都不带 config_talent 中没有的素质"""
        from tests import world

        save_handle = game("Script.Core.save_handle")
        game_config = game("Script.Config.game_config")
        abilities = game("Script.Modules.domains.abilities")
        new_round = game("Script.UI.Panel.new_round")
        identity = game("Script.Modules.domains.identity")
        try:
            self.write_version_22()
            save_handle.input_load_save(SAVE_ID)
        finally:
            shutil.rmtree(
                save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True
            )
        self.assertIn(GENERATED, identity.table())
        self.world.player.press("醒来")
        world.act(new_round.New_Round_Handle().start_new_round)
        self.world.player.check_done()
        self.assertIn(GENERATED, identity.table())
        unknown = {
            cid: sorted(
                set(abilities.talent(cid)) - set(game_config.config_talent)
            )
            for cid in identity.table()
        }
        self.assertEqual({cid: ids for cid, ids in unknown.items() if ids}, {})
