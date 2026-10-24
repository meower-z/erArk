# -*- coding: UTF-8 -*-
"""
列目录的顺序不影响数据构建与地图载入的回归测试
==============================================
文件系统列出目录项的顺序因检出目录而异（btrfs 上是文件的创建顺序）。
auto_build_config.py（游戏启动时的增量构建）与 buildconfig.py（完整构建）由 data/ 下的分文件构建出 data/*.json 等文件，
map_config.load_dir_now 在运行时读入 data/map；这些产物里条目的顺序决定开局时随机数落到哪个角色身上。
测试让 os.listdir 与 os.scandir（os.walk 经它列目录）按文件名正序与倒序各列一次：
两个构建脚本各在临时目录里跑两次，写出的每个文件逐字节相同（buildconfig.py 写进 po 文件头的生成时间除外）；地图载入两次，场景、地图与地点标签的顺序相同。
"""

import contextlib
import gc
import hashlib
import io
import os
import runpy
import tempfile
from unittest import mock

from tests.slow.base import SlowTestCase
from tests.world import ROOT

BUILD_SCRIPTS = ("auto_build_config.py", "buildconfig.py")
""" 受测的构建脚本，相对仓库根目录 """

SOURCE_DIRS = (
    "csv",
    "event",
    "talk",
    "talk_common",
    "target",
    "character",
    "ui_text",
    "official_event",
    "map",
)
""" 构建脚本读取的 data/ 子目录，在临时目录里以符号链接指向仓库中的真实目录 """


class _ListedScandir:
  """os.scandir 的替身：按给定顺序给出目录项，与 os.scandir 一样可迭代、可当上下文管理器"""

  def __init__(self, entries: list) -> None:
    """
    Keyword arguments:
    entries -- 排好顺序的目录项
    Return arguments:
    无
    """
    self._entries = iter(entries)

  def __iter__(self):
    """
    Keyword arguments:
    无
    Return arguments:
    _ListedScandir -- 自身
    """
    return self

  def __next__(self):
    """
    Keyword arguments:
    无
    Return arguments:
    os.DirEntry -- 下一个目录项
    """
    return next(self._entries)

  def __enter__(self):
    """
    Keyword arguments:
    无
    Return arguments:
    _ListedScandir -- 自身
    """
    return self

  def __exit__(self, *exc_info):
    """
    Keyword arguments:
    exc_info -- 异常信息
    Return arguments:
    无
    """
    self.close()

  def close(self) -> None:
    """
    丢弃余下的目录项
    Keyword arguments:
    无
    Return arguments:
    无
    """
    self._entries = iter(())


def listing_order(reverse: bool):
  """
  让 os.listdir 与 os.scandir 按文件名正序或倒序列目录
  Keyword arguments:
  reverse -- True 为倒序
  Return arguments:
  contextlib.AbstractContextManager -- 生效期间替换 os.listdir 与 os.scandir
  """
  real_listdir, real_scandir = os.listdir, os.scandir

  def ordered_listdir(path="."):
    """
    按文件名排序的 os.listdir
    Keyword arguments:
    path -- 目录
    Return arguments:
    list -- 文件名
    """
    return sorted(real_listdir(path), reverse=reverse)

  def ordered_scandir(path="."):
    """
    按文件名排序的 os.scandir
    Keyword arguments:
    path -- 目录
    Return arguments:
    _ListedScandir -- 目录项
    """
    with real_scandir(path) as entries:
      return _ListedScandir(
          sorted(entries, key=lambda entry: entry.name, reverse=reverse)
      )

  return mock.patch.multiple(
      os, listdir=ordered_listdir, scandir=ordered_scandir
  )


def run_build(script: str, reverse: bool) -> dict:
  """
  在临时目录里跑一次构建脚本，返回它写出的每个文件的摘要
  Keyword arguments:
  script -- 构建脚本，相对仓库根目录
  reverse -- 列目录是否按文件名倒序
  Return arguments:
  dict -- 写出的文件（相对临时目录）: sha256 摘要
  功能描述:
      构建脚本用相对路径读写 data/ 与 Script/Config/，所以在临时目录里建 data/（各源目录链到仓库）与 Script/Config/，
      构建期间把工作目录切到临时目录；构建的打印被收起。摘要不计 po 文件头里的生成时间（POT-Creation-Date 行）。
  """
  with tempfile.TemporaryDirectory() as temp_dir:
    os.makedirs(os.path.join(temp_dir, "Script", "Config"))
    os.makedirs(os.path.join(temp_dir, "data"))
    for name in SOURCE_DIRS:
      os.symlink(
          os.path.join(ROOT, "data", name), os.path.join(temp_dir, "data", name)
      )
    old_cwd = os.getcwd()
    os.chdir(temp_dir)
    try:
      with listing_order(reverse), contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(os.path.join(ROOT, script))
    finally:
      os.chdir(old_cwd)
    # 构建脚本的全局字典与其中的函数互相引用，要回收一次才放掉构建数据
    gc.collect()
    digests = {}
    for root, _, files in os.walk(temp_dir):
      for name in files:
        path = os.path.join(root, name)
        with open(path, "rb") as now_file:
          content = now_file.read()
        if name.endswith(".po"):
          content = b"".join(
              line
              for line in content.splitlines(keepends=True)
              if not line.startswith(b'"POT-Creation-Date:')
          )
        digests[os.path.relpath(path, temp_dir)] = hashlib.sha256(
            content
        ).hexdigest()
    return digests


class BuildSameForAnyListingOrderTest(SlowTestCase):
  """列目录按文件名正序或倒序，构建产物与地图载入的结果都相同"""

  def test_build_outputs_same(self) -> None:
    """两个构建脚本各跑两次（正序、倒序），写出的文件集合相同，每个文件逐字节相同（po 文件头的生成时间除外）"""
    for script in BUILD_SCRIPTS:
      ascending = run_build(script, reverse=False)
      descending = run_build(script, reverse=True)
      self.assertIn(os.path.join("data", "Character.json"), ascending, script)
      self.assertEqual(sorted(ascending), sorted(descending), script)
      changed = sorted(
          path for path in ascending if ascending[path] != descending[path]
      )
      self.assertEqual(
          changed, [], f"{script} 在两种列目录顺序下写出的这些文件不同"
      )

  def test_map_order_same(self):
    """地图载入两次（正序、倒序），场景字典、地图字典与地点标签（标签及其场景列表）的顺序相同"""
    from Script.Config import map_config
    from Script.Core import constant

    def load_map(reverse: bool) -> tuple:
      """
      在空的场景、地图与地点字典上载入 data/map，返回三者的顺序
      Keyword arguments:
      reverse -- 列目录是否按文件名倒序
      Return arguments:
      tuple -- (场景路径列表, 地图路径列表, [(地点标签, 场景路径列表)])
      """
      with listing_order(reverse), mock.patch.object(
          self.cache, "scene_data", {}
      ), mock.patch.object(self.cache, "map_data", {}), mock.patch.object(
          constant, "place_data", {}
      ):
        map_config.load_dir_now(map_config.map_data_path)
        return (
            list(self.cache.scene_data),
            list(self.cache.map_data),
            [(tag, list(paths)) for tag, paths in constant.place_data.items()],
        )

    ascending = load_map(reverse=False)
    descending = load_map(reverse=True)
    self.assertGreater(len(ascending[0]), 0)
    self.assertEqual(ascending[0], descending[0], "场景字典的顺序不同")
    self.assertEqual(ascending[1], descending[1], "地图字典的顺序不同")
    self.assertEqual(ascending[2], descending[2], "地点标签的顺序不同")
