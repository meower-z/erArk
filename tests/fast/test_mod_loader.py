"""
测试 mod_manager 加载已启用模组的行为。
"""

from pathlib import Path
import sys
import tempfile
from types import ModuleType
from typing import Any
from unittest.mock import Mock, patch

from Script.Config import game_config
from Script.Core import get_text, mod_manager
from Script.Design import handle_premise
from tests.fast.base import FastTestCase


class RecordingModManager(mod_manager.ModManager):
  """
  ModManager 的测试子类。
  它把新建模组命名空间的浅拷贝存入 self.injected。
  """

  def _create_mod_namespace(
      self, mod_info: mod_manager.ModInfo
  ) -> dict[str, Any]:
    """
    调用父类方法创建模组命名空间。
    该命名空间的浅拷贝会存入 self.injected。
    参数 mod_info (mod_manager.ModInfo)：模组信息。
    返回 (dict[str, Any])：父类创建的命名空间字典。
    """
    namespace = super()._create_mod_namespace(mod_info)
    self.injected = namespace.copy()
    return namespace


class ModLoaderTest(FastTestCase):
  """
  模组加载器的快速测试类。
  """

  def setUp(self) -> None:
    """
    用补丁隔离模组管理器的全局状态。
    测试结束后这些补丁会自动撤销。
    新建的 RecordingModManager 实例存入 self.manager。
    返回 (None)：无返回值。
    """
    super().setUp()
    self.enterContext(patch.object(RecordingModManager, "_instance", None))
    self.enterContext(
        patch.object(mod_manager, "ModManager", RecordingModManager)
    )
    self.enterContext(patch.object(mod_manager, "_original_functions", {}))
    self.enterContext(patch.object(mod_manager, "_mod_functions", {}))
    self.enterContext(patch.object(mod_manager, "_mod_assets", {}))
    self.manager = RecordingModManager()

  def test_semen_mod_loads_and_settles_with_injected_objects(self) -> None:
    """
    验证 semen_boost 模组的替换函数使用加载器注入的对象。
    验证该替换函数能完成一次射精结算。
    被替换的目标模块由测试构造的模块代替。
    返回 (None)：无返回值。
    """
    self.manager.scan_mods()
    info = self.manager.mods["semen_boost"]
    info.enabled = True
    self.manager.enabled_mods = [info.mod_id]
    target = ModuleType("Script.UI.Panel.ejaculation_panel")
    setattr(target, "common_ejaculation", Mock(return_value=("original", 7)))
    self.enterContext(patch.dict(sys.modules, {target.__name__: target}))
    self.enterContext(patch.object(handle_premise, "handle_pl_semen_le_2"))
    self.assertEqual(self.manager.load_all_enabled_mods(), {})
    self.assertTrue(info.loaded)
    namespace = target.common_ejaculation.__globals__
    asset_lookup = self.manager.injected["get_mod_asset"]
    self.assertIs(namespace["cache"], self.cache)
    self.assertIs(namespace["game_config"], game_config)
    self.assertIs(namespace["_"], get_text._)
    self.assertIs(namespace["get_mod_asset"], asset_lookup)
    self.assertTrue(
        Path(
            asset_lookup("mod:semen_boost/assets/data/Semen_Shoot_Amount.csv")
        ).is_file()
    )
    player = self.world.chara(0, "博士")
    player.target_character_id = 0
    player.semen_point = 50
    player.tem_extra_semen_point = 0
    player.action_info.day_first_shoot_semen = False
    player.h_state.endure_not_shot_count = 0
    for flag in ("p_orgasm_strong", "p_orgasm_normal"):
      player.second_behavior[flag] = 0
    for name in (
        "handle_self_semen_energy_agent",
        "handle_pl_semen_tmp_ge_max",
        "handle_self_semen_thick_1",
    ):
      self.enterContext(patch.object(handle_premise, name, return_value=0))
    self.enterContext(
        patch.object(
            handle_premise, "handle_aromatherapy_flag_7", return_value=1
        )
    )
    self.enterContext(
        patch.object(namespace["random"], "uniform", return_value=1.0)
    )
    before = self.cache.rhodes_island.total_semen_count
    text, amount = target.common_ejaculation()
    self.assertEqual(amount, 400)
    self.assertIn(game_config.config_aromatherapy_recipes[7].name, text)
    self.assertEqual(
        self.cache.rhodes_island.total_semen_count, before + amount
    )
    self.assertEqual(player.semen_point, 0)
    self.assertEqual(player.h_state.just_shoot, 1)

  def test_replacement_calls_saved_original_with_arguments(self) -> None:
    """
    验证替换函数通过 call_original 调用被替换的原函数。
    测试检查传给原函数的参数。
    测试检查包装后的返回值。
    返回 (None)：无返回值。
    """
    target = ModuleType("mod_loader_target")
    original = Mock(return_value=73)
    setattr(target, "run", original)
    self.enterContext(patch.dict(sys.modules, {target.__name__: target}))
    with tempfile.TemporaryDirectory() as temporary:
      Path(temporary, "wrapper.py").write_text(
          "def wrapped(value, *, scale):\n"
          "  return call_original(\n"
          '      "mod_loader_target", "run", value, scale=scale) + 1\n',
          encoding="utf-8",
      )
      info = mod_manager.ModInfo(
          "wrapper",
          {
              "scripts": [
                  {
                      "file": "wrapper.py",
                      "functions": [
                          {
                              "name": "wrapped",
                              "type": "replace",
                              "target_module": target.__name__,
                              "target_function": "run",
                          }
                      ],
                  }
              ]
          },
          temporary,
      )
      info.enabled = True
      self.manager.mods[info.mod_id] = info
      self.manager.enabled_mods = [info.mod_id]
      self.assertEqual(self.manager.load_all_enabled_mods(), {})
      self.assertEqual(target.run(9, scale=3), 74)
      original.assert_called_once_with(9, scale=3)
      self.assertIs(
          mod_manager.get_original_function(target.__name__, "run"), original
      )
