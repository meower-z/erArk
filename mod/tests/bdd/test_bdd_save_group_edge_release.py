#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
BDD 场景（近真实层）LB-BDD-009：真实实机存档上的群交寸止释放

用真实 Windows 实机存档（槽位99，群交进行中，多名参与者带待处理寸止计数）
驱动已安装的群交结束行为效果529（local_group_edge_release_fix 的包装），
断言包装职责内的精确释放语义：

- 恰好释放 orgasm_edge==1 且有待处理计数的参与者（可露希尔/陈/特蕾西娅/
  食铁兽/清流），计数清零、寸止标记复位；
- 释放按"每计数一次绝顶"结算进入 orgasm_count，且待释放计数≥3时按批处理
  修复的 climax_count>=3 路径追加一次奖励绝顶（3计数 -> +4次）；
- orgasm_edge==2（已在解放态的凯尔希）不在包装范围内——其计数由完整结算
  流程中的批处理 orgasm_settle 释放（由 Web 层全流程场景覆盖）；
- orgasm_edge==1 但无计数的参与者（杜宾等）不做处理，由上游群交结束链清理。

依赖用户实机存档 save/99（gitignore，不随仓库分发），缺失时整模块跳过。

运行方式：.venv/bin/pytest mod/tests/bdd/test_bdd_save_group_edge_release.py -v
"""

import os
import json
from pathlib import Path

import pytest

from mod.tests.bdd.near_real_boot import boot_game_once

_mod_config = json.loads(Path("mod/mod_config.json").read_text(encoding="utf-8"))
pytestmark = [
    pytest.mark.skipif(not os.path.exists(os.path.join("save", "99", "1")), reason="需要用户实机存档 save/99（未随仓库分发）"),
    pytest.mark.skipif("local_group_edge_release_fix" not in _mod_config["enabled_mods"], reason="旧群交寸止释放组件当前已禁用"),
]

BEHAVIOR_EFFECT_GROUP_SEX_END = 529
# 槽位99中 orgasm_edge==1 且有待处理计数的参与者及其计数（清点于2026-07-06）
PENDING_RELEASE = {
    7: {23: 1},          # 可露希尔
    10: {4: 1, 23: 3},   # 陈
    56: {23: 3},         # 特蕾西娅
    241: {23: 1},        # 食铁兽
    385: {23: 1},        # 清流
}
EDGE_ONLY_NO_COUNT = [130, 308, 4080, 4122]  # 杜宾/诗怀雅/林/小满


@pytest.fixture(scope="module")
def loaded99():
    """
    模块级夹具：近真实引导并读入槽位99

    返回值类型：BootContext
    功能描述：桩掉Web等待应答（进程内无客户端，结算路径的 WaitDraw 否则
    会在 askfor_wait 轮询中永久阻塞），随后经真实 input_load_save 读档。
    """
    ctx = boot_game_once(enable_debug=True)
    from Script.Core import flow_handle_web, save_handle

    flow_handle_web.get_wait_response = lambda: True
    save_handle.input_load_save("99")
    return ctx


def _edge_state(ctx, character_id):
    """
    参数：ctx(BootContext)为引导上下文，character_id(int)为角色id；
    返回值类型：tuple，(orgasm_edge, 非零寸止计数dict, orgasm_count副本dict)；
    功能描述：采集断言用的寸止/绝顶状态。
    """
    h_state = ctx.cache.character_data[character_id].h_state
    return (
        h_state.orgasm_edge,
        {k: v for k, v in h_state.orgasm_edge_count.items() if v},
        {k: list(v) for k, v in h_state.orgasm_count.items()},
    )


def test_group_end_effect_releases_pending_edges_on_real_save(loaded99):
    """
    场景：真实存档状态上驱动群交结束效果529完成寸止释放

    验证点：见模块docstring；释放集合、计数清零、每计数一次绝顶、
    ≥3计数的奖励绝顶、edge==2与无计数参与者不在包装范围。
    """
    ctx = loaded99
    from Script.Core import game_type

    effect = ctx.constant.settle_behavior_effect_data[BEHAVIOR_EFFECT_GROUP_SEX_END]
    assert "local_group_edge_release_fix" in effect.__module__, "效果529应为寸止释放包装"

    before = {cid: _edge_state(ctx, cid) for cid in list(PENDING_RELEASE) + EDGE_ONLY_NO_COUNT + [3]}
    # 前置状态与清点一致性自检（存档被外部改动时给出可读失败信息）
    for cid, pending in PENDING_RELEASE.items():
        assert before[cid][0] == 1 and before[cid][1] == pending, f"[{cid}] 存档前置状态与清点不符"
    assert before[3][0] == 2 and before[3][1] == {23: 5}, "凯尔希应处于解放态且带5次计数"

    change_data = game_type.CharacterStatusChange()
    effect(0, 10, change_data, ctx.cache.game_time)

    # 恰好释放5名待释放参与者
    assert set(change_data.target_change.keys()) == set(PENDING_RELEASE), "释放集合应恰为带计数的edge==1参与者"

    for cid, pending in PENDING_RELEASE.items():
        edge, edge_count, orgasm_count = _edge_state(ctx, cid)
        assert edge == 0, f"[{cid}] 释放后寸止标记应复位"
        assert edge_count == {}, f"[{cid}] 释放后计数应清零"
        for part, count in pending.items():
            expected = count + (1 if count >= 3 else 0)  # 批处理修复的≥3计数奖励绝顶
            got = orgasm_count.get(part, [0, 0])[0] - before[cid][2].get(part, [0, 0])[0]
            assert got == expected, f"[{cid}] 部位{part}应结算{expected}次绝顶，实际{got}"

    # edge==2 的凯尔希不在包装范围：状态原样保留，由完整结算流程释放
    assert _edge_state(ctx, 3)[0] == 2
    assert _edge_state(ctx, 3)[1] == {23: 5}

    # edge==1 无计数的参与者不做处理，由上游群交结束链清理
    for cid in EDGE_ONLY_NO_COUNT:
        assert _edge_state(ctx, cid)[0] == before[cid][0], f"[{cid}] 无计数参与者不应被包装改动"
