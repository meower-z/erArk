# -*- coding: UTF-8 -*-
"""Web BDD 驱动端口发现测试。"""

from mod.tests.bdd.web_game_driver import _extract_port_from_line


def test_port_detection_accepts_chinese_free_port_log():
    """参数：无；返回：None；用途：验证中文可用端口日志可被识别。"""
    assert _extract_port_from_line("已找到可用端口: 5001") == 5001


def test_port_detection_accepts_flask_ascii_url_log():
    """参数：无；返回：None；用途：验证 Werkzeug 的 ASCII URL 日志可兜底识别。"""
    assert _extract_port_from_line(" * Running on http://127.0.0.1:5011") == 5011
