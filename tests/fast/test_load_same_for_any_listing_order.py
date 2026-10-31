# -*- coding: UTF-8 -*-
"""
列目录的顺序不影响模组列表与角色口上大小的回归测试
==================================================
文件系统列出目录项的顺序因文件系统和文件的创建先后而异。测试让 os.listdir 与 glob.glob 按名称正序、倒序各返回一次，检查两次的结果相同。受检的结果是 ModManager.scan_mods 扫到的模组顺序与每个模组的文件夹，以及 character_config.find_files_and_get_size 返回的文件与大小。
"""

import contextlib
import glob
import json
import os
from pathlib import Path
import tempfile
from typing import Iterator
from unittest.mock import patch

from Script.Config import character_config
from Script.Core import mod_manager
from tests.fast.base import FastTestCase


@contextlib.contextmanager
def listing_order(reverse: bool) -> Iterator[None]:
  """
  在 with 块内让 os.listdir 按文件名、glob.glob 按路径排序后返回
  Keyword arguments:
  reverse -- True 时倒序，False 时正序
  Return arguments:
  Iterator[None] -- 供 contextlib.contextmanager 使用的生成器，with 块结束后恢复替换前的两个函数
  """
  real_listdir, real_iglob = os.listdir, glob.iglob
  with patch.object(
      os,
      "listdir",
      lambda path=".": sorted(real_listdir(path), reverse=reverse),
  ), patch.object(
      glob,
      "glob",
      lambda pathname, **kwargs: sorted(
          real_iglob(pathname, **kwargs), reverse=reverse
      ),
  ):
    yield


class LoadSameForAnyListingOrderTest(FastTestCase):
  """列目录按文件名正序或倒序时，模组扫描与角色口上文件查找的结果相同"""

  def test_mod_scan_same(self) -> None:
    """
    临时模组文件夹里有 alpha、beta 两个模组，另有 dup_a、dup_b 两个文件夹都声明 mod_id dup。列目录按文件名正序、倒序各扫描一次，两次得到的 (mod_id, 模组文件夹) 列表应相同。正序那次的 mod_id 应依次为 alpha、beta、dup。
    """
    folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
    for item, mod_id in (
        ("alpha", "alpha"),
        ("beta", "beta"),
        ("dup_a", "dup"),
        ("dup_b", "dup"),
    ):
      (folder / item).mkdir()
      (folder / item / "mod_info.json").write_text(
          json.dumps({"mod_id": mod_id, "name": item}), encoding="utf-8"
      )
    self.enterContext(patch.object(mod_manager.ModManager, "_instance", None))
    manager = mod_manager.get_mod_manager()
    manager.mod_folder = str(folder)

    def scan(reverse: bool) -> list[tuple[str, str]]:
      """
      在给定的列目录顺序下扫描一次模组
      Keyword arguments:
      reverse -- True 时列目录按文件名倒序，False 时正序
      Return arguments:
      list[tuple[str, str]] -- 每个模组的 (mod_id, 模组文件夹路径)，顺序同 scan_mods 的返回值
      """
      with listing_order(reverse):
        return [(info.mod_id, info.mod_path) for info in manager.scan_mods()]

    ascending = scan(reverse=False)
    self.assertEqual(
        [mod_id for mod_id, _ in ascending], ["alpha", "beta", "dup"]
    )
    self.assertEqual(ascending, scan(reverse=True))

  def test_talk_files_same(self) -> None:
    """
    临时目录里有角色甲的一个 100 字节口上文件，data/event/chara 里有甲的两个事件文件，分别为 1000 与 3000 字节。工作目录切到临时目录，因为函数按相对路径 data/event/chara 查找事件文件。列目录按文件名正序、倒序各查找一次，两次返回的文件与大小应相同。正序那次应返回两个文件。
    """
    root = Path(self.enterContext(tempfile.TemporaryDirectory()))
    talk_dir = root / "talk"
    talk_dir.mkdir()
    (talk_dir / "talk_甲.csv").write_bytes(b"x" * 100)
    event_dir = root / "data" / "event" / "chara"
    event_dir.mkdir(parents=True)
    (event_dir / "0001_甲.json").write_bytes(b"x" * 1000)
    (event_dir / "0002_甲.json").write_bytes(b"x" * 3000)
    self.enterContext(contextlib.chdir(root))

    def find(reverse: bool) -> dict[str, int]:
      """
      在给定的列目录顺序下查找一次甲的口上文件与事件文件
      Keyword arguments:
      reverse -- True 时列目录按文件名倒序，False 时正序
      Return arguments:
      dict[str, int] -- 文件路径:文件大小（字节）
      """
      with listing_order(reverse):
        return character_config.find_files_and_get_size(str(talk_dir), "甲")

    ascending = find(reverse=False)
    self.assertEqual(len(ascending), 2)
    self.assertEqual(ascending, find(reverse=True))
