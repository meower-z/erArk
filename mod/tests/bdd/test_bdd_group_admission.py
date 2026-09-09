#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BDD 场景（近真实层）LB-BDD-004 扩展：群交发起前提的参与准入

通过真实 ModManager 加载全部 mod 后，在真实前提注册表
（constant.handle_premise_data["place_all_not_tired"]，群交发起指令
ASK_GROUP_SEX 的疲劳门禁）与真实地图/场景数据上验证：
- core `handle_scene_all_not_tired` 已检查全部 NPC，mod 在其结果上补充群交规则；
- 体力耗尽（hit_point<=1）同样被拦截；
- 全员健康时前提通过。

运行方式：.venv/bin/pytest mod/tests/bdd/test_bdd_group_admission.py -v
"""

import pytest

from mod.tests.bdd.near_real_boot import boot_game_once
from mod.tests.bdd.test_bdd_pain_as_pleasure import _make_character

PREMISE_ID = "place_all_not_tired"


@pytest.fixture(scope="session")
def booted():
    """会话级近真实引导夹具；返回值类型：BootContext。"""
    return boot_game_once(enable_debug=True)


def _setup_scene_with_characters(booted, npc_ids):
    """
    在真实地图数据中选一个场景并放入玩家与NPC

    参数:
    booted (BootContext): 引导上下文
    npc_ids (list): NPC id 列表

    返回值类型：str，场景路径字符串
    功能描述：将玩家(0)与全部 NPC 的 position 指向同一真实场景，并把 id
    写入该场景的 character_list，使 map_handle 的场景角色查询返回它们。
    """
    booted.cache.character_data.clear()
    scene_path_str = next(iter(booted.cache.scene_data))
    scene_data = booted.cache.scene_data[scene_path_str]
    position = scene_path_str.split(" ")
    ids = [0] + list(npc_ids)
    for cid in ids:
        chara = _make_character(booted, cid, target_id=0)
        chara.position = position
    scene_data.character_list = set(ids)
    return scene_path_str


def _premise(booted):
    """参数：booted(BootContext)为引导上下文；返回：callable为已注册的前提函数；用途：从真实前提注册表取群交发起门禁。"""
    return booted.constant.handle_premise_data[PREMISE_ID]


def test_premise_registry_holds_mod_function(booted):
    """
    场景：真实前提注册表中的群交发起门禁已被本组件替换

    验证点：注册表项来自 local_group_participant_admission_fix 且保留原函数引用。
    """
    func = _premise(booted)
    assert "local_group_participant_admission_fix" in func.__module__
    assert getattr(func, "_local_group_participant_admission_original", None) is not None


def test_second_tired_npc_is_blocked_by_core_before_mod_extensions(booted):
    """
    场景：场景内第二个NPC疲劳时群交发起前提不通过

    验证点：替换后的前提与捕获的core原函数都返回0，证明mod不再复制
    全场景遍历修复，而是在core结果上补充规则。
    """
    _setup_scene_with_characters(booted, [1, 2])
    booted.cache.character_data[2].sp_flag.tired = 1

    patched = _premise(booted)
    upstream = patched._local_group_participant_admission_original

    assert patched(0) == 0, "第二个NPC疲劳时应拦截群交发起"
    assert upstream(0) == 0, "core前提应检查后续NPC，mod不得遮蔽core修复"


def test_hp_depleted_npc_blocks_group_start(booted):
    """
    场景：体力耗尽的NPC使群交发起前提不通过

    验证点：hit_point<=1 的角色按组件统一判据被拦截（上游仅查 sp_flag.tired）。
    """
    _setup_scene_with_characters(booted, [1, 2])
    booted.cache.character_data[1].hit_point = 1

    assert _premise(booted)(0) == 0


def test_all_healthy_scene_allows_group_start(booted):
    """
    场景：全员健康时群交发起前提通过

    验证点：替换后的前提对健康场景返回1，不改变正常游玩。
    """
    _setup_scene_with_characters(booted, [1, 2])
    for cid in (1, 2):
        booted.cache.character_data[cid].hit_point = 100

    assert _premise(booted)(0) == 1
