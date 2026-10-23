# -*- coding: UTF-8 -*-
"""
pytest 不收集本目录的脚本
========================
这里的 test_*.py 在导入时就运行全部断言并结束进程，由 tests/slow/test_education_suite.py 逐个在新进程里运行。
"""

collect_ignore_glob = ["test_*.py"]
""" pytest 不收集的文件 """
