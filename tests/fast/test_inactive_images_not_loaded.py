# -*- coding: UTF-8 -*-
"""
停用图片不被加载、不被打包的检查
================================
游戏不显示的图片放在仓库根目录的 image_inactive 文件夹，它在游戏加载图片的 image 目录之外。
本测试检查仓库里的文件，不检查游戏行为：image 目录下没有重名图片（启动时不打印「图片重名」提示）；
image_inactive 里有 png，且不在 image 目录里；发布流程 .github/workflows/python-app.yml 的复制命令不复制 image_inactive，也不复制整个仓库根目录。
"""

import os
import re

from Script.Core import image_path_index
from tests.fast.base import FastTestCase
from tests.world import ROOT

IMAGE_DIR = os.path.join(ROOT, "image")
""" 游戏加载图片的目录 """
INACTIVE_DIR = os.path.join(ROOT, "image_inactive")
""" 停用图片的文件夹 """
WORKFLOW = os.path.join(ROOT, ".github", "workflows", "python-app.yml")
""" 发布流程 """


class InactiveImagesNotLoadedTest(FastTestCase):
  """image 下没有重名图片；停用图片在 image 之外，发布流程不复制它们"""

  def test_no_duplicate_names_under_image(self) -> None:
    """image 目录下没有重名图片"""
    _, duplicates = image_path_index.build_image_path_index(IMAGE_DIR)
    self.assertEqual(sorted(duplicates), [])

  def test_inactive_folder_outside_image(self) -> None:
    """image_inactive 里有 png，且不在 image 目录里"""
    inactive_pngs = [
        file
        for _, _, files in os.walk(INACTIVE_DIR)
        for file in files
        if file.endswith(".png")
    ]
    self.assertTrue(inactive_pngs, "image_inactive 里没有 png")
    self.assertFalse(
        os.path.abspath(INACTIVE_DIR).startswith(
            os.path.abspath(IMAGE_DIR) + os.sep
        )
    )

  def test_release_copies_neither_inactive_nor_root(self) -> None:
    """发布流程有复制命令，复制来源里没有 image_inactive，也没有整个仓库根目录"""
    with open(WORKFLOW, encoding="utf-8") as f:
      copy_sources = re.findall(r"Copy-Item\s+(\"[^\"]+\"|\S+)", f.read())
    self.assertTrue(copy_sources, "发布流程里没有 Copy-Item 命令")
    self.assertEqual(
        [source for source in copy_sources if "image_inactive" in source], []
    )
    self.assertEqual(
        [
            source
            for source in copy_sources
            if source.strip('"') in (".", "*", "./*", ".\\*")
        ],
        [],
    )
