#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BDD 场景（近真实层）：进程内通过真实 ModManager 全量加载后的补丁安装校验

对应 design.md 的 near-real-game harness 定义：通过真实 Script.Core.mod_manager
对未 mock 的 Script 模块与真实配置数据完成加载，随后在真实缓存/结算入口上验证不变量。
本文件先校验"补丁确已安装到真实 Script 函数"，作为其余近真实场景的地基。

运行方式（仓库根目录）：.venv/bin/pytest mod/tests/bdd/test_bdd_near_real_boot.py -v
"""

from collections import defaultdict
from types import SimpleNamespace

import pytest

from mod.tests.bdd.near_real_boot import boot_game_once


@pytest.fixture(scope="session")
def booted():
    """
    会话级近真实引导夹具

    返回值类型：BootContext
    """
    return boot_game_once(enable_debug=True)


def test_mods_loaded_without_errors(booted):
    """
    场景：真实加载器加载全部启用 mod 且无错误

    验证点：init_mod_system() 返回 True（errors 为空）。
    """
    assert booted.mod_success is True


def test_orgasm_settlement_edge_patch_installed_on_real_module(booted):
    """
    场景：当前高潮结算共同寸止测试组件已安装到真实 second_behavior 模块

    验证点：只替换 orgasm_settle；旧批处理的 check_second_effect 与状态钩子不再加载。
    """
    import Script.Design.second_behavior as sb

    assert "local_orgasm_settle_edge_fix" in sb.orgasm_settle.__module__
    assert sb.check_second_effect.__module__ == "Script.Design.second_behavior"
    assert not hasattr(sb, "local_h_orgasm_batch_fix_is_settling")
    assert not hasattr(sb, "local_bugfix_is_orgasm_batch_settling")


@pytest.mark.parametrize("shared_decision", [True, False])
def test_real_orgasm_judge_uses_one_shared_decision_without_replay(booted, monkeypatch, shared_decision):
    """参数：真实引导、monkeypatch、共同判定结果(bool)；返回：None；用途：验证真实核心入口只判定并推进高潮等级一次。"""
    from Script.Design import attr_calculation, handle_premise, second_behavior

    cache = booted.cache
    character_id = 1000
    player = SimpleNamespace(ability=defaultdict(int))
    target = SimpleNamespace(
        ability=defaultdict(lambda: 10),
        talent=defaultdict(int),
        status_data=defaultdict(int, {4: 1}),
        second_behavior={},
        must_settle_second_behavior_id_list=[],
        must_show_second_behavior_id_list=[],
        h_state=SimpleNamespace(
            orgasm_edge=1,
            orgasm_edge_count={4: 2},
            orgasm_level=defaultdict(int),
            time_stop_orgasm_count={},
            time_stop_release=False,
            shoot_position_body=-1,
            extra_orgasm_feel={},
            extra_orgasm_count=0,
        ),
    )
    monkeypatch.setitem(cache.character_data, 0, player)
    monkeypatch.setitem(cache.character_data, character_id, target)
    monkeypatch.setattr(attr_calculation, "get_status_level", lambda value: value)
    monkeypatch.setattr(handle_premise, "handle_unconscious_flag_3", lambda _character_id: False)
    monkeypatch.setattr(handle_premise, "handle_self_orgasm_edge", lambda now_character_id: cache.character_data[now_character_id].h_state.orgasm_edge == 1)
    monkeypatch.setattr(handle_premise, "handle_group_sex_mode_on", lambda _character_id: False)
    monkeypatch.setattr(handle_premise, "handle_hidden_sex_mode_ge_1", lambda _character_id: False)
    monkeypatch.setattr(handle_premise, "handle_exhibitionism_sex_mode_ge_1", lambda _character_id: False)
    monkeypatch.setattr(handle_premise, "handle_unconscious_flag_1", lambda _character_id: False)
    monkeypatch.setattr(handle_premise, "handle_self_orgasm_edge_relase_or_time_stop_orgasm_relase", lambda now_character_id: cache.character_data[now_character_id].h_state.orgasm_edge == 2)
    monkeypatch.setattr(handle_premise, "handle_milk_ge_80", lambda _character_id: False)
    monkeypatch.setattr(handle_premise, "handle_urinate_ge_80", lambda _character_id: False)
    monkeypatch.setattr(handle_premise, "handle_in_human_power_room", lambda _character_id: False)
    monkeypatch.setattr(second_behavior, "judge_orgasm_degree", lambda _level: 0)
    snapshots = []

    def record_shared_decision(now_character_id):
        """参数：now_character_id(int)；返回：bool；用途：记录真实mod交给判定函数的完整快照。"""
        snapshots.append(dict(cache.character_data[now_character_id].h_state.orgasm_edge_count))
        return shared_decision

    monkeypatch.setattr(second_behavior, "judge_orgasm_edge_success", record_shared_decision)
    change_data = SimpleNamespace(status_data=defaultdict(int, {4: 1}), target_change={})
    second_behavior.orgasm_judge(character_id, change_data)

    assert snapshots == [{4: 3}]
    assert target.h_state.orgasm_level[4] == 1
    if shared_decision:
        assert target.h_state.orgasm_edge == 1
        assert target.h_state.orgasm_edge_count == {4: 3}
        assert target.second_behavior["v_orgasm_edge"] == 1
    else:
        assert target.h_state.orgasm_edge == 2
        assert target.h_state.orgasm_edge_count == {}
        assert target.second_behavior["v_orgasm_small"] == 1


def test_group_target_is_core_owned_and_move_patches_are_installed(booted):
    """
    场景：群交目标上下文由core负责，H移动中断修复仍由mod负责

    验证点：npc_ai_in_group_sex及无调用点的type-3保留core实现；
    own_charcter_move / npc_active_h仍来自H移动中断修复。
    """
    import Script.Design.handle_npc_ai_in_h as ai_h
    import Script.Design.character_move as move

    assert ai_h.npc_ai_in_group_sex.__module__ == "Script.Design.handle_npc_ai_in_h"
    assert ai_h.npc_ai_in_group_sex_type_3.__module__ == "Script.Design.handle_npc_ai_in_h"
    assert "local_h_movement_interrupt_fix" in move.own_charcter_move.__module__
    assert "local_h_movement_interrupt_fix" in ai_h.npc_active_h.__module__
