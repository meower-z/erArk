#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BDD 场景（近真实层）LB-BDD-001/002/003：真实实机存档上的群交AI不变量

用真实 Windows 实机存档（槽位99：群交进行中，玩家+10名NPC，npc_ai_type=1
全员自慰）驱动已安装的群交AI相关补丁，逐场景断言：

- LB-BDD-001（upstream core）：普通群交AI跑完或异常退出后玩家的
  交互对象不被污染，且被替代的本地mod已删除；
- LB-BDD-002（local_h_movement_interrupt_fix）：群交H状态下状态机移动入口
  把NPC拉回等待、清空移动计划并标记行为完成；
- LB-BDD-003（local_group_masturbation_intent_fix）：自慰意图（masturebate==3）
  路由到default91且同一玩家行动切片只消费一次，重复调用清理意图并标记完成。

Web层全流程烟雾验证（真实进程里 wait 指令驱动全部10名参与者的群交AI切片）
见 test_bdd_save_full_flow.py。依赖用户实机存档 save/99，缺失时整模块跳过。

运行方式：.venv/bin/pytest mod/tests/bdd/test_bdd_save_group_ai.py -v
"""

import copy
import hashlib
import os
from pathlib import Path

import pytest

from mod.tests.bdd.near_real_boot import boot_game_once

pytestmark = pytest.mark.skipif(
    not os.path.exists(os.path.join("save", "99", "1")),
    reason="需要用户实机存档 save/99（未随仓库分发）",
)


@pytest.fixture(scope="module")
def loaded99():
    """
    模块级夹具：近真实引导并读入槽位99

    返回值类型：BootContext
    功能描述：桩掉Web等待应答（进程内无客户端应答 askfor_wait 轮询），
    经真实 input_load_save 读档；模块内测试共享该会话状态。
    """
    ctx = boot_game_once(enable_debug=True)
    from Script.Core import flow_handle_web, save_handle

    flow_handle_web.get_wait_response = lambda: True
    save_handle.input_load_save("99")
    return ctx


@pytest.mark.parametrize("selector_result", [["overlay_test_status"], [], RuntimeError("selector failed")])
def test_group_ai_preserves_player_target_on_all_selector_exits(loaded99, monkeypatch, selector_result):
    """
    场景（LB-BDD-001）：真实群交状态上跑普通群交AI，玩家交互对象不被污染

    验证点：关闭type-1早退并强制进入需要临时切换target的状态筛选路径，
    分别覆盖非空结果、空结果和异常；每条路径都恢复玩家原交互对象。
    """
    ctx = loaded99
    from Script.Design import handle_npc_ai_in_h, handle_premise
    from Script.System.Sex_System import group_sex_panel

    config_path = Path("mod/mod_config.json")
    assert "local_group_target_context_fix" not in config_path.read_text(encoding="utf-8")
    assert not Path("mod/local_group_target_context_fix").exists()
    player = ctx.cache.character_data[0]
    candidate = ctx.cache.character_data[10]
    old_target = 3
    old_is_h = candidate.sp_flag.is_h
    old_template = copy.deepcopy(player.h_state.group_sex_body_template_dict)
    observed_targets = []

    def select_status(_body_part):
        """参数：_body_part(str)为模板部位；返回：list为状态；用途：记录筛选期间的临时target并驱动三种退出路径。"""
        observed_targets.append(player.target_character_id)
        if isinstance(selector_result, Exception):
            raise selector_result
        return selector_result

    monkeypatch.setattr(handle_premise, "handle_group_sex_mode_off", lambda _character_id: 0)
    monkeypatch.setattr(handle_premise, "handle_self_now_bondage", lambda _character_id: 0)
    monkeypatch.setattr(handle_premise, "handle_npc_ai_type_1_in_group_sex", lambda _character_id: 0)
    monkeypatch.setattr(group_sex_panel, "count_group_sex_character_list", lambda: [])
    monkeypatch.setattr(group_sex_panel, "get_now_template_part_list", lambda: (["overlay_test_part"], []))
    monkeypatch.setattr(group_sex_panel, "get_status_id_list_from_group_sex_body_part", select_status)
    monkeypatch.setattr(handle_npc_ai_in_h.random, "choice", lambda values: values[0])

    try:
        candidate.sp_flag.is_h = True
        player.target_character_id = old_target
        if isinstance(selector_result, Exception):
            with pytest.raises(RuntimeError, match="selector failed"):
                handle_npc_ai_in_h.npc_ai_in_group_sex(10)
        else:
            handle_npc_ai_in_h.npc_ai_in_group_sex(10)
        assert observed_targets == [10], "状态筛选必须在候选NPC上下文中执行"
        assert player.target_character_id == old_target, "群交AI退出后必须恢复玩家交互对象"
    finally:
        player.target_character_id = old_target
        player.h_state.group_sex_body_template_dict = old_template
        candidate.sp_flag.is_h = old_is_h


def test_group_move_entry_converted_to_wait(loaded99):
    """
    场景（LB-BDD-002）：群交H状态下的状态机移动入口被转换为等待

    验证点：对群交中参与者诗怀雅(308)调用真实状态机移动入口
    general_movement_module 返回False（不移动），行为转为WAIT、移动计划
    清空、交互对象指向自身、并加入 over_behavior_character。
    """
    ctx = loaded99
    from Script.StateMachine import default as state_default

    chara = ctx.cache.character_data[308]
    assert chara.sp_flag.is_h and ctx.cache.group_sex_mode
    chara.behavior.move_target = ["中枢", "0"]
    ctx.cache.over_behavior_character.discard(308)

    result = state_default.general_movement_module(308, ["中枢", "0"])

    assert result is False, "群交H状态下移动入口应拒绝移动"
    assert chara.behavior.behavior_id == ctx.constant.Behavior.WAIT
    assert chara.behavior.move_target == [] and chara.behavior.move_final_target == []
    assert chara.target_character_id == 308
    assert 308 in ctx.cache.over_behavior_character


def test_invited_complete_hypnosis_participants_enter_one_five_minute_masturbation_slice(loaded99, monkeypatch):
    """
    场景：单人H后直接邀请的第二名参与者，与原参与者一起执行催眠增强和全员自慰

    验证点：调用真实直接邀请回调并断言其输出，再以场景移动原语确定性跳过逐格旅行，
    由真实加入群交行为完成准入；不驱动邀请列表按钮或逐格旅行UI。群交上下文从恰好
    一名H参与者变为两名，两人进入真实模板并通过真实催眠增强前提、执行与输出边界。
    AI类型1随后经真实角色行为入口生成、消费并结算每人一个五分钟自慰行为，断言
    正式效果、数值输出和窗口终态。场景不写存档并恢复mod与UI全局。
    """
    ctx = loaded99
    from Script.Core import constant, constant_effect
    from Script.Design import game_time, handle_npc_ai, handle_npc_ai_in_h, handle_premise, instuct_judege, map_handle, settle_behavior, talk
    from Script.System.Instruct_System import handle_instruct
    from Script.UI.Moudle import draw
    from Script.System.Sex_System import group_sex_panel

    def file_digest(path):
        """参数：path(Path)为存档路径；返回：str为摘要；用途：证明场景没有改写共享存档。"""
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def panel_text(panel_data):
        """参数：panel_data为富文本面板；返回：str；用途：展开结算面板中的真实文本片段。"""
        if panel_data is None:
            return ""
        text_parts = []
        for draw_group in getattr(panel_data, "draw_list", []):
            draw_items = draw_group if isinstance(draw_group, list) else [draw_group]
            text_parts.extend(getattr(draw_item, "text", "") for draw_item in draw_items)
        return "".join(text_parts)

    save_paths = [Path("save/99/0"), Path("save/99/1")]
    save_digests = {path: file_digest(path) for path in save_paths}
    premise = constant.handle_premise_data["group_sex_extension_complete_hypnosis_ge_2"]
    group_context_func = premise.__globals__["_get_group_sex_character_ids"]
    complete_ids_func = premise.__globals__["_get_complete_hypnosis_character_ids"]
    initial_group_ids = group_context_func()
    player_position = list(ctx.cache.character_data[0].position)
    assistant_id = ctx.cache.character_data[0].assistant_character_id
    eligible_initial_ids = [
        character_id
        for character_id in initial_group_ids
        if character_id != assistant_id
        and ctx.cache.character_data[character_id].position == player_position
        and handle_premise.handle_normal_6(character_id)
    ]
    normal_candidate_ids = [
        character_id
        for character_id in sorted(ctx.cache.npc_id_got)
        if character_id
        and character_id not in initial_group_ids
        and character_id in ctx.cache.character_data
        and not ctx.cache.character_data[character_id].sp_flag.is_h
        and ctx.cache.character_data[character_id].position != ctx.cache.character_data[0].position
        and handle_premise.handle_normal_24567(character_id)
    ]
    first_id = eligible_initial_ids[0] if eligible_initial_ids else None
    assert first_id is not None, "存档99需要一名与玩家同场景、非助理且状态正常的初始H干员"
    invited_id = normal_candidate_ids[0] if normal_candidate_ids else None
    assert invited_id is not None, "存档99需要一名可由真实邀请入口准入的非H干员"

    player_scene_path = map_handle.get_map_system_path_str_for_list(player_position)
    player_scene = ctx.cache.scene_data[player_scene_path]
    invited_old_scene_path = map_handle.get_map_system_path_str_for_list(ctx.cache.character_data[invited_id].position)
    invited_old_scene = ctx.cache.scene_data[invited_old_scene_path]
    affected_ids = set(initial_group_ids) | {0, first_id, invited_id}
    character_snapshots = {character_id: copy.deepcopy(ctx.cache.character_data[character_id]) for character_id in affected_ids}
    original_scene_characters = copy.deepcopy(player_scene.character_list)
    original_invited_scene_characters = copy.deepcopy(invited_old_scene.character_list)
    original_invited_scene_close_flag = invited_old_scene.close_flag
    original_over_behavior = ctx.cache.over_behavior_character
    original_npc_id_got = ctx.cache.npc_id_got
    original_group_sex_mode = ctx.cache.group_sex_mode
    original_game_time = ctx.cache.game_time
    original_pre_game_time = ctx.cache.pre_game_time
    original_achievement = copy.deepcopy(ctx.cache.achievement)
    original_draw_elements = copy.deepcopy(getattr(ctx.cache, "current_draw_elements", []))
    ui_cache_snapshots = {
        cache_name: copy.deepcopy(getattr(ctx.cache, cache_name))
        for cache_name in ("web_instruct_texts", "web_value_changes", "web_draw_history")
        if hasattr(ctx.cache, cache_name)
    }
    intent_globals = handle_npc_ai.find_character_target.__globals__
    intent_global_snapshot = {
        "keys": dict(intent_globals["_GROUP_SEX_MASTURBATION_ACTION_KEYS"]),
        "serial": intent_globals["_GROUP_SEX_MASTURBATION_ACTION_SERIAL"],
        "over_object": intent_globals["_GROUP_SEX_MASTURBATION_OVER_OBJECT"],
        "active": set(intent_globals["_GROUP_SEX_MASTURBATION_ACTIVE_CHARACTERS"]),
        "window_duration": intent_globals["_GROUP_SEX_MASTURBATION_WINDOW_DURATION"],
        "duration_over_object": intent_globals["_GROUP_SEX_MASTURBATION_DURATION_OVER_OBJECT"],
    }
    assert character_snapshots[0].h_state.npc_ai_type_in_group_sex == 1, "存档99的实机群交策略应为类型1全员自慰"

    draw_texts = []
    for draw_class in (draw.NormalDraw, draw.WaitDraw):
        original_draw = draw_class.draw

        def recording_draw(self, *args, __original_draw=original_draw, **kwargs):
            """参数：同真实绘制入口；返回：原返回值；用途：记录真实邀请和批量指令输出。"""
            draw_texts.append(getattr(self, "text", ""))
            return __original_draw(self, *args, **kwargs)

        monkeypatch.setattr(draw_class, "draw", recording_draw)

    try:
        first_data = ctx.cache.character_data[first_id]
        for character_id in initial_group_ids:
            ctx.cache.character_data[character_id].sp_flag.is_h = character_id == first_id
        assert first_data.sp_flag.is_h is True
        assert group_context_func() == [first_id], "真实邀请前群交上下文必须恰好只有一名H参与者"

        invite_panel = group_sex_panel.Edit_Group_Sex_Temple_Panel(80)
        invite_panel.reset_template()
        invite_panel.change_temple()
        invite_panel.reset_template()
        invite_panel.change_temple()
        invite_panel.set_target_chara("A", "侍奉", first_id)

        invited_data = ctx.cache.character_data[invited_id]
        assert "local_group_participant_admission_fix" in invite_panel.invite_npc.__module__
        invite_text_start = len(draw_texts)
        invite_panel.invite_npc(invited_id)
        assert invited_data.sp_flag.go_to_join_group_sex is True
        assert any(f"已邀请{invited_data.name}来这里参加群交" in text for text in draw_texts[invite_text_start:])

        # 邀请回调与输出是真实边界；逐格寻路/UI未驱动，以场景移动原语确定性收束到加入行为。
        map_handle.character_move_scene(list(invited_data.position), player_position, invited_id)
        instuct_judege.init_character_behavior_start_time(invited_id, ctx.cache.game_time)
        constant.handle_state_machine_data[constant.StateMachine.JOIN_GROUP_SEX](invited_id)
        join_end_time = game_time.get_sub_date(minute=invited_data.behavior.duration, old_date=invited_data.behavior.start_time)
        settle_behavior.handle_settle_behavior(invited_id, join_end_time)
        assert invited_data.sp_flag.is_h is True
        assert invited_data.sp_flag.go_to_join_group_sex is False
        invite_panel.set_target_chara("A", "侍奉", invited_id)
        assert sorted(group_sex_panel.count_group_sex_character_list()) == sorted([first_id, invited_id])
        assert group_context_func() == sorted([first_id, invited_id])

        group_context_ids = group_context_func()
        for character_id in group_context_ids:
            character_snapshots.setdefault(character_id, copy.deepcopy(ctx.cache.character_data[character_id]))
            character_data = ctx.cache.character_data[character_id]
            character_data.talent[73] = 0
            character_data.hypnosis.hypnosis_degree = 0
            character_data.hypnosis.increase_body_sensitivity = False
            character_data.hypnosis.pain_as_pleasure = False
        for character_id in (first_id, invited_id):
            ctx.cache.character_data[character_id].hypnosis.hypnosis_degree = 200
        invited_data.sp_flag.unconscious_h = 0

        assert complete_ids_func() == sorted([first_id, invited_id]), "催眠增强资格必须恰好来自原参与者与真实受邀者"
        assert premise(0) == 1
        boost_text_start = len(draw_texts)
        constant.handle_instruct_data["group_sex_extension_hypnosis_boost_all"]()
        for character_id in (first_id, invited_id):
            character_data = ctx.cache.character_data[character_id]
            assert character_data.hypnosis.increase_body_sensitivity
            assert character_data.hypnosis.pain_as_pleasure
        assert invited_data.sp_flag.unconscious_h == 0, "增强不应偷偷切换受邀参与者的催眠态"
        assert any("已为2名完全催眠干员设置敏感度上升与苦痛快感化" in text for text in draw_texts[boost_text_start:])

        player = ctx.cache.character_data[0]
        player.h_state.npc_ai_type_in_group_sex = 0
        invite_panel.change_npc_ai()
        assert player.h_state.npc_ai_type_in_group_sex == 1, "应通过真实群交面板控制切换到全员自慰类型1"
        ctx.cache.npc_id_got = {0, first_id, invited_id}
        settlement_calls = []
        effect_calls = []
        talk_calls = []
        original_handle_settle_behavior = settle_behavior.handle_settle_behavior
        original_masturbation_effect = constant.settle_behavior_effect_data[constant_effect.BehaviorEffect.MASTUREBATE_ADD_ADJUST]
        original_handle_talk = talk.handle_talk
        original_h_judge = handle_npc_ai_in_h.judge_character_h_obscenity_unconscious
        original_find_target = handle_npc_ai.find_character_target
        ai_trace = []

        def recording_settlement(character_id, now_time, event_flag=1):
            """参数：同真实结算入口；返回：原返回值；用途：记录正式行为、时长与数值面板输出。"""
            character_data = ctx.cache.character_data[character_id]
            behavior_id = character_data.behavior.behavior_id
            result = original_handle_settle_behavior(character_id, now_time, event_flag)
            if behavior_id == constant.Behavior.MASTUREBATE:
                settlement_calls.append((character_id, behavior_id, character_data.behavior.duration, int((now_time - character_data.behavior.start_time).total_seconds() / 60), panel_text(result)))
            return result

        def recording_masturbation_effect(character_id, add_time, change_data, now_time):
            """参数：同自慰调整效果；返回：原返回值；用途：证明真实效果在五分钟变化对象上产生数值。"""
            result = original_masturbation_effect(character_id, add_time, change_data, now_time)
            effect_calls.append((character_id, add_time, id(change_data), dict(change_data.status_data), dict(change_data.experience)))
            return result

        def recording_talk(character_id):
            """参数：角色id；返回：原返回值；用途：证明正式自慰结算进入真实口上输出边界。"""
            behavior_id = ctx.cache.character_data[character_id].behavior.behavior_id
            if behavior_id == constant.Behavior.MASTUREBATE:
                talk_calls.append((character_id, behavior_id))
            return original_handle_talk(character_id)

        def recording_h_judge(character_id, pl_start_time):
            """参数：同真实H状态入口；返回：原返回值；用途：记录两名参与者进入群交AI前后的状态。"""
            if character_id in (first_id, invited_id):
                character_data = ctx.cache.character_data[character_id]
                ai_trace.append(("h-before", character_id, character_data.behavior.behavior_id, character_data.sp_flag.masturebate, handle_premise.handle_normal_6(character_id), character_id in ctx.cache.over_behavior_character))
            result = original_h_judge(character_id, pl_start_time)
            if character_id in (first_id, invited_id):
                character_data = ctx.cache.character_data[character_id]
                ai_trace.append(("h-after", character_id, character_data.behavior.behavior_id, character_data.sp_flag.masturebate, handle_premise.handle_normal_6(character_id), character_id in ctx.cache.over_behavior_character))
            return result

        def recording_find_target(character_id, now_time):
            """参数：同真实目标查找入口；返回：原返回值；用途：记录群交自慰意图的正式消费边界。"""
            if character_id in (first_id, invited_id):
                character_data = ctx.cache.character_data[character_id]
                ai_trace.append(("find-before", character_id, character_data.behavior.behavior_id, character_data.sp_flag.masturebate, handle_premise.handle_normal_6(character_id), character_id in ctx.cache.over_behavior_character))
            result = original_find_target(character_id, now_time)
            if character_id in (first_id, invited_id):
                character_data = ctx.cache.character_data[character_id]
                ai_trace.append(("find-after", character_id, character_data.behavior.behavior_id, character_data.sp_flag.masturebate, handle_premise.handle_normal_6(character_id), character_id in ctx.cache.over_behavior_character))
            return result

        settle_behavior.handle_settle_behavior = recording_settlement
        constant.settle_behavior_effect_data[constant_effect.BehaviorEffect.MASTUREBATE_ADD_ADJUST] = recording_masturbation_effect
        talk.handle_talk = recording_talk
        handle_npc_ai_in_h.judge_character_h_obscenity_unconscious = recording_h_judge
        handle_npc_ai.find_character_target = recording_find_target
        try:
            for character_id in (first_id, invited_id):
                character_data = ctx.cache.character_data[character_id]
                character_data.dead = False
                character_data.hit_point = max(character_data.hit_point, 2)
                character_data.tired_point = 0
                character_data.sp_flag.tired = False
                character_data.sp_flag.is_h = True
                character_data.sp_flag.is_follow = False
                character_data.sp_flag.unconscious_h = 0
                character_data.sp_flag.masturebate = 0
                character_data.h_state.bondage = 0
                character_data.h_state.orgasm_edge = 0
                character_data.h_state.time_stop_release = False
                character_data.target_character_id = character_id
                character_data.behavior.behavior_id = constant.Behavior.SHARE_BLANKLY
                instuct_judege.init_character_behavior_start_time(character_id, ctx.cache.game_time)
                handle_premise.settle_chara_unnormal_flag(character_id, 0)
            handle_instruct.handle_wait_5_min_in_h()
        finally:
            settle_behavior.handle_settle_behavior = original_handle_settle_behavior
            constant.settle_behavior_effect_data[constant_effect.BehaviorEffect.MASTUREBATE_ADD_ADJUST] = original_masturbation_effect
            talk.handle_talk = original_handle_talk
            handle_npc_ai_in_h.judge_character_h_obscenity_unconscious = original_h_judge
            handle_npc_ai.find_character_target = original_find_target

        settled_ids = [call[0] for call in settlement_calls]
        assert sorted(settled_ids) == sorted([first_id, invited_id]), ai_trace
        assert all(call[1:4] == (constant.Behavior.MASTUREBATE, 5, 5) for call in settlement_calls)
        assert all(ctx.cache.character_data[call[0]].name in call[4] and "5分钟过去了" in call[4] for call in settlement_calls)
        assert [call[0] for call in effect_calls] == settled_ids
        assert all(call[1] == 5 for call in effect_calls)
        assert all(status_data and experience_data for _character_id, _add_time, _change_id, status_data, experience_data in effect_calls)
        assert talk_calls == [(character_id, constant.Behavior.MASTUREBATE) for character_id in settled_ids]
        for character_id in (first_id, invited_id):
            character_trace = [entry[0] for entry in ai_trace if entry[1] == character_id]
            assert character_trace == ["h-before", "h-after", "find-before", "find-after"]
        assert int((ctx.cache.game_time - original_game_time).total_seconds() / 60) == 5
        current_action_key = intent_globals["_GROUP_SEX_MASTURBATION_ACTION_SERIAL"]
        assert intent_globals["_GROUP_SEX_MASTURBATION_ACTION_KEYS"] == {first_id: current_action_key, invited_id: current_action_key}
        assert intent_globals["_GROUP_SEX_MASTURBATION_ACTIVE_CHARACTERS"] == intent_global_snapshot["active"] | {first_id, invited_id}
        for character_id in (first_id, invited_id):
            character_data = ctx.cache.character_data[character_id]
            assert character_data.sp_flag.is_h is True
            assert character_data.hypnosis.increase_body_sensitivity is True
            assert character_data.hypnosis.pain_as_pleasure is True
            assert character_data.sp_flag.masturebate == 0
            assert character_data.behavior.behavior_id == constant.Behavior.SHARE_BLANKLY
            assert character_data.state == constant.CharacterStatus.STATUS_ARDER
            assert character_id in ctx.cache.over_behavior_character
        assert group_context_func() == sorted([first_id, invited_id])
        assert sorted(group_sex_panel.count_group_sex_character_list()) == sorted([first_id, invited_id])
    finally:
        for character_id, snapshot in character_snapshots.items():
            ctx.cache.character_data[character_id] = snapshot
        player_scene.character_list = original_scene_characters
        invited_old_scene.character_list = original_invited_scene_characters
        invited_old_scene.close_flag = original_invited_scene_close_flag
        ctx.cache.over_behavior_character = original_over_behavior
        ctx.cache.npc_id_got = original_npc_id_got
        ctx.cache.group_sex_mode = original_group_sex_mode
        ctx.cache.game_time = original_game_time
        ctx.cache.pre_game_time = original_pre_game_time
        ctx.cache.achievement = original_achievement
        ctx.cache.current_draw_elements = original_draw_elements
        for cache_name, snapshot in ui_cache_snapshots.items():
            setattr(ctx.cache, cache_name, snapshot)
        intent_globals["_GROUP_SEX_MASTURBATION_ACTION_KEYS"].clear()
        intent_globals["_GROUP_SEX_MASTURBATION_ACTION_KEYS"].update(intent_global_snapshot["keys"])
        intent_globals["_GROUP_SEX_MASTURBATION_ACTION_SERIAL"] = intent_global_snapshot["serial"]
        intent_globals["_GROUP_SEX_MASTURBATION_OVER_OBJECT"] = intent_global_snapshot["over_object"]
        intent_globals["_GROUP_SEX_MASTURBATION_ACTIVE_CHARACTERS"].clear()
        intent_globals["_GROUP_SEX_MASTURBATION_ACTIVE_CHARACTERS"].update(intent_global_snapshot["active"])
        intent_globals["_GROUP_SEX_MASTURBATION_WINDOW_DURATION"] = intent_global_snapshot["window_duration"]
        intent_globals["_GROUP_SEX_MASTURBATION_DURATION_OVER_OBJECT"] = intent_global_snapshot["duration_over_object"]

    assert {path: file_digest(path) for path in save_paths} == save_digests
