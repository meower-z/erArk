# -*- coding: UTF-8 -*-
"""BDD 强制退出状态码回归。"""

from types import SimpleNamespace

from mod.tests.bdd import conftest as bdd_conftest


def test_forced_thread_shutdown_preserves_pytest_failure_status(monkeypatch):
    """参数：monkeypatch为pytest夹具；返回：None；用途：验证非守护线程强退不会把失败伪装成成功。"""
    exit_codes = []
    monkeypatch.setattr(bdd_conftest.threading, "enumerate", lambda: [SimpleNamespace(name="init_instruct_handle_thread")])
    monkeypatch.setattr(bdd_conftest.os, "_exit", lambda exit_code: exit_codes.append(exit_code))

    bdd_conftest.pytest_sessionfinish(None, 3)
    bdd_conftest.pytest_unconfigure(None)

    assert exit_codes == [3]
