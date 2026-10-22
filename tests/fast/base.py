# -*- coding: UTF-8 -*-
"""
快速层测试的基类
================
小世界由 tests/fast/__init__.py 载入（每个进程一次）；每个测试方法开始前把它复原并重设随机源。
"""
import unittest

from tests.fast import WORLD


class FastTestCase(unittest.TestCase):
    """快速层测试的基类：self.world 为小世界，self.cache 为游戏缓存，每个测试方法开始时都已复原"""

    world = WORLD
    cache = WORLD.cache

    def setUp(self):
        """
        复原小世界并重设随机源
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.world.reset()
