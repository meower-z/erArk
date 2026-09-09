#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BDD 场景（基础层）：真实游戏进程的启动、mod 加载与主循环冒烟

对应 openspec/changes/modularize-local-bugfixes-and-audit-local-mods/bdd-scenarios.md：
- LB-BDD-010 的端到端补充：全部启用 mod 通过真实 ModManager 加载（此前仅有合成 mod 的加载器测试）。
- 主循环冒烟：开新档进入主场景后执行真实指令并完成行为结算，全程 error.log 无新增。

运行方式（仓库根目录）：.venv/bin/pytest mod/tests/bdd/ -v
"""

import json
import re
import time
from pathlib import Path


def _enabled_mod_names() -> list[str]:
    """参数：无；返回：list[str]为当前启用mod显示名；用途：从唯一配置源生成启动日志期望。"""
    repo_root = Path(__file__).resolve().parents[3]
    enabled_mods = json.loads((repo_root / "mod" / "mod_config.json").read_text(encoding="utf-8"))["enabled_mods"]
    manifests = {
        manifest["mod_id"]: manifest["name"]
        for manifest_path in (repo_root / "mod").glob("*/mod_info.json")
        for manifest in [json.loads(manifest_path.read_text(encoding="utf-8"))]
    }
    return [manifests[mod_id] for mod_id in enabled_mods]


def test_all_enabled_mods_load_in_real_game(game_driver):
    """
    场景：真实游戏进程内全部启用 mod 成功加载（LB-BDD-010 端到端补充）

    验证点：启动日志包含当前配置中每个启用 mod 的"[Mod] 成功加载"，无"加载失败"。
    """
    boot_log = "\n".join(game_driver.stdout_lines)
    for name in _enabled_mod_names():
        assert f"成功加载: {name}" in boot_log, f"mod 未成功加载: {name}"
    assert "加载失败" not in boot_log


def test_new_game_reaches_main_scene(game_driver, main_scene):
    """
    场景：开新档走完创建流程进入主场景

    验证点：场景信息栏含时间与位置；玩家信息为创建的角色；error.log 无新增。
    """
    bar = main_scene.get("scene_info_bar") or {}
    assert "当前位置" in (bar.get("scene_name") or "")
    assert re.search(r"\d+年", bar.get("game_time") or "")
    player = main_scene.get("player_info") or {}
    assert player.get("name") == "Doctor"
    assert game_driver.new_error_log_text() == ""


def test_instruct_settlement_advances_game_time(game_driver, main_scene):
    """
    场景：执行真实指令（休息）触发行为结算主循环

    验证点：SocketIO execute_instruct 路径走 handle_instruct ->
    update.game_update_flow -> character_behavior.init_character_behavior，
    结算后游戏时间前进；error.log 无新增。
    """
    before_bar = (game_driver.in_scene_state() or {}).get("scene_info_bar") or {}
    before_time = before_bar.get("game_time") or ""
    game_driver.execute_instruct("rest")
    # 结算期间可能出现等待元素/结算弹窗，自动推进
    deadline = time.time() + 60
    after_time = before_time
    while time.time() < deadline:
        game_driver.auto_advance(rounds=5)
        scene = game_driver.in_scene_state()
        if scene is not None:
            after_time = (scene.get("scene_info_bar") or {}).get("game_time") or ""
            if after_time != before_time:
                break
        time.sleep(0.5)
    assert after_time != before_time, f"游戏时间未前进: {before_time!r} -> {after_time!r}"
    assert game_driver.new_error_log_text() == ""
