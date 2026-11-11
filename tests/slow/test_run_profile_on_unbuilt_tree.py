# -*- coding: UTF-8 -*-
"""
在还没构建过数据的仓库目录里运行性能分析脚本 run_profile
========================================================
新克隆的仓库里还没有 data/ 下由构建写出的文件（下称生成物）。
测试在临时目录里用符号链接搭出这样的仓库目录。
子进程在其中运行 python -m profiling.run_profile --ticks 1。
测试要求子进程以退出码 0 结束，并要求 data/data.json 已写出。
本测试用不到 SlowTestCase.setUp 在测试进程里启动的游戏。
"""

import os
import subprocess
import sys
import tempfile

from tests.slow.base import SlowTestCase
from tests.world import ROOT

CHILD_TIME_LIMIT = 240
""" 等待子进程结束的时限，单位为秒 """

UNLINKED_TOP = ("data", "profiling_output")
""" 仓库根目录下不链接的条目：data 另行搭建，profiling_output 由脚本自己新建 """


def link_unbuilt_tree(temp_dir: str) -> None:
    """
    在空的 temp_dir 里搭出没有生成物的仓库目录
    生成物是 data/ 下直接放的文件和 data/po/zh_CN，所以只链接三类条目：
    仓库根目录下 UNLINKED_TOP 以外的条目、data/ 下 po 以外的子目录、
    data/po/ 下 zh_CN 以外的条目
    data/ 与 data/po/ 是本函数新建的目录，不是链接
    Keyword arguments:
    temp_dir -- 空的临时目录
    Return arguments:
    无
    """
    for name in os.listdir(ROOT):
        if name not in UNLINKED_TOP:
            os.symlink(os.path.join(ROOT, name), os.path.join(temp_dir, name))
    os.makedirs(os.path.join(temp_dir, "data", "po"))
    data_dir = os.path.join(ROOT, "data")
    for name in os.listdir(data_dir):
        if name != "po" and os.path.isdir(os.path.join(data_dir, name)):
            os.symlink(
                os.path.join(data_dir, name),
                os.path.join(temp_dir, "data", name),
            )
    po_dir = os.path.join(data_dir, "po")
    for name in os.listdir(po_dir):
        if name != "zh_CN":
            os.symlink(
                os.path.join(po_dir, name),
                os.path.join(temp_dir, "data", "po", name),
            )


class RunProfileOnUnbuiltTreeTest(SlowTestCase):
    """在没有生成物的仓库目录里运行 run_profile"""

    def test_run_profile_completes(self) -> None:
        """脚本以退出码 0 结束，并写出 data/data.json"""
        with tempfile.TemporaryDirectory() as temp_dir:
            link_unbuilt_tree(temp_dir)
            result = subprocess.run(
                [
                    sys.executable,
                    "-u",
                    "-m",
                    "profiling.run_profile",
                    "--ticks",
                    "1",
                ],
                cwd=temp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                timeout=CHILD_TIME_LIMIT,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout[-3000:])
            self.assertTrue(
                os.path.isfile(os.path.join(temp_dir, "data", "data.json"))
            )
