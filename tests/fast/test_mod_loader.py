"""
本模块测试 Script.Core.mod_manager.ModManager 加载 Mod 的过程。
其中两个测试用 ModManager 加载仓库 mod/ 目录下的 semen_boost Mod。
另一个测试在临时目录中写入一个 Mod 脚本，并用该脚本替换一个替身模块中的函数。替身模块是测试自己创建并放入 sys.modules 的模块对象。
"""

from pathlib import Path
import sys
import tempfile
from types import ModuleType
from typing import Any
from unittest.mock import Mock, patch

from Script.Config import game_config
from Script.Core import mod_manager
from Script.Design import handle_premise
from tests.fast.base import FastTestCase


class FailedImportModManager(mod_manager.ModManager):
  """
  本类是 mod_manager.ModManager 的子类，供测试使用。
  本类让 _create_mod_namespace 中对 Script.Config 的导入失败。
  因此本类的 _create_mod_namespace 返回的字典缺少 game_config、normal_config、constant 和 _。
  """

  def _create_mod_namespace(
      self, mod_info: mod_manager.ModInfo
  ) -> dict[str, Any]:
    """
    本方法在调用父类的 _create_mod_namespace 期间，把 sys.modules 中的 Script.Config 映射为 None。
    这个映射让父类中对 Script.Config 的导入抛出 ImportError。父类的 except 分支忽略该异常。

    参数:
        mod_info (mod_manager.ModInfo): 要加载的 Mod 的信息

    返回:
        dict[str, Any] -- Mod 脚本运行所用的命名空间字典，
        其中缺少 game_config、normal_config、constant 和 _
    """
    with patch.dict(sys.modules, {"Script.Config": None}):
      return super()._create_mod_namespace(mod_info)


