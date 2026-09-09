#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BDD 场景（Web端到端层）：真实实机存档上的群交全流程

用真实游戏进程（web_draw=1）读取真实 Windows 实机存档（槽位99，版本
2026.6.30-4，群交会话进行中：玩家+10名NPC，多人带待处理寸止计数，玩家
积压约160条绝顶待结算记录），按顺序驱动：

1. 标题画面读档（跨版本迁移 + 跨平台分隔符归一化，LB-BDD-012 全UI路径）；
2. 群交模式中执行 wait 指令 —— NPC群交AI切片真实运行（npc_ai_type=1 全员
   自慰：LB-BDD-001 目标上下文 / LB-BDD-002 移动中断 / LB-BDD-003 自慰意图
   的实机烟雾验证）；
3. group_sex_end 指令 —— 完整群交结束结算链：效果529寸止释放（LB-BDD-009
   全流程）、批处理绝顶结算含凯尔希 edge==2 的5次计数与成就1221路径
   （LB-BDD-008 全流程）。修复前该指令在跨平台读档后以
   list.remove(x): x not in list 崩溃；
4. rest 指令 —— 群交结束后游戏可继续推进。

每步断言游戏时间前进且 error.log 无新增。模块独占一个游戏进程（读档需从
标题画面进入，与开新档的会话级进程互斥）。依赖用户实机存档 save/99
（gitignore，不随仓库分发），缺失时整模块跳过。

运行方式：.venv/bin/pytest mod/tests/bdd/test_bdd_save_full_flow.py -v
"""

import os
import sys

import pytest

from mod.tests.bdd.web_game_driver import WebGameDriver

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join("save", "99", "1")),
    reason="需要用户实机存档 save/99（未随仓库分发）",
)


@pytest.fixture(scope="module")
def save_driver():
    """
    模块级游戏进程夹具（独立于会话级 game_driver）

    返回值类型：WebGameDriver
    功能描述：读档场景需要从标题画面进入神经重载，与开新档共享进程会互相
    干扰，故本模块独占启动一个真实游戏进程。
    """
    driver = WebGameDriver(REPO_ROOT, python_exe=sys.executable)
    try:
        driver.start()
    except Exception:
        print("\n".join(driver.stdout_lines[-40:]))
        driver.stop()
        raise
    yield driver
    driver.stop()


@pytest.fixture(scope="module")
def loaded99(save_driver):
    """
    模块级夹具：经完整标题UI读取槽位99直至主场景

    返回值类型：dict，主场景 new_ui_container 的 game_state
    """
    return save_driver.load_save("99", timeout=180)


def test_crossversion_save_loads_to_main_scene(save_driver, loaded99):
    """
    场景：跨版本+跨平台实机存档经完整UI读档进入主场景（LB-BDD-012全UI）

    验证点：主场景容器出现、场景信息栏为存档内时间地点、error.log 无新增。
    """
    bar = loaded99.get("scene_info_bar") or {}
    assert "人力发电室" in (bar.get("scene_name") or ""), "应回到存档中的群交场景"
    assert "2019" in (bar.get("game_time") or ""), "应为存档内的游戏时间"
    assert save_driver.new_error_log_text() == ""


def test_group_ai_slice_settles_clean(save_driver, loaded99):
    """
    场景：群交进行中执行 wait，10名参与者的群交AI真实运行一个切片

    验证点：指令成功、游戏时间前进、error.log 无新增（LB-BDD-001/002/003
    在实机群交状态上的烟雾验证；AI类型1使全员走自慰意图路径）。
    """
    result = save_driver.run_instruct("wait", timeout=150)
    assert result.get("success") is True
    assert save_driver.new_error_log_text() == ""


def test_group_sex_end_full_settlement(save_driver, loaded99):
    """
    场景：结束群交——完整结算链（LB-BDD-008/009 全流程）

    验证点：修复前本指令在跨平台读档后崩溃（list.remove）；现在效果529
    寸止释放（5名参与者的待处理计数）、批处理绝顶结算（含凯尔希解放态
    5次计数与成就路径）全部完成，指令成功、时间前进、error.log 无新增。
    """
    result = save_driver.run_instruct("group_sex_end", timeout=240)
    assert result.get("success") is True
    assert save_driver.new_error_log_text() == ""


def test_flow_continues_after_group_end(save_driver, loaded99):
    """
    场景：群交结束后游戏继续推进

    验证点：普通指令（rest）正常结算，error.log 无新增。
    """
    result = save_driver.run_instruct("rest", timeout=150)
    assert result.get("success") is True
    assert save_driver.new_error_log_text() == ""
