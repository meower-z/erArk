# -*- coding: UTF-8 -*-
"""
同名图片取舍规则的回归测试
==========================
image 目录下同一个图片名可能有多个文件（角色主文件夹里一份，草稿或差分子文件夹里一份，或两个分类各一份）。
tk 模式与 web 模式都通过 image_path_index.build_image_path_index 为每个图片名取一个文件：
目录层级浅的优先，层级相同时按 干员、特殊NPC、路人、女儿 的分类顺序，与文件系统的遍历顺序无关；重名的图片名全部列出，供启动时打印提示。
测试在临时目录里摆出这几种重名，不解码图片。
"""
import os
import tempfile
from unittest import mock

from Script.Core import image_path_index
from tests.fast.base import FastTestCase


def touch(root: str, *parts: str) -> str:
    """
    在临时目录里建一个空文件（取舍只看路径，不读内容）
    Keyword arguments:
    root -- 临时目录
    parts -- 相对路径的各段
    Return arguments:
    str -- 建好的文件路径
    """
    path = os.path.join(root, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").close()
    return path


class SameNameImagePickTest(FastTestCase):
    """同名图片按层级与分类顺序取文件，重名全部列出，与遍历顺序无关"""

    def setUp(self):
        """
        在临时目录里摆出三种重名与两张不重名的图片
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.root = root = os.path.join(temp_dir.name, "image")
        # 主文件夹与更深一层的草稿文件夹重名：草稿文件夹「构思」按路径排序在前，层级规则仍要选主文件夹
        self.main_full = touch(root, "立绘", "干员", "莱伊", "莱伊_全身.png")
        self.draft_full = touch(root, "立绘", "干员", "莱伊", "构思", "莱伊_全身.png")
        # 两个分类下同层级的重名：按分类顺序，干员在特殊NPC之前
        self.operator_half = touch(root, "立绘", "干员", "电弧", "电弧_半身.png")
        self.npc_half = touch(root, "立绘", "特殊NPC", "电弧", "电弧_半身.png")
        # 按路径排序时「女儿」排在「路人」之前，分类顺序要选路人
        self.passerby = touch(root, "立绘", "路人", "路人_1.png")
        self.daughter = touch(root, "立绘", "女儿", "路人_1.png")
        # 不重名的图片与不是 png 的文件
        self.single = touch(root, "立绘", "干员", "莱伊", "莱伊_半身.png")
        touch(root, "立绘", "干员", "莱伊", "莱伊_body.json")

    def test_pick_by_depth_then_category(self):
        """主文件夹胜过更深的草稿文件夹；同层级按分类顺序取干员、取路人；不重名的照常收录，只收 png"""
        index, _ = image_path_index.build_image_path_index(self.root)
        self.assertEqual(index.get("莱伊_全身"), self.main_full)
        self.assertEqual(index.get("电弧_半身"), self.operator_half)
        self.assertEqual(index.get("路人_1"), self.passerby)
        self.assertEqual(index.get("莱伊_半身"), self.single)
        self.assertEqual(set(index), {"电弧_半身", "路人_1", "莱伊_全身", "莱伊_半身"})

    def test_duplicates_listed_in_pick_order(self):
        """重名清单只含三个重名的图片名，每个按取舍顺序列出全部文件"""
        _, duplicates = image_path_index.build_image_path_index(self.root)
        self.assertEqual(
            duplicates,
            {
                "莱伊_全身": [self.main_full, self.draft_full],
                "电弧_半身": [self.operator_half, self.npc_half],
                "路人_1": [self.passerby, self.daughter],
            },
        )

    def test_walk_order_does_not_matter(self):
        """文件系统的遍历顺序反过来，取舍结果与重名清单都不变"""
        index, duplicates = image_path_index.build_image_path_index(self.root)
        real_walk = os.walk

        def reversed_walk(directory):
            """
            反序版 os.walk：目录与每个目录里的文件都倒过来
            Keyword arguments:
            directory -- 目录
            Return arguments:
            list -- (目录路径, 子目录名, 文件名) 的列表
            """
            return [(dir_path, dir_names, file_names[::-1]) for dir_path, dir_names, file_names in list(real_walk(directory))[::-1]]

        with mock.patch.object(image_path_index.os, "walk", reversed_walk):
            self.assertEqual(image_path_index.build_image_path_index(self.root), (index, duplicates))
