# -*- coding: UTF-8 -*-
"""
快速层测试的基类
================
小世界由 tests/fast/__init__.py 载入（每个进程一次）；每个测试方法开始前把它复原并重设随机源。
"""

import unittest

from Script.Modules.domains import warehouse
from tests import kernel_data
from tests.fast import WORLD


class FastTestCase(unittest.TestCase):
    """快速层测试的基类：self.world 为小世界，每个测试方法开始时都已复原"""

    world = WORLD

    def setUp(self) -> None:
        """
        复原小世界并重设随机源。内核换成没有角色的开局时钟，同读档一样由各插件的 Reset 钩子清掉自己的状态。
        复原后的 GameState 里没有 base.stock，所以再用 warehouse.start 给每种配置资源记下库存 0
        Keyword arguments:
        无
        Return arguments:
        无
        """
        self.world.reset()
        kernel_data.written(warehouse.start, {})