class ModLoaderTest(FastTestCase):
  """
  本类测试 ModManager 加载 semen_boost Mod 之后的结果。
  本类还测试一个替换函数能通过 call_original 调用被替换的原函数。
  """

  def setUp(self) -> None:
    """
    本方法让每个测试新建 ModManager 和 FailedImportModManager 的单例。
    本方法让每个测试从空的 _original_functions、_mod_functions 和 _mod_assets 开始。
    对 handle_premise.handle_pl_semen_le_2 的补丁让 Mod 对该函数的替换在测试结束后撤销。
    本方法把一个名为 Script.UI.Panel.ejaculation_panel 的替身模块放入 sys.modules。
    该替身模块存为 self.panel。替身模块中的 common_ejaculation 是一个 Mock。本方法施加的补丁在每个测试结束后撤销。

    返回:
        None
    """
    super().setUp()
    for manager_class in (mod_manager.ModManager, FailedImportModManager):
      self.enterContext(patch.object(manager_class, "_instance", None))
    self.enterContext(patch.object(mod_manager, "_original_functions", {}))
    self.enterContext(patch.object(mod_manager, "_mod_functions", {}))
    self.enterContext(patch.object(mod_manager, "_mod_assets", {}))
    self.enterContext(patch.object(handle_premise, "handle_pl_semen_le_2"))
    self.panel = ModuleType("Script.UI.Panel.ejaculation_panel")
    setattr(self.panel, "common_ejaculation", Mock(return_value=("", 0)))
    self.enterContext(
        patch.dict(sys.modules, {self.panel.__name__: self.panel})
    )

  def load_semen_mod(self, manager: mod_manager.ModManager) -> None:
    """
    本方法让 manager 扫描 Mod 目录。本方法只启用 semen_boost。本方法加载已启用的 Mod。本方法断言加载没有返回错误。
    本方法断言 semen_boost 的 loaded 为 True。

    参数:
        manager (mod_manager.ModManager): 用来加载 Mod 的管理器

    返回:
        None
    """
    manager.scan_mods()
    info = manager.mods["semen_boost"]
    info.enabled = True
    manager.enabled_mods = [info.mod_id]
    self.assertEqual(manager.load_all_enabled_mods(), {})
    self.assertTrue(info.loaded)

  def test_semen_mod_settles_after_load(self) -> None:
    """
    本测试用 ModManager 加载 semen_boost。
    本测试断言加载后 handle_premise.handle_pl_semen_le_2(0) 返回 0。
    本测试随后调用 Mod 换到替身模块上的 common_ejaculation。调用前，随机系数被固定为 1.0。
    角色 0 的 p_orgasm_strong 和 p_orgasm_normal 被设为 0。
    handle_aromatherapy_flag_7 被设为返回 1。handle_self_semen_energy_agent、
    handle_pl_semen_tmp_ge_max 和 handle_self_semen_thick_1 被设为返回 0。
    本测试断言射精量为 400。本测试断言返回的文本包含 game_config.config_aromatherapy_recipes[7].name。
    本测试断言 total_semen_count 增加的量等于射精量。本测试断言角色 0 的 semen_point 从 50 降为 0。
    本测试断言角色 0 的 h_state.just_shoot 为 1。

    返回:
        None
    """
    self.load_semen_mod(mod_manager.ModManager())
    self.assertEqual(handle_premise.handle_pl_semen_le_2(0), 0)
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
    settle = self.panel.common_ejaculation
    self.enterContext(
        patch.object(settle.__globals__["random"], "uniform", return_value=1.0)
    )
    before = self.cache.rhodes_island.total_semen_count
    text, amount = settle()
    self.assertEqual(amount, 400)
    self.assertIn(game_config.config_aromatherapy_recipes[7].name, text)
    self.assertEqual(
        self.cache.rhodes_island.total_semen_count, before + amount
    )
    self.assertEqual(player.semen_point, 0)
    self.assertEqual(player.h_state.just_shoot, 1)

  def test_semen_mod_loads_when_guarded_import_fails(self) -> None:
    """
    本测试用 FailedImportModManager 加载 semen_boost。
    此时 Mod 脚本运行所用的字典缺少 game_config、normal_config、constant 和 _。本测试断言加载没有返回错误。
    本测试断言 Mod 注册到替身模块上的 multiply_by_ten(3) 返回 30。
    本测试断言替换后的 handle_premise.handle_pl_semen_le_2(0) 返回 0。
    本测试断言调用替换后的 common_ejaculation 会抛出提到 _ 的 NameError。

    返回:
        None
    """
    self.load_semen_mod(FailedImportModManager())
    self.assertEqual(self.panel.multiply_by_ten(3), 30)
    self.assertEqual(handle_premise.handle_pl_semen_le_2(0), 0)
    self.world.chara(0, "博士")
    with self.assertRaisesRegex(NameError, "'_'"):
      self.panel.common_ejaculation()

  def test_replacement_calls_saved_original_with_arguments(self) -> None:
    """
    本测试在临时目录中写入 Mod 脚本 wrapper.py。该脚本中的 wrapped 替换替身模块 mod_loader_target 中的 run。
    wrapped 用 call_original 调用原来的 run。wrapped 返回原来的 run 的结果加 1。
    本测试断言 run(9, scale=3) 返回 74。本测试断言原来的 run 以参数 (9, scale=3) 被调用一次。
    本测试断言 mod_manager.get_original_function 返回原来的 run。

    返回:
        None
    """
    target = ModuleType("mod_loader_target")
    original = Mock(return_value=73)
    setattr(target, "run", original)
    self.enterContext(patch.dict(sys.modules, {target.__name__: target}))
    manager = mod_manager.ModManager()
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
      manager.mods[info.mod_id] = info
      manager.enabled_mods = [info.mod_id]
      self.assertEqual(manager.load_all_enabled_mods(), {})
      self.assertEqual(target.run(9, scale=3), 74)
      original.assert_called_once_with(9, scale=3)
      self.assertIs(
          mod_manager.get_original_function(target.__name__, "run"), original
      )
