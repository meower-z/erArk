#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BDD 场景（近真实层）：真实实机存档上的寸止窗口合并

用真实 Windows 实机存档（槽位99：群交进行中）驱动一次玩家等待指令，
复刻 debug_edge_loop.py 的陈(10)阈值布置，断言同一玩家行动窗口内每名
角色在窗口内不进行寸止成功/失败掷骰，窗口末尾每名待判角色至多掷骰一次，
且掷骰时每个跨级部位的计数都已经进入待释放寸止计数。

依赖用户实机存档 save/99（gitignore，不随仓库分发），缺失时整模块跳过。

运行方式：.venv/bin/python -m pytest mod/tests/bdd/test_bdd_save_edge_window_merge.py -v
"""

import os
import random
import hashlib
import traceback
import json
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from mod.tests.bdd.near_real_boot import boot_game_once

_mod_config = json.loads(Path("mod/mod_config.json").read_text(encoding="utf-8"))
pytestmark = [
    pytest.mark.skipif(not os.path.exists(os.path.join("save", "99", "1")), reason="需要用户实机存档 save/99（未随仓库分发）"),
    pytest.mark.skipif("local_h_orgasm_batch_fix" not in _mod_config["enabled_mods"], reason="旧玩家操作窗口合并组件当前已禁用"),
]

CHEN_ID = 10


@pytest.fixture()
def loaded99():
    """
    参数：无；返回值类型：BootContext；用途：近真实引导并重新读入槽位99。
    """
    ctx = boot_game_once(enable_debug=True)
    from Script.Core import flow_handle_web, save_handle

    flow_handle_web.get_wait_response = lambda: True
    save_handle.input_load_save("99")
    return ctx


def _place_chen_thresholds(ctx):
    """
    参数：ctx(BootContext)为引导上下文；返回值类型：None；
    用途：复刻诊断脚本，把陈的阴道和心理快感放到跨级门槛下。
    """
    chen = ctx.cache.character_data[CHEN_ID]
    chen.status_data[23] = 990
    chen.h_state.orgasm_level[23] = 2
    chen.status_data[4] = 990
    chen.h_state.orgasm_level[4] = 2
    chen.ability[34] = 8


def _edge_count_snapshot(ctx, character_id):
    """
    参数：ctx(BootContext)为引导上下文，character_id(int)为角色id；
    返回值类型：dict；用途：复制非零寸止待释放计数。
    """
    return {
        part: count
        for part, count in ctx.cache.character_data[character_id].h_state.orgasm_edge_count.items()
        if count
    }


def _orgasm_count_snapshot(ctx, character_id):
    """
    参数：ctx(BootContext)为引导上下文，character_id(int)为角色id；
    返回值类型：dict；用途：复制部位绝顶次数统计。
    """
    return {
        part: counts[0]
        for part, counts in ctx.cache.character_data[character_id].h_state.orgasm_count.items()
        if counts
    }


def _count_chen_edge_crossings(ctx, monkeypatch):
    """
    参数：ctx(BootContext)为引导上下文，monkeypatch为pytest夹具；
    返回值类型：defaultdict[int, int]；用途：按真实 orgasm_settle 入参统计
    陈在寸止状态下每个跨级部位应合并的 climax_count。
    """
    from Script.Design import handle_premise, second_behavior
    from mod.local_h_orgasm_batch_fix.scripts.h_orgasm_batch import ORGASM_PART_PREFIX

    crossed_parts = defaultdict(int)
    original_orgasm_settle = second_behavior.orgasm_settle

    def wrapped_orgasm_settle(character_id, change_data, normal_orgasm_dict=None, extra_orgasm_dict=None, un_count_orgasm_dict=None):
        normal_orgasm_dict = normal_orgasm_dict or {}
        extra_orgasm_dict = extra_orgasm_dict or {}
        un_count_orgasm_dict = un_count_orgasm_dict or {}
        if character_id == CHEN_ID and handle_premise.handle_self_orgasm_edge(character_id) and not handle_premise.handle_unconscious_flag_3(character_id):
            for orgasm in ORGASM_PART_PREFIX:
                if orgasm == 3:
                    continue
                normal_count = normal_orgasm_dict.get(orgasm, 0)
                extra_count = extra_orgasm_dict.get(orgasm, 0)
                un_count = un_count_orgasm_dict.get(orgasm, 0)
                if normal_count > 0 or extra_count > 0 or un_count > 0:
                    crossed_parts[orgasm] += normal_count + un_count
        return original_orgasm_settle(character_id, change_data, normal_orgasm_dict, extra_orgasm_dict, un_count_orgasm_dict)

    monkeypatch.setattr(second_behavior, "orgasm_settle", wrapped_orgasm_settle)
    return crossed_parts


def test_edge_roll_happens_once_per_character_per_player_action(loaded99, monkeypatch):
    """
    场景：一次玩家行动内同一角色多部位或跨结算跨级时，窗口内不掷骰，窗口末尾只掷骰一次。
    """
    ctx = loaded99
    from Script.Design import second_behavior
    from Script.System.Instruct_System import handle_instruct

    random.seed(42)
    _place_chen_thresholds(ctx)
    h_orgasm_batch_globals = second_behavior.orgasm_settle.__globals__

    chen_edge_before = _edge_count_snapshot(ctx, CHEN_ID)
    chen_crossed_parts = _count_chen_edge_crossings(ctx, monkeypatch)

    window_end_phase = {"active": False}
    roll_calls = []
    original_judge = second_behavior.judge_orgasm_edge_success
    original_window_end = h_orgasm_batch_globals["settle_pending_edge_judgments_at_window_end"]

    def wrapped_window_end():
        window_end_phase["active"] = True
        try:
            return original_window_end()
        finally:
            window_end_phase["active"] = False

    def wrapped_judge(character_id):
        roll_calls.append((character_id, window_end_phase["active"], _edge_count_snapshot(ctx, character_id)))
        return original_judge(character_id)

    monkeypatch.setitem(h_orgasm_batch_globals, "settle_pending_edge_judgments_at_window_end", wrapped_window_end)
    monkeypatch.setattr(second_behavior, "judge_orgasm_edge_success", wrapped_judge)

    handle_instruct.handle_wait_1_hour()

    assert roll_calls, "窗口末尾应至少对待判角色执行寸止掷骰"
    assert all(is_window_end for _character_id, is_window_end, _edge_count in roll_calls), "寸止掷骰只能发生在窗口末尾 hook 内"

    roll_count_by_character = Counter(character_id for character_id, _is_window_end, _edge_count in roll_calls)
    repeated_rolls = {
        character_id: count
        for character_id, count in roll_count_by_character.items()
        if count > 1
    }
    assert repeated_rolls == {}, f"同一玩家行动窗口内每名角色最多应寸止掷骰一次，实际重复：{repeated_rolls}"

    chen_edge_after = _edge_count_snapshot(ctx, CHEN_ID)
    expected_delta = dict(chen_crossed_parts)
    actual_delta = {
        part: chen_edge_after.get(part, 0) - chen_edge_before.get(part, 0)
        for part in expected_delta
    }
    assert actual_delta == expected_delta, "陈的每个跨级部位 climax_count 都应合并进 orgasm_edge_count"
    chen_roll_snapshots = [edge_count for character_id, _is_window_end, edge_count in roll_calls if character_id == CHEN_ID]
    assert len(chen_roll_snapshots) == 1, "陈在窗口末尾应恰好掷骰一次"
    for part, delta in expected_delta.items():
        assert chen_roll_snapshots[0].get(part, 0) >= chen_edge_before.get(part, 0) + delta, "掷骰时难度应包含本窗口累积"


def test_window_end_edge_failure_releases_accumulated_counts(loaded99, monkeypatch):
    """
    场景：窗口末尾寸止掷骰失败后，旧积攒与本窗口累积一起当场释放并清空状态。
    """
    ctx = loaded99
    from Script.Design import second_behavior

    random.seed(42)
    _place_chen_thresholds(ctx)
    h_orgasm_batch_globals = second_behavior.orgasm_settle.__globals__

    chen_edge_before = _edge_count_snapshot(ctx, CHEN_ID)
    chen_orgasm_before = _orgasm_count_snapshot(ctx, CHEN_ID)
    roll_calls = []

    def forced_failure_judge(character_id):
        roll_calls.append(character_id)
        return False

    monkeypatch.setattr(second_behavior, "judge_orgasm_edge_success", forced_failure_judge)

    first_change = ctx.game_type.CharacterStatusChange()
    second_behavior.orgasm_settle(CHEN_ID, first_change, normal_orgasm_dict={4: 1})

    chen = ctx.cache.character_data[CHEN_ID]
    assert roll_calls == [], "窗口内跨级不应立刻触发寸止掷骰"
    assert chen.h_state.orgasm_edge == 1, "窗口内跨级仍应保持寸止状态等待窗口末尾判定"
    assert chen.h_state.orgasm_edge_count.get(4, 0) >= chen_edge_before.get(4, 0) + 1

    h_orgasm_batch_globals["settle_pending_edge_judgments_at_window_end"]()

    assert roll_calls == [CHEN_ID], "窗口末尾应触发一次被打桩为失败的寸止掷骰"
    assert chen.h_state.orgasm_edge == 0, "窗口末尾失败释放后寸止标记应复位"
    assert _edge_count_snapshot(ctx, CHEN_ID) == {}, "窗口末尾失败释放后寸止计数应清空"
    chen_orgasm_after = _orgasm_count_snapshot(ctx, CHEN_ID)
    actual_release_delta = chen_orgasm_after.get(4, 0) - chen_orgasm_before.get(4, 0)
    assert actual_release_delta >= chen_edge_before.get(4, 0) + 1, "失败释放应包含旧积攒与本窗口累积"


def test_real_window_failure_keeps_release_derivatives_and_output_in_one_response(loaded99, monkeypatch):
    """
    场景：真实一小时玩家行动中插入确定性多部位寸止跨级，窗口末尾失败释放。

    参数：loaded99为真实存档夹具，monkeypatch为pytest夹具；返回值类型：None；
    用途：证明窗口内无寸止文本，末尾只有一次失败提示；同一变化对象完成释放、
    刻印、自动素质和数值输出，下一次真实行动不再泄漏上一窗口输出。
    """
    ctx = loaded99
    from Script.Design import character_behavior, second_behavior, settle_behavior, talk
    from Script.System.Instruct_System import handle_instruct
    from Script.System.Sex_System import group_sex_panel
    from Script.UI.Moudle import draw

    def file_digest(path):
        """参数：path(Path)为存档路径；返回：str为摘要；用途：证明测试没有写回存档。"""
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def queue_snapshot(character_data):
        """参数：character_data为角色数据；返回：dict；用途：记录本批二段与强制队列终态。"""
        return {
            "second": {behavior_id: value for behavior_id, value in character_data.second_behavior.items() if value},
            "must_show": list(character_data.must_show_second_behavior_id_list),
            "must_settle": list(character_data.must_settle_second_behavior_id_list),
        }

    save_paths = [Path("save/99/0"), Path("save/99/1")]
    save_digests = {path: file_digest(path) for path in save_paths}
    chen = ctx.cache.character_data[CHEN_ID]
    player = ctx.cache.character_data[0]
    assert chen.position == player.position and chen.sp_flag.is_h

    # 只保留陈的确定性待判路径，避免存档中其他参与者的既有寸止状态干扰计数。
    for character_id, character_data in ctx.cache.character_data.items():
        if not character_id or not hasattr(character_data, "h_state"):
            continue
        character_data.h_state.orgasm_edge = 0
        character_data.h_state.orgasm_edge_count.clear()
    chen.h_state.orgasm_edge = 1
    for behavior_id in chen.second_behavior:
        chen.second_behavior[behavior_id] = 0
    chen.must_show_second_behavior_id_list.clear()
    chen.must_settle_second_behavior_id_list.clear()
    for orgasm_count in chen.h_state.orgasm_count.values():
        orgasm_count[0] = 0
        orgasm_count[1] = 0
    chen.ability[13] = 0
    chen.talent[31] = 0
    chen.experience[111] = 49
    chen.h_state.shoot_position_body = 2
    player.ability[30] = 0
    monkeypatch.setattr(ctx.cache, "npc_id_got", {0})
    template_panel = group_sex_panel.Edit_Group_Sex_Temple_Panel(80)
    template_panel.reset_template()
    template_panel.change_temple()
    template_panel.reset_template()
    template_panel.change_temple()

    h_globals = second_behavior.orgasm_settle.__globals__
    h_globals["_get_edge_window_results"]().clear()
    injected_release = {1: 3, 2: 1, 4: 1, 5: 1, 23: 1}
    action_index = {"value": 1}
    window_end_phase = {"active": False}
    injected = {"done": False}
    draw_events = []
    talk_events = []
    roll_events = []
    release_calls = []
    derivative_calls = []
    value_output_calls = []

    for draw_class in (draw.NormalDraw, draw.WaitDraw):
        original_draw = draw_class.draw

        def recording_draw(self, *args, __original_draw=original_draw, **kwargs):
            """参数：同真实绘制入口；返回：原返回值；用途：记录文本所属行动、阶段与Web响应。"""
            draw_events.append((action_index["value"], window_end_phase["active"], ctx.cache.web_text_recording_flag, getattr(self, "text", "")))
            return __original_draw(self, *args, **kwargs)

        monkeypatch.setattr(draw_class, "draw", recording_draw)

    original_talk = talk.handle_second_talk

    def recording_talk(character_id, behavior_id):
        """参数：同真实二段口上入口；返回：原返回值；用途：记录刻印与派生输出归属。"""
        talk_events.append((action_index["value"], window_end_phase["active"], ctx.cache.web_text_recording_flag, character_id, behavior_id))
        return original_talk(character_id, behavior_id)

    monkeypatch.setattr(talk, "handle_second_talk", recording_talk)

    original_window_end = h_globals["settle_pending_edge_judgments_at_window_end"]

    def recording_window_end():
        """参数：无；返回：原返回值；用途：标记真实主循环中的窗口末尾响应边界。"""
        window_end_phase["active"] = True
        try:
            return original_window_end()
        finally:
            window_end_phase["active"] = False

    monkeypatch.setitem(h_globals, "settle_pending_edge_judgments_at_window_end", recording_window_end)

    original_character_behavior = character_behavior.character_behavior

    def injecting_character_behavior(character_id, now_time, pl_start_time):
        """参数：同真实角色行为入口；返回：原返回值；用途：在真实玩家窗口内注入确定性寸止跨级。"""
        if character_id == 0 and action_index["value"] == 1 and h_globals["_EDGE_WINDOW_BEHAVIOR_LOOP_ACTIVE"] and not injected["done"]:
            injected["done"] = True
            second_behavior.orgasm_settle(CHEN_ID, ctx.game_type.CharacterStatusChange(), normal_orgasm_dict=injected_release)
        return original_character_behavior(character_id, now_time, pl_start_time)

    monkeypatch.setattr(character_behavior, "character_behavior", injecting_character_behavior)

    original_judge = second_behavior.judge_orgasm_edge_success

    def recording_judge(character_id):
        """参数：角色id；返回：bool；用途：用真实必败概率与真实提示绘制记录窗口末尾唯一判定。"""
        roll_events.append((action_index["value"], window_end_phase["active"], ctx.cache.web_text_recording_flag, character_id, _edge_count_snapshot(ctx, character_id)))
        return original_judge(character_id)

    monkeypatch.setattr(second_behavior, "judge_orgasm_edge_success", recording_judge)

    original_release_settle = h_globals["patched_orgasm_settle"]

    def recording_release_settle(character_id, change_data, normal_orgasm_dict=None, extra_orgasm_dict=None, un_count_orgasm_dict=None):
        """参数：同真实绝顶结算；返回：原返回值；用途：诊断失败释放的唯一调用者、变化对象和队列所有权。"""
        before = queue_snapshot(ctx.cache.character_data[character_id])
        call_data = {
            "action": action_index["value"],
            "window_end": window_end_phase["active"],
            "recording": ctx.cache.web_text_recording_flag,
            "character_id": character_id,
            "change_id": id(change_data),
            "normal": dict(normal_orgasm_dict or {}),
            "extra": dict(extra_orgasm_dict or {}),
            "un_count": dict(un_count_orgasm_dict or {}),
            "edge": ctx.cache.character_data[character_id].h_state.orgasm_edge,
            "stack": "".join(traceback.format_stack(limit=8)),
            "before": before,
        }
        result = original_release_settle(character_id, change_data, normal_orgasm_dict, extra_orgasm_dict, un_count_orgasm_dict)
        call_data["after"] = queue_snapshot(ctx.cache.character_data[character_id])
        release_calls.append(call_data)
        return result

    monkeypatch.setitem(h_globals, "patched_orgasm_settle", recording_release_settle)

    original_derivatives = h_globals["_settle_window_end_release_derivatives"]

    def recording_derivatives(character_id, change_data):
        """参数：角色与变化对象；返回：原返回值；用途：记录同响应派生闭包及其队列终态。"""
        result = original_derivatives(character_id, change_data)
        derivative_calls.append((action_index["value"], window_end_phase["active"], ctx.cache.web_text_recording_flag, character_id, id(change_data), queue_snapshot(ctx.cache.character_data[character_id])))
        return result

    monkeypatch.setitem(h_globals, "_settle_window_end_release_derivatives", recording_derivatives)

    original_collect_values = settle_behavior.collect_web_value_changes

    def recording_collect_values(change_data, character_id):
        """参数：变化对象与角色；返回：原返回值；用途：记录失败释放数值进入当前Web响应。"""
        value_output_calls.append((action_index["value"], window_end_phase["active"], ctx.cache.web_text_recording_flag, character_id, id(change_data), dict(change_data.status_data), dict(change_data.experience)))
        return original_collect_values(change_data, character_id)

    monkeypatch.setattr(settle_behavior, "collect_web_value_changes", recording_collect_values)

    handle_instruct.handle_wait_1_hour()

    assert injected["done"], "确定性跨级必须发生在真实玩家行为循环内部"
    assert len(roll_events) == 1 and roll_events[0][:4] == (1, True, True, CHEN_ID)
    assert roll_events[0][4] == injected_release
    assert len(release_calls) == 1
    release_call = release_calls[0]
    assert release_call["action"] == 1 and release_call["window_end"] and release_call["recording"]
    assert release_call["character_id"] == CHEN_ID
    assert release_call["normal"] == {} and release_call["extra"] == {} and release_call["un_count"] == injected_release
    assert release_call["edge"] == 2
    assert "settle_pending_edge_judgments_at_window_end" in release_call["stack"] and "_release_failed_edge_at_window_end" in release_call["stack"]
    assert release_call["after"] == {"second": {}, "must_show": [], "must_settle": []}
    assert len(derivative_calls) == 1
    assert derivative_calls[0][:5] == (1, True, True, CHEN_ID, release_call["change_id"])
    assert derivative_calls[0][5] == {"second": {}, "must_show": [], "must_settle": []}
    matching_value_outputs = [call for call in value_output_calls if call[0] == 1 and call[3] == CHEN_ID and call[4] == release_call["change_id"]]
    assert len(matching_value_outputs) == 1 and matching_value_outputs[0][1:3] == (True, True)
    assert matching_value_outputs[0][5] and matching_value_outputs[0][6]

    failure_text = f"尝试寸止{chen.name}的绝顶，但失败了"
    failure_draws = [event for event in draw_events if failure_text in event[3]]
    assert len(failure_draws) == 1 and failure_draws[0][:3] == (1, True, True)
    assert not [event for event in draw_events if event[0] == 1 and not event[1] and ("绝顶寸止" in event[3] or failure_text in event[3])]
    assert not [event for event in draw_events if event[0] == 1 and "胸部小绝顶" in event[3]]
    assert chen.ability[13] >= 1
    assert chen.talent[31] == 1
    assert any(event[:4] == (1, True, True, CHEN_ID) and event[4].startswith("happy_mark_") for event in talk_events)
    assert any(event[:3] == (1, True, True) and "获得了[饮精绝顶]" in event[3] for event in draw_events)
    assert chen.h_state.orgasm_edge == 0 and _edge_count_snapshot(ctx, CHEN_ID) == {}
    assert not ctx.cache.web_text_recording_flag

    # 新行动仍走真实窗口，但不得重新输出上一窗口的失败、刻印或素质文本。
    action_index["value"] = 2
    handle_instruct.handle_wait_5_min_in_h()
    assert not [event for event in draw_events if event[0] == 2 and (failure_text in event[3] or "获得了[饮精绝顶]" in event[3])]
    assert not [event for event in talk_events if event[0] == 2 and event[4].startswith("happy_mark_")]
    assert queue_snapshot(chen) == {"second": {}, "must_show": [], "must_settle": []}
    assert {path: file_digest(path) for path in save_paths} == save_digests


def test_window_end_skips_character_after_mid_window_exit_cleanup(loaded99, monkeypatch):
    """
    场景：角色在窗口中途已由退出清算清空寸止状态后，窗口末尾静默跳过。
    """
    ctx = loaded99
    from Script.Design import second_behavior

    random.seed(42)
    _place_chen_thresholds(ctx)
    h_orgasm_batch_globals = second_behavior.orgasm_settle.__globals__

    roll_calls = []
    monkeypatch.setattr(second_behavior, "judge_orgasm_edge_success", lambda character_id: roll_calls.append(character_id) or True)

    first_change = ctx.game_type.CharacterStatusChange()
    second_behavior.orgasm_settle(CHEN_ID, first_change, normal_orgasm_dict={4: 1})

    chen = ctx.cache.character_data[CHEN_ID]
    chen.h_state.orgasm_edge_count.clear()
    chen.h_state.orgasm_edge = 0

    h_orgasm_batch_globals["settle_pending_edge_judgments_at_window_end"]()

    assert roll_calls == [], "退出清算后窗口末尾不应二次寸止判定"
