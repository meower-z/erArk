# -*- coding: UTF-8 -*-
"""
慢速层的 pytest 设置
====================
有 os.fork 的系统上必须加 --forked，否则报用法错误：同一进程跑多个测试会共用一局游戏。
没有 os.fork 的系统（Windows）上整层跳过，并关掉 --forked（pytest-forked 在那里会因没有 fork 而出错）。
有 os.fork 而没给 --durations 时，列出每个测试各阶段的用时。
"""

import os

import pytest

HAS_FORK = hasattr(os, "fork")
""" 本系统有没有 os.fork """


def pytest_configure(config: pytest.Config) -> None:
  """
  检查 --forked，设定用时列表
  Keyword arguments:
  config -- pytest 配置对象
  Return arguments:
  无
  """
  if not HAS_FORK:
    config.option.forked = False
    return
  if not config.option.forked:
    raise pytest.UsageError(
        "慢速层每个测试要一个新进程：pytest tests/slow --forked"
    )
  if config.option.durations is None:
    config.option.durations = 0
    config.option.durations_min = 0.0


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
  """
  没有 os.fork 时把慢速层的测试全部标为跳过
  Keyword arguments:
  config -- pytest 配置对象
  items -- 收集到的测试
  Return arguments:
  无
  """
  if HAS_FORK:
    return
  skip = pytest.mark.skip(
      reason="慢速层靠 os.fork 让每个测试一个新进程，本系统没有 os.fork（Windows），整层跳过"
  )
  for item in items:
    item.add_marker(skip)
