"""
本模块测试 Script.Core.mod_manager.ModManager 重新扫描 Mod 文件夹之后的加载状态与错误信息。
模组管理面板打开时会这样重新扫描。各 Mod 在重新扫描之后应仍带着启动时的加载结果。
"""

import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from Script.Core import mod_manager
from tests.fast.base import FastTestCase


class ModLoadStateTest(FastTestCase):
  """
  本类在临时目录中写入一个能加载的 Mod 和一个缺脚本文件的 Mod。
  本类测试先加载、再重新扫描之后，两个 Mod 的加载状态与错误信息。
  """

  def setUp(self) -> None:
    """
    本方法让每个测试新建 ModManager 的单例，并从空的 _original_functions、_mod_functions 和 _mod_assets 开始。
    本方法在临时目录中写入 Mod good、Mod broken，以及启用这两个 Mod 的 mod_config.json。
    good 的脚本 good.py 存在。broken 的 mod_info.json 指向不存在的脚本 missing.py。
    本方法把单例的 mod_folder 指向该临时目录，并把单例存为 self.manager。
    本方法施加的补丁和临时目录在每个测试结束后撤销。

    返回:
        None
    """
    super().setUp()
    self.enterContext(patch.object(mod_manager.ModManager, "_instance", None))
    self.enterContext(patch.object(mod_manager, "_original_functions", {}))
    self.enterContext(patch.object(mod_manager, "_mod_functions", {}))
    self.enterContext(patch.object(mod_manager, "_mod_assets", {}))
    folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
    for mod_id, script in (("good", "good.py"), ("broken", "missing.py")):
      (folder / mod_id).mkdir()
      (folder / mod_id / "mod_info.json").write_text(
          json.dumps({"mod_id": mod_id, "scripts": [{"file": script}]}),
          encoding="utf-8",
      )
    (folder / "good" / "good.py").write_text("VALUE = 1\n", encoding="utf-8")
    (folder / "mod_config.json").write_text(
        json.dumps({"enabled_mods": ["good", "broken"], "load_order": []}),
        encoding="utf-8",
    )
    self.manager = mod_manager.get_mod_manager()
    self.manager.mod_folder = str(folder)

  def test_rescan_keeps_startup_load_state(self) -> None:
    """
    本方法先用 init_mod_system 加载两个 Mod。broken 加载失败，所以 init_mod_system 返回 False。
    本方法再像模组管理面板打开时那样调用一次 scan_mods。
    本方法检查 good 已加载且错误信息为空。
    本方法还检查 broken 未加载且错误信息含 missing.py。

    返回:
        None
    """
    self.assertFalse(mod_manager.init_mod_system())
    self.manager.scan_mods()
    good = self.manager.mods["good"]
    broken = self.manager.mods["broken"]
    self.assertTrue(good.loaded)
    self.assertEqual(good.error_message, "")
    self.assertFalse(broken.loaded)
    self.assertIn("missing.py", broken.error_message)
